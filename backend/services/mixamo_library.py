"""
Mixamo / character library index.

Watches assets_library/mixamo/ (and the project's assets/custom/ FBX files). New or changed
FBX files are inspected in ONE headless Blender run: is it a skinned character or an
animation-only clip, bone count + Mixamo bone prefix, frame range, mesh height. Results
are cached in assets_library/mixamo/index.json keyed by size + mtime.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from config import MIXAMO_LIBRARY_DIR, detect_blender_executable
from database import get_settings

INDEX_FILE = MIXAMO_LIBRARY_DIR / "index.json"

_PROBE = r'''
import bpy, json, sys
from mathutils import Vector
paths = json.loads(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8").read())
for p in paths:
    out = {"path": p}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=p, automatic_bone_orientation=True, ignore_leaf_bones=True)
        arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        bones = [b.name for b in arms[0].data.bones] if arms else []
        prefix = next((b.split(":", 1)[0] + ":" for b in bones if ":" in b), "")
        acts = [a for a in bpy.data.actions]
        fr = [int(min(a.frame_range[0] for a in acts)), int(max(a.frame_range[1] for a in acts))] if acts else None
        zs = [(m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box]
        out.update(ok=True, armatures=len(arms), bones=len(bones), bone_prefix=prefix, meshes=len(meshes),
                   verts=sum(len(m.data.vertices) for m in meshes), frame_range=fr,
                   frames=(fr[1] - fr[0] + 1) if fr else 0,
                   height_m=round(max(zs) - min(zs), 3) if zs else None,
                   kind=("character" if meshes and arms else "animation" if arms else "mesh"))
    except Exception as e:
        out.update(ok=False, error=str(e)[:300])
    print("__SK_MIXAMO__" + json.dumps(out), flush=True)
'''


def _load_index() -> dict[str, Any]:
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _key(p: Path) -> str:
    st = p.stat()
    return f"{st.st_size}:{int(st.st_mtime)}"


def _probe(paths: list[Path]) -> dict[str, dict[str, Any]]:
    exe = get_settings().get("blender_path") or detect_blender_executable()
    if not exe or not paths:
        return {}
    tmp = Path(tempfile.mkdtemp(prefix="sk_mixamo_"))
    (tmp / "probe.py").write_text(_PROBE, encoding="utf-8")
    (tmp / "paths.json").write_text(json.dumps([str(p) for p in paths]), encoding="utf-8")
    try:
        proc = subprocess.run([exe, "--background", "--factory-startup", "--python", str(tmp / "probe.py"),
                               "--", str(tmp / "paths.json")], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60 + 30 * len(paths))
        res = {}
        for line in (proc.stdout or "").splitlines():
            if line.startswith("__SK_MIXAMO__"):
                d = json.loads(line[len("__SK_MIXAMO__"):])
                res[d["path"]] = d
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def scan(extra_dirs: Optional[list[Path]] = None, refresh: bool = False) -> dict[str, Any]:
    dirs = [MIXAMO_LIBRARY_DIR] + [d for d in (extra_dirs or []) if d and d.is_dir()]
    files = sorted({p.resolve() for d in dirs for p in d.rglob("*.fbx")})
    index = {} if refresh else _load_index()
    todo = [p for p in files if index.get(str(p), {}).get("key") != _key(p)]
    if todo:
        probed = _probe(todo)
        for p in todo:
            info = probed.get(str(p), {"ok": False, "error": "Blender probe returned nothing"})
            info["key"] = _key(p)
            index[str(p)] = info
    index = {k: v for k, v in index.items() if Path(k).is_file()}
    INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")
    items = []
    for p in files:
        info = index.get(str(p), {})
        items.append({
            "name": p.stem, "path": str(p), "folder": p.parent.name, "size_kb": round(p.stat().st_size / 1024, 1),
            "kind": info.get("kind", "unknown"), "bones": info.get("bones"), "bone_prefix": info.get("bone_prefix"),
            "frames": info.get("frames"), "frame_range": info.get("frame_range"), "height_m": info.get("height_m"),
            "verts": info.get("verts"), "ok": info.get("ok", False), "error": info.get("error"),
        })
    return {
        "folder": str(MIXAMO_LIBRARY_DIR),
        "characters": [i for i in items if i["kind"] == "character"],
        "animations": [i for i in items if i["kind"] == "animation"],
        "other": [i for i in items if i["kind"] not in ("character", "animation")],
        "probed_now": len(todo),
    }


def import_files(paths: list[Path]) -> list[str]:
    """Copy FBX files into the library (e.g. downloads from mixamo.com)."""
    out = []
    for p in paths:
        if p.suffix.lower() == ".fbx" and p.is_file():
            dest = MIXAMO_LIBRARY_DIR / p.name
            if not dest.exists():
                shutil.copy2(p, dest)
            out.append(str(dest))
    return out
