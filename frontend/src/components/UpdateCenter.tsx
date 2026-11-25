import React, { useEffect, useRef, useState } from 'react';
import { ArrowDownToLine, CheckCircle2, GitBranch, Loader2, RefreshCw, RotateCw, X } from 'lucide-react';
import { desktop, type GitStatus, type UpdateEvent } from '../desktop';

type Info = { version: string; packaged: boolean; repoRoot: string | null };

/**
 * Update button + popover.
 *  - Installed .exe: electron-updater against GitHub Releases (check → download → restart & install).
 *  - Source checkout: "Sync latest from GitHub" (git pull + deps + rebuild + restart).
 */
export const UpdateButton: React.FC<{ compact?: boolean }> = ({ compact }) => {
  const [info, setInfo] = useState<Info | null>(null);
  const [open, setOpen] = useState(false);
  const [evt, setEvt] = useState<UpdateEvent | null>(null);
  const [git, setGit] = useState<GitStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!desktop) return;
    desktop.info().then(setInfo);
    return desktop.onUpdateEvent((e) => {
      setEvt(e);
      if (e.state === 'available' || e.state === 'downloaded') setOpen(true);
    });
  }, []);

  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  if (!desktop || !info) return null;

  const hasUpdate = evt?.state === 'available' || evt?.state === 'downloaded' || (git?.behind ?? 0) > 0;

  const check = async () => {
    setBusy(true);
    setMessage(null);
    try {
      if (info.packaged) {
        const r = await desktop!.checkForUpdates();
        if (r.state === 'error') setMessage(r.message || 'Update check failed.');
      } else {
        const s = await desktop!.gitStatus();
        setGit(s);
        if (s.error) setMessage(s.error);
      }
    } finally {
      setBusy(false);
    }
  };

  const sync = async () => {
    setBusy(true);
    setMessage('Pulling the latest version from GitHub…');
    const r = await desktop!.gitSync();
    setBusy(false);
    if (!r.ok) setMessage(r.error || 'Sync failed.');
    else if (!r.changed) setMessage('Already up to date.');
    else setMessage(`Updated:\n${r.commits}\nThe studio restarted with the new version.`);
    setGit(await desktop!.gitStatus());
  };

  return (
    <div ref={ref} className="relative" style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
      <button
        onClick={() => {
          setOpen((o) => !o);
          if (!open && !evt && !git) check();
        }}
        className={`h-7 px-2.5 rounded-md text-[11px] flex items-center gap-1.5 transition-colors ${
          hasUpdate ? 'bg-accent/20 text-accent hover:bg-accent/30' : 'text-inkMuted hover:text-ink hover:bg-card'
        }`}
        title="Updates"
      >
        <ArrowDownToLine className="w-3.5 h-3.5" />
        {!compact && (hasUpdate ? 'Update available' : `v${info.version}`)}
        {hasUpdate && <span className="w-1.5 h-1.5 rounded-full bg-accent" />}
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1.5 z-[60] w-80 rounded-xl bg-card border border-borderStrong shadow-2xl p-3 text-xs space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-ink">Stick Knowledge 3D Studio</span>
            <button onClick={() => setOpen(false)} className="text-inkDim hover:text-ink">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="text-inkMuted">
            Version <span className="font-mono text-ink">{info.version}</span> ·{' '}
            {info.packaged ? 'installed app' : 'running from source'}
          </div>

          {info.packaged ? (
            <>
              {evt?.state === 'checking' && <Row icon={<Loader2 className="w-3.5 h-3.5 animate-spin" />}>Checking GitHub Releases…</Row>}
              {evt?.state === 'none' && <Row icon={<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}>You have the latest version.</Row>}
              {evt?.state === 'available' && (
                <>
                  <Row icon={<ArrowDownToLine className="w-3.5 h-3.5 text-accent" />}>Version {evt.version} is available.</Row>
                  <Btn onClick={() => desktop!.downloadUpdate()}>Download update</Btn>
                </>
              )}
              {evt?.state === 'downloading' && (
                <div>
                  <div className="flex justify-between text-inkMuted mb-1">
                    <span>Downloading…</span>
                    <span className="font-mono">{evt.percent}%</span>
                  </div>
                  <div className="h-1.5 bg-canvas rounded-full overflow-hidden">
                    <div className="h-full bg-accent transition-all" style={{ width: `${evt.percent}%` }} />
                  </div>
                </div>
              )}
              {evt?.state === 'downloaded' && (
                <>
                  <Row icon={<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}>Version {evt.version} is ready.</Row>
                  <Btn onClick={() => desktop!.installUpdate()}>
                    <RotateCw className="w-3.5 h-3.5" /> Restart & install update
                  </Btn>
                </>
              )}
              {evt?.state === 'error' && <div className="text-red-300 whitespace-pre-wrap">{evt.message}</div>}
              {(!evt || evt.state === 'none' || evt.state === 'error') && (
                <Btn onClick={check} disabled={busy} secondary>
                  <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} /> Check for updates
                </Btn>
              )}
            </>
          ) : (
            <>
              {git?.available && (
                <Row icon={<GitBranch className="w-3.5 h-3.5" />}>
                  <span className="font-mono">{git.branch}@{git.head}</span>
                  {git.behind != null && (
                    <span>
                      {' '}· {git.behind === 0 ? 'up to date' : `${git.behind} new commit${git.behind > 1 ? 's' : ''} on GitHub`}
                    </span>
                  )}
                  {git.dirty && <span className="text-amber-300"> · local changes</span>}
                </Row>
              )}
              <div className="flex gap-2">
                <Btn onClick={check} disabled={busy} secondary>
                  <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} /> Check
                </Btn>
                <Btn onClick={sync} disabled={busy || !git?.behind}>
                  <ArrowDownToLine className="w-3.5 h-3.5" /> Sync latest from GitHub
                </Btn>
              </div>
            </>
          )}
          {evt?.state === 'syncing' && <div className="font-mono text-[10px] text-inkDim truncate">{evt.line}</div>}
          {message && <div className="text-inkMuted whitespace-pre-wrap">{message}</div>}
        </div>
      )}
    </div>
  );
};

const Row: React.FC<{ icon: React.ReactNode; children: React.ReactNode }> = ({ icon, children }) => (
  <div className="flex items-start gap-2 text-ink">
    <span className="mt-0.5 shrink-0">{icon}</span>
    <span>{children}</span>
  </div>
);

const Btn: React.FC<{ onClick: () => void; disabled?: boolean; secondary?: boolean; children: React.ReactNode }> = ({
  onClick,
  disabled,
  secondary,
  children,
}) => (
  <button
    onClick={onClick}
    disabled={disabled}
    className={`flex-1 w-full px-3 py-1.5 rounded-lg flex items-center justify-center gap-1.5 font-medium disabled:opacity-40 ${
      secondary ? 'bg-canvas border border-borderStrong text-ink hover:bg-cardHover' : 'bg-accent hover:bg-accentHover text-white'
    }`}
  >
    {children}
  </button>
);
