from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

from PIL import Image, ImageDraw, ImageFont

from blender_engine.runner import BlenderRunner
from config import BACKEND_DIR
from database import get_project, get_settings, get_token_usage_summary, update_project
from services.asset_manager import AssetManager
from services.branding import prepare_branding_assets
from services.claude_director import ClaudeDirector
from services.elevenlabs_service import (
    ElevenLabsService,
    estimate_timestamps_from_storyboard,
    sync_storyboard_to_timestamps,
)
from services.video_assembler import VideoAssembler

EventCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


def ensure_project_folder_structure(target_folder: str) -> dict[str, Path]:
    """
    Creates the STRICT required folder layout directly inside the user's target folder:
      <user_target_folder>/
        ├── scripts/
        ├── assets/
        ├── audio/
        ├── previews/
        └── renders/
    """
    root = Path(target_folder)
    paths = {
        "root": root,
        "scripts": root / "scripts",
        "assets": root / "assets",
        "audio": root / "audio",
        "previews": root / "previews",
        "renders": root / "renders",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def pregenerate_branding_decals(assets_dir: Path, text: str = "STICK KNOWLEDGE") -> dict[str, str]:
    """
    Pre-generates high-resolution transparent PNG decals via Pillow inside `<target_folder>/assets/`
    so Blender always has crisp diegetic textures ready regardless of Blender's internal Python packages.
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    font_candidates = [
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\calibrib.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    font_main = None
    for fc in font_candidates:
        if os.path.isfile(fc):
            font_main = ImageFont.truetype(fc, 88)
            break
    if font_main is None:
        font_main = ImageFont.load_default()

    out_paths: dict[str, str] = {}
    modes = {
        "tshirt": {
            "bg": None,
            "border": None,
            "fg": (255, 255, 255, 255),
            "accent": (158, 226, 255, 255),
        },
        "prop_wrap": {
            "bg": (246, 248, 251, 245),
            "border": (20, 26, 36, 255),
            "fg": (18, 22, 30, 255),
            "accent": (217, 119, 87, 255),
        },
        "screen_ui": {
            "bg": (12, 22, 40, 248),
            "border": (56, 189, 248, 255),
            "fg": (255, 255, 255, 255),
            "accent": (56, 189, 248, 255),
        },
    }

    w, h = 1024, 320
    label = text.upper().strip()
    for mode, style in modes.items():
        dest = assets_dir / f"stick_knowledge_{mode}.png"
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        if style["bg"]:
            draw.rounded_rectangle(
                [16, 22, w - 16, h - 22],
                radius=30,
                fill=style["bg"],
                outline=style["border"],
                width=8,
            )
        bbox = draw.textbbox((0, 0), label, font=font_main)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (w - tw) // 2
        ty = (h - th) // 2 - 14
        draw.text((tx, ty), label, font=font_main, fill=style["fg"])
        draw.rectangle([w // 2 - 200, ty + th + 26, w // 2 + 200, ty + th + 36], fill=style["accent"])
        img.save(str(dest), "PNG")
        out_paths[mode] = str(dest)

    return out_paths


def save_project_meta_file(project: dict[str, Any]) -> Path:
    """Writes `<target_folder>/project_meta.json` with script, storyboard, timestamps, assets & token cost log."""
    paths = ensure_project_folder_structure(project["target_folder"])
    ts_path = paths["audio"] / "timestamps.json"
    timestamps = {}
    if ts_path.is_file():
        try:
            timestamps = json.loads(ts_path.read_text(encoding="utf-8"))
        except Exception:
            timestamps = {}

    usage = get_token_usage_summary(project["id"])
    meta_doc = {
        "project_id": project["id"],
        "name": project["name"],
        "topic": project["topic"],
        "target_folder": project["target_folder"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "storyboard": project.get("storyboard", {}),
        "timestamps": timestamps,
        "token_cost_log": usage,
    }
    meta_file = paths["root"] / "project_meta.json"
    meta_file.write_text(json.dumps(meta_doc, indent=2), encoding="utf-8")
    return meta_file


def generate_master_build_script(
    *,
    project_dir: Path,
    storyboard: dict[str, Any],
    render_engine: str,
    cycles_samples: int,
    render_previews: bool,
    preview_scene_indices: Optional[list[int]] = None,
) -> Path:
    """
    Generates `<target_folder>/scripts/master_build.py` — a 100% reproducible,
    self-contained Blender build script that orchestrates `zdf_helpers` + all `scene_XX.py` modules,
    packs all assets, saves `project.blend`, and renders fast per-scene PNG previews.
    """
    scripts_dir = project_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    engine_dir = str((BACKEND_DIR / "blender_engine").resolve())
    scenes = storyboard.get("scenes", [])
    fps = int(storyboard.get("fps", 30))
    total_end_frame = max((int(s.get("end_frame", 90)) for s in scenes), default=90)
    branding = storyboard.get("branding_placement", {})

    # Serialize scene contexts cleanly
    scene_entries = []
    for s in scenes:
        asset_map = {a["asset_id"]: a.get("local_path") for a in s.get("assets", [])}
        scene_entries.append(
            {
                "scene_index": int(s["scene_index"]),
                "script_module": f"scene_{int(s['scene_index']):02d}",
                "start_frame": int(s.get("start_frame", 1)),
                "end_frame": int(s.get("end_frame", 90)),
                "bg_mode": s.get("bg_mode", "cyan_studio"),
                "has_branding": bool(s.get("has_branding", False)),
                "assets": asset_map,
            }
        )

    master_code = f'''"""
Stick Knowledge 3D Studio — Master Reproducible Blender Build Script
Auto-generated for: {storyboard.get("title", "3D Short")}
Run via: blender --background --python master_build.py
"""
import importlib
import json
import sys
import traceback
from pathlib import Path

PROJECT_DIR = Path({json.dumps(str(project_dir.resolve()))})
SCRIPTS_DIR = PROJECT_DIR / "scripts"
ASSETS_DIR = PROJECT_DIR / "assets"
PREVIEWS_DIR = PROJECT_DIR / "previews"
ENGINE_DIR = Path({json.dumps(engine_dir)})

for _p in (str(ENGINE_DIR), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bpy
import zdf_helpers as zdf

RENDER_ENGINE = {json.dumps(render_engine)}
CYCLES_SAMPLES = {int(cycles_samples)}
FPS = {fps}
TOTAL_END_FRAME = {total_end_frame}
RENDER_PREVIEWS = {repr(bool(render_previews))}
PREVIEW_INDICES = {repr(preview_scene_indices)}
BRANDING_PLACEMENT = json.loads({json.dumps(json.dumps(branding))})
SCENES_CONFIG = json.loads({json.dumps(json.dumps(scene_entries))})


def main():
    print("[StickKnowledge3D] Initializing Zack D. Films 9:16 studio...")
    zdf.configure(project_dir=str(PROJECT_DIR), assets_dir=str(ASSETS_DIR))
    zdf.init_zdf_studio(
        render_engine=RENDER_ENGINE,
        bg_mode=SCENES_CONFIG[0]["bg_mode"] if SCENES_CONFIG else "cyan_studio",
        cycles_samples=CYCLES_SAMPLES,
        fps=FPS,
    )

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = TOTAL_END_FRAME

    built_scenes = []
    first_camera = None

    for cfg in SCENES_CONFIG:
        idx = cfg["scene_index"]
        mod_name = cfg["script_module"]
        script_file = SCRIPTS_DIR / f"{{mod_name}}.py"
        if not script_file.is_file():
            print(f"[StickKnowledge3D] Skipping missing script {{script_file.name}}")
            continue

        print(f"[StickKnowledge3D] Building Scene {{idx:02d}} (frames {{cfg['start_frame']}}-{{cfg['end_frame']}})...")
        ctx = {{
            "scene_index": idx,
            "start_frame": cfg["start_frame"],
            "end_frame": cfg["end_frame"],
            "fps": FPS,
            "assets": cfg["assets"],
            "project_dir": str(PROJECT_DIR),
            "assets_dir": str(ASSETS_DIR),
            "branding_placement": BRANDING_PLACEMENT if cfg["has_branding"] else None,
            "bg_mode": cfg["bg_mode"],
        }}
        try:
            mod = importlib.import_module(mod_name)
            importlib.reload(mod)
            res = mod.build_scene(ctx) or {{}}
            cam = res.get("camera")
            if cam is not None:
                if first_camera is None:
                    first_camera = cam
                    scene.camera = cam
                zdf.bind_camera_marker(scene, cam, cfg["start_frame"], f"Cam_Scene_{{idx:02d}}")
            preview_frame = int(res.get("preview_frame") or ((cfg["start_frame"] + cfg["end_frame"]) // 2))
            built_scenes.append((idx, cam, preview_frame))
        except Exception:
            print(f"__SK_SCENE_ERROR__:{{script_file.name}}")
            traceback.print_exc()
            raise

    # Save self-contained packed project.blend BEFORE preview renders
    blend_out = PROJECT_DIR / "project.blend"
    print(f"[StickKnowledge3D] Packing assets and saving {{blend_out}}...")
    zdf.pack_and_save_project(str(blend_out))

    # Render fast per-scene PNG previews for UI
    if RENDER_PREVIEWS:
        PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        for idx, cam, pframe in built_scenes:
            if PREVIEW_INDICES is not None and idx not in PREVIEW_INDICES:
                continue
            out_png = PREVIEWS_DIR / f"scene_{{idx:02d}}.png"
            print(f"[StickKnowledge3D] Rendering preview Scene {{idx:02d}} @ frame {{pframe}} -> {{out_png.name}}")
            zdf.render_scene_preview(pframe, str(out_png), camera_obj=cam, preview_scale_pct=50)

    print("[StickKnowledge3D] Master build complete!")


if __name__ == "__main__":
    main()
'''
    master_file = scripts_dir / "master_build.py"
    master_file.write_text(master_code, encoding="utf-8")
    return master_file


def generate_final_render_script(
    *,
    project_dir: Path,
    start_frame: int,
    end_frame: int,
    render_engine: str,
    cycles_samples: int,
) -> Path:
    engine_dir = str((BACKEND_DIR / "blender_engine").resolve())
    code = f'''"""
Stick Knowledge 3D Studio — Full 1080x1920 Final Animation Render Script
"""
import sys
from pathlib import Path

ENGINE_DIR = Path({json.dumps(engine_dir)})
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import zdf_helpers as zdf

zdf.render_animation(
    start_frame={int(start_frame)},
    end_frame={int(end_frame)},
    output_dir={json.dumps(str((project_dir / "renders").resolve()))},
    render_engine={json.dumps(render_engine)},
    cycles_samples={int(cycles_samples)},
)
print("[StickKnowledge3D] Animation frames rendered successfully!")
'''
    script_path = project_dir / "scripts" / "render_final.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(code, encoding="utf-8")
    return script_path


def generate_fallback_scene_script(scene: dict[str, Any], branding_placement: dict[str, Any]) -> str:
    """
    Deterministic fallback scene generator used only if an individual scene has no
    Claude-generated script yet (e.g., offline testing without an Anthropic API key).
    """
    idx = int(scene["scene_index"])
    overlays = scene.get("overlays", [])
    has_branding = bool(scene.get("has_branding", False))
    cutaway = bool(scene.get("cutaway_needed", False))
    first_asset_id = scene["assets"][0]["asset_id"] if scene.get("assets") else "hero_prop"
    brand_mode = branding_placement.get("mode", "prop_wrap")

    return f'''"""Scene {idx:02d} — {scene.get("title", "Explainer Beat")}"""
import math
import zdf_helpers as zdf


def build_scene(ctx: dict) -> dict:
    sf = ctx["start_frame"]
    ef = ctx["end_frame"]
    mid = (sf + ef) // 2
    col = zdf.setup_scene_collection(ctx["scene_index"], sf, ef)
    zdf.set_studio_bg_keyframe(ctx.get("bg_mode", "cyan_studio"), sf)

    # Grounded warm wood tabletop
    table = zdf.create_procedural_prop("table", name=f"Table_S{idx:02d}", location=(0, 0, -0.07), collection=col)

    # Primary Hero Prop (imported asset or procedural fallback)
    hero_path = ctx["assets"].get({json.dumps(first_asset_id)})
    hero = zdf.import_and_normalize_asset(hero_path, target_height=0.85, location=(0, 0, 0.02), collection=col, name=f"Hero_S{idx:02d}")
    if hero is None:
        hero = zdf.create_procedural_prop("battery", name=f"Hero_S{idx:02d}", location=(0, 0, 0.25), scale=(1.4, 1.4, 1.4), collection=col)

    zdf.animate_transform(hero, [
        (sf, (0.0, 0.0, 0.22), (0.0, 0.0, -0.35), (1.0, 1.0, 1.0)),
        (ef, (0.0, 0.0, 0.34), (0.0, 0.0, 0.35), (1.05, 1.05, 1.05)),
    ])

    if {repr(cutaway)}:
        zdf.apply_animated_cutaway(hero, start_frame=sf + 5, end_frame=min(ef, sf + 35), collection=col)

    if {repr(has_branding)}:
        zdf.create_branding_decal(
            text="STICK KNOWLEDGE",
            target_obj=hero,
            mode={json.dumps(brand_mode)},
            location=(0.0, -0.32, 0.12),
            width=0.52,
            assets_dir=ctx.get("assets_dir"),
            collection=col,
        )

    zdf.add_3d_arrow(start=(-0.55, 0, 0.15), end=(-0.55, 0, 0.85), start_frame=sf + 6, collection=col)
    zdf.add_3d_label_sign(text={json.dumps(scene.get("title", "EXPLAINER")[:14].upper())}, location=(0.0, 0.0, 1.05), start_frame=sf + 10, collection=col)

    cam = zdf.setup_cinematic_camera(
        keyframes=[
            (sf, (0.0, -3.1, 0.85)),
            (ef, (0.35, -2.4, 0.72)),
        ],
        target_location=(0.0, 0.0, 0.45),
        lens=52.0,
        dof_fstop=2.8,
        collection=col,
        name=f"Cam_S{idx:02d}",
    )

    zdf.finalize_scene_visibility(col, sf, ef)
    return {{"camera": cam, "collection": col, "preview_frame": mid}}
'''


class PipelineManager:
    def __init__(self, emit: EventCallback):
        self.emit = emit
        self.assets = AssetManager()
        self.assembler = VideoAssembler()

    async def _log(self, project_id: str, stage: str, message: str) -> None:
        await self.emit(
            project_id,
            {
                "type": "log",
                "stage": stage,
                "message": message,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def _progress(self, project_id: str, stage: str, percent: int, detail: str = "") -> None:
        await self.emit(
            project_id,
            {
                "type": "progress",
                "stage": stage,
                "percent": percent,
                "detail": detail,
            },
        )

    async def generate_voiceover_and_sync(self, project_id: str) -> dict[str, Any]:
        project = get_project(project_id)
        if not project:
            raise ValueError("Project not found.")
        sb = project.get("storyboard") or {}
        if not sb.get("scenes"):
            raise ValueError("Generate a storyboard first before synthesizing voiceover.")

        paths = ensure_project_folder_structure(project["target_folder"])
        settings = get_settings()
        voice_id = settings.get("elevenlabs_voice_id", "pNInz6obpgDQGcFmaJgB")
        full_text = " ".join(
            str(s.get("narration", "")).strip() for s in sb["scenes"] if s.get("narration")
        )
        sb["full_narration"] = full_text

        await self._progress(project_id, "voiceover", 15, "Synthesizing ElevenLabs voiceover + timestamps...")
        await self._log(project_id, "elevenlabs", f"Calling ElevenLabs TTS (voice={voice_id}, {len(full_text.split())} words)...")

        tts = ElevenLabsService()
        ts_data = await tts.generate_narration_with_timestamps(
            text=full_text,
            voice_id=voice_id,
            output_audio_path=paths["audio"] / "narration.mp3",
            output_timestamps_path=paths["audio"] / "timestamps.json",
            model_id=settings.get("elevenlabs_model_id") or "eleven_multilingual_v2",
        )
        from services.media_analysis import align_storyboard_to_words
        sb = align_storyboard_to_words(sb, ts_data, fps=int(sb.get("fps", 30)), adopt_spoken_text=False)

        updated = update_project(project_id, storyboard=sb, status="voice_synced")
        save_project_meta_file(updated)  # type: ignore

        await self._log(
            project_id,
            "elevenlabs",
            f"Synced {len(ts_data.get('words', []))} words ({ts_data.get('total_duration')}s) 1:1 to Blender scene frames!",
        )
        await self._progress(project_id, "voiceover", 100, "Voiceover & timestamps synced.")
        await self.emit(project_id, {"type": "project_updated", "project": updated})
        return {"project": updated, "timestamps": ts_data}

    async def build_blend_project(
        self,
        project_id: str,
        *,
        render_previews: bool = True,
        regenerate_scripts: bool = False,
        scene_indices: Optional[list[int]] = None,
    ) -> dict[str, Any]:
        project = get_project(project_id)
        if not project:
            raise ValueError("Project not found.")
        sb = project.get("storyboard") or {}
        scenes = sb.get("scenes", [])
        if not scenes:
            raise ValueError("Project has no storyboard scenes yet.")

        paths = ensure_project_folder_structure(project["target_folder"])
        settings = get_settings()
        update_project(project_id, status="building")

        # 1. Pre-generate crisp STICK KNOWLEDGE transparent decals via Pillow
        await self._progress(project_id, "assets", 10, "Generating STICK KNOWLEDGE diegetic decals...")
        pregenerate_branding_decals(paths["assets"], text="STICK KNOWLEDGE")
        prepare_branding_assets(paths["assets"])

        # Ensure timestamps.json exists even if ElevenLabs hasn't run yet
        ts_path = paths["audio"] / "timestamps.json"
        if not ts_path.is_file():
            estimate_timestamps_from_storyboard(sb, ts_path)

        # 2. Resolve 3D assets across the 100% free 6-tier pipeline
        target_indices = set(scene_indices) if scene_indices else {int(s["scene_index"]) for s in scenes}
        await self._progress(project_id, "assets", 20, "Resolving free 3D assets (BlenderKit / Poly Haven / Mixamo / NIH 3D)...")

        async def _asset_log(stage: str, msg: str) -> None:
            await self._log(project_id, stage, msg)

        for s in scenes:
            if int(s["scene_index"]) not in target_indices:
                continue
            resolved_list = []
            for asset_req in s.get("assets", []):
                if asset_req.get("status") == "resolved" and asset_req.get("local_path") and Path(asset_req["local_path"]).is_file():
                    resolved_list.append(asset_req)
                    continue
                res = await self.assets.resolve_asset(
                    asset_req,
                    paths["assets"],
                    allow_hf_fallback=bool(settings.get("huggingface_token")),
                    log=_asset_log,
                )
                resolved_list.append(res)
            s["assets"] = resolved_list

        update_project(project_id, storyboard=sb)
        await self.emit(project_id, {"type": "storyboard_updated", "storyboard": sb})

        # 3. Generate modular per-scene bpy scripts via Claude Director (only missing or targeted)
        await self._progress(project_id, "scripts", 45, "Generating modular Blender Python scene scripts...")
        director = ClaudeDirector()
        has_api_key = bool(settings.get("anthropic_api_key", "").strip())

        for s in scenes:
            idx = int(s["scene_index"])
            script_file = paths["scripts"] / f"scene_{idx:02d}.py"
            needs_gen = regenerate_scripts or (not script_file.is_file()) or bool(s.get("script_stale")) or (
                scene_indices is not None and idx in target_indices
            )
            if needs_gen:
                if has_api_key:
                    await self._log(project_id, "claude", f"Generating modular script scene_{idx:02d}.py via Claude...")
                    code, usage = await asyncio.to_thread(
                        director.generate_scene_script,
                        project_id=project_id,
                        scene=s,
                        branding_placement=sb.get("branding_placement", {}),
                    )
                    await self._log(
                        project_id,
                        "claude",
                        f"scene_{idx:02d}.py ready (in={usage['input_tokens']}, cached_read={usage['cache_read_tokens']}, out={usage['output_tokens']}, ${usage['cost_usd']:.4f})",
                    )
                    await self.emit(project_id, {"type": "usage_updated", "usage": get_token_usage_summary(project_id)})
                else:
                    await self._log(project_id, "claude", f"No Claude API key set; writing built-in zdf_helpers template for scene_{idx:02d}.py")
                    code = generate_fallback_scene_script(s, sb.get("branding_placement", {}))
                script_file.write_text(code, encoding="utf-8")
                s["script_stale"] = False
            s["script_file"] = str(script_file)

        # 4. Write master_build.py and execute Headless Blender (with 1-retry Claude self-heal!)
        await self._progress(project_id, "blender", 65, "Building project.blend & rendering scene previews in headless Blender...")
        render_engine = settings.get("render_engine", "EEVEE_NEXT")
        cycles_samples = int(settings.get("cycles_samples", 64))

        master_file = generate_master_build_script(
            project_dir=paths["root"],
            storyboard=sb,
            render_engine=render_engine,
            cycles_samples=cycles_samples,
            render_previews=render_previews,
            preview_scene_indices=scene_indices,
        )

        runner = BlenderRunner()

        async def _blender_log(stage: str, msg: str) -> None:
            await self._log(project_id, stage, msg)

        run_res = await runner.run_script(master_file, cwd=paths["root"], log=_blender_log)

        # Automatic 1-retry Claude Self-Heal if a bpy script error occurs!
        if not run_res["ok"] and has_api_key and run_res.get("failed_scene_file"):
            bad_name = run_res["failed_scene_file"]
            bad_path = paths["scripts"] / bad_name
            if bad_path.is_file():
                await self._log(project_id, "self_heal", f"Detected bpy error in {bad_name}. Triggering automatic Claude 1-retry self-heal...")
                fixed_code, heal_usage = await asyncio.to_thread(
                    director.self_heal_script,
                    project_id=project_id,
                    script_name=bad_name,
                    broken_code=bad_path.read_text(encoding="utf-8"),
                    error_traceback=run_res["output"],
                )
                bad_path.write_text(fixed_code, encoding="utf-8")
                await self._log(project_id, "self_heal", f"Patched {bad_name} (${heal_usage['cost_usd']:.4f}). Re-running Blender build...")
                await self.emit(project_id, {"type": "usage_updated", "usage": get_token_usage_summary(project_id)})
                run_res = await runner.run_script(master_file, cwd=paths["root"], log=_blender_log)

        # Refresh preview paths on scenes
        for s in scenes:
            idx = int(s["scene_index"])
            p_png = paths["previews"] / f"scene_{idx:02d}.png"
            if p_png.is_file():
                s["preview_path"] = str(p_png)
                s["render_status"] = "preview_ready"
            elif not run_res["ok"]:
                s["render_status"] = "error"

        status_val = "ready" if run_res["ok"] else "error"
        updated = update_project(project_id, storyboard=sb, status=status_val)
        save_project_meta_file(updated)  # type: ignore

        await self._progress(
            project_id,
            "blender",
            100 if run_res["ok"] else 90,
            "project.blend built and previews ready!" if run_res["ok"] else "Blender build encountered errors (see console).",
        )
        await self.emit(project_id, {"type": "project_updated", "project": updated})
        return {"ok": run_res["ok"], "project": updated, "blend_path": str(paths["root"] / "project.blend")}

    async def render_final_short(
        self,
        project_id: str,
        *,
        render_engine: Optional[str] = None,
        cycles_samples: Optional[int] = None,
        include_sfx: bool = True,
        burn_captions: bool = True,
    ) -> dict[str, Any]:
        project = get_project(project_id)
        if not project:
            raise ValueError("Project not found.")
        sb = project.get("storyboard") or {}
        scenes = sb.get("scenes", [])
        if not scenes:
            raise ValueError("Storyboard is empty.")

        paths = ensure_project_folder_structure(project["target_folder"])
        blend_file = paths["root"] / "project.blend"
        if not blend_file.is_file():
            await self._log(project_id, "pipeline", "project.blend missing; building project first...")
            build_res = await self.build_blend_project(project_id, render_previews=False)
            if not build_res["ok"]:
                raise RuntimeError("Failed to build project.blend before rendering.")

        settings = get_settings()
        engine = render_engine or settings.get("render_engine", "EEVEE_NEXT")
        samples = int(cycles_samples or settings.get("cycles_samples", 64))
        fps = int(sb.get("fps", 30))
        end_frame = max(int(s.get("end_frame", 90)) for s in scenes)

        update_project(project_id, status="rendering")
        await self._progress(project_id, "render", 10, f"Rendering {end_frame} frames ({engine}) in Blender...")

        render_script = generate_final_render_script(
            project_dir=paths["root"],
            start_frame=1,
            end_frame=end_frame,
            render_engine=engine,
            cycles_samples=samples,
        )

        runner = BlenderRunner()

        async def _log_cb(stage: str, msg: str) -> None:
            await self._log(project_id, stage, msg)
            if "Saved:" in msg and "frame_" in msg:
                try:
                    num = int(msg.split("frame_")[-1].split(".")[0])
                    pct = 10 + int((num / max(1, end_frame)) * 70)
                    await self._progress(project_id, "render", min(82, pct), f"Rendered frame {num}/{end_frame}")
                except Exception:
                    pass

        run_res = await runner.run_script(
            render_script, blend_file=blend_file, cwd=paths["root"], log=_log_cb
        )
        if not run_res["ok"]:
            update_project(project_id, status="error")
            raise RuntimeError("Blender animation render failed. Check Blender Console for details.")

        await self._progress(project_id, "ffmpeg", 85, "Assembling 1080x1920 final_short.mp4 with captions & audio...")
        mp4_path = await self.assembler.assemble_final_short(
            project_dir=paths["root"],
            storyboard=sb,
            fps=fps,
            include_sfx=include_sfx,
            burn_captions=burn_captions,
            log=_log_cb,
        )

        for s in scenes:
            s["render_status"] = "rendered"
        updated = update_project(project_id, storyboard=sb, status="completed")
        save_project_meta_file(updated)  # type: ignore

        await self._progress(project_id, "complete", 100, f"Final Short saved: {mp4_path.name}")
        await self.emit(project_id, {"type": "project_updated", "project": updated})
        return {"ok": True, "final_mp4": str(mp4_path), "project": updated}
