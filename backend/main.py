from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

# Ensure backend directory is on sys.path regardless of launch CWD
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from blender_engine.blenderkit_setup import (
    get_blenderkit_status,
    install_and_enable_blenderkit,
    probe_blender_environment,
)
from blender_engine.runner import BlenderRunner
from config import (
    CLAUDE_MODELS,
    DEFAULT_BLENDERKIT_SOURCE,
    MIXAMO_LIBRARY_DIR,
    detect_blender_executable,
    detect_ffmpeg_executable,
)
from database import (
    add_message,
    create_project,
    delete_project,
    get_messages,
    get_project,
    get_settings,
    get_token_usage_summary,
    init_db,
    list_projects,
    save_settings,
    update_project,
)
from models import (
    BuildRequest,
    ChatRequest,
    CreateProjectRequest,
    RenderFinalRequest,
    SettingsPayload,
    UpdateProjectRequest,
    ValidatePathRequest,
    VoicePreviewRequest,
)
from services.asset_manager import AssetManager
from services.claude_director import normalize_storyboard, run_chat_turn
from services.elevenlabs_service import ElevenLabsService
from services.model_catalog import list_models
from services import blender_bridge as live_blender
from services.blender_tools import register_blender_tools

register_blender_tools()
from services.pipeline_manager import (
    PipelineManager,
    ensure_project_folder_structure,
    save_project_meta_file,
)

init_db()

app = FastAPI(
    title="Stick Knowledge 3D Studio API",
    version="1.0.0",
    description="Local AI-Powered Zack D. Films-Style Blender 3D Explainer Production Suite",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# REAL-TIME WEBSOCKET HUB
# ==============================================================================

class ConnectionHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, project_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(project_id, set()).add(ws)

    def disconnect(self, project_id: str, ws: WebSocket) -> None:
        if project_id in self._connections:
            self._connections[project_id].discard(ws)

    async def broadcast(self, project_id: str, payload: dict[str, Any]) -> None:
        targets = list(self._connections.get(project_id, set())) + list(
            self._connections.get("global", set())
        )
        dead: list[tuple[str, WebSocket]] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append((project_id, ws))
        for pid, ws in dead:
            self.disconnect(pid, ws)


hub = ConnectionHub()
pipeline = PipelineManager(emit=hub.broadcast)
asset_manager = AssetManager()


@app.websocket("/ws/{project_id}")
async def websocket_endpoint(ws: WebSocket, project_id: str):
    await hub.connect(project_id, ws)
    try:
        while True:
            # Keepalive ping listener
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(project_id, ws)
    except Exception:
        hub.disconnect(project_id, ws)


# ==============================================================================
# SYSTEM, SETTINGS & BLENDERKIT ENDPOINTS
# ==============================================================================

@app.get("/api/health")
async def health():
    settings = get_settings()
    return {
        "ok": True,
        "app": "Stick Knowledge 3D Studio",
        "blender_detected": settings.get("blender_path") or detect_blender_executable(),
        "ffmpeg_detected": detect_ffmpeg_executable(),
    }


@app.get("/api/settings")
async def api_get_settings():
    s = get_settings()
    return {
        "settings": s,
        "models": CLAUDE_MODELS,
        "ffmpeg_path": detect_ffmpeg_executable(),
    }


@app.put("/api/settings")
async def api_update_settings(payload: SettingsPayload):
    saved = save_settings(payload.model_dump())
    return {"ok": True, "settings": saved}


@app.get("/api/models")
async def api_list_models(refresh: bool = False):
    """Every Claude model available to the configured API key (GET /v1/models), with pricing."""
    s = get_settings()
    return await list_models((s.get("anthropic_api_key") or "").strip(), force=refresh)


@app.post("/api/system/detect-blender")
async def api_detect_blender():
    exe = detect_blender_executable()
    env = await asyncio.to_thread(probe_blender_environment, exe)
    if exe:
        save_settings({"blender_path": exe})
    return env


@app.get("/api/system/blenderkit-status")
async def api_blenderkit_status():
    s = get_settings()
    src = s.get("blenderkit_source_path") or DEFAULT_BLENDERKIT_SOURCE
    bpath = s.get("blender_path") or detect_blender_executable()
    return await asyncio.to_thread(get_blenderkit_status, src, bpath)


@app.post("/api/system/install-blenderkit")
async def api_install_blenderkit(body: dict[str, Any] = {}):
    s = get_settings()
    src = body.get("source_path") or s.get("blenderkit_source_path") or DEFAULT_BLENDERKIT_SOURCE
    bpath = body.get("blender_path") or s.get("blender_path") or detect_blender_executable()
    api_key = body.get("api_key") if "api_key" in body else s.get("blenderkit_api_key", "")
    save_settings({"blenderkit_source_path": src, "blenderkit_api_key": api_key})
    return await asyncio.to_thread(install_and_enable_blenderkit, src, bpath, api_key)


@app.post("/api/system/pick-folder")
async def api_pick_folder():
    """Opens a native Windows Folder Browser dialog and returns the selected absolute directory path."""
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$f.Description = 'Select Target Output Folder for Stick Knowledge 3D Project'; "
        "$f.UseDescriptionForTitle = $true; "
        "$f.ShowNewFolderButton = $true; "
        "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.SelectedPath }"
    )
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        chosen = (proc.stdout or "").strip()
        return {"ok": bool(chosen), "path": chosen}
    except Exception as e:
        return {"ok": False, "path": "", "error": str(e)}


@app.post("/api/system/validate-path")
async def api_validate_path(req: ValidatePathRequest):
    raw = req.path.strip()
    if not raw:
        return {"valid": False, "message": "Path cannot be empty."}
    try:
        p = Path(raw)
        if not p.is_absolute():
            return {"valid": False, "message": "Please enter a full absolute Windows path (e.g. D:\\Videos\\StickKnowledge\\Ep01)."}
        drive_exists = p.drive == "" or Path(p.drive + "\\").exists()
        if not drive_exists:
            return {"valid": False, "message": f"Drive {p.drive} does not exist."}
        return {
            "valid": True,
            "exists": p.exists(),
            "resolved": str(p),
            "message": "Folder exists and is ready." if p.exists() else "Valid path (folder will be created automatically).",
        }
    except Exception as e:
        return {"valid": False, "message": str(e)}


# ==============================================================================
# ELEVENLABS VOICES & PREVIEW
# ==============================================================================

@app.get("/api/elevenlabs/voices")
async def api_list_voices():
    svc = ElevenLabsService()
    voices = await svc.list_voices()
    return {"voices": voices}


@app.post("/api/elevenlabs/preview")
async def api_preview_voice(req: VoicePreviewRequest):
    svc = ElevenLabsService()
    try:
        audio_bytes = await svc.preview_voice(req.voice_id, req.text)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==============================================================================
# ASSET LIBRARY MANAGER ENDPOINTS
# ==============================================================================

@app.get("/api/assets/library")
async def api_get_asset_library():
    catalog = asset_manager.scan_local_libraries()
    s = get_settings()
    bk_status = await asyncio.to_thread(
        get_blenderkit_status,
        s.get("blenderkit_source_path") or DEFAULT_BLENDERKIT_SOURCE,
        s.get("blender_path") or detect_blender_executable(),
    )
    return {
        "catalog": catalog,
        "mixamo_folder": str(MIXAMO_LIBRARY_DIR),
        "blenderkit": bk_status,
    }


@app.get("/api/assets/search")
async def api_search_assets(q: str, source: str = "all", category: str = "prop"):
    results: dict[str, Any] = {"query": q, "blenderkit": [], "polyhaven": []}
    if source in ("all", "blenderkit"):
        bk_type = "material" if category == "material" else "model"
        results["blenderkit"] = await asset_manager.search_blenderkit_free(q, asset_type=bk_type, limit=6)
    if source in ("all", "polyhaven"):
        ph_type = "textures" if category == "material" else ("hdris" if category == "hdri" else "models")
        results["polyhaven"] = await asset_manager.search_polyhaven(q, asset_type=ph_type, limit=6)
    return results


# ==============================================================================
# PROJECTS, CHAT & STORYBOARD ENDPOINTS
# ==============================================================================

@app.get("/api/projects")
async def api_list_projects():
    return {"projects": list_projects()}


@app.post("/api/projects")
async def api_create_project(req: CreateProjectRequest):
    target = req.target_folder.strip()
    if not target:
        raise HTTPException(status_code=400, detail="Target output folder is required.")
    ensure_project_folder_structure(target)
    proj = create_project(name=req.name.strip() or "Untitled 3D Short", target_folder=target, topic=req.topic)
    save_project_meta_file(proj)
    return {"project": proj}


@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: str):
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {
        "project": proj,
        "messages": get_messages(project_id),
        "usage": get_token_usage_summary(project_id),
    }


@app.put("/api/projects/{project_id}")
async def api_update_project(project_id: str, req: UpdateProjectRequest):
    sb_dict = req.storyboard.model_dump() if req.storyboard else None
    if sb_dict is not None:
        existing = get_project(project_id)
        sb_dict = normalize_storyboard(sb_dict, (existing or {}).get("storyboard") or {})
    if req.target_folder:
        ensure_project_folder_structure(req.target_folder)
    updated = update_project(
        project_id,
        name=req.name,
        target_folder=req.target_folder,
        storyboard=sb_dict,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found.")
    save_project_meta_file(updated)
    return {"project": updated}


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: str):
    ok = delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"ok": True}


@app.post("/api/projects/{project_id}/chat")
async def api_project_chat(project_id: str, req: ChatRequest):
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    """
    Streams one Claude turn as Server-Sent Events (text/event-stream). Each event is
    `data: {json}\\n\\n` with a `type` of: user_message, assistant_start, thinking_start,
    thinking_delta, text_delta, text_block_end, tool_start, tool_result, notice,
    project_updated, done, error.
    """
    user_msg = add_message(project_id, "user", req.message)
    if not proj.get("topic"):
        update_project(project_id, topic=req.message[:140])
    await hub.broadcast(project_id, {"type": "log", "stage": "claude", "message": f"Director prompt: {req.message[:200]}"})

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(evt: dict[str, Any]) -> None:
        await queue.put(evt)
        if evt.get("type") == "project_updated":
            await hub.broadcast(project_id, evt)

    async def agent() -> None:
        await emit({"type": "user_message", "message": user_msg})
        try:
            result = await run_chat_turn(
                project_id=project_id,
                user_content=req.message,
                emit=emit,
                model=req.model,
                thinking=req.thinking,
                effort=req.effort,
            )
            assistant_msg = add_message(
                project_id,
                "assistant",
                result.text or "_(no text reply)_",
                metadata={
                    "affected_scenes": result.affected_scenes,
                    "usage": result.usage,
                    "tool_calls": result.tool_calls,
                    "thinking": result.thinking[:20000],
                    "model": result.model,
                    "stop_reason": result.stop_reason,
                },
            )
            usage_summary = get_token_usage_summary(project_id)
            await hub.broadcast(project_id, {"type": "usage_updated", "usage": usage_summary})
            await emit({
                "type": "done",
                "assistant_message": assistant_msg,
                "project": get_project(project_id),
                "usage": usage_summary,
            })
        except Exception as e:  # API/auth/network errors surface in chat, never as a crash
            detail = getattr(e, "message", None) or str(e)
            err = add_message(project_id, "assistant", f"⚠️ Claude request failed: {detail}",
                              metadata={"error": True})
            await emit({"type": "error", "message": detail, "assistant_message": err})
        finally:
            await queue.put(None)

    task = asyncio.create_task(agent())

    async def sse():
        while True:
            evt = await queue.get()
            if evt is None:
                break
            yield f"data: {json.dumps(evt, ensure_ascii=False, default=str)}\n\n"
        await task

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ==============================================================================
# PIPELINE EXECUTION ENDPOINTS (VOICE, BUILD .BLEND, OPEN IN BLENDER, RENDER)
# ==============================================================================

@app.post("/api/projects/{project_id}/generate-voiceover")
async def api_generate_voiceover(project_id: str):
    try:
        return await pipeline.generate_voiceover_and_sync(project_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/projects/{project_id}/build")
async def api_build_project(project_id: str, req: BuildRequest):
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    async def _bg_build():
        try:
            await pipeline.build_blend_project(
                project_id,
                render_previews=req.render_previews,
                regenerate_scripts=req.regenerate_scripts,
                scene_indices=req.scene_indices,
            )
        except Exception as e:
            await hub.broadcast(project_id, {"type": "log", "stage": "error", "message": f"Build failed: {e}"})
            await hub.broadcast(project_id, {"type": "progress", "stage": "error", "percent": 0, "detail": str(e)})

    asyncio.create_task(_bg_build())
    return {"ok": True, "started": True, "message": "Blender project build started."}


@app.post("/api/projects/{project_id}/rerender-scene/{scene_index}")
async def api_rerender_scene(project_id: str, scene_index: int, regenerate_script: bool = False):
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    async def _bg():
        try:
            await pipeline.build_blend_project(
                project_id,
                render_previews=True,
                regenerate_scripts=regenerate_script,
                scene_indices=[scene_index],
            )
        except Exception as e:
            await hub.broadcast(project_id, {"type": "log", "stage": "error", "message": f"Scene {scene_index} re-render failed: {e}"})

    asyncio.create_task(_bg())
    return {"ok": True, "started": True}


@app.post("/api/projects/{project_id}/open-blender")
async def api_open_in_blender(project_id: str):
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    blend_file = Path(proj["target_folder"]) / "project.blend"
    try:
        runner = BlenderRunner()
        return runner.open_in_desktop_blender(blend_file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==============================================================================
# LIVE BLENDER BRIDGE
# ==============================================================================

@app.get("/api/blender/status")
async def api_blender_status():
    return await live_blender.bridge.status()


@app.post("/api/blender/install")
async def api_blender_install(force: bool = True):
    try:
        return await asyncio.to_thread(live_blender.install_addons, force)
    except live_blender.BridgeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/blender/launch")
async def api_blender_launch(body: dict[str, Any]):
    """Launch & Connect: open desktop Blender on <target_folder>/project.blend with the bridge live."""
    proj = get_project(body.get("project_id", "")) if body.get("project_id") else None
    target = (proj or {}).get("target_folder") or body.get("target_folder")
    if not target:
        raise HTTPException(status_code=400, detail="Choose a project or target folder first.")
    ensure_project_folder_structure(target)
    try:
        from services.branding import prepare_branding_assets
        await asyncio.to_thread(prepare_branding_assets, Path(target) / "assets")
    except Exception:
        pass
    try:
        return await live_blender.launch(target, bg_mode=body.get("bg_mode", "cyan_studio"))
    except live_blender.BridgeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/blender/capture")
async def api_blender_capture(body: dict[str, Any]):
    proj = get_project(body.get("project_id", ""))
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    try:
        res = await live_blender.bridge.call("capture_viewport", {k: v for k, v in body.items() if k in ("frame", "camera", "width")}, timeout=300)
    except live_blender.BridgeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    import base64, time as _t
    out_dir = Path(proj["target_folder"]) / "previews" / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"capture_{int(_t.time() * 1000)}.png"
    (out_dir / name).write_bytes(base64.b64decode(res["png_base64"]))
    return {"url": f"/api/projects/{proj['id']}/media/live/{name}", "frame": res.get("frame"), "camera": res.get("camera")}


@app.get("/api/projects/{project_id}/media/live/{name}")
async def api_live_capture_file(project_id: str, name: str):
    proj = get_project(project_id)
    if not proj or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=404, detail="Not found.")
    f = Path(proj["target_folder"]) / "previews" / "live" / name
    if not f.is_file():
        raise HTTPException(status_code=404, detail="Capture not found.")
    return FileResponse(str(f), media_type="image/png")


@app.post("/api/blender/render")
async def api_blender_render(body: dict[str, Any]):
    """Render the live project's animation to <target>/renders/frames (progress via /api/blender/render-status)."""
    proj = get_project(body.get("project_id", ""))
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    params = {"output_dir": str(Path(proj["target_folder"]) / "renders" / "frames"),
              "engine": body.get("engine", "EEVEE"), "samples": int(body.get("samples", 64))}
    for k in ("start", "end", "resolution_pct"):
        if body.get(k) is not None:
            params[k] = int(body[k])
    try:
        return await live_blender.bridge.call("render_animation", params, timeout=60)
    except live_blender.BridgeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/blender/render-status")
async def api_blender_render_status():
    try:
        return await live_blender.bridge.call("render_status", timeout=5)
    except live_blender.BridgeError as e:
        return {"running": False, "error": str(e)}


@app.post("/api/projects/{project_id}/render-final")
async def api_render_final(project_id: str, req: RenderFinalRequest):
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    async def _bg_render():
        try:
            await pipeline.render_final_short(
                project_id,
                render_engine=req.render_engine,
                cycles_samples=req.cycles_samples,
                include_sfx=req.include_sfx,
                burn_captions=req.burn_captions,
            )
        except Exception as e:
            await hub.broadcast(project_id, {"type": "log", "stage": "error", "message": f"Final render failed: {e}"})
            await hub.broadcast(project_id, {"type": "progress", "stage": "error", "percent": 0, "detail": str(e)})

    asyncio.create_task(_bg_render())
    return {"ok": True, "started": True, "message": "Final 1080x1920 render started."}


@app.get("/api/usage")
async def api_usage(project_id: str | None = None):
    return get_token_usage_summary(project_id)


# ==============================================================================
# MEDIA FILE SERVING (PREVIEWS, NARRATION AUDIO, FINAL MP4)
# ==============================================================================

@app.get("/api/projects/{project_id}/media/preview/{scene_index}")
async def api_get_preview_image(project_id: str, scene_index: int):
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    img = Path(proj["target_folder"]) / "previews" / f"scene_{scene_index:02d}.png"
    if not img.is_file():
        raise HTTPException(status_code=404, detail="Preview not rendered yet.")
    return FileResponse(str(img), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/projects/{project_id}/media/narration")
async def api_get_narration(project_id: str):
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    mp3 = Path(proj["target_folder"]) / "audio" / "narration.mp3"
    if not mp3.is_file():
        raise HTTPException(status_code=404, detail="Narration audio not generated yet.")
    return FileResponse(str(mp3), media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/projects/{project_id}/media/final-video")
async def api_get_final_video(project_id: str):
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    mp4 = Path(proj["target_folder"]) / "final_short.mp4"
    if not mp4.is_file():
        raise HTTPException(status_code=404, detail="Final video not rendered yet.")
    return FileResponse(str(mp4), media_type="video/mp4", headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8420, reload=False)
