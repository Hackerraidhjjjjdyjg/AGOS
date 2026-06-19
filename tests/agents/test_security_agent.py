"""Unit tests for SecurityAgent tools and parsing."""

import asyncio
import hashlib
import json
import socket

from agents.security_agent import SecurityAgent


def agent():
    return SecurityAgent()


def test_quick_think_scan_ports():
    plan = agent().quick_think("scan ports on 127.0.0.1")
    assert plan["steps"][0]["tool"] == "scan_ports"
    assert plan["steps"][0]["args"]["host"] == "127.0.0.1"


def test_quick_think_hash():
    plan = agent().quick_think("hash /tmp/file.txt")
    assert plan == {"steps": [{"tool": "hash_file", "args": {"path": "/tmp/file.txt"}}]}


def test_quick_think_permissions():
    plan = agent().quick_think("permissions /etc/hosts")
    assert plan == {"steps": [{"tool": "check_permissions", "args": {"path": "/etc/hosts"}}]}


def test_quick_think_audit():
    plan = agent().quick_think("audit trail")
    assert plan == {"steps": [{"tool": "audit_trail", "args": {"action": "list"}}]}


def test_quick_think_no_match():
    assert agent().quick_think("make me a sandwich") is None


def test_hash_file(tmp_path):
    f = tmp_path / "x.bin"
    content = b"agos rocks"
    f.write_bytes(content)
    out = agent()._hash_file(str(f))
    assert hashlib.sha256(content).hexdigest() in out
    assert hashlib.md5(content).hexdigest() in out


def test_hash_file_missing():
    assert agent()._hash_file("/no/such/file").startswith("File not found")


def test_check_permissions(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("data")
    out = agent()._check_permissions(str(f))
    assert "Permissions:" in out
    assert "Size:" in out


def test_check_permissions_missing():
    assert agent()._check_permissions("/no/such/path").startswith("Path not found")


def test_audit_trail_empty():
    assert agent()._audit_trail("list") == "No audit events recorded"


def test_audit_trail_lists_events():
    a = agent()
    a.audit_log.append({"tool": "hash_file", "status": "ok"})
    out = a._audit_trail("list")
    assert "Audit Trail" in out
    assert "hash_file → ok" in out


def test_validate_manifest_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert "not found" in agent()._validate_manifest()


def test_validate_manifest_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg_dir = tmp_path / "AGENTIC_AGOS" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "manifest.json").write_text(json.dumps({
        "agents": [{"name": "a"}],
        "permissions": {"fs": "read"},
    }))
    out = agent()._validate_manifest()
    assert "Manifest Validation" in out
    assert "1 agents defined" in out
    assert "Permissions block present" in out


def test_scan_ports_detects_open_and_closed():
    # Bind a listening socket to get a guaranteed-open port.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    open_port = srv.getsockname()[1]
    try:
        out = agent()._scan_ports(host="127.0.0.1", ports=str(open_port))
        assert "OPEN" in out
    finally:
        srv.close()

    # After closing, the same port should report closed.
    out = agent()._scan_ports(host="127.0.0.1", ports=str(open_port))
    assert "closed" in out


def test_act_runs_hash_file(tmp_path):
    f = tmp_path / "h.txt"
    f.write_text("hello")
    result = asyncio.run(agent().act(
        {"steps": [{"tool": "hash_file", "args": {"path": str(f)}}]}
    ))
    assert result.success is True
    assert hashlib.sha256(b"hello").hexdigest() in result.output
