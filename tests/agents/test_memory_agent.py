"""Unit tests for MemoryAgent (disk-backed memory index)."""

import agents.memory_agent as memory_agent_module
from agents.memory_agent import MemoryAgent


def make_agent(tmp_path, monkeypatch):
    # Redirect the module-level MEMORY_DIR to a temp dir before construction.
    monkeypatch.setattr(memory_agent_module, "MEMORY_DIR", str(tmp_path / "mem"))
    return MemoryAgent()


def test_quick_think_remember():
    plan = MemoryAgent().quick_think("remember the wifi password is hunter2")
    assert plan == {"steps": [{"tool": "store_memory",
                               "args": {"content": "the wifi password is hunter2"}}]}


def test_quick_think_recall():
    plan = MemoryAgent().quick_think("recall about wifi")
    assert plan == {"steps": [{"tool": "recall", "args": {"query": "wifi"}}]}


def test_quick_think_list():
    plan = MemoryAgent().quick_think("show memories")
    assert plan == {"steps": [{"tool": "list_memories", "args": {}}]}


def test_store_and_list(tmp_path, monkeypatch):
    a = make_agent(tmp_path, monkeypatch)
    msg = a._store_memory("the sky is blue", tags="nature, color")
    assert "Stored memory #1" in msg
    assert a.index["total"] == 1

    listing = a._list_memories()
    assert "Total: 1 memories" in listing
    assert "the sky is blue" in listing
    assert "nature, color" in listing


def test_recall_keyword_match(tmp_path, monkeypatch):
    a = make_agent(tmp_path, monkeypatch)
    a._store_memory("python is a programming language")
    a._store_memory("the cat sat on the mat")

    out = a._recall("python language")
    assert "Found" in out
    assert "python is a programming language" in out

    assert a._recall("nonexistent topic") == "No memories found for: nonexistent topic"


def test_semantic_search(tmp_path, monkeypatch):
    a = make_agent(tmp_path, monkeypatch)
    a._store_memory("machine learning models need data")
    out = a._semantic_search("learning data")
    assert "match" in out
    assert "machine learning" in out

    assert a._semantic_search("zzz qqq").startswith("No semantic matches")


def test_forget(tmp_path, monkeypatch):
    a = make_agent(tmp_path, monkeypatch)
    a._store_memory("delete me please")
    a._store_memory("keep this one")

    msg = a._forget("delete me")
    assert "Forgot 1 memories" in msg
    assert len(a.index["memories"]) == 1
    assert a.index["memories"][0]["content"] == "keep this one"


def test_list_empty(tmp_path, monkeypatch):
    a = make_agent(tmp_path, monkeypatch)
    assert a._list_memories() == "No memories stored yet"
