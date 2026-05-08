#!/usr/bin/env python3
"""
AGOS — End-to-End Integration Tests
Tests the complete flow: API → Agent → Tool execution → Result
"""

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8765"
PASS = 0
FAIL = 0


def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  ✅ {name}")
        PASS += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        FAIL += 1


def http_get(path):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    resp = urllib.request.urlopen(req, timeout=5)
    return json.loads(resp.read())


def http_post(path, data, token=None):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    resp = urllib.request.urlopen(req, timeout=5)
    return json.loads(resp.read())


# ─── Tests ────────────────────────────────────────────────────────────

def test_health():
    resp = http_get("/health")
    assert resp["status"] == "healthy", f"Expected healthy, got {resp['status']}"
    assert "version" in resp


def test_metrics():
    req = urllib.request.Request(f"{BASE_URL}/metrics")
    resp = urllib.request.urlopen(req, timeout=5)
    body = resp.read().decode()
    assert "agos_up 1" in body, "Missing agos_up metric"


def test_login():
    resp = http_post("/api/v1/auth/login", {"email": "admin@agos.dev", "password": "admin"})
    assert "access_token" in resp, "Missing access_token"
    return resp["access_token"]


def test_agents_unauthorized():
    try:
        http_get("/api/v1/agents")
        assert False, "Should have returned 401"
    except urllib.error.HTTPError as e:
        assert e.code == 401


def test_list_agents(token):
    req = urllib.request.Request(f"{BASE_URL}/api/v1/agents")
    req.add_header("Authorization", f"Bearer {token}")
    resp = urllib.request.urlopen(req, timeout=5)
    data = json.loads(resp.read())
    assert "agents" in data
    assert len(data["agents"]) > 0


def test_submit_task(token):
    resp = http_post("/api/v1/tasks", {"intent": "open Safari", "priority": 1}, token)
    assert "task_id" in resp
    assert resp["status"] == "queued"


def test_create_api_key(token):
    resp = http_post("/api/v1/keys", {}, token)
    assert resp["key"].startswith("agos_sk_")


def test_postgres_tables():
    result = subprocess.run(
        ["psql", "-d", "agos_db", "-t", "-c",
         "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'"],
        capture_output=True, text=True
    )
    count = int(result.stdout.strip())
    assert count >= 12, f"Expected 12+ tables, got {count}"


def test_docker_services():
    result = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True)
    running = result.stdout.strip().split("\n")
    for svc in ["agos-redis", "agos-nats", "agos-prometheus", "agos-grafana"]:
        assert svc in running, f"{svc} not running"


def test_rust_kernel():
    result = subprocess.run(
        ["cargo", "test", "--manifest-path", "rust-kernel/Cargo.toml"],
        capture_output=True, text=True, cwd="/Users/sehajvirsingh/AGENTIC_AGOS"
    )
    assert result.returncode == 0, f"Rust tests failed:\n{result.stderr[-200:]}"


def test_agent_direct_mode():
    """Test that the agent can parse commands without LLM."""
    sys.path.insert(0, "/Users/sehajvirsingh/AGENTIC_AGOS")
    from agents.system_agent import SystemAgent
    agent = SystemAgent()
    result = agent._parse_direct("open Safari")
    assert result is not None
    assert result["steps"][0]["tool"] == "open_app"
    assert result["steps"][0]["args"]["app_name"] == "Safari"


def test_agent_compound_command():
    sys.path.insert(0, "/Users/sehajvirsingh/AGENTIC_AGOS")
    from agents.system_agent import SystemAgent
    agent = SystemAgent()
    result = agent._parse_direct("open Spotify and set volume to 50")
    assert result is not None
    assert len(result["steps"]) == 2


# ─── Runner ───────────────────────────────────────────────────────────

def main():
    print("\n🧪 AGOS End-to-End Tests")
    print("=" * 50)

    print("\n📦 Infrastructure:")
    test("PostgreSQL has 12+ tables", test_postgres_tables)
    test("Docker services running", test_docker_services)
    test("Rust kernel tests pass", test_rust_kernel)

    print("\n🤖 Agent Direct Mode:")
    test("Parse 'open Safari'", test_agent_direct_mode)
    test("Parse compound command", test_agent_compound_command)

    print("\n🌐 API Server (run `go run ./cmd/agosd` first):")
    try:
        test("GET /health", test_health)
        test("GET /metrics", test_metrics)
        test("POST /api/v1/auth/login", test_login)
        token = test_login()
        test("GET /agents unauthorized → 401", test_agents_unauthorized)
        test("GET /agents with token", lambda: test_list_agents(token))
        test("POST /tasks", lambda: test_submit_task(token))
        test("POST /keys", lambda: test_create_api_key(token))
    except Exception:
        print("  ⚠️  API server not running, skipping HTTP tests")

    print("\n" + "=" * 50)
    print(f"Results: {PASS} passed, {FAIL} failed")
    print("=" * 50)
    sys.exit(1 if FAIL > 0 else 0)


if __name__ == "__main__":
    main()
