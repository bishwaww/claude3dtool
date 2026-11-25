"""
Chat attachments (Claude Desktop-style paperclip / drag-and-drop).

kind      purpose (default)   stored at                                  given to Claude as
image     reference           <target>/references/                        image block
image     asset | logo        <target>/assets/custom/ (logo -> logo.png)  text (path) / branding regenerated
video     reference           <target>/references/<id>/ (+ analysis)      contact-sheet image + analysis text
audio     voiceover           <target>/audio/uploads/                     text (transcript, re-timed storyboard)
model     asset               <target>/assets/custom/                     text (path for blender_import_asset)
"""
from __future__ import annotations

import base64
import io
import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from database import get_conn, get_project, update_project
from services import media_analysis as ma

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
MODEL_EXT = {".blend", ".glb", ".gltf", ".fbx", ".obj", ".stl", ".usd", ".usdz", ".hdr", ".exr", ".zip"}
PURPOSES = {"reference", "asset", "logo", "voiceover"}


def kind_of(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in MODEL_EXT:
        return "model"
    return "other"


def default_purpose(kind: str) -> str:
    return {"image": "reference", "video": "reference", "audio": "voiceover", "model": "asset"}.get(kind, "asset")


def _safe_name(name: str) -> str:
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" .") or "file"
    return f"{stem[:80]}{ext}"


def _row(r) -> dict[str, Any]:
    d = dict(r)
    d["meta"] = json.loads(d.pop("meta_json") or "{}")
    return d


def get_attachment(att_id: str) -> Optional[dict[str, Any]]:
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
        return _row(r) if r else None
    finally:
        conn.close()


def list_attachments(project_id: str) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        return [_row(r) for r in conn.execute(
            "SELECT * FROM attachments WHERE project_id = ? ORDER BY created_at", (project_id,)).fetchall()]
    finally:
        conn.close()


def _save_row(att: dict[str, Any]) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO attachments(id, project_id, kind, purpose, filename, path, status, meta_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (att["id"], att["project_id"], att["kind"], att["purpose"], att["filename"], att["path"],
             att.get("status", "ready"), json.dumps(att.get("meta", {})), att["created_at"]))
        conn.commit()
    finally:
        conn.close()


def store_upload(project: dict[str, Any], filename: str, data: bytes, purpose: Optional[str] = None) -> dict[str, Any]:
    kind = kind_of(filename)
    purpose = purpose if purpose in PURPOSES else default_purpose(kind)
    if purpose == "voiceover" and kind not in ("audio", "video"):
        raise ValueError("A voiceover must be an audio (or video) file.")
    if purpose == "logo" and kind != "image":
        raise ValueError("A logo must be an image file.")
    root = Path(project["target_folder"])
    att_id = uuid.uuid4().hex[:12]
    name = _safe_name(filename)
    if purpose == "reference":
        dest = root / "references" / f"{att_id}_{name}"
    elif purpose == "voiceover":
        dest = root / "audio" / "uploads" / name
    elif purpose == "logo":
        dest = root / "assets" / "custom" / f"logo_source{Path(name).suffix}"
    else:
        dest = root / "assets" / "custom" / name
        if dest.exists():
            dest = dest.with_name(f"{dest.stem}_{att_id[:4]}{dest.suffix}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    att = {"id": att_id, "project_id": project["id"], "kind": kind, "purpose": purpose, "filename": name,
           "path": str(dest), "status": "processing", "meta": {"bytes": len(data)},
           "created_at": datetime.now(timezone.utc).isoformat()}
    _save_row(att)
    return att


# ------------------------------------------------------------------------------
# Processing (runs in a worker thread)
# ------------------------------------------------------------------------------

def _claude_image(src: Path, out: Path, max_side: int = 1568) -> dict[str, Any]:
    from PIL import Image
    im = Image.open(src)
    im = im.convert("RGB")
    w, h = im.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1:
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    im.save(out, "JPEG", quality=88)
    return {"width": w, "height": h, "claude_path": str(out)}


def apply_voiceover(project_id: str, src: Path) -> dict[str, Any]:
    """Make `src` the project's narration: narration.mp3 + word timestamps + re-timed storyboard."""
    project = get_project(project_id)
    if not project:
        raise ValueError("Project not found.")
    audio_dir = Path(project["target_folder"]) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    mp3 = audio_dir / "narration.mp3"
    p = subprocess.run([ma._FFMPEG, "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "2", "-ar", "44100",
                        "-b:a", "192k", str(mp3)], capture_output=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f"Could not convert the voiceover: {p.stderr.decode('utf-8', 'replace')[-300:]}")
    ts = ma.transcribe(src)
    ts.update({"voice_id": "uploaded", "uploaded_file": src.name})
    (audio_dir / "timestamps.json").write_text(json.dumps(ts, indent=2), encoding="utf-8")

    sb = project.get("storyboard") or {}
    aligned = False
    if sb.get("scenes"):
        sb = ma.align_storyboard_to_words(sb, ts, fps=int(sb.get("fps", 30)))
        update_project(project_id, storyboard=sb, status="voice_synced")
        aligned = True
    try:
        from services.pipeline_manager import save_project_meta_file
        save_project_meta_file(get_project(project_id))  # type: ignore[arg-type]
    except Exception:
        pass
    return {"transcript": ts["text"], "stats": ts["stats"], "total_duration": ts["total_duration"],
            "language": ts.get("language"), "aligned_storyboard": aligned,
            "scenes": len(sb.get("scenes", [])) if aligned else 0}


def process_attachment(att_id: str) -> dict[str, Any]:
    att = get_attachment(att_id)
    if att is None:
        raise ValueError("Attachment not found.")
    src = Path(att["path"])
    meta = dict(att["meta"])
    try:
        if att["purpose"] == "reference" and att["kind"] == "image":
            meta.update(_claude_image(src, src.with_name(src.stem + "_claude.jpg")))
        elif att["purpose"] == "reference" and att["kind"] == "video":
            meta["analysis"] = ma.analyze_reference_video(src, src.parent / f"{att['id']}_analysis")
        elif att["purpose"] == "voiceover":
            meta["voiceover"] = apply_voiceover(att["project_id"], src)
        elif att["purpose"] == "logo":
            from PIL import Image
            from services.branding import prepare_branding_assets
            logo = src.with_name("logo.png")
            Image.open(src).convert("RGBA").save(logo, "PNG")
            meta["branding"] = sorted(Path(p).name for p in prepare_branding_assets(src.parent.parent, logo, force=True).values())
            meta["logo_path"] = str(logo)
        elif att["kind"] == "image":
            meta.update(_claude_image(src, src.with_name(src.stem + "_preview.jpg"), 512))
        att.update(status="ready", meta=meta)
    except Exception as e:
        meta["error"] = f"{type(e).__name__}: {e}"
        att.update(status="error", meta=meta)
    _save_row(att)
    return att


# ------------------------------------------------------------------------------
# What Claude receives
# ------------------------------------------------------------------------------

def _img_block(path: Path, media_type: str = "image/jpeg") -> dict[str, Any]:
    return {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                       "data": base64.standard_b64encode(path.read_bytes()).decode("ascii")}}


def content_blocks(att_ids: list[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for att_id in att_ids:
        att = get_attachment(att_id)
        if att is None:
            continue
        m, name = att["meta"], att["filename"]
        if att["status"] == "error":
            blocks.append({"type": "text", "text": f"[Attachment '{name}' could not be processed: {m.get('error')}]"})
            continue
        if att["purpose"] == "reference" and att["kind"] == "image" and m.get("claude_path"):
            blocks.append({"type": "text", "text": f"[Reference image: {name}]"})
            blocks.append(_img_block(Path(m["claude_path"])))
        elif att["purpose"] == "reference" and att["kind"] == "video" and m.get("analysis"):
            a = m["analysis"]
            if a.get("contact_sheet"):
                blocks.append(_img_block(Path(a["contact_sheet"])))
            blocks.append({"type": "text", "text": "[Reference video attached]\n" + ma.video_analysis_text(a, name)
                           + "\nUse it as a style/pacing reference: match its shot rhythm, camera moves, framing, colours "
                             "and narration style where the user asks."})
        elif att["purpose"] == "voiceover" and m.get("voiceover"):
            v = m["voiceover"]
            st = v["stats"]
            msg = (f"[Voiceover uploaded: {name} — {v['total_duration']:.1f} s, {st.get('word_count')} words, "
                   f"~{st.get('wpm')} wpm. It is now the project narration (audio/narration.mp3 + word-level "
                   f"audio/timestamps.json).]\nTranscript: \"{v['transcript']}\"\n")
            if v["aligned_storyboard"]:
                msg += ("The existing storyboard scenes were re-timed to these spoken words and their narration now "
                        "matches what was said. Keep scene boundaries on natural phrase breaks if you edit.")
            else:
                msg += ("There is no storyboard yet: build it with update_storyboard so the scenes' narration, in order, "
                        "is exactly this transcript split into 1.25–3 s phrases; durations will lock to the audio.")
            blocks.append({"type": "text", "text": msg})
        elif att["purpose"] == "logo":
            blocks.append({"type": "text", "text": f"[Logo uploaded: {name}. Brand textures were regenerated with it "
                                                    f"(assets/branding/: {', '.join(m.get('branding', []))}). Use it "
                                                    f"diegetically via zdf branding helpers.]"})
            if m.get("logo_path"):
                blocks.append(_img_block(Path(m["logo_path"]), "image/png"))
        else:
            blocks.append({"type": "text", "text": f"[3D/asset file added: {att['path']} ({att['kind']}). Import it into "
                                                    f"the live scene with blender_import_asset (kind='mixamo' for a Mixamo "
                                                    f"character FBX), or use the path in a scene script.]"})
            if att["kind"] == "image" and m.get("claude_path"):
                blocks.append(_img_block(Path(m["claude_path"])))
    return blocks


def public_view(att: dict[str, Any]) -> dict[str, Any]:
    """What the UI needs (no absolute internals beyond the file path)."""
    m = att["meta"]
    out = {k: att[k] for k in ("id", "kind", "purpose", "filename", "status", "path")}
    out["error"] = m.get("error")
    if att["kind"] in ("image",) or (att["kind"] == "video" and m.get("analysis", {}).get("contact_sheet")):
        out["thumb_url"] = f"/api/attachments/{att['id']}/thumb"
    if m.get("voiceover"):
        out["summary"] = f"{m['voiceover']['total_duration']:.1f}s · {m['voiceover']['stats'].get('word_count')} words"
    elif m.get("analysis"):
        a = m["analysis"]
        t = a.get("transcript") or {}
        out["summary"] = f"{a.get('duration', 0):.1f}s · {len(a.get('keyframes', []))} frames" + (
            f" · {t.get('stats', {}).get('wpm')} wpm" if t.get("words") else "")
    return out


def thumb_path(att: dict[str, Any]) -> Optional[Path]:
    m = att["meta"]
    for p in (m.get("claude_path"), (m.get("analysis") or {}).get("contact_sheet"), m.get("logo_path"),
              att["path"] if att["kind"] == "image" else None):
        if p and Path(p).is_file():
            return Path(p)
    return None
