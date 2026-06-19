"""Unit tests for the memory stores (episodic SQLite + semantic fallback)."""

import sqlite3

import pytest

import memory.semantic as semantic_module
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory


def make_episodic(tmp_path):
    return EpisodicMemory(db_path=str(tmp_path / "ep.db"))


def test_episodic_log_and_count(tmp_path):
    em = make_episodic(tmp_path)
    assert em.count() == 0
    em.log("user", "hello", agent_id="a1")
    em.log("assistant", "hi there", agent_id="a1",
           tool_calls=[{"tool": "x"}], metadata={"k": "v"})
    assert em.count() == 2


def test_episodic_get_recent_orders_newest_first(tmp_path):
    em = make_episodic(tmp_path)
    em.log("user", "first")
    em.log("user", "second")
    recent = em.get_recent(limit=10)
    assert [r["content"] for r in recent] == ["second", "first"]
    assert recent[0]["role"] == "user"


def test_episodic_search_known_limitation(tmp_path):
    # search() selects columns that don't exist on the FTS5 virtual table,
    # so it currently raises. Captured here so a fix is intentional.
    em = make_episodic(tmp_path)
    em.log("user", "the quick brown fox")
    with pytest.raises(sqlite3.OperationalError):
        em.search("fox")


def test_semantic_disabled_fallback(tmp_path, monkeypatch):
    # Force the no-ChromaDB path so the test is deterministic regardless of
    # whether chromadb is installed in the environment.
    monkeypatch.setattr(semantic_module, "HAS_CHROMADB", False)
    sm = SemanticMemory(persist_dir=str(tmp_path / "sem"))
    assert sm.client is None
    assert sm.collection is None
    # All operations degrade gracefully to no-ops.
    sm.store("doc1", "some text", {"k": "v"})
    assert sm.recall("anything") == []
    assert sm.count() == 0
