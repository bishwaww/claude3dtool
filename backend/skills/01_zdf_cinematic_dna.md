# 01 · Zack D. Films Cinematic DNA (measured from 4 reference Shorts)

This skill is distilled from frame-by-frame analysis of four reference Shorts (milk knife, mouth breathing, finger gun, "was there ever a beginning"): contact sheets every 1.25 s, word-level transcripts, pixel colour samples, caption measurements. Treat the numbers as targets, not suggestions.

## 1. Format
- 1080x1920 (9:16), 30 fps, 30–35 s typical (one essay-style piece ran 66 s). Never add an intro, title card, logo sting or outro card.
- Narration starts on frame 1 (measured 0.00 s in all four). The first visual is already the subject in action.

## 2. Script formulas (what the four scripts actually do)
Pick one formula per video:
1. **Imperative procedure (how-to / absurd procedure).** Second person, chained steps: "Pour in the milk, then mix in this type of acid. When the milk curdles, strain out the solids…", "Insert a sealed metal chamber into your fingertip and add a special blade as well as this tiny pump…". Ends with a payoff clause: "…to give you a milk knife that can cut through fruit", "…giving you a finger gun that actually works."
2. **"If you X…" consequence chain.** "If you breathe through your mouth instead of your nose, as you grow up, your tongue can start resting lower…". Each sentence is the cause of the next ("So without that support…", "which can shift…"). Ends on a personal, slightly funny sting: "And by the time you're an adult, well, you'll wish you'd seen this video."
3. **Backwards causal chain (essay).** Starts from the viewer's present moment ("If you're watching this video, it's because your finger swiped here.") and walks back link by link to a big idea. Ends on an open, unsettling line.

Measured voice: 150–187 words per minute (aim for ~175), ~90–100 words per 30 s. Sentences are long and joined with "and / then / which / while / so / because"; pauses longer than 0.35 s happen only 2–4 times per video. Plain words, no jargon without an on-screen picture of it. Never "Hey guys", "In this video", "Subscribe".

## 3. Shot rhythm
- The picture changes every **1.25–2.5 s** (one change per caption phrase). Changes are usually a continuous camera move landing on a new composition, a match-cut on the same object, or a hard cut — not cross-dissolves.
- Every shot moves: slow push-in, orbit, crane, slide or a macro creep. A static frame never lasts more than ~1.5 s.
- Each narrated noun gets its own picture at the moment it is said ("acetic acid" → bottle label pours; "ethanol" → label sign appears). Lock these beats to word timestamps.
- Ending patterns seen: hero payoff (character proudly demonstrates the result), meta-loop (character watching a phone that shows this video / the narrator character), zoom-out to cosmic scale, or comedic reaction.

## 4. Look — backdrops (exact measured colours)
| bg_mode | Use for | Measured colours |
|---|---|---|
| `cyan_studio` | default "studio" shots, anatomy, mechanisms, characters | radial glow centre `#9BDAF0` (slightly above frame centre) to edges/corners `#31B9E6` |
| `sky_gradient` | tabletop / kitchen shots, objects on a walnut table | top `#52ABFB` fading to horizon `#ACD6FE` just above the table line |
| `dark_space` | cosmos, microscopic, neurons, dark mood | deep navy centre `#0F1B2D` to near-black `#03060B` |
| `interior` | real rooms (living room, lab, power lines, forest) — the set fills the frame | neutral ambient |

The backdrop is locked to the FRAME (camera-ray world shader), so it looks identical from any camera angle; there is no visible floor or horizon in studio shots. Objects float in front of it or rest on a walnut tabletop. Colour pipeline: **Khronos PBR Neutral** view transform (measured: AgX desaturates the reference cyan to `#7AB8E1`, so it is not used by default).

## 5. Look — lighting & lensing
- Bright, soft, shadow-light studio lighting: big soft key from front-left/above, cool fill, a crisp rim separating subjects from the blue. Contact shadows on the table are soft and short.
- Macro is everywhere: extreme close-ups with shallow depth of field (f/1.8–2.8), foreground objects blurred, focus on the action (blade edge, fingertip, bubbles).
- Lenses: 35–50 mm for people and mid shots, 50–85 mm for products, 100 mm-equivalent framing for macro. Slight dutch angles on dramatic mechanism shots.
- The subject sits in the middle 60 % of the frame height; the top 12 % stays clear of Shorts UI and captions own the band at ~78 % height.

## 6. Look — materials (what makes it "realistic cinematic")
- **Skin:** warm, subsurface-scattered, slightly glossy, visible pores at macro, red-pink inner tones at cut edges.
- **Anatomy cutaways:** clean flat cross-section caps. Layers read outside-in: thin skin rim → glossy dark-red striated or spongy muscle → off-white bone with fine red capillary veins → tooth enamel/cartilage. Organs and airways get glossy wet highlights.
- **Mechanisms:** worn gunmetal with edge wear, brass gears, polished steel blades with a blue edge reflection, springs, rubber hoses, PCB green with gold traces. Mechanisms are built INTO bodies (gun in a finger) with the cutaway showing both.
- **Everyday props:** glazed ceramic bowls (often red), stainless strainers, non-stick pans, milk cartons, wooden spatulas, cutting boards, sandpaper/whetstones. Liquids are glossy, slightly translucent, with steam and bubbles when hot.
- **Neon accents:** one saturated hero colour per video (neon-green silicone cap, yellow highlight on a part) to point at the important object.

## 7. In-scene 3D explainers (all exist as helpers)
- Chunky **flat arrows with a thick black outline** — red `#E5321F` for force/pressure, pale blue `#A9C8F5` for gentle pressure/flow, yellow for highlights. They pop in one after another and nudge in their direction (`add_outlined_arrow`, `add_arrow_row`).
- **Red X marks** over blocked airways / wrong actions (`add_3d_x_mark`).
- **White/blue `>>` chevrons** showing direction of growth or flow (`add_3d_chevron_flow`).
- **White wispy airflow streaks** in and out of mouths and noses (`add_3d_airflow_streaks`).
- **Blue electric arcs / glowing nerve signals** travelling along arms or brains (`add_3d_energy_arc`, `make_tube` + `grow_tube` with `glow_cyan`).
- **White label signs on a thin pin** naming a liquid or part: "WATER", "ETHANOL", "ACETIC ACID" (`add_3d_label_sign`).
- **Orange sparks** when grinding/sanding, **steam** over boiling pots, **yellow light rays** for vision.
- Highlight a part by tinting it a flat colour (the chamber turns yellow, the cap turns neon green) instead of adding text.

## 8. Captions
White heavy rounded sans, ~80 px at 1080 wide, thin dark edge plus soft drop shadow, centred horizontally with the centre ~78 % down the frame. 2–3 words per caption, phrase-chunked, no word-by-word colour highlight, no emojis. (The assembler renders these — do not model text captions in Blender.)

## 9. Branding — diegetic only
The reference channel never uses a corner watermark; its name is printed on things in the world: a pan's side, a soda can, a T-shirt chest, a phone screen, a chip label. For this studio the brand is **STICK KNOWLEDGE** (handle `@stickknowledge`, or the user's logo). At least one hero surface per video carries it and it is readable for ≥2 s:
- T-shirt chest print on the presenter (`brand_tshirt`), can/bottle/mug label (`create_branded_can`, `create_branding_decal(mode="prop_wrap")`), phone screen at the meta-loop ending (`create_phone_with_screen`), engraved on a tool (`mode="engraved"`).

## 10. Storyboard translation checklist
For every scene ask: Which noun is being said? What single picture shows it? Which camera move reveals it? Which explainer graphic makes the invisible visible? Is there a hero colour? Does the shot change within 2.5 s? Is the brand visible somewhere in the video?
