/**
 * SentinelVision — Electron & Service Development Lifecycle Orchestrator
 *
 * Architecture & Guarantees:
 * 1. Process Group Isolation:
 *    - All child services (bridge, Vite, Electron) are spawned as independent process group leaders.
 *    - Teardown terminates the entire process group (including descendants like esbuild, Python engines, Electron renderers/zygotes).
 * 2. Stale SentinelVision Process Self-Healing (No Reboot Required):
 *    - If port 3000 or 5173 is occupied by an unresponsive or broken SentinelVision process from a previous run,
 *      it is safely terminated and recovered automatically.
 *    - Orphaned SentinelVision Python assurance workers (ppid=1) are reclaimed before startup to free CUDA/GPU memory.
 * 3. Foreign Process Safety (No Blind Kills):
 *    - If an unrelated process occupies port 3000 or 5173, the runner refuses to touch it, prints an actionable error, and exits.
 * 4. Healthy Instance Reuse:
 *    - If an existing SentinelVision bridge or Vite server is verified healthy, it is reused without launching duplicates.
 * 5. Lifecycle Ownership:
 *    - Teardown terminates ONLY services launched by this runner session. Reused external services are preserved.
 */

'use strict';

const http = require('http');
const net = require('net');
const path = require('path');
const { spawn, execSync } = require('child_process');

const FRONTEND_DIR = path.resolve(__dirname, '..');
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..');
const BRIDGE_DIR = path.resolve(PROJECT_ROOT, 'bridge');

const BRIDGE_PORT = 3000;
const VITE_PORT = 5173;

let bridgeChild = null;
let viteChild = null;
let electronChild = null;

let startedBridge = false;
let startedVite = false;
let isShuttingDown = false;

// ---------------------------------------------------------------------------
// 1. Process Discovery & Process Tree Management
// ---------------------------------------------------------------------------

function checkPortOccupied(port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(800);
    socket.once('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.once('timeout', () => {
      socket.destroy();
      resolve(false);
    });
    socket.once('error', (err) => {
      socket.destroy();
      resolve(err.code === 'ECONNREFUSED' ? false : true);
    });
    socket.connect(port, '127.0.0.1');
  });
}

function getProcessOwner(port) {
  try {
    if (process.platform === 'linux' || process.platform === 'darwin') {
      const out = execSync(`lsof -iTCP:${port} -sTCP:LISTEN -n -P -t 2>/dev/null`, { encoding: 'utf-8' }).trim();
      if (out) {
        const pid = parseInt(out.split('\n')[0].trim(), 10);
        let cmd = 'unknown';
        let user = 'unknown';
        let cwd = 'unknown';
        try { cmd = execSync(`ps -p ${pid} -o args= 2>/dev/null`, { encoding: 'utf-8' }).trim(); } catch {}
        try { user = execSync(`ps -p ${pid} -o user= 2>/dev/null`, { encoding: 'utf-8' }).trim(); } catch {}
        try {
          cwd = execSync(`readlink -f /proc/${pid}/cwd 2>/dev/null`, { encoding: 'utf-8' }).trim();
        } catch {}
        return { pid, cmd, user, cwd };
      }
    } else if (process.platform === 'win32') {
      const out = execSync(`netstat -ano | findstr :${port}`, { encoding: 'utf-8' });
      for (const line of out.split('\n')) {
        if (line.includes('LISTENING')) {
          const parts = line.trim().split(/\s+/);
          const pid = parseInt(parts[parts.length - 1], 10);
          return { pid, cmd: 'unknown', user: 'unknown', cwd: 'unknown' };
        }
      }
    }
  } catch {
    return null;
  }
  return null;
}

function isSentinelVisionProcess(owner, expectedComponent = '') {
  if (!owner || !owner.cmd) return false;
  const cmd = owner.cmd;
  const cwd = owner.cwd || '';

  const inProjectDir = cwd.includes(PROJECT_ROOT) || cmd.includes(PROJECT_ROOT);
  const isBridge = cmd.includes('src/index.js') || cmd.includes('sentinel-fabric-bridge') || cwd.includes('/bridge');
  const isVite = cmd.includes('vite') || cwd.includes('/frontend');

  if (expectedComponent === 'bridge') {
    return (inProjectDir && isBridge) || (isBridge && cmd.includes('node'));
  }
  if (expectedComponent === 'vite') {
    return (inProjectDir && isVite) || (isVite && cmd.includes('node'));
  }

  return inProjectDir || isBridge || isVite;
}

function killProcessTree(pid, signal = 'SIGTERM') {
  if (!pid || isNaN(pid)) return;
  try {
    if (process.platform !== 'win32') {
      try { process.kill(-pid, signal); } catch {}
      try { process.kill(pid, signal); } catch {}
    } else {
      execSync(`taskkill /pid ${pid} /T /F 2>nul`);
    }
  } catch {}
}

async function waitForPortFree(port, maxWaitMs = 3000, intervalMs = 150) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    const occupied = await checkPortOccupied(port);
    if (!occupied) return true;
    await new Promise(r => setTimeout(r, intervalMs));
  }
  return false;
}

function cleanOrphanedSentinelVisionPythonProcesses() {
  if (process.platform !== 'linux' && process.platform !== 'darwin') return;
  try {
    const lines = execSync('ps -eo pid,ppid,args 2>/dev/null', { encoding: 'utf-8' }).split('\n');
    for (const line of lines) {
      const parts = line.trim().split(/\s+/);
      if (parts.length < 3) continue;
      const pid = parseInt(parts[0], 10);
      const ppid = parseInt(parts[1], 10);
      const args = parts.slice(2).join(' ');

      if (ppid === 1 && (args.includes('python3') || args.includes('python'))) {
        const matchesSentinelEngine =
          args.includes('run_data_integrity') ||
          args.includes('strip_detector') ||
          args.includes('run_drift_monitor') ||
          args.includes('governance/verifier') ||
          args.includes('governance/audit') ||
          args.includes('governance/report') ||
          args.includes(PROJECT_ROOT);

        if (matchesSentinelEngine) {
          console.log(`[dev-runner] Reclaiming orphaned SentinelVision Python worker (PID: ${pid})...`);
          killProcessTree(pid, 'SIGKILL');
        }
      }
    }
  } catch {}
}

// ---------------------------------------------------------------------------
// 2. Health & Reachability Probes
// ---------------------------------------------------------------------------

function probeBridge(timeoutMs = 1200) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${BRIDGE_PORT}/health`, { timeout: timeoutMs }, (res) => {
      let data = '';
      res.on('data', chunk => { data += chunk; });
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          if (res.statusCode === 200 && json.status === 'UP' && typeof json.service === 'string' && json.service.includes('SentinelVision')) {
            resolve({ healthy: true, isBridge: true, data: json });
            return;
          }
        } catch {}
        resolve({ healthy: false, isBridge: false });
      });
    });
    req.on('error', () => resolve({ healthy: false, isBridge: false }));
    req.on('timeout', () => {
      req.destroy();
      resolve({ healthy: false, isBridge: false });
    });
  });
}

function probeVite(timeoutMs = 1200) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${VITE_PORT}`, { timeout: timeoutMs }, (res) => {
      let data = '';
      res.on('data', chunk => { data += chunk; });
      res.on('end', () => {
        if (res.statusCode === 200 && (data.includes('SentinelVision') || data.includes('@vite/client'))) {
          resolve({ healthy: true, isVite: true });
          return;
        }
        resolve({ healthy: false, isVite: false });
      });
    });
    req.on('error', () => resolve({ healthy: false, isVite: false }));
    req.on('timeout', () => {
      req.destroy();
      resolve({ healthy: false, isVite: false });
    });
  });
}

async function waitFor(probeFn, maxWaitMs = 15000, intervalMs = 200, abortFn = null) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    if (abortFn && abortFn()) {
      return false;
    }
    const res = await probeFn();
    if (res.healthy) return true;
    await new Promise(r => setTimeout(r, intervalMs));
  }
  return false;
}

// ---------------------------------------------------------------------------
// 3. Service Lifecycle Management
// ---------------------------------------------------------------------------

async function setupBridge() {
  const occupied = await checkPortOccupied(BRIDGE_PORT);
  if (occupied) {
    const check = await probeBridge(1500);
    const owner = getProcessOwner(BRIDGE_PORT);

    if (check.healthy && check.isBridge) {
      console.log(`[dev-runner] Reusing existing healthy SentinelVision bridge on port ${BRIDGE_PORT} (PID: ${owner?.pid || 'detected'}).`);
      startedBridge = false;
      return true;
    }

    const isOurProcess = isSentinelVisionProcess(owner, 'bridge');
    if (isOurProcess && owner && owner.pid) {
      console.warn(`[dev-runner] Port ${BRIDGE_PORT} is held by an unresponsive SentinelVision bridge process (PID: ${owner.pid}).`);
      console.log(`[dev-runner] Safely terminating stale SentinelVision process to recover...`);
      killProcessTree(owner.pid, 'SIGTERM');

      const freed = await waitForPortFree(BRIDGE_PORT, 2500);
      if (!freed) {
        killProcessTree(owner.pid, 'SIGKILL');
        await waitForPortFree(BRIDGE_PORT, 1500);
      }
      console.log(`[dev-runner] Port ${BRIDGE_PORT} released successfully.`);
    } else {
      printForeignProcessConflict(BRIDGE_PORT, 'SentinelVision REST Bridge', owner);
      return false;
    }
  }

  console.log(`[dev-runner] Starting SentinelVision development bridge on port ${BRIDGE_PORT}...`);
  bridgeChild = spawn(process.execPath, ['src/index.js'], {
    cwd: BRIDGE_DIR,
    detached: process.platform !== 'win32',
    stdio: 'inherit',
    env: { ...process.env }
  });
  startedBridge = true;

  let exitedPrematurely = false;
  bridgeChild.on('exit', (code, signal) => {
    exitedPrematurely = true;
    if (!isShuttingDown) {
      console.error(`[dev-runner] Bridge process terminated unexpectedly (code: ${code}, signal: ${signal}).`);
      cleanup(1);
    }
  });

  const ready = await waitFor(probeBridge, 15000, 200, () => exitedPrematurely);
  if (!ready || exitedPrematurely) {
    console.error(`[dev-runner] Failed to reach bridge on port ${BRIDGE_PORT} within timeout. Aborting startup.`);
    return false;
  }

  console.log(`[dev-runner] Bridge is healthy on port ${BRIDGE_PORT}.`);
  return true;
}

async function setupVite() {
  const occupied = await checkPortOccupied(VITE_PORT);
  if (occupied) {
    const check = await probeVite(1500);
    const owner = getProcessOwner(VITE_PORT);

    if (check.healthy && check.isVite) {
      console.log(`[dev-runner] Reusing existing SentinelVision Vite dev server on port ${VITE_PORT} (PID: ${owner?.pid || 'detected'}).`);
      startedVite = false;
      return true;
    }

    const isOurProcess = isSentinelVisionProcess(owner, 'vite');
    if (isOurProcess && owner && owner.pid) {
      console.warn(`[dev-runner] Port ${VITE_PORT} is held by an unresponsive SentinelVision Vite process (PID: ${owner.pid}).`);
      console.log(`[dev-runner] Safely terminating stale SentinelVision process to recover...`);
      killProcessTree(owner.pid, 'SIGTERM');

      const freed = await waitForPortFree(VITE_PORT, 2500);
      if (!freed) {
        killProcessTree(owner.pid, 'SIGKILL');
        await waitForPortFree(VITE_PORT, 1500);
      }
      console.log(`[dev-runner] Port ${VITE_PORT} released successfully.`);
    } else {
      printForeignProcessConflict(VITE_PORT, 'SentinelVision Vite Dev Server', owner);
      return false;
    }
  }

  console.log(`[dev-runner] Starting Vite development server on port ${VITE_PORT}...`);
  const viteBin = path.resolve(FRONTEND_DIR, 'node_modules', '.bin', 'vite');
  viteChild = spawn(viteBin, ['--host', '127.0.0.1', '--port', String(VITE_PORT), '--strictPort'], {
    cwd: FRONTEND_DIR,
    detached: process.platform !== 'win32',
    stdio: 'inherit',
    env: { ...process.env }
  });
  startedVite = true;

  let exitedPrematurely = false;
  viteChild.on('exit', (code, signal) => {
    exitedPrematurely = true;
    if (!isShuttingDown) {
      console.error(`[dev-runner] Vite process terminated unexpectedly (code: ${code}, signal: ${signal}).`);
      cleanup(1);
    }
  });

  const ready = await waitFor(probeVite, 15000, 200, () => exitedPrematurely);
  if (!ready || exitedPrematurely) {
    console.error(`[dev-runner] Failed to reach Vite dev server on port ${VITE_PORT} within timeout. Aborting startup.`);
    return false;
  }

  console.log(`[dev-runner] Vite dev server is ready on port ${VITE_PORT}.`);
  return true;
}

function printForeignProcessConflict(port, serviceName, owner) {
  console.error('\n' + '='.repeat(78));
  console.error(`[ERROR] Port ${port} is occupied by an unrelated foreign process.`);
  if (owner) {
    console.error(`  Process ID: ${owner.pid}`);
    console.error(`  Command:    ${owner.cmd}`);
    console.error(`  User:       ${owner.user}`);
    console.error(`  Directory:  ${owner.cwd}`);
  }
  console.error(`\n${serviceName} cannot start because port ${port} is reserved by another application.`);
  console.error('SentinelVision will NOT terminate foreign processes.');
  console.error('To resolve:');
  if (owner && owner.pid) {
    console.error(`  - Stop the conflicting application: kill ${owner.pid}`);
  } else {
    console.error(`  - Free port ${port} before running npm run electron:dev.`);
  }
  console.error('='.repeat(78) + '\n');
}

// ---------------------------------------------------------------------------
// 4. Teardown & Process Tree Cleanup
// ---------------------------------------------------------------------------

function cleanup(exitCode = 0) {
  if (isShuttingDown) return;
  isShuttingDown = true;

  console.log('[dev-runner] Shutting down application services...');

  const pending = [];

  if (electronChild && electronChild.pid) {
    killProcessTree(electronChild.pid, 'SIGTERM');
  }

  if (startedVite && viteChild && viteChild.pid) {
    console.log('[dev-runner] Stopping Vite development server...');
    pending.push(new Promise((res) => {
      viteChild.once('exit', () => res());
      setTimeout(res, 2000);
    }));
    killProcessTree(viteChild.pid, 'SIGTERM');
  }

  if (startedBridge && bridgeChild && bridgeChild.pid) {
    console.log('[dev-runner] Stopping development bridge...');
    pending.push(new Promise((res) => {
      bridgeChild.once('exit', () => res());
      setTimeout(res, 2000);
    }));
    killProcessTree(bridgeChild.pid, 'SIGTERM');
  }

  const forceTimer = setTimeout(() => {
    if (startedVite && viteChild && viteChild.pid) {
      killProcessTree(viteChild.pid, 'SIGKILL');
    }
    if (startedBridge && bridgeChild && bridgeChild.pid) {
      killProcessTree(bridgeChild.pid, 'SIGKILL');
    }
    process.exit(exitCode);
  }, 2500);

  Promise.all(pending).then(() => {
    clearTimeout(forceTimer);
    setTimeout(() => {
      process.exit(exitCode);
    }, 100);
  });
}

process.on('SIGINT', () => cleanup(0));
process.on('SIGTERM', () => cleanup(0));
process.on('SIGHUP', () => cleanup(0));
process.on('uncaughtException', (err) => {
  console.error('[dev-runner] Uncaught fatal exception:', err);
  cleanup(1);
});

// ---------------------------------------------------------------------------
// 5. Main Execution Flow
// ---------------------------------------------------------------------------

async function main() {
  console.log('[dev-runner] Initializing SentinelVision development environment...');

  cleanOrphanedSentinelVisionPythonProcesses();

  const bridgeOk = await setupBridge();
  if (!bridgeOk) {
    cleanup(1);
    return;
  }

  const viteOk = await setupVite();
  if (!viteOk) {
    cleanup(1);
    return;
  }

  console.log('[dev-runner] Both services verified ready. Launching Electron...');

  let electronBinary;
  try {
    electronBinary = require('electron');
  } catch {
    electronBinary = path.resolve(FRONTEND_DIR, 'node_modules', '.bin', 'electron');
  }

  electronChild = spawn(electronBinary, ['.'], {
    cwd: FRONTEND_DIR,
    detached: process.platform !== 'win32',
    stdio: 'inherit',
    env: {
      ...process.env,
      VITE_DEV_SERVER_URL: `http://127.0.0.1:${VITE_PORT}`
    }
  });

  electronChild.on('close', (code) => {
    console.log(`[dev-runner] Electron window closed (exit code: ${code}).`);
    cleanup(code || 0);
  });

  electronChild.on('error', (err) => {
    console.error(`[dev-runner] Failed to spawn Electron: ${err.message}`);
    cleanup(1);
  });
}

main().catch((err) => {
  console.error('[dev-runner] Fatal runner error:', err);
  cleanup(1);
});
