import React from 'react';
import {
  Clapperboard,
  Image as ImageIcon,
  Terminal,
  Hammer,
  ExternalLink,
  Video,
  Loader2,
  Box,
} from 'lucide-react';
import { useStudioStore, type ArtifactTab } from '../store/studioStore';
import { LiveBlenderTab } from './LiveBlender';
import { StoryboardTab } from './StoryboardTab';
import { PreviewsTab } from './PreviewsTab';
import { ConsoleTab } from './ConsoleTab';

export const ArtifactPanel: React.FC = () => {
  const {
    activeProject,
    artifactTab,
    setArtifactTab,
    buildBlendProject,
    openInBlender,
    renderFinalShort,
    isPipelineRunning,
    progress,
  } = useStudioStore();

  const hasScenes = Boolean((activeProject?.storyboard as any)?.scenes?.length);

  const tabs: { id: ArtifactTab; label: string; icon: React.ReactNode }[] = [
    { id: 'storyboard', label: 'Storyboard & Script', icon: <Clapperboard className="w-3.5 h-3.5" /> },
    { id: 'live', label: 'Live Blender', icon: <Box className="w-3.5 h-3.5" /> },
    { id: 'previews', label: 'Live Scene Previews', icon: <ImageIcon className="w-3.5 h-3.5" /> },
    { id: 'console', label: 'Blender Console & Budget', icon: <Terminal className="w-3.5 h-3.5" /> },
  ];

  return (
    <section className="w-[50%] max-w-[780px] min-w-[440px] flex flex-col h-full bg-[#181715]">
      {/* Sticky Production Action Bar */}
      <div className="px-4 py-2.5 border-b border-borderSubtle flex flex-wrap items-center justify-between gap-2 bg-sidebar/70 shrink-0">
        <div className="flex items-center gap-1 bg-canvas p-1 rounded-lg border border-borderSubtle">
          {tabs.map((t) => {
            const active = artifactTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setArtifactTab(t.id)}
                className={`px-2.5 py-1.5 rounded-md text-xs font-medium flex items-center gap-1.5 transition-colors ${
                  active
                    ? 'bg-card text-ink shadow-sm'
                    : 'text-inkMuted hover:text-ink'
                }`}
              >
                {t.icon}
                <span className="hidden xl:inline">{t.label}</span>
                <span className="xl:hidden">{t.label.split(' ')[0]}</span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => buildBlendProject()}
            disabled={!hasScenes || isPipelineRunning}
            className="px-3 py-1.5 rounded-lg bg-accent hover:bg-accentHover disabled:opacity-40 text-white text-xs font-medium flex items-center gap-1.5 transition-colors"
            title="Resolve free 3D assets, generate scene scripts, save packed project.blend & render previews"
          >
            {isPipelineRunning ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Hammer className="w-3.5 h-3.5" />
            )}
            Build/Update .blend
          </button>

          <button
            onClick={() => openInBlender()}
            disabled={!activeProject?.has_blend}
            className="px-3 py-1.5 rounded-lg bg-card hover:bg-cardHover border border-borderStrong disabled:opacity-40 text-ink text-xs font-medium flex items-center gap-1.5 transition-colors"
            title="Launch project.blend directly in desktop Blender"
          >
            <ExternalLink className="w-3.5 h-3.5 text-studioCyan" />
            Open in Blender
          </button>

          <button
            onClick={() => renderFinalShort()}
            disabled={!hasScenes || isPipelineRunning}
            className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-xs font-medium flex items-center gap-1.5 transition-colors"
            title="Render 1080x1920 animation and assemble final_short.mp4 with audio & captions"
          >
            <Video className="w-3.5 h-3.5" />
            Render Short (.mp4)
          </button>
        </div>
      </div>

      {/* Live Pipeline Progress Bar */}
      {progress && (isPipelineRunning || progress.stage === 'error') && (
        <div className="px-4 py-2 bg-card border-b border-borderSubtle shrink-0">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="font-medium text-ink capitalize flex items-center gap-2">
              {isPipelineRunning && <Loader2 className="w-3.5 h-3.5 animate-spin text-accent" />}
              {progress.detail || progress.stage}
            </span>
            <span className="font-mono text-inkMuted">{progress.percent}%</span>
          </div>
          <div className="w-full h-1.5 bg-canvas rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                progress.stage === 'error' ? 'bg-rose-500' : 'bg-accent'
              }`}
              style={{ width: `${Math.max(4, progress.percent)}%` }}
            />
          </div>
        </div>
      )}

      {/* Active Tab Content */}
      <div className="flex-1 overflow-y-auto">
        {artifactTab === 'storyboard' && <StoryboardTab />}
        {artifactTab === 'live' && <LiveBlenderTab />}
        {artifactTab === 'previews' && <PreviewsTab />}
        {artifactTab === 'console' && <ConsoleTab />}
      </div>
    </section>
  );
};
