from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

from config import detect_blender_executable
from database import get_settings

LogCallback = Optional[Callable[[str, str], Coroutine[Any, Any, None]]]


class BlenderRunner:
    """
    Executes headless Blender (`blender --background --python <script>`) via subprocess,
    streams real-time stdout/stderr logs over WebSocket, detects bpy errors, and supports
    launching `project.blend` directly in desktop Blender.
    """

    def __init__(self, blender_path: Optional[str] = None):
        settings = get_settings()
        self.blender_path = (
            blender_path
            or settings.get("blender_path")
            or detect_blender_executable()
        )

    def _ensure_blender(self) -> str:
        if not self.blender_path or not Path(self.blender_path).is_file():
            detected = detect_blender_executable()
            if detected:
                self.blender_path = detected
            else:
                raise FileNotFoundError(
                    "Blender executable not found. Set your Blender path in Settings."
                )
        return self.blender_path

    async def run_script(
        self,
        script_path: Path,
        *,
        blend_file: Optional[Path] = None,
        extra_args: Optional[list[str]] = None,
        cwd: Optional[Path] = None,
        log: LogCallback = None,
    ) -> dict[str, Any]:
        exe = self._ensure_blender()
        cmd = [exe, "--background"]
        if blend_file and blend_file.is_file():
            cmd.append(str(blend_file))
        cmd.extend(["--python-exit-code", "1", "--python", str(script_path)])
        if extra_args:
            cmd.append("--")
            cmd.extend(extra_args)

        if log:
            await log("blender", f"$ {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(cwd or script_path.parent),
        )

        collected: list[str] = []
        assert proc.stdout is not None
        while True:
            raw_line = await proc.stdout.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            collected.append(line)
            if log and line.strip():
                await log("blender", line)

        exit_code = await proc.wait()
        full_output = "\n".join(collected)
        has_py_error = (
            exit_code != 0
            or "Traceback (most recent call last):" in full_output
            or "__SK_SCENE_ERROR__" in full_output
        )

        # Parse failing scene file if any
        failed_scene_file = None
        m = re.search(r"__SK_SCENE_ERROR__:([^\s]+)", full_output)
        if m:
            failed_scene_file = m.group(1)

        return {
            "ok": not has_py_error,
            "exit_code": exit_code,
            "output": full_output,
            "failed_scene_file": failed_scene_file,
        }

    def open_in_desktop_blender(self, blend_file: Path) -> dict[str, Any]:
        exe = self._ensure_blender()
        if not blend_file.is_file():
            raise FileNotFoundError(f"Blender project file not found: {blend_file}")

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

        subprocess.Popen(
            [exe, str(blend_file)],
            cwd=str(blend_file.parent),
            creationflags=creationflags,
            close_fds=True,
        )
        return {"ok": True, "launched": str(blend_file), "blender_path": exe}
