# PyInstaller spec: freezes the FastAPI backend into build/stick-backend/stick-backend.exe
# (onedir). Electron ships that folder as resources/backend.
#   python -m PyInstaller --noconfirm --clean --distpath build --workpath build/pyi-work packaging/stick-backend.spec
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
BACKEND = ROOT / "backend"

datas = [
    (str(BACKEND / "skills"), "skills"),
    (str(BACKEND / "blender_engine"), "blender_engine"),
    (str(ROOT / "blender_addon"), "blender_addon"),
    (str(ROOT / "frontend" / "dist"), "frontend_dist"),
    (str(ROOT / "desktop" / "assets" / "logo.png"), "brand"),
]
if (ROOT / "desktop" / "assets" / "logo.placeholder").exists():
    datas.append((str(ROOT / "desktop" / "assets" / "logo.placeholder"), "brand"))

binaries = []
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("services")
    + collect_submodules("blender_engine")
    + ["multipart", "python_multipart", "websockets", "httptools", "watchfiles"]
)
# Packages with native libraries / data files (faster-whisper stack, PyAV, ONNX VAD).
for pkg in ("faster_whisper", "ctranslate2", "av", "onnxruntime", "tokenizers", "anthropic", "gradio_client"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:  # optional packages
        print(f"[spec] skipping {pkg}: {e}")

a = Analysis(
    [str(BACKEND / "server_entry.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "bpy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="stick-backend",
    console=True,  # Electron starts it hidden (windowsHide) and reads its stdout
    icon=str(ROOT / "desktop" / "assets" / "icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="stick-backend")
