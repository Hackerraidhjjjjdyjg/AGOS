# AGOS — Shared Tool Execution Utilities
"""
Eliminates duplicated act() and output-formatting patterns across agent implementations.

All agents share the same pattern:
  1. Iterate over plan["steps"]
  2. Look up tool handler (by dict or attribute naming convention)
  3. Call it (sync via asyncio.to_thread or async directly)
  4. Collect results and tool_calls
  5. Format output

This module provides `execute_tool_plan()` and `format_tool_output()` to replace
that boilerplate in every agent.
"""

import asyncio
import inspect
from typing import Any, Callable, Optional


async def execute_tool_plan(
    plan: dict,
    tools: Optional[dict[str, Callable]] = None,
    agent_instance: Any = None,
    tool_prefix: str = "_tool_",
) -> tuple[list[Any], list[dict]]:
    """
    Execute all steps in a plan dict, dispatching to the appropriate tool handler.

    Supports two tool lookup modes (tried in order):
      1. Dict-based: pass `tools` mapping name -> callable
      2. Attribute-based: pass `agent_instance` and `tool_prefix`

    Automatically handles both sync and async handlers:
      - Async handlers are awaited directly
      - Sync handlers are run via asyncio.to_thread to avoid blocking

    Returns:
        (results, tool_calls) — results is the list of return values,
        tool_calls is the list of dicts with 'tool' and 'result'/'error'.
    """
    results: list[Any] = []
    tool_calls: list[dict] = []

    for step in plan.get("steps", []):
        tool_name = step.get("tool")
        args = step.get("args", {})

        handler = _resolve_handler(tool_name, tools, agent_instance, tool_prefix)
        if handler is None:
            tool_calls.append({"tool": tool_name, "error": f"Tool '{tool_name}' not found"})
            continue

        try:
            if asyncio.iscoroutinefunction(handler) or inspect.iscoroutinefunction(handler):
                result = await handler(**args)
            else:
                result = await asyncio.to_thread(handler, **args)
            results.append(result)
            tool_calls.append({"tool": tool_name, "result": str(result)[:500]})
        except Exception as e:
            tool_calls.append({"tool": tool_name, "error": str(e)})

    return results, tool_calls


def format_tool_output(
    agent_name: str,
    tool_calls: list[dict],
    include_details: bool = True,
) -> str:
    """
    Format tool call results into a consistent output string.

    Args:
        agent_name: Display name for the agent prefix (e.g. "Code Agent")
        tool_calls: List of tool call dicts with 'tool' and 'result'/'error'
        include_details: Whether to include result/error text after the tool name
    """
    parts = []
    for tc in tool_calls:
        status = "\u2705" if "result" in tc else "\u274c"
        if include_details:
            detail = tc.get("result", tc.get("error", ""))[:200]
            parts.append(f"{status} {tc['tool']}: {detail}")
        else:
            parts.append(f"{status} {tc['tool']}")
    return f"[{agent_name}] " + " | ".join(parts)


def _resolve_handler(
    tool_name: str,
    tools: Optional[dict[str, Callable]],
    agent_instance: Any,
    tool_prefix: str,
) -> Optional[Callable]:
    """Resolve a tool handler by name from a dict or agent attribute."""
    if tools and tool_name in tools:
        return tools[tool_name]
    if agent_instance is not None:
        return getattr(agent_instance, f"{tool_prefix}{tool_name}", None)
    return None
