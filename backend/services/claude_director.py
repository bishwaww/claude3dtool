"""
Claude 3D Director — streaming, tool-using chat agent.

Why this file was rewritten
---------------------------
The previous version asked Claude to answer with a big storyboard JSON inside free
text and ran `json.loads()` on whatever came back. Any unescaped quote in a
narration line, or a response cut off at `max_tokens=4096` on a 15-scene plan,
raised `json.decoder.JSONDecodeError: Expecting ',' delimiter`.

Now Claude chats normally (streamed token by token, like Claude Desktop) and
changes project state only through *tool calls*. Tool inputs are parsed by the
Anthropic SDK, validated with Pydantic, and a bad input is returned to Claude as
an `is_error` tool_result so it corrects itself — nothing in this module calls
`json.loads()` on model text.

Later phases register more tools (live Blender bridge, assets, voiceover) on the
same `ToolRegistry`, so the agent loop below does not change.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, Optional, Union

import anthropic
from pydantic import BaseModel, Field, ValidationError

from config import BACKEND_DIR, DEFAULT_CLAUDE_MODEL, ZDF_HELPERS_DOC_PATH, get_model_pricing
from database import get_messages, get_project, get_settings, log_token_usage, update_project
from services.model_catalog import FALLBACK_BETA, is_legacy, request_options, supports_fallbacks

SKILLS_DIR = BACKEND_DIR / "skills"
MAX_AGENT_ITERATIONS = 40
MAX_HISTORY_MESSAGES = 60

Emit = Callable[[dict[str, Any]], Awaitable[None]]
ToolOutput = Union[str, list[dict[str, Any]]]


# ==============================================================================
# Cost tracking
# ==============================================================================

def compute_cost_usd(model_id: str, inp: int, out: int, cache_write: int, cache_read: int) -> float:
    p = get_model_pricing(model_id)
    cost = (
        inp * p["input_per_mtok"]
        + out * p["output_per_mtok"]
        + cache_write * p["cache_write_per_mtok"]
        + cache_read * p["cache_read_per_mtok"]
    ) / 1_000_000
    return round(cost, 6)


def _usage_record(project_id: Optional[str], operation: str, model: str, usage: Any) -> dict[str, Any]:
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    cw = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    return log_token_usage(
        project_id=project_id,
        operation=operation,
        model=model,
        input_tokens=inp,
        output_tokens=out,
        cache_creation_tokens=cw,
        cache_read_tokens=cr,
        cost_usd=compute_cost_usd(model, inp, out, cw, cr),
    )


def _sum_usage(records: list[dict[str, Any]], model: str) -> dict[str, Any]:
    keys = ("input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens")
    total = {k: sum(int(r.get(k, 0)) for r in records) for k in keys}
    total["cost_usd"] = round(sum(float(r.get("cost_usd", 0)) for r in records), 6)
    total["model"] = model
    total["operation"] = "chat"
    total["api_calls"] = len(records)
    return total


# ==============================================================================
# Skills / system prompt (prompt-cached)
# ==============================================================================

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def load_skill_suite() -> str:
    """All backend/skills/*.md in filename order (01_..., 02_..., 03_...)."""
    parts = []
    for p in sorted(SKILLS_DIR.glob("*.md")):
        parts.append(f"<skill file=\"{p.name}\">\n{_read(p).strip()}\n</skill>")
    return "\n\n".join(parts)


DIRECTOR_PERSONA = """You are the Claude 3D Director inside "Stick Knowledge 3D Studio", a desktop app that produces Zack D. Films-style vertical 3D explainer Shorts (1080x1920, 30 fps) in Blender.

How to behave
- Talk with the user naturally, like Claude Desktop: answer questions, brainstorm hooks, explain trade-offs, ask a short clarifying question when the request is genuinely ambiguous. Use Markdown.
- The user may write in English, Sinhala, or Singlish (romanized Sinhala). Reply in the language they use; keep technical names (Blender, bpy, storyboard fields) in English.
- You change the project ONLY through tools. Never paste a storyboard JSON or Blender script into chat in place of a tool call.
  - New video idea, or a rewrite of most scenes → call `update_storyboard` with the complete storyboard.
  - Small edits to specific scenes → call `patch_scenes` with only the fields that change.
  - Need to see current state before editing → call `get_project_state`.
- After a tool call succeeds, give a short summary: hook, scene count, total runtime, where the STICK KNOWLEDGE branding sits, and what the user can do next (generate/upload voiceover, build in Blender).
- If a tool returns an error, read it, fix the input, and call the tool again. Do not give up after one validation error.

Storyboard rules
- Runtime 30–55 s, usually 10–18 scenes of 1.5–3.5 s so the picture changes every 1.5–3 s.
- No intro or greeting: word one of the narration is the hook (second person or imperative).
- `full_narration` is derived automatically from the scenes; do not worry about keeping it in sync.
- At least one scene has `has_branding: true`, matching `branding_placement.scene_index`. Branding is diegetic (printed on a T-shirt, a label, a phone screen, engraved), never a corner watermark.
- `bg_mode` is "cyan_studio" by default; use "dark_space" only for space, microscopic, neural or dark-room shots.
- Asset queries are 1–3 words; category is one of prop, anatomy, character, material, hdri.
"""


def build_system_blocks(project_state: str) -> list[dict[str, Any]]:
    """
    Stable blocks first (cached), volatile project state last (not cached), so the
    prefix tools → persona → skills → helpers doc stays byte-identical across turns.
    """
    blocks: list[dict[str, Any]] = [{"type": "text", "text": DIRECTOR_PERSONA}]
    skills = load_skill_suite()
    if skills:
        blocks.append({"type": "text", "text": skills})
    api_doc = _read(ZDF_HELPERS_DOC_PATH)
    if api_doc:
        blocks.append({"type": "text", "text": f"<zdf_helpers_api>\n{api_doc}\n</zdf_helpers_api>"})
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    blocks.append({"type": "text", "text": f"<current_project_state>\n{project_state}\n</current_project_state>"})
    return blocks


# ==============================================================================
# Storyboard schema, validation and normalization
# ==============================================================================

class AssetIn(BaseModel):
    asset_id: Optional[str] = None
    query: str
    category: Literal["prop", "anatomy", "character", "material", "hdri"] = "prop"


class SceneIn(BaseModel):
    title: str
    narration: str
    duration_sec: float = Field(2.8, ge=0.8, le=10.0)
    bg_mode: Literal["cyan_studio", "dark_space"] = "cyan_studio"
    visual_description: str
    camera_move: str = "Smooth slow dolly push-in with subtle macro DoF"
    overlays: list[str] = Field(default_factory=list)
    cutaway_needed: bool = False
    has_branding: bool = False
    branding_note: str = ""
    assets: list[AssetIn] = Field(default_factory=list)


class BrandingIn(BaseModel):
    mode: Literal["tshirt", "prop_wrap", "screen_ui", "engraved"] = "prop_wrap"
    target_object: str = ""
    scene_index: int = 1
    description: str = ""


class StoryboardIn(BaseModel):
    title: str
    hook: str
    branding_placement: BrandingIn = Field(default_factory=BrandingIn)
    scenes: list[SceneIn] = Field(min_length=1, max_length=40)


_SCENE_PROPS: dict[str, Any] = {
    "title": {"type": "string", "description": "Short scene title"},
    "narration": {"type": "string", "description": "Exact voiceover line(s) for this scene"},
    "duration_sec": {"type": "number", "description": "1.5–3.5 typical"},
    "bg_mode": {"type": "string", "enum": ["cyan_studio", "dark_space"]},
    "visual_description": {"type": "string", "description": "What the 3D shot shows: hero objects, materials, action, framing"},
    "camera_move": {"type": "string"},
    "overlays": {
        "type": "array",
        "items": {"type": "string"},
        "description": "In-scene 3D explainers, e.g. '3d_arrow:red_up', '3d_label:WATER', 'x_mark', 'airflow', 'energy_arc', 'sparks', 'chevrons'",
    },
    "cutaway_needed": {"type": "boolean"},
    "has_branding": {"type": "boolean"},
    "branding_note": {"type": "string"},
    "assets": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "query": {"type": "string"},
                "category": {"type": "string", "enum": ["prop", "anatomy", "character", "material", "hdri"]},
            },
            "required": ["query"],
        },
    },
}

STORYBOARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook": {"type": "string", "description": "The exact 0–2 s opening line"},
        "branding_placement": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["tshirt", "prop_wrap", "screen_ui", "engraved"]},
                "target_object": {"type": "string"},
                "scene_index": {"type": "integer", "description": "1-based scene index"},
                "description": {"type": "string"},
            },
            "required": ["mode", "scene_index"],
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": _SCENE_PROPS,
                "required": ["title", "narration", "duration_sec", "visual_description"],
            },
        },
    },
    "required": ["title", "hook", "branding_placement", "scenes"],
}

_RESOLVED_ASSET_FIELDS = ("resolved_source", "local_path", "display_name", "license", "status", "preferred_source")
_CONTENT_FIELDS = ("narration", "visual_description", "camera_move", "overlays", "cutaway_needed",
                   "has_branding", "branding_note", "bg_mode", "assets")


def _scene_signature(s: dict[str, Any]) -> dict[str, Any]:
    sig = {k: s.get(k) for k in _CONTENT_FIELDS if k != "assets"}
    sig["assets"] = [
        (a.get("asset_id"), a.get("query"), a.get("category")) if isinstance(a, dict) else (None, a, None)
        for a in (s.get("assets") or [])
    ]
    return sig


def normalize_storyboard(sb: dict[str, Any], previous: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Recompute timing/frames, normalize assets, and carry over resolved data from
    the previous version of the same scene. Scenes whose content changed are marked
    `script_stale` so the build regenerates their Blender script."""
    prev_scenes = {int(s.get("scene_index", i + 1)): s for i, s in enumerate((previous or {}).get("scenes", []))}
    fps = int(sb.get("fps") or 30)
    cursor = 0.0
    narr: list[str] = []
    for idx, s in enumerate(sb.get("scenes", []), start=1):
        s["scene_index"] = idx
        dur = round(max(0.8, min(10.0, float(s.get("duration_sec", 2.8)))), 2)
        s["duration_sec"] = dur
        s["start_sec"] = round(cursor, 3)
        s["end_sec"] = round(cursor + dur, 3)
        s["start_frame"] = max(1, round(cursor * fps) + 1)
        s["end_frame"] = max(s["start_frame"] + 10, round((cursor + dur) * fps))
        cursor += dur
        narr.append(str(s.get("narration", "")).strip())

        prev = prev_scenes.get(idx, {})
        prev_assets = {a.get("asset_id"): a for a in prev.get("assets", []) if isinstance(a, dict)}
        assets = []
        for a_idx, a in enumerate(s.get("assets", []), start=1):
            a = {"query": a} if isinstance(a, str) else dict(a)
            a["asset_id"] = a.get("asset_id") or f"s{idx}_asset_{a_idx}"
            a.setdefault("category", "prop")
            old = prev_assets.get(a["asset_id"])
            if old and old.get("query") == a.get("query"):
                for k in _RESOLVED_ASSET_FIELDS:
                    if old.get(k) is not None and k not in a:
                        a[k] = old[k]
            a.setdefault("status", "pending")
            assets.append(a)
        s["assets"] = assets

        s.setdefault("bg_mode", "cyan_studio")
        s.setdefault("overlays", [])
        s.setdefault("cutaway_needed", False)
        s.setdefault("has_branding", False)
        s.setdefault("branding_note", "")
        s.setdefault("camera_move", "Smooth slow dolly push-in with subtle macro DoF")

        changed = not prev or _scene_signature(prev) != _scene_signature(s)
        if prev and not changed:
            for k in ("script_file", "preview_path", "render_status"):
                if k in prev and k not in s:
                    s[k] = prev[k]
            s["script_stale"] = bool(prev.get("script_stale", False))
        else:
            s["script_stale"] = True
            s["render_status"] = "idle"
            s.pop("preview_path", None)

    sb["fps"] = fps
    sb["total_duration_sec"] = round(cursor, 2)
    sb["full_narration"] = " ".join(p for p in narr if p)
    bp = sb.get("branding_placement") or {}
    if sb.get("scenes"):
        n = len(sb["scenes"])
        bp["scene_index"] = min(max(1, int(bp.get("scene_index", 1))), n)
        if not any(s.get("has_branding") for s in sb["scenes"]):
            sb["scenes"][bp["scene_index"] - 1]["has_branding"] = True
    sb["branding_placement"] = bp
    return sb


def _pydantic_error_text(e: ValidationError) -> str:
    lines = []
    for err in e.errors()[:12]:
        loc = ".".join(str(x) for x in err.get("loc", ()))
        lines.append(f"- {loc}: {err.get('msg')}")
    return "Input failed validation:\n" + "\n".join(lines) + "\nFix these fields and call the tool again."


# ==============================================================================
# Tool registry
# ==============================================================================

class ToolInputError(Exception):
    """Raise from a handler to return an is_error tool_result Claude can fix."""


@dataclass
class TurnContext:
    project_id: str
    emit: Emit
    affected_scenes: set[int] = field(default_factory=set)
    project_changed: bool = False


Handler = Callable[[dict[str, Any], TurnContext], Awaitable[ToolOutput]]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler
    label: str = ""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, name: str, description: str, input_schema: dict[str, Any],
                 handler: Handler, *, label: str = "") -> None:
        self._tools[name] = ToolSpec(name, description, input_schema, handler, label or name)

    def definitions(self) -> list[dict[str, Any]]:
        # Registration order is deterministic, which keeps the tools prefix cache-stable.
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "eager_input_streaming": True,
            }
            for t in self._tools.values()
        ]

    def label(self, name: str) -> str:
        t = self._tools.get(name)
        return t.label if t else name

    async def run(self, name: str, args: Any, ctx: TurnContext) -> tuple[ToolOutput, bool]:
        """Returns (content, is_error). Never raises."""
        spec = self._tools.get(name)
        if spec is None:
            return f"Unknown tool '{name}'.", True
        if not isinstance(args, dict):
            return "Tool input must be a JSON object. Call the tool again with valid input.", True
        try:
            return await spec.handler(args, ctx), False
        except ValidationError as e:
            return _pydantic_error_text(e), True
        except ToolInputError as e:
            return str(e), True
        except Exception as e:  # tool bug or environment failure — report, don't crash the chat
            return f"Tool '{name}' failed: {type(e).__name__}: {e}", True


# ------------------------------------------------------------------------------
# Built-in project tools
# ------------------------------------------------------------------------------

def _project_state_text(project: dict[str, Any]) -> str:
    sb = project.get("storyboard") or {}
    target = Path(project.get("target_folder") or ".")
    state = {
        "project_id": project.get("id"),
        "name": project.get("name"),
        "target_folder": str(target),
        "status": project.get("status"),
        "has_blend": project.get("has_blend"),
        "has_audio": project.get("has_audio"),
        "has_final_video": project.get("has_final"),
        "storyboard": sb if sb.get("scenes") else None,
    }
    return json.dumps(state, indent=1, ensure_ascii=False)


async def _tool_get_project_state(args: dict[str, Any], ctx: TurnContext) -> ToolOutput:
    proj = get_project(ctx.project_id)
    if not proj:
        raise ToolInputError("Project no longer exists.")
    return _project_state_text(proj)


async def _save_storyboard(ctx: TurnContext, sb: dict[str, Any], affected: list[int]) -> dict[str, Any]:
    proj = get_project(ctx.project_id) or {}
    previous = proj.get("storyboard") or {}
    sb = normalize_storyboard(sb, previous)
    name = proj.get("name") or "Untitled 3D Short"
    if name.startswith("Untitled") or not previous.get("scenes"):
        name = sb.get("title") or name
    updated = update_project(ctx.project_id, name=name, storyboard=sb, status="planned")
    try:
        from services.pipeline_manager import save_project_meta_file
        save_project_meta_file(updated)  # type: ignore[arg-type]
    except Exception:
        pass
    ctx.project_changed = True
    ctx.affected_scenes.update(affected)
    await ctx.emit({"type": "project_updated", "project": updated})
    return sb


async def _tool_update_storyboard(args: dict[str, Any], ctx: TurnContext) -> ToolOutput:
    plan = StoryboardIn.model_validate(args)
    sb = plan.model_dump()
    sb["fps"] = 30
    saved = await _save_storyboard(ctx, sb, list(range(1, len(sb["scenes"]) + 1)))
    return (
        f"Storyboard saved: \"{saved['title']}\" — {len(saved['scenes'])} scenes, "
        f"{saved['total_duration_sec']} s total, branding in scene {saved['branding_placement'].get('scene_index')}."
    )


class ScenePatch(BaseModel):
    scene_index: int = Field(ge=1)
    action: Literal["update", "delete", "insert_after"] = "update"
    changes: dict[str, Any] = Field(default_factory=dict)


class PatchScenesIn(BaseModel):
    patches: list[ScenePatch] = Field(min_length=1)
    title: Optional[str] = None
    hook: Optional[str] = None
    branding_placement: Optional[BrandingIn] = None


async def _tool_patch_scenes(args: dict[str, Any], ctx: TurnContext) -> ToolOutput:
    req = PatchScenesIn.model_validate(args)
    proj = get_project(ctx.project_id) or {}
    sb = json.loads(json.dumps(proj.get("storyboard") or {}))  # deep copy of stored (trusted) data
    scenes: list[dict[str, Any]] = sb.get("scenes") or []
    if not scenes:
        raise ToolInputError("There is no storyboard yet. Call update_storyboard to create one first.")

    allowed = set(SceneIn.model_fields)
    affected: list[int] = []
    # Apply from the highest index down so earlier indices stay valid during insert/delete.
    for p in sorted(req.patches, key=lambda x: x.scene_index, reverse=True):
        if p.scene_index > len(scenes):
            raise ToolInputError(f"scene_index {p.scene_index} is out of range (1–{len(scenes)}).")
        unknown = set(p.changes) - allowed
        if unknown:
            raise ToolInputError(f"Unknown scene fields: {sorted(unknown)}. Allowed: {sorted(allowed)}.")
        i = p.scene_index - 1
        if p.action == "delete":
            scenes.pop(i)
        elif p.action == "insert_after":
            new_scene = SceneIn.model_validate(p.changes).model_dump()
            new_scene["_touched"] = True
            scenes.insert(i + 1, new_scene)
        else:
            merged = {**scenes[i], **p.changes}
            SceneIn.model_validate({k: merged.get(k) for k in allowed if k in merged})
            merged["_touched"] = True
            scenes[i] = merged

    if not scenes:
        raise ToolInputError("That would delete every scene. Use update_storyboard to start over instead.")
    for n, s in enumerate(scenes, start=1):
        if s.pop("_touched", False):
            affected.append(n)
    if req.title:
        sb["title"] = req.title
    if req.hook:
        sb["hook"] = req.hook
    if req.branding_placement:
        sb["branding_placement"] = req.branding_placement.model_dump()
    sb["scenes"] = scenes
    saved = await _save_storyboard(ctx, sb, affected)
    return (
        f"Applied {len(req.patches)} patch(es). Storyboard now has {len(saved['scenes'])} scenes, "
        f"{saved['total_duration_sec']} s total. Changed scenes: {sorted(set(affected)) or 'none'}."
    )


def default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        "get_project_state",
        "Return the current project's folder, pipeline status and full storyboard JSON. "
        "Call this before editing if you are unsure what the storyboard currently contains.",
        {"type": "object", "properties": {}},
        _tool_get_project_state,
        label="Reading project",
    )
    reg.register(
        "update_storyboard",
        "Create or fully replace the Short's storyboard (title, hook, diegetic branding placement, and every "
        "scene with narration, duration, visuals, camera move, 3D overlays and assets). Timing, frame ranges and "
        "full_narration are computed automatically. Use for new videos or rewrites of most scenes.",
        STORYBOARD_SCHEMA,
        _tool_update_storyboard,
        label="Writing storyboard",
    )
    reg.register(
        "patch_scenes",
        "Surgically edit an existing storyboard: update fields of specific scenes, delete scenes, or insert a new "
        "scene after a given index. Only send the fields that change. Optionally update title, hook or branding.",
        {
            "type": "object",
            "properties": {
                "patches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "scene_index": {"type": "integer", "description": "1-based index in the CURRENT storyboard"},
                            "action": {"type": "string", "enum": ["update", "delete", "insert_after"]},
                            "changes": {
                                "type": "object",
                                "description": "Scene fields to set. For insert_after, a full scene object.",
                                "properties": _SCENE_PROPS,
                            },
                        },
                        "required": ["scene_index"],
                    },
                },
                "title": {"type": "string"},
                "hook": {"type": "string"},
                "branding_placement": STORYBOARD_SCHEMA["properties"]["branding_placement"],
            },
            "required": ["patches"],
        },
        _tool_patch_scenes,
        label="Editing scenes",
    )
    return reg


REGISTRY = default_registry()


# ==============================================================================
# Conversation history
# ==============================================================================

def _history_messages(project_id: str) -> list[dict[str, Any]]:
    """Text-only replay of earlier turns (tool calls of past turns are already
    reflected in <current_project_state>)."""
    msgs = [m for m in get_messages(project_id) if m["role"] in ("user", "assistant") and m["content"].strip()]
    msgs = msgs[-MAX_HISTORY_MESSAGES:]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    out: list[dict[str, Any]] = []
    for m in msgs:
        if out and out[-1]["role"] == m["role"]:
            out[-1]["content"] += "\n\n" + m["content"]
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


# ==============================================================================
# The agent loop
# ==============================================================================

@dataclass
class TurnResult:
    text: str
    thinking: str
    tool_calls: list[dict[str, Any]]
    usage: dict[str, Any]
    affected_scenes: list[int]
    project_changed: bool
    stop_reason: str
    model: str


def _resolve_model(settings: dict[str, Any], override: Optional[str]) -> str:
    return (override or settings.get("claude_model") or DEFAULT_CLAUDE_MODEL).strip()


def _max_output_tokens(model: str) -> int:
    if model.startswith("claude-3-5") or model.startswith("claude-3-haiku"):
        return 8192
    if model.startswith("claude-3"):
        return 32000
    return 64000


def _stream_ctx(client: anthropic.AsyncAnthropic, model: str, kwargs: dict[str, Any]):
    if supports_fallbacks(model):
        return client.beta.messages.stream(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
    return client.messages.stream(**kwargs)


async def run_chat_turn(
    *,
    project_id: str,
    user_content: Union[str, list[dict[str, Any]]],
    emit: Emit,
    model: Optional[str] = None,
    thinking: Optional[bool] = None,
    effort: Optional[str] = None,
    registry: Optional[ToolRegistry] = None,
) -> TurnResult:
    """
    Run one user turn: stream Claude's reply, execute any tool calls, loop until
    Claude ends its turn. `user_content` is a string or a list of content blocks
    (text/image) for attachments. Emits UI events through `emit`.
    """
    settings = get_settings()
    api_key = (settings.get("anthropic_api_key") or "").strip()
    if not api_key:
        raise ValueError("Anthropic API key is not configured. Open Settings and add your Claude API key.")
    registry = registry or REGISTRY
    model_id = _resolve_model(settings, model)
    use_thinking = bool(settings.get("extended_thinking", True) if thinking is None else thinking)
    effort_level = effort or settings.get("thinking_effort") or "high"

    proj = get_project(project_id)
    if not proj:
        raise ValueError("Project not found.")

    client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=3)
    ctx = TurnContext(project_id=project_id, emit=emit)

    history = _history_messages(project_id)
    # The current user message is already persisted; drop it from replay and append the rich version.
    if history and history[-1]["role"] == "user":
        history.pop()
    messages: list[Any] = history + [{"role": "user", "content": user_content}]

    system_blocks = build_system_blocks(_project_state_text(proj))
    tools = registry.definitions()
    base_kwargs: dict[str, Any] = {
        "model": model_id,
        "max_tokens": _max_output_tokens(model_id),
        "system": system_blocks,
        "tools": tools,
        "cache_control": {"type": "ephemeral"},  # auto-cache the growing conversation prefix
        **request_options(model_id, thinking=use_thinking, effort=effort_level),
    }

    final_text_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_log: list[dict[str, Any]] = []
    usage_records: list[dict[str, Any]] = []
    served_model = model_id
    stop_reason = "end_turn"
    json_retries = 0

    await emit({"type": "assistant_start", "model": model_id, "thinking": use_thinking})

    for _iteration in range(MAX_AGENT_ITERATIONS):
        try:
            async with _stream_ctx(client, model_id, {**base_kwargs, "messages": messages}) as stream:
                current_block: Optional[str] = None
                async for event in stream:
                    et = event.type
                    if et == "content_block_start":
                        cb = event.content_block
                        current_block = cb.type
                        if cb.type == "tool_use":
                            await emit({"type": "tool_start", "id": cb.id, "name": cb.name,
                                        "label": registry.label(cb.name)})
                        elif cb.type == "thinking":
                            await emit({"type": "thinking_start"})
                    elif et == "content_block_delta":
                        d = event.delta
                        if d.type == "text_delta":
                            await emit({"type": "text_delta", "text": d.text})
                        elif d.type == "thinking_delta" and d.thinking:
                            await emit({"type": "thinking_delta", "text": d.thinking})
                    elif et == "content_block_stop":
                        if current_block == "text":
                            await emit({"type": "text_block_end"})
                        current_block = None
                response = await stream.get_final_message()
            json_retries = 0
        except ValueError as e:
            # The SDK could not parse a streamed tool input at all — re-issue this step.
            json_retries += 1
            if json_retries > 2:
                raise RuntimeError(f"Claude produced unreadable tool input three times: {e}") from e
            await emit({"type": "notice", "text": "Retrying a malformed tool call…"})
            continue

        served_model = getattr(response, "model", model_id) or model_id
        usage_records.append(_usage_record(project_id, "chat", served_model, response.usage))
        stop_reason = response.stop_reason or "end_turn"

        for block in response.content:
            if block.type == "text" and block.text:
                final_text_parts.append(block.text)
            elif block.type == "thinking" and getattr(block, "thinking", ""):
                thinking_parts.append(block.thinking)
            elif block.type == "fallback":
                await emit({"type": "notice",
                            "text": f"{block.from_.model} declined; {block.to.model} continued this turn."})

        if stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue

        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            cat = getattr(details, "category", None) if details else None
            note = f"\n\n_Claude declined to continue this request{f' ({cat})' if cat else ''}._"
            final_text_parts.append(note)
            await emit({"type": "text_delta", "text": note})
            break

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            if stop_reason == "max_tokens":
                note = "\n\n_Reply hit the output limit. Ask me to continue._"
                final_text_parts.append(note)
                await emit({"type": "text_delta", "text": note})
            break

        messages.append({"role": "assistant", "content": response.content})

        results: list[dict[str, Any]] = []
        for tu in tool_uses:
            if stop_reason == "max_tokens" and tu is tool_uses[-1]:
                content, is_error = (
                    "Your tool input was cut off by the output limit. Send a shorter input "
                    "(e.g. use patch_scenes for a few scenes at a time).", True)
            else:
                content, is_error = await registry.run(tu.name, tu.input, ctx)
            summary = content if isinstance(content, str) else f"{len(content)} content block(s)"
            tool_log.append({"id": tu.id, "name": tu.name, "label": registry.label(tu.name),
                             "ok": not is_error, "summary": summary[:400]})
            await emit({"type": "tool_result", "id": tu.id, "name": tu.name, "ok": not is_error,
                        "summary": summary[:400]})
            results.append({"type": "tool_result", "tool_use_id": tu.id,
                            "content": content, **({"is_error": True} if is_error else {})})
        messages.append({"role": "user", "content": results})
    else:
        note = "\n\n_Stopped after many tool steps in one turn. Say “continue” to keep going._"
        final_text_parts.append(note)
        await emit({"type": "text_delta", "text": note})

    return TurnResult(
        text="\n\n".join(p.strip() for p in final_text_parts if p.strip()),
        thinking="\n\n".join(thinking_parts),
        tool_calls=tool_log,
        usage=_sum_usage(usage_records, served_model),
        affected_scenes=sorted(ctx.affected_scenes),
        project_changed=ctx.project_changed,
        stop_reason=stop_reason,
        model=served_model,
    )


# ==============================================================================
# One-shot helpers used by the headless build pipeline (scene scripts, self-heal)
# ==============================================================================

def _extract_python_code(text: str) -> str:
    """Python is returned in a fenced block; this never raises (no JSON parsing)."""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.DOTALL)
    if blocks:
        return max(blocks, key=len).strip()
    return text.strip()


class ClaudeDirector:
    """Synchronous single-call helpers for pipeline_manager (run via asyncio.to_thread)."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.get("anthropic_api_key", "")
        self.model = model or settings.get("claude_model") or DEFAULT_CLAUDE_MODEL

    def _client(self) -> anthropic.Anthropic:
        if not self.api_key:
            raise ValueError("Anthropic API key is not configured. Open Settings to add your Claude API key.")
        return anthropic.Anthropic(api_key=self.api_key, max_retries=3)

    def _call_claude(self, *, project_id: Optional[str], operation: str, user_prompt: str) -> tuple[str, dict[str, Any]]:
        client = self._client()
        system = build_system_blocks("(headless script generation — no chat context)")[:-1]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": _max_output_tokens(self.model),
            "system": system,
            "messages": [{"role": "user", "content": user_prompt}],
            **request_options(self.model, thinking=not is_legacy(self.model), effort="medium"),
        }
        if supports_fallbacks(self.model):
            ctx = client.beta.messages.stream(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
        else:
            ctx = client.messages.stream(**kwargs)
        with ctx as stream:
            response = stream.get_final_message()
        if response.stop_reason == "refusal":
            raise RuntimeError(f"Claude declined to generate {operation}.")
        text = "\n".join(b.text for b in response.content if b.type == "text").strip()
        usage = _usage_record(project_id, operation, getattr(response, "model", self.model) or self.model, response.usage)
        return text, usage

    def generate_scene_script(
        self,
        *,
        project_id: str,
        scene: dict[str, Any],
        branding_placement: dict[str, Any],
        edit_instruction: Optional[str] = None,
        existing_code: Optional[str] = None,
    ) -> tuple[str, dict[str, Any]]:
        idx = scene["scene_index"]
        parts = [
            f"Write the complete, bug-free Blender Python (`bpy`) module for Scene {idx:02d}.",
            "It MUST define `def build_scene(ctx: dict) -> dict:` and use `import zdf_helpers as zdf`.",
            "REQUIREMENTS:",
            "1. Start with `col = zdf.setup_scene_collection(ctx['scene_index'], ctx['start_frame'], ctx['end_frame'])`.",
            "2. Call `zdf.set_studio_bg_keyframe(ctx.get('bg_mode', 'cyan_studio'), ctx['start_frame'])`.",
            "3. For every asset in `ctx['assets']`, try `zdf.import_and_normalize_asset(ctx['assets'].get('<asset_id>'), ...)` "
            "and ALWAYS include an `if obj is None:` fallback that models the prop properly (bmesh / modifiers / bevels), "
            "never a raw primitive.",
            "4. Use realistic PBR materials via `zdf.create_pbr_material(...)` and `zdf.assign_material(...)`.",
            "5. If `cutaway_needed` is true, use `zdf.apply_animated_cutaway(...)`.",
            "6. Implement the listed 3D overlays, keyframed smoothly inside `[start_frame, end_frame]`.",
            "7. If `has_branding` is true, call `zdf.create_branding_decal(text='STICK KNOWLEDGE', ...)` visibly on the hero element.",
            "8. Camera via `cam = zdf.setup_cinematic_camera(...)`, framed for 9:16 (keep the subject in the middle 60%).",
            "9. Call `zdf.finalize_scene_visibility(col, ctx['start_frame'], ctx['end_frame'])` before returning.",
            "10. Return `{'camera': cam, 'collection': col, 'preview_frame': int((ctx['start_frame'] + ctx['end_frame']) // 2)}`.",
            "11. Output ONLY the Python file inside one ```python ... ``` block. Compatible with Blender 4.2 through 5.x.",
            "",
            f"SCENE SPECIFICATION:\n{json.dumps(scene, indent=2, ensure_ascii=False)}",
            f"GLOBAL DIEGETIC BRANDING PLACEMENT:\n{json.dumps(branding_placement, indent=2, ensure_ascii=False)}",
        ]
        if edit_instruction and existing_code:
            parts.append(f"\nEXISTING SCRIPT TO UPDATE:\n```python\n{existing_code}\n```")
            parts.append(f"\nSPECIFIC EDIT REQUEST:\n{edit_instruction}")
        raw, usage = self._call_claude(project_id=project_id, operation=f"generate_scene_{idx:02d}",
                                       user_prompt="\n".join(parts))
        return _extract_python_code(raw), usage

    def self_heal_script(
        self,
        *,
        project_id: str,
        script_name: str,
        broken_code: str,
        error_traceback: str,
    ) -> tuple[str, dict[str, Any]]:
        prompt = (
            f"The Blender Python script `{script_name}` raised an error in Blender.\n"
            "Fix the bug while preserving the visual intent and the `build_scene(ctx)` signature.\n"
            "Return ONLY the fixed Python file inside one ```python ... ``` block.\n\n"
            f"ERROR TRACEBACK:\n```\n{error_traceback[-4000:]}\n```\n\n"
            f"CURRENT CODE:\n```python\n{broken_code}\n```"
        )
        raw, usage = self._call_claude(project_id=project_id, operation=f"self_heal_{script_name}", user_prompt=prompt)
        return _extract_python_code(raw), usage
