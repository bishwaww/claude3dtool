import { create } from 'zustand';
import { api } from '../api/client';
import type {
  AssetLibraryResponse,
  ChatMessage,
  ClaudeModelOption,
  ConsoleLogEntry,
  PipelineProgress,
  Project,
  Settings,
  StoryboardPlan,
  TokenUsageSummary,
} from '../types';

export type ArtifactTab = 'storyboard' | 'previews' | 'console';

interface StudioState {
  projects: Project[];
  activeProjectId: string | null;
  activeProject: Project | null;
  messages: ChatMessage[];
  usage: TokenUsageSummary | null;
  settings: Settings | null;
  models: ClaudeModelOption[];
  ffmpegPath: string;
  assetLibrary: AssetLibraryResponse | null;

  targetFolderInput: string;
  pathValidation: { valid: boolean; message: string; exists?: boolean } | null;

  sidebarOpen: boolean;
  artifactTab: ArtifactTab;
  settingsModalOpen: boolean;
  assetModalOpen: boolean;

  isSendingChat: boolean;
  isGeneratingVoice: boolean;
  isPipelineRunning: boolean;
  progress: PipelineProgress | null;
  logs: ConsoleLogEntry[];
  mediaVersion: number;
  toast: { type: 'info' | 'success' | 'error'; message: string } | null;

  ws: WebSocket | null;

  // Actions
  init: () => Promise<void>;
  setSidebarOpen: (open: boolean) => void;
  setArtifactTab: (tab: ArtifactTab) => void;
  setSettingsModalOpen: (open: boolean) => void;
  setAssetModalOpen: (open: boolean) => void;
  setTargetFolderInput: (path: string) => void;
  validateTargetFolder: (path: string) => Promise<void>;
  pickTargetFolder: () => Promise<void>;
  showToast: (type: 'info' | 'success' | 'error', message: string) => void;
  clearLogs: () => void;

  createNewProject: (name?: string) => Promise<Project | null>;
  selectProject: (projectId: string) => Promise<void>;
  deleteProject: (projectId: string) => Promise<void>;
  saveStoryboardEdits: (storyboard: StoryboardPlan) => Promise<void>;
  sendPrompt: (message: string) => Promise<void>;
  generateVoiceover: () => Promise<void>;
  buildBlendProject: (opts?: { regenerateScripts?: boolean; sceneIndices?: number[] }) => Promise<void>;
  rerenderScene: (sceneIndex: number, regenerateScript?: boolean) => Promise<void>;
  openInBlender: () => Promise<void>;
  renderFinalShort: () => Promise<void>;
  saveSettings: (next: Settings) => Promise<void>;
  refreshAssetLibrary: () => Promise<void>;
  connectWebSocket: (projectId: string) => void;
}

const DEFAULT_OUTPUT_DIR = 'D:\\Videos\\StickKnowledge\\Ep01';

export const useStudioStore = create<StudioState>((set, get) => ({
  projects: [],
  activeProjectId: null,
  activeProject: null,
  messages: [],
  usage: null,
  settings: null,
  models: [],
  ffmpegPath: '',
  assetLibrary: null,

  targetFolderInput: DEFAULT_OUTPUT_DIR,
  pathValidation: null,

  sidebarOpen: true,
  artifactTab: 'storyboard',
  settingsModalOpen: false,
  assetModalOpen: false,

  isSendingChat: false,
  isGeneratingVoice: false,
  isPipelineRunning: false,
  progress: null,
  logs: [],
  mediaVersion: 1,
  toast: null,
  ws: null,

  showToast: (type, message) => {
    set({ toast: { type, message } });
    setTimeout(() => {
      if (get().toast?.message === message) {
        set({ toast: null });
      }
    }, 4500);
  },

  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setArtifactTab: (tab) => set({ artifactTab: tab }),
  setSettingsModalOpen: (open) => set({ settingsModalOpen: open }),
  setAssetModalOpen: (open) => set({ assetModalOpen: open }),
  clearLogs: () => set({ logs: [] }),

  setTargetFolderInput: (path) => {
    set({ targetFolderInput: path });
  },

  validateTargetFolder: async (path) => {
    try {
      const res = await api.validatePath(path);
      set({ pathValidation: res });
      const active = get().activeProject;
      if (res.valid && active && active.target_folder !== path) {
        const updated = await api.updateProject(active.id, { target_folder: path });
        set((s) => ({
          activeProject: updated.project,
          projects: s.projects.map((p) => (p.id === updated.project.id ? updated.project : p)),
        }));
      }
    } catch (e: any) {
      set({ pathValidation: { valid: false, message: e.message } });
    }
  },

  pickTargetFolder: async () => {
    try {
      const res = await api.pickFolder();
      if (res.ok && res.path) {
        set({ targetFolderInput: res.path });
        await get().validateTargetFolder(res.path);
      }
    } catch (e: any) {
      get().showToast('error', `Folder picker error: ${e.message}`);
    }
  },

  init: async () => {
    try {
      const [settingsRes, projectsRes, usageRes] = await Promise.all([
        api.getSettings(),
        api.listProjects(),
        api.getUsage(),
      ]);
      set({
        settings: settingsRes.settings,
        models: settingsRes.models,
        ffmpegPath: settingsRes.ffmpeg_path,
        projects: projectsRes.projects,
        usage: usageRes,
      });

      if (projectsRes.projects.length > 0) {
        await get().selectProject(projectsRes.projects[0].id);
      } else {
        await get().validateTargetFolder(get().targetFolderInput);
      }

      // Load asset library & BlenderKit status in background
      api.getAssetLibrary().then((lib) => set({ assetLibrary: lib })).catch(() => {});
    } catch (e: any) {
      get().showToast('error', `Backend connection failed: ${e.message}`);
    }
  },

  refreshAssetLibrary: async () => {
    try {
      const lib = await api.getAssetLibrary();
      set({ assetLibrary: lib });
    } catch (e: any) {
      get().showToast('error', `Could not refresh asset library: ${e.message}`);
    }
  },

  connectWebSocket: (projectId) => {
    const prev = get().ws;
    if (prev) {
      try {
        prev.close();
      } catch {
        // ignore
      }
    }
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/${projectId}`);
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'log') {
          set((s) => ({
            logs: [
              ...s.logs.slice(-400),
              {
                id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
                stage: msg.stage || 'info',
                message: msg.message || '',
                ts: msg.ts || new Date().toISOString(),
              },
            ],
          }));
        } else if (msg.type === 'progress') {
          const running = msg.percent > 0 && msg.percent < 100 && msg.stage !== 'error';
          set({
            progress: { stage: msg.stage, percent: msg.percent, detail: msg.detail || '' },
            isPipelineRunning: running,
          });
        } else if (msg.type === 'project_updated' && msg.project) {
          set((s) => ({
            activeProject: msg.project,
            projects: s.projects.map((p) => (p.id === msg.project.id ? msg.project : p)),
            mediaVersion: s.mediaVersion + 1,
            isPipelineRunning: ['building', 'rendering'].includes(msg.project.status),
          }));
        } else if (msg.type === 'storyboard_updated' && msg.storyboard) {
          set((s) =>
            s.activeProject
              ? { activeProject: { ...s.activeProject, storyboard: msg.storyboard } }
              : {}
          );
        } else if (msg.type === 'usage_updated' && msg.usage) {
          set({ usage: msg.usage });
        }
      } catch {
        // ignore
      }
    };
    set({ ws });
  },

  createNewProject: async (name) => {
    const folder = get().targetFolderInput.trim() || DEFAULT_OUTPUT_DIR;
    try {
      const res = await api.createProject({
        name: name || 'Untitled 3D Short',
        target_folder: folder,
      });
      set((s) => ({
        projects: [res.project, ...s.projects],
        activeProjectId: res.project.id,
        activeProject: res.project,
        messages: [],
        logs: [],
        progress: null,
        artifactTab: 'storyboard',
      }));
      get().connectWebSocket(res.project.id);
      await get().validateTargetFolder(folder);
      get().showToast('success', `Created project in ${folder}`);
      return res.project;
    } catch (e: any) {
      get().showToast('error', e.message);
      return null;
    }
  },

  selectProject: async (projectId) => {
    try {
      const res = await api.getProject(projectId);
      set({
        activeProjectId: projectId,
        activeProject: res.project,
        messages: res.messages,
        usage: res.usage,
        targetFolderInput: res.project.target_folder,
        logs: [],
        progress: null,
      });
      get().connectWebSocket(projectId);
      await get().validateTargetFolder(res.project.target_folder);
    } catch (e: any) {
      get().showToast('error', e.message);
    }
  },

  deleteProject: async (projectId) => {
    try {
      await api.deleteProject(projectId);
      const remaining = get().projects.filter((p) => p.id !== projectId);
      set({ projects: remaining });
      if (get().activeProjectId === projectId) {
        if (remaining.length > 0) {
          await get().selectProject(remaining[0].id);
        } else {
          set({ activeProjectId: null, activeProject: null, messages: [] });
        }
      }
      get().showToast('info', 'Project removed from studio history.');
    } catch (e: any) {
      get().showToast('error', e.message);
    }
  },

  saveStoryboardEdits: async (storyboard) => {
    const active = get().activeProject;
    if (!active) return;
    try {
      const res = await api.updateProject(active.id, { storyboard });
      set((s) => ({
        activeProject: res.project,
        projects: s.projects.map((p) => (p.id === res.project.id ? res.project : p)),
      }));
      get().showToast('success', 'Storyboard edits saved to project_meta.json');
    } catch (e: any) {
      get().showToast('error', e.message);
    }
  },

  sendPrompt: async (message) => {
    const trimmed = message.trim();
    if (!trimmed) return;

    let active = get().activeProject;
    if (!active) {
      active = await get().createNewProject(trimmed.slice(0, 42));
      if (!active) return;
    }

    const optimisticUser: ChatMessage = {
      id: Date.now(),
      project_id: active.id,
      role: 'user',
      content: trimmed,
      created_at: new Date().toISOString(),
    };
    set((s) => ({ isSendingChat: true, messages: [...s.messages, optimisticUser] }));

    try {
      const res = await api.sendChat(active.id, trimmed);
      set((s) => ({
        isSendingChat: false,
        activeProject: res.project,
        projects: s.projects.map((p) => (p.id === res.project.id ? res.project : p)),
        messages: [
          ...s.messages.filter((m) => m.id !== optimisticUser.id),
          res.user_message,
          res.assistant_message,
        ],
        usage: res.usage,
        artifactTab: 'storyboard',
      }));
    } catch (e: any) {
      set({ isSendingChat: false });
      get().showToast('error', e.message);
    }
  },

  generateVoiceover: async () => {
    const active = get().activeProject;
    if (!active) return;
    set({ isGeneratingVoice: true });
    try {
      const res = await api.generateVoiceover(active.id);
      set((s) => ({
        isGeneratingVoice: false,
        activeProject: res.project,
        projects: s.projects.map((p) => (p.id === res.project.id ? res.project : p)),
        mediaVersion: s.mediaVersion + 1,
      }));
      get().showToast('success', 'ElevenLabs narration & word timestamps synced 1:1 to Blender frames!');
    } catch (e: any) {
      set({ isGeneratingVoice: false });
      get().showToast('error', e.message);
    }
  },

  buildBlendProject: async (opts) => {
    const active = get().activeProject;
    if (!active) return;
    set({
      isPipelineRunning: true,
      artifactTab: 'console',
      progress: { stage: 'init', percent: 5, detail: 'Starting Blender build pipeline...' },
    });
    try {
      await api.buildProject(active.id, {
        render_previews: true,
        regenerate_scripts: opts?.regenerateScripts ?? false,
        scene_indices: opts?.sceneIndices,
      });
      get().showToast('info', 'Building project.blend & scene previews in Blender...');
    } catch (e: any) {
      set({ isPipelineRunning: false });
      get().showToast('error', e.message);
    }
  },

  rerenderScene: async (sceneIndex, regenerateScript = false) => {
    const active = get().activeProject;
    if (!active) return;
    set({
      isPipelineRunning: true,
      progress: { stage: 'blender', percent: 15, detail: `Re-rendering Scene ${sceneIndex}...` },
    });
    try {
      await api.rerenderScene(active.id, sceneIndex, regenerateScript);
      get().showToast('info', `Re-rendering Scene ${sceneIndex} preview...`);
    } catch (e: any) {
      set({ isPipelineRunning: false });
      get().showToast('error', e.message);
    }
  },

  openInBlender: async () => {
    const active = get().activeProject;
    if (!active) return;
    try {
      const res = await api.openInBlender(active.id);
      get().showToast('success', `Opened ${res.launched} in desktop Blender!`);
    } catch (e: any) {
      get().showToast('error', e.message);
    }
  },

  renderFinalShort: async () => {
    const active = get().activeProject;
    if (!active) return;
    const settings = get().settings;
    set({
      isPipelineRunning: true,
      artifactTab: 'console',
      progress: { stage: 'render', percent: 5, detail: 'Launching full 1080x1920 render...' },
    });
    try {
      await api.renderFinal(active.id, {
        render_engine: settings?.render_engine,
        cycles_samples: settings?.cycles_samples,
        include_sfx: true,
        burn_captions: true,
      });
      get().showToast('info', 'Rendering final 1080x1920 YouTube Short (.mp4)...');
    } catch (e: any) {
      set({ isPipelineRunning: false });
      get().showToast('error', e.message);
    }
  },

  saveSettings: async (next) => {
    try {
      const res = await api.saveSettings(next);
      set({ settings: res.settings });
      get().showToast('success', 'Studio settings saved.');
    } catch (e: any) {
      get().showToast('error', e.message);
    }
  },
}));
