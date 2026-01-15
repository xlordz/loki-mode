"""
Confidence-based routing for the Autonomi SDK.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from autonomi.types import ConfidenceScore, ConfidenceTier


@dataclass
class TierConfig:
    """Configuration for a confidence tier."""
    action: str  # "auto", "validate", "review", "escalate"
    model: str   # Preferred model for this tier
    require_approval: bool = False
    quality_gates: List[str] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.quality_gates is None:
            self.quality_gates = []


class ConfidenceRouter:
    """
    Routes tasks based on confidence scores.

    Higher confidence = faster execution, fewer checks.
    Lower confidence = more validation, potentially human review.
    """

    DEFAULT_TIERS = {
        0.90: TierConfig(action="auto", model="haiku"),
        0.60: TierConfig(action="validate", model="sonnet"),
        0.30: TierConfig(action="review", model="sonnet", quality_gates=["lint", "test"]),
        0.00: TierConfig(action="escalate", model="opus", require_approval=True),
    }

    def __init__(
        self,
        tiers: Optional[Dict[float, TierConfig]] = None,
        confidence_calculator: Optional[Callable[[str], ConfidenceScore]] = None,
    ):
        """
        Initialize the router.

        Args:
            tiers: Confidence threshold -> config mapping
            confidence_calculator: Function to calculate confidence
        """
        self.tiers = tiers or self.DEFAULT_TIERS
        self._confidence_calculator = confidence_calculator

    def get_tier_config(self, confidence: float) -> TierConfig:
        """Get config for the given confidence level."""
        sorted_thresholds = sorted(self.tiers.keys(), reverse=True)

        for threshold in sorted_thresholds:
            if confidence >= threshold:
                return self.tiers[threshold]

        # Return lowest tier config
        return self.tiers[min(self.tiers.keys())]

    def calculate_confidence(self, task: str) -> ConfidenceScore:
        """
        Calculate confidence for a task.

        Uses custom calculator if provided, otherwise uses heuristics.
        """
        if self._confidence_calculator:
            return self._confidence_calculator(task)

        # Simple heuristic-based calculation
        task_lower = task.lower()

        # Estimate factors
        requirement_clarity = 0.7
        technical_complexity = 0.3
        historical_success = 0.8  # Assume good history
        scope_size = 0.3

        # Adjust based on keywords
        complexity_keywords = [
            "refactor", "migrate", "architecture", "security",
            "database", "deploy", "production", "integration"
        ]
        simple_keywords = ["fix", "add", "update", "test", "simple", "small"]

        for kw in complexity_keywords:
            if kw in task_lower:
                technical_complexity += 0.15
                requirement_clarity -= 0.1

        for kw in simple_keywords:
            if kw in task_lower:
                technical_complexity -= 0.1
                requirement_clarity += 0.1

        # Clamp values
        requirement_clarity = max(0.1, min(1.0, requirement_clarity))
        technical_complexity = max(0.1, min(1.0, technical_complexity))

        return ConfidenceScore.calculate(
            requirement_clarity=requirement_clarity,
            technical_complexity=technical_complexity,
            historical_success=historical_success,
            scope_size=scope_size,
        )

    def route(self, task: str) -> str:
        """
        Route a task and return the recommended role/agent.

        This is the main routing function for use with Orchestrator.
        """
        confidence = self.calculate_confidence(task)
        config = self.get_tier_config(confidence.overall)

        # Return action as the "role" - can be used for routing
        return config.action

    def get_routing_decision(self, task: str) -> Dict[str, Any]:
        """
        Get full routing decision with all details.
        """
        confidence = self.calculate_confidence(task)
        config = self.get_tier_config(confidence.overall)

        return {
            "confidence": confidence.overall,
            "tier": confidence.tier.value,
            "factors": confidence.factors,
            "action": config.action,
            "model": config.model,
            "require_approval": config.require_approval,
            "quality_gates": config.quality_gates,
        }
