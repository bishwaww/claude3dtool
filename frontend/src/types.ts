export interface Settings {
  anthropic_api_key: string;
  claude_model: string;
  elevenlabs_api_key: string;
  elevenlabs_voice_id: string;
  elevenlabs_voice_name: string;
  blender_path: string;
  blenderkit_source_path: string;
  blenderkit_api_key: string;
  huggingface_token: string;
  render_engine: 'EEVEE_NEXT' | 'CYCLES_OPTIX';
  cycles_samples: number;
  budget_limit_usd: number;
}

export interface ClaudeModelOption {
  id: string;
  label: string;
  input_per_mtok: number;
  output_per_mtok: number;
  cache_read_per_mtok: number;
}

export interface ElevenLabsVoice {
  voice_id: string;
  name: string;
  category?: string;
  preview_url?: string;
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
  bg_mode: 'cyan_studio' | 'dark_space';
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
