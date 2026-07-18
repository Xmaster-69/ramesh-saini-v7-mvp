/**
 * Ramesh Saini v7.4 — Ironclad MVP
 * Electron Preload Script — expanded IPC bridge
 * 
 * Exposes secure channels for:
 * - Chat messages
 * - API key management (masked, encrypted)
 * - Tool execution (real-time status streaming)
 * - System status / backend health
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('rameshAPI', {

  // ================================================================
  // CHAT
  // ================================================================
  chat: (message, sessionId) => {
    return ipcRenderer.invoke('chat:send', { message, sessionId });
  },

  getBackendUrl: () => {
    return ipcRenderer.invoke('app:get-backend-url');
  },

  // ================================================================
  // API KEYS (secure — keys never touch renderer directly)
  // ================================================================
  apiKeys: {
    /** Get status of all configured API keys (previews only, never full keys) */
    getStatus: () => ipcRenderer.invoke('apikeys:get-status'),

    /** Set an API key for a provider. Key is encrypted before storage. */
    setKey: (provider, key) => ipcRenderer.invoke('apikeys:set-key', { provider, key }),

    /** Test a provider key by making a lightweight API call */
    testKey: (provider, key) => ipcRenderer.invoke('apikeys:test-key', { provider, key }),

    /** Remove a stored key */
    removeKey: (provider) => ipcRenderer.invoke('apikeys:remove-key', { provider }),

    /** Get which keys are available (from env) */
    discoverFromEnv: () => ipcRenderer.invoke('apikeys:discover'),
  },

  // ================================================================
  // TOOL EXECUTION (real-time status)
  // ================================================================
  agent: {
    /** Send a message to the agent with tool-calling capability */
    sendMessage: (message, sessionId) => {
      return ipcRenderer.invoke('agent-chat', { message, sessionId });
    },

    /** Listen for real-time tool execution updates */
    onToolUpdate: (callback) => {
      const handler = (event, data) => callback(data);
      ipcRenderer.on('agent-tool-update', handler);
      return () => ipcRenderer.removeListener('agent-tool-update', handler);
    },

    /** Execute a specific tool directly */
    executeTool: (toolName, params) => {
      return ipcRenderer.invoke('agent-execute-tool', { toolName, params });
    },

    /** Get available tool schemas */
    getToolSchemas: () => {
      return ipcRenderer.invoke('agent-get-tool-schemas');
    },
  },

  // ================================================================
  // SYSTEM STATUS
  // ================================================================
  system: {
    /** Get health + stats from backend */
    getHealth: () => ipcRenderer.invoke('system:get-health'),

    /** Get LLM Router model catalog */
    getModelCatalog: () => ipcRenderer.invoke('system:get-model-catalog'),

    /** Get security guard stats */
    getSecurityStats: () => ipcRenderer.invoke('system:get-security-stats'),

    /** Listen for periodic status updates */
    onStatusUpdate: (callback) => {
      const handler = (event, data) => callback(data);
      ipcRenderer.on('system:status-update', handler);
      return () => ipcRenderer.removeListener('system:status-update', handler);
    },
  },

  // ================================================================
  // PLATFORM
  // ================================================================
  platform: process.platform,
  version: '7.4.0-mvp',
});
