/**
 * Ramesh Saini v7.1 — Ironclad MVP
 * Electron Preload Script
 * 
 * Exposes safe IPC channels to the renderer process.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('rameshAPI', {
  // Send a chat message and get response
  chat: (message, sessionId) => {
    return ipcRenderer.invoke('chat:send', { message, sessionId });
  },

  // Get the backend URL for direct API calls
  getBackendUrl: () => {
    return ipcRenderer.invoke('app:get-backend-url');
  },

  // Platform info
  platform: process.platform,
  version: '7.1.0-mvp'
});
