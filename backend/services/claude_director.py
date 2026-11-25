from __future__ import annotations

import json
import re
from typing import Any, Optional

import anthropic

from config import (
    DEFAULT_CLAUDE_MODEL,
    SKILL_PATH,
    ZDF_HELPERS_DOC_PATH,
    get_model_pricing,
)
from database import get_settings, log_token_usage


def _load_text(path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def _compute_cost_usd(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
) -> float:
    pricing = get_model_pricing(model_id)
    cost = (
        (input_tokens / 1_000_000) * pricing["input_per_mtok"]
        + (output_tokens / 1_000_000) * pricing["output_per_mtok"]
        + (cache_creation_tokens / 1_000_000) * pricing["cache_write_per_mtok"]
        + (cache_read_tokens / 1_000_000) * pricing["cache_read_per_mtok"]
    )
    return round(cost, 6)


def _extract_json_block(text: str) -> dict[str, Any]:
    text = text.strip()
    # Try fenced json block first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Fallback: locate first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("Claude response did not contain a valid JSON object.")


def _extract_python_code(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:python|py)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


class ClaudeDirector:
    """
    Token-saving stateless Claude AI Director using Anthropic Prompt Caching
    (`cache_control: {"type": "ephemeral"}`) on `stick_knowledge_3d_skill.md`
    and `zdf_helpers_api_doc.md`.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.get("anthropic_api_key", "")
        self.model = model or settings.get("claude_model") or DEFAULT_CLAUDE_MODEL

    def _client(self) -> anthropic.Anthropic:
        if not self.api_key:
            raise ValueError(
                "Anthropic API key is not configured. Open Settings in the sidebar to add your Claude API key."
            )
        return anthropic.Anthropic(api_key=self.api_key)

    def _cached_system_blocks(self, include_api_doc: bool = True) -> list[dict[str, Any]]:
        skill_text = _load_text(SKILL_PATH)
        blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": skill_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if include_api_doc:
            api_doc = _load_text(ZDF_HELPERS_DOC_PATH)
            if api_doc:
                blocks.append(
                    {
                        "type": "text",
                        "text": api_doc,
                        "cache_control": {"type": "ephemeral"},
                    }
                )
        return blocks

    def _call_claude(
        self,
        *,
        project_id: Optional[str],
        operation: str,
        user_prompt: str,
        include_api_doc: bool = True,
        max_tokens: int = 4096,
        temperature: float = 0.4,
    ) -> tuple[str, dict[str, Any]]:
        client = self._client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": self._cached_system_blocks(include_api_doc=include_api_doc),
            "messages": [{"role": "user", "content": user_prompt}],
        }
        # anthropic SDK v2.x removed `temperature` from Messages.create; pass only if supported
        import inspect
        if "temperature" in inspect.signature(client.messages.create).parameters:
            kwargs["temperature"] = temperature
        response = client.messages.create(**kwargs)
        text_parts = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        full_text = "\n".join(text_parts).strip()

        usage = response.usage
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cache_creation_tokens = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        cache_read_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)

        cost_usd = _compute_cost_usd(
            self.model,
            input_tokens,
            output_tokens,
            cache_creation_tokens,
            cache_read_tokens,
        )
        usage_record = log_token_usage(
            project_id=project_id,
            operation=operation,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            cost_usd=cost_usd,
        )
        return full_text, usage_record

    def create_or_update_director_plan(
        self,
        *,
        project_id: str,
        user_message: str,
        existing_storyboard: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        """
        Generates a fresh structured JSON Director Plan or applies a surgical edit
        to an existing storyboard based on a conversational follow-up prompt.
        Returns (storyboard_dict, assistant_summary, usage_record).
        """
        is_edit = bool(existing_storyboard and existing_storyboard.get("scenes"))

        schema_instruction = """
Return ONLY valid JSON inside a ```json ... ``` block matching this exact structure:
{
  "assistant_reply": "Concise 2-4 sentence summary of the plan or edits made, highlighting the hook, scene count, and STICK KNOWLEDGE diegetic placement.",
  "affected_scenes": [1, 2],
  "storyboard": {
    "title": "Short punchy title",
    "hook": "The exact 0-2s opening line",
    "total_duration_sec": 36.0,
    "fps": 30,
    "full_narration": "Complete narration combining all scenes in exact order.",
    "branding_placement": {
      "mode": "prop_wrap",
      "target_object": "battery_label",
      "scene_index": 2,
      "description": "Printed cleanly as a crisp wrap label on the coin battery casing."
    },
    "scenes": [
      {
        "scene_index": 1,
        "title": "Immediate Hook",
        "narration": "If you swallow a tiny coin battery, your saliva starts a dangerous reaction within seconds.",
        "duration_sec": 3.5,
        "bg_mode": "cyan_studio",
        "visual_description": "Macro hero shot of a glossy metallic coin battery resting on a warm wood studio surface, then lifting smoothly toward a stylized cutaway profile.",
        "camera_move": "Smooth macro dolly push-in with shallow f/2.4 DoF",
        "overlays": ["3d_arrow:red_downward_pressure", "3d_label:3V LITHIUM"],
        "cutaway_needed": false,
        "has_branding": false,
        "branding_note": "",
        "assets": [
          {
            "asset_id": "coin_battery",
            "query": "coin battery",
            "category": "prop"
          }
        ]
      }
    ]
  }
}

STRICT RULES:
- Total runtime MUST be 30–55 seconds (10–18 crisp scenes, each 1.8–3.5 seconds long so cuts happen every 1.5–3.0s).
- Zero intros/greetings. Open word 1 with a second-person or imperative hook.
- Default `bg_mode` is `"cyan_studio"`. Only use `"dark_space"` for space, microscopic, neural, or dark-room scenes.
- `branding_placement.mode` MUST be one of: `"tshirt"`, `"prop_wrap"`, `"screen_ui"`, `"engraved"`. At least ONE scene MUST have `has_branding: true` matching `branding_placement.scene_index`.
- Keep asset queries concise (1–3 words) and `category` in `["prop", "anatomy", "character", "material", "hdri"]`.
- `full_narration` MUST equal the space-joined `narration` of all scenes.
"""

        if is_edit:
            prompt = (
                "You are editing an EXISTING Stick Knowledge 3D Short storyboard.\n"
                "Apply ONLY the user's requested changes while keeping unaffected scenes intact "
                "(preserve existing `asset_id`s and resolved fields on unchanged scenes).\n"
                "List ONLY the 1-based scene indices you modified in `affected_scenes`.\n\n"
                f"CURRENT STORYBOARD JSON:\n{json.dumps(existing_storyboard, indent=2)}\n\n"
                f"USER EDIT REQUEST:\n{user_message}\n\n"
                f"{schema_instruction}"
            )
            op_name = "edit_director_plan"
        else:
            prompt = (
                "Create a complete, viral Zack D. Films-style 9:16 3D explainer Short Director Plan "
                "for the following user request.\n"
                "Set `affected_scenes` to the list of all scene indices.\n\n"
                f"USER REQUEST:\n{user_message}\n\n"
                f"{schema_instruction}"
            )
            op_name = "create_director_plan"

        raw_text, usage = self._call_claude(
            project_id=project_id,
            operation=op_name,
            user_prompt=prompt,
            include_api_doc=False,
            max_tokens=4096,
            temperature=0.45,
        )
        parsed = _extract_json_block(raw_text)
        sb = parsed.get("storyboard", parsed)
        assistant_reply = parsed.get("assistant_reply") or "Director plan generated successfully."
        affected_scenes = parsed.get("affected_scenes") or [
            s["scene_index"] for s in sb.get("scenes", [])
        ]

        # Normalize frame timings (will be re-locked 1:1 once ElevenLabs timestamps are generated)
        fps = int(sb.get("fps", 30))
        cursor_sec = 0.0
        full_parts: list[str] = []
        for idx, s in enumerate(sb.get("scenes", []), start=1):
            s["scene_index"] = idx
            dur = float(s.get("duration_sec", 2.8))
            dur = max(1.2, min(8.0, dur))
            s["duration_sec"] = round(dur, 2)
            s["start_sec"] = round(cursor_sec, 3)
            s["end_sec"] = round(cursor_sec + dur, 3)
            s["start_frame"] = max(1, round(cursor_sec * fps) + 1)
            s["end_frame"] = max(s["start_frame"] + 10, round((cursor_sec + dur) * fps))
            cursor_sec += dur
            full_parts.append(str(s.get("narration", "")).strip())

            # Normalize asset entries
            norm_assets = []
            for a_idx, a in enumerate(s.get("assets", []), start=1):
                if isinstance(a, str):
                    norm_assets.append(
                        {
                            "asset_id": f"s{idx}_asset_{a_idx}",
                            "query": a,
                            "category": "prop",
                            "status": "pending",
                        }
                    )
                else:
                    a.setdefault("asset_id", f"s{idx}_asset_{a_idx}")
                    a.setdefault("category", "prop")
                    a.setdefault("status", "pending")
                    norm_assets.append(a)
            s["assets"] = norm_assets
            s.setdefault("bg_mode", "cyan_studio")
            s.setdefault("overlays", [])
            s.setdefault("cutaway_needed", False)
            s.setdefault("has_branding", False)
            s.setdefault("branding_note", "")
            s.setdefault("render_status", "idle")

        sb["total_duration_sec"] = round(cursor_sec, 2)
        sb["full_narration"] = " ".join(p for p in full_parts if p)
        sb["affected_scenes"] = affected_scenes

        return sb, assistant_reply, usage

    def generate_scene_script(
        self,
        *,
        project_id: str,
        scene: dict[str, Any],
        branding_placement: dict[str, Any],
        edit_instruction: Optional[str] = None,
        existing_code: Optional[str] = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Generates a single isolated, self-contained modular scene Python script (`scene_XX.py`)
        calling `zdf_helpers` cleanly. Stateless per-scene call keeps token usage minimal!
        """
        scene_idx = scene["scene_index"]
        prompt_parts = [
            f"Write the complete, bug-free Blender Python (`bpy`) module for Scene {scene_idx:02d}.",
            "It MUST define `def build_scene(ctx: dict) -> dict:` and use `import zdf_helpers as zdf`.",
            "REQUIREMENTS:",
            "1. Start by calling `col = zdf.setup_scene_collection(ctx['scene_index'], ctx['start_frame'], ctx['end_frame'])`.",
            "2. Call `zdf.set_studio_bg_keyframe(ctx.get('bg_mode', 'cyan_studio'), ctx['start_frame'])`.",
            "3. For every asset in `ctx['assets']`, try `zdf.import_and_normalize_asset(ctx['assets'].get('<asset_id>'), ...)` and ALWAYS include an `if obj is None:` fallback using `zdf.create_procedural_prop(...)` so the scene builds richly even if an external file is missing.",
            "4. Apply semi-realistic PBR materials via `zdf.create_pbr_material(...)` and `zdf.assign_material(...)`.",
            "5. If `cutaway_needed` is true, use `zdf.apply_animated_cutaway(...)`.",
            "6. Implement the listed 3D explainer overlays (`add_3d_arrow`, `add_3d_chevron_flow`, `add_3d_x_mark`, `add_3d_airflow_streaks`, `add_3d_energy_arc`, `add_3d_sparks`, `add_3d_label_sign`) keyframed smoothly inside `[start_frame, end_frame]`.",
            "7. If `has_branding` is true, MUST call `zdf.create_branding_decal(text='STICK KNOWLEDGE', ...)` visibly placed in-camera on the hero 3D element!",
            "8. Set up smooth Bezier camera motion via `cam = zdf.setup_cinematic_camera(...)` framed specifically for 9:16 vertical Shorts (middle 60% vertical safe zone).",
            "9. Call `zdf.finalize_scene_visibility(col, ctx['start_frame'], ctx['end_frame'])` BEFORE returning.",
            "10. Return `{'camera': cam, 'collection': col, 'preview_frame': int((ctx['start_frame'] + ctx['end_frame']) // 2)}`.",
            "11. Output ONLY clean Python code inside a ```python ... ``` block. Compatible with Blender 4.2 through 5.3+.",
            "",
            f"SCENE SPECIFICATION:\n{json.dumps(scene, indent=2)}",
            f"GLOBAL DIEGETIC BRANDING PLACEMENT:\n{json.dumps(branding_placement, indent=2)}",
        ]

        if edit_instruction and existing_code:
            prompt_parts.append(f"\nEXISTING SCRIPT TO UPDATE:\n```python\n{existing_code}\n```")
            prompt_parts.append(f"\nSPECIFIC EDIT REQUEST:\n{edit_instruction}")

        raw, usage = self._call_claude(
            project_id=project_id,
            operation=f"generate_scene_{scene_idx:02d}",
            user_prompt="\n".join(prompt_parts),
            include_api_doc=True,
            max_tokens=3072,
            temperature=0.25,
        )
        return _extract_python_code(raw), usage

    def self_heal_script(
        self,
        *,
        project_id: str,
        script_name: str,
        broken_code: str,
        error_traceback: str,
    ) -> tuple[str, dict[str, Any]]:
        """Automatic 1-retry Claude self-heal when headless Blender raises a bpy exception."""
        prompt = (
            f"The Blender Python script `{script_name}` raised an error in headless Blender 5.x/4.x.\n"
            "Fix the bug cleanly while preserving the exact visual intent and `build_scene(ctx)` signature.\n"
            "Return ONLY the fixed Python file inside a ```python ... ``` block.\n\n"
            f"ERROR TRACEBACK:\n```\n{error_traceback[-3000:]}\n```\n\n"
            f"CURRENT CODE:\n```python\n{broken_code}\n```"
        )
        raw, usage = self._call_claude(
            project_id=project_id,
            operation=f"self_heal_{script_name}",
            user_prompt=prompt,
            include_api_doc=True,
            max_tokens=3072,
            temperature=0.15,
        )
        return _extract_python_code(raw), usage
