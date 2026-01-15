"""
Session management for the Autonomi SDK.

Sessions track conversation state and enable persistence.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from autonomi.types import Message, Role, Usage


@dataclass
class SessionConfig:
    """Configuration for a session."""
    max_messages: int = 100
    auto_summarize: bool = True
    summarize_threshold: int = 50
    persist: bool = False
    persist_path: Optional[str] = None


@dataclass
class SessionState:
    """State of a session."""
    id: str
    messages: List[Message] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    total_usage: Usage = field(default_factory=lambda: Usage(0, 0, 0))
    total_cost: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    agent_history: List[str] = field(default_factory=list)


class Session:
    """
    Manages conversation state and context.

    Sessions enable:
    - Multi-turn conversations
    - State persistence
    - Context management
    - Usage tracking
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        config: Optional[SessionConfig] = None,
    ):
        """
        Initialize a session.

        Args:
            session_id: Optional existing session ID
            config: Session configuration
        """
        self.config = config or SessionConfig()
        self.state = SessionState(
            id=session_id or str(uuid.uuid4()),
        )

    @property
    def id(self) -> str:
        """Get session ID."""
        return self.state.id

    @property
    def messages(self) -> List[Message]:
        """Get conversation messages."""
        return self.state.messages

    def add_message(self, message: Message) -> None:
        """Add a message to the conversation."""
        self.state.messages.append(message)
        self.state.updated_at = datetime.now()

        # Auto-summarize if threshold reached
        if (
            self.config.auto_summarize
            and len(self.state.messages) > self.config.summarize_threshold
        ):
            self._summarize_messages()

        # Trim if exceeds max
        if len(self.state.messages) > self.config.max_messages:
            # Keep system message and recent messages
            system_msgs = [m for m in self.state.messages if m.role == Role.SYSTEM]
            other_msgs = [m for m in self.state.messages if m.role != Role.SYSTEM]
            keep_count = self.config.max_messages - len(system_msgs)
            self.state.messages = system_msgs + other_msgs[-keep_count:]

    def add_user_message(self, content: str) -> Message:
        """Add a user message."""
        msg = Message(role=Role.USER, content=content)
        self.add_message(msg)
        return msg

    def add_assistant_message(self, content: str) -> Message:
        """Add an assistant message."""
        msg = Message(role=Role.ASSISTANT, content=content)
        self.add_message(msg)
        return msg

    def add_system_message(self, content: str) -> Message:
        """Add a system message."""
        msg = Message(role=Role.SYSTEM, content=content)
        self.add_message(msg)
        return msg

    def set_variable(self, key: str, value: Any) -> None:
        """Set a session variable."""
        self.state.variables[key] = value
        self.state.updated_at = datetime.now()

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get a session variable."""
        return self.state.variables.get(key, default)

    def record_usage(self, usage: Usage, cost: float) -> None:
        """Record usage from an agent execution."""
        self.state.total_usage.input_tokens += usage.input_tokens
        self.state.total_usage.output_tokens += usage.output_tokens
        self.state.total_usage.total_tokens += usage.total_tokens
        self.state.total_cost += cost
        self.state.updated_at = datetime.now()

    def record_agent(self, agent_name: str) -> None:
        """Record an agent that was used."""
        self.state.agent_history.append(agent_name)

    def get_context(self) -> Dict[str, Any]:
        """Get session context for passing to agents."""
        return {
            "session_id": self.state.id,
            "variables": self.state.variables,
            "message_count": len(self.state.messages),
            "total_cost": self.state.total_cost,
        }

    def _summarize_messages(self) -> None:
        """
        Summarize older messages to reduce context size.

        In production, use an LLM to create better summaries.
        """
        if len(self.state.messages) <= self.config.summarize_threshold:
            return

        # Simple approach: keep system msgs and recent messages
        system_msgs = [m for m in self.state.messages if m.role == Role.SYSTEM]
        other_msgs = [m for m in self.state.messages if m.role != Role.SYSTEM]

        # Create summary of older messages
        older = other_msgs[:-20]
        recent = other_msgs[-20:]

        if older:
            summary_content = f"[Summary of {len(older)} previous messages]"
            summary = Message(role=Role.SYSTEM, content=summary_content)
            self.state.messages = system_msgs + [summary] + recent

    def clear(self) -> None:
        """Clear conversation history."""
        self.state.messages = []
        self.state.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary."""
        return {
            "id": self.state.id,
            "messages": [m.to_dict() for m in self.state.messages],
            "variables": self.state.variables,
            "total_usage": {
                "input_tokens": self.state.total_usage.input_tokens,
                "output_tokens": self.state.total_usage.output_tokens,
                "total_tokens": self.state.total_usage.total_tokens,
            },
            "total_cost": self.state.total_cost,
            "created_at": self.state.created_at.isoformat(),
            "updated_at": self.state.updated_at.isoformat(),
            "agent_history": self.state.agent_history,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Deserialize session from dictionary."""
        session = cls(session_id=data["id"])
        session.state.messages = [
            Message(
                role=Role(m["role"]),
                content=m["content"],
                name=m.get("name"),
                tool_call_id=m.get("tool_call_id"),
            )
            for m in data.get("messages", [])
        ]
        session.state.variables = data.get("variables", {})
        usage_data = data.get("total_usage", {})
        session.state.total_usage = Usage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        session.state.total_cost = data.get("total_cost", 0.0)
        session.state.agent_history = data.get("agent_history", [])
        if "created_at" in data:
            session.state.created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            session.state.updated_at = datetime.fromisoformat(data["updated_at"])
        return session
