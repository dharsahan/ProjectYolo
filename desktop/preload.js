const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('yoloAPI', {
  sendMessage: (payload) => ipcRenderer.invoke('send-message', payload),
  runCommand: (payload) => ipcRenderer.invoke('run-command', payload),
  getSession: (payload) => ipcRenderer.invoke('get-session', payload),
  healthCheck: () => ipcRenderer.invoke('health-check'),
  fetchWorkers: (userId) => ipcRenderer.invoke('fetch-workers', userId),
  fetchWorkerSession: (taskId) => ipcRenderer.invoke('fetch-worker-session', taskId),
  onBridgeStatus: (callback) => {
    ipcRenderer.on('bridge-status', (_event, status) => callback(status));
  },
});
