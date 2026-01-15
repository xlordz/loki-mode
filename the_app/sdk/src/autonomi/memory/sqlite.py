"""
SQLite memory backend for the Autonomi SDK.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from autonomi.memory.base import Memory, MemoryConfig, MemoryEvent, MemoryTier


class SQLiteMemory(Memory):
    """
    SQLite-based memory implementation.

    Good for local development and single-agent scenarios.
    For production multi-agent systems, use PostgreSQL.
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        super().__init__(config)
        self._conn: Optional[sqlite3.Connection] = None
        self._initialized = False

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create the database connection."""
        if self._conn is None:
            # Ensure directory exists
            db_path = self.config.path
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row

            if not self._initialized:
                self._initialize_schema()
                self._initialized = True

        return self._conn

    def _initialize_schema(self) -> None:
        """Create database tables."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                tier TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                timestamp TEXT NOT NULL,
                agent_name TEXT,
                session_id TEXT,
                relevance_score REAL DEFAULT 0,
                access_count INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_memories_tier ON memories(tier);
            CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_name);
            CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);
            CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp);

            -- Full-text search index
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content,
                content_rowid='rowid'
            );
        """)
        self.conn.commit()

    async def store(self, event: MemoryEvent) -> None:
        """Store a memory event."""
        cursor = self.conn.execute(
            """
            INSERT OR REPLACE INTO memories
            (id, tier, content, metadata, timestamp, agent_name, session_id, relevance_score, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.tier.value,
                event.content,
                json.dumps(event.metadata),
                event.timestamp.isoformat(),
                event.agent_name,
                event.session_id,
                event.relevance_score,
                event.access_count,
            ),
        )

        # Update FTS index
        self.conn.execute(
            """
            INSERT OR REPLACE INTO memories_fts (rowid, content)
            VALUES ((SELECT rowid FROM memories WHERE id = ?), ?)
            """,
            (event.id, event.content),
        )

        self.conn.commit()

    async def retrieve(
        self,
        query: str,
        tier: Optional[MemoryTier] = None,
        limit: int = 10,
        agent_name: Optional[str] = None,
    ) -> List[MemoryEvent]:
        """Retrieve relevant memories using full-text search."""
        # Build query
        sql = """
            SELECT m.*, bm25(memories_fts) as rank
            FROM memories m
            JOIN memories_fts fts ON m.rowid = fts.rowid
            WHERE memories_fts MATCH ?
        """
        params: List[Any] = [query]

        if tier:
            sql += " AND m.tier = ?"
            params.append(tier.value)

        if agent_name:
            sql += " AND m.agent_name = ?"
            params.append(agent_name)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        try:
            cursor = self.conn.execute(sql, params)
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            # FTS query failed, fall back to LIKE search
            sql = """
                SELECT * FROM memories
                WHERE content LIKE ?
            """
            params = [f"%{query}%"]

            if tier:
                sql += " AND tier = ?"
                params.append(tier.value)

            if agent_name:
                sql += " AND agent_name = ?"
                params.append(agent_name)

            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = self.conn.execute(sql, params)
            rows = cursor.fetchall()

        events: List[MemoryEvent] = []
        for row in rows:
            event = MemoryEvent(
                id=row["id"],
                tier=MemoryTier(row["tier"]),
                content=row["content"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                timestamp=datetime.fromisoformat(row["timestamp"]),
                agent_name=row["agent_name"] or "",
                session_id=row["session_id"] or "",
                relevance_score=row["relevance_score"] or 0.0,
                access_count=row["access_count"] or 0,
            )

            # Update access count
            self.conn.execute(
                "UPDATE memories SET access_count = access_count + 1 WHERE id = ?",
                (event.id,),
            )

            events.append(event)

        self.conn.commit()
        return events

    async def consolidate(self) -> int:
        """
        Consolidate episodic memories into semantic memories.

        Groups similar episodic memories and creates semantic summaries.
        """
        # Get episodic memories to consolidate
        cursor = self.conn.execute(
            """
            SELECT * FROM memories
            WHERE tier = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (MemoryTier.EPISODIC.value, self.config.consolidation_threshold),
        )
        rows = cursor.fetchall()

        if len(rows) < self.config.consolidation_threshold:
            return 0

        # Simple consolidation: group by agent and create summary
        # In production, use LLM to create better summaries
        by_agent: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            agent = row["agent_name"] or "unknown"
            if agent not in by_agent:
                by_agent[agent] = []
            by_agent[agent].append(dict(row))

        consolidated = 0
        for agent_name, memories in by_agent.items():
            if len(memories) < 5:
                continue

            # Create semantic summary
            contents = [m["content"][:100] for m in memories[:10]]
            summary = f"Summary of {len(memories)} interactions:\n" + "\n".join(
                f"- {c}" for c in contents
            )

            semantic_event = MemoryEvent(
                tier=MemoryTier.SEMANTIC,
                content=summary,
                metadata={
                    "source": "consolidation",
                    "episodic_count": len(memories),
                },
                agent_name=agent_name,
            )
            await self.store(semantic_event)
            consolidated += 1

            # Mark consolidated episodic memories
            ids = [m["id"] for m in memories]
            placeholders = ",".join("?" * len(ids))
            self.conn.execute(
                f"DELETE FROM memories WHERE id IN ({placeholders})",
                ids,
            )

        self.conn.commit()
        return consolidated

    async def forget(
        self,
        before: Optional[datetime] = None,
        tier: Optional[MemoryTier] = None,
        agent_name: Optional[str] = None,
    ) -> int:
        """Forget memories matching criteria."""
        sql = "DELETE FROM memories WHERE 1=1"
        params: List[Any] = []

        if before:
            sql += " AND timestamp < ?"
            params.append(before.isoformat())

        if tier:
            sql += " AND tier = ?"
            params.append(tier.value)

        if agent_name:
            sql += " AND agent_name = ?"
            params.append(agent_name)

        cursor = self.conn.execute(sql, params)
        count = cursor.rowcount
        self.conn.commit()
        return count

    async def count(self, tier: Optional[MemoryTier] = None) -> int:
        """Count memories."""
        if tier:
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM memories WHERE tier = ?",
                (tier.value,),
            )
        else:
            cursor = self.conn.execute("SELECT COUNT(*) FROM memories")

        return cursor.fetchone()[0]

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
