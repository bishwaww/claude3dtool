import React, { useEffect, useState } from 'react';
import {
  X,
  Layers,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Search,
  Loader2,
  User,
  Box,
  HeartPulse,
  Sparkles,
} from 'lucide-react';
import { api } from '../api/client';
import { useStudioStore } from '../store/studioStore';
import { MixamoPanel } from './MixamoPanel';

export const AssetLibraryModal: React.FC = () => {
  const {
    assetModalOpen,
    setAssetModalOpen,
    assetLibrary,
    refreshAssetLibrary,
    showToast,
  } = useStudioStore();

  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('coffee mug');
  const [searching, setSearching] = useState(false);
  const [searchRes, setSearchRes] = useState<{ blenderkit: any[]; polyhaven: any[] } | null>(null);

  useEffect(() => {
    if (assetModalOpen) {
      refreshAssetLibrary();
    }
  }, [assetModalOpen]);

  if (!assetModalOpen) return null;

  const handleRefresh = async () => {
    setRefreshing(true);
    await refreshAssetLibrary();
    setRefreshing(false);
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await api.searchAssets(searchQuery.trim());
      setSearchRes({ blenderkit: res.blenderkit, polyhaven: res.polyhaven });
    } catch (err: any) {
      showToast('error', err.message);
    } finally {
      setSearching(false);
    }
  };

  const bk = assetLibrary?.blenderkit;
  const cat = assetLibrary?.catalog;

  return (
    <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
      <div className="w-full max-w-3xl max-h-[88vh] bg-card border border-borderStrong rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-borderSubtle flex items-center justify-between bg-sidebar">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-studioCyan" />
            <h2 className="text-sm font-semibold text-ink">
              100% Free 3D Asset Library Manager
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="px-2.5 py-1 rounded-lg bg-card hover:bg-cardHover border border-borderSubtle text-xs text-inkMuted flex items-center gap-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              Rescan
            </button>
            <button
              onClick={() => setAssetModalOpen(false)}
              className="p-1 rounded-lg text-inkMuted hover:text-ink hover:bg-card"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs">
          {/* Tier 1: BlenderKit + MPFB2 Status */}
          <div className="p-4 rounded-xl bg-canvas border border-borderSubtle space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Box className="w-4 h-4 text-sky-400" />
                <span className="font-semibold text-ink">
                  BlenderKit Local Add-on & Blender Environment
                </span>
              </div>
              {bk?.blenderkit_enabled || bk?.copied_in_addons ? (
                <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 text-[11px] flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Ready (v{bk?.source_version || 'ok'})
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 text-[11px] flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> Needs Sync in Settings
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] font-mono text-inkMuted">
              <div className="p-2 rounded bg-card truncate" title={bk?.source_path}>
                Source: {bk?.source_path || 'D:\\B Software LK\\blender.crt\\blenderkit'}
              </div>
              <div className="p-2 rounded bg-card truncate" title={bk?.blender_path}>
                Blender: {bk?.blender_version || 'Not detected'} ({bk?.blender_path || '—'})
              </div>
            </div>

            <div className="flex flex-wrap gap-2 text-[11px]">
              <span
                className={`px-2 py-0.5 rounded border ${
                  bk?.mpfb2_installed
                    ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
                    : 'bg-card border-borderSubtle text-inkDim'
                }`}
              >
                MPFB2 Procedural Humans: {bk?.mpfb2_installed ? 'Installed & Detected' : 'Not Installed'}
              </span>
              <span className="px-2 py-0.5 rounded bg-card border border-borderSubtle text-inkMuted">
                BlenderKit Cache: {cat?.blenderkit_cache?.length ?? 0} `.blend` files
              </span>
              <span className="px-2 py-0.5 rounded bg-card border border-borderSubtle text-inkMuted">
                Poly Haven CC0 Cache: {cat?.polyhaven_cache?.length ?? 0} files
              </span>
            </div>
          </div>

          {/* Live Free Asset Search Tester (BlenderKit Free + Poly Haven CC0) */}
          <div className="p-4 rounded-xl bg-canvas border border-borderSubtle space-y-3">
            <div className="flex items-center gap-2 font-semibold text-ink">
              <Sparkles className="w-4 h-4 text-accent" />
              Test Live Free Search (BlenderKit Free + Poly Haven CC0)
            </div>
            <form onSubmit={handleSearch} className="flex gap-2">
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search free 3D props (e.g., mug, table, phone, battery, bottle)..."
                className="flex-1 bg-card border border-borderStrong rounded-lg px-3 py-2 text-ink focus:outline-none focus:border-accent"
              />
              <button
                type="submit"
                disabled={searching}
                className="px-4 py-2 rounded-lg bg-accent hover:bg-accentHover text-white font-medium flex items-center gap-1.5"
              >
                {searching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                Search
              </button>
            </form>

            {searchRes && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                <div className="space-y-1.5">
                  <div className="text-[11px] font-semibold text-sky-400">
                    BlenderKit Free ({searchRes.blenderkit.length})
                  </div>
                  {searchRes.blenderkit.length === 0 ? (
                    <div className="text-[11px] text-inkDim">No free matches returned.</div>
                  ) : (
                    searchRes.blenderkit.map((it) => (
                      <div key={it.id} className="p-2 rounded-lg bg-card flex items-center gap-2.5">
                        {it.thumbnail && (
                          <img src={it.thumbnail} alt="" className="w-9 h-9 rounded object-cover shrink-0" />
                        )}
                        <div className="min-w-0">
                          <div className="text-ink truncate font-medium">{it.name}</div>
                          <div className="text-[10px] text-inkDim uppercase">{it.asset_type} · Free</div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
                <div className="space-y-1.5">
                  <div className="text-[11px] font-semibold text-emerald-400">
                    Poly Haven CC0 ({searchRes.polyhaven.length})
                  </div>
                  {searchRes.polyhaven.length === 0 ? (
                    <div className="text-[11px] text-inkDim">No CC0 matches returned.</div>
                  ) : (
                    searchRes.polyhaven.map((it) => (
                      <div key={it.id} className="p-2 rounded-lg bg-card flex items-center gap-2.5">
                        {it.thumbnail && (
                          <img src={it.thumbnail} alt="" className="w-9 h-9 rounded object-cover shrink-0" />
                        )}
                        <div className="min-w-0">
                          <div className="text-ink truncate font-medium">{it.name}</div>
                          <div className="text-[10px] text-inkDim uppercase">CC0 · Poly Haven</div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Mixamo library (indexed with a headless Blender probe) */}
          <MixamoPanel />

          {/* NIH 3D Anatomy Cache */}
          <div className="p-4 rounded-xl bg-canvas border border-borderSubtle space-y-2">
            <div className="flex items-center gap-2 font-semibold text-ink">
              <HeartPulse className="w-4 h-4 text-rose-400" />
              NIH 3D Anatomy Cache ({cat?.anatomy?.length ?? 0})
            </div>
            {!cat?.anatomy?.length ? (
              <div className="text-[11px] text-inkDim">
                Anatomy `.glb` models fetched from `3d.nih.gov` automatically cache here for instant reuse.
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {cat.anatomy.map((a) => (
                  <span
                    key={a.path}
                    className="px-2.5 py-1 rounded-lg bg-card border border-borderSubtle text-ink text-[11px]"
                  >
                    {a.name} ({a.size_kb} KB)
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
