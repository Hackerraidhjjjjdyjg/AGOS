#!/bin/bash
# AGOS — DMG Packager for macOS
# Builds the Go daemon, bundles web UI + agents, creates .dmg

set -euo pipefail

APP_NAME="AGOS"
VERSION="0.1.0"
BUILD_DIR="/tmp/agos-build"
DMG_DIR="/tmp/agos-dmg"
OUTPUT="$HOME/Desktop/AGOS-${VERSION}.dmg"
AGOS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "╔══════════════════════════════════════════╗"
echo "║  AGOS DMG Packager v${VERSION}              ║"
echo "╚══════════════════════════════════════════╝"

# Clean
rm -rf "$BUILD_DIR" "$DMG_DIR"
mkdir -p "$BUILD_DIR/${APP_NAME}.app/Contents/MacOS"
mkdir -p "$BUILD_DIR/${APP_NAME}.app/Contents/Resources"

# ─── 1. Build Go daemon ─────────────────────────

echo "🔨 Building Go daemon..."
cd "$AGOS_ROOT/go-orchestrator"
CGO_ENABLED=0 go build -o "$BUILD_DIR/${APP_NAME}.app/Contents/MacOS/agosd" ./cmd/agosd/
echo "   ✅ Binary built"

# ─── 2. Build Rust kernel ───────────────────────

echo "🦀 Building Rust kernel..."
cd "$AGOS_ROOT/rust-kernel"
cargo build --release --quiet
cp target/release/libagos_kernel.dylib "$BUILD_DIR/${APP_NAME}.app/Contents/MacOS/" 2>/dev/null || true
echo "   ✅ Kernel built"

# ─── 3. Bundle web UI ───────────────────────────

echo "🌐 Bundling web UI..."
cp -r "$AGOS_ROOT/web" "$BUILD_DIR/${APP_NAME}.app/Contents/Resources/web"
echo "   ✅ Web UI bundled"

# ─── 4. Bundle Python agents ────────────────────

echo "🤖 Bundling agents..."
cp -r "$AGOS_ROOT/agents" "$BUILD_DIR/${APP_NAME}.app/Contents/Resources/agents"
echo "   ✅ Agents bundled"

# ─── 5. Create launcher script ──────────────────

cat > "$BUILD_DIR/${APP_NAME}.app/Contents/MacOS/AGOS" << 'LAUNCHER'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
RESOURCES="$(cd "$DIR/../Resources" && pwd)"
export AGOS_WEB_DIR="$RESOURCES/web"
export PYTHONPATH="$RESOURCES:$PYTHONPATH"

# Start daemon
"$DIR/agosd" --web "$RESOURCES/web" --port 8765 &
DAEMON_PID=$!

# Wait for daemon
sleep 1

# Open browser
open "http://localhost:8765"

# Keep alive
wait $DAEMON_PID
LAUNCHER
chmod +x "$BUILD_DIR/${APP_NAME}.app/Contents/MacOS/AGOS"
echo "   ✅ Launcher created"

# ─── 6. Create Info.plist ───────────────────────

cat > "$BUILD_DIR/${APP_NAME}.app/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>AGOS</string>
    <key>CFBundleDisplayName</key>
    <string>AGOS - Agentic Operating System</string>
    <key>CFBundleIdentifier</key>
    <string>dev.agos.desktop</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleExecutable</key>
    <string>AGOS</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST
echo "   ✅ Info.plist created"

# ─── 7. Create DMG ──────────────────────────────

echo "📦 Creating DMG..."
mkdir -p "$DMG_DIR"
cp -r "$BUILD_DIR/${APP_NAME}.app" "$DMG_DIR/"

# Create Applications symlink for drag-to-install
ln -s /Applications "$DMG_DIR/Applications"

# Build DMG
hdiutil create -volname "$APP_NAME" \
    -srcfolder "$DMG_DIR" \
    -ov -format UDZO \
    "$OUTPUT" \
    -quiet

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ DMG created: ~/Desktop/AGOS-${VERSION}.dmg  ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Install: Double-click DMG → Drag AGOS to Applications"
echo "Launch:  Open AGOS from Launchpad or /Applications"

# Cleanup
rm -rf "$BUILD_DIR" "$DMG_DIR"
