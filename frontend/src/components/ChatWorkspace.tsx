import React, { useEffect, useRef, useState } from 'react';
import {
  Send,
  Sparkles,
  Loader2,
  Cpu,
  Volume2,
  Folder,
  Wand2,
} from 'lucide-react';
import { api } from '../api/client';
import { useStudioStore } from '../store/studioStore';

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
    settings,
    mediaVersion,
    targetFolderInput,
  } = useStudioStore();

  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSendingChat]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isSendingChat) return;
    const text = input;
    setInput('');
    await sendPrompt(text);
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
    <section className="flex-1 min-w-[340px] flex flex-col h-full bg-canvas border-r border-borderSubtle">
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
          <span className="text-[11px] px-2.5 py-1 rounded-full bg-card border border-borderStrong text-inkMuted flex items-center gap-1.5">
            <Cpu className="w-3 h-3 text-studioCyan" />
            {engineLabel}
          </span>
        </div>
      </header>

      {/* Optional Narration Audio Bar */}
      {activeProject?.has_audio && (
        <div className="px-5 py-2 bg-card/60 border-b border-borderSubtle flex items-center gap-3">
          <Volume2 className="w-4 h-4 text-accent shrink-0" />
          <span className="text-xs text-inkMuted shrink-0">ElevenLabs Narration:</span>
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
            {messages.map((m) => {
              const isUser = m.role === 'user';
              return (
                <div
                  key={m.id}
                  className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      isUser
                        ? 'bg-card border border-borderStrong text-ink'
                        : 'bg-transparent text-ink'
                    }`}
                  >
                    {!isUser && (
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="w-5 h-5 rounded-md bg-accent/20 text-accent flex items-center justify-center text-[10px] font-bold">
                          SK
                        </span>
                        <span className="text-xs font-semibold text-ink">Claude 3D Director</span>
                      </div>
                    )}
                    <div className="whitespace-pre-wrap">{m.content}</div>
                    {!isUser && m.metadata?.usage && (
                      <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[11px] font-mono text-inkDim">
                        <span className="px-2 py-0.5 rounded bg-card border border-borderSubtle">
                          in: {m.metadata.usage.input_tokens}
                        </span>
                        <span className="px-2 py-0.5 rounded bg-card border border-borderSubtle text-emerald-400/90">
                          cache hit: {m.metadata.usage.cache_read_tokens}
                        </span>
                        <span className="px-2 py-0.5 rounded bg-card border border-borderSubtle">
                          out: {m.metadata.usage.output_tokens}
                        </span>
                        <span className="px-2 py-0.5 rounded bg-accent/15 text-accent">
                          ${m.metadata.usage.cost_usd.toFixed(4)}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {isSendingChat && (
              <div className="flex items-center gap-2.5 text-xs text-inkMuted px-2">
                <Loader2 className="w-4 h-4 animate-spin text-accent" />
                Claude Director is crafting scenes & 3D shot choreography (Prompt Cache active)...
              </div>
            )}
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
          <textarea
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              messages.length > 0
                ? 'Ask for follow-up edits (e.g., "Zoom closer on scene 3 and put STICK KNOWLEDGE on the battery label")...'
                : 'Describe your 3D explainer Short topic (30–60s)...'
            }
            className="w-full bg-transparent resize-none px-2 py-1 text-sm text-ink placeholder:text-inkDim focus:outline-none"
          />
          <div className="flex items-center justify-between pt-1.5 px-1">
            <span className="text-[11px] text-inkDim font-mono truncate">
              {settings?.claude_model || 'claude-sonnet-4-5'} · Prompt Cached
            </span>
            <button
              type="submit"
              disabled={!input.trim() || isSendingChat}
              className="px-3.5 py-1.5 rounded-xl bg-accent hover:bg-accentHover disabled:opacity-40 text-white text-xs font-medium flex items-center gap-1.5 transition-colors"
            >
              {isSendingChat ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Send className="w-3.5 h-3.5" />
              )}
              Send
            </button>
          </div>
        </form>
      </div>
    </section>
  );
};
