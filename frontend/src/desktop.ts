/** Bridge to the Electron shell (undefined when the studio runs in a normal browser). */
export type UpdateEvent =
  | { state: 'checking' }
  | { state: 'available'; version: string; notes?: string }
  | { state: 'none'; version?: string }
  | { state: 'downloading'; percent: number; bytesPerSecond?: number }
  | { state: 'downloaded'; version: string }
  | { state: 'syncing'; line: string }
  | { state: 'error'; message: string };

export interface GitStatus {
  available: boolean;
  branch?: string;
  head?: string;
  behind?: number | null;
  ahead?: number | null;
  dirty?: boolean;
  error?: string | null;
}

export interface SkDesktop {
  platform: string;
  minimize(): Promise<void>;
  toggleMaximize(): Promise<void>;
  close(): Promise<void>;
  isMaximized(): Promise<boolean>;
  onMaximizedChange(cb: (max: boolean) => void): () => void;
  pickFolder(opts?: { title?: string; defaultPath?: string }): Promise<string | null>;
  pickFiles(opts?: { title?: string; multiple?: boolean; filters?: { name: string; extensions: string[] }[] }): Promise<string[]>;
  openExternal(url: string): Promise<void>;
  openPath(p: string): Promise<string>;
  info(): Promise<{ version: string; packaged: boolean; dataDir: string; repoRoot: string | null; logFile: string }>;
  relaunch(): Promise<void>;
  restartBackend(): Promise<void>;
  checkForUpdates(): Promise<{ state: string; version?: string | null; message?: string }>;
  downloadUpdate(): Promise<void>;
  installUpdate(): Promise<void>;
  onUpdateEvent(cb: (e: UpdateEvent) => void): () => void;
  onBackendExited(cb: (code: number) => void): () => void;
  gitStatus(): Promise<GitStatus>;
  gitSync(): Promise<{ ok: boolean; changed?: boolean; commits?: string; error?: string; desktopChanged?: boolean }>;
}

export const desktop: SkDesktop | undefined = (window as unknown as { skDesktop?: SkDesktop }).skDesktop;
