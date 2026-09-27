'use strict';

const { app, BrowserWindow, shell } = require('electron');
const path = require('path');

// SentinelVision's ML/CUDA workloads run in the Python engines, not Chromium.
// Disable Electron/Chromium hardware acceleration so the desktop shell also
// works on Linux systems where the Chromium GPU process cannot launch.
app.disableHardwareAcceleration();

const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL || '';

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1120,
    minHeight: 700,
    show: false,
    backgroundColor: '#05070f',
    autoHideMenuBar: true,
    title: 'SentinelVision — AI Security Command Center',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  if (DEV_SERVER_URL) {
    mainWindow.loadURL(DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  mainWindow.webContents.on('did-finish-load', () => {
    console.log('[sentinelvision] renderer loaded OK');
  });
  mainWindow.webContents.on('did-fail-load', (_e, code, desc) => {
    console.error('[sentinelvision] did-fail-load:', code, desc);
  });
  mainWindow.webContents.on('render-process-gone', (_e, details) => {
    console.error('[sentinelvision] renderer gone:', details.reason);
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());

  // Open external links in the default browser, never inside the app shell.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  app.quit();
});
