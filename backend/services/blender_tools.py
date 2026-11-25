"""
Live Blender tools for the Claude Director (registered on the shared ToolRegistry).
They talk to the open Blender through services.blender_bridge.
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

from database import get_project
from services.blender_bridge import BridgeError, bridge
from services.claude_director import REGISTRY, ToolInputError, ToolOutput, TurnContext


def _project_dir(ctx: TurnContext) -> Path:
    proj = get_project(ctx.project_id) or {}
    return Path(proj.get("target_folder") or ".")


async def _call(cmd: str, params: dict[str, Any] | None = None, timeout: float = 300.0) -> Any:
    try:
        return await bridge.call(cmd, params, timeout=timeout)
    except BridgeError as e:
        raise ToolInputError(str(e)) from e


async def _ensure_project_open(ctx: TurnContext) -> None:
    """Make sure the live Blender is working on THIS project's project.blend."""
    st = await bridge.status()
    if not st.get("connected"):
        raise ToolInputError("Blender is not connected. Ask the user to click “Launch & Connect Blender” "
                             "in the header, then try again.")
    pdir = _project_dir(ctx)
    await _call("execute_python", {"code": f"zdf.configure(project_dir={str(pdir)!r}, assets_dir={str(pdir / 'assets')!r})"}, 30)


async def t_scene_info(args: dict[str, Any], ctx: TurnContext) -> ToolOutput:
    await _ensure_project_open(ctx)
    info = await _call("get_scene_info", {"limit": int(args.get("limit", 120))}, 60)
    return json.dumps(info, ensure_ascii=False)[:60000]


async def t_execute(args: dict[str, Any], ctx: TurnContext) -> ToolOutput:
    code = args.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ToolInputError("`code` must be a non-empty string of Python.")
    await _ensure_project_open(ctx)
    await ctx.emit({"type": "notice", "text": f"Blender: {args.get('description') or 'running code'}…"})
    res = await _call("execute_python", {"code": code}, float(args.get("timeout", 300)))
    parts = []
    if res.get("stdout"):
        parts.append("stdout:\n" + res["stdout"])
    if res.get("stderr"):
        parts.append("stderr:\n" + res["stderr"])
    if not res.get("ok"):
        parts.append(f"ERROR: {res.get('error')}\n{res.get('traceback', '')}")
        raise ToolInputError("\n\n".join(parts) + "\n\nThe scene was left as it was before the error "
                             "(objects created before the failing line still exist). Fix the code and run it again.")
    if res.get("result") is not None:
        parts.append("result = " + json.dumps(res["result"], ensure_ascii=False)[:20000])
    parts.append(f"OK in {res.get('seconds')} s.")
    return "\n\n".join(parts)


async def t_capture(args: dict[str, Any], ctx: TurnContext) -> ToolOutput:
    await _ensure_project_open(ctx)
    params = {"width": int(args.get("width", 540))}
    if args.get("frame") is not None:
        params["frame"] = int(args["frame"])
    if args.get("camera"):
        params["camera"] = args["camera"]
    res = await _call("capture_viewport", params, 300)
    png = base64.b64decode(res["png_base64"])
    out_dir = _project_dir(ctx) / "previews" / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"capture_{int(time.time() * 1000)}.png"
    (out_dir / name).write_bytes(png)
    url = f"/api/projects/{ctx.project_id}/media/live/{name}"
    ctx.images.append(url)
    await ctx.emit({"type": "viewport_capture", "url": url, "frame": res.get("frame"), "camera": res.get("camera")})
    return [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": res["png_base64"]}},
        {"type": "text", "text": f"Camera view of '{res.get('camera')}' at frame {res.get('frame')} "
                                 f"(9:16 frame, captions will sit at ~78% height). Critique framing, scale, "
                                 f"materials, lighting and story before moving on."},
    ]


async def t_import(args: dict[str, Any], ctx: TurnContext) -> ToolOutput:
    path = args.get("path", "")
    if not path or not Path(path).is_file():
        raise ToolInputError(f"File not found: {path!r}. Use a path from the asset library or the project's assets/custom folder.")
    await _ensure_project_open(ctx)
    res = await _call("import_asset", args, 600)
    return json.dumps(res)


async def t_save(args: dict[str, Any], ctx: TurnContext) -> ToolOutput:
    await _ensure_project_open(ctx)
    path = str(_project_dir(ctx) / "project.blend")
    res = await _call("save_project", {"path": path, "pack": bool(args.get("pack", False))}, 300)
    return f"Saved {res.get('file')}"


async def t_list_assets(args: dict[str, Any], ctx: TurnContext) -> ToolOutput:
    import asyncio
    from services import mixamo_library
    from services.attachments import list_attachments
    pdir = _project_dir(ctx)
    custom = pdir / "assets" / "custom"
    lib = await asyncio.to_thread(mixamo_library.scan, [custom])
    files = []
    if custom.is_dir():
        files = [{"path": str(p), "size_kb": round(p.stat().st_size / 1024, 1)} for p in sorted(custom.rglob("*"))
                 if p.is_file() and p.suffix.lower() in {".blend", ".glb", ".gltf", ".fbx", ".obj", ".png", ".jpg", ".hdr", ".exr"}]
    refs = []
    for a in list_attachments(ctx.project_id):
        r = {"file": a["filename"], "purpose": a["purpose"], "kind": a["kind"], "status": a["status"]}
        vo = a["meta"].get("voiceover")
        if vo:
            r["voiceover"] = {"applied_as_narration": True, "seconds": vo["total_duration"], "transcript": vo["transcript"]}
        refs.append(r)

    def slim(items):
        return [{k: i[k] for k in ("name", "path", "frames", "height_m", "bone_prefix") if i.get(k) is not None} for i in items]
    return json.dumps({
        "mixamo_characters": slim(lib["characters"]),
        "mixamo_animations": slim(lib["animations"]),
        "project_custom_assets": files,
        "attachments": refs,
        "hint": "Characters: blender_import_asset(kind='mixamo', path=<character>, anim_path=<animation>) or "
                "zdf.import_mixamo_character / zdf.add_mixamo_animation in code. If no character exists, ask the "
                "user to download one from mixamo.com (FBX Binary, With Skin) into the Mixamo library.",
    }, ensure_ascii=False)[:40000]


def register_blender_tools() -> None:
    REGISTRY.register(
        "list_assets",
        "List usable assets: Mixamo characters and animation clips in the library (with frame counts and heights), "
        "the project's custom asset files (user uploads), and chat attachments. Use paths from here with "
        "blender_import_asset or in Blender code.",
        {"type": "object", "properties": {}},
        t_list_assets, label="Listing assets")
    REGISTRY.register(
        "blender_get_scene_info",
        "Inspect the LIVE Blender session: file, frame range, cameras, timeline markers, collections, objects "
        "(transforms, dimensions, materials, modifiers). Use before editing an existing scene.",
        {"type": "object", "properties": {"limit": {"type": "integer", "description": "max objects listed (default 120)"}}},
        t_scene_info, label="Inspecting Blender scene")
    REGISTRY.register(
        "blender_execute_python",
        "Run Python inside the LIVE open Blender (the user watches it happen). `bpy`, `zdf` (zdf_helpers), "
        "`math`, `mathutils`, `Vector` are pre-imported and the namespace persists between calls. Set a variable "
        "named `result` to return data. Build one shot or one asset per call, using zdf helpers and real modeling "
        "(skill 02). Each call is one undo step for the user.",
        {"type": "object", "properties": {
            "description": {"type": "string", "description": "Short label shown to the user, e.g. 'Model the glazed bowl'"},
            "code": {"type": "string", "description": "Python source to execute"},
            "timeout": {"type": "number", "description": "seconds (default 300)"}},
         "required": ["description", "code"]},
        t_execute, label="Running code in Blender")
    REGISTRY.register(
        "blender_capture_viewport",
        "Render the camera view of the LIVE scene (fast EEVEE, 9:16) and return the image so you can SEE it. "
        "Mandatory after building or changing a hero asset or shot (skill 02 §6): critique and iterate.",
        {"type": "object", "properties": {
            "frame": {"type": "integer", "description": "frame to show (default: current). Pick a frame AFTER pop-in "
                                                       "animations finish (≥ their start_frame + 8), e.g. ~60% into the shot; "
                                                       "check the first and last frame of camera moves too."},
            "camera": {"type": "string", "description": "camera object name (default: the shot camera at that frame)"},
            "width": {"type": "integer", "description": "pixels wide, 270–1080 (default 540)"}}},
        t_capture, label="Capturing camera view")
    REGISTRY.register(
        "blender_import_asset",
        "Import a model file into the LIVE scene with clean scale and placement. kind='asset' for .blend/.glb/.gltf/"
        ".fbx/.obj props (normalised to target_height metres), kind='mixamo' for a Mixamo character FBX "
        "(optional anim_path for its first clip).",
        {"type": "object", "properties": {
            "path": {"type": "string"}, "kind": {"type": "string", "enum": ["asset", "mixamo"]},
            "anim_path": {"type": "string"}, "name": {"type": "string"}, "collection": {"type": "string"},
            "target_height": {"type": "number"}, "start_frame": {"type": "integer"},
            "location": {"type": "array", "items": {"type": "number"}},
            "rotation": {"type": "array", "items": {"type": "number"}}},
         "required": ["path"]},
        t_import, label="Importing asset")
    REGISTRY.register(
        "blender_save_project",
        "Save the LIVE session to <project>/project.blend (pack=true also embeds textures).",
        {"type": "object", "properties": {"pack": {"type": "boolean"}}},
        t_save, label="Saving project.blend")
