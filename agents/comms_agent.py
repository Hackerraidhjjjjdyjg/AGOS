from typing import Optional
# AGOS — Communication Agent
"""
Communication Agent — Email drafting, message formatting, scheduling.
Tools: draft_email, summarize_thread, schedule_event, format_message
"""

import asyncio
import json
import subprocess
from agents.base import BaseAgent, AgentConfig, TaskResult


class CommsAgent(BaseAgent):
    """Drafts emails, formats messages, creates calendar events via macOS."""

    def __init__(self, config=None):
        if config is None:
            config = AgentConfig(
                name="Communication Agent",
                model="llama-3.1-8b-instant",
                priority=3,
                token_budget=4096,
                capabilities=[
                    "draft_email", "summarize_thread",
                    "schedule_event", "format_message",
                ],
            )
        super().__init__(config)

    async def sense(self, task: str) -> str:
        return f"Communication task: {task}"

    def quick_think(self, task: str) -> Optional[dict]:
        t = task.lower().strip()
        if any(kw in t for kw in ["email", "mail", "send to"]):
            return {"steps": [{"tool": "draft_email", "args": {"request": task}}]}
        if any(kw in t for kw in ["schedule", "meeting", "calendar", "event"]):
            return {"steps": [{"tool": "schedule_event", "args": {"request": task}}]}
        if any(kw in t for kw in ["summarize thread", "summarize conversation"]):
            text = task.split(" ", 2)[-1] if len(task.split()) > 2 else task
            return {"steps": [{"tool": "summarize_thread", "args": {"thread": text}}]}
        if any(kw in t for kw in ["format", "reformat", "clean up"]):
            return {"steps": [{"tool": "format_message", "args": {"text": task}}]}
        return None

    async def act(self, plan: dict) -> TaskResult:
        results, tool_calls = [], []
        for step in plan.get("steps", []):
            tool_name = step.get("tool")
            args = step.get("args", {})
            handler = getattr(self, f"_tool_{tool_name}", None)
            if handler:
                try:
                    result = await handler(**args)
                    results.append(result)
                    tool_calls.append({"tool": tool_name, "result": str(result)[:500]})
                except Exception as e:
                    tool_calls.append({"tool": tool_name, "error": str(e)})

        output = f"[Communication Agent] " + " | ".join(
            f"{'✅' if 'result' in tc else '❌'} {tc['tool']}"
            for tc in tool_calls
        )
        if results:
            output += f"\n\n{results[-1]}"
        return TaskResult(success=len(tool_calls) > 0, output=output, tool_calls=tool_calls, tokens_used=self._tokens_used)

    async def _tool_draft_email(self, request: str, to: str = "", subject: str = "") -> str:
        """Draft a professional email using LLM."""
        email = await self.call_llm(
            f"Draft this email: {request}\nTo: {to}\nSubject: {subject}",
            system=(
                "You are an executive assistant. Draft a professional, concise email. "
                "Format: Subject: ...\n\nDear ...,\n\n[body]\n\nBest regards,\nSehaj Vir Singh"
            ),
        )
        return email or "Failed to draft email"

    async def _tool_summarize_thread(self, thread: str) -> str:
        """Summarize an email/message thread."""
        return await self.call_llm(
            f"Summarize this thread concisely:\n\n{thread}",
            system="Summarize in 3-5 bullet points: key decisions, action items, deadlines.",
        )

    async def _tool_schedule_event(self, request: str) -> str:
        """Create a calendar event via macOS Calendar."""
        event_info = await self.call_llm(
            f"Extract event details from: {request}",
            system='Return JSON: {{"title":"...","date":"YYYY-MM-DD","time":"HH:MM","duration_min":60}}',
        )
        try:
            info = json.loads(event_info)
            # Create via AppleScript
            script = f'''
            tell application "Calendar"
                tell calendar "Home"
                    make new event with properties {{summary:"{info.get('title', 'Meeting')}", start date:date "{info.get('date', 'tomorrow')}"}}
                end tell
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5,
            )
            return f"📅 Event created: {info.get('title')} on {info.get('date')}"
        except Exception as e:
            return f"Event info extracted: {event_info}\n(Calendar integration: {e})"

    async def _tool_format_message(self, text: str, format: str = "professional") -> str:
        """Format a message professionally."""
        return await self.call_llm(
            f"Format this message in a {format} style:\n\n{text}",
            system="Rewrite the message to be clear, professional, and well-structured.",
        )
