const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('yoloAPI', {
  sendMessage: (payload) => ipcRenderer.invoke('send-message', payload),
  streamChat: (payload) => ipcRenderer.invoke('stream-chat', payload),
  onChatStreamEvent: (callback) => {
    ipcRenderer.on('chat-stream-event', (_event, data) => callback(data));
  },
  removeChatStreamListeners: () => {
    ipcRenderer.removeAllListeners('chat-stream-event');
  },
  runCommand: (payload) => ipcRenderer.invoke('run-command', payload),
  getSession: (payload) => ipcRenderer.invoke('get-session', payload),
  healthCheck: () => ipcRenderer.invoke('health-check'),
  fetchWorkers: (userId) => ipcRenderer.invoke('fetch-workers', userId),
  fetchWorkerSession: (taskId) => ipcRenderer.invoke('fetch-worker-session', taskId),
  onBridgeStatus: (callback) => {
    ipcRenderer.on('bridge-status', (_event, status) => callback(status));
  },
});
