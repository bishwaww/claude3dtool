# Stick Knowledge 3D Studio

A local, Claude Desktop-inspired AI Chat & Automated 3D Explainer Production Suite that generates Zack D. Films-style vertical (9:16, 1080×1920, 30fps) 3D explainer Shorts end-to-end inside **Blender** (`4.2–5.3+`), powered by the **Anthropic Claude API** (with Prompt Caching), **ElevenLabs API** (with word-level timestamps), **FFmpeg** (with crisp Shorts ASS captions), and a **100% free 6-tier 3D asset pipeline**.

## Quick Start

1. Double-click `start_studio.bat` (or run `.\start_studio.ps1`).
2. Open **http://localhost:5173**.
3. Open **Studio Settings** in the bottom-left sidebar:
   - Enter your **Anthropic Claude API Key** and choose your model (default: `claude-sonnet-4-5`).
   - Enter your **ElevenLabs API Key** and select/preview a narrator voice.
   - Verify your auto-detected **Blender** executable (`D:\B Software LK\blender.exe`) and click **Install/Sync BlenderKit into Blender** (`D:\B Software LK\blender.crt\blenderkit`).
   - Choose `EEVEE Next (Fast)` or `Cycles GPU OptiX (Cinematic)`.
4. Enter your **Target Output Folder** in the sidebar (e.g. `D:\Videos\StickKnowledge\Ep01`) and describe your 3D explainer Short in chat.

## Project Output Folder Structure

Every project saves all files cleanly inside your chosen `<user_target_folder>`:
```text
<user_target_folder>/
├── project.blend              # Complete, editable, packed Blender project
├── project_meta.json          # Script, storyboard, timestamps, resolved assets & token cost log
├── scripts/
│   ├── master_build.py        # Full reproducible bpy build script
│   └── scene_01.py ...        # Modular per-scene scripts
├── assets/                    # BlenderKit .blend, Poly Haven, Mixamo, NIH 3D, STICK KNOWLEDGE decals
├── audio/
│   ├── narration.mp3          # ElevenLabs voiceover
│   └── timestamps.json        # Word-level alignment data
├── previews/                  # Fast per-scene preview PNGs
├── renders/                   # Rendered scene frames & ASS subtitles
└── final_short.mp4            # Final 1080x1920 H.264 YouTube Short with audio & captions
```

## Free 6-Tier 3D Asset Pipeline
1. **BlenderKit Free** — Native `.blend` models & PBR shaders + local add-on sync from `D:\B Software LK\blender.crt\blenderkit`.
2. **Poly Haven Live API** — CC0 3D models, PBR textures, and studio HDRIs (zero auth required).
3. **Local Mixamo & Custom Library** — Drop rigged `.fbx`/`.glb` characters into `assets_library/mixamo/` (+ automatic MPFB2 detection).
4. **NIH 3D Anatomy** — Open-access `.glb` anatomical meshes cached in `assets_library/anatomy/`.
5. **Hugging Face Free AI 3D Fallback** — `gradio_client` targeting `tencent/Hunyuan3D-2` / `microsoft/TRELLIS`.
6. **Procedural `bpy` Fallback** — High-quality procedural geometry so builds never fail.
