#!/bin/bash
# AGOS — Full Build Pipeline
# Builds: Rust Kernel → Go Daemon → (Swift App — requires Xcode)
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "╔══════════════════════════════════════════╗"
echo "║     AGOS Build Pipeline                   ║"
echo "╚══════════════════════════════════════════╝"
echo "[BUILD] Root: $ROOT"

# --- Phase 1: Rust Kernel ---
echo ""
echo "═══ Phase 1: Rust Kernel ═══"
cd "$ROOT/rust-kernel"
echo "[RUST] Building libagos_kernel (release)..."
cargo build --release 2>&1
echo "[RUST] Running tests..."
cargo test 2>&1
DYLIB="$ROOT/rust-kernel/target/release/libagos_kernel.dylib"
if [ -f "$DYLIB" ]; then
    echo "[RUST] ✅ Built: $DYLIB"
    echo "[RUST]    Size: $(du -h "$DYLIB" | cut -f1)"
else
    echo "[RUST] ❌ Build failed — dylib not found"
    exit 1
fi

# --- Phase 2: Go Daemon ---
echo ""
echo "═══ Phase 2: Go Daemon ═══"
cd "$ROOT/go-orchestrator"

# For CGo FFI with Rust (when bridge is wired):
# export CGO_ENABLED=1
# export CGO_LDFLAGS="-L$ROOT/rust-kernel/target/release -lagos_kernel"
# export DYLD_LIBRARY_PATH="$ROOT/rust-kernel/target/release:$DYLD_LIBRARY_PATH"

echo "[GO] Downloading dependencies..."
go mod tidy 2>&1 || echo "[GO] Warning: go mod tidy had issues (expected if deps not yet resolved)"
echo "[GO] Building agosd daemon..."
go build -o "$ROOT/build/agosd" ./cmd/agosd/ 2>&1
if [ -f "$ROOT/build/agosd" ]; then
    echo "[GO] ✅ Built: $ROOT/build/agosd"
    echo "[GO]    Size: $(du -h "$ROOT/build/agosd" | cut -f1)"
else
    echo "[GO] ❌ Build failed"
    exit 1
fi

# --- Phase 3: Swift App (requires Xcode) ---
echo ""
echo "═══ Phase 3: Swift App ═══"
if command -v xcodebuild &> /dev/null; then
    if [ -d "$ROOT/macos-app/AGOS.xcodeproj" ]; then
        cd "$ROOT/macos-app"
        echo "[SWIFT] Building AGOS.app..."
        xcodebuild -scheme AGOS -configuration Release -derivedDataPath "$ROOT/build/swift" 2>&1
        echo "[SWIFT] ✅ Built"
    else
        echo "[SWIFT] ⏩ Xcode project not yet created — skipping"
    fi
else
    echo "[SWIFT] ⏩ Xcode not installed — skipping Swift build"
fi

# --- Summary ---
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     Build Complete                         ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Rust Kernel: ✅ libagos_kernel.dylib     ║"
echo "║  Go Daemon:   ✅ agosd                    ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Run: ./scripts/start-dev.sh to start AGOS"
