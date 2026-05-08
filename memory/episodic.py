"""
AGOS — Episodic Memory
SQLite-based interaction logs for conversation history and context.
"""

import json
import logging
import sqlite3
import time
from typing import Optional

logger = logging.getLogger("agos.memory.episodic")


class EpisodicMemory:
    """
    SQLite-based episodic memory for agent interactions.
    Logs every interaction with timestamps, roles, and tool calls.
    """

    def __init__(self, db_path: str = "./data/episodic_memory.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_tables()
        logger.info(f"EpisodicMemory initialized: {db_path}")

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                agent_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT,
                metadata TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_timestamp ON interactions(timestamp);
            CREATE INDEX IF NOT EXISTS idx_agent ON interactions(agent_id);
            
            CREATE VIRTUAL TABLE IF NOT EXISTS interactions_fts USING fts5(
                content, tokenize='porter'
            );
        """)
        self.conn.commit()

    def log(self, role: str, content: str, agent_id: str = "", 
            tool_calls: Optional[list] = None, metadata: Optional[dict] = None):
        """Log an interaction."""
        self.conn.execute(
            "INSERT INTO interactions (timestamp, agent_id, role, content, tool_calls, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), agent_id, role, content, 
             json.dumps(tool_calls) if tool_calls else None,
             json.dumps(metadata) if metadata else None),
        )
        self.conn.execute("INSERT INTO interactions_fts (content) VALUES (?)", (content,))
        self.conn.commit()

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search interactions by text content."""
        cursor = self.conn.execute(
            "SELECT id, timestamp, agent_id, role, content FROM interactions_fts "
            "WHERE content MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        )
        return [
            {"id": r[0], "timestamp": r[1], "agent_id": r[2], "role": r[3], "content": r[4]}
            for r in cursor.fetchall()
        ]

    def get_recent(self, limit: int = 20) -> list[dict]:
        """Get most recent interactions."""
        cursor = self.conn.execute(
            "SELECT id, timestamp, agent_id, role, content FROM interactions ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [
            {"id": r[0], "timestamp": r[1], "agent_id": r[2], "role": r[3], "content": r[4]}
            for r in cursor.fetchall()
        ]

    def count(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM interactions")
        return cursor.fetchone()[0]
