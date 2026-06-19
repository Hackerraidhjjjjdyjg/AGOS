"""Unit tests for CodeAgent parsing and local (non-LLM) tools."""

import os

from agents.code_agent import CodeAgent


def agent():
    return CodeAgent()


def test_quick_think_run_python():
    plan = agent().quick_think("run print('hi')")
    assert plan == {"steps": [{"tool": "run_python", "args": {"code": "print('hi')"}}]}


def test_quick_think_read_file():
    plan = agent().quick_think("read /tmp/notes.txt")
    assert plan == {"steps": [{"tool": "read_file", "args": {"path": "/tmp/notes.txt"}}]}


def test_quick_think_git():
    plan = agent().quick_think("git status please")
    assert plan == {"steps": [{"tool": "git_status", "args": {}}]}


def test_quick_think_generate():
    plan = agent().quick_think("generate a fibonacci function")
    assert plan["steps"][0]["tool"] == "generate_code"
    assert plan["steps"][0]["args"]["language"] == "python"


def test_quick_think_no_match():
    assert agent().quick_think("hello world") is None


def test_run_python_success():
    out = agent()._run_python("print(2 + 2)")
    assert "4" in out


def test_run_python_error():
    out = agent()._run_python("raise ValueError('boom')")
    assert "ValueError" in out


def test_run_python_no_output():
    assert agent()._run_python("x = 1") == "(no output)"


def test_read_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("contents here")
    assert agent()._read_file(str(f)) == "contents here"


def test_read_file_missing():
    assert agent()._read_file("/no/such/file").startswith("File not found")


def test_write_file(tmp_path):
    target = tmp_path / "sub" / "out.txt"
    msg = agent()._write_file(str(target), "payload")
    assert "Written" in msg
    assert os.path.exists(target)
    assert target.read_text() == "payload"
