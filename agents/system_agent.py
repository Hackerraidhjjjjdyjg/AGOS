"""
AGOS — System Agent
Controls macOS system functions (apps, volume, music, screenshots) via AppleScript.
"""

import asyncio
import json
import logging
import subprocess
from typing import Optional

from .base import AgentConfig, BaseAgent, TaskResult

logger = logging.getLogger("agos.system_agent")


class SystemAgent(BaseAgent):
    """
    macOS system control agent.
    Executes AppleScript commands for OS-level actions.
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(
                name="System Agent",
                model="llama-3.1-8b-instant",
                priority=2,
                token_budget=4096,
                capabilities=[
                    "open_app", "get_active_apps", "set_volume", "say",
                    "search_web", "play_music", "screenshot", "get_system_info",
                    "send_notification", "get_clipboard", "set_clipboard",
                ],
            )
        super().__init__(config)

    async def sense(self, task: str) -> str:
        """Get current system state."""
        info = {
            "active_apps": await self._run_osascript(
                'tell application "System Events" to get name of every process whose background only is false'
            ),
            "volume": await self._run_osascript("output volume of (get volume settings)"),
        }
        return json.dumps(info)

    def quick_think(self, task: str) -> Optional[dict]:
        """Parse common commands directly without LLM."""
        t = task.lower().strip()

        # "open safari" / "open spotify" / "launch finder"
        if t.startswith(("open ", "launch ", "start ")):
            app = task.split(" ", 1)[1].strip()
            # BRUTAL FIX: check for common websites mis-identified as apps
            web_apps = {
                "youtube": "https://youtube.com",
                "google": "https://google.com",
                "gmail": "https://mail.google.com",
                "github": "https://github.com",
                "x": "https://x.com",
                "twitter": "https://twitter.com",
                "facebook": "https://facebook.com",
                "netflix": "https://netflix.com"
            }
            if app.lower() in web_apps:
                return {"steps": [{"tool": "search_web", "args": {"query": web_apps[app.lower()]}}]}
            
            return {"steps": [{"tool": "open_app", "args": {"app_name": app}}]}

        # "volume 50" / "set volume to 80"
        import re
        vol_match = re.search(r'volume\s*(?:to\s*)?(\d+)', t)
        if vol_match:
            return {"steps": [{"tool": "set_volume", "args": {"level": int(vol_match.group(1))}}]}

        # "say hello" / "speak this text"
        if t.startswith(("say ", "speak ")):
            text = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "say", "args": {"text": text}}]}

        # "search for python tutorials" / "google machine learning"
        if t.startswith(("search ", "google ")):
            query = task.split(" ", 1)[1].strip()
            if query.startswith("for "): query = query[4:]
            return {"steps": [{"tool": "search_web", "args": {"query": query}}]}

        # "screenshot" / "take a screenshot"
        if "screenshot" in t:
            return {"steps": [{"tool": "screenshot", "args": {"output_path": "/tmp/agos_screenshot.png"}}]}

        # "what apps" / "running apps" / "list apps"
        if any(kw in t for kw in ["what app", "running app", "list app", "active app"]):
            return {"steps": [{"tool": "get_active_apps", "args": {}}]}

        # "system info" / "my mac info"
        if any(kw in t for kw in ["system info", "mac info", "my mac", "cpu", "memory"]):
            return {"steps": [{"tool": "get_system_info", "args": {}}]}

        # "clipboard" / "paste"
        if any(kw in t for kw in ["clipboard", "paste", "copied"]):
            return {"steps": [{"tool": "get_clipboard", "args": {}}]}

        # "notify" / "notification"
        if t.startswith("notify "):
            msg = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "send_notification", "args": {"title": "AGOS", "message": msg}}]}

        # "open spotify and set volume to 50" — compound command
        if " and " in t:
            parts = task.split(" and ")
            steps = []
            for part in parts:
                parsed = self.quick_think(part.strip())
                if parsed:
                    steps.extend(parsed["steps"])
            if steps:
                return {"steps": steps}

        return None  # Fall back to LLM

    async def act(self, plan: dict) -> TaskResult:
        """Execute the planned tool calls."""
        steps = plan.get("steps", [])
        outputs = []
        tool_calls = []

        for step in steps:
            tool = step.get("tool", "")
            args = step.get("args", {})

            try:
                # Use await because tool methods might now be async
                method = getattr(self, f"_tool_{tool}", None)
                if method is None:
                    raise NotImplementedError(f"Tool '{tool}' not implemented")
                
                import inspect
                if inspect.iscoroutinefunction(method):
                    result = await method(**args)
                else:
                    result = method(**args)
                
                outputs.append(f"✅ {tool}: {result}")
                tool_calls.append({"tool": tool, "args": args, "result": result})
            except Exception as e:
                outputs.append(f"❌ {tool}: {e}")
                tool_calls.append({"tool": tool, "args": args, "error": str(e)})

        return TaskResult(
            success=all("✅" in o for o in outputs),
            output="\n".join(outputs),
            tool_calls=tool_calls,
            tokens_used=self.tokens_used,
        )

    def _execute_tool(self, tool: str, args: dict) -> str:
        """Execute a single tool call."""
        if tool not in self.config.capabilities:
            raise PermissionError(f"Tool '{tool}' not in capabilities")

        method = getattr(self, f"_tool_{tool}", None)
        if method is None:
            raise NotImplementedError(f"Tool '{tool}' not implemented")
        return method(**args)

    # --- Tool Implementations ---

    async def _tool_open_app(self, app_name: str) -> str:
        # PRINCIPAL ENGINEERING: Stability delay to handle OS context-switching (Section 1)
        script = f'''
        tell application "{app_name}" to activate
        delay 0.5
        tell application "System Events" to return exists (process "{app_name}")
        '''
        res = await self._run_osascript(script)
        if res == "true":
            return f"Opened {app_name} (Verified)"
        return f"Signaled {app_name} to open"

    def _tool_get_active_apps(self) -> str:
        return self._run_osascript(
            'tell application "System Events" to get name of every process whose background only is false'
        )

    def _tool_set_volume(self, level: int) -> str:
        return self._run_osascript(f"set volume output volume {level}")
    async def _tool_set_volume(self, level: int) -> str:
        return await self._run_osascript(f"set volume output volume {level}")

    async def _tool_say(self, text: str) -> str:
        return await self._run_osascript(f'say "{text}"')

    async def _tool_search_web(self, query: str) -> str:
        import urllib.parse
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        return await self._run_osascript(f'tell application "Safari" to open location "{url}"')

    async def _tool_screenshot(self, output_path: str = "/tmp/agos_screenshot.png") -> str:
        # screencapture is a shell command
        process = await asyncio.create_subprocess_exec("screencapture", "-x", output_path)
        await process.wait()
        return f"Screenshot saved to {output_path}"

    async def _tool_get_system_info(self) -> str:
        import platform, psutil
        info = {
            "hostname": platform.node(),
            "os_version": platform.mac_ver()[0],
            "cpu": platform.processor(),
            "memory_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        }
        return json.dumps(info)

    async def _tool_send_notification(self, title: str, message: str) -> str:
        return await self._run_osascript(
            f'display notification "{message}" with title "{title}"'
        )

    async def _tool_get_clipboard(self) -> str:
        process = await asyncio.create_subprocess_exec("pbpaste", stdout=asyncio.subprocess.PIPE)
        stdout, _ = await process.communicate()
        return stdout.decode().strip()

    async def _tool_set_clipboard(self, text: str) -> str:
        process = await asyncio.create_subprocess_exec("pbcopy", stdin=asyncio.subprocess.PIPE)
        await process.communicate(text.encode())
        return "Clipboard set"

    async def _tool_play_music(self) -> str:
        return await self._run_osascript('tell application "Music" to play')

    # --- Internal ---

    async def _run_osascript(self, script: str) -> str:
        """Execute an AppleScript command asynchronously."""
        try:
            process = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                err_msg = stderr.decode().strip()
                self.logger.error(f"AppleScript error: {err_msg}")
                return err_msg
            return stdout.decode().strip()
        except Exception as e:
            self.logger.error(f"Failed to run AppleScript: {e}")
            return str(e)
