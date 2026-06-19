"""Unit tests for agents.base (AgentConfig, TaskResult, BaseAgent lifecycle)."""

import asyncio

from agents.base import AgentConfig, TaskResult
from agents.data_agent import DataAgent


def test_agent_config_defaults():
    c = AgentConfig(name="X")
    assert c.name == "X"
    assert c.model == "llama-3.1-8b-instant"
    assert c.priority == 2
    assert c.token_budget == 4096
    assert c.capabilities == []
    assert c.groq_url == "https://api.groq.com/openai/v1/chat/completions"


def test_task_result_defaults():
    r = TaskResult(success=True, output="hello")
    assert r.success is True
    assert r.output == "hello"
    assert r.tool_calls == []
    assert r.tokens_used == 0
    assert r.cost_usd == 0.0
    assert r.error is None


def test_default_system_prompt_mentions_capabilities():
    agent = DataAgent()
    prompt = agent._default_system_prompt()
    assert "Data Agent" in prompt
    assert "query_sqlite" in prompt
    assert "ReAct" in prompt


def test_create_result_cost_calculation():
    agent = DataAgent()
    agent.agent_uuid = "uuid-123"
    agent._tokens_used = 1000
    result = agent._create_result(True, "done", [{"tool": "x"}])

    # Cost spec: $0.00073 per 1K tokens.
    assert result.cost_usd == 0.00073
    assert result.tokens_used == 1000
    assert result.agent_uuid == "uuid-123"
    assert result.success is True
    assert result.output == "done"


def test_is_running_and_tokens_used_properties():
    agent = DataAgent()
    assert agent.is_running is False
    assert agent.tokens_used == 0
    agent._tokens_used = 42
    assert agent.tokens_used == 42


def test_call_llm_without_api_key_returns_empty(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    agent = DataAgent()
    agent.config.groq_api_key = ""
    assert asyncio.run(agent.call_llm("hello")) == ""


def test_execute_fast_path_runs_quick_think():
    # "stats ..." triggers quick_think -> compute_stats (no LLM, deterministic).
    agent = DataAgent()
    result = asyncio.run(agent.execute("stats 1 2 3 4 5"))
    assert result.success is True
    assert "Mean" in result.output
    assert result.ttft_ms == 1  # fast-path latency marker


def test_execute_slow_path_without_llm(monkeypatch):
    # No quick_think match + no API key -> graceful "no results" outcome.
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    agent = DataAgent()
    agent.config.groq_api_key = ""
    result = asyncio.run(agent.execute("ponder the meaning of existence"))
    assert result.success is False
    assert result.output == "No definitive results found."
