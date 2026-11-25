import React, { useEffect } from 'react';
import {
  Box,
  CheckCircle2,
  AlertCircle,
  FolderOpen,
  Layers,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Settings,
  Trash2,
  Film,
  Sparkles,
} from 'lucide-react';
import { useStudioStore } from '../store/studioStore';

export const Sidebar: React.FC = () => {
  const {
    sidebarOpen,
    setSidebarOpen,
    projects,
    activeProjectId,
    targetFolderInput,
    pathValidation,
    setTargetFolderInput,
    validateTargetFolder,
    pickTargetFolder,
    createNewProject,
    selectProject,
    deleteProject,
    setSettingsModalOpen,
    setAssetModalOpen,
    assetLibrary,
    usage,
  } = useStudioStore();

  useEffect(() => {
    const t = setTimeout(() => {
      if (targetFolderInput.trim()) {
        validateTargetFolder(targetFolderInput);
      }
    }, 450);
    return () => clearTimeout(t);
  }, [targetFolderInput]);

  if (!sidebarOpen) {
    return (
      <aside className="w-14 shrink-0 bg-sidebar border-r border-borderSubtle flex flex-col items-center py-3 gap-3">
        <button
          onClick={() => setSidebarOpen(true)}
          title="Expand Sidebar"
          className="p-2 rounded-lg text-inkMuted hover:text-ink hover:bg-card transition-colors"
        >
          <PanelLeftOpen className="w-5 h-5" />
        </button>
        <button
          onClick={() => createNewProject()}
          title="New 3D Short"
          className="p-2 rounded-lg bg-accent text-white hover:bg-accentHover transition-colors"
        >
          <Plus className="w-5 h-5" />
        </button>
        <div className="flex-1" />
        <button
          onClick={() => setAssetModalOpen(true)}
          title="Asset Library Manager"
          className="p-2 rounded-lg text-inkMuted hover:text-ink hover:bg-card transition-colors"
        >
          <Layers className="w-5 h-5" />
        </button>
        <button
          onClick={() => setSettingsModalOpen(true)}
          title="Studio Settings"
          className="p-2 rounded-lg text-inkMuted hover:text-ink hover:bg-card transition-colors"
        >
          <Settings className="w-5 h-5" />
        </button>
      </aside>
    );
  }

  const bkReady = assetLibrary?.blenderkit?.blenderkit_enabled || assetLibrary?.blenderkit?.copied_in_addons;
  const globalCost = usage?.global_totals?.cost_usd ?? 0;
  const budgetLimit = usage?.budget_limit_usd ?? 100;

  return (
    <aside className="w-72 shrink-0 bg-sidebar border-r border-borderSubtle flex flex-col h-full select-none">
      {/* Header */}
      <div className="px-4 py-3.5 flex items-center justify-between border-b border-borderSubtle">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-amber-600 flex items-center justify-center shadow-sm shrink-0">
            <Box className="w-4 h-4 text-white" />
          </div>
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-ink truncate leading-tight">
              Stick Knowledge
            </h1>
            <p className="text-[11px] text-inkMuted truncate">3D Studio · Blender Engine</p>
          </div>
        </div>
        <button
          onClick={() => setSidebarOpen(false)}
          title="Collapse Sidebar"
          className="p-1.5 rounded-md text-inkMuted hover:text-ink hover:bg-card transition-colors"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* New 3D Short CTA */}
      <div className="p-3">
        <button
          onClick={() => createNewProject()}
          className="w-full py-2.5 px-3 rounded-xl bg-accent hover:bg-accentHover text-white font-medium text-sm flex items-center justify-center gap-2 transition-colors shadow-sm"
        >
          <Plus className="w-4 h-4" />
          New 3D Short
        </button>
      </div>

      {/* Target Output Folder Picker & Validator */}
      <div className="px-3 pb-3 border-b border-borderSubtle">
        <label className="block text-[11px] font-medium uppercase tracking-wider text-inkMuted mb-1.5">
          Target Output Folder
        </label>
        <div className="flex items-center gap-1.5">
          <input
            type="text"
            value={targetFolderInput}
            onChange={(e) => setTargetFolderInput(e.target.value)}
            placeholder="D:\Videos\StickKnowledge\Ep01"
            className="flex-1 min-w-0 bg-canvas border border-borderStrong rounded-lg px-2.5 py-1.5 text-xs font-mono text-ink focus:outline-none focus:border-accent transition-colors"
          />
          <button
            onClick={pickTargetFolder}
            title="Browse Windows Folder"
            className="p-1.5 rounded-lg bg-card border border-borderStrong text-inkMuted hover:text-ink hover:bg-cardHover transition-colors shrink-0"
          >
            <FolderOpen className="w-4 h-4" />
          </button>
        </div>
        {pathValidation && (
          <div
            className={`mt-1.5 flex items-start gap-1.5 text-[11px] leading-snug ${
              pathValidation.valid ? 'text-emerald-400/90' : 'text-rose-400'
            }`}
          >
            {pathValidation.valid ? (
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            )}
            <span className="truncate" title={pathValidation.message}>
              {pathValidation.message}
            </span>
          </div>
        )}
      </div>

      {/* Project History */}
      <div className="flex-1 overflow-y-auto px-2 py-2.5">
        <div className="px-2 mb-1.5 flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-wider text-inkMuted">
            Projects ({projects.length})
          </span>
        </div>
        {projects.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-inkDim">
            No 3D Shorts yet. Click <span className="text-inkMuted">New 3D Short</span> or type a topic in chat.
          </div>
        ) : (
          <div className="space-y-1">
            {projects.map((p) => {
              const isActive = p.id === activeProjectId;
              return (
                <div
                  key={p.id}
                  onClick={() => selectProject(p.id)}
                  className={`group flex items-start gap-2.5 px-2.5 py-2 rounded-lg cursor-pointer transition-colors ${
                    isActive
                      ? 'bg-card text-ink border border-borderStrong'
                      : 'text-inkMuted hover:bg-card/50 hover:text-ink border border-transparent'
                  }`}
                >
                  <Film className={`w-4 h-4 shrink-0 mt-0.5 ${isActive ? 'text-accent' : 'text-inkDim'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium truncate">{p.name}</div>
                    <div className="flex items-center gap-1.5 mt-1">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-canvas text-inkMuted capitalize">
                        {p.status}
                      </span>
                      {p.has_blend && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 font-mono">
                          .blend
                        </span>
                      )}
                      {p.has_final && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 font-mono">
                          .mp4
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteProject(p.id);
                    }}
                    title="Delete from history"
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-canvas text-inkDim hover:text-rose-400 transition-all"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Bottom Utility Buttons */}
      <div className="p-3 border-t border-borderSubtle space-y-1.5">
        {/* Mini API Budget Meter */}
        <div className="px-2.5 py-2 rounded-lg bg-canvas border border-borderSubtle mb-2">
          <div className="flex items-center justify-between text-[11px] mb-1">
            <span className="text-inkMuted flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-accent" /> API Budget
            </span>
            <span className="font-mono text-ink">
              ${globalCost.toFixed(3)} / ${budgetLimit.toFixed(0)}
            </span>
          </div>
          <div className="w-full h-1.5 bg-card rounded-full overflow-hidden">
            <div
              className="h-full bg-accent rounded-full transition-all"
              style={{ width: `${Math.min(100, (globalCost / Math.max(1, budgetLimit)) * 100)}%` }}
            />
          </div>
        </div>

        <button
          onClick={() => setAssetModalOpen(true)}
          className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs text-inkMuted hover:text-ink hover:bg-card transition-colors"
        >
          <span className="flex items-center gap-2">
            <Layers className="w-4 h-4" />
            Asset Library Manager
          </span>
          <span
            className={`w-2 h-2 rounded-full ${bkReady ? 'bg-emerald-400' : 'bg-amber-400'}`}
            title={bkReady ? 'BlenderKit synced' : 'BlenderKit needs sync'}
          />
        </button>

        <button
          onClick={() => setSettingsModalOpen(true)}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-inkMuted hover:text-ink hover:bg-card transition-colors"
        >
          <Settings className="w-4 h-4" />
          Studio Settings
        </button>

        <div className="pt-1.5 text-center text-[10px] text-inkDim">
          Assets via{' '}
          <a
            href="https://polyhaven.com"
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-inkMuted"
          >
            Poly Haven
          </a>{' '}
          · BlenderKit · NIH 3D · Mixamo
        </div>
      </div>
    </aside>
  );
};
