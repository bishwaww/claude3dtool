import type {
  AssetLibraryResponse,
  BlenderKitStatus,
  ChatMessage,
  ClaudeModelOption,
  ElevenLabsVoice,
  Project,
  Settings,
  StoryboardPlan,
  TokenUsageSummary,
} from '../types';

const BASE = '';

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail || data.message || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<{ ok: boolean; blender_detected: string; ffmpeg_detected: string }>('/api/health'),

  getSettings: () =>
    req<{ settings: Settings; models: ClaudeModelOption[]; ffmpeg_path: string }>('/api/settings'),
  saveSettings: (settings: Settings) =>
    req<{ ok: boolean; settings: Settings }>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),

  detectBlender: () =>
    req<{ blender_found: boolean; blender_path: string; blender_version: string; error?: string }>(
      '/api/system/detect-blender',
      { method: 'POST' }
    ),

  getBlenderKitStatus: () => req<BlenderKitStatus>('/api/system/blenderkit-status'),
  installBlenderKit: (payload: { source_path?: string; blender_path?: string; api_key?: string }) =>
    req<{ ok: boolean; message: string; status?: BlenderKitStatus }>('/api/system/install-blenderkit', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  pickFolder: () => req<{ ok: boolean; path: string; error?: string }>('/api/system/pick-folder', { method: 'POST' }),
  validatePath: (path: string) =>
    req<{ valid: boolean; exists?: boolean; resolved?: string; message: string }>('/api/system/validate-path', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),

  listVoices: () => req<{ voices: ElevenLabsVoice[] }>('/api/elevenlabs/voices'),
  previewVoice: async (voice_id: string, text?: string): Promise<Blob> => {
    const res = await fetch('/api/elevenlabs/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voice_id, ...(text ? { text } : {}) }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Voice preview failed' }));
      throw new Error(err.detail || 'Voice preview failed');
    }
    return res.blob();
  },

  getAssetLibrary: () => req<AssetLibraryResponse>('/api/assets/library'),
  searchAssets: (q: string, source = 'all', category = 'prop') =>
    req<{ query: string; blenderkit: any[]; polyhaven: any[] }>(
      `/api/assets/search?q=${encodeURIComponent(q)}&source=${encodeURIComponent(source)}&category=${encodeURIComponent(category)}`
    ),

  listProjects: () => req<{ projects: Project[] }>('/api/projects'),
  createProject: (payload: { name: string; target_folder: string; topic?: string }) =>
    req<{ project: Project }>('/api/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getProject: (id: string) =>
    req<{ project: Project; messages: ChatMessage[]; usage: TokenUsageSummary }>(`/api/projects/${id}`),
  updateProject: (id: string, payload: { name?: string; target_folder?: string; storyboard?: StoryboardPlan }) =>
    req<{ project: Project }>(`/api/projects/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  deleteProject: (id: string) => req<{ ok: boolean }>(`/api/projects/${id}`, { method: 'DELETE' }),

  sendChat: (projectId: string, message: string) =>
    req<{
      project: Project;
      user_message: ChatMessage;
      assistant_message: ChatMessage;
      affected_scenes: number[];
      usage: TokenUsageSummary;
    }>(`/api/projects/${projectId}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),

  generateVoiceover: (projectId: string) =>
    req<{ project: Project; timestamps: any }>(`/api/projects/${projectId}/generate-voiceover`, {
      method: 'POST',
    }),

  buildProject: (
    projectId: string,
    payload: { render_previews?: boolean; regenerate_scripts?: boolean; scene_indices?: number[] } = {}
  ) =>
    req<{ ok: boolean; started: boolean }>(`/api/projects/${projectId}/build`, {
      method: 'POST',
      body: JSON.stringify({
        render_previews: payload.render_previews ?? true,
        regenerate_scripts: payload.regenerate_scripts ?? false,
        scene_indices: payload.scene_indices ?? null,
      }),
    }),

  rerenderScene: (projectId: string, sceneIndex: number, regenerateScript = false) =>
    req<{ ok: boolean; started: boolean }>(
      `/api/projects/${projectId}/rerender-scene/${sceneIndex}?regenerate_script=${regenerateScript}`,
      { method: 'POST' }
    ),

  openInBlender: (projectId: string) =>
    req<{ ok: boolean; launched: string }>(`/api/projects/${projectId}/open-blender`, { method: 'POST' }),

  renderFinal: (
    projectId: string,
    payload: {
      render_engine?: 'EEVEE_NEXT' | 'CYCLES_OPTIX';
      cycles_samples?: number;
      include_sfx?: boolean;
      burn_captions?: boolean;
    } = {}
  ) =>
    req<{ ok: boolean; started: boolean }>(`/api/projects/${projectId}/render-final`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getUsage: (projectId?: string) =>
    req<TokenUsageSummary>(projectId ? `/api/usage?project_id=${encodeURIComponent(projectId)}` : '/api/usage'),

  previewImageUrl: (projectId: string, sceneIndex: number, bust = 0) =>
    `/api/projects/${projectId}/media/preview/${sceneIndex}?v=${bust}`,
  narrationAudioUrl: (projectId: string, bust = 0) => `/api/projects/${projectId}/media/narration?v=${bust}`,
  finalVideoUrl: (projectId: string, bust = 0) => `/api/projects/${projectId}/media/final-video?v=${bust}`,
};
