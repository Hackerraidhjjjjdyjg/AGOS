#!/bin/bash
# AGOS — Install Dependencies
# Run once on a fresh machine to set up the dev environment.
set -e

echo "╔══════════════════════════════════════════╗"
echo "║     AGOS Dependency Installer             ║"
echo "╚══════════════════════════════════════════╝"

# --- Check macOS ---
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: AGOS requires macOS. Detected: $(uname)"
    exit 1
fi

# --- Homebrew ---
if ! command -v brew &> /dev/null; then
    echo "[INSTALL] Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# --- System Dependencies ---
echo "[INSTALL] Installing system dependencies..."
brew install go protobuf nats-server ollama create-dmg python@3.11 || true

# --- Rust Toolchain ---
if ! command -v rustc &> /dev/null; then
    echo "[INSTALL] Installing Rust via rustup..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi
echo "[INSTALL] Rust: $(rustc --version)"

# --- Python Dependencies ---
echo "[INSTALL] Installing Python dependencies..."
pip3 install --upgrade pip
pip3 install -r "$(dirname "$0")/../requirements.txt"

# --- Ollama Model ---
echo "[INSTALL] Pulling Ollama model (llama3)..."
ollama pull llama3 || echo "[WARN] Ollama pull failed — is ollama running?"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     Dependencies installed successfully   ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Next: Run ./scripts/build.sh to build AGOS"
