# `zdf_helpers` API (import zdf_helpers as zdf) — Blender 4.2–5.3

Colours: pass display hex through `zdf.hex_to_linear("#RRGGBB")`. Units: metres. Frames: `zdf.sec_to_frame(seconds)` (frame 1 = 0 s).

## Studio, backdrop, timing
- `zdf.configure(project_dir=None, assets_dir=None)` — where brand textures/assets live (the build/bridge calls it).
- `zdf.init_zdf_studio(render_engine="EEVEE_NEXT", bg_mode="cyan_studio", cycles_samples=64, fps=30, cyclorama=False)` — 1080x1920, Khronos PBR Neutral colour, frame-locked ZDF backdrop, 3-point lights. Called by the build.
- `zdf.set_studio_bg_keyframe(bg_mode, frame)` — hard switch at `frame`: `"cyan_studio"` (radial #9BDAF0→#31B9E6), `"sky_gradient"` (#52ABFB→#ACD6FE above the table line), `"dark_space"`, `"interior"`.
- `zdf.setup_zdf_backdrop(bg_mode, glow_center=(0.5,0.46), glow_radius=0.62, horizon=0.40)` — rebuild the world (rarely needed).
- `zdf.add_studio_tabletop(size=(3.2,1.6,0.06), location=(0,0,-0.03), wood="walnut", collection=None)` — top surface at z = loc.z + size.z/2.
- `zdf.setup_scene_collection(scene_index, start_frame, end_frame) -> Collection` (named `Scene_01`, `Scene_02`, …; reuse the returned object rather than looking it up by name); `zdf.finalize_scene_visibility(col, start_frame, end_frame)` (call last); `zdf.show_between(obj, start_frame, end_frame)`.

## Modeling
- `zdf.make_lathe(profile[(r,z),...], segments=64, name, location, cap_bottom=True, cap_top=False, thickness=0.0, subsurf=2, material=None, collection=None)` — revolve around Z; UV U=around, V=along profile.
- `zdf.make_rounded_box(size=(x,y,z), location, bevel=0.02, segments=4, name, material=None, collection=None)` — full extents; box UVs.
- `zdf.make_tube(points, radius=0.02, name, radii=None, resolution=10, smooth_path=True, caps=True, material=None, collection=None)` — curve tube; `zdf.grow_tube(tube, start_frame, end_frame)` animates it drawing on.
- `zdf.finish_surface(obj, bevel=0.0, bevel_segments=3, subsurf=0, weighted_normals=True, smooth=True)` — bevel → subsurf → weighted normals.
- `zdf.smart_uv(obj)` — before image textures on arbitrary meshes.
- `zdf.create_procedural_prop(kind, name, location, scale, material, collection)` — quick fallbacks: battery, bottle, mug, pan, phone, table, tube/esophagus, chamber/stomach, bone, gear, box/plate, human_bust.
- `zdf.import_and_normalize_asset(filepath, target_height=1.0, location, rotation, collection, name) -> Object|None` — .blend/.glb/.gltf/.fbx/.obj.

## Materials
- `zdf.create_pbr_material(preset, name=None, base_color=None)` presets:
  organic `skin_realistic` `muscle_striated` `tissue_spongy` `bone_veined` `tooth_enamel` `skin_sss` `bone` `muscle_cutaway` ·
  hard `gunmetal_worn` `brass` `steel_polished` `brushed_metal` `glossy_plastic` `dark_rubber` `ceramic_glazed` `pcb_green` `clear_glass` ·
  soft `milk` `liquid` `silicone_neon` · set `walnut_wood` `warm_wood` · graphics `toon_flat` `outline_black` `glow_cyan` `glowing_energy` `warning_red`.
- `zdf.assign_material(obj, mat)` — obj and all mesh children.

## Cutaways
- `zdf.cutaway_layers([(obj, cap_mat), ...], cutter_size=(2,2,2), cutter_location=(0,-1,0), start_frame=None, end_frame=None, slide_from=(0,-2.5,0), name, collection) -> root_empty` — shared exact Boolean, per-layer flat cap material, optional slide-in reveal.
- `zdf.apply_animated_cutaway(target_obj, cutter_bounds, start_frame, end_frame, cap_material, collection)` — older single-object version.

## Explainer graphics
- `zdf.add_outlined_arrow(location, direction=(0,0,1), facing=(0,-1,0), length=0.25, width=None, color="#E5321F", outline=None, depth=None, start_frame=1, pop_frames=7, nudge=True, collection, name)` — flat arrow, thick black outline (reference style).
- `zdf.add_arrow_row(start, end, count=4, direction, facing, length=0.2, color="#A9C8F5", start_frame=1, stagger=3, collection, name)`.
- `zdf.add_3d_arrow(start, end, color, radius, start_frame, pop_frames, collection, name)` — tube-style 3D arrow.
- `zdf.add_3d_x_mark(location, scale, color, start_frame, collection)` · `zdf.add_3d_chevron_flow(points, count, color, start_frame, end_frame, scale, collection)` · `zdf.add_3d_airflow_streaks(points, count, start_frame, end_frame, collection)` · `zdf.add_3d_energy_arc(start, end, color, start_frame, end_frame, collection)` · `zdf.add_3d_sparks(origin, count, start_frame, end_frame, collection)` · `zdf.add_3d_label_sign(text, location, scale=0.035, start_frame=1, collection=None, pin_length=0.0, facing_rotation=(0,0,0), dark=False)` — reference-style off-white sign with dark letters on an optional metal pin; `scale` = letter height in metres (0.035 for a 0.22 m bowl, 0.12 for a person); faces −Y.
- Pop-in graphics (arrows, labels, X marks) are scaled to ~0 at their start_frame — capture a frame AFTER the pop (≥ start_frame + 8) when checking them.

## Branding (diegetic)
- `zdf.brand_image(kind)` — path to `<project>/assets/branding/{tshirt,tshirt_dark,prop_wrap,screen_ui,can_label,phone_screen,logo}.png`.
- `zdf.create_branded_can(location, height=0.122, radius=0.033, label_image=None, name, collection)`.
- `zdf.create_phone_with_screen(location, rotation=(0,0,0), screen_image=None, height=0.16, name, collection)` — upright, screen faces −Y.
- `zdf.brand_tshirt(torso_obj, chest_location, facing_rotation=(pi/2,0,0), width=0.26, collection)`.
- `zdf.create_branding_decal(text="STICK KNOWLEDGE", target_obj=None, mode="prop_wrap"|"tshirt"|"screen_ui"|"engraved", location, rotation, width, assets_dir, collection)`.

## Characters (Mixamo)
- `zdf.import_mixamo_character(char_fbx, anim_fbx=None, location=(0,0,0), rotation_z=0, start_frame=1, target_height=1.75, in_place=False, name, collection) -> armature|None`.
- `zdf.add_mixamo_animation(armature, anim_fbx, start_frame=1, blend_in=6, repeat=1, speed=1, in_place=False, name=None) -> NLA strip|None`.
- `zdf.list_mixamo_bones(armature)`.

## Camera & animation
- `zdf.make_shot(preset, target, start_frame, end_frame, distance=0.6, azimuth_deg=-90, elevation_deg=12, sweep_deg=25, lens=50, fstop=2.2, collection, name)` — presets push_in, pull_back, orbit, crane_down, crane_up, slide, macro_creep, static. Pass frames as keywords or positionally; the names are `start_frame`/`end_frame` (not start/end).
- `zdf.setup_cinematic_camera(keyframes[(frame,(x,y,z))], target_obj=None, target_location, lens, dof_fstop, collection, name)` — custom paths.
- `zdf.animate_transform(obj, [(frame, loc, rot, scale), ...], interpolation="BEZIER")` · `zdf.bind_camera_marker(scene, camera_obj, frame, name)`.

## Save & render
- `zdf.pack_and_save_project(filepath)` · `zdf.render_scene_preview(frame, output_path, camera_obj, preview_scale_pct=50)` · `zdf.render_animation(start_frame, end_frame, output_dir, render_engine, cycles_samples)`.
