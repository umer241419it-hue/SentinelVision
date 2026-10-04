const { app, BrowserWindow, shell, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');

// SentinelVision's ML/CUDA workloads run in the Python engines, not Chromium.
// Some Linux environments still attempt to spawn Chromium's GPU child process
// even after hardware acceleration is disabled. Keep Chromium out of the
// separate GPU-process path so the Electron renderer can start reliably.
app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-gpu-compositing');
app.commandLine.appendSwitch('in-process-gpu');
app.commandLine.appendSwitch('disable-gpu-sandbox');
app.disableHardwareAcceleration();

const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL || '';

let mainWindow = null;

// Native file/folder dialog handler for SentinelVision asset selection
ipcMain.handle('sentinel:openDialog', async (_event, options = {}) => {
  if (!mainWindow) return null;
  const isDirectory = options.type === 'directory';
  const properties = isDirectory ? ['openDirectory'] : ['openFile', 'multiSelections'];
  const res = await dialog.showOpenDialog(mainWindow, {
    title: options.title || (isDirectory ? 'Select Folder' : 'Select File'),
    properties,
    filters: options.filters
  });
  if (res.canceled || !res.filePaths.length) return null;
  return {
    canceled: false,
    filePaths: res.filePaths,
    isFolder: isDirectory
  };
});

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
