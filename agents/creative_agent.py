from typing import Optional
# AGOS — Creative Agent
"""
Creative Agent — Content creation, rewriting, translation, formatting.
Tools: write_text, rewrite, translate, format_markdown, generate_outline
"""

from agents.base import BaseAgent, AgentConfig, TaskResult


class CreativeAgent(BaseAgent):
    """Creates, rewrites, translates, and formats content using LLM."""

    def __init__(self, config=None):
        if config is None:
            config = AgentConfig(
                name="Creative Agent",
                model="llama-3.1-8b-instant",
                priority=3,
                token_budget=4096,
                capabilities=[
                    "write_text", "rewrite", "translate",
                    "format_markdown", "generate_outline",
                ],
            )
        super().__init__(config)

    async def sense(self, task: str) -> str:
        return f"Creative task: {task}"

    def quick_think(self, task: str) -> Optional[dict]:
        t = task.lower().strip()
        if any(t.startswith(kw) for kw in ["write ", "compose ", "draft "]):
            topic = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "write_text", "args": {"topic": topic, "style": "professional"}}]}
        if t.startswith(("rewrite ", "improve ", "polish ")):
            text = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "rewrite", "args": {"text": text, "tone": "professional"}}]}
        if t.startswith(("translate ", "convert to ")):
            parts = task.split(" to ", 1)
            text = parts[0].split(" ", 1)[1].strip() if len(parts[0].split()) > 1 else ""
            lang = parts[1].strip() if len(parts) > 1 else "English"
            return {"steps": [{"tool": "translate", "args": {"text": text, "target_language": lang}}]}
        if t.startswith(("outline ", "plan for ")):
            topic = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "generate_outline", "args": {"topic": topic}}]}
        return None

    async def act(self, plan: dict) -> TaskResult:
        results = []
        tool_calls = []

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

        output = f"[Creative Agent] " + " | ".join(
            f"{'✅' if 'result' in tc else '❌'} {tc['tool']}"
            for tc in tool_calls
        )
        if results:
            output += f"\n\n{results[-1]}"

        return TaskResult(
            success=len(tool_calls) > 0,
            output=output,
            tool_calls=tool_calls,
            tokens_used=self._tokens_used,
        )

    # ─── Tools ───────────────────────────────────

    async def _tool_write_text(self, topic: str, style: str = "professional", length: str = "medium") -> str:
        return await self.call_llm(
            f"Write about: {topic}\nStyle: {style}\nLength: {length}",
            system="You are a world-class writer. Create compelling, polished content. Be specific and engaging.",
        )

    async def _tool_rewrite(self, text: str, tone: str = "professional") -> str:
        return await self.call_llm(
            f"Rewrite this in a {tone} tone:\n\n{text}",
            system="You are an expert editor. Rewrite for clarity, impact, and the requested tone.",
        )

    async def _tool_translate(self, text: str, target_language: str = "Spanish") -> str:
        return await self.call_llm(
            f"Translate to {target_language}:\n\n{text}",
            system=f"You are a professional translator. Translate accurately to {target_language}. Preserve meaning and nuance.",
        )

    async def _tool_format_markdown(self, text: str) -> str:
        return await self.call_llm(
            f"Format this as clean markdown:\n\n{text}",
            system="Format the text as clean, well-structured markdown with headers, lists, and emphasis.",
        )

    async def _tool_generate_outline(self, topic: str) -> str:
        return await self.call_llm(
            f"Create a detailed outline for: {topic}",
            system="Create a structured outline with numbered sections, sub-sections, and key points.",
        )
