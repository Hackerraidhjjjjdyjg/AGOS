from typing import Optional
# AGOS — Data Agent
"""
Data Agent — Data analysis, SQL queries, CSV processing, statistics.
Tools: query_sqlite, analyze_csv, compute_stats, create_chart, pivot_data
"""

import asyncio
import csv
import io
import json
import math
import os
import re
import sqlite3
import tempfile
from collections import Counter
from agents.base import BaseAgent, AgentConfig, TaskResult


class DataAgent(BaseAgent):
    """Analyzes data: SQL queries, CSV processing, statistics, charts."""

    def __init__(self, config=None):
        if config is None:
            config = AgentConfig(
                name="Data Agent",
                model="llama-3.1-8b-instant",
                priority=2,
                token_budget=4096,
                capabilities=[
                    "query_sqlite", "analyze_csv", "compute_stats",
                    "create_chart", "pivot_data",
                ],
            )
        super().__init__(config)
        self.tools = {
            "query_sqlite": self._query_sqlite,
            "analyze_csv": self._analyze_csv,
            "compute_stats": self._compute_stats,
            "create_chart": self._create_chart,
            "pivot_data": self._pivot_data,
        }

    async def sense(self, task: str) -> str:
        return f"Data task: {task}"

    def quick_think(self, task: str) -> Optional[dict]:
        t = task.lower().strip()
        if t.startswith(("query ", "sql ", "select ")):
            sql = task.split(" ", 1)[1].strip() if not t.startswith("select") else task
            return {"steps": [{"tool": "query_sqlite", "args": {"query": sql}}]}
        if t.startswith(("analyze ", "read csv ")):
            path = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "analyze_csv", "args": {"path": path}}]}
        if t.startswith(("stats ", "statistics ")):
            data = task.split(" ", 1)[1].strip()
            return {"steps": [{"tool": "compute_stats", "args": {"data": data}}]}
        return None

    async def act(self, plan: dict) -> TaskResult:
        results, tool_calls = [], []
        for step in plan.get("steps", []):
            tool_name = step.get("tool")
            args = step.get("args", {})
            if tool_name in self.tools:
                try:
                    result = await asyncio.to_thread(self.tools[tool_name], **args)
                    results.append(result)
                    tool_calls.append({"tool": tool_name, "result": str(result)[:500]})
                except Exception as e:
                    tool_calls.append({"tool": tool_name, "error": str(e)})

        output = f"[Data Agent] " + " | ".join(
            f"{'✅' if 'result' in tc else '❌'} {tc['tool']}: {tc.get('result', tc.get('error', ''))[:200]}"
            for tc in tool_calls
        )
        return TaskResult(success=len(tool_calls) > 0, output=output, tool_calls=tool_calls, tokens_used=self._tokens_used)

    # ─── Tools ───────────────────────────────────

    # SQL statements that modify data or schema
    _DANGEROUS_SQL_PATTERNS = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|ATTACH|DETACH|PRAGMA|LOAD_EXTENSION)\b",
        re.IGNORECASE,
    )

    def _query_sqlite(self, query: str, db_path: str = "") -> str:
        """Execute read-only SQL on AGOS database or in-memory."""
        if self._DANGEROUS_SQL_PATTERNS.search(query):
            return "Rejected: only SELECT / read-only queries are allowed"

        db = db_path or ":memory:"
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA query_only = ON")
            cursor = conn.execute(query)
            cols = [d[0] for d in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            conn.close()
            if not rows:
                return "Query returned 0 rows"
            header = " | ".join(cols)
            lines = [header, "-" * len(header)]
            for row in rows[:50]:
                lines.append(" | ".join(str(v) for v in row))
            return "\n".join(lines)
        except Exception as e:
            return f"SQL error: {e}"

    def _analyze_csv(self, path: str) -> str:
        """Analyze a CSV file — rows, columns, types, sample."""
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return f"File not found: {path}"
        with open(path) as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            rows = list(reader)

        report = [
            f"File: {path}",
            f"Rows: {len(rows)}",
            f"Columns: {len(headers)} → {', '.join(headers[:10])}",
        ]

        # Sample
        if rows:
            report.append(f"\nFirst 3 rows:")
            for row in rows[:3]:
                report.append("  " + " | ".join(str(v)[:20] for v in row))

        return "\n".join(report)

    def _compute_stats(self, data: str) -> str:
        """Compute statistics on a list of numbers."""
        nums = []
        for token in data.replace(",", " ").split():
            try:
                nums.append(float(token))
            except ValueError:
                continue

        if not nums:
            return "No numeric data found"

        n = len(nums)
        mean = sum(nums) / n
        sorted_nums = sorted(nums)
        median = sorted_nums[n // 2] if n % 2 else (sorted_nums[n // 2 - 1] + sorted_nums[n // 2]) / 2
        variance = sum((x - mean) ** 2 for x in nums) / n
        std = math.sqrt(variance)

        return (
            f"Count: {n}\n"
            f"Mean: {mean:.4f}\n"
            f"Median: {median:.4f}\n"
            f"Std Dev: {std:.4f}\n"
            f"Min: {min(nums):.4f}\n"
            f"Max: {max(nums):.4f}\n"
            f"Sum: {sum(nums):.4f}"
        )

    def _create_chart(self, data: str, chart_type: str = "bar", title: str = "Chart") -> str:
        """Create a text-based chart (ASCII art)."""
        nums = []
        labels = []
        for line in data.strip().split("\n"):
            parts = line.split(":")
            if len(parts) == 2:
                labels.append(parts[0].strip())
                try:
                    nums.append(float(parts[1].strip()))
                except ValueError:
                    continue

        if not nums:
            return "No data to chart. Format: label: value (one per line)"

        max_val = max(nums)
        chart_lines = [f"  {title}", "  " + "─" * 40]
        for label, val in zip(labels, nums):
            bar_len = int((val / max_val) * 30) if max_val else 0
            bar = "█" * bar_len
            chart_lines.append(f"  {label:>12} │{bar} {val:.1f}")
        chart_lines.append("  " + "─" * 40)
        return "\n".join(chart_lines)

    def _pivot_data(self, data: str, group_by: str = "") -> str:
        """Pivot/group data by a key."""
        lines = data.strip().split("\n")
        if not lines:
            return "No data to pivot"
        groups = Counter()
        for line in lines:
            key = line.split(",")[0].strip() if "," in line else line.strip()
            groups[key] += 1
        result = [f"Group: {k} → Count: {v}" for k, v in groups.most_common(20)]
        return "\n".join(result) if result else "No groups found"
