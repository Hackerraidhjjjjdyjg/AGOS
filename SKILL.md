---
name: AGOS Build Skill
description: How to build, run, and develop the AGOS Enterprise Agentic OS for macOS (Rust + Go + Swift)
---

# AGOS — Enterprise Agentic OS for macOS

## Architecture

```
┌─────────────────────────────────┐
│   Swift/SwiftUI (macOS App)     │  ← Native menu bar agent, .dmg install
│   └── gRPC client               │
├─────────────────────────────────┤
│   Go Orchestrator (agosd)       │  ← Agent scheduler, MCP, NATS
│   └── CGo FFI bridge            │
├─────────────────────────────────┤
│   Rust Kernel (libagos)         │  ← Memory pager, IPC bus, firewall
├─────────────────────────────────┤
│   Python Agents (subprocess)    │  ← LLM inference, RAG, research
└─────────────────────────────────┘
```

## Prerequisites

```bash
# System dependencies
// turbo
brew install go protobuf nats-server ollama node
// turbo
brew install create-dmg

# Rust toolchain
// turbo
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Python dependencies
// turbo
pip install -r requirements.txt

# Xcode (from Mac App Store — must be installed manually)
# Required for Swift/SwiftUI compilation and DMG signing
```

## Build Pipeline

### 1. Build Rust Kernel
```bash
// turbo
cd ~/AGENTIC_AGOS/rust-kernel && cargo build --release
# Output: target/release/libagos_kernel.dylib
```

### 2. Build Go Daemon
```bash
// turbo
cd ~/AGENTIC_AGOS/go-orchestrator && CGO_ENABLED=1 go build -o agosd ./cmd/agosd/
```

### 3. Build Swift App
```bash
cd ~/AGENTIC_AGOS/macos-app && xcodebuild -scheme AGOS -configuration Release
```

### 4. Package DMG
```bash
cd ~/AGENTIC_AGOS && bash scripts/package-dmg.sh
```

## Development Mode

```bash
# Terminal 1: NATS server
// turbo
nats-server -p 4222

# Terminal 2: Ollama
// turbo
ollama serve

# Terminal 3: Go daemon (dev mode)
cd ~/AGENTIC_AGOS/go-orchestrator && go run ./cmd/agosd/ --dev

# Terminal 4: Python agents
cd ~/AGENTIC_AGOS && python -m agents.runtime
```

## Testing

```bash
# Rust tests
// turbo
cd ~/AGENTIC_AGOS/rust-kernel && cargo test

# Go tests
// turbo
cd ~/AGENTIC_AGOS/go-orchestrator && go test ./...

# Python tests
// turbo
cd ~/AGENTIC_AGOS && python -m pytest tests/agents/ -v
```

## Key Files

| File | Language | Purpose |
|---|---|---|
| `rust-kernel/src/memory/pager.rs` | Rust | V-RAM page manager |
| `rust-kernel/src/ipc/bus.rs` | Rust | Zero-copy IPC bus |
| `rust-kernel/src/security/firewall.rs` | Rust | Constitutional firewall |
| `go-orchestrator/scheduler/scheduler.go` | Go | Preemptive agent scheduler |
| `go-orchestrator/bridge/rust_ffi.go` | Go | CGo bridge to Rust |
| `macos-app/AGOS/AGOSApp.swift` | Swift | macOS app entry point |
| `agents/orchestrator.py` | Python | Multi-agent task decomposition |
| `config/manifest.json` | JSON | Security policy |
