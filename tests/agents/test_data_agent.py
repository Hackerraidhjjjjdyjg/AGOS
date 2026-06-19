"""Unit tests for DataAgent tools and parsing."""

import asyncio
import os

from agents.data_agent import DataAgent


def agent():
    return DataAgent()


def test_quick_think_query():
    plan = agent().quick_think("query SELECT * FROM users")
    assert plan == {"steps": [{"tool": "query_sqlite",
                               "args": {"query": "SELECT * FROM users"}}]}


def test_quick_think_select_keeps_full_statement():
    plan = agent().quick_think("select name from t")
    assert plan["steps"][0]["args"]["query"] == "select name from t"


def test_quick_think_stats():
    plan = agent().quick_think("stats 1 2 3")
    assert plan == {"steps": [{"tool": "compute_stats", "args": {"data": "1 2 3"}}]}


def test_quick_think_no_match():
    assert agent().quick_think("hello there") is None


def test_compute_stats():
    out = agent()._compute_stats("2, 4, 6, 8, 10")
    assert "Count: 5" in out
    assert "Mean: 6.0000" in out
    assert "Median: 6.0000" in out
    assert "Min: 2.0000" in out
    assert "Max: 10.0000" in out
    assert "Sum: 30.0000" in out


def test_compute_stats_even_count_median():
    out = agent()._compute_stats("1 2 3 4")
    assert "Median: 2.5000" in out


def test_compute_stats_no_numbers():
    assert agent()._compute_stats("nothing numeric") == "No numeric data found"


def test_query_sqlite_in_memory():
    out = agent()._query_sqlite("SELECT 2 + 3 AS total")
    assert "total" in out
    assert "5" in out


def test_query_sqlite_empty_result():
    out = agent()._query_sqlite("SELECT 1 WHERE 1 = 0")
    assert out == "Query returned 0 rows"


def test_query_sqlite_error():
    assert agent()._query_sqlite("NOT VALID SQL").startswith("SQL error:")


def test_analyze_csv(tmp_path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("name,age\nAlice,30\nBob,25\nCarol,40\n")
    out = agent()._analyze_csv(str(csv_file))
    assert "Rows: 3" in out
    assert "Columns: 2" in out
    assert "name" in out and "age" in out


def test_analyze_csv_missing():
    assert agent()._analyze_csv("/no/such/file.csv").startswith("File not found")


def test_create_chart():
    out = agent()._create_chart("apples: 5\nbananas: 10", title="Fruit")
    assert "Fruit" in out
    assert "█" in out
    assert "apples" in out and "bananas" in out


def test_create_chart_no_data():
    assert agent()._create_chart("garbage").startswith("No data to chart")


def test_pivot_data():
    out = agent()._pivot_data("east,1\neast,2\nwest,3")
    assert "Group: east → Count: 2" in out
    assert "Group: west → Count: 1" in out


def test_act_runs_compute_stats():
    result = asyncio.run(agent().act(
        {"steps": [{"tool": "compute_stats", "args": {"data": "5 10 15"}}]}
    ))
    assert result.success is True
    assert "Mean: 10.0000" in result.output
    assert result.tool_calls[0]["tool"] == "compute_stats"
