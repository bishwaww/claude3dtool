"""
Stick Knowledge 3D Studio — Master Reusable Blender Python (`bpy`) Engine Helpers
Compatible with Blender 4.2 through 5.3+.
"""
from __future__ import annotations

import math
import os
import random
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import bpy
from mathutils import Euler, Matrix, Vector


# ==============================================================================
# INTERNAL COMPATIBILITY UTILITIES (Blender 4.2 - 5.3+)
# ==============================================================================

def _set_bsdf_input(bsdf, names: Sequence[str], value: Any) -> None:
    for name in names:
        if name in bsdf.inputs:
            try:
                bsdf.inputs[name].default_value = value
                return
            except Exception:
                pass


def _link_to_collection(obj: bpy.types.Object, collection: Optional[bpy.types.Collection] = None) -> None:
    target_col = collection or bpy.context.scene.collection
    if obj.name not in target_col.objects:
        target_col.objects.link(obj)
    for col in list(obj.users_collection):
        if col != target_col:
            col.objects.unlink(obj)


def _shade_smooth_safe(obj: bpy.types.Object) -> None:
    if obj.type != "MESH" or not obj.data:
        return
    try:
        mesh = obj.data
        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
        mesh.update()
    except Exception:
        pass


def _available_render_engines() -> list[str]:
    try:
        return [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    except Exception:
        return ["BLENDER_EEVEE", "CYCLES"]


def _resolve_eevee_engine() -> str:
    engines = _available_render_engines()
    if "BLENDER_EEVEE_NEXT" in engines:
        return "BLENDER_EEVEE_NEXT"
    if "BLENDER_EEVEE" in engines:
        return "BLENDER_EEVEE"
    return engines[0] if engines else "BLENDER_EEVEE"


def _action_fcurves(action: Optional[bpy.types.Action], slot: Any = None) -> list:
    """F-curves of an action on Blender 4.2 (legacy) and 4.4+/5.x (layered/slotted)."""
    if action is None:
        return []
    legacy = getattr(action, "fcurves", None)
    if legacy is not None and not getattr(action, "is_action_layered", False):
        return list(legacy)
    out: list = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            slots = [slot] if slot is not None else list(getattr(action, "slots", []))
            for s in slots:
                try:
                    bag = strip.channelbag(s)
                except Exception:
                    bag = None
                if bag is not None:
                    out.extend(bag.fcurves)
    if not out and legacy is not None:
        out = list(legacy)
    return out


def _set_bezier_interpolation(obj: bpy.types.Object, interpolation: str = "BEZIER") -> None:
    if not obj.animation_data or not obj.animation_data.action:
        return
    action = obj.animation_data.action
    fcurves = _action_fcurves(action, getattr(obj.animation_data, "action_slot", None))
    for fc in fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = interpolation
            if interpolation == "BEZIER":
                kp.handle_left_type = "AUTO_CLAMPED"
                kp.handle_right_type = "AUTO_CLAMPED"


# ==============================================================================
# 1. STUDIO INITIALIZATION (9:16 1080x1920, AgX, CYAN CYCLORAMA, 3-POINT LIGHTS)
# ==============================================================================

def init_zdf_studio(
    render_engine: str = "EEVEE_NEXT",
    bg_mode: str = "cyan_studio",
    cycles_samples: int = 64,
    fps: int = 30,
    cyclorama: bool = False,
    factory_reset: bool = True,
) -> dict[str, Any]:
    """
    Initializes a clean Zack D. Films 9:16 (1080x1920, 30fps) studio scene:
      - AgX Color Management with Medium High Contrast
      - Curved Studio Cyclorama with vibrant Sky-Blue/Cyan radial gradient (#9EE2FF -> #26A6F5)
        or dark cinematic navy/black (#060B14) for space/microscopic/dark scenes
      - 3-point softbox studio area lighting (warm key, cool fill, crisp rim)
      - EEVEE Next (Raytracing) or Cycles GPU OptiX + OpenImageDenoise (6GB+ VRAM safe)
    """
    # Wipe the scene. Headless builds use a factory reset; the LIVE bridge must pass
    # factory_reset=False — a factory reset in an open Blender would reset the user's
    # preferences and unload every add-on (including the bridge itself).
    if factory_reset:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    else:
        clear_scene()
    scene = bpy.context.scene

    # Resolution & FPS (9:16 Shorts)
    scene.render.resolution_x = 1080
    scene.render.resolution_y = 1920
    scene.render.resolution_percentage = 100
    scene.render.fps = int(fps)
    scene.render.fps_base = 1.0
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False

    # Color management (see VIEW_TRANSFORM note in section 11.1)
    try:
        scene.view_settings.view_transform = VIEW_TRANSFORM
        try:
            scene.view_settings.look = VIEW_LOOK
        except Exception:
            scene.view_settings.look = "None"
    except Exception:
        try:
            scene.view_settings.view_transform = "AgX"
        except Exception:
            scene.view_settings.view_transform = "Filmic"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0

    # Render Engine Configuration
    if render_engine in ("CYCLES_OPTIX", "CYCLES"):
        try:
            bpy.ops.preferences.addon_enable(module="cycles")
        except Exception:
            pass
        engines = _available_render_engines()
        if "CYCLES" in engines:
            scene.render.engine = "CYCLES"
            scene.cycles.samples = max(32, min(128, int(cycles_samples)))
            scene.cycles.use_adaptive_sampling = True
            scene.cycles.adaptive_threshold = 0.02
            scene.cycles.use_denoising = True
            try:
                scene.cycles.denoiser = "OPENIMAGEDENOISE"
            except Exception:
                pass
            # Memory-safe VRAM config for 6GB+ GPUs
            scene.cycles.max_bounces = 8
            scene.cycles.diffuse_bounces = 4
            scene.cycles.glossy_bounces = 4
            scene.cycles.transmission_bounces = 6
            scene.cycles.transparent_max_bounces = 6
            if hasattr(scene.cycles, "use_auto_tile"):
                scene.cycles.use_auto_tile = True
                scene.cycles.tile_size = 512
            if hasattr(scene.render, "use_persistent_data"):
                scene.render.use_persistent_data = False

            # Configure OptiX -> CUDA -> HIP -> CPU fallback
            try:
                prefs = bpy.context.preferences.addons["cycles"].preferences
                gpu_configured = False
                for device_type in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
                    try:
                        prefs.compute_device_type = device_type
                        prefs.get_devices()
                        usable = [d for d in prefs.devices if d.type == device_type]
                        if usable:
                            for d in prefs.devices:
                                d.use = d.type == device_type
                            scene.cycles.device = "GPU"
                            gpu_configured = True
                            break
                    except Exception:
                        continue
                if not gpu_configured:
                    scene.cycles.device = "CPU"
            except Exception:
                scene.cycles.device = "CPU"
        else:
            scene.render.engine = _resolve_eevee_engine()
    else:
        scene.render.engine = _resolve_eevee_engine()
        eevee = scene.eevee
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = 48
        if hasattr(eevee, "use_raytracing"):
            eevee.use_raytracing = True
        if hasattr(eevee, "use_shadows"):
            eevee.use_shadows = True

    # Create Studio Environment Collection
    studio_col = bpy.data.collections.new("ZDF_Studio_Rig")
    scene.collection.children.link(studio_col)

    # Frame-locked ZDF backdrop (camera rays) + soft ambient light (all other rays).
    # Measured from the reference Shorts — see setup_zdf_backdrop().
    world = bpy.data.worlds.new("ZDF_World")
    scene.world = world
    setup_zdf_backdrop(bg_mode)

    # Optional physical cyclorama (only when a scene needs a visible floor cove).
    cyc = _build_studio_cyclorama(studio_col, bg_mode=bg_mode) if cyclorama else None

    # 3-Point Soft Studio Area Lighting
    lights = _build_three_point_lighting(studio_col)

    return {"studio_collection": studio_col, "cyclorama": cyc, "lights": lights}


def clear_scene(keep_world: bool = False) -> None:
    """Remove every object, collection and orphan datablock from the current scene
    without touching preferences or add-ons (safe inside a live Blender session)."""
    scene = bpy.context.scene
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    scene.timeline_markers.clear()
    if scene.animation_data:
        scene.animation_data_clear()
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights,
                 bpy.data.armatures, bpy.data.actions, bpy.data.node_groups, bpy.data.images):
        for block in list(coll):
            if block.users == 0 or (coll is bpy.data.actions and not block.use_fake_user):
                try:
                    coll.remove(block)
                except Exception:
                    pass
    if not keep_world:
        for w in list(bpy.data.worlds):
            if w.users == 0 or w == scene.world:
                scene.world = None
                try:
                    bpy.data.worlds.remove(w)
                except Exception:
                    pass


def _build_studio_cyclorama(studio_col: bpy.types.Collection, bg_mode: str = "cyan_studio") -> bpy.types.Object:
    """Builds a smooth seamless L-curve studio cyclorama with radial #9EE2FF -> #26A6F5 gradient."""
    bpy.ops.mesh.primitive_plane_add(size=18.0, location=(0.0, 4.5, 0.0))
    cyc = bpy.context.active_object
    cyc.name = "ZDF_Studio_Cyclorama"
    _link_to_collection(cyc, studio_col)

    # Build curved backdrop mesh procedurally (floor + smooth bevel curve up to vertical wall)
    mesh = bpy.data.meshes.new("ZDF_Cyclorama_Mesh")
    verts = []
    faces = []
    width = 22.0
    x_segs = 12
    profile_pts = []
    # Floor from y=-6 to y=2.5
    for y in (-7.0, -3.0, 0.5, 2.2):
        profile_pts.append((y, -0.02))
    # Smooth quarter-circle cove radius 3.2m
    cove_r = 3.2
    cove_cy = 2.2
    cove_cz = cove_r - 0.02
    steps = 12
    for i in range(1, steps + 1):
        ang = -math.pi / 2 + (math.pi / 2) * (i / steps)
        py = cove_cy + math.cos(ang) * cove_r
        pz = cove_cz + math.sin(ang) * cove_r
        profile_pts.append((py, pz))
    # Tall vertical wall up to z=16
    for z in (6.5, 11.0, 16.5):
        profile_pts.append((cove_cy + cove_r, z))

    for yi, (py, pz) in enumerate(profile_pts):
        for xi in range(x_segs + 1):
            px = -width / 2 + width * (xi / x_segs)
            verts.append((px, py, pz))

    row_len = x_segs + 1
    for yi in range(len(profile_pts) - 1):
        for xi in range(x_segs):
            v0 = yi * row_len + xi
            v1 = v0 + 1
            v2 = v0 + row_len + 1
            v3 = v0 + row_len
            faces.append((v0, v1, v2, v3))

    mesh.from_pydata(verts, [], faces)
    mesh.update()
    cyc.data = mesh
    _shade_smooth_safe(cyc)

    # Shader: Radial Sky-Blue / Cyan Glow (#9EE2FF center -> #26A6F5 outer)
    # plus switchable dark space mode (#060B14) via ZDF_BgModeMix
    mat = bpy.data.materials.new("ZDF_Cyclorama_Mat")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    _set_bsdf_input(bsdf, ["Roughness"], 0.85)
    _set_bsdf_input(bsdf, ["Specular IOR Level", "Specular"], 0.08)

    tex_coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Location"].default_value = (0.0, -0.75, -0.25)
    mapping.inputs["Scale"].default_value = (0.16, 0.16, 0.14)

    grad = nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "QUADRATIC_SPHERE"

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "EASE"
    # Outer edge: #26A6F5 (sRGB -> linear approx (0.019, 0.38, 0.91))
    ramp.color_ramp.elements[0].position = 0.05
    ramp.color_ramp.elements[0].color = (0.020, 0.36, 0.90, 1.0)
    # Soft center glow: #9EE2FF (sRGB -> linear approx (0.34, 0.76, 1.0))
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (0.38, 0.80, 1.0, 1.0)

    # Dark Space color (#060B14 -> linear approx (0.002, 0.004, 0.010))
    mode_mix = nodes.new("ShaderNodeMix")
    mode_mix.data_type = "RGBA"
    mode_mix.name = "ZDF_BgModeMix"
    mode_mix.inputs[0].default_value = 1.0 if bg_mode == "dark_space" else 0.0
    mode_mix.inputs[7].default_value = (0.003, 0.006, 0.015, 1.0)

    # Subtle self-illumination so cyclorama stays vibrant and clean like Zack D. Films
    links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
    links.new(grad.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mode_mix.inputs[6])
    links.new(mode_mix.outputs[2], bsdf.inputs["Base Color"])
    _set_bsdf_input(bsdf, ["Emission Strength"], 0.42 if bg_mode == "cyan_studio" else 0.12)
    if "Emission Color" in bsdf.inputs:
        links.new(mode_mix.outputs[2], bsdf.inputs["Emission Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    cyc.data.materials.append(mat)
    return cyc


def set_studio_bg_keyframe(bg_mode: str, frame: int) -> None:
    """Hard-switches the backdrop at `frame` (None = set without keyframing).
    Modes: 'cyan_studio', 'sky_gradient', 'dark_space', 'interior'."""
    _world_set_mode(bg_mode, frame)
    if frame is None:
        frame = bpy.context.scene.frame_current
    factor = 1.0 if bg_mode == "dark_space" else 0.0
    mat = bpy.data.materials.get("ZDF_Cyclorama_Mat")
    if mat and mat.use_nodes:
        mix = mat.node_tree.nodes.get("ZDF_BgModeMix")
        if mix:
            mix.inputs[0].default_value = factor
            mix.inputs[0].keyframe_insert(data_path="default_value", frame=frame)
            if frame > 1:
                # Hold crisp cut on scene boundary
                pass
    world = bpy.context.scene.world
    if world and world.use_nodes:
        w_mix = world.node_tree.nodes.get("ZDF_WorldModeMix")
        if w_mix:
            w_mix.inputs[0].default_value = factor
            w_mix.inputs[0].keyframe_insert(data_path="default_value", frame=frame)


def _build_three_point_lighting(studio_col: bpy.types.Collection) -> list[bpy.types.Object]:
    specs = [
        # Warm-white softbox Key Light
        ("ZDF_KeyLight", (3.6, -3.4, 4.4), (math.radians(52), 0.0, math.radians(42)), 420.0, (1.0, 0.96, 0.90), 2.8),
        # Cool soft Fill Light
        ("ZDF_FillLight", (-4.0, -2.5, 2.8), (math.radians(65), 0.0, math.radians(-55)), 190.0, (0.85, 0.94, 1.0), 3.6),
        # Crisp Rim / Back Light
        ("ZDF_RimLight", (0.2, 2.8, 4.2), (math.radians(-48), 0.0, math.radians(180)), 340.0, (0.95, 0.98, 1.0), 1.8),
    ]
    created = []
    for name, loc, rot, energy, color, size in specs:
        ldata = bpy.data.lights.new(name=name, type="AREA")
        ldata.energy = energy
        ldata.color = color
        ldata.shape = "RECTANGLE"
        ldata.size = size
        ldata.size_y = size * 0.75
        lobj = bpy.data.objects.new(name=name, object_data=ldata)
        lobj.location = loc
        lobj.rotation_euler = rot
        _link_to_collection(lobj, studio_col)
        created.append(lobj)
    return created


# ==============================================================================
# 2. SCENE COLLECTION & VISIBILITY MANAGEMENT
# ==============================================================================

def setup_scene_collection(
    scene_index: int, start_frame: int, end_frame: int
) -> bpy.types.Collection:
    col_name = f"Scene_{scene_index:02d}"
    col = bpy.data.collections.get(col_name)
    if col is None:
        col = bpy.data.collections.new(col_name)
        bpy.context.scene.collection.children.link(col)
    col["start_frame"] = int(start_frame)
    col["end_frame"] = int(end_frame)
    return col


def finalize_scene_visibility(
    col: bpy.types.Collection, start_frame: int, end_frame: int
) -> None:
    """Keyframes hide_viewport & hide_render so objects in this scene only appear during [start_frame, end_frame]."""
    sf = max(1, int(start_frame))
    ef = max(sf, int(end_frame))
    for obj in list(col.all_objects):
        if obj.type == "CAMERA" or obj.get("zdf_always_hidden"):
            continue
        if sf > 1:
            obj.hide_viewport = True
            obj.hide_render = True
            obj.keyframe_insert(data_path="hide_viewport", frame=1)
            obj.keyframe_insert(data_path="hide_render", frame=1)
            obj.keyframe_insert(data_path="hide_viewport", frame=sf - 1)
            obj.keyframe_insert(data_path="hide_render", frame=sf - 1)

        obj.hide_viewport = False
        obj.hide_render = False
        obj.keyframe_insert(data_path="hide_viewport", frame=sf)
        obj.keyframe_insert(data_path="hide_render", frame=sf)
        obj.keyframe_insert(data_path="hide_viewport", frame=ef)
        obj.keyframe_insert(data_path="hide_render", frame=ef)

        obj.hide_viewport = True
        obj.hide_render = True
        obj.keyframe_insert(data_path="hide_viewport", frame=ef + 1)
        obj.keyframe_insert(data_path="hide_render", frame=ef + 1)


# ==============================================================================
# 3. ASSET IMPORTING & NORMALIZATION
# ==============================================================================

def import_and_normalize_asset(
    filepath: Optional[str],
    target_height: float = 1.0,
    location: Sequence[float] = (0.0, 0.0, 0.0),
    rotation: Sequence[float] = (0.0, 0.0, 0.0),
    collection: Optional[bpy.types.Collection] = None,
    name: str = "ImportedAsset",
) -> Optional[bpy.types.Object]:
    """
    Imports `.blend`, `.glb`/`.gltf`, `.fbx`, or `.obj`, normalizes pivot (XY centered, Z min at 0),
    scales uniformly to `target_height`, places at `location` & `rotation`, and links to `collection`.
    Returns the root parent object (or None if missing/invalid).
    """
    if not filepath:
        return None
    p = Path(filepath)
    if not p.is_file():
        return None

    before = set(bpy.data.objects)
    ext = p.suffix.lower()

    try:
        if ext == ".blend":
            with bpy.data.libraries.load(str(p), link=False) as (data_from, data_to):
                data_to.objects = [o for o in data_from.objects if o]
            imported = [o for o in data_to.objects if o is not None]
            for o in imported:
                bpy.context.scene.collection.objects.link(o)
        elif ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=str(p))
            imported = [o for o in bpy.data.objects if o not in before]
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(p))
            imported = [o for o in bpy.data.objects if o not in before]
        elif ext == ".obj":
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=str(p))
            else:
                bpy.ops.import_scene.obj(filepath=str(p))
            imported = [o for o in bpy.data.objects if o not in before]
        else:
            return None
    except Exception as e:
        print(f"[zdf_helpers] Asset import failed for {filepath}: {e}")
        return None

    # Filter out cameras/lights embedded inside external blend/glb files
    valid = [o for o in imported if o.type in ("MESH", "ARMATURE", "CURVE", "EMPTY")]
    for o in imported:
        if o not in valid:
            bpy.data.objects.remove(o, do_unlink=True)

    if not valid:
        return None

    # Compute world-space bounding box of mesh objects
    meshes = [o for o in valid if o.type == "MESH"]
    bpy.context.view_layer.update()

    min_v = Vector((1e9, 1e9, 1e9))
    max_v = Vector((-1e9, -1e9, -1e9))
    for m in (meshes or valid):
        for corner in m.bound_box:
            wc = m.matrix_world @ Vector(corner)
            min_v.x = min(min_v.x, wc.x)
            min_v.y = min(min_v.y, wc.y)
            min_v.z = min(min_v.z, wc.z)
            max_v.x = max(max_v.x, wc.x)
            max_v.y = max(max_v.y, wc.y)
            max_v.z = max(max_v.z, wc.z)

    size = max_v - min_v
    max_dim = max(size.z, size.x, size.y, 1e-4)
    scale_factor = float(target_height) / (size.z if size.z > 1e-3 else max_dim)
    center_xy = Vector(((min_v.x + max_v.x) * 0.5, (min_v.y + max_v.y) * 0.5, min_v.z))

    # Create clean root Empty so armatures/multi-mesh hierarchies stay intact
    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.2
    _link_to_collection(root, collection)

    top_level = [o for o in valid if o.parent is None or o.parent not in valid]
    for o in valid:
        _link_to_collection(o, collection)
        if o.type == "MESH":
            _shade_smooth_safe(o)

    for o in top_level:
        o.location = (o.location - center_xy) * scale_factor
        o.scale = o.scale * scale_factor
        o.parent = root

    root.location = tuple(location)
    root.rotation_euler = tuple(rotation)
    return root


# ==============================================================================
# 4. SEMI-REALISTIC PBR MATERIAL PRESETS
# ==============================================================================

def create_pbr_material(
    preset: str,
    name: Optional[str] = None,
    base_color: Optional[Sequence[float]] = None,
) -> bpy.types.Material:
    mat_name = name or f"ZDF_Mat_{preset}"
    existing = bpy.data.materials.get(mat_name)
    if existing and base_color is None:
        return existing

    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")

    p = preset.lower()

    if p == "skin_sss":
        col = base_color or (0.78, 0.50, 0.39, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Roughness"], 0.42)
        _set_bsdf_input(bsdf, ["Subsurface Weight", "Subsurface"], 0.45)
        _set_bsdf_input(bsdf, ["Subsurface Scale"], 0.04)
        _set_bsdf_input(bsdf, ["Specular IOR Level", "Specular"], 0.35)
    elif p == "bone":
        col = base_color or (0.86, 0.83, 0.74, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Roughness"], 0.34)
        _set_bsdf_input(bsdf, ["Subsurface Weight", "Subsurface"], 0.12)
        # Subtle procedural noise bump
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 42.0
        noise.inputs["Detail"].default_value = 6.0
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.08
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    elif p == "muscle_cutaway":
        col = base_color or (0.42, 0.035, 0.04, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Roughness"], 0.18)
        _set_bsdf_input(bsdf, ["Coat Weight", "Clearcoat"], 0.65)
        _set_bsdf_input(bsdf, ["Subsurface Weight", "Subsurface"], 0.35)
    elif p == "brushed_metal":
        col = base_color or (0.74, 0.77, 0.80, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Metallic"], 0.96)
        _set_bsdf_input(bsdf, ["Roughness"], 0.24)
    elif p == "clear_glass":
        col = base_color or (0.94, 0.98, 1.0, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Roughness"], 0.05)
        _set_bsdf_input(bsdf, ["IOR"], 1.48)
        _set_bsdf_input(bsdf, ["Transmission Weight", "Transmission"], 0.92)
    elif p == "liquid":
        col = base_color or (0.18, 0.65, 0.92, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Roughness"], 0.04)
        _set_bsdf_input(bsdf, ["IOR"], 1.333)
        _set_bsdf_input(bsdf, ["Transmission Weight", "Transmission"], 0.85)
    elif p == "warm_wood":
        col = base_color or (0.38, 0.20, 0.09, 1.0)
        wave = nodes.new("ShaderNodeTexWave")
        wave.wave_type = "BANDS"
        wave.inputs["Scale"].default_value = 3.5
        wave.inputs["Distortion"].default_value = 6.0
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (col[0] * 0.65, col[1] * 0.65, col[2] * 0.65, 1.0)
        ramp.color_ramp.elements[1].color = col
        links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        _set_bsdf_input(bsdf, ["Roughness"], 0.38)
    elif p == "glossy_plastic":
        col = base_color or (0.90, 0.25, 0.18, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Roughness"], 0.16)
        _set_bsdf_input(bsdf, ["Coat Weight", "Clearcoat"], 0.45)
    elif p in ("glowing_energy", "glow_cyan"):
        col = base_color or (0.06, 0.88, 1.0, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Emission Color", "Emission"], col)
        _set_bsdf_input(bsdf, ["Emission Strength"], 6.5)
        _set_bsdf_input(bsdf, ["Roughness"], 0.2)
    elif p == "warning_red":
        col = base_color or (0.95, 0.09, 0.08, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Emission Color", "Emission"], col)
        _set_bsdf_input(bsdf, ["Emission Strength"], 2.4)
        _set_bsdf_input(bsdf, ["Roughness"], 0.25)
    elif p == "fabric_tshirt":
        col = base_color or (0.12, 0.14, 0.18, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Roughness"], 0.88)
        _set_bsdf_input(bsdf, ["Sheen Weight", "Sheen"], 0.5)
    elif p == "dark_rubber":
        col = base_color or (0.04, 0.045, 0.05, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Roughness"], 0.62)
    else:
        col = base_color or (0.65, 0.68, 0.72, 1.0)
        _set_bsdf_input(bsdf, ["Base Color"], col)
        _set_bsdf_input(bsdf, ["Roughness"], 0.35)

    return mat


def assign_material(obj: Optional[bpy.types.Object], mat: bpy.types.Material) -> None:
    if obj is None or mat is None:
        return
    targets = [obj] if obj.type == "MESH" else []
    targets.extend([c for c in obj.children_recursive if c.type == "MESH"])
    for m in targets:
        if len(m.data.materials) == 0:
            m.data.materials.append(mat)
        else:
            m.data.materials[0] = mat


# ==============================================================================
# 5. BUILT-IN PROCEDURAL PROPS (HIGH-QUALITY FALLBACKS)
# ==============================================================================

def create_procedural_prop(
    kind: str,
    name: str = "Prop",
    location: Sequence[float] = (0.0, 0.0, 0.0),
    scale: Sequence[float] = (1.0, 1.0, 1.0),
    material: Optional[bpy.types.Material] = None,
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    k = kind.lower()
    if k == "battery":
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.28, depth=0.10, location=location)
        obj = bpy.context.active_object
        bev = obj.modifiers.new("Bevel", "BEVEL")
        bev.width = 0.015
        bev.segments = 3
        default_mat = create_pbr_material("brushed_metal")
    elif k in ("bottle", "jar"):
        bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=0.22, depth=0.72, location=location)
        obj = bpy.context.active_object
        bev = obj.modifiers.new("Bevel", "BEVEL")
        bev.width = 0.04
        bev.segments = 4
        default_mat = create_pbr_material("clear_glass")
    elif k == "mug":
        bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=0.20, depth=0.38, location=location)
        obj = bpy.context.active_object
        solid = obj.modifiers.new("Solidify", "SOLIDIFY")
        solid.thickness = 0.02
        default_mat = create_pbr_material("glossy_plastic", base_color=(0.92, 0.93, 0.95, 1.0))
    elif k == "pan":
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.55, depth=0.14, location=location)
        obj = bpy.context.active_object
        bev = obj.modifiers.new("Bevel", "BEVEL")
        bev.width = 0.025
        bev.segments = 3
        default_mat = create_pbr_material("brushed_metal", base_color=(0.14, 0.15, 0.17, 1.0))
    elif k == "phone":
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
        obj = bpy.context.active_object
        obj.scale = (0.42, 0.045, 0.86)
        bpy.ops.object.transform_apply(scale=True)
        bev = obj.modifiers.new("Bevel", "BEVEL")
        bev.width = 0.022
        bev.segments = 4
        default_mat = create_pbr_material("dark_rubber")
    elif k == "table":
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
        obj = bpy.context.active_object
        obj.scale = (3.6, 2.2, 0.14)
        bpy.ops.object.transform_apply(scale=True)
        bev = obj.modifiers.new("Bevel", "BEVEL")
        bev.width = 0.02
        bev.segments = 3
        default_mat = create_pbr_material("warm_wood")
    elif k in ("tube", "esophagus", "pipe"):
        bpy.ops.mesh.primitive_cylinder_add(vertices=36, radius=0.24, depth=1.5, location=location)
        obj = bpy.context.active_object
        solid = obj.modifiers.new("Solidify", "SOLIDIFY")
        solid.thickness = 0.055
        sub = obj.modifiers.new("Subsurf", "SUBSURF")
        sub.levels = 2
        default_mat = create_pbr_material("skin_sss", base_color=(0.82, 0.42, 0.40, 1.0))
    elif k in ("chamber", "stomach", "organ", "heart", "brain"):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=36, ring_count=24, radius=0.48, location=location)
        obj = bpy.context.active_object
        obj.scale = (1.15, 0.78, 1.32)
        bpy.ops.object.transform_apply(scale=True)
        default_mat = create_pbr_material("skin_sss", base_color=(0.76, 0.28, 0.28, 1.0))
    elif k == "bone":
        bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.11, depth=1.2, location=location)
        obj = bpy.context.active_object
        sub = obj.modifiers.new("Subsurf", "SUBSURF")
        sub.levels = 2
        default_mat = create_pbr_material("bone")
    elif k == "gear":
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.45, depth=0.12, location=location)
        obj = bpy.context.active_object
        bev = obj.modifiers.new("Bevel", "BEVEL")
        bev.width = 0.015
        default_mat = create_pbr_material("brushed_metal")
    elif k == "human_bust":
        # Stylized semi-realistic human torso + shoulders + head with T-shirt
        root = bpy.data.objects.new(name, None)
        root.location = tuple(location)
        root.scale = tuple(scale)
        _link_to_collection(root, collection)

        skin_mat = material or create_pbr_material("skin_sss")
        shirt_mat = create_pbr_material("fabric_tshirt", base_color=(0.12, 0.16, 0.22, 1.0))

        # Torso (T-shirt)
        bpy.ops.mesh.primitive_cylinder_add(vertices=36, radius=0.38, depth=0.82, location=(0, 0, 0.41))
        torso = bpy.context.active_object
        torso.name = f"{name}_Torso"
        torso.scale = (1.18, 0.68, 1.0)
        bpy.ops.object.transform_apply(scale=True)
        torso.modifiers.new("Bevel", "BEVEL").width = 0.08
        _shade_smooth_safe(torso)
        assign_material(torso, shirt_mat)
        _link_to_collection(torso, collection)
        torso.parent = root

        # Neck
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.12, depth=0.22, location=(0, 0, 0.90))
        neck = bpy.context.active_object
        neck.name = f"{name}_Neck"
        _shade_smooth_safe(neck)
        assign_material(neck, skin_mat)
        _link_to_collection(neck, collection)
        neck.parent = root

        # Head
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=20, radius=0.23, location=(0, 0, 1.18))
        head = bpy.context.active_object
        head.name = f"{name}_Head"
        head.scale = (0.86, 0.95, 1.12)
        bpy.ops.object.transform_apply(scale=True)
        _shade_smooth_safe(head)
        assign_material(head, skin_mat)
        _link_to_collection(head, collection)
        head.parent = root
        return root
    else:
        bpy.ops.mesh.primitive_cube_add(size=0.65, location=location)
        obj = bpy.context.active_object
        bev = obj.modifiers.new("Bevel", "BEVEL")
        bev.width = 0.04
        bev.segments = 3
        default_mat = create_pbr_material("glossy_plastic")

    obj.name = name
    obj.scale = tuple(scale)
    _shade_smooth_safe(obj)
    assign_material(obj, material or default_mat)
    _link_to_collection(obj, collection)
    return obj


# ==============================================================================
# 6. ANIMATED BOOLEAN CUTAWAY
# ==============================================================================

def apply_animated_cutaway(
    target_obj: bpy.types.Object,
    cutter_bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] = (
        (-2.0, 2.0),
        (-2.0, 0.0),
        (-2.0, 2.0),
    ),
    start_frame: int = 1,
    end_frame: int = 30,
    cap_material: str = "muscle_cutaway",
    collection: Optional[bpy.types.Collection] = None,
) -> Optional[bpy.types.Object]:
    """
    Non-destructive Boolean difference cutaway with animated slide-in and clean capped cross-section shading.
    """
    if target_obj is None:
        return None
    meshes = [target_obj] if target_obj.type == "MESH" else [
        c for c in target_obj.children_recursive if c.type == "MESH"
    ]
    if not meshes:
        return None

    (x0, x1), (y0, y1), (z0, z1) = cutter_bounds
    cx, cy, cz = (x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5
    sx, sy, sz = max(0.05, x1 - x0), max(0.05, y1 - y0), max(0.05, z1 - z0)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy - sy * 1.4, cz))
    cutter = bpy.context.active_object
    cutter.name = f"CutawayCutter_{target_obj.name}"
    cutter.scale = (sx, sy, sz)
    cutter.display_type = "WIRE"
    cutter.hide_render = True
    cutter.hide_viewport = True
    cutter["zdf_always_hidden"] = True
    _link_to_collection(cutter, collection)

    cap_mat = create_pbr_material(cap_material)
    assign_material(cutter, cap_mat)

    # Animate cutter sliding smoothly into cutaway position
    cutter.location = (cx, cy - sy * 1.6, cz)
    cutter.keyframe_insert(data_path="location", frame=max(1, int(start_frame)))
    cutter.location = (cx, cy, cz)
    cutter.keyframe_insert(data_path="location", frame=max(int(start_frame) + 2, int(end_frame)))
    _set_bezier_interpolation(cutter)

    for m in meshes:
        if cap_mat.name not in [mat.name for mat in m.data.materials if mat]:
            m.data.materials.append(cap_mat)
        mod = m.modifiers.new(name="ZDF_Cutaway", type="BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.object = cutter
        if hasattr(mod, "solver"):
            mod.solver = "EXACT"

    return cutter


# ==============================================================================
# 7. DIEGETIC CHANNEL BRANDING ("STICK KNOWLEDGE")
# ==============================================================================

def _generate_decal_png(text: str, mode: str, output_path: Path) -> Optional[Path]:
    """Generates a crisp high-res transparent PNG decal using Pillow if available."""
    if output_path.is_file() and output_path.stat().st_size > 1000:
        return output_path
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = 1024, 320
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if mode == "screen_ui":
        draw.rounded_rectangle([18, 18, w - 18, h - 18], radius=36, fill=(14, 24, 42, 245), outline=(56, 189, 248, 255), width=8)
        fg = (255, 255, 255, 255)
        accent = (56, 189, 248, 255)
    elif mode == "prop_wrap":
        draw.rounded_rectangle([12, 28, w - 12, h - 28], radius=24, fill=(245, 246, 248, 245), outline=(24, 28, 36, 255), width=8)
        fg = (18, 22, 30, 255)
        accent = (217, 119, 87, 255)
    else:  # tshirt / default
        fg = (255, 255, 255, 255)
        accent = (158, 226, 255, 255)

    # Pick bold font
    font_candidates = [
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\calibrib.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    font_main = None
    font_sub = None
    for fc in font_candidates:
        if os.path.isfile(fc):
            font_main = ImageFont.truetype(fc, 86)
            font_sub = ImageFont.truetype(fc, 30)
            break
    if font_main is None:
        font_main = ImageFont.load_default()
        font_sub = font_main

    label = text.upper().strip()
    bbox = draw.textbbox((0, 0), label, font=font_main)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (w - tw) // 2
    ty = (h - th) // 2 - 14
    draw.text((tx, ty), label, font=font_main, fill=fg)
    draw.rectangle([w // 2 - 180, ty + th + 24, w // 2 + 180, ty + th + 34], fill=accent)

    img.save(str(output_path), "PNG")
    return output_path


def create_branding_decal(
    text: str = "STICK KNOWLEDGE",
    target_obj: Optional[bpy.types.Object] = None,
    mode: str = "prop_wrap",
    location: Optional[Sequence[float]] = None,
    rotation: Optional[Sequence[float]] = None,
    width: float = 0.55,
    assets_dir: Optional[str] = None,
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    """
    Embeds diegetic 'STICK KNOWLEDGE' branding onto a 3D hero surface:
      - mode='tshirt' | 'prop_wrap' | 'screen_ui': High-res transparent PNG decal plane
        (optionally shrinkwrapped / parented to `target_obj`).
      - mode='engraved': Real 3D extruded metallic/embossed text directly on the prop.
    """
    if mode == "engraved":
        bpy.ops.object.text_add(location=tuple(location or (0.0, -0.35, 0.3)))
        txt = bpy.context.active_object
        txt.name = "STICK_KNOWLEDGE_Engraved"
        txt.data.body = text.upper()
        txt.data.align_x = "CENTER"
        txt.data.align_y = "CENTER"
        txt.data.extrude = 0.015
        txt.data.bevel_depth = 0.004
        txt.data.size = width * 0.16
        txt.rotation_euler = tuple(rotation or (math.pi / 2, 0.0, 0.0))
        mat = create_pbr_material("brushed_metal", name="SK_Engraved_Mat", base_color=(0.92, 0.94, 0.98, 1.0))
        txt.data.materials.append(mat)
        _link_to_collection(txt, collection)
        if target_obj is not None:
            txt.parent = target_obj
        return txt

    # Locate or generate PNG decal texture
    decal_dir = Path(assets_dir) if assets_dir else Path(bpy.app.tempdir)
    png_path = decal_dir / f"stick_knowledge_{mode}.png"
    if not png_path.is_file():
        generic = decal_dir / "stick_knowledge_decal.png"
        if generic.is_file():
            png_path = generic
        else:
            generated = _generate_decal_png(text, mode, png_path)
            if generated is not None:
                png_path = generated

    height = width * (320.0 / 1024.0)
    loc = tuple(location) if location is not None else (0.0, -0.30, 0.50)
    rot = tuple(rotation) if rotation is not None else (math.pi / 2, 0.0, 0.0)

    if png_path.is_file():
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=loc, rotation=rot)
        plane = bpy.context.active_object
        plane.name = f"STICK_KNOWLEDGE_Decal_{mode}"
        plane.scale = (width, height, 1.0)
        bpy.ops.object.transform_apply(scale=True)

        mat = bpy.data.materials.new(f"SK_Decal_Mat_{mode}")
        mat.use_nodes = True
        nt = mat.node_tree
        nodes = nt.nodes
        links = nt.links
        bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
        tex = nodes.new("ShaderNodeTexImage")
        img = bpy.data.images.load(str(png_path), check_existing=True)
        tex.image = img
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if "Alpha" in bsdf.inputs:
            links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        if mode == "screen_ui":
            if "Emission Color" in bsdf.inputs:
                links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
            _set_bsdf_input(bsdf, ["Emission Strength"], 2.2)
        else:
            _set_bsdf_input(bsdf, ["Roughness"], 0.45)

        if hasattr(mat, "blend_method"):
            try:
                mat.blend_method = "BLEND"
            except Exception:
                pass
        plane.data.materials.append(mat)
        _link_to_collection(plane, collection)

        if target_obj is not None:
            plane.parent = target_obj
            if target_obj.type == "MESH" and mode in ("tshirt", "prop_wrap"):
                sub = plane.modifiers.new("Subdivide", "SUBSURF")
                sub.subdivision_type = "SIMPLE"
                sub.levels = 3
                sub.render_levels = 3
                sw = plane.modifiers.new("Shrinkwrap", "SHRINKWRAP")
                sw.target = target_obj
                sw.offset = 0.004
        return plane

    # Fallback: crisp 3D embossed text if PNG wasn't available
    return create_branding_decal(
        text=text,
        target_obj=target_obj,
        mode="engraved",
        location=loc,
        rotation=rot,
        width=width,
        collection=collection,
    )


# ==============================================================================
# 8. IN-WORLD 3D MOTION-GRAPHIC OVERLAYS
# ==============================================================================

def _pop_in_scale(obj: bpy.types.Object, start_frame: int, pop_frames: int = 8, target_scale=(1.0, 1.0, 1.0)) -> None:
    sf = max(1, int(start_frame))
    obj.scale = (0.001, 0.001, 0.001)
    obj.keyframe_insert(data_path="scale", frame=sf)
    obj.scale = tuple(s * 1.12 for s in target_scale)
    obj.keyframe_insert(data_path="scale", frame=sf + max(2, int(pop_frames * 0.7)))
    obj.scale = tuple(target_scale)
    obj.keyframe_insert(data_path="scale", frame=sf + max(3, pop_frames))
    _set_bezier_interpolation(obj)


def add_3d_arrow(
    start: Sequence[float] = (0.0, 0.0, 0.0),
    end: Sequence[float] = (0.0, 0.0, 0.8),
    color: Sequence[float] = (0.95, 0.12, 0.10, 1.0),
    radius: float = 0.042,
    start_frame: int = 1,
    pop_frames: int = 10,
    collection: Optional[bpy.types.Collection] = None,
    name: str = "ZDF_Arrow",
) -> bpy.types.Object:
    v_start = Vector(start)
    v_end = Vector(end)
    vec = v_end - v_start
    length = max(0.08, vec.length)
    shaft_len = length * 0.68
    head_len = length * 0.32

    root = bpy.data.objects.new(name, None)
    root.location = v_start
    rot_quat = Vector((0, 0, 1)).rotation_difference(vec.normalized())
    root.rotation_euler = rot_quat.to_euler()
    _link_to_collection(root, collection)

    mat = create_pbr_material("warning_red", name=f"Mat_{name}", base_color=color)

    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=radius, depth=shaft_len, location=(0, 0, shaft_len * 0.5))
    shaft = bpy.context.active_object
    shaft.name = f"{name}_Shaft"
    _shade_smooth_safe(shaft)
    assign_material(shaft, mat)
    _link_to_collection(shaft, collection)
    shaft.parent = root

    bpy.ops.mesh.primitive_cone_add(
        vertices=24, radius1=radius * 2.25, radius2=0.0, depth=head_len, location=(0, 0, shaft_len + head_len * 0.5)
    )
    head = bpy.context.active_object
    head.name = f"{name}_Head"
    _shade_smooth_safe(head)
    assign_material(head, mat)
    _link_to_collection(head, collection)
    head.parent = root

    _pop_in_scale(root, start_frame, pop_frames)
    return root


def add_3d_chevron_flow(
    points: Sequence[Sequence[float]] = ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    count: int = 4,
    color: Sequence[float] = (0.05, 0.92, 1.0, 1.0),
    start_frame: int = 1,
    end_frame: int = 90,
    scale: float = 0.14,
    collection: Optional[bpy.types.Collection] = None,
) -> list[bpy.types.Object]:
    """Glowing cyan '>>' animated directional flow chevrons marching along `points`."""
    pts = [Vector(p) for p in points]
    if len(pts) < 2:
        pts = [Vector((0, 0, 0)), Vector((0, 0, 1))]

    mat = create_pbr_material("glow_cyan", name="ZDF_Chevron_Mat", base_color=color)
    chevrons: list[bpy.types.Object] = []
    span = max(12, int(end_frame) - int(start_frame))

    for i in range(max(1, count)):
        bpy.ops.object.text_add(location=pts[0])
        ch = bpy.context.active_object
        ch.name = f"ZDF_Chevron_{i+1}"
        ch.data.body = "»"
        ch.data.align_x = "CENTER"
        ch.data.align_y = "CENTER"
        ch.data.extrude = 0.06
        ch.data.size = scale * 2.4
        ch.rotation_euler = (math.pi / 2, 0.0, 0.0)
        ch.data.materials.append(mat)
        _link_to_collection(ch, collection)

        phase = i / max(1, count)
        steps = 8
        for s in range(steps + 1):
            t_norm = (s / steps + phase) % 1.0
            pos = _sample_polyline(pts, t_norm)
            frame = int(start_frame) + int((s / steps) * span)
            ch.location = pos
            ch.keyframe_insert(data_path="location", frame=frame)
        _set_bezier_interpolation(ch, "LINEAR")
        chevrons.append(ch)
    return chevrons


def _sample_polyline(pts: list[Vector], t: float) -> Vector:
    if len(pts) == 2:
        return pts[0].lerp(pts[1], t)
    seg_f = t * (len(pts) - 1)
    idx = min(len(pts) - 2, int(seg_f))
    local_t = seg_f - idx
    return pts[idx].lerp(pts[idx + 1], local_t)


def add_3d_x_mark(
    location: Sequence[float] = (0.0, 0.0, 0.0),
    scale: float = 0.35,
    color: Sequence[float] = (0.95, 0.10, 0.08, 1.0),
    start_frame: int = 1,
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    root = bpy.data.objects.new("ZDF_X_Mark", None)
    root.location = tuple(location)
    _link_to_collection(root, collection)
    mat = create_pbr_material("warning_red", name="ZDF_XMark_Mat", base_color=color)

    for idx, angle in enumerate((math.pi / 4, -math.pi / 4)):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
        bar = bpy.context.active_object
        bar.name = f"ZDF_XBar_{idx}"
        bar.scale = (scale * 1.15, scale * 0.16, scale * 0.24)
        bpy.ops.object.transform_apply(scale=True)
        bar.rotation_euler = (0.0, angle, 0.0)
        bar.modifiers.new("Bevel", "BEVEL").width = 0.018
        _shade_smooth_safe(bar)
        assign_material(bar, mat)
        _link_to_collection(bar, collection)
        bar.parent = root

    _pop_in_scale(root, start_frame, pop_frames=8)
    return root


def add_3d_airflow_streaks(
    points: Sequence[Sequence[float]] = ((0.0, 0.0, 0.0), (0.2, 0.0, 0.5), (0.0, 0.0, 1.1)),
    count: int = 3,
    start_frame: int = 1,
    end_frame: int = 90,
    collection: Optional[bpy.types.Collection] = None,
) -> list[bpy.types.Object]:
    """Wispy white curved airflow/fluid trails with animated bevel reveal."""
    mat = create_pbr_material("glowing_energy", name="ZDF_Airflow_Mat", base_color=(0.95, 0.98, 1.0, 1.0))
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        _set_bsdf_input(bsdf, ["Emission Strength"], 2.2)

    streaks = []
    for i in range(max(1, count)):
        offset = Vector(((i - (count - 1) * 0.5) * 0.12, (i % 2) * 0.06, 0.0))
        cdata = bpy.data.curves.new(f"ZDF_Airflow_{i}", type="CURVE")
        cdata.dimensions = "3D"
        cdata.bevel_depth = 0.014
        cdata.bevel_resolution = 4
        spline = cdata.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for pi, pt in enumerate(points):
            v = Vector(pt) + offset
            spline.points[pi].co = (v.x, v.y, v.z, 1.0)

        cobj = bpy.data.objects.new(f"ZDF_Airflow_{i}", cdata)
        cobj.data.materials.append(mat)
        _link_to_collection(cobj, collection)

        sf = max(1, int(start_frame) + i * 4)
        ef = max(sf + 10, int(end_frame))
        cdata.bevel_factor_end = 0.0
        cdata.keyframe_insert(data_path="bevel_factor_end", frame=sf)
        cdata.bevel_factor_end = 1.0
        cdata.keyframe_insert(data_path="bevel_factor_end", frame=min(ef, sf + 24))
        streaks.append(cobj)
    return streaks


def add_3d_energy_arc(
    start: Sequence[float] = (0.0, 0.0, 0.0),
    end: Sequence[float] = (0.5, 0.0, 0.5),
    color: Sequence[float] = (0.15, 0.85, 1.0, 1.0),
    start_frame: int = 1,
    end_frame: int = 90,
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    v0, v1 = Vector(start), Vector(end)
    cdata = bpy.data.curves.new("ZDF_EnergyArc", type="CURVE")
    cdata.dimensions = "3D"
    cdata.bevel_depth = 0.016
    spline = cdata.splines.new("POLY")
    segs = 8
    spline.points.add(segs)
    rng = random.Random(42)
    for i in range(segs + 1):
        t = i / segs
        p = v0.lerp(v1, t)
        if 0 < i < segs:
            p += Vector((rng.uniform(-0.07, 0.07), rng.uniform(-0.05, 0.05), rng.uniform(-0.07, 0.07)))
        spline.points[i].co = (p.x, p.y, p.z, 1.0)

    obj = bpy.data.objects.new("ZDF_EnergyArc", cdata)
    mat = create_pbr_material("glow_cyan", name="ZDF_EnergyArc_Mat", base_color=color)
    obj.data.materials.append(mat)
    _link_to_collection(obj, collection)
    _pop_in_scale(obj, start_frame, pop_frames=6)
    return obj


def add_3d_sparks(
    origin: Sequence[float] = (0.0, 0.0, 0.0),
    count: int = 12,
    start_frame: int = 1,
    end_frame: int = 60,
    collection: Optional[bpy.types.Collection] = None,
) -> list[bpy.types.Object]:
    orig = Vector(origin)
    mat = create_pbr_material("glowing_energy", name="ZDF_Spark_Mat", base_color=(1.0, 0.45, 0.05, 1.0))
    rng = random.Random(99)
    sparks = []
    span = max(12, int(end_frame) - int(start_frame))
    for i in range(max(1, count)):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.022, location=orig)
        sp = bpy.context.active_object
        sp.name = f"ZDF_Spark_{i}"
        assign_material(sp, mat)
        _link_to_collection(sp, collection)
        vel = Vector((rng.uniform(-0.6, 0.6), rng.uniform(-0.4, 0.4), rng.uniform(0.15, 0.85)))
        sf = int(start_frame) + rng.randint(0, max(1, span // 3))
        ef = min(int(end_frame), sf + rng.randint(12, 26))
        sp.location = orig
        sp.scale = (0.01, 0.01, 0.01)
        sp.keyframe_insert(data_path="location", frame=sf)
        sp.keyframe_insert(data_path="scale", frame=sf)
        sp.scale = (1.0, 1.0, 1.0)
        sp.keyframe_insert(data_path="scale", frame=sf + 3)
        sp.location = orig + vel
        sp.scale = (0.01, 0.01, 0.01)
        sp.keyframe_insert(data_path="location", frame=ef)
        sp.keyframe_insert(data_path="scale", frame=ef)
        sparks.append(sp)
    return sparks


def add_3d_label_sign(
    text: str = "WATER",
    location: Sequence[float] = (0.0, 0.0, 1.0),
    scale: float = 0.035,
    start_frame: int = 1,
    collection: Optional[bpy.types.Collection] = None,
    pin_length: float = 0.0,
    facing_rotation: Sequence[float] = (0.0, 0.0, 0.0),
    dark: bool = False,
) -> bpy.types.Object:
    """
    Label sign in the reference style: off-white board, dark letters, optional thin metal
    pin below it (the 'WATER' / 'ETHANOL' signs stuck into bowls).
    `scale` = letter height in METRES (0.035 suits a 0.22 m bowl; 0.12 suits a person).
    Board width ≈ scale × (0.68 × letters + 1.2). The board faces −Y (towards a default
    front camera); turn it with facing_rotation. `dark=True` gives white text on dark.
    Pops in at start_frame (so capture a frame a few frames AFTER it).
    """
    label = text.upper()
    root = bpy.data.objects.new(f"ZDF_Label_{label[:12]}", None)
    root.location = tuple(location)
    root.rotation_euler = tuple(facing_rotation)
    _link_to_collection(root, collection)

    s = float(scale)
    w, h, d = s * (0.68 * len(label) + 1.2), s * 1.9, s * 0.12
    board = make_rounded_box(size=(w, d, h), location=(0, 0, 0), bevel=min(d * 0.45, s * 0.12), segments=3,
                             name=f"ZDF_LabelBoard_{label[:12]}", collection=collection)
    bg = hex_to_linear("#1B1F27") if dark else hex_to_linear("#F1F0EC")
    fg = hex_to_linear("#FFFFFF") if dark else hex_to_linear("#1C1C1E")
    assign_material(board, create_pbr_material("glossy_plastic", name=f"ZDF_LabelBoard_{'dark' if dark else 'light'}", base_color=bg))
    board.parent = root

    cu = bpy.data.curves.new(f"ZDF_LabelTxt_{label[:12]}", "FONT")
    cu.body = label
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.size = s * 1.25
    cu.extrude = s * 0.02
    for fp in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf"):
        if os.path.isfile(fp):
            try:
                cu.font = bpy.data.fonts.load(fp, check_existing=True)
            except Exception:
                pass
            break
    txt = bpy.data.objects.new(cu.name, cu)
    txt.location = (0, -d / 2 - s * 0.03, 0)
    txt.rotation_euler = (math.pi / 2, 0.0, 0.0)
    cu.materials.append(create_pbr_material("toon_flat", name=f"ZDF_LabelInk_{'dark' if dark else 'light'}", base_color=fg))
    _link_to_collection(txt, collection)
    txt.parent = root

    if pin_length > 0:
        pin = make_lathe([(0, 0), (s * 0.06, 0), (s * 0.06, pin_length), (0, pin_length)], segments=16, subsurf=0,
                         name=f"ZDF_LabelPin_{label[:12]}", location=(0, 0, -h / 2 - pin_length),
                         material=create_pbr_material("steel_polished"), collection=collection)
        pin.parent = root

    _pop_in_scale(root, start_frame, pop_frames=8)
    return root


# ==============================================================================
# 9. ANIMATION & CINEMATIC CAMERA
# ==============================================================================

def animate_transform(
    obj: bpy.types.Object,
    keyframes: Sequence[tuple[int, Optional[Sequence[float]], Optional[Sequence[float]], Optional[Sequence[float]]]],
    interpolation: str = "BEZIER",
) -> None:
    for frame, loc, rot, scl in keyframes:
        f = max(1, int(frame))
        if loc is not None:
            obj.location = tuple(loc)
            obj.keyframe_insert(data_path="location", frame=f)
        if rot is not None:
            obj.rotation_euler = tuple(rot)
            obj.keyframe_insert(data_path="rotation_euler", frame=f)
        if scl is not None:
            obj.scale = tuple(scl)
            obj.keyframe_insert(data_path="scale", frame=f)
    _set_bezier_interpolation(obj, interpolation)


def setup_cinematic_camera(
    keyframes: Sequence[tuple[int, Sequence[float]]],
    target_obj: Optional[bpy.types.Object] = None,
    target_location: Sequence[float] = (0.0, 0.0, 0.5),
    lens: float = 50.0,
    dof_fstop: float = 2.8,
    collection: Optional[bpy.types.Collection] = None,
    name: str = "SceneCam",
) -> bpy.types.Object:
    """
    Creates a cinematic 9:16 camera with smooth Bezier-eased dolly/orbit keyframes,
    Track-To target constraint, and subtle macro Depth of Field (DoF).
    """
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = float(lens)
    cam_data.sensor_width = 36.0
    cam_data.clip_start = 0.05
    cam_data.clip_end = 250.0

    cam = bpy.data.objects.new(name, cam_data)
    _link_to_collection(cam, collection)

    # Focus / LookAt target
    focus_target = target_obj
    if focus_target is None:
        focus_target = bpy.data.objects.new(f"{name}_Target", None)
        focus_target.location = tuple(target_location)
        _link_to_collection(focus_target, collection)

    track = cam.constraints.new(type="TRACK_TO")
    track.target = focus_target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    # Subtle Depth of Field focused on hero subject
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = focus_target
    cam_data.dof.aperture_fstop = float(dof_fstop)

    for frame, loc in keyframes:
        cam.location = tuple(loc)
        cam.keyframe_insert(data_path="location", frame=max(1, int(frame)))
    _set_bezier_interpolation(cam, "BEZIER")

    return cam


def bind_camera_marker(scene: bpy.types.Scene, camera_obj: bpy.types.Object, frame: int, name: str) -> None:
    """Binds a camera to a timeline marker so multi-scene cuts happen seamlessly inside a single .blend!"""
    marker = scene.timeline_markers.new(name=name, frame=max(1, int(frame)))
    marker.camera = camera_obj


# ==============================================================================
# 10. PACK, SAVE & RENDER HELPERS
# ==============================================================================

def pack_and_save_project(filepath: str) -> str:
    p = Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        bpy.ops.file.pack_all()
    except Exception as e:
        print(f"[zdf_helpers] pack_all warning: {e}")
    bpy.ops.wm.save_as_mainfile(filepath=str(p))
    return str(p)


def render_scene_preview(
    frame: int,
    output_path: str,
    camera_obj: Optional[bpy.types.Object] = None,
    preview_scale_pct: int = 50,
) -> str:
    scene = bpy.context.scene
    prev_pct = scene.render.resolution_percentage
    prev_cam = scene.camera
    prev_engine = scene.render.engine

    try:
        # Fast EEVEE preview for instant UI feedback
        scene.render.engine = _resolve_eevee_engine()
        scene.render.resolution_percentage = preview_scale_pct
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 16
        if camera_obj is not None:
            scene.camera = camera_obj
        scene.frame_set(max(1, int(frame)))
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(out)
        scene.render.image_settings.file_format = "PNG"
        bpy.ops.render.render(write_still=True)
        return str(out)
    finally:
        scene.render.engine = prev_engine
        scene.render.resolution_percentage = prev_pct
        scene.camera = prev_cam


def render_animation(
    start_frame: int,
    end_frame: int,
    output_dir: str,
    render_engine: Optional[str] = None,
    cycles_samples: Optional[int] = None,
) -> str:
    scene = bpy.context.scene
    if render_engine:
        if render_engine in ("CYCLES_OPTIX", "CYCLES"):
            try:
                bpy.ops.preferences.addon_enable(module="cycles")
            except Exception:
                pass
            if "CYCLES" in _available_render_engines():
                scene.render.engine = "CYCLES"
                if cycles_samples:
                    scene.cycles.samples = int(cycles_samples)
        else:
            scene.render.engine = _resolve_eevee_engine()

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scene.frame_start = max(1, int(start_frame))
    scene.frame_end = max(scene.frame_start, int(end_frame))
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(out_dir / "frame_")
    bpy.ops.render.render(animation=True)
    return str(out_dir)


# ==============================================================================
# 11. PRO TOOLKIT — calibrated ZDF backdrops, real modeling, layered cutaways,
#     outlined explainer arrows, diegetic branding, Mixamo characters + NLA,
#     shot-preset cameras. (Phase 2 upgrade; see skills/02_* and 03_*.)
# ==============================================================================

import bmesh  # noqa: E402  (bpy-only module)

_CONFIG: dict[str, Optional[str]] = {"project_dir": None, "assets_dir": None}


def configure(project_dir: Optional[str] = None, assets_dir: Optional[str] = None) -> None:
    """Tell the helpers where the project lives (master_build / the live bridge call this)."""
    if project_dir:
        _CONFIG["project_dir"] = str(project_dir)
    if assets_dir:
        _CONFIG["assets_dir"] = str(assets_dir)


def _assets_dir(explicit: Optional[str] = None) -> Optional[Path]:
    for cand in (explicit, _CONFIG.get("assets_dir")):
        if cand and Path(cand).is_dir():
            return Path(cand)
    if bpy.data.filepath:
        p = Path(bpy.data.filepath).parent / "assets"
        if p.is_dir():
            return p
    return None


def hex_to_linear(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """'#31B9E6' (display sRGB hex) -> linear RGBA for Blender colour sockets."""
    h = hex_color.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2], alpha)


def sec_to_frame(seconds: float, fps: int = 30) -> int:
    """Timeline frame for a narration time (frame 1 == 0.0 s)."""
    return int(round(float(seconds) * fps)) + 1


# ------------------------------------------------------------------------------
# 11.1 Screen-locked ZDF backdrops (measured from the reference Shorts)
# ------------------------------------------------------------------------------
# The blue background in the references is locked to the FRAME, not the set: the
# same glow sits behind every angle (macro, top-down, low). So it is drawn for
# camera rays only, in Window space, while lighting rays see a soft ambient colour.
# BACKDROP_LINEAR holds shader values already compensated for AgX so that rendered
# pixels land on the measured sRGB targets (tools/calibrate_backdrop.py).

BACKDROP_TARGETS = {
    "cyan_studio": {"inner": "#9BDAF0", "outer": "#31B9E6"},   # finger-gun short
    "sky_gradient": {"top": "#52ABFB", "bottom": "#ACD6FE"},   # milk-knife tabletop short
    "dark_space": {"inner": "#0F1B2D", "outer": "#03060B"},    # cosmic / microscopic
    "interior": {"flat": "#B9B5AD"},                           # real rooms fill the frame
}

# Calibrated 2026-11-25 under "Khronos PBR Neutral" in Blender 5.3 (EEVEE):
# rendered cyan inner #9AD8EE / outer #31B8E5, sky top #55A8F5 / bottom #A8D0F6.
BACKDROP_LINEAR = {
    "cyan_studio": {"inner": (0.38699, 0.79062, 0.97704), "outer": (0.06462, 0.52188, 0.83146)},
    "sky_gradient": {"top": (0.10159, 0.49971, 1.19809), "bottom": (0.5445, 0.88012, 1.29848)},
    "dark_space": {"inner": (0.02778, 0.03356, 0.04806), "outer": (0.0046, 0.00515, 0.00617)},
    "interior": {"flat": (0.51569, 0.49179, 0.44894)},
}

import os as _os  # noqa: E402

# View transform for every ZDF render. Measured with tools/calibrate_backdrop.py:
#   AgX (any look) cannot reach the reference cyan — it desaturates it to ~#7AB8E1.
#   Standard matches exactly but clips highlights on lit props.
#   Khronos PBR Neutral matches within a few levels AND rolls highlights off softly.
# Override with env ZDF_VIEW / ZDF_LOOK (re-run the calibration if you do).
VIEW_TRANSFORM = _os.environ.get("ZDF_VIEW", "Khronos PBR Neutral")
VIEW_LOOK = _os.environ.get("ZDF_LOOK", "None")

BG_MODES = ("cyan_studio", "sky_gradient", "dark_space", "interior")
_AMBIENT = {
    "cyan_studio": ((0.30, 0.55, 0.78), 0.65),
    "sky_gradient": ((0.42, 0.58, 0.80), 0.70),
    "dark_space": ((0.02, 0.03, 0.06), 0.30),
    "interior": ((0.80, 0.72, 0.62), 0.55),
}


def _n(nodes, type_name: str, loc=(0, 0), name: Optional[str] = None):
    node = nodes.new(type_name)
    node.location = loc
    if name:
        node.name = name
        node.label = name
    return node


def _math(nodes, links, op: str, a, b=None, loc=(0, 0), clamp=False):
    m = _n(nodes, "ShaderNodeMath", loc)
    m.operation = op
    m.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = float(v)
        else:
            links.new(v, m.inputs[i])
    return m.outputs[0]


def _ramp(nodes, links, fac, c0, c1, loc=(0, 0), interp="EASE"):
    r = _n(nodes, "ShaderNodeValToRGB", loc)
    r.color_ramp.interpolation = interp
    r.color_ramp.elements[0].position = 0.0
    r.color_ramp.elements[0].color = (*tuple(c0)[:3], 1.0)
    r.color_ramp.elements[1].position = 1.0
    r.color_ramp.elements[1].color = (*tuple(c1)[:3], 1.0)
    links.new(fac, r.inputs["Fac"])
    return r.outputs["Color"]


def _mix_rgb(nodes, links, fac_value_name: str, a, b, loc=(0, 0)):
    """Mix(a, b) whose factor is a named Value node (keyframed per scene)."""
    val = _n(nodes, "ShaderNodeValue", (loc[0] - 200, loc[1] - 120), fac_value_name)
    val.outputs[0].default_value = 0.0
    mix = _n(nodes, "ShaderNodeMix", loc)
    mix.data_type = "RGBA"
    links.new(val.outputs[0], mix.inputs[0])
    links.new(a, mix.inputs[6])
    links.new(b, mix.inputs[7])
    return mix.outputs[2]


def setup_zdf_backdrop(bg_mode: str = "cyan_studio", glow_center=(0.5, 0.46), glow_radius: float = 0.62,
                       horizon: float = 0.40) -> bpy.types.World:
    """
    Builds the ZDF world: a frame-locked backdrop for camera rays (radial cyan glow,
    vertical sky gradient, dark space or neutral interior) plus soft ambient light for
    everything else. Switch per scene with set_studio_bg_keyframe(mode, frame).
    """
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new("ZDF_World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()

    aspect = scene.render.resolution_x / max(1, scene.render.resolution_y)
    tc = _n(nodes, "ShaderNodeTexCoord", (-1400, 0))
    sep = _n(nodes, "ShaderNodeSeparateXYZ", (-1200, 0))
    links.new(tc.outputs["Window"], sep.inputs[0])

    dx = _math(nodes, links, "MULTIPLY", _math(nodes, links, "SUBTRACT", sep.outputs[0], glow_center[0], (-1000, 120)), aspect, (-850, 120))
    dy = _math(nodes, links, "SUBTRACT", sep.outputs[1], glow_center[1], (-1000, -40))
    d2 = _math(nodes, links, "ADD", _math(nodes, links, "POWER", dx, 2.0, (-700, 120)),
               _math(nodes, links, "POWER", dy, 2.0, (-700, -40)), (-550, 60))
    radial = _math(nodes, links, "DIVIDE", _math(nodes, links, "SQRT", d2, None, (-400, 60)), glow_radius, (-250, 60), clamp=True)

    L = BACKDROP_LINEAR
    cyan = _ramp(nodes, links, radial, L["cyan_studio"]["inner"], L["cyan_studio"]["outer"], (0, 300))
    sky_fac = _n(nodes, "ShaderNodeMapRange", (-250, -200))
    sky_fac.inputs["From Min"].default_value = float(horizon)
    sky_fac.inputs["From Max"].default_value = 1.0
    sky_fac.clamp = True
    links.new(sep.outputs[1], sky_fac.inputs["Value"])
    sky = _ramp(nodes, links, sky_fac.outputs[0], L["sky_gradient"]["bottom"], L["sky_gradient"]["top"], (0, 80), "LINEAR")
    dark = _ramp(nodes, links, radial, L["dark_space"]["inner"], L["dark_space"]["outer"], (0, -140))
    flat = _n(nodes, "ShaderNodeRGB", (0, -360))
    flat.outputs[0].default_value = (*L["interior"]["flat"], 1.0)

    m1 = _mix_rgb(nodes, links, "ZDF_BG_sky_gradient", cyan, sky, (350, 200))
    m2 = _mix_rgb(nodes, links, "ZDF_BG_dark_space", m1, dark, (600, 120))
    cam_col = _mix_rgb(nodes, links, "ZDF_BG_interior", m2, flat.outputs[0], (850, 40))

    def amb_rgb(mode, loc):
        n = _n(nodes, "ShaderNodeRGB", loc)
        n.outputs[0].default_value = (*_AMBIENT[mode][0], 1.0)
        return n.outputs[0]

    a1 = _mix_rgb(nodes, links, "ZDF_AMB_sky_gradient", amb_rgb("cyan_studio", (0, -600)), amb_rgb("sky_gradient", (0, -760)), (350, -650))
    a2 = _mix_rgb(nodes, links, "ZDF_AMB_dark_space", a1, amb_rgb("dark_space", (0, -920)), (600, -700))
    amb = _mix_rgb(nodes, links, "ZDF_AMB_interior", a2, amb_rgb("interior", (0, -1080)), (850, -760))

    bg_cam = _n(nodes, "ShaderNodeBackground", (1100, 60))
    bg_cam.inputs["Strength"].default_value = 1.0
    links.new(cam_col, bg_cam.inputs["Color"])
    bg_amb = _n(nodes, "ShaderNodeBackground", (1100, -200), "ZDF_AmbientBG")
    bg_amb.inputs["Strength"].default_value = 0.65
    links.new(amb, bg_amb.inputs["Color"])
    lp = _n(nodes, "ShaderNodeLightPath", (1100, 300))
    mix = _n(nodes, "ShaderNodeMixShader", (1350, 0))
    links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    links.new(bg_amb.outputs[0], mix.inputs[1])
    links.new(bg_cam.outputs[0], mix.inputs[2])
    out = _n(nodes, "ShaderNodeOutputWorld", (1550, 0))
    links.new(mix.outputs[0], out.inputs["Surface"])

    _world_set_mode(bg_mode, None)
    return world


def _world_set_mode(bg_mode: str, frame: Optional[int]) -> bool:
    world = bpy.context.scene.world
    if not (world and world.use_nodes and world.node_tree.nodes.get("ZDF_BG_sky_gradient")):
        return False
    nodes = world.node_tree.nodes
    mode = bg_mode if bg_mode in BG_MODES else "cyan_studio"
    for prefix in ("ZDF_BG_", "ZDF_AMB_"):
        for m in BG_MODES[1:]:
            node = nodes.get(prefix + m)
            if node is None:
                continue
            node.outputs[0].default_value = 1.0 if m == mode else 0.0
            if frame is not None:
                node.outputs[0].keyframe_insert("default_value", frame=int(frame))
    amb = nodes.get("ZDF_AmbientBG")
    if amb is not None:
        amb.inputs["Strength"].default_value = _AMBIENT[mode][1]
        if frame is not None:
            amb.inputs["Strength"].keyframe_insert("default_value", frame=int(frame))
    if frame is not None and world.node_tree.animation_data:
        ad = world.node_tree.animation_data
        for fc in _action_fcurves(ad.action, getattr(ad, "action_slot", None)):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"  # hard cut on scene boundaries
    return True


def add_studio_tabletop(
    size: Sequence[float] = (3.2, 1.6, 0.06),
    location: Sequence[float] = (0.0, 0.0, -0.03),
    wood: str = "walnut",
    collection: Optional[bpy.types.Collection] = None,
    name: str = "ZDF_Tabletop",
) -> bpy.types.Object:
    """Warm walnut tabletop with a rounded front edge (the reference kitchen-table look).
    Its top surface sits at z = location.z + size.z / 2."""
    top = make_rounded_box(size=size, location=location, bevel=0.012, segments=4, name=name, collection=collection)
    assign_material(top, create_pbr_material("walnut_wood" if wood == "walnut" else "warm_wood"))
    return top


# ------------------------------------------------------------------------------
# 11.2 Pro materials (registered into create_pbr_material)
# ------------------------------------------------------------------------------

def _new_mat(name: str):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None) or nt.nodes.new("ShaderNodeBsdfPrincipled")
    return mat, nt.nodes, nt.links, bsdf


def _bump(nodes, links, bsdf, height_socket, strength=0.1, distance=0.02):
    b = nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    if "Distance" in b.inputs:
        b.inputs["Distance"].default_value = distance
    links.new(height_socket, b.inputs["Height"])
    links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return b


def _tex(nodes, kind: str, **inputs):
    t = nodes.new(kind)
    for k, v in inputs.items():
        if k in t.inputs:
            t.inputs[k].default_value = v
    return t


def _scaled(c: Sequence[float], k: float) -> tuple:
    return tuple(min(1.0, x * k) for x in tuple(c)[:3])


def _pro_material(p: str, name: str, base_color: Optional[Sequence[float]]) -> bpy.types.Material:
    mat, nodes, links, bsdf = _new_mat(name)
    col = tuple(base_color) if base_color else None
    out = next(n for n in nodes if n.type == "OUTPUT_MATERIAL")

    if p == "skin_realistic":
        c = col or hex_to_linear("#D9A189")
        noise = _tex(nodes, "ShaderNodeTexNoise", Scale=18.0, Detail=8.0)
        links.new(_ramp(nodes, links, noise.outputs["Fac"], _scaled(c, 0.86), c), bsdf.inputs["Base Color"])
        _set_bsdf_input(bsdf, ["Subsurface Weight", "Subsurface"], 0.28)
        _set_bsdf_input(bsdf, ["Subsurface Radius"], (1.0, 0.35, 0.18))
        _set_bsdf_input(bsdf, ["Subsurface Scale"], 0.015)
        _set_bsdf_input(bsdf, ["Roughness"], 0.46)
        _set_bsdf_input(bsdf, ["Specular IOR Level", "Specular"], 0.42)
        pores = _tex(nodes, "ShaderNodeTexVoronoi", Scale=900.0)
        _bump(nodes, links, bsdf, pores.outputs["Distance"], 0.06, 0.002)
    elif p == "muscle_striated":
        c = col or hex_to_linear("#8E1A22")
        wave = _tex(nodes, "ShaderNodeTexWave", Scale=28.0, Distortion=3.0, Detail=4.0)
        wave.wave_type = "BANDS"
        links.new(_ramp(nodes, links, wave.outputs["Fac"], _scaled(c, 0.55), c), bsdf.inputs["Base Color"])
        _set_bsdf_input(bsdf, ["Roughness"], 0.28)
        _set_bsdf_input(bsdf, ["Coat Weight", "Clearcoat"], 0.55)
        _set_bsdf_input(bsdf, ["Subsurface Weight", "Subsurface"], 0.25)
        _set_bsdf_input(bsdf, ["Subsurface Radius"], (1.0, 0.2, 0.15))
        _bump(nodes, links, bsdf, wave.outputs["Fac"], 0.25, 0.01)
    elif p == "tissue_spongy":
        c = col or hex_to_linear("#9C1C26")
        vor = _tex(nodes, "ShaderNodeTexVoronoi", Scale=22.0)
        if hasattr(vor, "feature"):
            vor.feature = "DISTANCE_TO_EDGE"
        links.new(_ramp(nodes, links, vor.outputs["Distance"], _scaled(c, 0.35), c, interp="LINEAR"), bsdf.inputs["Base Color"])
        _set_bsdf_input(bsdf, ["Roughness"], 0.22)
        _set_bsdf_input(bsdf, ["Coat Weight", "Clearcoat"], 0.6)
        _bump(nodes, links, bsdf, vor.outputs["Distance"], 0.45, 0.02)
    elif p == "bone_veined":
        c = col or hex_to_linear("#ECE6DC")
        vein = hex_to_linear("#C8323A")
        tc = nodes.new("ShaderNodeTexCoord")
        noise = _tex(nodes, "ShaderNodeTexNoise", Scale=9.0, Detail=6.0)
        warp = nodes.new("ShaderNodeMix")
        warp.data_type = "VECTOR"
        warp.inputs[0].default_value = 0.35
        links.new(tc.outputs["Object"], warp.inputs[4])
        links.new(noise.outputs["Color"], warp.inputs[5])
        vor = _tex(nodes, "ShaderNodeTexVoronoi", Scale=3.2, Randomness=1.0)
        if hasattr(vor, "feature"):
            vor.feature = "DISTANCE_TO_EDGE"
        links.new(warp.outputs[1], vor.inputs["Vector"])
        # thin red capillary lines where distance-to-edge is tiny
        line = _n(nodes, "ShaderNodeMapRange")
        line.inputs["From Min"].default_value = 0.0
        line.inputs["From Max"].default_value = 0.03
        line.inputs["To Min"].default_value = 0.6
        line.inputs["To Max"].default_value = 0.0
        line.clamp = True
        links.new(vor.outputs["Distance"], line.inputs["Value"])
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        links.new(line.outputs[0], mix.inputs[0])
        mix.inputs[6].default_value = c
        mix.inputs[7].default_value = vein
        links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        _set_bsdf_input(bsdf, ["Roughness"], 0.42)
        _set_bsdf_input(bsdf, ["Subsurface Weight", "Subsurface"], 0.12)
        grain = _tex(nodes, "ShaderNodeTexNoise", Scale=60.0, Detail=8.0)
        _bump(nodes, links, bsdf, grain.outputs["Fac"], 0.05, 0.005)
    elif p == "tooth_enamel":
        _set_bsdf_input(bsdf, ["Base Color"], col or hex_to_linear("#F1EDE4"))
        _set_bsdf_input(bsdf, ["Roughness"], 0.18)
        _set_bsdf_input(bsdf, ["Subsurface Weight", "Subsurface"], 0.2)
        _set_bsdf_input(bsdf, ["Coat Weight", "Clearcoat"], 0.4)
    elif p == "gunmetal_worn":
        c = col or hex_to_linear("#3A3A3C")
        noise = _tex(nodes, "ShaderNodeTexNoise", Scale=14.0, Detail=10.0, Roughness=0.65)
        links.new(_ramp(nodes, links, noise.outputs["Fac"], _scaled(c, 0.6), _scaled(c, 1.6)), bsdf.inputs["Base Color"])
        links.new(_ramp(nodes, links, noise.outputs["Fac"], (0.28,) * 3, (0.62,) * 3), bsdf.inputs["Roughness"])
        _set_bsdf_input(bsdf, ["Metallic"], 0.92)
        _bump(nodes, links, bsdf, noise.outputs["Fac"], 0.12, 0.01)
    elif p == "brass":
        _set_bsdf_input(bsdf, ["Base Color"], col or hex_to_linear("#B8873F"))
        _set_bsdf_input(bsdf, ["Metallic"], 1.0)
        noise = _tex(nodes, "ShaderNodeTexNoise", Scale=20.0, Detail=6.0)
        links.new(_ramp(nodes, links, noise.outputs["Fac"], (0.22,) * 3, (0.45,) * 3), bsdf.inputs["Roughness"])
    elif p == "steel_polished":
        _set_bsdf_input(bsdf, ["Base Color"], col or hex_to_linear("#C9CED6"))
        _set_bsdf_input(bsdf, ["Metallic"], 1.0)
        _set_bsdf_input(bsdf, ["Roughness"], 0.09)
        _set_bsdf_input(bsdf, ["Anisotropic"], 0.5)
    elif p == "silicone_neon":
        _set_bsdf_input(bsdf, ["Base Color"], col or hex_to_linear("#5BFF2E"))
        _set_bsdf_input(bsdf, ["Subsurface Weight", "Subsurface"], 0.35)
        _set_bsdf_input(bsdf, ["Subsurface Radius"], (0.6, 1.0, 0.4))
        _set_bsdf_input(bsdf, ["Roughness"], 0.38)
    elif p == "ceramic_glazed":
        _set_bsdf_input(bsdf, ["Base Color"], col or hex_to_linear("#C9424D"))
        _set_bsdf_input(bsdf, ["Roughness"], 0.22)
        _set_bsdf_input(bsdf, ["Coat Weight", "Clearcoat"], 0.8)
        speck = _tex(nodes, "ShaderNodeTexNoise", Scale=180.0, Detail=2.0)
        _bump(nodes, links, bsdf, speck.outputs["Fac"], 0.03, 0.002)
    elif p == "milk":
        _set_bsdf_input(bsdf, ["Base Color"], col or hex_to_linear("#F4F1EA"))
        _set_bsdf_input(bsdf, ["Subsurface Weight", "Subsurface"], 1.0)
        _set_bsdf_input(bsdf, ["Subsurface Radius"], (1.0, 0.9, 0.7))
        _set_bsdf_input(bsdf, ["Subsurface Scale"], 0.05)
        _set_bsdf_input(bsdf, ["Roughness"], 0.08)
    elif p == "walnut_wood":
        # Grain runs along X. Long stretched noise = figure; distorted bands = fine grain lines.
        tc = nodes.new("ShaderNodeTexCoord")
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (0.25, 4.0, 4.0)
        links.new(tc.outputs["Object"], mapping.inputs["Vector"])
        figure = _tex(nodes, "ShaderNodeTexNoise", Scale=1.6, Detail=9.0, Roughness=0.6, Distortion=1.2)
        links.new(mapping.outputs["Vector"], figure.inputs["Vector"])
        lines = _tex(nodes, "ShaderNodeTexWave", Scale=3.0, Distortion=16.0, Detail=8.0)
        lines.inputs["Detail Scale"].default_value = 2.5
        lines.wave_type = "BANDS"
        if hasattr(lines, "bands_direction"):
            lines.bands_direction = "Y"
        links.new(mapping.outputs["Vector"], lines.inputs["Vector"])
        r = _n(nodes, "ShaderNodeValToRGB")
        r.color_ramp.elements[0].position = 0.3
        r.color_ramp.elements[0].color = hex_to_linear("#4A2C1E")
        r.color_ramp.elements[1].position = 0.75
        r.color_ramp.elements[1].color = hex_to_linear("#7C523A")
        links.new(figure.outputs["Fac"], r.inputs["Fac"])
        dark = nodes.new("ShaderNodeMix")
        dark.data_type = "RGBA"
        dark.blend_type = "MULTIPLY"
        line_mask = _ramp(nodes, links, lines.outputs["Fac"], (0.82, 0.82, 0.82), (1, 1, 1))
        dark.inputs[0].default_value = 0.6
        links.new(r.outputs["Color"], dark.inputs[6])
        links.new(line_mask, dark.inputs[7])
        links.new(dark.outputs[2], bsdf.inputs["Base Color"])
        _set_bsdf_input(bsdf, ["Roughness"], 0.38)
        _set_bsdf_input(bsdf, ["Coat Weight", "Clearcoat"], 0.18)
        _bump(nodes, links, bsdf, lines.outputs["Fac"], 0.03, 0.004)
    elif p == "pcb_green":
        brick = _tex(nodes, "ShaderNodeTexBrick", Scale=18.0)
        brick.inputs["Color1"].default_value = hex_to_linear("#1E5E2E")
        brick.inputs["Color2"].default_value = hex_to_linear("#2A7A3C")
        brick.inputs["Mortar"].default_value = hex_to_linear("#C9A646")
        links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
        _set_bsdf_input(bsdf, ["Roughness"], 0.35)
        _set_bsdf_input(bsdf, ["Coat Weight", "Clearcoat"], 0.5)
    elif p == "toon_flat":
        # flat cartoon fill for explainer arrows / X marks (2D graphic living in 3D)
        c = col or hex_to_linear("#E53322")
        emit = nodes.new("ShaderNodeEmission")
        emit.inputs["Color"].default_value = (*tuple(c)[:3], 1.0)
        emit.inputs["Strength"].default_value = 1.0
        links.new(emit.outputs[0], out.inputs["Surface"])
    elif p == "outline_black":
        # inverted-hull outline: the flipped shell is visible only behind the silhouette
        geo = nodes.new("ShaderNodeNewGeometry")
        transp = nodes.new("ShaderNodeBsdfTransparent")
        emit = nodes.new("ShaderNodeEmission")
        emit.inputs["Color"].default_value = (*tuple(col or (0.0, 0.0, 0.0))[:3], 1.0)
        mixs = nodes.new("ShaderNodeMixShader")
        links.new(geo.outputs["Backfacing"], mixs.inputs[0])
        links.new(emit.outputs[0], mixs.inputs[1])
        links.new(transp.outputs[0], mixs.inputs[2])
        links.new(mixs.outputs[0], out.inputs["Surface"])
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
    else:
        raise KeyError(p)
    return mat


PRO_MATERIAL_PRESETS = (
    "skin_realistic", "muscle_striated", "tissue_spongy", "bone_veined", "tooth_enamel",
    "gunmetal_worn", "brass", "steel_polished", "silicone_neon", "ceramic_glazed", "milk",
    "walnut_wood", "pcb_green", "toon_flat", "outline_black",
)

_create_pbr_material_base = create_pbr_material


def create_pbr_material(  # type: ignore[no-redef]  # noqa: F811
    preset: str,
    name: Optional[str] = None,
    base_color: Optional[Sequence[float]] = None,
) -> bpy.types.Material:
    """All presets: the originals plus PRO_MATERIAL_PRESETS. base_color is linear RGBA
    (use zdf.hex_to_linear('#RRGGBB') for display hex colours)."""
    p = preset.lower()
    if p not in PRO_MATERIAL_PRESETS:
        return _create_pbr_material_base(preset, name=name, base_color=base_color)
    mat_name = name or f"ZDF_Mat_{p}"
    existing = bpy.data.materials.get(mat_name)
    if existing and base_color is None:
        return existing
    return _pro_material(p, mat_name, base_color)


# ------------------------------------------------------------------------------
# 11.3 Real modeling: lathe, rounded boxes, tubes, finishing stack, UVs
# ------------------------------------------------------------------------------

def _mesh_object(name: str, bm, location, collection) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = tuple(location)
    _link_to_collection(obj, collection)
    return obj


def finish_surface(
    obj: bpy.types.Object,
    bevel: float = 0.0,
    bevel_segments: int = 3,
    subsurf: int = 0,
    weighted_normals: bool = True,
    smooth: bool = True,
) -> bpy.types.Object:
    """Production finishing stack: angle-limited bevel -> subdivision -> weighted normals."""
    if obj.type != "MESH":
        return obj
    if bevel > 0:
        b = obj.modifiers.new("ZDF_Bevel", "BEVEL")
        b.width = bevel
        b.segments = bevel_segments
        b.limit_method = "ANGLE"
        b.angle_limit = math.radians(35)
    if subsurf > 0:
        s = obj.modifiers.new("ZDF_Subsurf", "SUBSURF")
        s.levels = min(2, subsurf)
        s.render_levels = subsurf
    if smooth:
        _shade_smooth_safe(obj)
    if weighted_normals and subsurf == 0:
        try:
            w = obj.modifiers.new("ZDF_WeightedNormal", "WEIGHTED_NORMAL")
            w.keep_sharp = True
        except Exception:
            pass
    return obj


def make_lathe(
    profile: Sequence[Sequence[float]],
    segments: int = 64,
    name: str = "ZDF_Lathe",
    location: Sequence[float] = (0.0, 0.0, 0.0),
    cap_bottom: bool = True,
    cap_top: bool = False,
    thickness: float = 0.0,
    subsurf: int = 2,
    material: Optional[bpy.types.Material] = None,
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    """
    Revolve a list of (radius, z) points around Z — the right way to model bowls, cups,
    cans, bottles, pans, lenses, pistons, pills, bolts. Put extra points close together
    near rims for crisp edges under subdivision. `thickness` adds a Solidify wall for
    open shells. UVs: U around, V along the profile (label-ready).
    """
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    seg = max(8, int(segments))
    rings: list[list] = []
    for r, z in profile:
        if r <= 1e-6:
            rings.append([bm.verts.new((0.0, 0.0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), z)) for i in range(seg)])
    n_prof = max(1, len(rings) - 1)

    def add_face(verts, uvs):
        try:
            f = bm.faces.new(verts)
        except ValueError:
            return
        for loop, uv in zip(f.loops, uvs):
            loop[uv_layer].uv = uv

    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        v0, v1 = k / n_prof, (k + 1) / n_prof
        for i in range(seg):
            j = (i + 1) % seg
            u0, u1 = i / seg, (i + 1) / seg
            if len(a) > 1 and len(b) > 1:
                add_face([a[i], a[j], b[j], b[i]], [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
            elif len(a) == 1 and len(b) > 1:
                add_face([a[0], b[j], b[i]], [((u0 + u1) / 2, v0), (u1, v1), (u0, v1)])
            elif len(a) > 1 and len(b) == 1:
                add_face([a[i], a[j], b[0]], [(u0, v0), (u1, v0), ((u0 + u1) / 2, v1)])
    if cap_bottom and len(rings[0]) > 1:
        try:
            bm.faces.new(list(reversed(rings[0])))
        except ValueError:
            pass
    if cap_top and len(rings[-1]) > 1:
        try:
            bm.faces.new(rings[-1])
        except ValueError:
            pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _mesh_object(name, bm, location, collection)
    if thickness > 0:
        sol = obj.modifiers.new("ZDF_Wall", "SOLIDIFY")
        sol.thickness = thickness
        sol.offset = -1.0
        sol.use_even_offset = True
    finish_surface(obj, subsurf=subsurf, weighted_normals=False)
    if material is not None:
        assign_material(obj, material)
    return obj


def make_rounded_box(
    size: Sequence[float] = (1.0, 1.0, 1.0),
    location: Sequence[float] = (0.0, 0.0, 0.0),
    bevel: float = 0.02,
    segments: int = 4,
    name: str = "ZDF_RoundedBox",
    material: Optional[bpy.types.Material] = None,
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    """Hard-surface block with real rounded edges + weighted normals (phones, housings,
    chips, boards, blocks). `size` = full extents in metres."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:  # simple box projection, good enough for decals
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        u_i, v_i = [i for i in range(3) if i != ax]
        for loop in f.loops:
            co = loop.vert.co
            loop[uv].uv = (co[u_i] / max(size[u_i], 1e-6) + 0.5, co[v_i] / max(size[v_i], 1e-6) + 0.5)
    obj = _mesh_object(name, bm, location, collection)
    finish_surface(obj, bevel=min(bevel, min(size) * 0.49), bevel_segments=segments)
    if material is not None:
        assign_material(obj, material)
    return obj


def make_tube(
    points: Sequence[Sequence[float]],
    radius: float = 0.02,
    name: str = "ZDF_Tube",
    radii: Optional[Sequence[float]] = None,
    resolution: int = 10,
    smooth_path: bool = True,
    caps: bool = True,
    material: Optional[bpy.types.Material] = None,
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    """Tube swept along a path (veins, nerves, cables, hoses, straws, airflow ribbons).
    `radii` gives a per-point radius (taper). Returns a Curve object."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = max(2, resolution // 2)
    cu.resolution_u = 16
    cu.use_fill_caps = caps
    pts = [Vector(p) for p in points]
    if smooth_path:
        sp = cu.splines.new("BEZIER")
        sp.bezier_points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            bp = sp.bezier_points[i]
            bp.co = p
            bp.handle_left_type = bp.handle_right_type = "AUTO"
            bp.radius = (radii[i] / radius) if radii else 1.0
    else:
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (*p, 1.0)
            sp.points[i].radius = (radii[i] / radius) if radii else 1.0
    obj = bpy.data.objects.new(name, cu)
    _link_to_collection(obj, collection)
    if material is not None:
        cu.materials.append(material)
    return obj


def smart_uv(obj: bpy.types.Object, angle_deg: float = 66.0, margin: float = 0.003) -> bool:
    """Smart-UV-project a mesh (needed before image decals/labels on arbitrary meshes).
    Works headless and inside the live bridge. Returns True on success."""
    if obj is None or obj.type != "MESH" or not obj.data.polygons:
        return False
    view_layer = bpy.context.view_layer
    prev_active = view_layer.objects.active
    prev_sel = [o for o in bpy.context.selected_objects]
    try:
        for o in prev_sel:
            o.select_set(False)
        view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(angle_deg), island_margin=margin)
        return True
    except Exception as e:
        print(f"[zdf_helpers] smart_uv skipped for {obj.name}: {e}")
        return False
    finally:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
        obj.select_set(False)
        for o in prev_sel:
            try:
                o.select_set(True)
            except Exception:
                pass
        view_layer.objects.active = prev_active


def grow_tube(tube: bpy.types.Object, start_frame: int, end_frame: int) -> None:
    """Animate a tube drawing itself from its first point (nerve signals, veins, airflow)."""
    cu = tube.data
    cu.bevel_factor_end = 0.0
    cu.keyframe_insert("bevel_factor_end", frame=int(start_frame))
    cu.bevel_factor_end = 1.0
    cu.keyframe_insert("bevel_factor_end", frame=int(end_frame))


# ------------------------------------------------------------------------------
# 11.4 Layered capped cutaways (skin rim -> muscle -> bone, or casing -> mechanism)
# ------------------------------------------------------------------------------

def cutaway_layers(
    layers: Sequence[tuple],
    cutter_size: Sequence[float] = (2.0, 2.0, 2.0),
    cutter_location: Sequence[float] = (0.0, -1.0, 0.0),
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
    slide_from: Sequence[float] = (0.0, -2.5, 0.0),
    name: str = "ZDF_Cutaway",
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    """
    Cut every layer with ONE shared box (Boolean DIFFERENCE, exact solver) and give each
    layer its own cap material on the cut face, e.g.
      [(skin, create_pbr_material('skin_realistic')),
       (muscle, create_pbr_material('muscle_striated')),
       (bone, create_pbr_material('bone_veined'))]
    With start/end frames the cutter slides in from `slide_from` for a reveal.
    Returns the cutter root empty (animate it to move the cut later).
    """
    root = bpy.data.objects.new(f"{name}_Root", None)
    root.location = tuple(cutter_location)
    _link_to_collection(root, collection)

    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(cutter_size), verts=bm.verts)
    shared = bpy.data.meshes.new(f"{name}_CutterMesh")
    bm.to_mesh(shared)
    bm.free()
    shared.materials.append(None)

    for i, (target, cap_mat) in enumerate(layers):
        if target is None or target.type != "MESH":
            continue
        cutter = bpy.data.objects.new(f"{name}_Cutter_{i}", shared)
        _link_to_collection(cutter, collection)
        cutter.parent = root
        cutter.display_type = "WIRE"
        cutter.hide_render = True
        cutter["zdf_always_hidden"] = True  # finalize_scene_visibility must never unhide it
        cutter.material_slots[0].link = "OBJECT"
        cutter.material_slots[0].material = cap_mat
        if cap_mat is not None and cap_mat.name not in [m.name for m in target.data.materials if m]:
            target.data.materials.append(cap_mat)
        mod = target.modifiers.new(f"{name}_Bool", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.object = cutter
        try:
            mod.solver = "EXACT"
        except Exception:
            pass
        if hasattr(mod, "material_mode"):
            mod.material_mode = "TRANSFER"
        # boolean must run before bevel/subsurf so the cap stays a crisp flat section
        try:
            target.modifiers.move(len(target.modifiers) - 1, 0 if not any(m.type == "ARMATURE" for m in target.modifiers) else 1)
        except Exception:
            pass

    if start_frame is not None and end_frame is not None:
        final = Vector(cutter_location)
        root.location = final + Vector(slide_from)
        root.keyframe_insert("location", frame=int(start_frame))
        root.location = final
        root.keyframe_insert("location", frame=int(end_frame))
        _set_bezier_interpolation(root)
    return root


# ------------------------------------------------------------------------------
# 11.5 ZDF explainer graphics: outlined cartoon arrows (the reference look)
# ------------------------------------------------------------------------------

def _orient_matrix(direction: Sequence[float], facing: Sequence[float]) -> Matrix:
    y = Vector(direction).normalized()
    z = Vector(facing).normalized()
    x = y.cross(z)
    if x.length < 1e-5:
        z = Vector((0, -1, 0)) if abs(y.z) > 0.9 else Vector((0, 0, 1))
        x = y.cross(z)
    x.normalize()
    z = x.cross(y).normalized()
    return Matrix((x, y, z)).transposed()


def add_outlined_arrow(
    location: Sequence[float] = (0.0, 0.0, 0.0),
    direction: Sequence[float] = (0.0, 0.0, 1.0),
    facing: Sequence[float] = (0.0, -1.0, 0.0),
    length: float = 0.25,
    width: Optional[float] = None,
    color: Any = "#E5321F",
    outline: Optional[float] = None,
    depth: Optional[float] = None,
    start_frame: int = 1,
    pop_frames: int = 7,
    nudge: bool = True,
    collection: Optional[bpy.types.Collection] = None,
    name: str = "ZDF_OutlinedArrow",
) -> bpy.types.Object:
    """
    Flat chunky arrow with a thick black outline, exactly the reference style
    ('outward pressure' pale-blue arrows, red pressure arrows). `direction` = where it
    points, `facing` = towards the camera. Colours: red '#E5321F', pale blue '#A9C8F5',
    yellow '#FFD23A'. Pops in at start_frame, then nudges along its direction once.
    """
    w = width or length * 0.62
    outline = outline if outline is not None else length * 0.045
    depth = depth if depth is not None else length * 0.05
    shaft_w, head_len = w * 0.42, length * 0.45
    pts2d = [(-shaft_w / 2, 0), (shaft_w / 2, 0), (shaft_w / 2, length - head_len), (w / 2, length - head_len),
             (0, length), (-w / 2, length - head_len), (-shaft_w / 2, length - head_len)]
    bm = bmesh.new()
    verts = [bm.verts.new((x, y, 0.0)) for x, y in pts2d]
    face = bm.faces.new(verts)
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, -depth), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _mesh_object(name, bm, (0, 0, 0), collection)
    obj.matrix_world = Matrix.Translation(Vector(location)) @ _orient_matrix(direction, facing).to_4x4()

    fill_col = hex_to_linear(color) if isinstance(color, str) else tuple(color)
    obj.data.materials.append(create_pbr_material("toon_flat", name=f"{name}_Fill", base_color=fill_col))
    obj.data.materials.append(create_pbr_material("outline_black"))
    bev = obj.modifiers.new("ZDF_Bevel", "BEVEL")
    bev.width = min(outline * 0.4, depth * 0.45)
    bev.segments = 2
    sol = obj.modifiers.new("ZDF_Outline", "SOLIDIFY")
    sol.thickness = outline
    sol.offset = 1.0
    sol.use_flip_normals = True
    sol.material_offset = 1
    sol.use_rim = False

    _pop_in_scale(obj, start_frame, pop_frames, (1.0, 1.0, 1.0))
    if nudge:
        d = Vector(direction).normalized() * length * 0.12
        base = obj.location.copy()
        f0 = int(start_frame) + pop_frames
        for k, off in enumerate((0, 1, 0)):
            obj.location = base + d * off
            obj.keyframe_insert("location", frame=f0 + k * 6)
        _set_bezier_interpolation(obj)
    return obj


def add_arrow_row(
    start: Sequence[float],
    end: Sequence[float],
    count: int = 4,
    direction: Sequence[float] = (0.0, 0.0, 1.0),
    facing: Sequence[float] = (0.0, -1.0, 0.0),
    length: float = 0.2,
    color: Any = "#A9C8F5",
    start_frame: int = 1,
    stagger: int = 3,
    collection: Optional[bpy.types.Collection] = None,
    name: str = "ZDF_ArrowRow",
) -> list:
    """A row of outlined arrows popping in one after another (pressure / force fields)."""
    a, b = Vector(start), Vector(end)
    out = []
    for i in range(max(1, count)):
        t = i / max(1, count - 1)
        out.append(add_outlined_arrow(a.lerp(b, t), direction, facing, length, color=color,
                                      start_frame=start_frame + i * stagger, collection=collection,
                                      name=f"{name}_{i + 1:02d}"))
    return out


# ------------------------------------------------------------------------------
# 11.6 Diegetic branding (STICK KNOWLEDGE on hero props, never a watermark)
# ------------------------------------------------------------------------------

def brand_image(kind: str = "prop_wrap", assets_dir: Optional[str] = None) -> Optional[Path]:
    """Path of a brand texture pre-rendered by the backend into <project>/assets/branding/:
    'tshirt', 'prop_wrap', 'screen_ui', 'can_label', 'phone_screen' or 'logo'."""
    base = _assets_dir(assets_dir)
    if base is None:
        return None
    for cand in (base / "branding" / f"{kind}.png", base / f"stick_knowledge_{kind}.png"):
        if cand.is_file():
            return cand
    return None


def _image_material(name: str, image_path: Path, emission: float = 0.0, roughness: float = 0.35,
                    metallic_under: bool = False) -> bpy.types.Material:
    """Image (with alpha) printed over a base colour — labels, prints, screens."""
    mat, nodes, links, bsdf = _new_mat(name)
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(image_path), check_existing=True)
    mix = nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (0.80, 0.82, 0.85, 1.0) if metallic_under else (0.95, 0.95, 0.95, 1.0)
    links.new(tex.outputs["Alpha"], mix.inputs[0])
    links.new(tex.outputs["Color"], mix.inputs[7])
    links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    _set_bsdf_input(bsdf, ["Roughness"], roughness)
    if metallic_under:
        inv = nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        links.new(tex.outputs["Alpha"], inv.inputs[1])
        links.new(inv.outputs[0], bsdf.inputs["Metallic"])
    if emission > 0:
        if "Emission Color" in bsdf.inputs:
            links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        _set_bsdf_input(bsdf, ["Emission Strength"], emission)
    return mat


def create_branded_can(
    location: Sequence[float] = (0.0, 0.0, 0.0),
    height: float = 0.122,
    radius: float = 0.033,
    label_image: Optional[str] = None,
    name: str = "SK_Can",
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    """Soda can with a wrap-around STICK KNOWLEDGE label (like the finger-gun short's can)."""
    r, h = radius, height
    profile = [(0.0, 0.0), (r * 0.80, 0.0), (r * 0.93, 0.004), (r, h * 0.07), (r, h * 0.12), (r, h * 0.88),
               (r, h * 0.92), (r * 0.86, h * 0.985), (r * 0.80, h), (r * 0.74, h), (r * 0.72, h * 0.985), (0.0, h * 0.985)]
    can = make_lathe(profile, segments=72, name=name, location=location, cap_bottom=False, subsurf=1, collection=collection)
    img = Path(label_image) if label_image else brand_image("can_label")
    if img is not None and Path(img).is_file():
        assign_material(can, _image_material(f"{name}_Label", Path(img), roughness=0.25, metallic_under=True))
    else:
        assign_material(can, create_pbr_material("brushed_metal"))
        create_branding_decal(mode="prop_wrap", target_obj=can,
                              location=(location[0], location[1] - r - 0.002, location[2] + h / 2),
                              width=h * 0.8, collection=collection)
    return can


def create_phone_with_screen(
    location: Sequence[float] = (0.0, 0.0, 0.0),
    rotation: Sequence[float] = (0.0, 0.0, 0.0),
    screen_image: Optional[str] = None,
    height: float = 0.16,
    name: str = "SK_Phone",
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    """Smartphone showing a Shorts screen (@stickknowledge) — the meta-loop ending prop.
    Pass `screen_image` (e.g. a rendered frame of this very video) to put it on screen.
    Built upright (height along Z) with the screen facing -Y, i.e. towards a default
    front camera; tilt with rotation=(radians(-20), 0, 0) to lean the top away."""
    w, d = height * 0.47, height * 0.055
    body = make_rounded_box(size=(w, d, height), location=(0, 0, 0), bevel=w * 0.14, segments=6, name=name,
                            material=create_pbr_material("dark_rubber", name="SK_PhoneBody", base_color=hex_to_linear("#1B1C1F")),
                            collection=collection)
    me = bpy.data.meshes.new(f"{name}_ScreenMesh")
    sw, sh = w * 0.46, height * 0.475
    me.from_pydata([(-sw, 0, -sh), (sw, 0, -sh), (sw, 0, sh), (-sw, 0, sh)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for li, co in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[li].uv = co
    screen = bpy.data.objects.new(f"{name}_Screen", me)
    screen.location = (0, -d / 2 - 0.0008, 0)
    _link_to_collection(screen, collection)
    img = Path(screen_image) if screen_image else brand_image("phone_screen")
    if img is not None and Path(img).is_file():
        assign_material(screen, _image_material(f"{name}_ScreenMat", Path(img), emission=1.4, roughness=0.08))
    else:
        assign_material(screen, create_pbr_material("glow_cyan", name="SK_ScreenFallback", base_color=(0.02, 0.05, 0.1, 1.0)))
    screen.parent = body
    body.location = tuple(location)
    body.rotation_euler = tuple(rotation)
    return body


def brand_tshirt(torso_obj: bpy.types.Object, chest_location: Sequence[float],
                 facing_rotation: Sequence[float] = (math.radians(90), 0, 0), width: float = 0.26,
                 collection: Optional[bpy.types.Collection] = None) -> bpy.types.Object:
    """Chest print that follows the shirt surface (shrinkwrapped; deforms with the rig)."""
    return create_branding_decal(mode="tshirt", target_obj=torso_obj, location=chest_location,
                                 rotation=facing_rotation, width=width, collection=collection)


# ------------------------------------------------------------------------------
# 11.7 Mixamo characters: import, normalise, retarget, NLA clip stacking
# ------------------------------------------------------------------------------

def _import_fbx(filepath: str) -> list:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(filepath), automatic_bone_orientation=True,
                             ignore_leaf_bones=True, use_anim=True)
    return [o for o in bpy.data.objects if o not in before]


def _bone_prefix(names: Iterable[str]) -> str:
    for n in names:
        if ":" in n:
            return n.split(":", 1)[0] + ":"
    return ""


def _world_bbox_z(objs: Sequence[bpy.types.Object]) -> tuple[float, float]:
    dg = bpy.context.evaluated_depsgraph_get()
    zs = []
    for o in objs:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(dg)
        zs.extend((ev.matrix_world @ Vector(c)).z for c in ev.bound_box)
    return (min(zs), max(zs)) if zs else (0.0, 1.0)


def _push_strip(arm: bpy.types.Object, action: bpy.types.Action, start_frame: int, name: str,
                blend_in: float = 0.0, repeat: float = 1.0, speed: float = 1.0):
    ad = arm.animation_data_create()
    ad.action = None
    track = ad.nla_tracks.new()
    track.name = name
    strip = track.strips.new(name, int(start_frame), action)
    if hasattr(strip, "action_slot") and getattr(action, "slots", None):
        try:
            strip.action_slot = action.slots[0]
        except Exception:
            pass
    strip.repeat = max(0.1, float(repeat))
    if speed != 1.0:
        strip.scale = 1.0 / max(0.05, float(speed))
    strip.use_auto_blend = False
    strip.blend_in = min(float(blend_in), max(0.0, (strip.frame_end - strip.frame_start) / 2 - 0.01))
    strip.extrapolation = "HOLD_FORWARD"
    action.use_fake_user = True
    return strip


def import_mixamo_character(
    char_fbx: str,
    anim_fbx: Optional[str] = None,
    location: Sequence[float] = (0.0, 0.0, 0.0),
    rotation_z: float = 0.0,
    start_frame: int = 1,
    target_height: float = 1.75,
    in_place: bool = False,
    name: str = "Character",
    collection: Optional[bpy.types.Collection] = None,
) -> Optional[bpy.types.Object]:
    """
    Import a Mixamo character FBX ('With Skin'), scale it to `target_height` metres with
    its feet on `location`, and optionally add a first animation clip (any Mixamo FBX —
    'Without Skin' is fine) as an NLA strip at `start_frame`. Returns the armature.
    """
    if not char_fbx or not Path(char_fbx).is_file():
        print(f"[zdf_helpers] Mixamo character not found: {char_fbx}")
        return None
    new = _import_fbx(char_fbx)
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    meshes = [o for o in new if o.type == "MESH"]
    if arm is None:
        print("[zdf_helpers] FBX has no armature; is this a Mixamo download?")
        return None
    arm.name = name
    for o in new:
        _link_to_collection(o, collection)

    ad = arm.animation_data_create()
    baked = ad.action
    ad.action = None

    bpy.context.view_layer.update()
    zmin, zmax = _world_bbox_z(meshes)
    f = float(target_height) / max(1e-4, zmax - zmin)
    arm.scale = tuple(s * f for s in arm.scale)
    bpy.context.view_layer.update()
    zmin, _ = _world_bbox_z(meshes)
    arm.location = (location[0], location[1], arm.location.z - zmin + location[2])
    arm.rotation_euler.z += float(rotation_z)
    for m in meshes:
        _shade_smooth_safe(m)

    if anim_fbx:
        add_mixamo_animation(arm, anim_fbx, start_frame=start_frame, blend_in=0.0, in_place=in_place)
    elif baked is not None:
        _push_strip(arm, baked, start_frame, name=f"{name}_Baked")
    return arm


def _retarget_action(action: bpy.types.Action, src_prefix: str, dst_prefix: str) -> bpy.types.Action:
    if src_prefix == dst_prefix:
        return action
    act = action.copy()
    for fc in _action_fcurves(act):
        if f'"{src_prefix}' in fc.data_path:
            fc.data_path = fc.data_path.replace(f'"{src_prefix}', f'"{dst_prefix}')
    return act


def _flatten_root_motion(action: bpy.types.Action, hips_bone: str) -> None:
    for fc in _action_fcurves(action):
        if fc.data_path == f'pose.bones["{hips_bone}"].location' and fc.array_index in (0, 2) and fc.keyframe_points:
            v = fc.keyframe_points[0].co[1]
            for kp in fc.keyframe_points:
                kp.co[1] = v
                kp.handle_left[1] = v
                kp.handle_right[1] = v


def add_mixamo_animation(
    armature: bpy.types.Object,
    anim_fbx: str,
    start_frame: int = 1,
    blend_in: float = 6.0,
    repeat: float = 1.0,
    speed: float = 1.0,
    in_place: bool = False,
    name: Optional[str] = None,
):
    """
    Add a Mixamo clip (talking, walking, pointing, sitting...) to the character's NLA,
    starting at `start_frame` and cross-fading over `blend_in` frames from the clip
    below it. Works across downloads whose bone prefixes differ (mixamorig: vs mixamorig1:).
    Returns the NLA strip (None if the file is missing).
    """
    if armature is None or not anim_fbx or not Path(anim_fbx).is_file():
        print(f"[zdf_helpers] Mixamo animation not found: {anim_fbx}")
        return None
    new = _import_fbx(anim_fbx)
    src_arm = next((o for o in new if o.type == "ARMATURE"), None)
    action = src_arm.animation_data.action if (src_arm and src_arm.animation_data) else None
    if action is None:
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
        print(f"[zdf_helpers] No animation found in {anim_fbx}")
        return None
    src_prefix = _bone_prefix(b.name for b in src_arm.data.bones)
    dst_prefix = _bone_prefix(b.name for b in armature.data.bones)
    action = _retarget_action(action, src_prefix, dst_prefix)
    action.name = name or Path(anim_fbx).stem
    if in_place:
        _flatten_root_motion(action, f"{dst_prefix}Hips")
    for o in new:
        data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        try:
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Armature) and data.users == 0:
                bpy.data.armatures.remove(data)
        except Exception:
            pass
    return _push_strip(armature, action, start_frame, action.name, blend_in=blend_in, repeat=repeat, speed=speed)


def list_mixamo_bones(armature: bpy.types.Object) -> list:
    return [b.name for b in armature.data.bones] if armature is not None and armature.type == "ARMATURE" else []


# ------------------------------------------------------------------------------
# 11.8 Shot presets (ZDF camera grammar) and timing helpers
# ------------------------------------------------------------------------------

def make_shot(
    preset: str,
    target: Any,
    start_frame: int,
    end_frame: int,
    distance: float = 0.6,
    azimuth_deg: float = -90.0,
    elevation_deg: float = 12.0,
    sweep_deg: float = 25.0,
    lens: float = 50.0,
    fstop: float = 2.2,
    collection: Optional[bpy.types.Collection] = None,
    name: str = "ShotCam",
) -> bpy.types.Object:
    """
    One eased camera move per shot, always tracking `target` (object or (x, y, z)).
    presets: 'push_in', 'pull_back', 'orbit', 'crane_down', 'crane_up', 'slide',
             'macro_creep' (tiny 8 % push for macro detail), 'static' (subtle drift).
    azimuth -90 = camera in front (on -Y) looking towards +Y. distance in metres.
    """
    tgt = target.location.copy() if hasattr(target, "location") else Vector(target)

    def pos(dist, az, el):
        a, e = math.radians(az), math.radians(el)
        return tgt + Vector((dist * math.cos(e) * math.cos(a), dist * math.cos(e) * math.sin(a), dist * math.sin(e)))

    p = preset.lower()
    if p == "push_in":
        keys = [pos(distance * 1.35, azimuth_deg, elevation_deg), pos(distance * 0.85, azimuth_deg, elevation_deg)]
    elif p == "pull_back":
        keys = [pos(distance * 0.8, azimuth_deg, elevation_deg), pos(distance * 1.3, azimuth_deg, elevation_deg)]
    elif p == "orbit":
        keys = [pos(distance, azimuth_deg - sweep_deg / 2 + sweep_deg * t / 4, elevation_deg) for t in range(5)]
    elif p == "crane_down":
        keys = [pos(distance, azimuth_deg, elevation_deg + 35), pos(distance, azimuth_deg, elevation_deg)]
    elif p == "crane_up":
        keys = [pos(distance, azimuth_deg, elevation_deg), pos(distance, azimuth_deg, elevation_deg + 35)]
    elif p == "slide":
        side = Vector((-math.sin(math.radians(azimuth_deg)), math.cos(math.radians(azimuth_deg)), 0)) * distance * 0.35
        base = pos(distance, azimuth_deg, elevation_deg)
        keys = [base - side, base + side]
    elif p == "macro_creep":
        keys = [pos(distance * 1.04, azimuth_deg, elevation_deg), pos(distance * 0.96, azimuth_deg, elevation_deg)]
    else:
        keys = [pos(distance * 1.01, azimuth_deg - 1.5, elevation_deg), pos(distance * 0.99, azimuth_deg + 1.5, elevation_deg)]

    s, e = int(start_frame), int(end_frame)
    frames = [round(s + (e - s) * i / (len(keys) - 1)) for i in range(len(keys))]
    return setup_cinematic_camera(list(zip(frames, [tuple(k) for k in keys])),
                                  target_obj=target if hasattr(target, "location") else None,
                                  target_location=tuple(tgt), lens=lens, dof_fstop=fstop,
                                  collection=collection, name=name)


def show_between(obj: bpy.types.Object, start_frame: int, end_frame: int) -> None:
    """Keyframe render/viewport visibility so `obj` only exists in [start, end]."""
    for attr in ("hide_render", "hide_viewport"):
        setattr(obj, attr, True)
        obj.keyframe_insert(attr, frame=max(0, int(start_frame) - 1))
        setattr(obj, attr, False)
        obj.keyframe_insert(attr, frame=int(start_frame))
        setattr(obj, attr, True)
        obj.keyframe_insert(attr, frame=int(end_frame) + 1)
