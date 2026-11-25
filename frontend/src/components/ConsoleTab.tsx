import React, { useEffect, useRef } from 'react';
import {
  Terminal,
  Trash2,
  DollarSign,
  Database,
  Cpu,
} from 'lucide-react';
import { useStudioStore } from '../store/studioStore';

const STAGE_COLOR: Record<string, string> = {
  blender: 'text-sky-400',
  claude: 'text-accent',
  asset: 'text-emerald-400',
  elevenlabs: 'text-violet-400',
  ffmpeg: 'text-amber-300',
  self_heal: 'text-yellow-300',
  error: 'text-rose-400',
};

export const ConsoleTab: React.FC = () => {
  const { logs, clearLogs, usage } = useStudioStore();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs.length]);

  const g = usage?.global_totals || {
    input_tokens: 0,
    output_tokens: 0,
    cache_creation_tokens: 0,
    cache_read_tokens: 0,
    cost_usd: 0,
  };
  const p = usage?.project_totals || g;
  const budget = usage?.budget_limit_usd ?? 100;
  const pct = Math.min(100, (g.cost_usd / Math.max(1, budget)) * 100);
  const totalInAll = g.input_tokens + g.cache_read_tokens + g.cache_creation_tokens;
  const cacheHitPct = totalInAll > 0 ? Math.round((g.cache_read_tokens / totalInAll) * 100) : 0;

  return (
    <div className="p-4 flex flex-col h-full gap-4">
      {/* Token Usage & $100 API Budget Card */}
      <div className="p-4 rounded-xl bg-card border border-borderSubtle space-y-3 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-accent" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-ink">
              Claude Token Usage & API Budget Tracker
            </h3>
          </div>
          <span className="font-mono text-xs text-ink">
            ${g.cost_usd.toFixed(4)} / ${budget.toFixed(2)}
          </span>
        </div>

        <div className="w-full h-2 bg-canvas rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-accent to-amber-400 rounded-full transition-all"
            style={{ width: `${Math.max(1, pct)}%` }}
          />
        </div>

        <div className="grid grid-cols-4 gap-2 text-center">
          <div className="p-2 rounded-lg bg-canvas border border-borderSubtle">
            <div className="text-[10px] text-inkDim uppercase">Project Cost</div>
            <div className="font-mono text-xs font-semibold text-accent mt-0.5">
              ${(p.cost_usd ?? 0).toFixed(4)}
            </div>
          </div>
          <div className="p-2 rounded-lg bg-canvas border border-borderSubtle">
            <div className="text-[10px] text-inkDim uppercase">Cache Read</div>
            <div className="font-mono text-xs font-semibold text-emerald-400 mt-0.5">
              {g.cache_read_tokens.toLocaleString()} ({cacheHitPct}%)
            </div>
          </div>
          <div className="p-2 rounded-lg bg-canvas border border-borderSubtle">
            <div className="text-[10px] text-inkDim uppercase">Input Tokens</div>
            <div className="font-mono text-xs font-semibold text-ink mt-0.5">
              {g.input_tokens.toLocaleString()}
            </div>
          </div>
          <div className="p-2 rounded-lg bg-canvas border border-borderSubtle">
            <div className="text-[10px] text-inkDim uppercase">Output Tokens</div>
            <div className="font-mono text-xs font-semibold text-ink mt-0.5">
              {g.output_tokens.toLocaleString()}
            </div>
          </div>
        </div>

        {usage?.entries && usage.entries.length > 0 && (
          <div className="max-h-28 overflow-y-auto border-t border-borderSubtle pt-2 space-y-1">
            {usage.entries.slice(0, 8).map((e, idx) => (
              <div
                key={e.id ?? idx}
                className="flex items-center justify-between text-[11px] font-mono text-inkMuted px-1"
              >
                <span className="truncate flex items-center gap-1.5">
                  <Cpu className="w-3 h-3 text-inkDim shrink-0" />
                  {e.operation}
                </span>
                <span className="shrink-0 flex items-center gap-2">
                  <span className="text-emerald-400/80">cache:{e.cache_read_tokens}</span>
                  <span>out:{e.output_tokens}</span>
                  <span className="text-accent">${e.cost_usd.toFixed(4)}</span>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Real-Time WebSocket Blender Console */}
      <div className="flex-1 min-h-0 rounded-xl bg-[#11100E] border border-borderSubtle flex flex-col overflow-hidden">
        <div className="px-3.5 py-2 border-b border-borderSubtle flex items-center justify-between bg-sidebar">
          <div className="flex items-center gap-2 text-xs text-inkMuted">
            <Terminal className="w-3.5 h-3.5 text-studioCyan" />
            <span className="font-medium text-ink">Blender & Pipeline Live Stream</span>
            <span className="text-[10px] font-mono text-inkDim">({logs.length} lines)</span>
          </div>
          <button
            onClick={clearLogs}
            className="text-[11px] text-inkDim hover:text-ink flex items-center gap-1 px-2 py-0.5 rounded hover:bg-card"
          >
            <Trash2 className="w-3 h-3" /> Clear
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed space-y-1">
          {logs.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-inkDim gap-1.5">
              <Database className="w-5 h-5 opacity-50" />
              <span>Waiting for Blender build, asset downloads, or render logs...</span>
            </div>
          ) : (
            logs.map((l) => (
              <div key={l.id} className="flex items-start gap-2 break-all">
                <span className={`uppercase shrink-0 font-semibold ${STAGE_COLOR[l.stage] || 'text-inkMuted'}`}>
                  [{l.stage}]
                </span>
                <span className="text-ink/90">{l.message}</span>
              </div>
            ))
          )}
          <div ref={endRef} />
        </div>
      </div>
    </div>
  );
};
