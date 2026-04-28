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
    const resp = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/session?user_id=${userId || 1}`, { cache: 'no-store' });
    return await resp.json();
  } catch {
    return { messages: [], history_length: 0 };
  }
});

ipcMain.handle('health-check', async () => {
  try {
    const resp = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/health`, { cache: 'no-store' });
    return await resp.json();
  } catch {
    return { status: 'offline' };
  }
});

ipcMain.handle('fetch-workers', async (_event, userId) => {
  try {
    const resp = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/workers?user_id=${userId || 1}`, { cache: 'no-store' });
    return await resp.json();
  } catch {
    return { workers: [] };
  }
});

ipcMain.handle('fetch-worker-session', async (_event, taskId) => {
  try {
    const resp = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/workers/${taskId}/session`, { cache: 'no-store' });
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

// Streaming chat: opens SSE connection to /chat/stream and relays events to renderer
ipcMain.handle('stream-chat', async (_event, { message, userId }) => {
  try {
    const resp = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, user_id: userId || 1 }),
    });

    if (!resp.ok) {
      const errBody = await resp.text();
      mainWindow?.webContents?.send('chat-stream-event', { type: 'error', data: errBody });
      return { error: errBody };
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer
      const parts = buffer.split('\n\n');
      buffer = parts.pop(); // keep incomplete chunk

      for (const part of parts) {
        const lines = part.split('\n');
        let eventType = 'message';
        let data = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7);
          else if (line.startsWith('data: ')) data = line.slice(6);
        }
        if (data) {
          try {
            const parsed = JSON.parse(data);
            mainWindow?.webContents?.send('chat-stream-event', { type: eventType, data: parsed });
          } catch {
            mainWindow?.webContents?.send('chat-stream-event', { type: eventType, data });
          }
        }
      }
    }
    return { ok: true };
  } catch (err) {
    mainWindow?.webContents?.send('chat-stream-event', { type: 'error', data: err.message });
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
