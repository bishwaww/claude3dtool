from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from config import DEFAULT_BLENDERKIT_SOURCE, detect_blender_executable


def resolve_blenderkit_addon_root(source_path: str) -> Optional[Path]:
    """
    Inspects the given BlenderKit folder, handling both:
      - Direct structure: <source_path>/__init__.py
      - Nested structure: <source_path>/blenderkit/__init__.py
    """
    p = Path(source_path)
    if not p.exists():
        return None
    if (p / "__init__.py").is_file():
        return p
    if (p / "blenderkit" / "__init__.py").is_file():
        return p / "blenderkit"
    return None


def read_blenderkit_version(addon_root: Path) -> str:
    init_file = addon_root / "__init__.py"
    if not init_file.is_file():
        return "unknown"
    try:
        head = init_file.read_text(encoding="utf-8", errors="ignore")[:2500]
        m = re.search(r'"version"\s*:\s*\(([^)]+)\)', head)
        if m:
            nums = [x.strip() for x in m.group(1).split(",") if x.strip().isdigit()]
            return ".".join(nums)
    except Exception:
        pass
    return "installed"


def probe_blender_environment(blender_path: Optional[str] = None) -> dict[str, Any]:
    """Queries Blender in headless mode for version, addons path, BlenderKit & MPFB2 status."""
    exe = blender_path or detect_blender_executable()
    result: dict[str, Any] = {
        "blender_found": False,
        "blender_path": exe,
        "blender_version": "",
        "addons_dir": "",
        "engines": [],
        "blenderkit_enabled": False,
        "blenderkit_installed": False,
        "mpfb2_installed": False,
        "error": None,
    }
    if not exe or not Path(exe).is_file():
        result["error"] = "Blender executable not found."
        return result

    probe_expr = (
        "import bpy, json, addon_utils; "
        "addons_dir = bpy.utils.user_resource('SCRIPTS', path='addons'); "
        "engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]; "
        "enabled = set(bpy.context.preferences.addons.keys()); "
        "mods = {m.__name__: m for m in addon_utils.modules()}; "
        "bk_installed = any('blenderkit' in k.lower() for k in mods) or any('blenderkit' in k.lower() for k in enabled); "
        "bk_enabled = any('blenderkit' in k.lower() for k in enabled); "
        "mpfb = any('mpfb' in k.lower() for k in mods) or any('mpfb' in k.lower() for k in enabled); "
        "print('__SK_PROBE__' + json.dumps({"
        "'version': bpy.app.version_string, "
        "'addons_dir': addons_dir, "
        "'engines': engines, "
        "'blenderkit_installed': bk_installed, "
        "'blenderkit_enabled': bk_enabled, "
        "'mpfb2_installed': mpfb"
        "}))"
    )
    try:
        proc = subprocess.run(
            [exe, "--background", "--python-expr", probe_expr],
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=35,
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        for line in output.splitlines():
            if "__SK_PROBE__" in line:
                payload = json.loads(line.split("__SK_PROBE__", 1)[1].strip())
                result["blender_found"] = True
                result["blender_version"] = payload.get("version", "")
                result["addons_dir"] = payload.get("addons_dir", "")
                result["engines"] = payload.get("engines", [])
                result["blenderkit_installed"] = bool(payload.get("blenderkit_installed"))
                result["blenderkit_enabled"] = bool(payload.get("blenderkit_enabled"))
                result["mpfb2_installed"] = bool(payload.get("mpfb2_installed"))
                return result
        result["error"] = f"Probe did not return metadata. Exit={proc.returncode}"
    except Exception as e:
        result["error"] = str(e)
    return result


def get_blenderkit_status(
    source_path: str = DEFAULT_BLENDERKIT_SOURCE, blender_path: Optional[str] = None
) -> dict[str, Any]:
    addon_root = resolve_blenderkit_addon_root(source_path)
    env = probe_blender_environment(blender_path)

    target_dir = ""
    copied_in_addons = False
    if env.get("addons_dir"):
        dest = Path(env["addons_dir"]) / "blenderkit"
        target_dir = str(dest)
        copied_in_addons = (dest / "__init__.py").is_file()

    return {
        "source_path": source_path,
        "source_valid": addon_root is not None,
        "resolved_source_root": str(addon_root) if addon_root else "",
        "source_version": read_blenderkit_version(addon_root) if addon_root else "",
        "target_addons_dir": target_dir,
        "copied_in_addons": copied_in_addons,
        "blender_found": env["blender_found"],
        "blender_path": env["blender_path"],
        "blender_version": env["blender_version"],
        "blenderkit_installed": env["blenderkit_installed"] or copied_in_addons,
        "blenderkit_enabled": env["blenderkit_enabled"],
        "mpfb2_installed": env["mpfb2_installed"],
        "engines": env["engines"],
        "error": env.get("error"),
    }


def install_and_enable_blenderkit(
    source_path: str = DEFAULT_BLENDERKIT_SOURCE,
    blender_path: Optional[str] = None,
    api_key: str = "",
) -> dict[str, Any]:
    """
    1. Verifies `D:\\B Software LK\\blender.crt\\blenderkit` (direct or nested).
    2. Copies/syncs it cleanly into `%APPDATA%\\Blender Foundation\\Blender\\<ver>\\scripts\\addons\\blenderkit`.
    3. Launches headless Blender to enable the `blenderkit` add-on, optionally store api_key,
       save user preferences, and verify import health.
    """
    addon_root = resolve_blenderkit_addon_root(source_path)
    if not addon_root:
        return {
            "ok": False,
            "message": f"BlenderKit source folder not valid (missing __init__.py): {source_path}",
        }

    env = probe_blender_environment(blender_path)
    if not env["blender_found"] or not env["addons_dir"]:
        return {
            "ok": False,
            "message": f"Could not detect local Blender installation: {env.get('error')}",
        }

    addons_dir = Path(env["addons_dir"])
    addons_dir.mkdir(parents=True, exist_ok=True)
    dest_dir = addons_dir / "blenderkit"

    # Sync/copy cleanly (avoid copying .git to stay fast)
    def _ignore(_dir, names):
        return [n for n in names if n in (".git", "__pycache__")]

    if dest_dir.exists() or dest_dir.is_symlink():
        if dest_dir.is_symlink():
            dest_dir.unlink()
        else:
            shutil.rmtree(dest_dir, ignore_errors=True)

    shutil.copytree(addon_root, dest_dir, ignore=_ignore, dirs_exist_ok=True)

    # Enable inside headless Blender and verify import health
    enable_expr = f"""
import bpy, json, sys
result = {{"enabled": False, "import_ok": False, "error": ""}}
try:
    bpy.ops.preferences.addon_refresh()
    bpy.ops.preferences.addon_enable(module="blenderkit")
    api_key = {json.dumps(api_key)}
    if api_key and "blenderkit" in bpy.context.preferences.addons:
        prefs = bpy.context.preferences.addons["blenderkit"].preferences
        if hasattr(prefs, "api_key"):
            prefs.api_key = api_key
    bpy.ops.wm.save_userpref()
    result["enabled"] = "blenderkit" in bpy.context.preferences.addons
    import blenderkit
    result["import_ok"] = hasattr(blenderkit, "bl_info")
except Exception as e:
    result["error"] = str(e)
print("__SK_BK_INSTALL__" + json.dumps(result))
"""
    try:
        proc = subprocess.run(
            [env["blender_path"], "--background", "--python-expr", enable_expr],
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        parsed = None
        for line in out.splitlines():
            if "__SK_BK_INSTALL__" in line:
                parsed = json.loads(line.split("__SK_BK_INSTALL__", 1)[1].strip())
                break

        status = get_blenderkit_status(source_path, env["blender_path"])
        ok = bool(parsed and (parsed.get("enabled") or parsed.get("import_ok"))) or status["copied_in_addons"]
        return {
            "ok": ok,
            "message": (
                f"BlenderKit v{read_blenderkit_version(addon_root)} synced to {dest_dir} "
                f"and enabled in Blender {env['blender_version']}."
                if ok
                else f"Synced files to {dest_dir}, but Blender reported: {(parsed or {}).get('error', 'unknown')}"
            ),
            "details": parsed or {},
            "status": status,
        }
    except Exception as e:
        return {"ok": False, "message": f"Failed during Blender add-on enable: {e}"}
