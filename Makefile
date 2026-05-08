# AGOS — Makefile
# Enterprise build system for the Agentic OS

.PHONY: all build test clean install run package

VERSION := 0.1.0
ROOT := $(shell pwd)

# ─── Main Targets ──────────────────────────────────────────────────

all: build test

build: build-rust build-go

test: test-rust test-go test-python

clean:
	cd rust-kernel && cargo clean
	cd go-orchestrator && rm -f agosd
	rm -rf build/

install:
	bash scripts/install-deps.sh

run:
	bash scripts/start-dev.sh

package:
	bash scripts/package-dmg.sh

# ─── Rust ──────────────────────────────────────────────────────────

build-rust:
	@echo "═══ Building Rust Kernel ═══"
	cd rust-kernel && cargo build --release

test-rust:
	@echo "═══ Testing Rust Kernel ═══"
	cd rust-kernel && cargo test

bench-rust:
	cd rust-kernel && cargo bench

# ─── Go ────────────────────────────────────────────────────────────

build-go:
	@echo "═══ Building Go Orchestrator ═══"
	cd go-orchestrator && go build -o $(ROOT)/build/agosd ./cmd/agosd/

test-go:
	@echo "═══ Testing Go Orchestrator ═══"
	cd go-orchestrator && go test ./...

# ─── Python ────────────────────────────────────────────────────────

test-python:
	@echo "═══ Testing Python Agents ═══"
	python3 -m pytest tests/ -v

lint-python:
	python3 -m py_compile agents/base.py agents/orchestrator.py agents/system_agent.py

# ─── Helpers ───────────────────────────────────────────────────────

version:
	@echo "AGOS v$(VERSION)"

tree:
	@find . -type f -not -path './*/target/*' -not -path './*/.git/*' -not -path '*/node_modules/*' | head -60
