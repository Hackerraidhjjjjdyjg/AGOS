from typing import Optional
# AGOS — Security Agent
"""
Security Agent — Vulnerability scanning, file integrity, audit trail.
Tools: scan_ports, check_permissions, hash_file, audit_trail, validate_manifest
"""

import asyncio
import hashlib
import json
import os
import socket
import stat
import subprocess
from agents.base import BaseAgent, AgentConfig, TaskResult
from agents.tool_executor import execute_tool_plan, format_tool_output


class SecurityAgent(BaseAgent):
    """Scans ports, checks file permissions, hashes files, manages audit trail."""

    def __init__(self, config=None):
        if config is None:
            config = AgentConfig(
                name="Security Agent",
                model="llama-3.1-8b-instant",
                priority=1,  # Highest priority — security first
                token_budget=4096,
                capabilities=[
                    "scan_ports", "check_permissions", "hash_file",
                    "audit_trail", "validate_manifest", "check_ssl",
                ],
            )
        super().__init__(config)
        self.tools = {
            "scan_ports": self._scan_ports,
            "check_permissions": self._check_permissions,
            "hash_file": self._hash_file,
            "audit_trail": self._audit_trail,
            "validate_manifest": self._validate_manifest,
            "check_ssl": self._check_ssl,
        }
        self.audit_log = []

    async def sense(self, task: str) -> str:
        return f"Security task: {task}"

    def quick_think(self, task: str) -> Optional[dict]:
        t = task.lower().strip()
        if any(kw in t for kw in ["scan port", "port scan", "open ports"]):
            host = "localhost"
            for word in task.split():
                if "." in word or word == "localhost":
                    host = word
                    break
            return {"steps": [{"tool": "scan_ports", "args": {"host": host}}]}
        if t.startswith(("hash ", "checksum ")):
            path = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "hash_file", "args": {"path": path}}]}
        if t.startswith(("permissions ", "check perm")):
            path = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "check_permissions", "args": {"path": path}}]}
        if t.startswith(("audit", "show audit", "view trail")) or t == "audit trail":
            return {"steps": [{"tool": "audit_trail", "args": {"action": "list"}}]}
        if t.startswith(("validate ", "check manifest")):
            return {"steps": [{"tool": "validate_manifest", "args": {}}]}
        if t.startswith("ssl ") or "certificate" in t:
            host = task.split()[-1] if len(task.split()) > 1 else "localhost"
            return {"steps": [{"tool": "check_ssl", "args": {"host": host}}]}
        return None

    async def act(self, plan: dict) -> TaskResult:
        results, tool_calls = await execute_tool_plan(plan, tools=self.tools)
        for tc in tool_calls:
            if "result" in tc:
                self.audit_log.append({"tool": tc["tool"], "status": "ok"})
            else:
                self.audit_log.append({"tool": tc["tool"], "status": "error", "error": tc.get("error", "")})
        output = format_tool_output("Security Agent", tool_calls)
        return TaskResult(success=len(tool_calls) > 0, output=output, tool_calls=tool_calls, tokens_used=self._tokens_used)

    # ─── Tools ───────────────────────────────────

    def _scan_ports(self, host: str = "localhost", ports: str = "80,443,5432,6379,4222,8765,9090,3000") -> str:
        """Scan common ports on a host."""
        port_list = [int(p.strip()) for p in ports.split(",")]
        results = []
        for port in port_list:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                r = sock.connect_ex((host, port))
                status = "OPEN" if r == 0 else "CLOSED"
                sock.close()
                if r == 0:
                    results.append(f"  🟢 {port:>5} OPEN")
                else:
                    results.append(f"  ⚫ {port:>5} closed")
            except Exception:
                results.append(f"  🔴 {port:>5} error")

        return f"Port scan: {host}\n" + "\n".join(results)

    def _check_permissions(self, path: str) -> str:
        """Check file/directory permissions."""
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return f"Path not found: {path}"

        st = os.stat(path)
        mode = stat.filemode(st.st_mode)
        owner = st.st_uid
        group = st.st_gid
        size = st.st_size

        warnings = []
        if st.st_mode & stat.S_IWOTH:
            warnings.append("⚠️ WORLD-WRITABLE")
        if st.st_mode & stat.S_ISUID:
            warnings.append("⚠️ SETUID bit set")

        return (
            f"Path: {path}\n"
            f"Permissions: {mode}\n"
            f"Owner/Group: {owner}/{group}\n"
            f"Size: {size:,} bytes\n"
            + ("\n".join(warnings) if warnings else "✅ No security issues")
        )

    def _hash_file(self, path: str) -> str:
        """Compute SHA-256 hash of a file."""
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return f"File not found: {path}"

        sha = hashlib.sha256()
        md5 = hashlib.md5()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                sha.update(chunk)
                md5.update(chunk)

        return f"File: {path}\nSHA-256: {sha.hexdigest()}\nMD5: {md5.hexdigest()}"

    def _audit_trail(self, action: str = "list") -> str:
        """View or log audit events."""
        if action == "list":
            if not self.audit_log:
                return "No audit events recorded"
            lines = [f"{i+1}. {e['tool']} → {e['status']}" for i, e in enumerate(self.audit_log[-20:])]
            return "Audit Trail (last 20):\n" + "\n".join(lines)
        self.audit_log.append({"tool": "manual", "status": action})
        return f"Logged: {action}"

    def _validate_manifest(self) -> str:
        """Validate the AGOS agent manifest."""
        manifest_path = os.path.expanduser("~/AGENTIC_AGOS/config/manifest.json")
        if not os.path.exists(manifest_path):
            return "❌ manifest.json not found"
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            checks = []
            checks.append(f"✅ Valid JSON ({len(json.dumps(manifest))} bytes)")
            if "agents" in manifest:
                checks.append(f"✅ {len(manifest['agents'])} agents defined")
            if "permissions" in manifest:
                checks.append(f"✅ Permissions block present")
            return "Manifest Validation:\n" + "\n".join(checks)
        except json.JSONDecodeError as e:
            return f"❌ Invalid JSON: {e}"

    def _check_ssl(self, host: str) -> str:
        """Check SSL certificate for a host."""
        try:
            result = subprocess.run(
                ["openssl", "s_client", "-connect", f"{host}:443", "-servername", host],
                input=b"", capture_output=True, timeout=5,
            )
            output = result.stdout.decode("utf-8", errors="ignore")
            if "Verify return code: 0" in output:
                return f"✅ SSL valid for {host}"
            return f"⚠️ SSL issues for {host}"
        except Exception as e:
            return f"SSL check error: {e}"
