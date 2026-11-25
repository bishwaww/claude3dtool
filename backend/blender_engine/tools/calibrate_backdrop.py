"""
Calibrate zdf_helpers.BACKDROP_LINEAR so rendered backdrop pixels match the colours
measured from the reference Shorts (BACKDROP_TARGETS), through AgX.

Run:  blender --background --factory-startup --python tools/calibrate_backdrop.py
Prints the corrected BACKDROP_LINEAR dict to paste into zdf_helpers.py.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bpy  # noqa: E402
import zdf_helpers as zdf  # noqa: E402

W, H = 54, 96


def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_lin(h):
    return [srgb_to_lin(int(h.lstrip("#")[i:i + 2], 16) / 255) for i in (0, 2, 4)]


def render(mode):
    zdf.init_zdf_studio(render_engine="EEVEE_NEXT", bg_mode=mode)
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = W, H
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    scene.collection.objects.link(cam)
    cam.location = (0, -3, 1)
    cam.rotation_euler = (1.4, 0, 0)
    scene.camera = cam
    for o in list(bpy.data.objects):  # backdrop only: remove the studio lights
        if o.type == "LIGHT":
            bpy.data.objects.remove(o)
    out = Path(tempfile.gettempdir()) / f"zdf_cal_{mode}.png"
    scene.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(str(out), check_existing=False)
    px = list(img.pixels)
    bpy.data.images.remove(img)

    def at(fx, fy):  # fy measured from the TOP of the frame
        x, y = int(fx * (W - 1)), int((1 - fy) * (H - 1))
        i = (y * W + x) * 4
        return px[i:i + 3]
    return at


print(f"[calibrate] view transform: {zdf.VIEW_TRANSFORM} / look: {zdf.VIEW_LOOK}")
# start from the plain sRGB->linear targets (exact for a neutral display transform)
for _mode, _keys in zdf.BACKDROP_TARGETS.items():
    for _k, _hex in _keys.items():
        zdf.BACKDROP_LINEAR[_mode][_k] = tuple(hex_lin(_hex))

SAMPLES = {
    "cyan_studio": {"inner": (0.5, 0.54), "outer": (0.02, 0.02)},
    "sky_gradient": {"top": (0.5, 0.01), "bottom": (0.5, 0.58)},
    "dark_space": {"inner": (0.5, 0.54), "outer": (0.02, 0.02)},
    "interior": {"flat": (0.5, 0.5)},
}

for it in range(5):
    worst = 0.0
    for mode, pts in SAMPLES.items():
        at = render(mode)
        for key, (fx, fy) in pts.items():
            got = [srgb_to_lin(c) for c in at(fx, fy)]
            want = hex_lin(zdf.BACKDROP_TARGETS[mode][key])
            cur = list(zdf.BACKDROP_LINEAR[mode][key])
            err = max(abs(g ** (1 / 2.2) - w ** (1 / 2.2)) for g, w in zip(got, want))
            worst = max(worst, err)
            if err < 0.008:
                continue  # this key is already on target; don't disturb it
            new = [max(0.0, c * ((w + 1e-3) / (g + 1e-3)) ** 0.5) for c, g, w in zip(cur, got, want)]
            zdf.BACKDROP_LINEAR[mode][key] = tuple(round(v, 5) for v in new)
    print(f"[calibrate] iteration {it + 1}: worst channel error (gamma space) = {worst:.3f}")
    if worst < 0.012:
        break

print("BACKDROP_LINEAR =", zdf.BACKDROP_LINEAR)
for mode, pts in SAMPLES.items():
    at = render(mode)
    for key, (fx, fy) in pts.items():
        r, g, b = (round(c * 255) for c in at(fx, fy))
        print(f"  {mode}.{key}: rendered #{r:02X}{g:02X}{b:02X} target {zdf.BACKDROP_TARGETS[mode][key]}")
