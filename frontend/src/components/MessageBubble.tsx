import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Brain, CheckCircle2, ChevronRight, Loader2, Wrench, XCircle } from 'lucide-react';
import type { ChatMessage, ToolCallInfo, TokenUsageEntry } from '../types';

export const Markdown: React.FC<{ text: string }> = ({ text }) => (
  <div className="sk-markdown">
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
  </div>
);

export const ThinkingBlock: React.FC<{ text: string; live?: boolean }> = ({ text, live }) => {
  const [open, setOpen] = useState(false);
  if (!text && !live) return null;
  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-[12px] text-inkDim hover:text-inkMuted"
      >
        <Brain className={`w-3.5 h-3.5 ${live ? 'animate-pulse text-accent' : ''}`} />
        {live ? 'Thinking…' : 'Thought process'}
        <ChevronRight className={`w-3 h-3 transition-transform ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && text && (
        <div className="mt-1.5 pl-3 border-l-2 border-borderStrong text-[12px] text-inkMuted whitespace-pre-wrap max-h-64 overflow-y-auto">
          {text}
        </div>
      )}
    </div>
  );
};

export const ToolChips: React.FC<{ tools: ToolCallInfo[] }> = ({ tools }) => {
  if (!tools.length) return null;
  return (
    <div className="my-2 space-y-1.5">
      {tools.map((t) => (
        <div
          key={t.id}
          className="flex items-start gap-2 px-2.5 py-1.5 rounded-lg bg-card border border-borderSubtle text-[12px]"
          title={t.summary}
        >
          {t.running ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin text-accent mt-0.5 shrink-0" />
          ) : t.ok ? (
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
          ) : (
            <XCircle className="w-3.5 h-3.5 text-red-400 mt-0.5 shrink-0" />
          )}
          <Wrench className="w-3.5 h-3.5 text-inkDim mt-0.5 shrink-0" />
          <div className="min-w-0 flex-1">
            <span className="text-ink">{t.label || t.name}</span>
            {t.summary && !t.running && <div className="text-inkDim truncate">{t.summary}</div>}
            {t.image_url && (
              <a href={t.image_url} target="_blank" rel="noreferrer">
                <img
                  src={t.image_url}
                  alt="Blender camera view"
                  className="mt-1.5 h-40 aspect-[9/16] object-cover rounded-md border border-borderSubtle"
                />
              </a>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

export const UsageRow: React.FC<{ usage: Omit<TokenUsageEntry, 'model'> & { model?: string } }> = ({ usage }) => (
  <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[11px] font-mono text-inkDim">
    {usage.model && <span className="px-2 py-0.5 rounded bg-card border border-borderSubtle">{usage.model}</span>}
    <span className="px-2 py-0.5 rounded bg-card border border-borderSubtle">in: {usage.input_tokens}</span>
    <span className="px-2 py-0.5 rounded bg-card border border-borderSubtle text-emerald-400/90">
      cache: {usage.cache_read_tokens}
    </span>
    <span className="px-2 py-0.5 rounded bg-card border border-borderSubtle">out: {usage.output_tokens}</span>
    <span className="px-2 py-0.5 rounded bg-accent/15 text-accent">${usage.cost_usd.toFixed(4)}</span>
  </div>
);

const AssistantHeader: React.FC = () => (
  <div className="flex items-center gap-2 mb-1.5">
    <span className="w-5 h-5 rounded-md bg-accent/20 text-accent flex items-center justify-center text-[10px] font-bold">
      SK
    </span>
    <span className="text-xs font-semibold text-ink">Claude 3D Director</span>
  </div>
);

export const MessageBubble: React.FC<{ message: ChatMessage }> = ({ message: m }) => {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-relaxed bg-card border border-borderStrong text-ink whitespace-pre-wrap">
          {m.content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className={`max-w-[94%] px-1 py-1 text-sm leading-relaxed ${m.metadata?.error ? 'text-red-300' : 'text-ink'}`}>
        <AssistantHeader />
        {m.metadata?.thinking && <ThinkingBlock text={m.metadata.thinking} />}
        {m.metadata?.tool_calls && <ToolChips tools={m.metadata.tool_calls} />}
        <Markdown text={m.content} />
        {m.metadata?.usage && <UsageRow usage={{ ...m.metadata.usage, model: m.metadata.model }} />}
      </div>
    </div>
  );
};

export const StreamingBubble: React.FC<{
  text: string;
  thinking: string;
  isThinking: boolean;
  tools: ToolCallInfo[];
  notices: string[];
  model: string;
}> = ({ text, thinking, isThinking, tools, notices, model }) => (
  <div className="flex justify-start">
    <div className="max-w-[94%] px-1 py-1 text-sm leading-relaxed text-ink">
      <AssistantHeader />
      {(thinking || isThinking) && <ThinkingBlock text={thinking} live={isThinking} />}
      <ToolChips tools={tools} />
      {notices.map((n, i) => (
        <div key={i} className="text-[12px] text-amber-400/90 mb-1">
          {n}
        </div>
      ))}
      {text ? (
        <Markdown text={text} />
      ) : (
        !isThinking &&
        !tools.some((t) => t.running) && (
          <div className="flex items-center gap-2 text-xs text-inkDim">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-accent" />
            {model || 'Claude'} is responding…
          </div>
        )
      )}
    </div>
  </div>
);
