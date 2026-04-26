const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');

let mainWindow;
const BRIDGE_PORT = parseInt(process.env.DESKTOP_BRIDGE_PORT || '8790', 10);

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    title: 'Yolo',
    icon: path.join(__dirname, 'renderer', 'icon.png'),
    backgroundColor: '#0f0f1a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    frame: process.platform === 'darwin' ? false : true,
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── IPC Handlers (all relay to the bridge started by server.py / bot.py) ──

ipcMain.handle('send-message', async (_event, { message, userId }) => {
  try {
    const resp = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, user_id: userId || 1 }),
    });
    return await resp.json();
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('get-session', async (_event, { userId }) => {
  try {
    const resp = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/session?user_id=${userId || 1}`);
    return await resp.json();
  } catch {
    return { messages: [], history_length: 0 };
  }
});

ipcMain.handle('health-check', async () => {
  try {
    const resp = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/health`);
    return await resp.json();
  } catch {
    return { status: 'offline' };
  }
});

ipcMain.handle('fetch-workers', async (_event, userId) => {
  try {
    const resp = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/workers?user_id=${userId || 1}`);
    return await resp.json();
  } catch {
    return { workers: [] };
  }
});

ipcMain.handle('fetch-worker-session', async (_event, taskId) => {
  try {
    const resp = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/workers/${taskId}/session`);
    return await resp.json();
  } catch {
    return { messages: [] };
  }
});

ipcMain.handle('run-command', async (_event, { command, args, userId }) => {
  try {
    const resp = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, args: args || [], user_id: userId || 1 }),
    });
    return await resp.json();
  } catch (err) {
    return { error: err.message };
  }
});

// ── App lifecycle ──

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
