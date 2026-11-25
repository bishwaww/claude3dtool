"""
Stick Knowledge Bridge — live JSON-RPC link between Stick Knowledge 3D Studio and an
open Blender session.

Threading model (keeps the Blender UI responsive):
  * A background thread owns the TCP socket (127.0.0.1, default port 9876). It only
    reads/writes bytes; it never touches bpy.
  * Each request is queued; a bpy.app.timers callback on Blender's MAIN thread pops
    requests and executes them (bpy is not thread-safe), then hands the reply back.

Protocol: one JSON object per line.
  request  {"id": 1, "token": "...", "cmd": "ping", "params": {}}
  response {"id": 1, "ok": true, "result": {...}}  |  {"id": 1, "ok": false, "error": "...", "traceback": "..."}

Discovery: the live port + auth token are written to
  %TEMP%/stick_knowledge_bridge.json  so the studio backend can connect.
"""
from __future__ import annotations

bl_info = {
    "name": "Stick Knowledge Bridge",
    "author": "Stick Knowledge 3D Studio",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Stick Knowledge",
    "description": "Lets Stick Knowledge 3D Studio (Claude) build, inspect and render this Blender session live",
    "category": "System",
}

import base64
import contextlib
import io
import json
import os
import queue
import secrets
import socket
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

import bpy

DEFAULT_PORT = 9876
PORT_RANGE = range(DEFAULT_PORT, DEFAULT_PORT + 6)
DISCOVERY_FILE = Path(tempfile.gettempdir()) / "stick_knowledge_bridge.json"
ADDON_DIR = Path(__file__).resolve().parent
PROTOCOL_VERSION = 1

_state = {
    "server": None,       # socket
    "thread": None,
    "port": None,
    "token": None,
    "running": False,
    "clients": 0,
    "last_cmd": "",
    "last_error": "",
    "render": {"running": False, "frame": 0, "start": 0, "end": 0, "done": False,
               "cancelled": False, "output": "", "started_at": 0.0},
}
_requests: "queue.Queue[dict]" = queue.Queue()
_namespace: dict = {}


# ------------------------------------------------------------------------------
# Engine (zdf_helpers) discovery
# ------------------------------------------------------------------------------

def _engine_dir() -> str:
    cands = [os.environ.get("SK_ENGINE_DIR", "")]
    p = ADDON_DIR / "engine_path.txt"
    if p.is_file():
        cands.append(p.read_text(encoding="utf-8").strip())
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
        cands.append(getattr(prefs, "engine_dir", ""))
    except Exception:
        pass
    for c in cands:
        if c and (Path(c) / "zdf_helpers.py").is_file():
            return c
    return ""


def _zdf():
    eng = _engine_dir()
    if eng and eng not in sys.path:
        sys.path.insert(0, eng)
    try:
        import zdf_helpers  # noqa: WPS433
        return zdf_helpers
    except Exception:
        return None


def _project_dir() -> Path | None:
    z = _zdf()
    if z is not None and z._CONFIG.get("project_dir"):
        return Path(z._CONFIG["project_dir"])
    if bpy.data.filepath:
        return Path(bpy.data.filepath).parent
    return None


# ------------------------------------------------------------------------------
# Command handlers (run on the main thread)
# ------------------------------------------------------------------------------

def cmd_ping(params):
    return {
        "app": "stick_knowledge_bridge",
        "protocol": PROTOCOL_VERSION,
        "addon_version": ".".join(map(str, bl_info["version"])),
        "blender": bpy.app.version_string,
        "file": bpy.data.filepath,
        "dirty": bool(bpy.data.is_dirty),
        "background": bool(bpy.app.background),
        "zdf_helpers": _zdf() is not None,
    }


def _obj_info(o):
    info = {
        "name": o.name, "type": o.type,
        "location": [round(v, 4) for v in o.location],
        "rotation": [round(v, 4) for v in o.rotation_euler],
        "scale": [round(v, 4) for v in o.scale],
        "dimensions": [round(v, 4) for v in o.dimensions],
        "parent": o.parent.name if o.parent else None,
        "collections": [c.name for c in o.users_collection],
        "hide_render": o.hide_render,
    }
    if o.type in ("MESH", "CURVE") and getattr(o.data, "materials", None):
        info["materials"] = [m.name for m in o.data.materials if m]
    if o.modifiers:
        info["modifiers"] = [f"{m.name}:{m.type}" for m in o.modifiers]
    return info


def cmd_get_scene_info(params):
    scene = bpy.context.scene
    limit = int(params.get("limit", 150))

    def walk(col, depth=0):
        return {"name": col.name, "objects": len(col.objects),
                "children": [walk(c, depth + 1) for c in col.children] if depth < 4 else []}

    objs = list(scene.objects)
    return {
        "file": bpy.data.filepath, "dirty": bool(bpy.data.is_dirty),
        "scene": scene.name, "frame_current": scene.frame_current,
        "frame_start": scene.frame_start, "frame_end": scene.frame_end, "fps": scene.render.fps,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "engine": scene.render.engine,
        "view_transform": scene.view_settings.view_transform,
        "camera": scene.camera.name if scene.camera else None,
        "cameras": [o.name for o in objs if o.type == "CAMERA"],
        "markers": [(m.name, m.frame, m.camera.name if m.camera else None) for m in scene.timeline_markers],
        "collections": walk(scene.collection),
        "object_count": len(objs),
        "objects": [_obj_info(o) for o in objs[:limit]],
        "materials": [m.name for m in bpy.data.materials][:200],
        "truncated": len(objs) > limit,
    }


def cmd_execute_python(params):
    code = params.get("code", "")
    if not _namespace:
        import math
        import mathutils
        _namespace.update({"bpy": bpy, "math": math, "mathutils": mathutils, "Vector": mathutils.Vector,
                           "__name__": "sk_live"})
    z = _zdf()
    if z is not None:
        _namespace["zdf"] = z
    _namespace.pop("result", None)
    out, err = io.StringIO(), io.StringIO()
    t0 = time.time()
    try:
        bpy.ops.ed.undo_push(message="Before Claude edit")
    except Exception:
        pass
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            exec(compile(code, "<claude>", "exec"), _namespace)
    except Exception as e:
        return {"ok": False, "stdout": out.getvalue()[-8000:], "stderr": err.getvalue()[-4000:],
                "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-6000:],
                "seconds": round(time.time() - t0, 2)}
    try:
        bpy.ops.ed.undo_push(message="Claude edit")
    except Exception:
        pass
    res = _namespace.get("result")
    try:
        json.dumps(res)
    except Exception:
        res = repr(res)
    return {"ok": True, "stdout": out.getvalue()[-8000:], "stderr": err.getvalue()[-4000:],
            "result": res, "seconds": round(time.time() - t0, 2)}


def cmd_import_asset(params):
    z = _zdf()
    if z is None:
        raise RuntimeError("zdf_helpers not found; reinstall the bridge from the studio.")
    path = params["path"]
    kind = params.get("kind", "asset")
    loc = tuple(params.get("location", (0, 0, 0)))
    name = params.get("name") or Path(path).stem
    col = None
    if params.get("collection"):
        col = bpy.data.collections.get(params["collection"])
        if col is None:
            col = bpy.data.collections.new(params["collection"])
            bpy.context.scene.collection.children.link(col)
    if kind == "mixamo":
        arm = z.import_mixamo_character(path, params.get("anim_path"), location=loc,
                                        start_frame=int(params.get("start_frame", 1)),
                                        target_height=float(params.get("target_height", 1.75)),
                                        name=name, collection=col)
        if arm is None:
            raise RuntimeError(f"Could not import Mixamo character {path}")
        return {"armature": arm.name, "objects": [c.name for c in arm.children]}
    obj = z.import_and_normalize_asset(path, target_height=float(params.get("target_height", 1.0)),
                                       location=loc, rotation=tuple(params.get("rotation", (0, 0, 0))),
                                       collection=col, name=name)
    if obj is None:
        raise RuntimeError(f"Import failed for {path}")
    return {"object": obj.name, "dimensions": [round(v, 4) for v in obj.dimensions]}


def cmd_capture_viewport(params):
    """Quick render of the active (or given) camera to PNG; returns base64."""
    scene = bpy.context.scene
    if params.get("camera"):
        cam = bpy.data.objects.get(params["camera"])
        if cam is None:
            raise RuntimeError(f"No camera named {params['camera']}")
    else:
        cam = scene.camera
    if cam is None:
        raise RuntimeError("Scene has no camera. Create one (zdf.make_shot) before capturing.")
    width = int(params.get("width", 540))
    prev = {
        "frame": scene.frame_current, "camera": scene.camera, "engine": scene.render.engine,
        "pct": scene.render.resolution_percentage, "path": scene.render.filepath,
        "fmt": scene.render.image_settings.file_format,
    }
    eevee = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
    samples_prev = getattr(scene.eevee, "taa_render_samples", None)
    out = Path(tempfile.gettempdir()) / f"sk_capture_{int(time.time() * 1000)}.png"
    try:
        if params.get("frame") is not None:
            scene.frame_set(int(params["frame"]))
        markers = [m for m in scene.timeline_markers if m.camera and m.frame <= scene.frame_current]
        scene.camera = cam if params.get("camera") or not markers else max(markers, key=lambda m: m.frame).camera
        scene.render.engine = eevee
        scene.render.resolution_percentage = max(5, min(100, round(100 * width / scene.render.resolution_x)))
        if samples_prev is not None:
            scene.eevee.taa_render_samples = int(params.get("samples", 16))
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(out)
        bpy.ops.render.render(write_still=True)
        data = out.read_bytes()
    finally:
        scene.frame_set(prev["frame"])
        scene.camera = prev["camera"]
        scene.render.engine = prev["engine"]
        scene.render.resolution_percentage = prev["pct"]
        scene.render.filepath = prev["path"]
        scene.render.image_settings.file_format = prev["fmt"]
        if samples_prev is not None:
            scene.eevee.taa_render_samples = samples_prev
        try:
            out.unlink()
        except Exception:
            pass
    return {"png_base64": base64.b64encode(data).decode("ascii"), "frame": int(params.get("frame") or prev["frame"]),
            "camera": (scene.camera.name if scene.camera else None), "bytes": len(data)}


def cmd_save_project(params):
    path = params.get("path") or bpy.data.filepath
    if not path:
        pd = _project_dir()
        if pd is None:
            raise RuntimeError("No path given and the file has never been saved.")
        path = str(pd / "project.blend")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if params.get("pack", False):
        try:
            bpy.ops.file.pack_all()
        except Exception as e:
            print(f"[SK Bridge] pack_all warning: {e}")
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    return {"file": bpy.data.filepath}


def cmd_open_project(params):
    """Open <path>; if missing and create=True, build a fresh ZDF studio and save it there."""
    path = Path(params["path"])
    z = _zdf()
    if z is not None and params.get("project_dir"):
        z.configure(project_dir=params["project_dir"], assets_dir=str(Path(params["project_dir"]) / "assets"))
    if path.is_file():
        if bpy.data.filepath and Path(bpy.data.filepath) == path:
            return {"file": bpy.data.filepath, "created": False, "loading": False}

        def _deferred_open():
            # Loading replaces the window data the request's context override points
            # at, so it runs on its own tick; clients poll ping until file == path.
            try:
                bpy.ops.wm.open_mainfile(filepath=str(path))
            except Exception as e:
                _state["last_error"] = f"open failed: {e}"
            return None

        bpy.app.timers.register(_deferred_open, first_interval=0.1)
        return {"file": str(path), "created": False, "loading": True}
    if not params.get("create", True):
        raise RuntimeError(f"{path} does not exist")
    if z is None:
        raise RuntimeError("zdf_helpers not found; cannot initialise a studio scene.")
    z.init_zdf_studio(render_engine=params.get("render_engine", "EEVEE_NEXT"),
                      bg_mode=params.get("bg_mode", "cyan_studio"), factory_reset=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    return {"file": bpy.data.filepath, "created": True}


def cmd_init_studio(params):
    z = _zdf()
    if z is None:
        raise RuntimeError("zdf_helpers not found.")
    z.init_zdf_studio(render_engine=params.get("render_engine", "EEVEE_NEXT"),
                      bg_mode=params.get("bg_mode", "cyan_studio"),
                      cycles_samples=int(params.get("cycles_samples", 64)), factory_reset=False)
    return {"objects": len(bpy.context.scene.objects)}


# --- animation rendering (non-blocking in the UI) ---

def _on_render_post(scene, *_):
    r = _state["render"]
    r["frame"] = scene.frame_current


def _on_render_complete(scene, *_):
    r = _state["render"]
    r["running"], r["done"] = False, True
    _remove_render_handlers()


def _on_render_cancel(scene, *_):
    r = _state["render"]
    r["running"], r["cancelled"] = False, True
    _remove_render_handlers()


def _remove_render_handlers():
    for lst, fn in ((bpy.app.handlers.render_post, _on_render_post),
                    (bpy.app.handlers.render_complete, _on_render_complete),
                    (bpy.app.handlers.render_cancel, _on_render_cancel)):
        if fn in lst:
            lst.remove(fn)


def cmd_render_animation(params):
    scene = bpy.context.scene
    r = _state["render"]
    if r["running"]:
        raise RuntimeError("A render is already running.")
    out_dir = Path(params.get("output_dir") or ((_project_dir() or Path(tempfile.gettempdir())) / "renders" / "frames"))
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = params.get("engine", "EEVEE")
    if engine.upper().startswith("CYCLES"):
        scene.render.engine = "CYCLES"
        scene.cycles.samples = int(params.get("samples", 64))
        try:
            scene.cycles.device = "GPU"
        except Exception:
            pass
    else:
        ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in ids else "BLENDER_EEVEE"
    scene.frame_start = int(params.get("start", scene.frame_start))
    scene.frame_end = int(params.get("end", scene.frame_end))
    scene.render.resolution_percentage = int(params.get("resolution_pct", 100))
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(out_dir / "frame_")
    r.update({"running": True, "frame": scene.frame_start, "start": scene.frame_start, "end": scene.frame_end,
              "done": False, "cancelled": False, "output": str(out_dir), "started_at": time.time()})
    bpy.app.handlers.render_post.append(_on_render_post)
    bpy.app.handlers.render_complete.append(_on_render_complete)
    bpy.app.handlers.render_cancel.append(_on_render_cancel)
    if bpy.app.background:
        bpy.ops.render.render(animation=True)
        r["running"], r["done"] = False, True
        _remove_render_handlers()
    else:
        bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
    return dict(r)


def cmd_render_status(params):
    return dict(_state["render"])


def cmd_reload_helpers(params):
    """Reload zdf_helpers after the studio updated it (no Blender restart needed)."""
    import importlib
    z = _zdf()
    if z is None:
        raise RuntimeError("zdf_helpers not found.")
    cfg = dict(z._CONFIG) if hasattr(z, "_CONFIG") else {}
    z = importlib.reload(z)
    if cfg and hasattr(z, "configure"):
        z.configure(**{k: v for k, v in cfg.items() if v})
    _namespace["zdf"] = z
    return {"reloaded": True, "functions": len([n for n in dir(z) if not n.startswith("_")])}


COMMANDS = {
    "reload_helpers": cmd_reload_helpers,
    "ping": cmd_ping,
    "get_scene_info": cmd_get_scene_info,
    "execute_python": cmd_execute_python,
    "import_asset": cmd_import_asset,
    "capture_viewport": cmd_capture_viewport,
    "save_project": cmd_save_project,
    "open_project": cmd_open_project,
    "init_studio": cmd_init_studio,
    "render_animation": cmd_render_animation,
    "render_status": cmd_render_status,
}


# ------------------------------------------------------------------------------
# Main-thread pump
# ------------------------------------------------------------------------------

def _pump():
    deadline = time.time() + 0.05
    while time.time() < deadline:
        try:
            req = _requests.get_nowait()
        except queue.Empty:
            break
        cmd = req["msg"].get("cmd", "")
        _state["last_cmd"] = cmd
        handler = COMMANDS.get(cmd)
        try:
            if handler is None:
                raise RuntimeError(f"Unknown command '{cmd}'")
            with _ui_context():
                result = handler(req["msg"].get("params") or {})
            req["reply"] = {"ok": True, "result": result}
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"
            req["reply"] = {"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-6000:]}
        req["event"].set()
        _tag_redraw()
    return 0.05 if _state["running"] else None


@contextlib.contextmanager
def _ui_context():
    """Timers run without a window/area, so operators (bpy.ops.mesh.*, mode_set, uv.*)
    would fail their poll(). Borrow the main window and a 3D View for the call."""
    wm = bpy.context.window_manager
    win = wm.windows[0] if wm and wm.windows else None
    if win is None:
        yield
        return
    area = next((a for a in win.screen.areas if a.type == "VIEW_3D"), None)
    kwargs = {"window": win, "screen": win.screen}
    if area is not None:
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        kwargs.update(area=area, region=region)
    with bpy.context.temp_override(**kwargs):
        yield


def _tag_redraw():
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass


# ------------------------------------------------------------------------------
# Socket thread
# ------------------------------------------------------------------------------

def _serve_client(conn: socket.socket):
    _state["clients"] += 1
    buf = b""
    try:
        conn.settimeout(None)
        while _state["running"]:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except Exception as e:
                    conn.sendall((json.dumps({"id": None, "ok": False, "error": f"bad json: {e}"}) + "\n").encode())
                    continue
                if msg.get("token") != _state["token"] and msg.get("cmd") != "ping":
                    reply = {"ok": False, "error": "auth: bad or missing token"}
                else:
                    req = {"msg": msg, "event": threading.Event(), "reply": None}
                    _requests.put(req)
                    timeout = float(msg.get("timeout", 900))
                    if not req["event"].wait(timeout):
                        reply = {"ok": False, "error": f"timeout after {timeout}s (Blender busy?)"}
                    else:
                        reply = req["reply"]
                reply["id"] = msg.get("id")
                conn.sendall((json.dumps(reply, default=str) + "\n").encode("utf-8"))
    except (ConnectionResetError, OSError):
        pass
    finally:
        _state["clients"] -= 1
        try:
            conn.close()
        except Exception:
            pass


def _accept_loop(server: socket.socket):
    while _state["running"]:
        try:
            conn, _addr = server.accept()
        except OSError:
            break
        threading.Thread(target=_serve_client, args=(conn,), daemon=True).start()


def _write_discovery():
    DISCOVERY_FILE.write_text(json.dumps({
        "port": _state["port"], "token": _state["token"], "pid": os.getpid(),
        "blender": bpy.app.version_string, "started": time.time(), "protocol": PROTOCOL_VERSION,
    }), encoding="utf-8")


def start_server(port: int | None = None) -> int:
    if _state["running"]:
        return _state["port"]
    ports = [port] if port else list(PORT_RANGE)
    last_err = None
    for p in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            s.listen(4)
        except OSError as e:
            last_err = e
            s.close()
            continue
        _state.update({"server": s, "port": p, "running": True, "token": secrets.token_hex(16)})
        t = threading.Thread(target=_accept_loop, args=(s,), daemon=True, name="SKBridgeAccept")
        _state["thread"] = t
        t.start()
        if not bpy.app.timers.is_registered(_pump):
            bpy.app.timers.register(_pump, first_interval=0.05, persistent=True)
        _write_discovery()
        print(f"[SK Bridge] listening on 127.0.0.1:{p}")
        return p
    raise RuntimeError(f"No free port in {list(ports)}: {last_err}")


def stop_server():
    _state["running"] = False
    s = _state.get("server")
    if s:
        try:
            s.close()
        except Exception:
            pass
    _state["server"] = None
    try:
        if DISCOVERY_FILE.is_file() and json.loads(DISCOVERY_FILE.read_text()).get("pid") == os.getpid():
            DISCOVERY_FILE.unlink()
    except Exception:
        pass
    if bpy.app.timers.is_registered(_pump):
        bpy.app.timers.unregister(_pump)
    print("[SK Bridge] stopped")


# ------------------------------------------------------------------------------
# UI
# ------------------------------------------------------------------------------

class SKBridgePreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    autostart: bpy.props.BoolProperty(name="Start bridge when Blender opens", default=True)
    port: bpy.props.IntProperty(name="Preferred port", default=DEFAULT_PORT, min=1024, max=65535)
    engine_dir: bpy.props.StringProperty(name="zdf_helpers folder", subtype="DIR_PATH", default="")

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "autostart")
        col.prop(self, "port")
        col.prop(self, "engine_dir")


class SK_OT_bridge_toggle(bpy.types.Operator):
    bl_idname = "sk_bridge.toggle"
    bl_label = "Start / Stop Bridge"

    def execute(self, context):
        if _state["running"]:
            stop_server()
        else:
            try:
                start_server()
            except Exception as e:
                self.report({"ERROR"}, str(e))
                return {"CANCELLED"}
        return {"FINISHED"}


class SK_PT_bridge(bpy.types.Panel):
    bl_label = "Stick Knowledge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Stick Knowledge"

    def draw(self, context):
        col = self.layout.column(align=True)
        if _state["running"]:
            col.label(text=f"Bridge live · port {_state['port']}", icon="LINKED")
            col.label(text=f"Studio clients: {_state['clients']}")
            if _state["last_cmd"]:
                col.label(text=f"Last: {_state['last_cmd']}")
            r = _state["render"]
            if r["running"]:
                col.label(text=f"Rendering {r['frame']}/{r['end']}", icon="RENDER_ANIMATION")
        else:
            col.label(text="Bridge stopped", icon="UNLINKED")
        col.operator("sk_bridge.toggle", text="Stop Bridge" if _state["running"] else "Start Bridge")


_CLASSES = (SKBridgePreferences, SK_OT_bridge_toggle, SK_PT_bridge)


def _autostart():
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
        if not prefs.autostart or bpy.app.background:
            return None
        start_server(None)
    except Exception as e:
        print(f"[SK Bridge] autostart failed: {e}")
    return None


def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)
    if os.environ.get("SK_BRIDGE_NO_AUTOSTART") != "1":
        bpy.app.timers.register(_autostart, first_interval=1.0)


def unregister():
    stop_server()
    _remove_render_handlers()
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)
