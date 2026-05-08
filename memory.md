# AGOS — Project Memory & Knowledge Base v2

> Enterprise Agentic OS for macOS — Persistent project knowledge.

---

## 📌 Project Identity

- **Name**: AGOS — Agentic Operating System
- **Type**: Native macOS application (`.dmg` distribution)
- **Owner**: Sehaj Vir Singh
- **Platform**: macOS (Apple Silicon / Intel)
- **Standard**: Enterprise-grade, institutional quality

---

## 🧠 Architecture Decisions

### ADR-001: Three-Language Architecture
- **Rust** → Kernel core (memory pager, IPC bus, firewall, crypto)
- **Go** → Orchestration (scheduler, gRPC, NATS, MCP server, daemon)
- **Swift/SwiftUI** → Native macOS UI (menu bar agent, `.dmg` packaging)
- **Python** → Agent intelligence only (LLM scripts, called as subprocesses)
- **Rationale**: Rust for memory-safe zero-GC kernel. Go for concurrent orchestration. Swift for Apple-native UX. Python for AI ecosystem.

### ADR-002: Native macOS App, Not Web Dashboard
- **Decision**: SwiftUI menu bar agent distributed as signed `.dmg`
- **Rationale**: Enterprise standard. Web dashboards are fragile, non-native. macOS apps integrate with Notification Center, Accessibility, status bar.
- **Packaging**: `create-dmg` or `pkgbuild` for enterprise MDM distribution

### ADR-003: Rust ↔ Go via CGo FFI
- **Decision**: Rust exposes `extern "C"` functions, Go calls via CGo
- **Rationale**: Go orchestrator manages agent lifecycle; Rust kernel handles hot-path operations (memory, IPC, security) with zero GC pause
- **Interface**: `libagos_kernel.dylib` loaded by `agosd` daemon

### ADR-004: NATS for Agent Messaging
- **Decision**: NATS pub/sub (not ZMQ from PoC)
- **Rationale**: Native Go client, request/reply + pub/sub, single binary, zero config

### ADR-005: ChromaDB for Semantic Memory
- **Decision**: Embedded ChromaDB vector database (Python)
- **Rationale**: No external server, persistent, supports multiple embedding models

### ADR-006: MCP Protocol for Tool Interface
- **Decision**: Go-native MCP server exposing macOS tools
- **Rationale**: Industry standard (Anthropic, Microsoft, Google). Any MCP client can use AGOS tools.

---

## 📦 Code Inventory

### Legacy PoC: `~/AGENTIC AGOS/`
| File | Status | Migration |
|---|---|---|
| `agent_kernel.py` | Working PoC | → Logic into `agents/orchestrator.py` |
| `mac_tools.py` | Working | → Migrate to Swift `MacTools.swift` + Python `mac/tools.py` |
| `memory_system.py` | Working | → `memory/episodic.py` + `memory/semantic.py` |
| `security_middleware.py` | Working | → Rust `firewall.rs` (rewrite) |
| `manifest.json` | Working | → `config/manifest.json` (extend) |

### Production: `~/AGENTIC_AGOS/`
| Component | Language | Status |
|---|---|---|
| `rust-kernel/` | Rust | 🔴 Not started |
| `go-orchestrator/` | Go | 🔴 Not started |
| `macos-app/` | Swift | 🔴 Not started |
| `agents/` | Python | 🔴 Not started |
| `memory/` | Python | 🔴 Not started |

---

## 🔑 API Keys

| Service | Status |
|---|---|
| Ollama (local) | ✅ Installed |
| Anthropic Claude | 🟡 Need key |
| Google Gemini | 🟡 Need key |
| Groq | 🟡 Optional |

---

## 🏗️ Build Phases

| # | Phase | Status |
|---|---|---|
| 1 | Architecture & Planning | ✅ Complete |
| 2 | Rust Kernel Core | 🔴 Not started |
| 3 | Go Orchestration Layer | 🔴 Not started |
| 4 | Swift macOS Application | 🔴 Not started |
| 5 | Python Agent Runtime | 🔴 Not started |
| 6 | Memory Stack | 🔴 Not started |
| 7 | DMG Packaging & Testing | 🔴 Not started |

---

## 💡 Key Gotchas

- **CGo + Rust FFI**: Rust lib must be built with `crate-type = ["cdylib"]` for Go to load via CGo
- **macOS Notarization**: Unsigned `.dmg` triggers Gatekeeper. Need Apple Developer ID for distribution.
- **SwiftUI + gRPC**: Use `grpc-swift` package (apple/grpc-swift on SPM)
- **NATS vs ZMQ**: PoC used ZMQ port 5555; production uses NATS port 4222
- **Python as Subprocess**: Agents run as Python subprocesses managed by Go daemon, NOT in-process
