#!/usr/bin/env bash
# ==============================================================================
# SentinelVision - Unified Trust & Assurance Platform Startup Script
# SIH Problem Statement 26228: Trustworthy Computer Vision Integrity Assurance
# ==============================================================================
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$PROJECT_ROOT"

echo "======================================================================"
echo "    SENTINELVISION: TRUSTWORTHY COMPUTER VISION INTEGRITY PLATFORM    "
echo "======================================================================"
echo "[*] Project Root: $PROJECT_ROOT"
echo "[*] Timestamp:    $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# 1. Environment & Pre-flight Checks
mkdir -p logs
mkdir -p reports/runs
mkdir -p data/uploads

echo "[*] Checking Python environment..."
python3 --version

echo "[*] Checking Node.js environment..."
node --version
npm --version

echo "[*] Checking Hardware / GPU Acceleration..."
GPU_STATUS=$(python3 -c "
import sys
try:
    import torch
    if torch.cuda.is_available():
        print(f'ACTIVE: {torch.cuda.get_device_name(0)} (CUDA {torch.version.cuda})')
    else:
        print('INACTIVE: CUDA not available, using CPU')
except Exception as e:
    print(f'WARNING: {e}')
" 2>/dev/null || echo "CPU fallback")
echo "    GPU Status: $GPU_STATUS"

# 2. Cleanup stale processes on ports 3000 and 5173 if running
echo "[*] Checking network ports..."
fuser -k 3000/tcp >/dev/null 2>&1 || true
fuser -k 5173/tcp >/dev/null 2>&1 || true

# 3. Start Backend API Bridge Service (Port 3000)
echo "[*] Starting SentinelVision Assurance Engine & REST Bridge (Port 3000)..."
(cd "$PROJECT_ROOT/bridge" && node src/index.js) > "$PROJECT_ROOT/logs/bridge.log" 2>&1 &
BRIDGE_PID=$!
echo "    -> Backend PID: $BRIDGE_PID (Logs: logs/bridge.log)"

# 4. Wait for Backend Health Check
echo "[*] Waiting for Backend Bridge to become healthy..."
MAX_WAIT=20
WAIT_COUNT=0
BACKEND_UP=0
while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if curl -s http://127.0.0.1:3000/health | grep -q "UP"; then
        BACKEND_UP=1
        break
    fi
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

if [ $BACKEND_UP -eq 1 ]; then
    echo "    -> [OK] Backend Bridge is ONLINE at http://127.0.0.1:3000"
else
    echo "    -> [WARNING] Backend health check took longer than expected. Continuing startup..."
fi

# 5. Start Frontend UI Service (Port 5173)
echo "[*] Starting SentinelVision Command Center UI (Port 5173)..."
(cd "$PROJECT_ROOT/frontend" && npm run dev -- --host 127.0.0.1 --port 5173) > "$PROJECT_ROOT/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "    -> Frontend PID: $FRONTEND_PID (Logs: logs/frontend.log)"

# 6. Wait for Frontend Availability
WAIT_COUNT=0
FRONTEND_UP=0
while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if curl -s http://127.0.0.1:5173 | grep -q "SentinelVision"; then
        FRONTEND_UP=1
        break
    fi
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

if [ $FRONTEND_UP -eq 1 ]; then
    echo "    -> [OK] Frontend Command Center is ONLINE at http://127.0.0.1:5173"
fi

# Trap signals for graceful shutdown
cleanup() {
    echo ""
    echo "[!] Shutting down SentinelVision services..."
    kill $FRONTEND_PID 2>/dev/null || true
    kill $BRIDGE_PID 2>/dev/null || true
    wait $FRONTEND_PID 2>/dev/null || true
    wait $BRIDGE_PID 2>/dev/null || true
    echo "[OK] SentinelVision services stopped cleanly."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

echo "======================================================================"
echo "          SENTINELVISION IS READY FOR OPERATION (OFFLINE)             "
echo "======================================================================"
echo "  Web UI Console:      http://127.0.0.1:5173"
echo "  Backend API / Health: http://127.0.0.1:3000/health"
echo ""
echo "  Pre-configured Accounts:"
echo "    - Analyst: analyst@sentinelvision.io  /  Password123!"
echo "    - Auditor: auditor@sentinelvision.io  /  Password123!"
echo ""
echo "  Press Ctrl+C to stop all services."
echo "======================================================================"

# Keep running until Ctrl+C
wait
