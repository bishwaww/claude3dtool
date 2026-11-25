"""
Media analysis for attachments and custom voiceovers.

- decode_audio_16k(): ffmpeg -> 16 kHz mono float32 (we never use PyAV: the venv's PyAV
  build breaks faster-whisper's own decoder).
- transcribe(): faster-whisper with word timestamps -> the same timestamps.json schema the
  ElevenLabs path writes ({"words": [{"word","start","end"}], "total_duration", ...}).
- analyze_reference_video(): duration/fps/size, shot-change times, keyframes, a contact
  sheet for Claude's vision, backdrop colour samples, and a transcript with pacing stats.
- align_storyboard_to_words(): lock storyboard scenes to the words actually spoken.
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Optional

import numpy as np

from database import get_settings

_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "ffprobe"
_model_lock = threading.Lock()
_models: dict[str, Any] = {}


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def probe(path: Path) -> dict[str, Any]:
    p = _run([_FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], 60)
    try:
        data = json.loads(p.stdout.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError:
        data = {}
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    fps = 0.0
    if v.get("r_frame_rate") and "/" in v["r_frame_rate"]:
        n, d = v["r_frame_rate"].split("/")
        fps = round(float(n) / max(1.0, float(d)), 3)
    return {
        "duration": float(data.get("format", {}).get("duration") or 0.0),
        "width": int(v.get("width") or 0), "height": int(v.get("height") or 0), "fps": fps,
        "has_video": bool(v), "has_audio": bool(a),
    }


# ------------------------------------------------------------------------------
# Speech
# ------------------------------------------------------------------------------

def decode_audio_16k(path: Path) -> np.ndarray:
    p = _run([_FFMPEG, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], 900)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg could not decode audio: {p.stderr.decode('utf-8', 'replace')[-400:]}")
    return np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768.0


def _whisper(model_size: str):
    with _model_lock:
        if model_size not in _models:
            from faster_whisper import WhisperModel
            _models[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
        return _models[model_size]


def transcribe(path: Path, model_size: Optional[str] = None, language: Optional[str] = None) -> dict[str, Any]:
    """Word-level transcript in the studio's timestamps.json schema."""
    size = model_size or get_settings().get("whisper_model") or "small.en"
    audio = decode_audio_16k(path)
    if audio.size == 0:
        raise RuntimeError("The file has no audio.")
    model = _whisper(size)
    segments, info = model.transcribe(audio, word_timestamps=True, vad_filter=False,
                                      language=language or ("en" if size.endswith(".en") else None))
    words = []
    for seg in segments:
        for w in seg.words or []:
            tok = w.word.strip()
            if tok:
                words.append({"word": tok, "start": round(float(w.start), 3), "end": round(float(w.end), 3)})
    total = round(len(audio) / 16000.0, 3)
    speech = (words[-1]["end"] - words[0]["start"]) if words else 0.0
    pauses = [round(b["start"] - a["end"], 2) for a, b in zip(words, words[1:]) if b["start"] - a["end"] > 0.35]
    return {
        "text": " ".join(w["word"] for w in words),
        "language": getattr(info, "language", None),
        "total_duration": total,
        "words": words,
        "stats": {
            "word_count": len(words),
            "speech_start": words[0]["start"] if words else None,
            "wpm": round(60 * len(words) / speech) if speech > 1 else None,
            "long_pauses": len(pauses),
        },
        "source": "faster-whisper:" + size,
    }


# ------------------------------------------------------------------------------
# Reference video analysis
# ------------------------------------------------------------------------------

def _scene_cuts(path: Path, threshold: float = 0.22) -> list[float]:
    p = _run([_FFMPEG, "-v", "info", "-i", str(path), "-vf", f"scale=270:-2,select='gt(scene,{threshold})',showinfo",
              "-an", "-f", "null", "-"], 900)
    times = [float(t) for t in re.findall(r"pts_time:([0-9.]+)", p.stderr.decode("utf-8", "replace"))]
    merged: list[float] = []
    for t in times:  # ignore flashes / fast motion shorter than 0.4 s
        if not merged or t - merged[-1] >= 0.4:
            merged.append(round(t, 2))
    return merged


def _grab_frame(path: Path, t: float, out: Path, width: int = 360) -> bool:
    p = _run([_FFMPEG, "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
              "-vf", f"scale={width}:-2", "-q:v", "3", str(out)], 120)
    return p.returncode == 0 and out.is_file()


def analyze_reference_video(path: Path, out_dir: Path, max_frames: int = 16) -> dict[str, Any]:
    from PIL import Image, ImageDraw, ImageFont

    out_dir.mkdir(parents=True, exist_ok=True)
    meta = probe(path)
    dur = meta["duration"] or 0.0
    cuts = _scene_cuts(path) if meta["has_video"] else []

    # keyframes: one per ~1.25 s pace beat, capped, always including the first frame
    n = max(1, min(max_frames, int(dur / 1.25) + 1)) if dur else 1
    times = sorted({round(min(dur - 0.05, i * dur / n), 2) for i in range(n)} if dur else {0.0})
    frames = []
    for i, t in enumerate(times):
        f = out_dir / f"frame_{i:02d}_{t:06.2f}s.jpg"
        if meta["has_video"] and _grab_frame(path, t, f):
            frames.append({"t": t, "path": str(f)})

    # contact sheet (labelled), sized for Claude vision (long side <= 1568 px)
    sheet_path = None
    backdrop = []
    if frames:
        ims = [Image.open(fr["path"]).convert("RGB") for fr in frames]
        w, h = ims[0].size
        cols = min(6, len(ims))
        rows = (len(ims) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * w, rows * h), (0, 0, 0))
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", max(14, w // 14))
        except Exception:
            font = ImageFont.load_default()
        for i, (im, fr) in enumerate(zip(ims, frames)):
            x, y = (i % cols) * w, (i // cols) * h
            sheet.paste(im, (x, y))
            draw.rectangle([x, y, x + w // 3, y + w // 11], fill=(0, 0, 0))
            draw.text((x + 4, y + 2), f"{fr['t']:.1f}s", fill=(255, 255, 255), font=font)
            top = im.crop((0, 0, w, max(1, h // 12))).resize((1, 1)).getpixel((0, 0))
            backdrop.append("#%02X%02X%02X" % top)
        scale = min(1.0, 1568 / max(sheet.size))
        if scale < 1:
            sheet = sheet.resize((int(sheet.width * scale), int(sheet.height * scale)), Image.LANCZOS)
        sheet_path = out_dir / "contact_sheet.jpg"
        sheet.save(sheet_path, quality=86)

    transcript = None
    if meta["has_audio"]:
        try:
            transcript = transcribe(path)
        except Exception as e:
            transcript = {"error": str(e)}

    shots = [round(b - a, 2) for a, b in zip([0.0] + cuts, cuts + [dur])] if dur else []
    analysis = {
        "file": str(path),
        **meta,
        "hard_cuts": cuts,
        "shot_lengths": shots,
        "median_shot": sorted(shots)[len(shots) // 2] if shots else None,
        "keyframes": frames,
        "contact_sheet": str(sheet_path) if sheet_path else None,
        "top_band_colors": backdrop,
        "transcript": transcript,
    }
    (out_dir / "analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    return analysis


def video_analysis_text(a: dict[str, Any], name: str) -> str:
    t = a.get("transcript") or {}
    lines = [
        f"Reference video '{name}': {a.get('duration', 0):.1f} s, {a.get('width')}x{a.get('height')} @ {a.get('fps')} fps.",
        f"Hard cuts at: {a.get('hard_cuts') or 'none detected (continuous camera moves / match cuts)'}; "
        f"median shot {a.get('median_shot')} s.",
        f"Top-band (backdrop) colours over time: {', '.join(a.get('top_band_colors', [])[:16])}.",
        "The attached contact sheet shows the video every ~1.25 s (timestamps in the corner of each frame).",
    ]
    if t.get("words"):
        st = t.get("stats", {})
        lines.append(f"Narration ({st.get('word_count')} words, ~{st.get('wpm')} wpm, starts at {st.get('speech_start')} s, "
                     f"{st.get('long_pauses')} pauses > 0.35 s):\n\"{t.get('text')}\"")
    elif t.get("error"):
        lines.append(f"(Transcript failed: {t['error']})")
    else:
        lines.append("(No speech in the audio track.)")
    return "\n".join(lines)


# ------------------------------------------------------------------------------
# Storyboard <-> spoken words alignment
# ------------------------------------------------------------------------------

def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def align_storyboard_to_words(storyboard: dict[str, Any], ts: dict[str, Any], fps: int = 30,
                              adopt_spoken_text: bool = True) -> dict[str, Any]:
    """
    Lock scene timing to a real voiceover. Scene narration words are matched to the
    spoken words with difflib (handles ad-libs, skipped or reworded lines), so each
    scene starts on the first spoken word that belongs to it. With adopt_spoken_text the
    scene narration is replaced by what was actually said (captions follow the audio).
    """
    words = ts.get("words", [])
    scenes = storyboard.get("scenes", [])
    if not words or not scenes:
        return storyboard

    script_tokens: list[str] = []
    owner: list[int] = []
    for i, s in enumerate(scenes):
        for w in str(s.get("narration", "")).split():
            script_tokens.append(_norm(w))
            owner.append(i)
    spoken = [_norm(w["word"]) for w in words]

    # map each spoken word to a scene via the matching blocks
    spoken_scene = [-1] * len(spoken)
    sm = difflib.SequenceMatcher(a=script_tokens, b=spoken, autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            spoken_scene[blk.b + k] = owner[blk.a + k]
    # fill unmatched spoken words from the previous matched scene (monotonic)
    cur = 0
    for j in range(len(spoken)):
        if spoken_scene[j] < cur:
            spoken_scene[j] = cur
        cur = spoken_scene[j]

    n = len(scenes)
    first_word = [None] * n
    for j, sc in enumerate(spoken_scene):
        if first_word[sc] is None:
            first_word[sc] = j
    # scenes the speaker skipped get a share of their neighbour's time
    for i in range(n):
        if first_word[i] is None:
            first_word[i] = first_word[i - 1] if i > 0 and first_word[i - 1] is not None else 0

    total = float(ts.get("total_duration") or words[-1]["end"] + 0.4)
    starts = [0.0] + [float(words[first_word[i]]["start"]) for i in range(1, n)]
    for i in range(1, n):  # keep monotonic with a minimum of 0.5 s per scene
        starts[i] = max(starts[i], starts[i - 1] + 0.5)
    ends = starts[1:] + [max(total, starts[-1] + 0.8)]

    for i, s in enumerate(scenes):
        s["start_sec"], s["end_sec"] = round(starts[i], 3), round(ends[i], 3)
        s["duration_sec"] = round(ends[i] - starts[i], 3)
        s["start_frame"] = int(round(starts[i] * fps)) + 1
        s["end_frame"] = int(round(ends[i] * fps))
        if adopt_spoken_text:
            spoken_words = [words[j]["word"] for j, sc in enumerate(spoken_scene) if sc == i]
            if spoken_words:
                s["narration"] = " ".join(spoken_words)
    for a, b in zip(scenes, scenes[1:]):
        b["start_frame"] = a["end_frame"] + 1
    storyboard["fps"] = fps
    storyboard["total_duration_sec"] = round(ends[-1], 3)
    storyboard["full_narration"] = " ".join(str(s.get("narration", "")) for s in scenes)
    return storyboard
