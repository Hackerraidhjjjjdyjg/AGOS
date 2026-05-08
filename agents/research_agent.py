from typing import Optional
# AGOS — Research Agent
"""
Research Agent — Multi-source information synthesis.
Tools: web_search, fetch_url, summarize, extract_facts, cite_sources
"""

import asyncio
import json
import subprocess
import urllib.request
import urllib.parse
from agents.base import BaseAgent, AgentConfig, TaskResult


class ResearchAgent(BaseAgent):
    """Searches the web, fetches pages, summarizes, extracts facts with citations."""

    def __init__(self, config=None):
        if config is None:
            config = AgentConfig(
                name="Research Agent",
                model="llama-3.1-8b-instant",
                priority=2,
                token_budget=4096,
                capabilities=[
                    "web_search", "fetch_url", "summarize",
                    "extract_facts", "cite_sources",
                ],
            )
        super().__init__(config)
        self.tools = {
            "web_search": self._web_search,
            "fetch_url": self._fetch_url,
            "summarize": self._summarize,
            "extract_facts": self._extract_facts,
            "cite_sources": self._cite_sources,
        }

    async def sense(self, task: str) -> str:
        return f"Research task: {task}"

    def quick_think(self, task: str) -> Optional[dict]:
        t = task.lower().strip()
        # Handle conversational filler
        import re
        clean_task = re.sub(r'^(can you|please|i need to|help me|find|search for|research about|look up information on)\s+', '', t)
        
        if any(t.startswith(kw) or clean_task.startswith(kw) for kw in ["search ", "research ", "look up ", "find info "]):
            query = re.sub(r'^(search for|research about|look up|find info on)\s+', '', clean_task)
            # Strip instruction phrases from the query
            query = re.sub(
                r',?\s*(write|create|make|generate|draft|compose|summarize|and\s+write|and\s+summarize|and\s+create).*$',
                '', query, flags=re.IGNORECASE
            ).strip().rstrip(",.")
            return {"steps": [{"tool": "web_search", "args": {"query": query}}, {"tool": "summarize", "args": {"text": ""}}]}
        
        if t.startswith(("summarize ", "summary of ")):
            text = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "summarize", "args": {"text": text}}]}
            
        if t.startswith(("fetch ", "open url ")):
            url = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "fetch_url", "args": {"url": url}}]}
        return None

    async def act(self, plan: dict) -> TaskResult:
        results = []
        tool_calls = []

        for step in plan.get("steps", []):
            tool_name = step.get("tool")
            args = step.get("args", {})

            if tool_name in self.tools:
                try:
                    # Pass previous results to summarize
                    if tool_name == "summarize" and not args.get("text") and results:
                        args["text"] = "\n".join(str(r) for r in results)

                    result = await asyncio.to_thread(self.tools[tool_name], **args)
                    results.append(result)
                    tool_calls.append({"tool": tool_name, "result": str(result)[:500]})
                except Exception as e:
                    tool_calls.append({"tool": tool_name, "error": str(e)})

        # Build output: prefer the last successful result (usually the summary)
        best_output = ""
        for r in reversed(results):
            if r and len(str(r)) > 20 and "error" not in str(r).lower():
                best_output = str(r)
                break
        if not best_output and results:
            best_output = str(results[-1])

        return TaskResult(
            success=len(tool_calls) > 0,
            output=best_output or "No results found",
            tool_calls=tool_calls,
            tokens_used=self._tokens_used,
        )

    # ─── Tools ───────────────────────────────────

    def _web_search(self, query: str) -> str:
        """Search via DuckDuckGo Instant Answer API."""
        try:
            encoded = urllib.parse.urlencode({"q": query, "format": "json", "no_html": 1})
            url = f"https://api.duckduckgo.com/?{encoded}"
            req = urllib.request.Request(url, headers={"User-Agent": "AGOS/1.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())

            results = []
            if data.get("AbstractText"):
                results.append(f"Summary: {data['AbstractText']}")
            if data.get("AbstractSource"):
                results.append(f"Source: {data['AbstractSource']}")
            for topic in data.get("RelatedTopics", [])[:5]:
                if isinstance(topic, dict) and "Text" in topic:
                    results.append(f"- {topic['Text'][:200]}")

            if not results:
                return f"No instant answer found for '{query}'. Please use 'fetch_url' with a specific URL or try a broader query."
            
            return "\n".join(results)
        except Exception as e:
            return f"Search error: {e}"

    def _fetch_url(self, url: str) -> str:
        """Fetch a URL and extract text content."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AGOS/1.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            html = resp.read().decode("utf-8", errors="ignore")

            # Basic HTML to text
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:3000]
        except Exception as e:
            return f"Fetch error: {e}"

    def _summarize(self, text: str, **kwargs) -> str:
        """Summarize text (returns first 500 chars if no LLM)."""
        if len(text) <= 500:
            return text
        # Extractive summary: first paragraph + key sentences
        sentences = text.split(". ")
        summary = ". ".join(sentences[:5]) + "."
        return summary[:500]

    def _extract_facts(self, text: str) -> str:
        """Extract key facts from text."""
        sentences = text.split(". ")
        facts = [s.strip() for s in sentences if len(s) > 20][:10]
        return "\n".join(f"• {f}" for f in facts)

    def _cite_sources(self, query: str, sources: str = "") -> str:
        """Format citations."""
        return f"[1] DuckDuckGo search: {query}\n{sources}"
