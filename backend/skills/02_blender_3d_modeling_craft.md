# 02 · Blender 3D Modeling Craft (how a senior artist builds ZDF shots)

You write Blender Python (`bpy`, Blender 4.2–5.3) that builds shots with `import zdf_helpers as zdf`. You are a 3D modeler, not a primitive placer: a raw cube or UV sphere with a flat colour is a bug.

## 1. Non-negotiables
1. **Real forms.** Revolved objects (bowls, cups, cans, bottles, pans, pistons, lenses, fingers, bones, pills) → `zdf.make_lathe(profile)` with a hand-written (radius, z) profile. Hard-surface parts (phones, chips, housings, boards, blocks) → `zdf.make_rounded_box(...)`. Tubes (veins, nerves, cables, hoses, intestines, airflow) → `zdf.make_tube(points, radius, radii=...)`. Organic blobs → lathe or subdivided bmesh, never a sphere.
2. **Edges catch light.** Every hard edge is bevelled (`zdf.finish_surface(obj, bevel=…)` or the bevel built into `make_rounded_box`). Subdivided objects get extra profile points near rims so edges stay crisp.
3. **Smooth shading + weighted normals** on everything except deliberately faceted things.
4. **Real-world scale in metres.** A fingertip is 0.018 m across, a bowl 0.22 m, a can 0.122 m tall, a person 1.75 m. Scale drives depth of field and subsurface scattering; wrong scale = fake look.
5. **Materials from presets, then tuned.** Use `zdf.create_pbr_material(preset, base_color=zdf.hex_to_linear("#RRGGBB"))`:
   - organic: `skin_realistic`, `muscle_striated`, `tissue_spongy`, `bone_veined`, `tooth_enamel`, `skin_sss`, `bone`, `muscle_cutaway`
   - hard: `gunmetal_worn`, `brass`, `steel_polished`, `brushed_metal`, `glossy_plastic`, `dark_rubber`, `ceramic_glazed`, `pcb_green`, `clear_glass`
   - liquids/soft: `milk`, `liquid`, `silicone_neon`
   - set: `walnut_wood`, `warm_wood`
   - graphics: `toon_flat` (flat colour), `outline_black`, `glow_cyan`, `glowing_energy`, `warning_red`
   Never leave the default grey Principled BSDF on a visible object.
6. **Imported assets first, modeling as the fallback.** For every asset in `ctx["assets"]`, try `zdf.import_and_normalize_asset(path, target_height=…)`; if it returns `None`, model it properly with the tools above (not `create_procedural_prop` boxes unless it fits).
7. **UVs before images.** Lathe and rounded-box UVs are generated; for other meshes call `zdf.smart_uv(obj)` before applying labels or decals.

## 2. Profiles that work (copy and adapt)
```python
# Glazed bowl (open shell, wall from Solidify)
bowl = zdf.make_lathe([(0,0),(0.05,0),(0.06,0.004),(0.085,0.03),(0.105,0.075),(0.112,0.085),(0.114,0.088)],
                      thickness=0.006, material=zdf.create_pbr_material("ceramic_glazed"), collection=col)
# Liquid surface inside it
milk = zdf.make_lathe([(0,0.07),(0.103,0.07)], cap_bottom=False, subsurf=1, material=zdf.create_pbr_material("milk"), collection=col)
# Fingertip (rotate 90° on Y to lie along X)
finger = [(0,0),(0.05,0),(0.085,0.02),(0.09,0.1),(0.09,0.42),(0.08,0.5),(0.05,0.545),(0,0.555)]  # scale 0.2 for a real finger
# Piston / chamber
chamber = zdf.make_lathe([(0,0),(0.026,0),(0.028,0.004),(0.028,0.15),(0.024,0.155),(0,0.155)], subsurf=1,
                         material=zdf.create_pbr_material("gunmetal_worn"))
```
Nested anatomy = the same profile scaled inward: skin (1.0) → muscle (0.86) → bone (its own thinner profile).

## 3. Cutaways (the signature reveal)
```python
zdf.cutaway_layers([(skin,   zdf.create_pbr_material("skin_realistic", name="SkinCap", base_color=zdf.hex_to_linear("#E8B9A6"))),
                    (muscle, zdf.create_pbr_material("tissue_spongy")),
                    (bone,   zdf.create_pbr_material("bone_veined"))],
                   cutter_size=(1.0, 0.4, 1.0), cutter_location=(0, -0.2, 0.25),
                   start_frame=ctx["start_frame"], end_frame=ctx["start_frame"] + 18, collection=col)
```
One shared cutter, a flat cap material per layer, sliding in for a reveal. Put mechanisms (chamber, gears, springs) inside the cut so both read at once. Cutters are never rendered.

## 4. Explainers, branding, characters
- Arrows: `zdf.add_outlined_arrow(location, direction, facing=toward_camera, length, color="#E5321F", start_frame=beat)`, or `zdf.add_arrow_row(start, end, count=4, color="#A9C8F5", start_frame=beat, stagger=3)`.
- Labels: `zdf.add_3d_label_sign("WATER", location, scale, start_frame)`; X marks, chevrons, airflow, arcs, sparks: see the helper API doc.
- Branding: `zdf.create_branded_can(...)`, `zdf.create_phone_with_screen(...)` (screen faces −Y), `zdf.brand_tshirt(torso, chest_location)`, `zdf.create_branding_decal(mode=...)`. Brand textures come from `<project>/assets/branding/` automatically.
- People: `arm = zdf.import_mixamo_character(char_fbx, anim_fbx, location, start_frame, target_height=1.75)` (details in skill 03).

## 5. Scene script contract (headless build)
```python
import zdf_helpers as zdf

def build_scene(ctx):
    col = zdf.setup_scene_collection(ctx["scene_index"], ctx["start_frame"], ctx["end_frame"])
    zdf.set_studio_bg_keyframe(ctx.get("bg_mode", "cyan_studio"), ctx["start_frame"])
    # ... model, shade, animate everything INTO `col` ...
    cam = zdf.make_shot("push_in", target, ctx["start_frame"], ctx["end_frame"], distance=0.6, collection=col)
    zdf.finalize_scene_visibility(col, ctx["start_frame"], ctx["end_frame"])
    return {"camera": cam, "collection": col, "preview_frame": (ctx["start_frame"] + ctx["end_frame"]) // 2}
```
Every object goes into `col`. All motion is keyframed inside `[start_frame, end_frame]`. Return the camera.

## 6. Mandatory visual self-critique loop
Code that runs is not a finished shot. When the live Blender bridge is connected, after building or changing a hero asset or a shot:
1. Call `blender_capture_viewport` at the shot's key frame — after pop-in graphics have finished (they are invisible on their start frame) — and LOOK at the image. For camera moves, also check the first and last frame.
2. Critique it like a director, in this order:
   - **Framing:** subject inside the middle 60 % height of the 9:16 frame? Nothing important under the caption band (~70–85 % height)? Hero big enough? Readable silhouette?
   - **Scale & intersections:** objects floating, sinking into the table, clipping through each other, wrong relative sizes?
   - **Form:** any raw primitive, faceted curve, missing bevel, pinched subdivision?
   - **Material:** grey default anywhere? Skin waxy? Metal flat? Liquids opaque? Cut caps the right colour?
   - **Light & backdrop:** subject separated from the blue? Blown-out highlights? Wrong bg_mode for the shot?
   - **Story:** does the picture show the noun being said at that moment? Is the explainer graphic visible and pointing the right way? Branding readable where planned?
3. Fix the worst problem, capture again, and repeat until the shot passes — usually 2–4 rounds. Say briefly what you changed each round.
4. Only then move to the next shot. Never report a shot "done" without having looked at it.

When working headless (no bridge), the build renders `previews/scene_XX.png`; treat those the same way when the user shares them or the pipeline returns them.

## 7. Asset requests in the storyboard
Give each asset a 1–3 word query and a category; the pipeline resolves them in tiers before falling back to your modeling:
- `anatomy` (skull, teeth, heart, lungs…): NIH 3D → BlenderKit → model it.
- `character` (people, hands, animals): local Mixamo library / user uploads → BlenderKit → Hunyuan3D/TRELLIS.
- `prop`, `material`, `hdri`: user uploads in `assets/custom/` → BlenderKit free → Poly Haven (CC0) → AI 3D → model it.
User-supplied files in `<project>/assets/custom/` always win.

## 8. Common failures to avoid
- Booleans after Subdivision (cut faces get smeared) → `cutaway_layers` puts the Boolean first.
- Decals floating in the air → parent and shrinkwrap them to the target (`create_branding_decal(target_obj=…)`).
- Everything at the origin overlapping → lay shots out apart or rely on per-scene visibility; check the capture.
- Cameras inside objects → keep `distance` larger than the subject radius; check the capture.
- Units in centimetres from FBX imports → always normalise with the import helpers.
