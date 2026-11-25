from __future__ import annotations

import os
import shutil
import glob
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "studio.db"
SKILL_PATH = BACKEND_DIR / "skills" / "stick_knowledge_3d_skill.md"
ZDF_HELPERS_PATH = BACKEND_DIR / "blender_engine" / "zdf_helpers.py"
ZDF_HELPERS_DOC_PATH = BACKEND_DIR / "blender_engine" / "zdf_helpers_api_doc.md"

ASSETS_LIBRARY_DIR = ROOT_DIR / "assets_library"
MIXAMO_LIBRARY_DIR = ASSETS_LIBRARY_DIR / "mixamo"
CUSTOM_LIBRARY_DIR = ASSETS_LIBRARY_DIR / "custom"
ANATOMY_LIBRARY_DIR = ASSETS_LIBRARY_DIR / "anatomy"
POLYHAVEN_CACHE_DIR = ASSETS_LIBRARY_DIR / "polyhaven"
BLENDERKIT_CACHE_DIR = ASSETS_LIBRARY_DIR / "blenderkit"

for _d in (
    ASSETS_LIBRARY_DIR,
    MIXAMO_LIBRARY_DIR,
    CUSTOM_LIBRARY_DIR,
    ANATOMY_LIBRARY_DIR,
    POLYHAVEN_CACHE_DIR,
    BLENDERKIT_CACHE_DIR,
):
    _d.mkdir(parents=True, exist_ok=True)

DEFAULT_BLENDERKIT_SOURCE = r"D:\B Software LK\blender.crt\blenderkit"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"
DEFAULT_RENDER_ENGINE = "EEVEE_NEXT"  # "EEVEE_NEXT" or "CYCLES_OPTIX"
DEFAULT_BUDGET_USD = 100.0

CLAUDE_MODELS = [
    {
        "id": "claude-sonnet-5-5",
        "label": "Claude Sonnet 5.5 (Latest — Recommended)",
        "input_per_mtok": 3.00,
        "output_per_mtok": 15.00,
        "cache_write_per_mtok": 3.75,
        "cache_read_per_mtok": 0.30,
    },
    {
        "id": "claude-sonnet-5",
        "label": "Claude Sonnet 5",
        "input_per_mtok": 3.00,
        "output_per_mtok": 15.00,
        "cache_write_per_mtok": 3.75,
        "cache_read_per_mtok": 0.30,
    },
    {
        "id": "claude-sonnet-4-6",
        "label": "Claude Sonnet 4.6",
        "input_per_mtok": 3.00,
        "output_per_mtok": 15.00,
        "cache_write_per_mtok": 3.75,
        "cache_read_per_mtok": 0.30,
    },
    {
        "id": "claude-haiku-5-5",
        "label": "Claude Haiku 5.5 (Fast & Low Cost)",
        "input_per_mtok": 0.80,
        "output_per_mtok": 4.00,
        "cache_write_per_mtok": 1.00,
        "cache_read_per_mtok": 0.08,
    },
    {
        "id": "claude-haiku-4-5-20251001",
        "label": "Claude Haiku 4.5 (Ultra Low Cost)",
        "input_per_mtok": 0.80,
        "output_per_mtok": 4.00,
        "cache_write_per_mtok": 1.00,
        "cache_read_per_mtok": 0.08,
    },
    {
        "id": "claude-opus-5-5",
        "label": "Claude Opus 5.5 (Maximum Quality)",
        "input_per_mtok": 15.00,
        "output_per_mtok": 75.00,
        "cache_write_per_mtok": 18.75,
        "cache_read_per_mtok": 1.50,
    },
]


def get_model_pricing(model_id: str) -> dict:
    for m in CLAUDE_MODELS:
        if m["id"] == model_id:
            return m
    # Sensible default (Sonnet tier)
    return {
        "id": model_id,
        "label": model_id,
        "input_per_mtok": 3.00,
        "output_per_mtok": 15.00,
        "cache_write_per_mtok": 3.75,
        "cache_read_per_mtok": 0.30,
    }


def detect_blender_executable() -> str:
    """Auto-detect Blender on Windows (checks custom install dirs, Program Files, PATH, Steam)."""
    candidates: list[str] = []

    # 1. Explicit env override
    env_blender = os.environ.get("BLENDER_PATH")
    if env_blender and Path(env_blender).is_file():
        return str(Path(env_blender))

    # 2. Check PATH
    in_path = shutil.which("blender")
    if in_path:
        candidates.append(in_path)

    # 3. Known custom Windows install locations (including D:\B Software LK\blender.exe)
    direct_checks = [
        r"D:\B Software LK\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender\blender.exe",
    ]
    for p in direct_checks:
        if Path(p).is_file():
            candidates.append(p)

    # 4. Versioned directories (newest first)
    glob_patterns = [
        r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
        r"D:\Program Files\Blender Foundation\Blender *\blender.exe",
        r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation\Blender *\blender.exe"),
    ]
    for pat in glob_patterns:
        matches = sorted(glob.glob(pat), reverse=True)
        candidates.extend(matches)

    for c in candidates:
        if c and Path(c).is_file():
            return str(Path(c))

    return ""


def detect_ffmpeg_executable() -> str:
    found = shutil.which("ffmpeg")
    return found or ""
