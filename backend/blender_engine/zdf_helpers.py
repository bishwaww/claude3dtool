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


def _set_bezier_interpolation(obj: bpy.types.Object, interpolation: str = "BEZIER") -> None:
    if not obj.animation_data or not obj.animation_data.action:
        return
    action = obj.animation_data.action
    # Blender 5.0+ layered actions vs legacy fcurves
    fcurves = getattr(action, "fcurves", None)
    if fcurves is None:
        return
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
) -> dict[str, Any]:
    """
    Initializes a clean Zack D. Films 9:16 (1080x1920, 30fps) studio scene:
      - AgX Color Management with Medium High Contrast
      - Curved Studio Cyclorama with vibrant Sky-Blue/Cyan radial gradient (#9EE2FF -> #26A6F5)
        or dark cinematic navy/black (#060B14) for space/microscopic/dark scenes
      - 3-point softbox studio area lighting (warm key, cool fill, crisp rim)
      - EEVEE Next (Raytracing) or Cycles GPU OptiX + OpenImageDenoise (6GB+ VRAM safe)
    """
    # Wipe existing scene objects cleanly
    bpy.ops.wm.read_factory_settings(use_empty=True)
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

    # Color Management (AgX)
    try:
        scene.view_settings.view_transform = "AgX"
        try:
            scene.view_settings.look = "AgX - Medium High Contrast"
        except Exception:
            scene.view_settings.look = "None"
    except Exception:
        scene.view_settings.view_transform = "Filmic"
    scene.view_settings.exposure = 0.05
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

    # World Shader (soft ambient bounce + radial cyan or dark space)
    world = bpy.data.worlds.new("ZDF_World")
    scene.world = world
    world.use_nodes = True
    w_nodes = world.node_tree.nodes
    w_links = world.node_tree.links
    w_nodes.clear()

    w_out = w_nodes.new("ShaderNodeOutputWorld")
    w_bg = w_nodes.new("ShaderNodeBackground")
    w_mix = w_nodes.new("ShaderNodeMix")
    w_mix.data_type = "RGBA"
    w_mix.name = "ZDF_WorldModeMix"
    w_mix.inputs[0].default_value = 1.0 if bg_mode == "dark_space" else 0.0
    # Cyan soft ambient vs dark cinematic space
    w_mix.inputs[6].default_value = (0.32, 0.72, 0.96, 1.0)
    w_mix.inputs[7].default_value = (0.008, 0.015, 0.035, 1.0)
    w_bg.inputs["Strength"].default_value = 0.55 if bg_mode == "cyan_studio" else 0.25
    w_links.new(w_mix.outputs[2], w_bg.inputs["Color"])
    w_links.new(w_bg.outputs["Background"], w_out.inputs["Surface"])

    # Curved Studio Cyclorama Backdrop
    cyc = _build_studio_cyclorama(studio_col, bg_mode=bg_mode)

    # 3-Point Soft Studio Area Lighting
    lights = _build_three_point_lighting(studio_col)

    return {"studio_collection": studio_col, "cyclorama": cyc, "lights": lights}


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
    """Switches studio backdrop cleanly between 'cyan_studio' and 'dark_space' at a given frame."""
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
    scale: float = 0.13,
    start_frame: int = 1,
    collection: Optional[bpy.types.Collection] = None,
) -> bpy.types.Object:
    """Crisp white floating 3D label placard (Zack D. Films callout style, sized for 9:16)."""
    root = bpy.data.objects.new(f"ZDF_Label_{text[:12]}", None)
    root.location = tuple(location)
    _link_to_collection(root, collection)

    # Dark backing pill for readability over cyan backdrop
    w = max(0.36, len(text) * 0.085 + 0.18) * (scale / 0.13)
    h = 0.19 * (scale / 0.13)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0.03, 0))
    pill = bpy.context.active_object
    pill.name = f"ZDF_LabelPill_{text[:12]}"
    pill.scale = (w, 0.04, h)
    bpy.ops.object.transform_apply(scale=True)
    pill.modifiers.new("Bevel", "BEVEL").width = 0.025
    _shade_smooth_safe(pill)
    assign_material(pill, create_pbr_material("dark_rubber", name="ZDF_LabelBg_Mat", base_color=(0.06, 0.08, 0.12, 1.0)))
    _link_to_collection(pill, collection)
    pill.parent = root

    bpy.ops.object.text_add(location=(0, 0.0, 0))
    txt = bpy.context.active_object
    txt.name = f"ZDF_LabelTxt_{text[:12]}"
    txt.data.body = text.upper()
    txt.data.align_x = "CENTER"
    txt.data.align_y = "CENTER"
    txt.data.extrude = 0.012
    txt.data.size = scale
    txt.rotation_euler = (math.pi / 2, 0.0, 0.0)
    txt.data.materials.append(
        create_pbr_material("glowing_energy", name="ZDF_LabelWhite_Mat", base_color=(1.0, 1.0, 1.0, 1.0))
    )
    _link_to_collection(txt, collection)
    txt.parent = root

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
