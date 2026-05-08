# AGOS — Multi-Agent Orchestrator
"""
Orchestrator Agent — Routes tasks to 8 specialized agents.
Supports compound commands, parallel execution, and intent classification.
"""

import asyncio
import json
import logging
from agents.base import BaseAgent, AgentConfig, TaskResult
from agents.system_agent import SystemAgent
from agents.research_agent import ResearchAgent
from agents.code_agent import CodeAgent
from agents.creative_agent import CreativeAgent
from agents.data_agent import DataAgent
from agents.security_agent import SecurityAgent
from agents.comms_agent import CommsAgent
from agents.memory_agent import MemoryAgent

logger = logging.getLogger("agos.agent.Orchestrator")


# Intent classification rules (direct mode — no LLM needed)
INTENT_RULES = {
    "system": [
        "open ", "launch ", "start ", "quit ", "close ",
        "volume", "screenshot", "system info", "mac info",
        "say ", "clipboard", "paste", "notify ",
        "active app", "running app", "what app", "list app",
        "brightness", "play music", "play song",
    ],
    "research": [
        "search ", "research ", "look up ", "find info ",
        "what is ", "who is ", "explain ",
        "fetch ", "read url ", "summarize url",
    ],
    "code": [
        "write code ", "generate code", "debug ", "fix code",
        "python ", "run python", "execute code",
        "read file ", "write file ", "git ",
        "explain code", "refactor ",
    ],
    "creative": [
        "write ", "compose ", "draft article", "blog ",
        "rewrite ", "improve ", "polish ",
        "translate ", "outline ",
    ],
    "data": [
        "query ", "sql ", "select ", "analyze ",
        "csv ", "statistics ", "stats ",
        "chart ", "graph ", "pivot ",
    ],
    "security": [
        "scan port", "port scan", "open ports",
        "hash ", "checksum ", "permissions ",
        "audit", "security", "validate manifest",
        "ssl ", "certificate",
    ],
    "comms": [
        "email ", "mail ", "send to ",
        "schedule ", "meeting ", "calendar ",
        "summarize thread",
    ],
    "memory": [
        "remember ", "store ", "save memory",
        "recall ", "what do you know",
        "forget ", "delete memory",
        "list memories", "show memories",
        "search memory",
    ],
}


class Orchestrator:
    """
    Master orchestrator — classifies intent, routes to the right agent,
    handles compound commands, and aggregates results.
    """

    def __init__(self):
        self.sub_agents = {
            "system": SystemAgent(),
            "research": ResearchAgent(),
            "code": CodeAgent(),
            "creative": CreativeAgent(),
            "data": DataAgent(),
            "security": SecurityAgent(),
            "comms": CommsAgent(),
            "memory": MemoryAgent(),
        }
        for name, agent in self.sub_agents.items():
            logger.info(f"Registered agent: {name} → {agent.config.name}")

    async def execute(self, task: str, agent_uuid: str = "unknown") -> TaskResult:
        """Execute a task by routing to the appropriate agent(s)."""
        task = self._clean_input(task)
        logger.info(f"[Orchestrator] Executing: {task} | UUID: {agent_uuid}")

        # Decompose into sub-tasks
        sub_tasks = self._decompose(task)

        if len(sub_tasks) > 1:
            return await self._execute_pipeline(sub_tasks, agent_uuid=agent_uuid)

        # Single command — clean the query and route
        clean_task = sub_tasks[0]
        agent_key = self._classify_intent(clean_task)
        agent = self.sub_agents[agent_key]
        logger.info(f"[Orchestrator] Routed to: {agent.config.name}")

        result = await agent.execute(clean_task)
        logger.info(f"[Orchestrator] Completed: success={result.success}")
        return result

    def _decompose(self, task: str) -> list[str]:
        """
        Recursive natural language decomposition.
        Splits on multiple connectors to handle complex chains like:
        "A, then B, and C" -> ["A", "B", "C"]
        """
        import re

        # Define splitters in priority order
        splitters = [
            r',\s*and\s+then\s+', r'\s+and\s+then\s+', 
            r',\s*then\s+', r'\s+then\s+', 
            r',\s*and\s+finally\s+', r'\s+and\s+finally\s+',
            r',\s*and\s+', r',\s+'
        ]
        
        parts = [task]
        for pattern in splitters:
            new_parts = []
            for p in parts:
                split = re.split(pattern, p, flags=re.IGNORECASE)
                new_parts.extend([s.strip() for s in split if s.strip()])
            parts = new_parts

        # Final pass for standalone " and " only if it separates multi-agent tasks
        final_parts = []
        for p in parts:
            if " and " in p.lower():
                split = p.split(" and ")
                agents = set()
                for s in split:
                    agents.add(self._classify_intent(s.strip()))
                if len(agents) > 1:
                    final_parts.extend([s.strip() for s in split])
                else:
                    final_parts.append(p)
            else:
                final_parts.append(p)

        # Clean each part
        cleaned = []
        for p in final_parts:
            p = p.strip().rstrip(".,;")
            if len(p) > 2:  # Skip empty fragments
                cleaned.append(p)

        return cleaned if cleaned else [task]

    async def _execute_pipeline(self, sub_tasks: list[str], agent_uuid: str = "unknown") -> TaskResult:
        """
        Execute sub-tasks as a PIPELINE — each agent receives the results
        of the previous agent as context. This enables:
        "research X, write a summary, and remember it" to flow data correctly.
        """
        results = []
        all_tool_calls = []
        total_tokens = 0
        previous_output = ""

        for sub_task in sub_tasks:
            agent_key = self._classify_intent(sub_task)
            agent = self.sub_agents[agent_key]

            # Inject previous results as context for pipeline agents
            enriched_task = sub_task
            if previous_output:
                # For memory agent, store the actual results
                if agent_key == "memory":
                    enriched_task = f"remember this: {previous_output[:1000]}"
                # For creative agent, work with the data
                elif agent_key == "creative":
                    enriched_task = f"{sub_task}: {previous_output[:1000]}"
                # For other agents, append as context
                else:
                    enriched_task = f"{sub_task} (context: {previous_output[:500]})"

            logger.info(f"[Orchestrator] Pipeline → {agent.config.name}: {enriched_task[:80]}...")

            result = await agent.execute(enriched_task, agent_uuid=agent_uuid)
            results.append(result)
            previous_output = result.output  # Forward to next agent

        total_tokens = sum(r.tokens_used for r in results)
        total_cost = sum(r.cost_usd for r in results)
        all_tool_calls = []
        for r in results:
            all_tool_calls.extend(r.tool_calls)

        return TaskResult(
            success=all(r.success for r in results),
            output="\n\n".join(r.output for r in results),
            tool_calls=all_tool_calls,
            tokens_used=total_tokens,
            cost_usd=round(total_cost, 6),
            agent_uuid=agent_uuid
        )

    def _classify_intent(self, task: str) -> str:
        """Classify the intent of a task to determine which agent handles it."""
        t = task.lower().strip()

        # Score each agent
        scores = {}
        for agent_key, keywords in INTENT_RULES.items():
            score = 0
            for kw in keywords:
                if kw in t:
                    # Longer keywords = more specific = higher score
                    score += len(kw)
            if score > 0:
                scores[agent_key] = score

        if scores:
            best = max(scores, key=scores.get)
            return best

        # Default fallback: system agent
        return "system"

    def _clean_input(self, task: str) -> str:
        """Strip terminal prompts and common conversational prefixes."""
        import re
        # Strip internal AGOS prompt and user/assistant labels
        task = re.sub(r'^(🤖\s*AGOS\s*>\s*)+', '', task).strip()
        task = re.sub(r'^(User|Assistant|Human|AI):\s*', '', task, flags=re.IGNORECASE).strip()
        return task

    def list_agents(self) -> list[dict]:
        """Return info about all registered agents."""
        return [
            {
                "id": key,
                "name": agent.config.name,
                "model": agent.config.model,
                "priority": agent.config.priority,
                "capabilities": agent.config.capabilities,
                "status": "active",
            }
            for key, agent in self.sub_agents.items()
        ]
