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
SKILLS_DIR = BACKEND_DIR / "skills"  # every *.md here is loaded into the Claude system prompt (cached)
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
DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
DEFAULT_RENDER_ENGINE = "EEVEE_NEXT"  # "EEVEE_NEXT" or "CYCLES_OPTIX"
DEFAULT_BUDGET_USD = 100.0

# ------------------------------------------------------------------------------
# Claude model pricing (USD per million tokens, Anthropic first-party API).
# The live model LIST comes from GET /v1/models (see services/model_catalog.py);
# this table only supplies prices + an offline fallback list. Prices are matched
# by longest id prefix so dated snapshots (e.g. claude-haiku-4-5-20251001) resolve.
# cache_write = 5-minute ephemeral write (1.25x input).
# ------------------------------------------------------------------------------
def _price(inp: float, out: float, cache_read: Optional[float] = None) -> dict:
    return {
        "input_per_mtok": inp,
        "output_per_mtok": out,
        "cache_write_per_mtok": round(inp * 1.25, 4),
        "cache_read_per_mtok": cache_read if cache_read is not None else round(inp * 0.1, 4),
    }


MODEL_PRICING: dict[str, dict] = {
    "claude-fable-5-2": _price(8.00, 40.00, 0.20),
    "claude-mythos-5-2": _price(8.00, 40.00, 0.20),
    "claude-fable-5-1": _price(10.00, 50.00),
    "claude-mythos-5-1": _price(10.00, 50.00),
    "claude-fable-5": _price(10.00, 50.00),
    "claude-opus-5-5": _price(4.00, 20.00, 0.20),
    "claude-opus-5": _price(5.00, 25.00),
    "claude-opus-4-8": _price(5.00, 25.00),
    "claude-opus-4-7": _price(5.00, 25.00),
    "claude-opus-4-6": _price(5.00, 25.00),
    "claude-opus-4-5": _price(5.00, 25.00),
    "claude-opus-4-1": _price(15.00, 75.00),
    "claude-opus-4": _price(15.00, 75.00),
    "claude-sonnet-5-5": _price(2.00, 10.00, 0.10),
    "claude-sonnet-5": _price(2.00, 10.00),
    "claude-sonnet-4": _price(3.00, 15.00),  # 4, 4.5, 4.6
    "claude-haiku-5-5": _price(0.10, 0.50),
    "claude-haiku-4-5": _price(1.00, 5.00),
    "claude-3-5-haiku": _price(0.80, 4.00),
    "claude-3": _price(3.00, 15.00),
}

# Offline fallback list (used only when GET /v1/models is unreachable).
FALLBACK_MODELS: list[dict] = [
    {"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5"},
    {"id": "claude-sonnet-5-5", "display_name": "Claude Sonnet 5.5"},
    {"id": "claude-haiku-5-5", "display_name": "Claude Haiku 5.5"},
    {"id": "claude-fable-5-2", "display_name": "Claude Fable 5.2"},
    {"id": "claude-opus-5", "display_name": "Claude Opus 5"},
    {"id": "claude-sonnet-5", "display_name": "Claude Sonnet 5"},
    {"id": "claude-opus-4-8", "display_name": "Claude Opus 4.8"},
    {"id": "claude-sonnet-4-6", "display_name": "Claude Sonnet 4.6"},
    {"id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5"},
]


def get_model_pricing(model_id: str) -> dict:
    best = ""
    for prefix in MODEL_PRICING:
        if model_id.startswith(prefix) and len(prefix) > len(best):
            best = prefix
    price = MODEL_PRICING.get(best) or _price(3.00, 15.00)  # unknown → Sonnet-tier estimate
    return {"id": model_id, **price}


def decorate_model(m: dict) -> dict:
    """Attach pricing + a UI label to a model entry from /v1/models or the fallback list."""
    price = get_model_pricing(m["id"])
    name = m.get("display_name") or m["id"]
    return {
        **m,
        **price,
        "label": f"{name}  ·  ${price['input_per_mtok']:g}/${price['output_per_mtok']:g} per MTok",
    }


# Back-compat for code that still imports CLAUDE_MODELS.
CLAUDE_MODELS = [decorate_model(m) for m in FALLBACK_MODELS]


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
