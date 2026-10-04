const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('sentinel', {
  platform: process.platform,
  isElectron: true,
  versions: {
    electron: process.versions.electron || '—',
    chrome: process.versions.chrome || '—',
    node: process.versions.node || '—'
  },
  openDialog: (options) => ipcRenderer.invoke('sentinel:openDialog', options)
});
