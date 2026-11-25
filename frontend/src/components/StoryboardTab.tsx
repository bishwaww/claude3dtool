import React, { useEffect, useState } from 'react';
import {
  Camera,
  Clock,
  Layers,
  Mic,
  Save,
  Scissors,
  Sparkles,
  Tag,
  Sun,
  Moon,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { useStudioStore } from '../store/studioStore';
import type { SceneSpec, StoryboardPlan } from '../types';

const SOURCE_BADGE_STYLES: Record<string, string> = {
  blenderkit: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  polyhaven: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  mixamo: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
  nih3d: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  huggingface: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  procedural: 'bg-zinc-500/20 text-zinc-300 border-zinc-500/30',
};

export const StoryboardTab: React.FC = () => {
  const {
    activeProject,
    saveStoryboardEdits,
    generateVoiceover,
    isGeneratingVoice,
    rerenderScene,
    isPipelineRunning,
  } = useStudioStore();

  const sb = activeProject?.storyboard as StoryboardPlan | undefined;
  const [draft, setDraft] = useState<StoryboardPlan | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (sb && Array.isArray(sb.scenes) && sb.scenes.length > 0) {
      setDraft(JSON.parse(JSON.stringify(sb)));
      setDirty(false);
    } else {
      setDraft(null);
      setDirty(false);
    }
  }, [activeProject?.id, activeProject?.updated_at]);

  if (!draft || !draft.scenes?.length) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-10 text-center text-inkMuted">
        <Sparkles className="w-9 h-9 text-inkDim mb-3" />
        <p className="text-sm font-medium text-ink mb-1">No Storyboard Generated Yet</p>
        <p className="text-xs text-inkDim max-w-sm">
          Enter a topic in the chat on the left to generate a scene-by-scene Zack D. Films-style 3D
          explainer storyboard with diegetic STICK KNOWLEDGE branding.
        </p>
      </div>
    );
  }

  const updateScene = (idx: number, patch: Partial<SceneSpec>) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const scenes = prev.scenes.map((s) => (s.scene_index === idx ? { ...s, ...patch } : s));
      return {
        ...prev,
        scenes,
        full_narration: scenes.map((s) => s.narration.trim()).join(' '),
      };
    });
    setDirty(true);
  };

  const handleSave = async () => {
    if (!draft) return;
    await saveStoryboardEdits(draft);
    setDirty(false);
  };

  return (
    <div className="p-4 space-y-4">
      {/* Top Plan Summary Card */}
      <div className="p-4 rounded-xl bg-card border border-borderSubtle space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-base font-semibold text-ink">{draft.title}</h3>
            <p className="text-xs text-inkMuted mt-1 italic">“{draft.hook}”</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={generateVoiceover}
              disabled={isGeneratingVoice}
              className="px-3 py-1.5 rounded-lg bg-studioCyan/15 hover:bg-studioCyan/25 border border-studioCyan/30 text-studioCyan text-xs font-medium flex items-center gap-1.5 transition-colors"
            >
              {isGeneratingVoice ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Mic className="w-3.5 h-3.5" />
              )}
              Generate Voiceover & Sync
            </button>

            {dirty && (
              <button
                onClick={handleSave}
                className="px-3 py-1.5 rounded-lg bg-accent hover:bg-accentHover text-white text-xs font-medium flex items-center gap-1.5 transition-colors"
              >
                <Save className="w-3.5 h-3.5" />
                Save Edits
              </button>
            )}
          </div>
        </div>

        {/* Metadata Strip */}
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span className="px-2 py-1 rounded-md bg-canvas border border-borderSubtle text-inkMuted flex items-center gap-1 font-mono">
            <Clock className="w-3 h-3 text-accent" />
            {draft.total_duration_sec.toFixed(1)}s · {draft.scenes.length} scenes · {draft.fps}fps
          </span>
          <span className="px-2 py-1 rounded-md bg-accent/15 border border-accent/30 text-accent flex items-center gap-1">
            <Tag className="w-3 h-3" />
            STICK KNOWLEDGE ({draft.branding_placement?.mode || 'prop_wrap'} · Scene{' '}
            {draft.branding_placement?.scene_index || 1})
          </span>
        </div>

        {draft.branding_placement?.description && (
          <div className="text-xs text-inkMuted bg-canvas/70 rounded-lg px-3 py-2 border border-borderSubtle">
            <span className="text-ink font-medium">Diegetic Branding Plan:</span>{' '}
            {draft.branding_placement.description}
          </div>
        )}
      </div>

      {/* Editable Scene Cards */}
      <div className="space-y-3">
        {draft.scenes.map((scene) => (
          <div
            key={scene.scene_index}
            className="p-4 rounded-xl bg-card border border-borderSubtle hover:border-borderStrong transition-colors space-y-3"
          >
            {/* Scene Header */}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-md bg-accent/20 text-accent font-mono text-xs font-semibold">
                  S{String(scene.scene_index).padStart(2, '0')}
                </span>
                <input
                  value={scene.title}
                  onChange={(e) => updateScene(scene.scene_index, { title: e.target.value })}
                  className="bg-transparent text-sm font-semibold text-ink focus:outline-none focus:bg-canvas px-1.5 py-0.5 rounded"
                />
              </div>

              <div className="flex items-center gap-1.5 text-[11px] font-mono">
                <span className="px-2 py-0.5 rounded bg-canvas text-inkMuted">
                  {scene.duration_sec.toFixed(1)}s · F{scene.start_frame}–{scene.end_frame}
                </span>

                <button
                  onClick={() =>
                    updateScene(scene.scene_index, {
                      bg_mode: scene.bg_mode === 'cyan_studio' ? 'dark_space' : 'cyan_studio',
                    })
                  }
                  className={`px-2 py-0.5 rounded border flex items-center gap-1 ${
                    scene.bg_mode === 'cyan_studio'
                      ? 'bg-sky-500/15 border-sky-500/30 text-sky-300'
                      : 'bg-indigo-950/80 border-indigo-500/30 text-indigo-300'
                  }`}
                  title="Toggle Studio Backdrop Mode"
                >
                  {scene.bg_mode === 'cyan_studio' ? (
                    <>
                      <Sun className="w-3 h-3" /> Cyan Studio
                    </>
                  ) : (
                    <>
                      <Moon className="w-3 h-3" /> Dark Space
                    </>
                  )}
                </button>

                {scene.cutaway_needed && (
                  <span className="px-2 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30 flex items-center gap-1">
                    <Scissors className="w-3 h-3" /> Cutaway
                  </span>
                )}

                {scene.has_branding && (
                  <span className="px-2 py-0.5 rounded bg-accent/20 text-accent border border-accent/30 font-sans font-semibold">
                    STICK KNOWLEDGE
                  </span>
                )}

                <button
                  onClick={() => rerenderScene(scene.scene_index, true)}
                  disabled={isPipelineRunning}
                  title="Regenerate this scene's bpy script & re-render preview"
                  className="p-1 rounded bg-canvas hover:bg-cardHover text-inkMuted hover:text-ink border border-borderSubtle"
                >
                  <RefreshCw className="w-3 h-3" />
                </button>
              </div>
            </div>

            {/* Narration */}
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-inkDim mb-1">
                Voiceover Narration
              </label>
              <textarea
                rows={2}
                value={scene.narration}
                onChange={(e) => updateScene(scene.scene_index, { narration: e.target.value })}
                className="w-full bg-canvas border border-borderSubtle focus:border-accent rounded-lg px-3 py-2 text-xs text-ink leading-relaxed focus:outline-none resize-none"
              />
            </div>

            {/* Visual & Camera Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-inkDim mb-1">
                  3D Action & Staging
                </label>
                <textarea
                  rows={2}
                  value={scene.visual_description}
                  onChange={(e) =>
                    updateScene(scene.scene_index, { visual_description: e.target.value })
                  }
                  className="w-full bg-canvas border border-borderSubtle focus:border-accent rounded-lg px-2.5 py-1.5 text-xs text-inkMuted focus:text-ink focus:outline-none resize-none"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-inkDim mb-1 flex items-center gap-1">
                  <Camera className="w-3 h-3" /> Camera Move
                </label>
                <input
                  value={scene.camera_move}
                  onChange={(e) => updateScene(scene.scene_index, { camera_move: e.target.value })}
                  className="w-full bg-canvas border border-borderSubtle focus:border-accent rounded-lg px-2.5 py-1.5 text-xs text-inkMuted focus:text-ink focus:outline-none"
                />
                {scene.overlays?.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {scene.overlays.map((ov, i) => (
                      <span
                        key={i}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-canvas border border-borderSubtle text-inkMuted font-mono"
                      >
                        {ov}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Resolved 3D Assets */}
            {scene.assets?.length > 0 && (
              <div className="pt-1 border-t border-borderSubtle/70">
                <div className="text-[10px] uppercase tracking-wider text-inkDim mb-1.5 flex items-center gap-1">
                  <Layers className="w-3 h-3" /> 3D Assets ({scene.assets.length})
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {scene.assets.map((asset) => {
                    const src = (asset.resolved_source || 'pending').toLowerCase();
                    const cls =
                      SOURCE_BADGE_STYLES[src] ||
                      'bg-canvas text-inkDim border-borderSubtle';
                    return (
                      <div
                        key={asset.asset_id}
                        className={`px-2 py-1 rounded-md border text-[11px] flex items-center gap-1.5 ${cls}`}
                        title={asset.local_path || asset.query}
                      >
                        <span className="font-medium">{asset.display_name || asset.query}</span>
                        <span className="text-[10px] opacity-75 uppercase font-mono">
                          {asset.resolved_source || asset.category}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
