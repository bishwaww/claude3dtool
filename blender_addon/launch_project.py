"""
Startup script used by "Launch & Connect Blender".

  blender [project.blend] --python launch_project.py -- --project <dir> [--engine-dir <dir>] [--addon-dir <dir>]

* Makes sure the Stick Knowledge Bridge add-on is loaded (installed copy or the repo copy),
* points zdf_helpers at the project,
* if no project.blend exists yet, turns the default startup scene into a fresh ZDF
  studio and saves it as <project>/project.blend,
* starts the bridge server so the studio connects immediately.
"""
import argparse
import os
import sys
from pathlib import Path

import addon_utils
import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--project", required=True)
ap.add_argument("--engine-dir", default="")
ap.add_argument("--addon-dir", default=str(Path(__file__).resolve().parent))
ap.add_argument("--bg-mode", default="cyan_studio")
args = ap.parse_args(argv)

project = Path(args.project)
project.mkdir(parents=True, exist_ok=True)
blend = project / "project.blend"
if args.engine_dir:
    os.environ["SK_ENGINE_DIR"] = args.engine_dir
    if args.engine_dir not in sys.path:
        sys.path.insert(0, args.engine_dir)
os.environ["SK_BRIDGE_NO_AUTOSTART"] = "1"  # we start it explicitly below

# 1. Load the bridge add-on (prefer the installed copy, fall back to the repo copy).
bridge = None
try:
    addon_utils.enable("stick_knowledge_bridge", default_set=True, persistent=True)
    bridge = sys.modules.get("stick_knowledge_bridge")
except Exception as e:
    print(f"[SK Launch] installed add-on not available: {e}")
if bridge is None:
    if args.addon_dir not in sys.path:
        sys.path.insert(0, args.addon_dir)
    import stick_knowledge_bridge as bridge  # noqa: E402
    bridge.register()

# 2. BlenderKit (best effort — installed by the studio beforehand).
try:
    addon_utils.enable("blenderkit", default_set=True, persistent=True)
except Exception as e:
    print(f"[SK Launch] BlenderKit not enabled: {e}")

# 3. Project scene.
import zdf_helpers as zdf  # noqa: E402

zdf.configure(project_dir=str(project), assets_dir=str(project / "assets"))
if not bpy.data.filepath:
    zdf.init_zdf_studio(render_engine="EEVEE_NEXT", bg_mode=args.bg_mode, factory_reset=False)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    print(f"[SK Launch] created {blend}")
else:
    print(f"[SK Launch] opened {bpy.data.filepath}")

# 4. Bridge server.
port = bridge.start_server()
print(f"[SK Launch] bridge ready on port {port}")
