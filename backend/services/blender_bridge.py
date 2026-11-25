"""
Studio side of the live Blender bridge.

  install_addons()  copy stick_knowledge_bridge (+ BlenderKit) into Blender's user add-ons
                    folder and enable both (one headless Blender run, cached by version stamp)
  launch(project)   open desktop Blender on <target>/project.blend (created if missing) with
                    the bridge started, then wait until it answers
  BlenderBridge     async JSON-RPC client (newline-delimited JSON over 127.0.0.1)
"""
from __future__ import annotations

import asyncio
import itertools
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from blender_engine.blenderkit_setup import probe_blender_environment, resolve_blenderkit_addon_root
from config import BACKEND_DIR, DEFAULT_BLENDERKIT_SOURCE, ROOT_DIR, detect_blender_executable
from database import get_settings

ADDON_SRC = ROOT_DIR / "blender_addon" / "stick_knowledge_bridge"
LAUNCH_SCRIPT = ROOT_DIR / "blender_addon" / "launch_project.py"
ENGINE_DIR = (BACKEND_DIR / "blender_engine").resolve()
DISCOVERY_FILE = Path(tempfile.gettempdir()) / "stick_knowledge_bridge.json"
DEFAULT_PORT = 9876


class BridgeError(Exception):
    pass


def _blender_exe() -> str:
    s = get_settings()
    exe = s.get("blender_path") or detect_blender_executable()
    if not exe or not Path(exe).is_file():
        raise BridgeError("Blender executable not found. Set it in Settings.")
    return exe


def _addon_version() -> str:
    init = (ADDON_SRC / "__init__.py").read_text(encoding="utf-8")
    import re
    m = re.search(r'"version":\s*\((\d+),\s*(\d+),\s*(\d+)\)', init)
    return ".".join(m.groups()) if m else "0"


# ------------------------------------------------------------------------------
# Install
# ------------------------------------------------------------------------------

def install_addons(force: bool = False) -> dict[str, Any]:
    exe = _blender_exe()
    env = probe_blender_environment(exe)
    if not env.get("addons_dir"):
        raise BridgeError(f"Could not query Blender's add-on folder: {env.get('error')}")
    addons_dir = Path(env["addons_dir"])
    addons_dir.mkdir(parents=True, exist_ok=True)
    dest = addons_dir / "stick_knowledge_bridge"
    stamp = dest / ".sk_installed"
    bk_src = resolve_blenderkit_addon_root(get_settings().get("blenderkit_source_path") or DEFAULT_BLENDERKIT_SOURCE)
    bk_dest = addons_dir / "blenderkit"
    import hashlib
    digest = hashlib.sha1((ADDON_SRC / "__init__.py").read_bytes()).hexdigest()[:12]
    want = f"{_addon_version()}|{digest}|{ENGINE_DIR}|bk={bool(bk_src)}"
    if not force and stamp.is_file() and stamp.read_text() == want and (dest / "__init__.py").is_file() \
            and (not bk_src or (bk_dest / "__init__.py").is_file()):
        return {"ok": True, "skipped": True, "addons_dir": str(addons_dir), "blender_version": env.get("blender_version")}

    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(ADDON_SRC, dest, ignore=shutil.ignore_patterns("__pycache__"))
    (dest / "engine_path.txt").write_text(str(ENGINE_DIR), encoding="utf-8")
    if bk_src and not (bk_dest / "__init__.py").is_file():
        shutil.copytree(bk_src, bk_dest, ignore=shutil.ignore_patterns(".git", "__pycache__"), dirs_exist_ok=True)

    expr = (
        "import bpy, json, addon_utils, os\n"
        "os.environ['SK_BRIDGE_NO_AUTOSTART']='1'\n"
        "res={}\n"
        "bpy.ops.preferences.addon_refresh()\n"
        "for mod in ('stick_knowledge_bridge','blenderkit'):\n"
        "    try:\n"
        "        addon_utils.enable(mod, default_set=True, persistent=True)\n"
        "        res[mod] = mod in bpy.context.preferences.addons\n"
        "    except Exception as e:\n"
        "        res[mod] = 'error: %s' % e\n"
        f"p = bpy.context.preferences.addons.get('stick_knowledge_bridge')\n"
        f"if p: p.preferences.engine_dir = {json.dumps(str(ENGINE_DIR))}\n"
        "bpy.ops.wm.save_userpref()\n"
        "print('__SK_INSTALL__' + json.dumps(res))\n"
    )
    proc = subprocess.run([exe, "--background", "--python-expr", expr], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    out = (proc.stdout or "") + (proc.stderr or "")
    res: dict[str, Any] = {}
    for line in out.splitlines():
        if "__SK_INSTALL__" in line:
            res = json.loads(line.split("__SK_INSTALL__", 1)[1])
    ok = res.get("stick_knowledge_bridge") is True
    if ok:
        stamp.write_text(want, encoding="utf-8")
    return {"ok": ok, "skipped": False, "enabled": res, "addons_dir": str(addons_dir),
            "blender_version": env.get("blender_version"),
            "log_tail": "" if ok else out[-2000:]}


# ------------------------------------------------------------------------------
# Client
# ------------------------------------------------------------------------------

def _discovery() -> dict[str, Any]:
    try:
        return json.loads(DISCOVERY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


class BlenderBridge:
    _ids = itertools.count(1)

    def __init__(self, host: str = "127.0.0.1"):
        self.host = host

    async def call(self, cmd: str, params: Optional[dict[str, Any]] = None, timeout: float = 120.0) -> Any:
        info = _discovery()
        port = int(info.get("port") or DEFAULT_PORT)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, port, limit=128 * 1024 * 1024), timeout=3.0)
        except (OSError, asyncio.TimeoutError) as e:
            raise BridgeError("Blender is not connected. Click “Launch & Connect Blender”.") from e
        msg = {"id": next(self._ids), "token": info.get("token"), "cmd": cmd, "params": params or {}, "timeout": timeout}
        try:
            writer.write((json.dumps(msg) + "\n").encode("utf-8"))
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=timeout + 5)
        except asyncio.TimeoutError as e:
            raise BridgeError(f"Blender did not answer '{cmd}' within {timeout:.0f}s (still busy?).") from e
        finally:
            writer.close()
        if not line:
            raise BridgeError("Blender closed the connection.")
        reply = json.loads(line.decode("utf-8"))
        if not reply.get("ok"):
            raise BridgeError(reply.get("error", "unknown error") + ("\n" + reply["traceback"] if reply.get("traceback") else ""))
        return reply.get("result")

    async def status(self) -> dict[str, Any]:
        try:
            info = await self.call("ping", timeout=2.0)
            if info.get("app") != "stick_knowledge_bridge":
                return {"connected": False, "error": "Another program is using the bridge port."}
            return {"connected": True, "port": _discovery().get("port"), **info}
        except BridgeError as e:
            return {"connected": False, "error": str(e).splitlines()[0]}


bridge = BlenderBridge()
_launched: dict[str, Any] = {"proc": None, "at": 0.0, "project": None}


async def launch(target_folder: str, bg_mode: str = "cyan_studio", wait_s: float = 120.0) -> dict[str, Any]:
    """Open (or reuse) desktop Blender on <target_folder>/project.blend with the bridge live."""
    project = Path(target_folder)
    project.mkdir(parents=True, exist_ok=True)
    blend = project / "project.blend"

    st = await bridge.status()
    if st.get("connected"):
        # Reuse the running Blender: switch it to this project if needed.
        if Path(st.get("file") or "") != blend:
            await bridge.call("open_project", {"path": str(blend), "project_dir": str(project),
                                               "bg_mode": bg_mode, "create": True}, timeout=180)
            await _wait_for_file(blend, 60)
        else:
            await bridge.call("execute_python", {"code": f"zdf.configure(project_dir={str(project)!r}, assets_dir={str(project / 'assets')!r})"})
        return {"ok": True, "reused": True, **(await bridge.status())}

    install = await asyncio.to_thread(install_addons)
    exe = _blender_exe()
    cmd = [exe]
    if blend.is_file():
        cmd.append(str(blend))
    cmd += ["--python", str(LAUNCH_SCRIPT), "--", "--project", str(project),
            "--engine-dir", str(ENGINE_DIR), "--addon-dir", str(ADDON_SRC.parent), "--bg-mode", bg_mode]
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    log = open(project / "blender_live.log", "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=str(project), stdout=log, stderr=subprocess.STDOUT, creationflags=flags, close_fds=True)
    _launched.update(proc=proc, at=time.time(), project=str(project))

    deadline = time.time() + wait_s
    last = {}
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = (project / "blender_live.log").read_text(encoding="utf-8", errors="replace")[-1500:]
            raise BridgeError(f"Blender exited during startup (code {proc.returncode}).\n{tail}")
        last = await bridge.status()
        if last.get("connected") and last.get("file"):
            return {"ok": True, "reused": False, "install": install, **last}
        await asyncio.sleep(1.0)
    raise BridgeError(f"Blender started but the bridge did not answer within {wait_s:.0f}s. Last status: {last}")


async def _wait_for_file(blend: Path, wait_s: float) -> None:
    deadline = time.time() + wait_s
    while time.time() < deadline:
        st = await bridge.status()
        if st.get("connected") and Path(st.get("file") or "") == blend:
            return
        await asyncio.sleep(0.8)
    raise BridgeError(f"Blender did not finish opening {blend}.")
