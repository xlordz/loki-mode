"""
Base memory classes for the Autonomi SDK.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class MemoryTier(str, Enum):
    """Memory tiers."""
    EPISODIC = "episodic"    # What happened
    SEMANTIC = "semantic"    # What we know
    PROCEDURAL = "procedural"  # How to do things


@dataclass
class MemoryEvent:
    """A memory event."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tier: MemoryTier = MemoryTier.EPISODIC
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    timestamp: datetime = field(default_factory=datetime.now)
    agent_name: str = ""
    session_id: str = ""
    relevance_score: float = 0.0
    access_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "tier": self.tier.value,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "relevance_score": self.relevance_score,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEvent":
        """Create from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            tier=MemoryTier(data.get("tier", "episodic")),
            content=data.get("content", ""),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
            agent_name=data.get("agent_name", ""),
            session_id=data.get("session_id", ""),
            relevance_score=data.get("relevance_score", 0.0),
            access_count=data.get("access_count", 0),
        )


@dataclass
class MemoryConfig:
    """Configuration for memory."""
    backend: str = "sqlite"
    path: str = ".autonomi/memory.db"
    max_episodic_events: int = 1000
    max_semantic_events: int = 500
    max_procedural_events: int = 100
    consolidation_threshold: int = 100  # Consolidate after N episodic events
    embedding_model: Optional[str] = None  # Model for generating embeddings


class Memory(ABC):
    """
    Abstract base class for memory systems.

    Memory enables agents to learn and improve over time
    without retraining.
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or MemoryConfig()

    @abstractmethod
    async def store(self, event: MemoryEvent) -> None:
        """Store a memory event."""
        pass

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        tier: Optional[MemoryTier] = None,
        limit: int = 10,
        agent_name: Optional[str] = None,
    ) -> List[MemoryEvent]:
        """
        Retrieve relevant memories.

        Args:
            query: Search query
            tier: Specific tier to search (None = all)
            limit: Maximum results
            agent_name: Filter by agent

        Returns:
            List of relevant memory events
        """
        pass

    @abstractmethod
    async def consolidate(self) -> int:
        """
        Consolidate episodic memories into semantic memories.

        Returns:
            Number of memories consolidated
        """
        pass

    @abstractmethod
    async def forget(
        self,
        before: Optional[datetime] = None,
        tier: Optional[MemoryTier] = None,
        agent_name: Optional[str] = None,
    ) -> int:
        """
        Forget memories matching criteria.

        Returns:
            Number of memories forgotten
        """
        pass

    @abstractmethod
    async def count(self, tier: Optional[MemoryTier] = None) -> int:
        """Count memories."""
        pass

    async def store_interaction(
        self,
        agent_name: str,
        session_id: str,
        prompt: str,
        response: str,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEvent:
        """
        Convenience method to store an interaction.
        """
        event = MemoryEvent(
            tier=MemoryTier.EPISODIC,
            content=f"Prompt: {prompt}\nResponse: {response}",
            metadata={
                "prompt": prompt,
                "response": response,
                "success": success,
                **(metadata or {}),
            },
            agent_name=agent_name,
            session_id=session_id,
        )
        await self.store(event)
        return event

    async def store_skill(
        self,
        agent_name: str,
        skill_name: str,
        description: str,
        success_rate: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEvent:
        """
        Store a learned skill.
        """
        event = MemoryEvent(
            tier=MemoryTier.PROCEDURAL,
            content=f"Skill: {skill_name}\n{description}",
            metadata={
                "skill_name": skill_name,
                "success_rate": success_rate,
                **(metadata or {}),
            },
            agent_name=agent_name,
        )
        await self.store(event)
        return event

    async def get_context_for_task(
        self,
        task: str,
        agent_name: str,
        limit: int = 5,
    ) -> List[MemoryEvent]:
        """
        Get relevant context for a task.

        Retrieves from all tiers and merges results.
        """
        results: List[MemoryEvent] = []

        # Get relevant episodic memories (similar past tasks)
        episodic = await self.retrieve(
            task, tier=MemoryTier.EPISODIC, limit=limit, agent_name=agent_name
        )
        results.extend(episodic)

        # Get relevant semantic memories (patterns, facts)
        semantic = await self.retrieve(
            task, tier=MemoryTier.SEMANTIC, limit=limit, agent_name=agent_name
        )
        results.extend(semantic)

        # Get relevant procedural memories (skills)
        procedural = await self.retrieve(
            task, tier=MemoryTier.PROCEDURAL, limit=limit, agent_name=agent_name
        )
        results.extend(procedural)

        # Sort by relevance and limit
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit]
