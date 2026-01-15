"""
Base guardrail classes for the Autonomi SDK.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class GuardrailAction(Enum):
    """Actions a guardrail can take."""
    ALLOW = auto()      # Input/output passes, continue
    TRANSFORM = auto()  # Input/output modified, continue with new value
    BLOCK = auto()      # Input/output rejected, return error
    ESCALATE = auto()   # Input/output flagged for human review


@dataclass
class GuardrailResult:
    """Result of a guardrail check."""
    action: GuardrailAction
    reason: str = ""
    transformed_value: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def allow(cls) -> "GuardrailResult":
        """Allow the input/output to pass."""
        return cls(action=GuardrailAction.ALLOW)

    @classmethod
    def transform(cls, new_value: str, reason: str = "") -> "GuardrailResult":
        """Transform the input/output."""
        return cls(
            action=GuardrailAction.TRANSFORM,
            reason=reason,
            transformed_value=new_value,
        )

    @classmethod
    def block(cls, reason: str) -> "GuardrailResult":
        """Block the input/output."""
        return cls(action=GuardrailAction.BLOCK, reason=reason)

    @classmethod
    def escalate(cls, reason: str) -> "GuardrailResult":
        """Escalate for human review."""
        return cls(action=GuardrailAction.ESCALATE, reason=reason)

    @property
    def is_allowed(self) -> bool:
        """Check if the result allows continuation."""
        return self.action in (GuardrailAction.ALLOW, GuardrailAction.TRANSFORM)

    @property
    def is_blocked(self) -> bool:
        """Check if the result blocks continuation."""
        return self.action == GuardrailAction.BLOCK


class Guardrail(ABC):
    """
    Base class for guardrails.

    Guardrails validate and transform inputs/outputs.
    """

    name: str = "guardrail"
    description: str = ""

    @abstractmethod
    async def check(self, value: str) -> GuardrailResult:
        """
        Check a value against this guardrail.

        Args:
            value: The input or output to check

        Returns:
            GuardrailResult indicating the action to take
        """
        pass

    def check_sync(self, value: str) -> GuardrailResult:
        """Synchronous version of check."""
        import asyncio
        return asyncio.run(self.check(value))


class InputGuardrail(Guardrail):
    """
    Guardrail for validating inputs before agent execution.

    Common uses:
    - Injection detection
    - Content policy validation
    - Scope validation
    - PII detection/redaction
    """
    pass


class OutputGuardrail(Guardrail):
    """
    Guardrail for validating outputs after agent execution.

    Common uses:
    - Secret detection
    - Quality validation
    - Policy compliance
    - Content safety
    """
    pass


class GuardrailPipeline:
    """
    Pipeline of guardrails to run in sequence.
    """

    def __init__(self, guardrails: Optional[List[Guardrail]] = None):
        self.guardrails = guardrails or []

    def add(self, guardrail: Guardrail) -> "GuardrailPipeline":
        """Add a guardrail to the pipeline."""
        self.guardrails.append(guardrail)
        return self

    async def check(self, value: str) -> GuardrailResult:
        """
        Run all guardrails in sequence.

        Stops on first BLOCK or ESCALATE.
        Applies transformations in order.
        """
        current_value = value

        for guardrail in self.guardrails:
            result = await guardrail.check(current_value)

            if result.action == GuardrailAction.BLOCK:
                return result

            if result.action == GuardrailAction.ESCALATE:
                return result

            if result.action == GuardrailAction.TRANSFORM:
                current_value = result.transformed_value or current_value

        # All guardrails passed
        if current_value != value:
            return GuardrailResult.transform(current_value, "Transformed by pipeline")

        return GuardrailResult.allow()
