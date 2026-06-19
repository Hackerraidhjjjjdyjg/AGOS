"""Unit tests for SystemAgent.quick_think parsing and act() error handling."""

import asyncio

from agents.system_agent import SystemAgent


def think(task):
    return SystemAgent().quick_think(task)


def test_open_app():
    plan = think("open Safari")
    assert plan == {"steps": [{"tool": "open_app", "args": {"app_name": "Safari"}}]}


def test_open_known_website_routes_to_search():
    plan = think("open youtube")
    assert plan["steps"][0]["tool"] == "search_web"
    assert plan["steps"][0]["args"]["query"] == "https://youtube.com"


def test_set_volume():
    plan = think("set volume to 50")
    assert plan == {"steps": [{"tool": "set_volume", "args": {"level": 50}}]}


def test_say():
    plan = think("say hello world")
    assert plan == {"steps": [{"tool": "say", "args": {"text": "hello world"}}]}


def test_search():
    plan = think("search for python tutorials")
    assert plan == {"steps": [{"tool": "search_web", "args": {"query": "python tutorials"}}]}


def test_screenshot():
    plan = think("take a screenshot now")
    assert plan["steps"][0]["tool"] == "screenshot"


def test_active_apps():
    plan = think("what apps are running")
    assert plan == {"steps": [{"tool": "get_active_apps", "args": {}}]}


def test_system_info():
    plan = think("show me system info")
    assert plan == {"steps": [{"tool": "get_system_info", "args": {}}]}


def test_clipboard():
    plan = think("read my clipboard")
    assert plan == {"steps": [{"tool": "get_clipboard", "args": {}}]}


def test_notify():
    plan = think("notify build finished")
    assert plan == {"steps": [{"tool": "send_notification",
                               "args": {"title": "AGOS", "message": "build finished"}}]}


def test_open_prefix_wins_over_compound_split():
    # "open ..." matches the open_app prefix on the whole string, so the
    # remainder (including "and ...") is treated as the app name.
    plan = think("open Spotify and set volume to 50")
    assert plan == {"steps": [{"tool": "open_app",
                               "args": {"app_name": "Spotify and set volume to 50"}}]}


def test_compound_command_when_no_prefix_matches():
    # No anchored prefix matches the full string, so the " and " branch runs
    # and recursively parses each part.
    plan = think("do something and open safari")
    assert plan == {"steps": [{"tool": "open_app", "args": {"app_name": "safari"}}]}


def test_no_match_returns_none():
    assert think("xyzzy plugh frobnicate") is None


def test_act_unimplemented_tool_is_error():
    agent = SystemAgent()
    result = asyncio.run(agent.act({"steps": [{"tool": "does_not_exist", "args": {}}]}))
    assert result.success is False
    assert "❌" in result.output
    assert result.tool_calls[0]["tool"] == "does_not_exist"
    assert "error" in result.tool_calls[0]
