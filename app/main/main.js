/**
 * Ramesh Saini v7.1 — Ironclad MVP
 * Electron Main Process
 * 
 * - Spawns the Python FastAPI backend as a child process
 * - Creates the BrowserWindow with React chat UI
 * - Manages lifecycle: start Python → show UI → graceful shutdown
 */
const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

// ============================================================
// Configuration
// ============================================================
const BACKEND_PORT = process.env.MVP_PORT || 8567;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

let mainWindow = null;
let pythonProcess = null;

// ============================================================
// Python Backend Management
// ============================================================

function getBackendScriptPath() {
  if (isDev) {
    return path.join(__dirname, '..', 'backend', 'main.py');
  }
  // In packaged build, backend is bundled in the resources
  return path.join(process.resourcesPath, 'backend', 'main.py');
}

function getPythonCommand() {
  return process.platform === 'win32' ? 'python' : 'python3';
}

function startPythonBackend() {
  return new Promise((resolve, reject) => {
    const scriptPath = getBackendScriptPath();
    console.log(`[Main] Starting Python backend: ${scriptPath}`);
    
    const pythonCmd = getPythonCommand();
    
    pythonProcess = spawn(pythonCmd, [scriptPath], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        MVP_PORT: String(BACKEND_PORT),
        RAMESHMEM_DB: path.join(app.getPath('userData'), 'ramesh_mvp.db'),
        PYTHONUNBUFFERED: '1'
      }
    });

    pythonProcess.stdout.on('data', (data) => {
      console.log(`[Backend] ${data.toString().trim()}`);
    });

    pythonProcess.stderr.on('data', (data) => {
      console.error(`[Backend:err] ${data.toString().trim()}`);
    });

    pythonProcess.on('error', (err) => {
      console.error('[Main] Failed to start Python backend:', err.message);
      reject(err);
    });

    pythonProcess.on('exit', (code) => {
      console.log(`[Main] Python backend exited with code ${code}`);
      pythonProcess = null;
    });

    // Wait for backend to be ready by polling /health
    let attempts = 0;
    const maxAttempts = 30; // 15 seconds max
    const healthCheck = setInterval(() => {
      attempts++;
      const req = http.get(`${BACKEND_URL}/health`, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          clearInterval(healthCheck);
          console.log('[Main] ✅ Python backend is ready');
          resolve();
        });
      });
      req.on('error', () => {
        if (attempts >= maxAttempts) {
          clearInterval(healthCheck);
          reject(new Error('Backend failed to start within timeout'));
        } else {
          console.log(`[Main] Waiting for backend... (${attempts}/${maxAttempts})`);
        }
      });
      req.setTimeout(2000, () => req.destroy());
    }, 500);
  });
}

function stopPythonBackend() {
  if (pythonProcess) {
    console.log('[Main] Stopping Python backend...');
    pythonProcess.kill('SIGTERM');
    
    // Force kill after 3 seconds
    setTimeout(() => {
      if (pythonProcess) {
        pythonProcess.kill('SIGKILL');
        pythonProcess = null;
      }
    }, 3000);
  }
}

// ============================================================
// IPC Handlers
// ============================================================

ipcMain.handle('chat:send', async (event, { message, sessionId }) => {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ message, session_id: sessionId });
    
    const req = http.request(`${BACKEND_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body)
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(new Error(`Parse error: ${e.message}`));
        }
      });
    });
    
    req.on('error', reject);
    req.write(body);
    req.end();
  });
});

ipcMain.handle('app:get-backend-url', () => BACKEND_URL);

// ============================================================
// Window Creation
// ============================================================

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    backgroundColor: '#0d1117',
    title: 'Ramesh Saini v7.1 MVP',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    show: false
  });

  if (isDev) {
    // In dev, load from the Vite dev server or built HTML
    const rendererPath = path.join(__dirname, '..', 'renderer', 'dist', 'index.html');
    if (require('fs').existsSync(rendererPath)) {
      mainWindow.loadFile(rendererPath);
    } else {
      mainWindow.loadURL(`http://localhost:5173`);
    }
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'dist', 'index.html'));
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ============================================================
// App Lifecycle
// ============================================================

app.whenReady().then(async () => {
  try {
    await startPythonBackend();
    createWindow();
  } catch (err) {
    console.error('[Main] Failed to start:', err.message);
    // Show error window
    mainWindow = new BrowserWindow({ width: 600, height: 400 });
    mainWindow.loadURL(`data:text/html,<h1 style="color:red;">Failed to start backend: ${err.message}</h1>`);
    mainWindow.show();
  }
});

app.on('window-all-closed', () => {
  stopPythonBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  stopPythonBackend();
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});
