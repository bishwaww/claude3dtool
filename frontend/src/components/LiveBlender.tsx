import React from 'react';
import { Box, Camera, Film, Loader2, Plug, RefreshCw } from 'lucide-react';
import { useStudioStore } from '../store/studioStore';

const fileName = (p?: string) => (p ? p.split(/[\\/]/).pop() : '');

/** Header badge: green = connected, amber = connecting, grey = offline. */
export const BlenderStatusBadge: React.FC = () => {
  const { blender, blenderBusy, launchBlender, activeProject } = useStudioStore();
  const connected = Boolean(blender?.connected);
  const onThisProject =
    connected && activeProject && blender?.file?.toLowerCase().startsWith(activeProject.target_folder.toLowerCase());

  if (blenderBusy === 'launching') {
    return (
      <span className="text-[11px] px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 flex items-center gap-1.5">
        <Loader2 className="w-3 h-3 animate-spin" /> Connecting Blender…
      </span>
    );
  }
  if (connected && onThisProject) {
    return (
      <span
        className="text-[11px] px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 flex items-center gap-1.5"
        title={`${blender?.file}\nBlender ${blender?.blender} · port ${blender?.port}`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        Blender Connected · {fileName(blender?.file)}
        {blender?.dirty ? ' •' : ''}
      </span>
    );
  }
  return (
    <button
      onClick={launchBlender}
      className="text-[11px] px-2.5 py-1 rounded-full bg-card hover:bg-cardHover border border-borderStrong text-ink flex items-center gap-1.5 transition-colors"
      title={connected ? `Blender is open on ${blender?.file} — switch it to this project` : blender?.error || 'Open Blender with the live bridge'}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-amber-400' : 'bg-inkDim'}`} />
      <Plug className="w-3 h-3 text-studioCyan" />
      {connected ? 'Switch Blender to this project' : 'Launch & Connect Blender'}
    </button>
  );
};

/** Artifact tab: what Claude sees in Blender, plus manual capture and live render. */
export const LiveBlenderTab: React.FC = () => {
  const { blender, blenderBusy, liveCaptures, liveRender, launchBlender, captureBlender, renderLive, activeProject } =
    useStudioStore();
  const connected = Boolean(blender?.connected);
  const latest = liveCaptures[0];
  const pct =
    liveRender?.running && liveRender.end && liveRender.start != null
      ? Math.round((100 * ((liveRender.frame ?? 0) - liveRender.start)) / Math.max(1, liveRender.end - liveRender.start))
      : null;

  return (
    <div className="p-4 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {!connected ? (
          <button
            onClick={launchBlender}
            disabled={blenderBusy === 'launching'}
            className="px-3 py-1.5 rounded-lg bg-accent hover:bg-accentHover disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1.5"
          >
            {blenderBusy === 'launching' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plug className="w-3.5 h-3.5" />}
            Launch & Connect Blender
          </button>
        ) : (
          <>
            <button
              onClick={captureBlender}
              disabled={!activeProject || blenderBusy === 'capturing'}
              className="px-3 py-1.5 rounded-lg bg-card hover:bg-cardHover border border-borderStrong text-ink text-xs font-medium flex items-center gap-1.5 disabled:opacity-50"
            >
              {blenderBusy === 'capturing' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Camera className="w-3.5 h-3.5 text-studioCyan" />}
              Capture camera view
            </button>
            <button
              onClick={() => renderLive('EEVEE')}
              disabled={!activeProject || liveRender?.running}
              className="px-3 py-1.5 rounded-lg bg-card hover:bg-cardHover border border-borderStrong text-ink text-xs font-medium flex items-center gap-1.5 disabled:opacity-50"
            >
              <Film className="w-3.5 h-3.5" /> Render frames (EEVEE)
            </button>
            <button
              onClick={() => renderLive('CYCLES')}
              disabled={!activeProject || liveRender?.running}
              className="px-3 py-1.5 rounded-lg bg-card hover:bg-cardHover border border-borderStrong text-ink text-xs font-medium flex items-center gap-1.5 disabled:opacity-50"
            >
              <Film className="w-3.5 h-3.5 text-emerald-400" /> Render frames (Cycles)
            </button>
            <button
              onClick={launchBlender}
              className="px-2 py-1.5 rounded-lg text-inkDim hover:text-ink text-xs flex items-center gap-1"
              title="Re-open this project's project.blend in the running Blender"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Re-sync project
            </button>
          </>
        )}
      </div>

      {liveRender?.running && (
        <div className="text-xs text-inkMuted">
          <div className="flex justify-between mb-1">
            <span>
              Rendering frame {liveRender.frame} of {liveRender.end}
            </span>
            <span className="font-mono">{pct ?? 0}%</span>
          </div>
          <div className="h-1.5 bg-canvas rounded-full overflow-hidden">
            <div className="h-full bg-emerald-500 transition-all" style={{ width: `${Math.max(3, pct ?? 0)}%` }} />
          </div>
        </div>
      )}

      {latest ? (
        <div className="space-y-2">
          <div className="text-[11px] text-inkDim font-mono">
            Latest camera view · {latest.camera ?? 'camera'} · frame {latest.frame ?? '–'}
          </div>
          <div className="mx-auto max-w-[360px] aspect-[9/16] rounded-xl overflow-hidden border border-borderStrong bg-black">
            <img src={latest.url} alt="Live Blender camera view" className="w-full h-full object-cover" />
          </div>
          {liveCaptures.length > 1 && (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {liveCaptures.slice(1).map((c) => (
                <img key={c.ts} src={c.url} alt="" className="h-24 aspect-[9/16] object-cover rounded-md border border-borderSubtle opacity-80" />
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-16 text-inkMuted">
          <Box className="w-8 h-8 mx-auto mb-3 text-inkDim" />
          <p className="text-sm">
            {connected
              ? 'Ask Claude to build a shot — every camera check it takes appears here.'
              : 'Connect Blender to watch Claude model, light and animate your Short live.'}
          </p>
        </div>
      )}
    </div>
  );
};
