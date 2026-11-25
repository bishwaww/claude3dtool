/** Safe bridge between the React UI and the Electron main process (window.skDesktop). */
const { contextBridge, ipcRenderer } = require('electron');

const on = (channel) => (cb) => {
  const handler = (_e, payload) => cb(payload);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
};

contextBridge.exposeInMainWorld('skDesktop', {
  platform: process.platform,
  // window controls (frameless window)
  minimize: () => ipcRenderer.invoke('win:minimize'),
  toggleMaximize: () => ipcRenderer.invoke('win:toggleMaximize'),
  close: () => ipcRenderer.invoke('win:close'),
  isMaximized: () => ipcRenderer.invoke('win:isMaximized'),
  onMaximizedChange: on('win:maximized'),
  // native dialogs & shell
  pickFolder: (opts) => ipcRenderer.invoke('dialog:pickFolder', opts),
  pickFiles: (opts) => ipcRenderer.invoke('dialog:pickFiles', opts),
  openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),
  openPath: (p) => ipcRenderer.invoke('shell:openPath', p),
  // app & updates
  info: () => ipcRenderer.invoke('app:info'),
  relaunch: () => ipcRenderer.invoke('app:relaunch'),
  restartBackend: () => ipcRenderer.invoke('app:restartBackend'),
  checkForUpdates: () => ipcRenderer.invoke('updater:check'),
  downloadUpdate: () => ipcRenderer.invoke('updater:download'),
  installUpdate: () => ipcRenderer.invoke('updater:install'),
  onUpdateEvent: on('updater:event'),
  onBackendExited: on('app:backend-exited'),
  gitStatus: () => ipcRenderer.invoke('git:status'),
  gitSync: () => ipcRenderer.invoke('git:sync'),
});
