import pytest
from agents.creative_agent import CreativeAgent

def test_quick_think_translate_default_lang():
    agent = CreativeAgent()
    task = "translate hello"
    result = agent.quick_think(task)
    assert result is not None
    assert result["steps"][0]["tool"] == "translate"
    assert result["steps"][0]["args"]["text"] == "hello"
    assert result["steps"][0]["args"]["target_language"] == "English"

def test_quick_think_translate_with_lang():
    agent = CreativeAgent()
    task = "translate hello to French"
    result = agent.quick_think(task)
    assert result is not None
    assert result["steps"][0]["tool"] == "translate"
    assert result["steps"][0]["args"]["text"] == "hello"
    assert result["steps"][0]["args"]["target_language"] == "French"

def test_quick_think_convert_to_lang():
    agent = CreativeAgent()
    # "convert to Spanish"
    # parts = task.split(" to ", 1) -> ["convert", "Spanish"]
    # text = parts[0].split(" ", 1)[1].strip() if len(parts[0].split()) > 1 else ""
    # "convert" split is ["convert"], len is 1. So text = ""
    # lang = parts[1].strip() if len(parts) > 1 else "English" -> "Spanish"
    task = "convert to Spanish"
    result = agent.quick_think(task)
    assert result is not None
    assert result["steps"][0]["tool"] == "translate"
    assert result["steps"][0]["args"]["text"] == ""
    assert result["steps"][0]["args"]["target_language"] == "Spanish"

def test_quick_think_write():
    agent = CreativeAgent()
    task = "write a poem about AI"
    result = agent.quick_think(task)
    assert result is not None
    assert result["steps"][0]["tool"] == "write_text"
    assert result["steps"][0]["args"]["topic"] == "a poem about AI"

def test_quick_think_rewrite():
    agent = CreativeAgent()
    task = "rewrite this sentence"
    result = agent.quick_think(task)
    assert result is not None
    assert result["steps"][0]["tool"] == "rewrite"
    assert result["steps"][0]["args"]["text"] == "this sentence"

def test_quick_think_outline():
    agent = CreativeAgent()
    task = "outline a blog post"
    result = agent.quick_think(task)
    assert result is not None
    assert result["steps"][0]["tool"] == "generate_outline"
    assert result["steps"][0]["args"]["topic"] == "a blog post"

def test_quick_think_no_match():
    agent = CreativeAgent()
    task = "random task"
    result = agent.quick_think(task)
    assert result is None
