# 03 · Animation, Camera & Mixamo

## 1. Timing is locked to the voice
- Frame for a word: `zdf.sec_to_frame(seconds)` = `round(seconds * 30) + 1` (frame 1 = 0.00 s).
- `<project>/audio/timestamps.json` holds word-level times (ElevenLabs alignment or faster-whisper on an uploaded voiceover). Scene `start_frame`/`end_frame` come from it; inside a scene, key every visual beat (arrow pop, label, cut-in, pour) to the frame of the word it illustrates, landing 2–4 frames BEFORE the word so the eye arrives with the ear.
- A scene lasts one caption phrase or two (1.25–3 s). Long sentences become several shots.

## 2. Camera grammar (`zdf.make_shot`)
```python
cam = zdf.make_shot("push_in", target_obj_or_xyz, start, end, distance=0.6, azimuth_deg=-90, elevation_deg=12, lens=50, fstop=2.2, collection=col)
```
| preset | use it for |
|---|---|
| `push_in` | default reveal; hooks; "look at this" moments |
| `pull_back` | context reveal, endings, "and that's why…" |
| `orbit` (sweep 20–40°) | showing a mechanism or cutaway in 3D |
| `crane_down` / `crane_up` | from overview into the action / leaving the scene |
| `slide` | following a pour, a row of items, a process |
| `macro_creep` | extreme close-ups (blade edge, pores, bubbles): tiny 8 % push |
| `static` | near-static hold with micro drift (never truly locked) |
- Everything is Bezier-eased with a Track-To target; depth of field focuses on the target. Macro: lens 85–100, f/1.8–2.4, distance 0.05–0.25 m. People: lens 35–50, f/2.8–4, distance 1.2–2.5 m.
- One move per shot. Vary angle between consecutive shots (low → top-down → side) so cuts feel energetic.
- Bind each shot's camera with `zdf.bind_camera_marker(scene, cam, start_frame, name)` (the build does this when you return the camera).

## 3. Object animation
- Use `zdf.animate_transform(obj, [(frame, loc, rot, scale), ...])` or plain `keyframe_insert`; set Bezier via the helpers. Pops: `_pop_in_scale` overshoot is built into arrows/labels.
- Mechanical timing: blades and triggers snap (3–5 frames), pistons and springs compress over 6–10 frames with a small overshoot, gears rotate continuously at a constant rate (linear interpolation), liquids pour over 15–30 frames.
- Growth/flow: `zdf.make_tube(...)` + `zdf.grow_tube(tube, start, end)` for signals travelling, veins appearing, airflow paths.
- Visibility for a part of a shot: `zdf.show_between(obj, start, end)`.

## 4. Mixamo characters
Files live in `assets_library/mixamo/` (and the user's own uploads). Download from mixamo.com as **FBX Binary**; the character "With Skin", animations "Without Skin" are fine (same skeleton). Tick **In Place** for walks/runs when the character should stay on its mark.
```python
arm = zdf.import_mixamo_character(r".../Remy.fbx", r".../Talking.fbx", location=(0, 0, 0),
                                  rotation_z=0.0, start_frame=ctx["start_frame"], target_height=1.75,
                                  name="Presenter", collection=col)
zdf.add_mixamo_animation(arm, r".../Pointing.fbx", start_frame=beat_frame, blend_in=8)   # cross-fade
zdf.add_mixamo_animation(arm, r".../Walking.fbx", start_frame=f, in_place=True, speed=1.0, repeat=2)
```
- Scale is normalised to `target_height` with feet at `location`; bone prefixes (`mixamorig:` vs `mixamorig1:`) are remapped automatically; each clip is an NLA strip on its own track, holding its last pose.
- Pick clips that act the narration: talking for explanations, pointing at the hero prop, shocked/head-shake reactions for the sting, sitting + phone for meta-loop endings, walking in/out for transitions.
- Brand the presenter: `zdf.brand_tshirt(torso_mesh, chest_location)`.
- Faces matter in ZDF: frame characters from chest up for reactions, use 50 mm, f/2.8, and push in slowly.

## 5. Shot recipes from the references
- **Pour / process (tabletop):** `sky_gradient`, walnut table, hero vessel centre-low, `slide` or `push_in` at 15–25° elevation, label sign pops when the ingredient is named.
- **Inside-the-body reveal:** `cyan_studio`, presenter face push-in → match-cut to skull/anatomy model at the same framing → `cutaway_layers` slide → outlined arrows show the force.
- **Mechanism in a body part:** cutaway finger/arm with the machine inside, `orbit` 30°, hero part tinted neon/yellow when named, sparks/flame on the payoff.
- **Payoff ending:** presenter (branded shirt) demonstrates the result to camera, `push_in`, or meta-loop: phone (`create_phone_with_screen`) showing the video.
- **Cosmic / abstract:** `dark_space`, slow `pull_back`, glowing chains/links or a single bright point.

## 6. Rendering
- Look-dev and previews: EEVEE (fast). Finals: Cycles GPU (OptiX) 64–128 samples with denoising. Colour: Khronos PBR Neutral (set by `init_zdf_studio`).
- Motion blur on for fast mechanical action shots only.
