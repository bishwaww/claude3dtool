import React, { useEffect, useRef, useState } from 'react';
import { Brain, Check, ChevronDown, RefreshCw } from 'lucide-react';
import { useStudioStore } from '../store/studioStore';
import type { ThinkingEffort } from '../types';

const EFFORTS: { id: ThinkingEffort; label: string }[] = [
  { id: 'low', label: 'Low' },
  { id: 'medium', label: 'Medium' },
  { id: 'high', label: 'High' },
  { id: 'xhigh', label: 'Extra high' },
  { id: 'max', label: 'Max' },
];

function useClickOutside(ref: React.RefObject<HTMLElement>, onOutside: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onOutside();
    };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [ref, onOutside]);
}

/** Claude Desktop-style model switcher that lives in the chat input bar. */
export const ModelPicker: React.FC = () => {
  const { models, modelsSource, modelsError, settings, setChatModel, refreshModels, isSendingChat } =
    useStudioStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false));

  const current = settings?.claude_model || '';
  const currentModel = models.find((m) => m.id === current);
  const name = currentModel?.display_name || current || 'Choose model';

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={isSendingChat}
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 px-2 py-1 rounded-lg text-[12px] text-inkMuted hover:text-ink hover:bg-cardHover disabled:opacity-50 transition-colors"
        title={current}
      >
        <span className="truncate max-w-[160px]">{name}</span>
        <ChevronDown className="w-3.5 h-3.5 shrink-0" />
      </button>
      {open && (
        <div className="absolute bottom-full mb-2 left-0 z-50 w-80 max-h-96 overflow-y-auto rounded-xl bg-card border border-borderStrong shadow-2xl p-1.5">
          <div className="flex items-center justify-between px-2 py-1.5">
            <span className="text-[11px] uppercase tracking-wide text-inkDim">
              {modelsSource === 'live' ? 'Models on your API key' : 'Offline model list'}
            </span>
            <button
              type="button"
              onClick={() => refreshModels(true)}
              className="p-1 rounded hover:bg-cardHover text-inkDim hover:text-ink"
              title="Refresh from Anthropic API"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
          {modelsError && <div className="px-2 pb-1.5 text-[11px] text-amber-400/90">{modelsError}</div>}
          {models.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => {
                setChatModel(m.id);
                setOpen(false);
              }}
              className={`w-full text-left px-2.5 py-2 rounded-lg flex items-start gap-2 hover:bg-cardHover ${
                m.id === current ? 'bg-cardHover' : ''
              }`}
            >
              <div className="flex-1 min-w-0">
                <div className="text-[13px] text-ink truncate">{m.display_name || m.id}</div>
                <div className="text-[11px] text-inkDim font-mono truncate">
                  {m.id} · ${m.input_per_mtok}/${m.output_per_mtok} per MTok
                </div>
              </div>
              {m.id === current && <Check className="w-4 h-4 text-accent shrink-0 mt-0.5" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

/** Extended-thinking toggle + effort level. */
export const ThinkingToggle: React.FC = () => {
  const { settings, setChatThinking, isSendingChat } = useStudioStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false));

  const enabled = settings?.extended_thinking ?? true;
  const effort = settings?.thinking_effort ?? 'high';

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={isSendingChat}
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1 px-2 py-1 rounded-lg text-[12px] transition-colors disabled:opacity-50 ${
          enabled ? 'text-accent bg-accent/10 hover:bg-accent/20' : 'text-inkMuted hover:text-ink hover:bg-cardHover'
        }`}
        title="Extended thinking"
      >
        <Brain className="w-3.5 h-3.5" />
        <span>{enabled ? `Thinking · ${EFFORTS.find((e) => e.id === effort)?.label}` : 'Thinking off'}</span>
      </button>
      {open && (
        <div className="absolute bottom-full mb-2 left-0 z-50 w-56 rounded-xl bg-card border border-borderStrong shadow-2xl p-1.5">
          <label className="flex items-center justify-between px-2.5 py-2 rounded-lg hover:bg-cardHover cursor-pointer">
            <span className="text-[13px] text-ink">Extended thinking</span>
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setChatThinking(e.target.checked)}
              className="accent-[#d97757]"
            />
          </label>
          <div className="px-2.5 pt-1.5 pb-1 text-[11px] uppercase tracking-wide text-inkDim">Effort</div>
          {EFFORTS.map((e) => (
            <button
              key={e.id}
              type="button"
              disabled={!enabled}
              onClick={() => setChatThinking(true, e.id)}
              className="w-full text-left px-2.5 py-1.5 rounded-lg text-[13px] text-ink hover:bg-cardHover disabled:opacity-40 flex items-center justify-between"
            >
              {e.label}
              {enabled && e.id === effort && <Check className="w-3.5 h-3.5 text-accent" />}
            </button>
          ))}
          <div className="px-2.5 pt-1.5 text-[11px] text-inkDim leading-snug">
            Some models always think a little. With thinking off they run at low effort.
          </div>
        </div>
      )}
    </div>
  );
};
