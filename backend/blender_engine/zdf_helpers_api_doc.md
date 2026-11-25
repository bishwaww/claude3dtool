# `zdf_helpers.py` — Master Blender 3D Studio API Reference

Every generated scene script (`scene_XX.py`) has `zdf_helpers` importable directly (`import zdf_helpers as zdf`).
Always use these helpers instead of hand-coding boilerplate nodes, render settings, or raw vertex arrays.

## Scene & Collection Management
- `zdf.init_zdf_studio(render_engine="EEVEE_NEXT", bg_mode="cyan_studio", cycles_samples=64)`
  Initializes 1080x1920 30fps, AgX color management, curved cyclorama backdrop (`#9EE2FF -> #26A6F5` for `"cyan_studio"`, `#060B14` for `"dark_space"`), 3-point softbox lighting, and GPU denoising. (Called automatically by `master_build.py`; scenes can call `zdf.set_studio_bg_keyframe(bg_mode, frame)` to switch backdrop mode on scene cuts.)
- `zdf.setup_scene_collection(scene_index: int, start_frame: int, end_frame: int) -> bpy.types.Collection`
  Creates `Scene_XX` collection, makes it active, and keyframes `hide_viewport` / `hide_render` on all its objects (via an automated finalizer or `zdf.finalize_scene_visibility(col, start_frame, end_frame)`) so objects only appear during `[start_frame, end_frame]`.
- `zdf.finalize_scene_visibility(col, start_frame: int, end_frame: int)`
  MUST be called at the end of `build_scene(ctx)` after creating all objects in `col`. Keyframes `hide_render` and `hide_viewport` cleanly on every object inside `col` so it is invisible before `start_frame` and after `end_frame`.

## Asset Importing & Procedural Fallback
- `zdf.import_and_normalize_asset(filepath: str | None, target_height: float = 1.0, location=(0, 0, 0), rotation=(0, 0, 0), collection=None, name="Asset") -> bpy.types.Object | None`
  Cleanly imports `.blend` (appends mesh objects), `.glb`/`.gltf`, `.fbx`, or `.obj`, joins/parents under an empty or normalized root mesh, centers XY pivot with bottom at `Z=0`, scales uniformly to `target_height`, and places at `location`/`rotation`. Returns `None` if `filepath` is `None` or unreadable.
- `zdf.create_procedural_prop(kind: str, name="Prop", location=(0, 0, 0), scale=(1, 1, 1), material=None, collection=None) -> bpy.types.Object`
  Built-in high-quality procedural props with smooth bevels & subdivision:
  - `"battery"` (coin/cylindrical battery with metallic rim & terminal cap)
  - `"bottle"` (cylindrical bottle with neck & cap)
  - `"mug"` (handle + hollow cup)
  - `"pan"` (frying pan with handle)
  - `"phone"` (sleek rounded smartphone slab with screen face)
  - `"table"` (warm wood studio tabletop)
  - `"tube"` / `"esophagus"` (curved organic/mechanical cutaway tube)
  - `"chamber"` / `"stomach"` (organic sculpted pouch/chamber)
  - `"bone"` (anatomical bone shaft with condyle ends)
  - `"gear"` (toothed mechanical gear)
  - `"box"` / `"plate"` (beveled metallic/plastic housing or plate)
  - `"human_bust"` (stylized semi-realistic head/neck/shoulders/tshirt torso fallback if no Mixamo/MPFB2 character is loaded)

## Materials (Semi-Realistic PBR)
- `zdf.create_pbr_material(preset: str, name: str | None = None, base_color: tuple | None = None) -> bpy.types.Material`
  Presets: `"skin_sss"`, `"bone"`, `"muscle_cutaway"`, `"brushed_metal"`, `"clear_glass"`, `"glossy_plastic"`, `"warm_wood"`, `"glowing_energy"`, `"liquid"`, `"fabric_tshirt"`, `"dark_rubber"`, `"warning_red"`, `"glow_cyan"`.
- `zdf.assign_material(obj, mat)` — Safely assigns material to a mesh object or all mesh children of a hierarchy.

## 3D Explainer Mechanics & Motion Graphics
- `zdf.apply_animated_cutaway(target_obj, cutter_bounds=((-2, 2), (-2, 0), (-2, 2)), start_frame=1, end_frame=30, cap_material="muscle_cutaway", collection=None)`
  Non-destructive Boolean difference cutaway that slides smoothly from outside to `cutter_bounds` between `start_frame` and `end_frame` with clean `cap_material` shading on the cut face.
- `zdf.create_branding_decal(text="STICK KNOWLEDGE", target_obj=None, mode="prop_wrap", location=(0, -0.5, 0.5), rotation=(1.5708, 0, 0), width=0.55, assets_dir=None, collection=None)`
  Generates a crisp transparent PNG decal with Pillow (or 3D embossed text for `mode="engraved"`) and attaches/wraps it diegetically onto `target_obj` (`mode` in `{"tshirt", "prop_wrap", "screen_ui", "engraved"}`).
- `zdf.add_3d_arrow(start=(0,0,0), end=(0,0,1), color=(0.95, 0.12, 0.1, 1.0), radius=0.04, start_frame=1, pop_frames=10, collection=None, name="Arrow")`
- `zdf.add_3d_chevron_flow(points=[(0,0,0),(0,0,1)], count=4, color=(0.05, 0.92, 1.0, 1.0), start_frame=1, end_frame=90, scale=0.14, collection=None)`
- `zdf.add_3d_x_mark(location=(0,0,0), scale=0.35, color=(0.95, 0.1, 0.1, 1.0), start_frame=1, collection=None)`
- `zdf.add_3d_airflow_streaks(points=[(0,0,0),(0.2,0,0.5),(0,0,1.2)], count=3, start_frame=1, end_frame=90, collection=None)`
- `zdf.add_3d_energy_arc(start=(0,0,0), end=(0.5,0,0.5), color=(0.2, 0.85, 1.0, 1.0), start_frame=1, end_frame=90, collection=None)`
- `zdf.add_3d_sparks(origin=(0,0,0), count=14, start_frame=1, end_frame=60, collection=None)`
- `zdf.add_3d_label_sign(text="WATER", location=(0,0,1.2), scale=0.22, start_frame=1, collection=None)`

## Camera & Animation Helpers
- `zdf.animate_transform(obj, keyframes: list[tuple[int, tuple, tuple, tuple]], interpolation="BEZIER")`
  Each keyframe tuple: `(frame, location, rotation_euler_rad, scale)`.
- `zdf.setup_cinematic_camera(keyframes: list[tuple[int, tuple]], target_obj=None, target_location=(0, 0, 0.5), lens=50.0, dof_fstop=2.8, collection=None, name="SceneCam") -> bpy.types.Object`
  `keyframes`: list of `(frame, (x, y, z))` camera locations. Automatically creates a smooth Track-To target empty, Bezier-eased dolly/orbit motion, and subtle macro Depth of Field focused on the target!
