/**
 * Stick Knowledge 3D Studio — Electron main process.
 *
 * - Starts the Python backend (packaged: resources/backend/stick-backend.exe,
 *   source checkout: backend/.venv python server_entry.py) on a free local port and
 *   stops it on quit. A splash window shows until the backend says it is ready.
 * - Frameless Claude Desktop-style window; the React UI draws the titlebar and talks
 *   to this process through preload.js (window controls, native dialogs, updates).
 * - Updates: packaged builds use electron-updater against GitHub Releases of
 *   bishwaww/claude3dtool; a source checkout can "Sync latest from GitHub" (git pull,
 *   reinstall changed dependencies, rebuild the UI, restart the backend).
 */
const { app, BrowserWindow, ipcMain, dialog, shell, nativeImage } = require('electron');
const path = require('path');
const fs = require('fs');
const net = require('net');
const { spawn, execFile } = require('child_process');
const log = require('electron-log/main');

log.initialize();
log.transports.file.level = 'info';

const IS_DEV = !app.isPackaged;
const REPO_ROOT = path.resolve(__dirname, '..');
const DATA_DIR = path.join(app.getPath('appData'), 'StickKnowledge3DStudio');
const ICON = path.join(__dirname, 'assets', 'icon.png');
const SELFTEST = process.env.SK_SELFTEST === '1';

let mainWindow = null;
let splash = null;
let backend = null;
let backendPort = 0;
let quitting = false;

if (!app.requestSingleInstanceLock()) {
  app.quit();
}
app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

// ---------------------------------------------------------------------------
// Backend lifecycle
// ---------------------------------------------------------------------------

function freePort(start) {
  return new Promise((resolve) => {
    const tryPort = (p) => {
      const srv = net.createServer();
      srv.once('error', () => tryPort(p + 1));
      srv.once('listening', () => srv.close(() => resolve(p)));
      srv.listen(p, '127.0.0.1');
    };
    tryPort(start);
  });
}

function backendCommand(port) {
  const args = ['--port', String(port), '--parent-pid', String(process.pid)];
  if (!IS_DEV) {
    const exe = path.join(process.resourcesPath, 'backend', 'stick-backend.exe');
    return { cmd: exe, args, cwd: path.dirname(exe) };
  }
  const py = path.join(REPO_ROOT, 'backend', '.venv', 'Scripts', 'python.exe');
  return { cmd: py, args: [path.join(REPO_ROOT, 'backend', 'server_entry.py'), ...args], cwd: path.join(REPO_ROOT, 'backend') };
}

function setSplash(text, isError = false) {
  if (splash && !splash.isDestroyed()) {
    splash.webContents.executeJavaScript(`window.setStatus && window.setStatus(${JSON.stringify(text)}, ${isError})`).catch(() => {});
  }
}

async function startBackend() {
  backendPort = await freePort(8420);
  const { cmd, args, cwd } = backendCommand(backendPort);
  if (!fs.existsSync(cmd)) throw new Error(`Backend not found: ${cmd}`);
  const env = {
    ...process.env,
    SK_DATA_DIR: DATA_DIR,
    SK_APP_VERSION: app.getVersion(),
    PYTHONUNBUFFERED: '1',
    PYTHONIOENCODING: 'utf-8',
  };
  if (IS_DEV) env.SK_FRONTEND_DIST = path.join(REPO_ROOT, 'frontend', 'dist');
  log.info(`Starting backend: ${cmd} ${args.join(' ')}`);
  backend = spawn(cmd, args, { cwd, env, windowsHide: true });

  return new Promise((resolve, reject) => {
    let settled = false;
    const tail = [];
    const onLine = (buf) => {
      const text = buf.toString();
      text.split(/\r?\n/).forEach((line) => {
        if (!line.trim()) return;
        log.info(`[backend] ${line}`);
        tail.push(line);
        if (tail.length > 40) tail.shift();
        if (!settled && line.includes('SK_BACKEND_READY')) {
          settled = true;
          resolve(backendPort);
        }
      });
    };
    backend.stdout.on('data', onLine);
    backend.stderr.on('data', onLine);
    backend.on('exit', (code) => {
      log.warn(`Backend exited with code ${code}`);
      if (!settled) {
        settled = true;
        reject(new Error(`Backend exited (code ${code}).\n${tail.slice(-12).join('\n')}`));
      } else if (!quitting && mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('app:backend-exited', code);
      }
    });
    setTimeout(() => {
      if (!settled) {
        settled = true;
        reject(new Error(`Backend did not start within 90 s.\n${tail.slice(-12).join('\n')}`));
      }
    }, 90000);
  });
}

function stopBackend() {
  if (!backend || backend.exitCode !== null) return;
  try {
    if (process.platform === 'win32') {
      execFile('taskkill', ['/pid', String(backend.pid), '/T', '/F'], () => {});
    } else {
      backend.kill('SIGTERM');
    }
  } catch (e) {
    log.warn('stopBackend', e);
  }
}

async function restartBackend() {
  stopBackend();
  await new Promise((r) => setTimeout(r, 1200));
  await startBackend();
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.loadURL(`http://127.0.0.1:${backendPort}/`);
}

// ---------------------------------------------------------------------------
// Windows
// ---------------------------------------------------------------------------

function createSplash() {
  splash = new BrowserWindow({
    width: 420,
    height: 300,
    frame: false,
    resizable: false,
    transparent: false,
    backgroundColor: '#1a1917',
    show: true,
    icon: ICON,
    webPreferences: { contextIsolation: true },
  });
  splash.loadFile(path.join(__dirname, 'splash.html'), { query: { version: app.getVersion() } });
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1560,
    height: 960,
    minWidth: 1100,
    minHeight: 680,
    frame: false,
    show: false,
    backgroundColor: '#1a1917',
    icon: ICON,
    title: 'Stick Knowledge 3D Studio',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });
  mainWindow.setMenuBarVisibility(false);

  // Links (mixamo.com, docs, images) open in the user's browser, not inside the app.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url) && !url.startsWith(`http://127.0.0.1:${backendPort}`)) shell.openExternal(url);
    else if (url.startsWith(`http://127.0.0.1:${backendPort}`)) shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith(`http://127.0.0.1:${backendPort}`)) {
      e.preventDefault();
      shell.openExternal(url);
    }
  });

  const sendMax = () => mainWindow.webContents.send('win:maximized', mainWindow.isMaximized());
  mainWindow.on('maximize', sendMax);
  mainWindow.on('unmaximize', sendMax);

  mainWindow.once('ready-to-show', () => {
    if (splash && !splash.isDestroyed()) splash.destroy();
    mainWindow.show();
    if (SELFTEST) runSelfTest();
  });
  mainWindow.loadURL(`http://127.0.0.1:${backendPort}/`);
}

async function runSelfTest() {
  // SK_SELFTEST=1: capture the window after the UI settles, write a report, quit.
  const out = process.env.SK_SELFTEST_DIR || app.getPath('temp');
  await new Promise((r) => setTimeout(r, 6000));
  try {
    const img = await mainWindow.webContents.capturePage();
    fs.writeFileSync(path.join(out, 'sk_selftest.png'), img.toPNG());
    const hasBridge = await mainWindow.webContents.executeJavaScript('Boolean(window.skDesktop)');
    fs.writeFileSync(path.join(out, 'sk_selftest.json'), JSON.stringify({
      ok: true, version: app.getVersion(), packaged: app.isPackaged, port: backendPort, preloadBridge: hasBridge,
    }));
  } catch (e) {
    fs.writeFileSync(path.join(out, 'sk_selftest.json'), JSON.stringify({ ok: false, error: String(e) }));
  }
  app.quit();
}

// ---------------------------------------------------------------------------
// Updates
// ---------------------------------------------------------------------------

let autoUpdater = null;
function sendUpdate(evt) {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('updater:event', evt);
}

function setupAutoUpdater() {
  if (IS_DEV) return;
  ({ autoUpdater } = require('electron-updater'));
  autoUpdater.logger = log;
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.on('checking-for-update', () => sendUpdate({ state: 'checking' }));
  autoUpdater.on('update-available', (i) => sendUpdate({ state: 'available', version: i.version, notes: i.releaseNotes || '' }));
  autoUpdater.on('update-not-available', (i) => sendUpdate({ state: 'none', version: i.version }));
  autoUpdater.on('download-progress', (p) => sendUpdate({ state: 'downloading', percent: Math.round(p.percent), bytesPerSecond: p.bytesPerSecond }));
  autoUpdater.on('update-downloaded', (i) => sendUpdate({ state: 'downloaded', version: i.version }));
  autoUpdater.on('error', (e) => sendUpdate({ state: 'error', message: String(e && e.message ? e.message : e) }));
  setTimeout(() => autoUpdater.checkForUpdates().catch((e) => log.warn('update check', e)), 15000);
}

function git(args, cwd = REPO_ROOT, timeout = 120000) {
  return new Promise((resolve) => {
    execFile('git', args, { cwd, timeout, windowsHide: true }, (err, stdout, stderr) =>
      resolve({ ok: !err, out: (stdout || '').trim(), err: (stderr || (err && err.message) || '').trim() }),
    );
  });
}

function run(cmd, args, cwd, timeout = 900000) {
  return new Promise((resolve) => {
    const p = spawn(cmd, args, { cwd, shell: process.platform === 'win32', windowsHide: true });
    let out = '';
    p.stdout.on('data', (d) => { out += d; sendUpdate({ state: 'syncing', line: d.toString().slice(-200) }); });
    p.stderr.on('data', (d) => { out += d; });
    const t = setTimeout(() => p.kill(), timeout);
    p.on('exit', (code) => { clearTimeout(t); resolve({ ok: code === 0, out: out.slice(-4000) }); });
  });
}

async function gitStatus() {
  if (!IS_DEV) return { available: false };
  const fetch = await git(['fetch', 'origin', '--quiet']);
  const branch = (await git(['rev-parse', '--abbrev-ref', 'HEAD'])).out;
  const head = (await git(['rev-parse', '--short', 'HEAD'])).out;
  const behind = await git(['rev-list', '--count', `HEAD..origin/${branch}`]);
  const ahead = await git(['rev-list', '--count', `origin/${branch}..HEAD`]);
  const dirty = (await git(['status', '--porcelain'])).out;
  return {
    available: true, branch, head,
    behind: behind.ok ? Number(behind.out) : null,
    ahead: ahead.ok ? Number(ahead.out) : null,
    dirty: Boolean(dirty),
    error: fetch.ok ? null : fetch.err || 'git fetch failed (is the remote set up and are you signed in to GitHub?)',
  };
}

async function gitSync() {
  const before = (await git(['rev-parse', 'HEAD'])).out;
  sendUpdate({ state: 'syncing', line: 'git pull --ff-only' });
  const pull = await git(['pull', '--ff-only', 'origin'], REPO_ROOT, 300000);
  if (!pull.ok) return { ok: false, error: pull.err };
  const after = (await git(['rev-parse', 'HEAD'])).out;
  if (before === after) return { ok: true, changed: false };
  const changed = (await git(['diff', '--name-only', before, after])).out.split(/\r?\n/);
  const steps = [];
  if (changed.some((f) => f.startsWith('backend/requirements'))) {
    const py = path.join(REPO_ROOT, 'backend', '.venv', 'Scripts', 'python.exe');
    steps.push(['uv', ['pip', 'install', '--python', py, '-r', 'requirements.txt'], path.join(REPO_ROOT, 'backend')]);
  }
  if (changed.some((f) => f.startsWith('frontend/package'))) steps.push(['npm', ['ci'], path.join(REPO_ROOT, 'frontend')]);
  if (changed.some((f) => f.startsWith('frontend/'))) steps.push(['npm', ['run', 'build'], path.join(REPO_ROOT, 'frontend')]);
  if (changed.some((f) => f.startsWith('desktop/package'))) steps.push(['npm', ['ci'], __dirname]);
  for (const [cmd, args, cwd] of steps) {
    sendUpdate({ state: 'syncing', line: `${cmd} ${args.join(' ')}` });
    const r = await run(cmd, args, cwd);
    if (!r.ok) return { ok: false, error: `${cmd} ${args.join(' ')} failed:\n${r.out}` };
  }
  const desktopChanged = changed.some((f) => f.startsWith('desktop/'));
  return { ok: true, changed: true, commits: (await git(['log', '--oneline', `${before}..${after}`])).out, desktopChanged };
}

// ---------------------------------------------------------------------------
// IPC
// ---------------------------------------------------------------------------

function registerIpc() {
  ipcMain.handle('win:minimize', () => mainWindow.minimize());
  ipcMain.handle('win:toggleMaximize', () => (mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize()));
  ipcMain.handle('win:close', () => mainWindow.close());
  ipcMain.handle('win:isMaximized', () => mainWindow.isMaximized());

  ipcMain.handle('dialog:pickFolder', async (_e, opts = {}) => {
    const r = await dialog.showOpenDialog(mainWindow, {
      title: opts.title || 'Choose a folder',
      defaultPath: opts.defaultPath,
      properties: ['openDirectory', 'createDirectory'],
    });
    return r.canceled ? null : r.filePaths[0];
  });
  ipcMain.handle('dialog:pickFiles', async (_e, opts = {}) => {
    const r = await dialog.showOpenDialog(mainWindow, {
      title: opts.title || 'Choose files',
      properties: ['openFile', ...(opts.multiple ? ['multiSelections'] : [])],
      filters: opts.filters,
    });
    return r.canceled ? [] : r.filePaths;
  });
  ipcMain.handle('shell:openExternal', (_e, url) => (/^https?:\/\//.test(url) ? shell.openExternal(url) : null));
  ipcMain.handle('shell:openPath', (_e, p) => shell.openPath(p));

  ipcMain.handle('app:info', () => ({
    version: app.getVersion(), packaged: app.isPackaged, dataDir: DATA_DIR,
    repoRoot: IS_DEV ? REPO_ROOT : null, logFile: log.transports.file.getFile().path,
  }));
  ipcMain.handle('app:relaunch', () => { app.relaunch(); app.quit(); });
  ipcMain.handle('app:restartBackend', () => restartBackend());

  ipcMain.handle('updater:check', async () => {
    if (IS_DEV) return { state: 'dev' };
    try {
      const r = await autoUpdater.checkForUpdates();
      return { state: 'checked', version: r && r.updateInfo ? r.updateInfo.version : null };
    } catch (e) {
      return { state: 'error', message: String(e.message || e) };
    }
  });
  ipcMain.handle('updater:download', () => (autoUpdater ? autoUpdater.downloadUpdate() : null));
  ipcMain.handle('updater:install', () => {
    quitting = true;
    stopBackend();
    setImmediate(() => autoUpdater.quitAndInstall(false, true));
  });

  ipcMain.handle('git:status', () => gitStatus());
  ipcMain.handle('git:sync', async () => {
    const r = await gitSync();
    if (r.ok && r.changed) {
      if (r.desktopChanged) {
        app.relaunch();
        app.quit();
      } else {
        await restartBackend();
      }
    }
    return r;
  });
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  if (process.platform === 'win32') app.setAppUserModelId('com.stickknowledge.studio3d');
  registerIpc();
  createSplash();
  try {
    setSplash('Starting the studio engine…');
    await startBackend();
    setSplash('Opening the studio…');
    createMainWindow();
    setupAutoUpdater();
  } catch (e) {
    log.error(e);
    setSplash(`Could not start the backend.\n${e.message}\n\nLog: ${log.transports.file.getFile().path}`, true);
    if (SELFTEST) {
      fs.writeFileSync(path.join(process.env.SK_SELFTEST_DIR || app.getPath('temp'), 'sk_selftest.json'),
        JSON.stringify({ ok: false, error: String(e.message || e) }));
      app.quit();
    }
  }
});

app.on('before-quit', () => {
  quitting = true;
  stopBackend();
});
app.on('window-all-closed', () => app.quit());
