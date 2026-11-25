export interface Settings {
  anthropic_api_key: string;
  claude_model: string;
  extended_thinking: boolean;
  thinking_effort: ThinkingEffort;
  elevenlabs_api_key: string;
  elevenlabs_voice_id: string;
  elevenlabs_voice_name: string;
  elevenlabs_model_id: string;
  whisper_model: string;
  blender_path: string;
  blenderkit_source_path: string;
  blenderkit_api_key: string;
  huggingface_token: string;
  render_engine: 'EEVEE_NEXT' | 'CYCLES_OPTIX';
  cycles_samples: number;
  budget_limit_usd: number;
}

export type ThinkingEffort = 'low' | 'medium' | 'high' | 'xhigh' | 'max';

export interface ClaudeModelOption {
  id: string;
  display_name?: string;
  label: string;
  created_at?: string;
  max_input_tokens?: number | null;
  max_tokens?: number | null;
  input_per_mtok: number;
  output_per_mtok: number;
  cache_write_per_mtok?: number;
  cache_read_per_mtok: number;
}

export interface ModelsResponse {
  models: ClaudeModelOption[];
  source: 'live' | 'fallback';
  error: string | null;
}

export interface ToolCallInfo {
  id: string;
  name: string;
  label?: string;
  ok?: boolean;
  summary?: string;
  running?: boolean;
  image_url?: string;
}

export type AttachmentPurpose = 'reference' | 'asset' | 'logo' | 'voiceover';

export interface AttachmentView {
  id: string;
  kind: 'image' | 'video' | 'audio' | 'model' | 'other';
  purpose: AttachmentPurpose;
  filename: string;
  status: 'processing' | 'ready' | 'error';
  path: string;
  error?: string | null;
  thumb_url?: string;
  summary?: string;
}

export interface VoicesResponse {
  voices: ElevenLabsVoice[];
  source: 'live' | 'fallback';
  error: string | null;
}

export interface MixamoItem {
  name: string;
  path: string;
  folder: string;
  size_kb: number;
  kind: 'character' | 'animation' | 'mesh' | 'unknown';
  bones?: number | null;
  bone_prefix?: string | null;
  frames?: number | null;
  height_m?: number | null;
  ok: boolean;
  error?: string | null;
}

export interface MixamoLibrary {
  folder: string;
  characters: MixamoItem[];
  animations: MixamoItem[];
  other: MixamoItem[];
  probed_now: number;
}

export interface BlenderStatus {
  connected: boolean;
  file?: string;
  blender?: string;
  port?: number;
  dirty?: boolean;
  zdf_helpers?: boolean;
  error?: string;
}

export interface LiveCapture {
  url: string;
  frame?: number;
  camera?: string;
  ts: number;
}

export interface LiveRenderStatus {
  running: boolean;
  frame?: number;
  start?: number;
  end?: number;
  done?: boolean;
  cancelled?: boolean;
  output?: string;
  error?: string;
}

/** Server-Sent Event payloads streamed by POST /api/projects/{id}/chat */
export type ChatStreamEvent =
  | { type: 'user_message'; message: ChatMessage }
  | { type: 'assistant_start'; model: string; thinking: boolean }
  | { type: 'thinking_start' }
  | { type: 'thinking_delta'; text: string }
  | { type: 'text_delta'; text: string }
  | { type: 'text_block_end' }
  | { type: 'tool_start'; id: string; name: string; label: string }
  | { type: 'tool_result'; id: string; name: string; ok: boolean; summary: string; label?: string; image_url?: string }
  | { type: 'viewport_capture'; url: string; frame?: number; camera?: string }
  | { type: 'notice'; text: string }
  | { type: 'project_updated'; project: Project }
  | { type: 'done'; assistant_message: ChatMessage; project: Project; usage: TokenUsageSummary }
  | { type: 'error'; message: string; assistant_message: ChatMessage };

export interface ElevenLabsVoice {
  voice_id: string;
  name: string;
  category?: string;
  preview_url?: string;
  description?: string;
  labels?: Record<string, string>;
}

export interface AssetRequirement {
  asset_id: string;
  query: string;
  category: 'prop' | 'anatomy' | 'character' | 'material' | 'hdri';
  resolved_source?: string | null;
  local_path?: string | null;
  display_name?: string | null;
  license?: string | null;
  status: 'pending' | 'resolved' | 'procedural_fallback' | 'error';
}

export interface BrandingPlacement {
  mode: 'tshirt' | 'prop_wrap' | 'screen_ui' | 'engraved';
  target_object: string;
  scene_index: number;
  description: string;
}

export interface SceneSpec {
  scene_index: number;
  title: string;
  narration: string;
  duration_sec: number;
  start_sec: number;
  end_sec: number;
  start_frame: number;
  end_frame: number;
  bg_mode: 'cyan_studio' | 'sky_gradient' | 'dark_space' | 'interior';
  visual_description: string;
  camera_move: string;
  overlays: string[];
  cutaway_needed: boolean;
  has_branding: boolean;
  branding_note: string;
  assets: AssetRequirement[];
  script_file?: string | null;
  preview_path?: string | null;
  render_status: 'idle' | 'building' | 'preview_ready' | 'rendered' | 'error';
}

export interface StoryboardPlan {
  title: string;
  hook: string;
  total_duration_sec: number;
  fps: number;
  full_narration: string;
  branding_placement: BrandingPlacement;
  scenes: SceneSpec[];
}

export interface Project {
  id: string;
  name: string;
  target_folder: string;
  topic: string;
  status: string;
  storyboard: StoryboardPlan | Record<string, never>;
  has_blend: boolean;
  has_audio: boolean;
  has_final: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: number;
  project_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  metadata?: {
    affected_scenes?: number[];
    usage?: TokenUsageEntry;
    tool_calls?: ToolCallInfo[];
    attachments?: AttachmentView[];
    thinking?: string;
    model?: string;
    error?: boolean;
  };
  created_at: string;
}

export interface TokenUsageEntry {
  id?: number;
  project_id?: string | null;
  operation: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  cost_usd: number;
  created_at?: string;
}

export interface TokenUsageSummary {
  budget_limit_usd: number;
  global_totals: {
    input_tokens: number;
    output_tokens: number;
    cache_creation_tokens: number;
    cache_read_tokens: number;
    cost_usd: number;
  };
  project_totals: {
    input_tokens: number;
    output_tokens: number;
    cache_creation_tokens: number;
    cache_read_tokens: number;
    cost_usd: number;
  };
  entries: TokenUsageEntry[];
}

export interface ConsoleLogEntry {
  id: string;
  stage: string;
  message: string;
  ts: string;
}

export interface PipelineProgress {
  stage: string;
  percent: number;
  detail: string;
}

export interface BlenderKitStatus {
  source_path: string;
  source_valid: boolean;
  resolved_source_root: string;
  source_version: string;
  target_addons_dir: string;
  copied_in_addons: boolean;
  blender_found: boolean;
  blender_path: string;
  blender_version: string;
  blenderkit_installed: boolean;
  blenderkit_enabled: boolean;
  mpfb2_installed: boolean;
  engines: string[];
  error?: string | null;
}

export interface LocalAssetItem {
  name: string;
  filename: string;
  path: string;
  ext: string;
  size_kb: number;
  source: string;
  tags: string[];
  character_type: string;
}

export interface AssetLibraryResponse {
  catalog: {
    mixamo: LocalAssetItem[];
    custom: LocalAssetItem[];
    anatomy: LocalAssetItem[];
    polyhaven_cache: LocalAssetItem[];
    blenderkit_cache: LocalAssetItem[];
  };
  mixamo_folder: string;
  blenderkit: BlenderKitStatus;
}
