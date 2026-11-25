import React, { useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatWorkspace } from './components/ChatWorkspace';
import { ArtifactPanel } from './components/ArtifactPanel';
import { SettingsModal } from './components/SettingsModal';
import { AssetLibraryModal } from './components/AssetLibraryModal';
import { useStudioStore } from './store/studioStore';

export const App: React.FC = () => {
  const { init, toast } = useStudioStore();

  useEffect(() => {
    init();
  }, [init]);

  return (
    <div className="h-screen w-screen flex bg-canvas text-ink overflow-hidden font-sans">
      <Sidebar />
      <main className="flex-1 flex min-w-0 h-full overflow-hidden">
        <ChatWorkspace />
        <ArtifactPanel />
      </main>

      <SettingsModal />
      <AssetLibraryModal />

      {/* Toast Notifications */}
      {toast && (
        <div
          className={`fixed bottom-5 right-5 z-50 px-4 py-2.5 rounded-xl border text-xs font-medium shadow-2xl max-w-md ${
            toast.type === 'error'
              ? 'bg-rose-950/95 border-rose-500/50 text-rose-100'
              : toast.type === 'success'
              ? 'bg-emerald-950/95 border-emerald-500/50 text-emerald-100'
              : 'bg-card border-borderStrong text-ink'
          }`}
        >
          {toast.message}
        </div>
      )}
    </div>
  );
};

export default App;
