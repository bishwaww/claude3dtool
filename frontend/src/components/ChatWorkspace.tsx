import React, { useEffect, useRef, useState } from 'react';
import { ArrowUp, Sparkles, Square, Cpu, Volume2, Folder, Wand2, Paperclip, Mic } from 'lucide-react';
import { ACCEPT, DraftTray, PURPOSES_BY_KIND, kindOf, type Draft } from './Attachments';
import type { AttachmentPurpose } from '../types';
import { api } from '../api/client';
import { useStudioStore } from '../store/studioStore';
import { MessageBubble, StreamingBubble } from './MessageBubble';
import { ModelPicker, ThinkingToggle } from './ChatComposerControls';
import { BlenderStatusBadge } from './LiveBlender';
import { desktop } from '../desktop';

const STARTER_PROMPTS = [
  'Make a 35s video on what happens if you swallow a tiny coin battery',
  'Explain how noise-cancelling headphones erase sound waves in 40 seconds',
  'What actually happens inside your ear when it pops on an airplane? (35s)',
  'Why does pouring water on a grease fire cause a massive explosion? (38s)',
];

export const ChatWorkspace: React.FC = () => {
  const {
    activeProject,
    messages,
    isSendingChat,
    sendPrompt,
    stopStreaming,
    streaming,
    settings,
    mediaVersion,
    targetFolderInput,
  } = useStudioStore();

  const { ensureProject, uploadVoiceover, showToast } = useStudioStore();
  const [input, setInput] = useState('');
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const voRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: streaming ? 'auto' : 'smooth' });
  }, [messages, isSendingChat, streaming?.text, streaming?.tools.length]);

  const patchDraft = (id: string, p: Partial<Draft>) =>
    setDrafts((ds) => ds.map((d) => (d.localId === id ? { ...d, ...p } : d)));

  const uploadDraft = async (d: Draft) => {
    const project = await ensureProject();
    if (!project) return patchDraft(d.localId, { status: 'error', error: 'No project' });
    try {
      const res = await api.uploadAttachments(project.id, [d.file], d.purpose);
      const view = res.attachments[0];
      patchDraft(d.localId, {
        status: view.status === 'error' ? 'error' : 'ready',
        view,
        error: view.error || undefined,
      });
      if (view.purpose === 'voiceover' && view.status === 'ready') {
        useStudioStore.setState((s) => ({
          activeProject: res.project,
          projects: s.projects.map((p) => (p.id === res.project.id ? res.project : p)),
          mediaVersion: s.mediaVersion + 1,
        }));
      }
    } catch (e: any) {
      patchDraft(d.localId, { status: 'error', error: e.message });
    }
  };

  const addFiles = (files: FileList | File[]) => {
    const list = Array.from(files).filter((f) => f.size > 0);
    if (!list.length) return;
    const tooBig = list.find((f) => f.size > 1024 * 1024 * 1024);
    if (tooBig) {
      showToast('error', `${tooBig.name} is larger than 1 GB.`);
      return;
    }
    const added: Draft[] = list.map((file) => {
      const kind = kindOf(file.name);
      return {
        localId: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        file,
        kind,
        purpose: PURPOSES_BY_KIND[kind][0],
        status: 'uploading',
        previewUrl: kind === 'image' ? URL.createObjectURL(file) : undefined,
      };
    });
    setDrafts((ds) => [...ds, ...added]);
    added.forEach(uploadDraft);
  };

  const changePurpose = (id: string, purpose: AttachmentPurpose) => {
    const d = drafts.find((x) => x.localId === id);
    if (!d || d.purpose === purpose) return;
    const next = { ...d, purpose, status: 'uploading' as const, view: undefined, error: undefined };
    patchDraft(id, next);
    uploadDraft(next);
  };

  const removeDraft = (id: string) =>
    setDrafts((ds) => {
      const d = ds.find((x) => x.localId === id);
      if (d?.previewUrl) URL.revokeObjectURL(d.previewUrl);
      return ds.filter((x) => x.localId !== id);
    });

  const uploading = drafts.some((d) => d.status === 'uploading');

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const ready = drafts.filter((d) => d.status === 'ready' && d.view).map((d) => d.view!);
    if ((!input.trim() && !ready.length) || isSendingChat || uploading) return;
    const text = input;
    setInput('');
    drafts.forEach((d) => d.previewUrl && URL.revokeObjectURL(d.previewUrl));
    setDrafts([]);
    await sendPrompt(text, ready);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
  };

  const onPaste = (e: React.ClipboardEvent) => {
    const files = Array.from(e.clipboardData.files || []);
    if (files.length) {
      e.preventDefault();
      addFiles(files);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const engineLabel =
    settings?.render_engine === 'CYCLES_OPTIX'
      ? `Cycles OptiX (${settings?.cycles_samples ?? 64} spp)`
      : 'EEVEE Next (Fast)';

  return (
    <section
      className="relative flex-1 min-w-[340px] flex flex-col h-full bg-canvas border-r border-borderSubtle"
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes('Files')) {
          e.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={onDrop}
    >
      {dragging && (
        <div className="absolute inset-0 z-40 bg-canvas/85 border-2 border-dashed border-accent rounded-xl m-2 flex flex-col items-center justify-center pointer-events-none">
          <Paperclip className="w-8 h-8 text-accent mb-2" />
          <div className="text-sm text-ink font-medium">Drop files for Claude</div>
          <div className="text-xs text-inkMuted mt-1">
            Reference images & videos · voiceover audio · .blend / .glb / .fbx / .obj assets · logo
          </div>
        </div>
      )}
      <input
        ref={fileRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          if (e.target.files) addFiles(e.target.files);
          e.target.value = '';
        }}
      />
      <input
        ref={voRef}
        type="file"
        accept="audio/*,video/*,.mp3,.wav,.m4a"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) uploadVoiceover(f);
          e.target.value = '';
        }}
      />
      {/* Top Bar */}
      <header className="h-14 px-5 border-b border-borderSubtle flex items-center justify-between shrink-0">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-ink truncate">
            {activeProject?.name || 'New 3D Explainer Short'}
          </h2>
          <div className="flex items-center gap-2 text-[11px] text-inkDim truncate">
            <Folder className="w-3 h-3 shrink-0" />
            <span className="font-mono truncate">
              {activeProject?.target_folder || targetFolderInput}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => voRef.current?.click()}
            className="text-[11px] px-2.5 py-1 rounded-full bg-card hover:bg-cardHover border border-borderStrong text-ink flex items-center gap-1.5"
            title="Use your own voiceover (ElevenLabs website, CapCut, mic…). It is word-timed with faster-whisper and the storyboard locks to it."
          >
            <Mic className="w-3 h-3 text-violet-400" />
            Upload voiceover
          </button>
          {!desktop && <BlenderStatusBadge />}
          <span className="text-[11px] px-2.5 py-1 rounded-full bg-card border border-borderStrong text-inkMuted hidden 2xl:flex items-center gap-1.5">
            <Cpu className="w-3 h-3 text-studioCyan" />
            {engineLabel}
          </span>
        </div>
      </header>

      {/* Optional Narration Audio Bar */}
      {activeProject?.has_audio && (
        <div className="px-5 py-2 bg-card/60 border-b border-borderSubtle flex items-center gap-3">
          <Volume2 className="w-4 h-4 text-accent shrink-0" />
          <span className="text-xs text-inkMuted shrink-0">Narration:</span>
          <audio
            key={`${activeProject.id}-${mediaVersion}`}
            controls
            src={api.narrationAudioUrl(activeProject.id, mediaVersion)}
            className="h-8 flex-1 max-w-md"
          />
        </div>
      )}

      {/* Conversation Feed */}
      <div className="flex-1 overflow-y-auto px-5 py-6">
        {messages.length === 0 ? (
          <div className="max-w-xl mx-auto mt-10 text-center">
            <div className="w-12 h-12 mx-auto rounded-2xl bg-accent/15 border border-accent/30 flex items-center justify-center mb-4">
              <Sparkles className="w-6 h-6 text-accent" />
            </div>
            <h3 className="text-xl font-semibold text-ink mb-2">
              Direct your next 3D Explainer Short
            </h3>
            <p className="text-sm text-inkMuted mb-7 leading-relaxed">
              Describe a topic or science mechanism. Stick Knowledge 3D Studio builds a native 9:16{' '}
              <span className="font-mono text-ink">project.blend</span> with radial cyan studio lighting,
              free 3D assets, diegetic <span className="text-ink font-medium">STICK KNOWLEDGE</span>{' '}
              branding, synced ElevenLabs voiceover, and crisp Shorts captions.
            </p>

            <div className="grid grid-cols-1 gap-2.5 text-left">
              {STARTER_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => sendPrompt(p)}
                  disabled={isSendingChat}
                  className="group p-3.5 rounded-xl bg-card hover:bg-cardHover border border-borderSubtle hover:border-borderStrong transition-all flex items-center justify-between gap-3"
                >
                  <span className="text-xs text-ink leading-relaxed">{p}</span>
                  <Wand2 className="w-4 h-4 text-inkDim group-hover:text-accent shrink-0 transition-colors" />
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto space-y-5">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}

            {streaming && <StreamingBubble {...streaming} />}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="p-4 border-t border-borderSubtle bg-canvas">
        <form
          onSubmit={handleSubmit}
          className="max-w-2xl mx-auto bg-card border border-borderStrong focus-within:border-accent/80 rounded-2xl p-2.5 transition-colors shadow-sm"
        >
          <DraftTray drafts={drafts} onRemove={removeDraft} onPurpose={changePurpose} />
          <textarea
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={onPaste}
            placeholder={
              messages.length > 0
                ? 'Ask for follow-up edits (e.g., "Zoom closer on scene 3 and put STICK KNOWLEDGE on the battery label")...'
                : 'Describe your 3D explainer Short topic (30–60s)...'
            }
            className="w-full bg-transparent resize-none px-2 py-1 text-sm text-ink placeholder:text-inkDim focus:outline-none"
          />
          <div className="flex items-center justify-between pt-1.5 px-1 gap-2">
            <div className="flex items-center gap-1 min-w-0">
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                title="Attach reference images/videos, a voiceover, 3D assets or a logo (or drag & drop / paste)"
                className="w-8 h-8 rounded-lg text-inkMuted hover:text-ink hover:bg-cardHover flex items-center justify-center"
              >
                <Paperclip className="w-4 h-4" />
              </button>
              <ThinkingToggle />
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <ModelPicker />
              {isSendingChat ? (
                <button
                  type="button"
                  onClick={stopStreaming}
                  title="Stop"
                  className="w-8 h-8 rounded-lg bg-ink/90 hover:bg-ink text-canvas flex items-center justify-center transition-colors"
                >
                  <Square className="w-3.5 h-3.5 fill-current" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={uploading || (!input.trim() && !drafts.some((d) => d.status === 'ready'))}
                  title={uploading ? 'Waiting for attachments to finish processing…' : 'Send (Enter)'}
                  className="w-8 h-8 rounded-lg bg-accent hover:bg-accentHover disabled:opacity-40 text-white flex items-center justify-center transition-colors"
                >
                  <ArrowUp className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </form>
      </div>
    </section>
  );
};
