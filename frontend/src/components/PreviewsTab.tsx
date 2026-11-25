import React, { useState } from 'react';
import {
  Image as ImageIcon,
  RefreshCw,
  Maximize2,
  X,
  Film,
  Sparkles,
} from 'lucide-react';
import { api } from '../api/client';
import { useStudioStore } from '../store/studioStore';
import type { StoryboardPlan } from '../types';

export const PreviewsTab: React.FC = () => {
  const {
    activeProject,
    mediaVersion,
    rerenderScene,
    isPipelineRunning,
    buildBlendProject,
  } = useStudioStore();

  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);
  const sb = activeProject?.storyboard as StoryboardPlan | undefined;
  const scenes = sb?.scenes || [];

  if (!activeProject || scenes.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-10 text-center text-inkMuted">
        <ImageIcon className="w-9 h-9 text-inkDim mb-3" />
        <p className="text-sm font-medium text-ink mb-1">No Scene Previews Yet</p>
        <p className="text-xs text-inkDim max-w-sm">
          Create a storyboard and click <span className="text-ink">Build/Update .blend</span> to
          render fast 9:16 preview frames directly from Blender.
        </p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-5">
      {/* Final Rendered Short Preview Card (when available) */}
      {activeProject.has_final && (
        <div className="p-4 rounded-xl bg-card border border-emerald-500/30 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Film className="w-4 h-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-ink">Final Rendered Short (1080×1920)</h3>
            </div>
            <span className="text-[11px] font-mono text-emerald-400">final_short.mp4</span>
          </div>
          <div className="flex justify-center bg-black/50 rounded-xl p-3">
            <video
              key={`final-${activeProject.id}-${mediaVersion}`}
              src={api.finalVideoUrl(activeProject.id, mediaVersion)}
              controls
              className="max-h-[420px] rounded-lg shadow-lg"
            />
          </div>
        </div>
      )}

      {/* Per-Scene 9:16 Preview Grid */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-inkMuted">
          Blender Scene Previews ({scenes.length})
        </h3>
        <button
          onClick={() => buildBlendProject({ regenerateScripts: false })}
          disabled={isPipelineRunning}
          className="text-xs text-accent hover:text-accentHover flex items-center gap-1"
        >
          <Sparkles className="w-3.5 h-3.5" /> Re-render All Previews
        </button>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-3 gap-3.5">
        {scenes.map((scene) => {
          const hasPreview = Boolean(scene.preview_path) || scene.render_status === 'preview_ready' || scene.render_status === 'rendered';
          const imgUrl = api.previewImageUrl(activeProject.id, scene.scene_index, mediaVersion);

          return (
            <div
              key={scene.scene_index}
              className="rounded-xl bg-card border border-borderSubtle overflow-hidden flex flex-col"
            >
              {/* 9:16 Frame Area */}
              <div className="relative aspect-[9/16] bg-canvas flex items-center justify-center overflow-hidden group">
                {hasPreview ? (
                  <>
                    <img
                      src={imgUrl}
                      alt={`Scene ${scene.scene_index}`}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.display = 'none';
                      }}
                    />
                    <button
                      onClick={() => setLightboxIdx(scene.scene_index)}
                      className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Expand Preview"
                    >
                      <Maximize2 className="w-3.5 h-3.5" />
                    </button>
                  </>
                ) : (
                  <div className="text-center p-4 text-inkDim">
                    <ImageIcon className="w-6 h-6 mx-auto mb-1.5 opacity-50" />
                    <span className="text-[11px]">Not rendered yet</span>
                  </div>
                )}

                <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/70 text-[10px] font-mono text-white">
                  S{String(scene.scene_index).padStart(2, '0')} · {scene.duration_sec.toFixed(1)}s
                </div>
              </div>

              {/* Card Footer */}
              <div className="p-2.5 space-y-2">
                <div className="text-xs font-medium text-ink truncate" title={scene.title}>
                  {scene.title}
                </div>
                <button
                  onClick={() => rerenderScene(scene.scene_index, false)}
                  disabled={isPipelineRunning}
                  className="w-full py-1.5 px-2 rounded-lg bg-canvas hover:bg-cardHover border border-borderSubtle text-[11px] text-inkMuted hover:text-ink flex items-center justify-center gap-1.5 transition-colors disabled:opacity-40"
                >
                  <RefreshCw className="w-3 h-3" />
                  Re-render Scene
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Lightbox Modal */}
      {lightboxIdx !== null && (
        <div
          className="fixed inset-0 z-50 bg-black/85 flex items-center justify-center p-6"
          onClick={() => setLightboxIdx(null)}
        >
          <div className="relative max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setLightboxIdx(null)}
              className="absolute -top-10 right-0 p-1.5 rounded-lg bg-card text-ink hover:bg-cardHover"
            >
              <X className="w-5 h-5" />
            </button>
            <img
              src={api.previewImageUrl(activeProject.id, lightboxIdx, mediaVersion)}
              alt={`Scene ${lightboxIdx}`}
              className="max-h-[85vh] rounded-xl border border-borderStrong shadow-2xl"
            />
          </div>
        </div>
      )}
    </div>
  );
};
