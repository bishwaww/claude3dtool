import React, { useEffect, useState } from 'react';
import { Copy, Minus, Square, X } from 'lucide-react';
import { desktop } from '../desktop';
import { useStudioStore } from '../store/studioStore';
import { BlenderStatusBadge } from './LiveBlender';
import { UpdateButton } from './UpdateCenter';

const drag = { WebkitAppRegion: 'drag' } as React.CSSProperties;
const noDrag = { WebkitAppRegion: 'no-drag' } as React.CSSProperties;

/** Frameless-window titlebar (desktop app only), Claude Desktop style. */
export const TitleBar: React.FC = () => {
  const { activeProject } = useStudioStore();
  const [max, setMax] = useState(false);

  useEffect(() => {
    if (!desktop) return;
    desktop.isMaximized().then(setMax);
    return desktop.onMaximizedChange(setMax);
  }, []);

  if (!desktop) return null;

  return (
    <div
      className="h-9 shrink-0 flex items-center bg-sidebar border-b border-borderSubtle select-none"
      style={drag}
      onDoubleClick={() => desktop!.toggleMaximize()}
    >
      <div className="flex items-center gap-2 pl-3 pr-4 min-w-0">
        <img src="/logo.png" alt="" className="w-[18px] h-[18px] rounded-[5px]" draggable={false} />
        <span className="text-[12px] font-medium text-ink whitespace-nowrap">Stick Knowledge 3D Studio</span>
        {activeProject && (
          <span className="text-[12px] text-inkDim truncate hidden md:inline">· {activeProject.name}</span>
        )}
      </div>
      <div className="flex-1" />
      <div className="flex items-center gap-1.5 pr-2" style={noDrag}>
        <BlenderStatusBadge />
        <UpdateButton />
      </div>
      <div className="flex h-full" style={noDrag}>
        <WinBtn onClick={() => desktop!.minimize()} title="Minimize">
          <Minus className="w-4 h-4" />
        </WinBtn>
        <WinBtn onClick={() => desktop!.toggleMaximize()} title={max ? 'Restore' : 'Maximize'}>
          {max ? <Copy className="w-3.5 h-3.5 -scale-x-100" /> : <Square className="w-3.5 h-3.5" />}
        </WinBtn>
        <WinBtn onClick={() => desktop!.close()} title="Close" danger>
          <X className="w-4 h-4" />
        </WinBtn>
      </div>
    </div>
  );
};

const WinBtn: React.FC<{ onClick: () => void; title: string; danger?: boolean; children: React.ReactNode }> = ({
  onClick,
  title,
  danger,
  children,
}) => (
  <button
    onClick={onClick}
    title={title}
    className={`w-11 h-full flex items-center justify-center text-inkMuted transition-colors ${
      danger ? 'hover:bg-[#c42b1c] hover:text-white' : 'hover:bg-card hover:text-ink'
    }`}
  >
    {children}
  </button>
);
