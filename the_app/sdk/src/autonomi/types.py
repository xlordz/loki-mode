"""
Core types for the Autonomi SDK.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Union
from datetime import datetime


class Role(str, Enum):
    """Message roles in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ConfidenceTier(Enum):
    """Confidence tiers for task routing."""
    TIER_1 = 1  # >= 0.90: auto-execute, skip review
    TIER_2 = 2  # 0.60-0.90: execute, post-validation
    TIER_3 = 3  # 0.30-0.60: execute, full quality pipeline
    TIER_4 = 4  # < 0.30: escalate, human required


@dataclass
class Message:
    """A message in a conversation."""
    role: Role
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API calls."""
        d: Dict[str, Any] = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        return d


@dataclass
class ToolCall:
    """A tool call made by the model."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class Usage:
    """Token usage information."""
    input_tokens: int
    output_tokens: int
    total_tokens: int

    @property
    def cost_estimate(self) -> float:
        """Rough cost estimate (provider-specific pricing applied elsewhere)."""
        # Default estimate, overridden by actual provider pricing
        return (self.input_tokens * 0.003 + self.output_tokens * 0.015) / 1000


@dataclass
class ExecutionContext:
    """Context passed through agent execution."""
    session_id: str
    task_id: str
    parent_agent: Optional[str] = None
    handoff_chain: List[str] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    files: Dict[str, str] = field(default_factory=dict)
    memory_context: List[Dict[str, Any]] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)

    def with_handoff(self, agent_name: str) -> "ExecutionContext":
        """Create new context with handoff recorded."""
        return ExecutionContext(
            session_id=self.session_id,
            task_id=self.task_id,
            parent_agent=agent_name,
            handoff_chain=self.handoff_chain + [agent_name],
            variables=self.variables.copy(),
            files=self.files.copy(),
            memory_context=self.memory_context.copy(),
            start_time=self.start_time,
        )


@dataclass
class ConfidenceScore:
    """Confidence score with breakdown."""
    overall: float
    tier: ConfidenceTier
    factors: Dict[str, float] = field(default_factory=dict)
    reasoning: str = ""

    @classmethod
    def calculate(
        cls,
        requirement_clarity: float,
        technical_complexity: float,
        historical_success: float,
        scope_size: float,
    ) -> "ConfidenceScore":
        """Calculate confidence score from factors."""
        weights = {
            "requirement_clarity": 0.30,
            "technical_complexity": 0.25,
            "historical_success": 0.25,
            "scope_size": 0.20,
        }

        factors = {
            "requirement_clarity": requirement_clarity,
            "technical_complexity": 1.0 - technical_complexity,  # Invert: low complexity = high confidence
            "historical_success": historical_success,
            "scope_size": 1.0 - scope_size,  # Invert: small scope = high confidence
        }

        overall = sum(factors[k] * weights[k] for k in weights)

        if overall >= 0.90:
            tier = ConfidenceTier.TIER_1
        elif overall >= 0.60:
            tier = ConfidenceTier.TIER_2
        elif overall >= 0.30:
            tier = ConfidenceTier.TIER_3
        else:
            tier = ConfidenceTier.TIER_4

        return cls(overall=overall, tier=tier, factors=factors)
