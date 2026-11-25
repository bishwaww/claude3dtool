import React, { useEffect, useRef, useState } from 'react';
import { ExternalLink, FolderOpen, Loader2, PersonStanding, Play, RefreshCw, Upload, User } from 'lucide-react';
import { api } from '../api/client';
import { useStudioStore } from '../store/studioStore';
import type { MixamoItem, MixamoLibrary } from '../types';

const Item: React.FC<{ item: MixamoItem }> = ({ item }) => (
  <div className="p-2.5 rounded-lg bg-card border border-borderSubtle" title={item.path}>
    <div className="font-medium text-ink truncate">{item.name}</div>
    <div className="flex flex-wrap gap-1 mt-1 text-[10px] font-mono">
      {item.kind === 'character' ? (
        <span className="px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-300">{item.bones} bones · rigged mesh</span>
      ) : item.kind === 'animation' ? (
        <span className="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300">
          {item.frames} frames · {((item.frames || 0) / 30).toFixed(1)} s
        </span>
      ) : (
        <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300">{item.error ? 'unreadable' : item.kind}</span>
      )}
      {item.bone_prefix && <span className="px-1.5 py-0.5 rounded bg-canvas text-inkMuted">{item.bone_prefix}</span>}
      <span className="px-1.5 py-0.5 rounded bg-canvas text-inkDim">{item.size_kb} KB</span>
    </div>
  </div>
);

/** Mixamo character & animation library (indexed by a headless Blender probe). */
export const MixamoPanel: React.FC = () => {
  const { activeProject, showToast } = useStudioStore();
  const [lib, setLib] = useState<MixamoLibrary | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async (refresh = false) => {
    setBusy(true);
    try {
      setLib(await api.mixamoLibrary(refresh, activeProject?.id ?? ''));
    } catch (e: any) {
      showToast('error', e.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.id]);

  const onFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    try {
      const res = await api.mixamoUpload(Array.from(files));
      setLib(res.library);
      showToast('success', `Added ${res.saved.length} Mixamo file(s) to the library.`);
    } catch (e: any) {
      showToast('error', e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-4 rounded-xl bg-canvas border border-borderSubtle space-y-3">
      <input ref={fileRef} type="file" multiple accept=".fbx" className="hidden" onChange={(e) => onFiles(e.target.files)} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-semibold text-ink">
          <User className="w-4 h-4 text-violet-400" />
          Mixamo Characters & Animations
          {busy && <Loader2 className="w-3.5 h-3.5 animate-spin text-accent" />}
        </div>
        <div className="flex flex-wrap gap-1.5">
          <a
            href="https://www.mixamo.com/"
            target="_blank"
            rel="noreferrer"
            className="px-2.5 py-1 rounded-lg bg-card hover:bg-cardHover border border-borderStrong text-[11px] text-ink flex items-center gap-1"
          >
            <ExternalLink className="w-3 h-3" /> mixamo.com
          </a>
          <button
            onClick={() => fileRef.current?.click()}
            className="px-2.5 py-1 rounded-lg bg-card hover:bg-cardHover border border-borderStrong text-[11px] text-ink flex items-center gap-1"
          >
            <Upload className="w-3 h-3" /> Add .fbx
          </button>
          {lib?.folder && (
            <button
              onClick={() => api.openFolder(lib.folder).catch((e) => showToast('error', e.message))}
              className="px-2.5 py-1 rounded-lg bg-card hover:bg-cardHover border border-borderStrong text-[11px] text-ink flex items-center gap-1"
            >
              <FolderOpen className="w-3 h-3" /> Open folder
            </button>
          )}
          <button
            onClick={() => load(true)}
            className="px-2.5 py-1 rounded-lg bg-card hover:bg-cardHover border border-borderStrong text-[11px] text-ink flex items-center gap-1"
          >
            <RefreshCw className="w-3 h-3" /> Rescan
          </button>
        </div>
      </div>
      <div className="text-[11px] text-inkDim leading-relaxed">
        On mixamo.com pick a character and download it as <span className="text-inkMuted">FBX Binary · With Skin</span>; for
        animations choose <span className="text-inkMuted">Without Skin</span> (tick <span className="text-inkMuted">In Place</span>{' '}
        for walks/runs). Drop the files here or into <span className="font-mono">{lib?.folder || 'assets_library/mixamo'}</span>. Claude
        sees them through <span className="font-mono">list_assets</span> and imports them into Blender with clean scale and NLA
        clip blending.
      </div>
      {lib && (
        <>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-inkDim mb-1.5 flex items-center gap-1">
              <PersonStanding className="w-3 h-3" /> Characters ({lib.characters.length})
            </div>
            {lib.characters.length ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">{lib.characters.map((i) => <Item key={i.path} item={i} />)}</div>
            ) : (
              <div className="text-[11px] text-inkDim">No characters yet.</div>
            )}
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-inkDim mb-1.5 flex items-center gap-1">
              <Play className="w-3 h-3" /> Animation clips ({lib.animations.length})
            </div>
            {lib.animations.length ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">{lib.animations.map((i) => <Item key={i.path} item={i} />)}</div>
            ) : (
              <div className="text-[11px] text-inkDim">No animation clips yet.</div>
            )}
          </div>
          {lib.other.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">{lib.other.map((i) => <Item key={i.path} item={i} />)}</div>
          )}
        </>
      )}
    </div>
  );
};
