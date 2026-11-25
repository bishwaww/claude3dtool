"""
Integration test for the zdf_helpers pro toolkit. Builds three ZDF-style shots in one
timeline, renders a preview of each, saves the .blend, and prints PASS/FAIL checks.

blender --background --factory-startup --python tools/showcase_test.py -- <out_dir> [mixamo_char.fbx] [mixamo_anim.fbx]
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bpy  # noqa: E402
import zdf_helpers as zdf  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(argv[0] if argv else ".").resolve()
CHAR = argv[1] if len(argv) > 1 else None
ANIM = argv[2] if len(argv) > 2 else None
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


try:
    zdf.configure(project_dir=str(OUT), assets_dir=str(OUT / "assets"))
    zdf.init_zdf_studio(render_engine="EEVEE_NEXT", bg_mode="sky_gradient")
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 180
    check("view transform", scene.view_settings.view_transform == zdf.VIEW_TRANSFORM, scene.view_settings.view_transform)

    # ---------- Shot A: tabletop (sky gradient) ----------
    colA = zdf.setup_scene_collection(1, 1, 60)
    zdf.set_studio_bg_keyframe("sky_gradient", 1)
    zdf.add_studio_tabletop(size=(2.0, 1.2, 0.06), location=(0, 0.2, -0.03), collection=colA)
    bowl = zdf.make_lathe([(0.0, 0.0), (0.05, 0.0), (0.06, 0.004), (0.085, 0.03), (0.105, 0.075), (0.112, 0.085), (0.114, 0.088)],
                          segments=64, thickness=0.006, name="Bowl", material=zdf.create_pbr_material("ceramic_glazed"), collection=colA)
    milk = zdf.make_lathe([(0.0, 0.07), (0.103, 0.07)], segments=64, cap_bottom=False, subsurf=1, name="MilkSurface",
                          material=zdf.create_pbr_material("milk"), collection=colA)
    can = zdf.create_branded_can(location=(0.24, 0.06, 0.0), collection=colA)
    zdf.add_arrow_row((-0.09, -0.12, 0.14), (0.09, -0.12, 0.14), count=3, direction=(0, 0, 1), facing=(0, -1, 0.2),
                      length=0.06, color="#E5321F", start_frame=10, collection=colA)
    camA = zdf.make_shot("push_in", (0.12, 0.04, 0.07), 1, 60, distance=0.95, elevation_deg=16, lens=45, fstop=2.8, collection=colA, name="CamA")
    zdf.finalize_scene_visibility(colA, 1, 60)
    zdf.bind_camera_marker(scene, camA, 1, "A")
    check("lathe has UVs", len(bowl.data.uv_layers) > 0)
    check("can label texture", any(n.type == "TEX_IMAGE" for m in can.data.materials for n in m.node_tree.nodes))

    # ---------- Shot B: layered finger cutaway (cyan studio) ----------
    colB = zdf.setup_scene_collection(2, 61, 120)
    zdf.set_studio_bg_keyframe("cyan_studio", 61)
    finger = [(0.0, 0.0), (0.05, 0.0), (0.085, 0.02), (0.09, 0.1), (0.09, 0.42), (0.08, 0.5), (0.05, 0.545), (0.0, 0.555)]
    skin = zdf.make_lathe(finger, name="FingerSkin", material=zdf.create_pbr_material("skin_realistic"), collection=colB)
    muscle = zdf.make_lathe([(r * 0.86, z * 0.97 + 0.008) for r, z in finger], name="FingerMuscle",
                            material=zdf.create_pbr_material("tissue_spongy"), collection=colB)
    bone = zdf.make_lathe([(0.0, 0.04), (0.035, 0.045), (0.04, 0.07), (0.03, 0.12), (0.03, 0.4), (0.042, 0.45), (0.035, 0.48), (0.0, 0.485)],
                          name="FingerBone", material=zdf.create_pbr_material("bone_veined"), collection=colB)
    for o in (skin, muscle, bone):
        o.rotation_euler = (0, 1.5708, 0)
        o.location = (-0.27, 0, 0.25)
    zdf.cutaway_layers([(skin, zdf.create_pbr_material("skin_realistic", name="SkinCap", base_color=zdf.hex_to_linear("#E8B9A6"))),
                        (muscle, zdf.create_pbr_material("tissue_spongy")),
                        (bone, zdf.create_pbr_material("bone_veined"))],
                       cutter_size=(1.0, 0.4, 1.0), cutter_location=(0, -0.2, 0.25), start_frame=62, end_frame=80, collection=colB)
    chamber = zdf.make_lathe([(0.0, 0.0), (0.026, 0.0), (0.028, 0.004), (0.028, 0.15), (0.024, 0.155), (0.0, 0.155)],
                             subsurf=1, name="Chamber", material=zdf.create_pbr_material("gunmetal_worn"), collection=colB)
    chamber.rotation_euler = (0, 1.5708, 0)
    chamber.location = (-0.02, 0.01, 0.25)
    gear = zdf.create_procedural_prop("gear", name="Gear", location=(0.16, -0.02, 0.32), scale=(0.05, 0.05, 0.05),
                                      material=zdf.create_pbr_material("brass"), collection=colB)
    camB = zdf.make_shot("orbit", (0.0, 0.0, 0.25), 61, 120, distance=0.75, elevation_deg=22, sweep_deg=30, lens=50, fstop=2.4,
                         collection=colB, name="CamB")
    zdf.finalize_scene_visibility(colB, 61, 120)
    zdf.bind_camera_marker(scene, camB, 61, "B")
    check("cutaway booleans", all(any(m.type == "BOOLEAN" for m in o.modifiers) for o in (skin, muscle, bone)))

    # ---------- Shot C: Mixamo character + phone (interior / cyan) ----------
    colC = zdf.setup_scene_collection(3, 121, 180)
    zdf.set_studio_bg_keyframe("cyan_studio", 121)
    target = (0, 0, 1.45)
    if CHAR:
        arm = zdf.import_mixamo_character(CHAR, ANIM, location=(0, 0, 0), start_frame=121, target_height=1.75,
                                          name="Presenter", collection=colC)
        check("mixamo armature", arm is not None and arm.type == "ARMATURE")
        if arm is not None:
            strips = [s for t in arm.animation_data.nla_tracks for s in t.strips]
            check("mixamo NLA strip", len(strips) >= 1, f"strips={[(s.name, s.frame_start, s.frame_end) for s in strips]}")
            meshes = [o for o in bpy.data.objects if o.parent == arm and o.type == "MESH"]
            zmin, zmax = zdf._world_bbox_z(meshes)
            check("mixamo height ~1.75 m", abs((zmax - zmin) - 1.75) < 0.05, f"{zmax - zmin:.3f} m, feet z={zmin:.3f}")
            if ANIM:
                s2 = zdf.add_mixamo_animation(arm, ANIM, start_frame=150, blend_in=8, in_place=True, name="Talk2")
                check("second clip blended", s2 is not None and s2.blend_in > 0)
    phone = zdf.create_phone_with_screen(location=(0.22, -0.45, 1.15), rotation=(-0.25, 0, 0.3), collection=colC)
    camC = zdf.make_shot("push_in", target, 121, 180, distance=1.9, elevation_deg=2, lens=50, fstop=2.8, collection=colC, name="CamC")
    zdf.finalize_scene_visibility(colC, 121, 180)
    zdf.bind_camera_marker(scene, camC, 121, "C")
    check("phone screen image", any(n.type == "TEX_IMAGE" for c in phone.children for m in c.data.materials for n in m.node_tree.nodes))

    blend = OUT / "showcase.blend"
    zdf.pack_and_save_project(str(blend))
    check("saved blend", blend.is_file())
    for frame, cam, tag in ((45, camA, "A_tabletop"), (100, camB, "B_cutaway"), (170, camC, "C_character")):
        png = OUT / f"preview_{tag}.png"
        zdf.render_scene_preview(frame, str(png), camera_obj=cam, preview_scale_pct=50)
        check(f"render {tag}", png.is_file())
except Exception:
    traceback.print_exc()
    results.append(("exception", False))

failed = [n for n, ok in results if not ok]
print(f"SHOWCASE RESULT: {len(results) - len(failed)}/{len(results)} passed" + (f"; failed: {failed}" if failed else ""))
