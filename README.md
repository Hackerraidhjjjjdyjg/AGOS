# AGOS — Agentic Operating System for macOS

> Enterprise-grade native macOS application. Rust kernel + Go orchestration + Swift UI. Distributed as `.dmg`.

## Architecture

```
┌──────────────────────────────────────┐
│  Swift/SwiftUI (macOS Menu Bar App)  │
│  └── gRPC client to daemon           │
├──────────────────────────────────────┤
│  Go Orchestrator (agosd daemon)      │
│  ├── Agent Scheduler (P0-P4)         │
│  ├── gRPC Server                     │
│  ├── MCP Protocol Server             │
│  └── CGo FFI → Rust Kernel           │
├──────────────────────────────────────┤
│  Rust Kernel (libagos_kernel.dylib)  │
│  ├── V-RAM Memory Pager              │
│  ├── IPC Bus (pub/sub)               │
│  ├── Constitutional Firewall         │
│  └── Agent Attestation (Ed25519)     │
├──────────────────────────────────────┤
│  Python Agents (subprocess)          │
│  ├── Orchestrator (task decomp)      │
│  ├── System Agent (macOS tools)      │
│  ├── Research Agent                  │
│  └── Code Agent                      │
└──────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Install dependencies
make install

# 2. Build everything (Rust → Go)
make build

# 3. Run in dev mode
make run

# 4. Package as DMG
make package
```

## Requirements

- macOS 13+ (Ventura or later)
- Rust 1.77+ (`rustup`)
- Go 1.22+ (`brew install go`)
- Python 3.11+ (`brew install python@3.11`)
- Xcode 15+ (for Swift app, Mac App Store)
- Ollama (`brew install ollama`)

## Project Structure

```
rust-kernel/     → Rust: memory pager, IPC bus, firewall, crypto
go-orchestrator/ → Go: scheduler, gRPC, MCP, NATS, daemon
macos-app/       → Swift: native macOS menu bar app
agents/          → Python: base agent, orchestrator, system agent
memory/          → Python: episodic (SQLite), semantic (ChromaDB)
config/          → JSON/TOML: security manifest, agent config
scripts/         → Bash: build, install, dev, DMG packaging
```

## License

Proprietary — Sehaj Vir Singh
