#!/bin/bash
# AGOS — Development Mode Launcher
# Starts NATS, Ollama, Go Daemon, and Python agents for local development.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDS=()

cleanup() {
    echo ""
    echo "[DEV] Shutting down all services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    echo "[DEV] All services stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "╔══════════════════════════════════════════╗"
echo "║     AGOS Development Environment          ║"
echo "╚══════════════════════════════════════════╝"

# --- NATS Server ---
echo "[DEV] Starting NATS server on :4222..."
nats-server -p 4222 -T &
PIDS+=($!)
sleep 1

# --- Ollama ---
echo "[DEV] Starting Ollama..."
ollama serve &
PIDS+=($!)
sleep 2

# --- Go Daemon ---
if [ -f "$ROOT/build/agosd" ]; then
    echo "[DEV] Starting AGOS daemon..."
    "$ROOT/build/agosd" --dev --port 50051 --ws-port 8765 --manifest "$ROOT/config/manifest.json" &
    PIDS+=($!)
else
    echo "[DEV] ⚠️  Daemon not built. Run: ./scripts/build.sh"
fi

# --- Python Agent Runtime ---
echo "[DEV] Starting Python agent runtime..."
if [ -f "$ROOT/agents/runtime.py" ]; then
    python3 "$ROOT/agents/runtime.py" &
    PIDS+=($!)
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Services Running:                        ║"
echo "║  • NATS Server    → :4222                ║"
echo "║  • Ollama         → :11434               ║"
echo "║  • AGOS Daemon    → :50051 (gRPC)        ║"
echo "║  • Telemetry      → :8765  (HTTP)        ║"
echo "║                                           ║"
echo "║  Health: curl http://localhost:8765/health ║"
echo "║  Press Ctrl+C to stop all services        ║"
echo "╚══════════════════════════════════════════╝"

# Wait for all background processes.
wait
