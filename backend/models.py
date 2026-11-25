from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class SettingsPayload(BaseModel):
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5-5"
    extended_thinking: bool = True
    thinking_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB"  # Adam default
    elevenlabs_voice_name: str = "Adam (Default)"
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    whisper_model: str = "small.en"
    blender_path: str = ""
    blenderkit_source_path: str = r"D:\B Software LK\blender.crt\blenderkit"
    blenderkit_api_key: str = ""
    huggingface_token: str = ""
    render_engine: Literal["EEVEE_NEXT", "CYCLES_OPTIX"] = "EEVEE_NEXT"
    cycles_samples: int = 64
    budget_limit_usd: float = 100.0


class BrandingPlacement(BaseModel):
    mode: Literal["tshirt", "prop_wrap", "screen_ui", "engraved"] = "prop_wrap"
    target_object: str = ""
    scene_index: int = 1
    description: str = ""


class AssetRequirement(BaseModel):
    asset_id: str
    query: str
    category: Literal["prop", "anatomy", "character", "material", "hdri"] = "prop"
    preferred_source: Optional[str] = None
    resolved_source: Optional[str] = None  # blenderkit, polyhaven, mixamo, mpfb2, nih3d, huggingface, procedural
    local_path: Optional[str] = None
    display_name: Optional[str] = None
    license: Optional[str] = None
    status: Literal["pending", "resolved", "procedural_fallback", "error"] = "pending"


class SceneSpec(BaseModel):
    scene_index: int
    title: str
    narration: str
    duration_sec: float = 3.0
    start_sec: float = 0.0
    end_sec: float = 3.0
    start_frame: int = 1
    end_frame: int = 90
    bg_mode: Literal["cyan_studio", "sky_gradient", "dark_space", "interior"] = "cyan_studio"
    visual_description: str = ""
    camera_move: str = "Smooth slow dolly push-in with subtle macro DoF"
    overlays: list[str] = Field(default_factory=list)
    cutaway_needed: bool = False
    has_branding: bool = False
    branding_note: str = ""
    assets: list[AssetRequirement] = Field(default_factory=list)
    script_file: Optional[str] = None
    script_stale: bool = False
    preview_path: Optional[str] = None
    render_status: Literal["idle", "building", "preview_ready", "rendered", "error"] = "idle"


class StoryboardPlan(BaseModel):
    title: str
    hook: str
    total_duration_sec: float = 35.0
    fps: int = 30
    full_narration: str = ""
    branding_placement: BrandingPlacement = Field(default_factory=BrandingPlacement)
    scenes: list[SceneSpec] = Field(default_factory=list)


class ChatMessage(BaseModel):
    id: Optional[int] = None
    project_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class TokenUsageEntry(BaseModel):
    id: Optional[int] = None
    project_id: Optional[str] = None
    operation: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    created_at: Optional[str] = None


class CreateProjectRequest(BaseModel):
    name: str = "Untitled 3D Short"
    target_folder: str
    topic: str = ""


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    target_folder: Optional[str] = None
    storyboard: Optional[StoryboardPlan] = None


class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None  # per-message model override from the chat-bar switcher
    thinking: Optional[bool] = None
    effort: Optional[Literal["low", "medium", "high", "xhigh", "max"]] = None
    attachments: list[str] = Field(default_factory=list)  # attachment ids uploaded beforehand
    auto_generate_voice: bool = False
    auto_build_blend: bool = False


class BuildRequest(BaseModel):
    render_previews: bool = True
    regenerate_scripts: bool = False
    scene_indices: Optional[list[int]] = None


class RenderFinalRequest(BaseModel):
    render_engine: Optional[Literal["EEVEE_NEXT", "CYCLES_OPTIX"]] = None
    cycles_samples: Optional[int] = None
    include_sfx: bool = True
    burn_captions: bool = True


class ValidatePathRequest(BaseModel):
    path: str


class VoicePreviewRequest(BaseModel):
    voice_id: str
    text: str = "If you swallow a tiny coin battery, saliva immediately triggers an electrical circuit inside your throat."
