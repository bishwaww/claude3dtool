import React from 'react';
import { AudioLines, Box, FileQuestion, Film, Image as ImageIcon, Loader2, X } from 'lucide-react';
import type { AttachmentPurpose, AttachmentView } from '../types';

export const ACCEPT =
  'image/*,video/*,audio/*,.blend,.glb,.gltf,.fbx,.obj,.stl,.usd,.usdz,.hdr,.exr,.zip,.mp3,.wav,.m4a,.aac,.ogg,.flac';

export type Kind = AttachmentView['kind'];

export function kindOf(name: string): Kind {
  const ext = name.toLowerCase().split('.').pop() || '';
  if (['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)) return 'image';
  if (['mp4', 'mov', 'webm', 'mkv', 'm4v', 'avi'].includes(ext)) return 'video';
  if (['mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac'].includes(ext)) return 'audio';
  if (['blend', 'glb', 'gltf', 'fbx', 'obj', 'stl', 'usd', 'usdz', 'hdr', 'exr', 'zip'].includes(ext)) return 'model';
  return 'other';
}

export const PURPOSES_BY_KIND: Record<Kind, AttachmentPurpose[]> = {
  image: ['reference', 'asset', 'logo'],
  video: ['reference', 'voiceover'],
  audio: ['voiceover'],
  model: ['asset'],
  other: ['asset'],
};

export const PURPOSE_LABEL: Record<AttachmentPurpose, string> = {
  reference: 'Reference',
  asset: '3D / texture asset',
  logo: 'Brand logo',
  voiceover: 'Voiceover',
};

export interface Draft {
  localId: string;
  file: File;
  kind: Kind;
  purpose: AttachmentPurpose;
  status: 'uploading' | 'ready' | 'error';
  view?: AttachmentView;
  error?: string;
  previewUrl?: string;
}

const KindIcon: React.FC<{ kind: Kind; className?: string }> = ({ kind, className }) => {
  const C = kind === 'image' ? ImageIcon : kind === 'video' ? Film : kind === 'audio' ? AudioLines : kind === 'model' ? Box : FileQuestion;
  return <C className={className} />;
};

/** Chips shown above the composer while attachments upload/process. */
export const DraftTray: React.FC<{
  drafts: Draft[];
  onRemove: (id: string) => void;
  onPurpose: (id: string, p: AttachmentPurpose) => void;
}> = ({ drafts, onRemove, onPurpose }) => {
  if (!drafts.length) return null;
  return (
    <div className="flex flex-wrap gap-2 px-1 pb-2">
      {drafts.map((d) => (
        <div
          key={d.localId}
          className={`relative flex items-center gap-2 pl-1.5 pr-2 py-1.5 rounded-xl border text-[11px] max-w-[260px] ${
            d.status === 'error' ? 'border-red-500/50 bg-red-500/10' : 'border-borderStrong bg-canvas'
          }`}
          title={d.error || d.view?.summary || d.file.name}
        >
          {d.previewUrl ? (
            <img src={d.previewUrl} alt="" className="w-9 h-9 rounded-md object-cover shrink-0" />
          ) : d.view?.thumb_url ? (
            <img src={d.view.thumb_url} alt="" className="w-9 h-9 rounded-md object-cover shrink-0" />
          ) : (
            <span className="w-9 h-9 rounded-md bg-card flex items-center justify-center shrink-0">
              <KindIcon kind={d.kind} className="w-4 h-4 text-inkMuted" />
            </span>
          )}
          <div className="min-w-0">
            <div className="text-ink truncate">{d.file.name}</div>
            <div className="flex items-center gap-1 text-inkDim">
              {d.status === 'uploading' && <Loader2 className="w-3 h-3 animate-spin text-accent" />}
              {PURPOSES_BY_KIND[d.kind].length > 1 && d.status !== 'uploading' ? (
                <select
                  value={d.purpose}
                  onChange={(e) => onPurpose(d.localId, e.target.value as AttachmentPurpose)}
                  className="bg-transparent text-inkMuted hover:text-ink focus:outline-none cursor-pointer"
                >
                  {PURPOSES_BY_KIND[d.kind].map((p) => (
                    <option key={p} value={p}>
                      {PURPOSE_LABEL[p]}
                    </option>
                  ))}
                </select>
              ) : (
                <span>{d.status === 'uploading' ? (d.kind === 'video' || d.kind === 'audio' ? 'Analysing…' : 'Uploading…') : PURPOSE_LABEL[d.purpose]}</span>
              )}
              {d.status === 'ready' && d.view?.summary && <span className="truncate">· {d.view.summary}</span>}
              {d.status === 'error' && <span className="text-red-300 truncate">· {d.error}</span>}
            </div>
          </div>
          <button
            type="button"
            onClick={() => onRemove(d.localId)}
            className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-cardHover border border-borderStrong flex items-center justify-center text-inkMuted hover:text-ink"
            title="Remove"
          >
            <X className="w-2.5 h-2.5" />
          </button>
        </div>
      ))}
    </div>
  );
};

/** Attachment chips inside a sent user message. */
export const SentAttachments: React.FC<{ items: AttachmentView[] }> = ({ items }) => (
  <div className="flex flex-wrap justify-end gap-2 mb-1.5">
    {items.map((a) =>
      a.thumb_url && (a.kind === 'image' || a.kind === 'video') ? (
        <a key={a.id} href={a.thumb_url} target="_blank" rel="noreferrer" title={`${a.filename} · ${PURPOSE_LABEL[a.purpose]}`}>
          <img src={a.thumb_url} alt={a.filename} className="h-24 max-w-[180px] object-cover rounded-lg border border-borderStrong" />
        </a>
      ) : (
        <span
          key={a.id}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-card border border-borderStrong text-[11px] text-ink"
          title={a.path}
        >
          <KindIcon kind={a.kind} className="w-3.5 h-3.5 text-inkMuted" />
          {a.filename}
          <span className="text-inkDim">· {a.summary || PURPOSE_LABEL[a.purpose]}</span>
        </span>
      )
    )}
  </div>
);
