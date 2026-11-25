"""
Entry point used by the desktop app (and frozen by PyInstaller into stick-backend.exe).

  stick-backend.exe --port 8420
  python server_entry.py --port 8420

Prints "SK_BACKEND_READY <port>" once the server accepts connections so Electron can hide
its splash screen. Exits when the parent (Electron) process disappears.
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
import threading
import time
from pathlib import Path


def _watch_parent(ppid: int) -> None:
    """If Electron dies without stopping us, don't linger as an orphan."""
    if ppid <= 0:
        return
    import ctypes

    SYNCHRONIZE = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, ppid) if os.name == "nt" else None
    while True:
        time.sleep(2)
        if os.name == "nt":
            if not handle or ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0:
                os._exit(0)
        else:
            try:
                os.kill(ppid, 0)
            except OSError:
                os._exit(0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8420)
    ap.add_argument("--parent-pid", type=int, default=0)
    args = ap.parse_args()

    here = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    threading.Thread(target=_watch_parent, args=(args.parent_pid,), daemon=True).start()

    import uvicorn
    from main import app  # noqa: WPS433

    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info", access_log=False)
    server = uvicorn.Server(config)

    def announce():
        while not server.started:
            time.sleep(0.1)
        print(f"SK_BACKEND_READY {args.port}", flush=True)

    threading.Thread(target=announce, daemon=True).start()
    server.run()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
