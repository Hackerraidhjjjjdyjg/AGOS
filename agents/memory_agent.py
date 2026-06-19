# AGOS — Memory Agent
"""
Memory Agent — Long-term knowledge storage and semantic retrieval.
Tools: store_memory, recall, semantic_search, forget, list_memories
"""

import asyncio
import json
import os
import time
from typing import Optional
from agents.base import BaseAgent, AgentConfig, TaskResult
from agents.tool_executor import execute_tool_plan, format_tool_output


MEMORY_DIR = os.path.expanduser("~/AGENTIC_AGOS/.memory")


class MemoryAgent(BaseAgent):
    """Stores, retrieves, and searches through persistent memories."""

    def __init__(self, config=None):
        if config is None:
            config = AgentConfig(
                name="Memory Agent",
                model="llama-3.1-8b-instant",
                priority=2,
                token_budget=4096,
                capabilities=[
                    "store_memory", "recall", "semantic_search",
                    "forget", "list_memories",
                ],
            )
        super().__init__(config)
        self.tools = {
            "store_memory": self._store_memory,
            "recall": self._recall,
            "semantic_search": self._semantic_search,
            "forget": self._forget,
            "list_memories": self._list_memories,
        }
        os.makedirs(MEMORY_DIR, exist_ok=True)
        self._load_index()

    def _load_index(self):
        """Load memory index from disk."""
        idx_path = os.path.join(MEMORY_DIR, "index.json")
        if os.path.exists(idx_path):
            with open(idx_path) as f:
                self.index = json.load(f)
        else:
            self.index = {"memories": [], "total": 0}

    def _save_index(self):
        """Persist memory index."""
        with open(os.path.join(MEMORY_DIR, "index.json"), "w") as f:
            json.dump(self.index, f, indent=2)

    async def sense(self, task: str) -> str:
        return f"Memory task: {task} | Total memories: {self.index['total']}"

    def quick_think(self, task: str) -> Optional[dict]:
        t = task.lower().strip()
        if any(t.startswith(kw) for kw in ["remember ", "store ", "save "]):
            content = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "store_memory", "args": {"content": content}}]}
        if any(t.startswith(kw) for kw in ["recall ", "what do you know about ", "remember about "]):
            query = task.split(" ", 1)[1].strip()
            if query.startswith("about "):
                query = query[6:]
            return {"steps": [{"tool": "recall", "args": {"query": query}}]}
        if any(t.startswith(kw) for kw in ["search ", "find memory ", "look up "]):
            query = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "semantic_search", "args": {"query": query}}]}
        if any(t.startswith(kw) for kw in ["forget ", "delete memory ", "remove "]):
            query = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "forget", "args": {"query": query}}]}
        if any(kw in t for kw in ["list memories", "all memories", "show memories"]):
            return {"steps": [{"tool": "list_memories", "args": {}}]}
        return None

    async def act(self, plan: dict) -> TaskResult:
        results, tool_calls = await execute_tool_plan(plan, tools=self.tools)
        output = format_tool_output("Memory Agent", tool_calls)
        return TaskResult(success=len(tool_calls) > 0, output=output, tool_calls=tool_calls, tokens_used=self._tokens_used)

    # ─── Tools ───────────────────────────────────

    def _store_memory(self, content: str, tags: str = "", importance: int = 5) -> str:
        """Store a memory to persistent disk storage."""
        memory = {
            "id": self.index["total"] + 1,
            "content": content,
            "tags": [t.strip() for t in tags.split(",") if t.strip()] if tags else [],
            "importance": importance,
            "created_at": time.time(),
            "accessed_count": 0,
        }
        self.index["memories"].append(memory)
        self.index["total"] += 1
        self._save_index()

        # Also save as individual file
        mem_file = os.path.join(MEMORY_DIR, f"mem_{memory['id']}.json")
        with open(mem_file, "w") as f:
            json.dump(memory, f, indent=2)

        return f"Stored memory #{memory['id']}: {content[:100]}..."

    def _recall(self, query: str) -> str:
        """Recall memories matching a query (keyword search)."""
        query_lower = query.lower()
        matches = []
        for mem in self.index["memories"]:
            content = mem["content"].lower()
            score = 0
            for word in query_lower.split():
                if word in content:
                    score += 1
            if score > 0:
                matches.append((score, mem))

        matches.sort(key=lambda x: (-x[0], -x[1].get("importance", 0)))

        if not matches:
            return f"No memories found for: {query}"

        results = [f"Found {len(matches)} memories:"]
        for score, mem in matches[:5]:
            results.append(f"  #{mem['id']} (relevance: {score}) — {mem['content'][:150]}")
        return "\n".join(results)

    def _semantic_search(self, query: str) -> str:
        """Search memories with fuzzy matching."""
        # Enhanced keyword search with partial matching
        query_words = set(query.lower().split())
        matches = []

        for mem in self.index["memories"]:
            content_words = set(mem["content"].lower().split())
            overlap = query_words & content_words
            if overlap:
                score = len(overlap) / len(query_words) * 100
                matches.append((score, mem))

        matches.sort(key=lambda x: -x[0])

        if not matches:
            return f"No semantic matches for: {query}"

        results = [f"Semantic search results ({len(matches)} matches):"]
        for score, mem in matches[:5]:
            results.append(f"  #{mem['id']} ({score:.0f}% match) — {mem['content'][:150]}")
        return "\n".join(results)

    def _forget(self, query: str) -> str:
        """Remove memories matching a query."""
        query_lower = query.lower()
        removed = []
        remaining = []
        for mem in self.index["memories"]:
            if query_lower in mem["content"].lower():
                removed.append(mem)
                # Delete file
                mem_file = os.path.join(MEMORY_DIR, f"mem_{mem['id']}.json")
                if os.path.exists(mem_file):
                    os.unlink(mem_file)
            else:
                remaining.append(mem)

        self.index["memories"] = remaining
        self._save_index()
        return f"Forgot {len(removed)} memories matching '{query}'"

    def _list_memories(self, limit: int = 20) -> str:
        """List all stored memories."""
        if not self.index["memories"]:
            return "No memories stored yet"

        lines = [f"Total: {len(self.index['memories'])} memories\n"]
        for mem in self.index["memories"][-limit:]:
            tags = ", ".join(mem.get("tags", []))
            tag_str = f" [{tags}]" if tags else ""
            lines.append(f"  #{mem['id']}{tag_str} — {mem['content'][:100]}")
        return "\n".join(lines)
