from typing import Optional
# AGOS — Code Agent
"""
Code Agent — Code generation, debugging, explanation, and file operations.
Tools: generate_code, explain_code, debug_code, run_python, read_file, write_file, git_status
"""

import asyncio
import json
import os
import subprocess
import tempfile
from agents.base import BaseAgent, AgentConfig, TaskResult


class CodeAgent(BaseAgent):
    """Generates, debugs, explains, and refactors code. Runs Python safely."""

    def __init__(self, config=None):
        if config is None:
            config = AgentConfig(
                name="Code Agent",
                model="llama-3.1-8b-instant",
                priority=2,
                token_budget=4096,
                capabilities=[
                    "generate_code", "explain_code", "debug_code",
                    "run_python", "read_file", "write_file", "git_status",
                ],
            )
        super().__init__(config)
        self.tools = {
            "generate_code": self._generate_code,
            "explain_code": self._explain_code,
            "debug_code": self._debug_code,
            "run_python": self._run_python,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "git_status": self._git_status,
        }

    async def sense(self, task: str) -> str:
        return f"Code task: {task}"

    def quick_think(self, task: str) -> Optional[dict]:
        t = task.lower().strip()
        if any(t.startswith(kw) for kw in ["write code ", "generate ", "create a ", "code "]):
            desc = task.split(" ", 2)[-1] if len(task.split()) > 2 else task
            return {"steps": [{"tool": "generate_code", "args": {"language": "python", "description": desc}}]}
        if t.startswith(("explain ", "what does ")):
            code = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "explain_code", "args": {"code": code}}]}
        if t.startswith(("debug ", "fix ")):
            code = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "debug_code", "args": {"code": code}}]}
        if t.startswith(("run ", "execute ", "python ")):
            code = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "run_python", "args": {"code": code}}]}
        if t.startswith(("read ", "cat ", "show ")):
            path = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "read_file", "args": {"path": path}}]}
        if t.startswith("git"):
            return {"steps": [{"tool": "git_status", "args": {}}]}
        return None

    async def act(self, plan: dict) -> TaskResult:
        results = []
        tool_calls = []

        for step in plan.get("steps", []):
            tool_name = step.get("tool")
            args = step.get("args", {})

            if tool_name in self.tools:
                try:
                    if asyncio.iscoroutinefunction(self.tools[tool_name]):
                        result = await self.tools[tool_name](**args)
                    else:
                        result = await asyncio.to_thread(self.tools[tool_name], **args)
                    results.append(result)
                    tool_calls.append({"tool": tool_name, "result": str(result)[:500]})
                except Exception as e:
                    tool_calls.append({"tool": tool_name, "error": str(e)})

        output = f"[Code Agent] " + " | ".join(
            f"{'✅' if 'result' in tc else '❌'} {tc['tool']}: {tc.get('result', tc.get('error', ''))[:200]}"
            for tc in tool_calls
        )
        return TaskResult(
            success=len(tool_calls) > 0,
            output=output,
            tool_calls=tool_calls,
            tokens_used=self._tokens_used,
        )

    # ─── Tools ───────────────────────────────────

    async def _generate_code(self, language: str = "python", description: str = "", filename: str = "") -> str:
        """Generate code using LLM."""
        response = await self.call_llm(
            f"Write {language} code that: {description}\n\nReturn ONLY the code, no explanation.",
            system=f"You are a principal Google engineer. Write clean, production-quality {language} code. No markdown fences.",
        )
        if filename:
            with open(filename, "w") as f:
                f.write(response)
            return f"Generated {language} code → {filename}\n{response[:300]}"
        return response

    async def _explain_code(self, code: str) -> str:
        """Explain code using LLM."""
        return await self.call_llm(
            f"Explain this code clearly:\n\n{code}",
            system="You are a senior engineer. Explain code concisely — what it does, key patterns, complexity.",
        )

    async def _debug_code(self, code: str) -> str:
        """Debug code using LLM."""
        return await self.call_llm(
            f"Find bugs in this code and fix them:\n\n{code}",
            system="You are a debugging expert. Find ALL bugs, explain each, provide fixed code.",
        )

    def _run_python(self, code: str) -> str:
        """Run Python code safely in a subprocess."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                result = subprocess.run(
                    ["python3", f.name],
                    capture_output=True, text=True, timeout=10,
                )
                output = result.stdout or result.stderr
                return output[:1000] if output else "(no output)"
            except subprocess.TimeoutExpired:
                return "ERROR: execution timed out (10s limit)"
            finally:
                os.unlink(f.name)

    def _read_file(self, path: str) -> str:
        """Read a file from disk."""
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return f"File not found: {path}"
        with open(path) as f:
            content = f.read()
        return content[:3000]

    def _write_file(self, path: str, content: str) -> str:
        """Write content to a file."""
        path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {path}"

    def _git_status(self) -> str:
        """Get git status of the AGOS repo."""
        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True, text=True,
                cwd=os.path.expanduser("~/AGENTIC_AGOS"),
                timeout=5,
            )
            return result.stdout or "Clean working tree"
        except Exception as e:
            return f"Git error: {e}"
