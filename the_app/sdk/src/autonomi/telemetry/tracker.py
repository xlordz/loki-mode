"""
Cost tracking for the Autonomi SDK.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from autonomi.types import Usage


class BudgetAction(str, Enum):
    """Actions when budget is exceeded."""
    LOG = "log"      # Continue, log warning
    PAUSE = "pause"  # Stop, wait for approval
    HALT = "halt"    # Stop, return error


class BudgetExceeded(Exception):
    """Raised when budget is exceeded."""

    def __init__(
        self,
        message: str,
        budget_type: str,
        current: float,
        limit: float,
    ):
        self.budget_type = budget_type
        self.current = current
        self.limit = limit
        super().__init__(message)


@dataclass
class Budget:
    """Budget configuration."""
    per_request: Optional[float] = None    # Max per LLM call
    per_task: Optional[float] = None       # Max per task
    per_session: Optional[float] = None    # Max per session
    per_day: Optional[float] = None        # Max per day
    on_exceed: BudgetAction = BudgetAction.PAUSE
    warning_threshold: float = 0.8         # Warn at 80%

    def check(
        self,
        request_cost: float = 0.0,
        task_cost: float = 0.0,
        session_cost: float = 0.0,
        daily_cost: float = 0.0,
    ) -> Optional[str]:
        """
        Check if any budget is exceeded.

        Returns warning message if near limit, raises if exceeded.
        """
        checks = [
            ("per_request", self.per_request, request_cost),
            ("per_task", self.per_task, task_cost),
            ("per_session", self.per_session, session_cost),
            ("per_day", self.per_day, daily_cost),
        ]

        for budget_type, limit, current in checks:
            if limit is None:
                continue

            if current >= limit:
                if self.on_exceed == BudgetAction.HALT:
                    raise BudgetExceeded(
                        f"Budget exceeded: {budget_type} ${current:.2f} >= ${limit:.2f}",
                        budget_type,
                        current,
                        limit,
                    )
                elif self.on_exceed == BudgetAction.PAUSE:
                    raise BudgetExceeded(
                        f"Budget exceeded (paused): {budget_type} ${current:.2f} >= ${limit:.2f}",
                        budget_type,
                        current,
                        limit,
                    )
                else:
                    return f"WARNING: Budget exceeded: {budget_type} ${current:.2f} >= ${limit:.2f}"

            elif current >= limit * self.warning_threshold:
                return f"WARNING: Approaching budget limit: {budget_type} ${current:.2f} / ${limit:.2f}"

        return None


@dataclass
class CostRecord:
    """Record of a cost event."""
    timestamp: datetime
    cost: float
    usage: Usage
    agent_name: str
    model: str
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class CostTracker:
    """
    Tracks costs across requests, tasks, sessions, and time.
    """

    def __init__(
        self,
        budget: Optional[Budget] = None,
        on_warning: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize cost tracker.

        Args:
            budget: Budget configuration
            on_warning: Callback for budget warnings
        """
        self.budget = budget or Budget()
        self.on_warning = on_warning or (lambda msg: print(msg))

        self._records: List[CostRecord] = []
        self._task_costs: Dict[str, float] = {}
        self._session_costs: Dict[str, float] = {}
        self._daily_costs: Dict[date, float] = {}

        # Current context
        self._current_task_id: Optional[str] = None
        self._current_session_id: Optional[str] = None

    @property
    def total_cost(self) -> float:
        """Total cost across all records."""
        return sum(r.cost for r in self._records)

    @property
    def last_cost(self) -> float:
        """Cost of last request."""
        if self._records:
            return self._records[-1].cost
        return 0.0

    @property
    def session_cost(self) -> float:
        """Cost of current session."""
        if self._current_session_id:
            return self._session_costs.get(self._current_session_id, 0.0)
        return self.total_cost

    @property
    def task_cost(self) -> float:
        """Cost of current task."""
        if self._current_task_id:
            return self._task_costs.get(self._current_task_id, 0.0)
        return self.last_cost

    @property
    def daily_cost(self) -> float:
        """Cost for today."""
        today = date.today()
        return self._daily_costs.get(today, 0.0)

    def set_context(
        self,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Set current task and session context."""
        self._current_task_id = task_id
        self._current_session_id = session_id

    def record(
        self,
        cost: float,
        usage: Usage,
        agent_name: str,
        model: str,
        **metadata: Any,
    ) -> None:
        """
        Record a cost event.

        Args:
            cost: Cost in USD
            usage: Token usage
            agent_name: Name of agent
            model: Model used
            **metadata: Additional metadata
        """
        # Check budget before recording
        warning = self.budget.check(
            request_cost=cost,
            task_cost=self.task_cost + cost,
            session_cost=self.session_cost + cost,
            daily_cost=self.daily_cost + cost,
        )
        if warning:
            self.on_warning(warning)

        # Create record
        record = CostRecord(
            timestamp=datetime.now(),
            cost=cost,
            usage=usage,
            agent_name=agent_name,
            model=model,
            task_id=self._current_task_id,
            session_id=self._current_session_id,
            metadata=metadata,
        )
        self._records.append(record)

        # Update aggregates
        if self._current_task_id:
            self._task_costs[self._current_task_id] = (
                self._task_costs.get(self._current_task_id, 0.0) + cost
            )

        if self._current_session_id:
            self._session_costs[self._current_session_id] = (
                self._session_costs.get(self._current_session_id, 0.0) + cost
            )

        today = date.today()
        self._daily_costs[today] = self._daily_costs.get(today, 0.0) + cost

    def get_stats(self) -> Dict[str, Any]:
        """Get cost statistics."""
        if not self._records:
            return {
                "total_cost": 0.0,
                "total_requests": 0,
                "total_tokens": 0,
            }

        total_tokens = sum(r.usage.total_tokens for r in self._records)
        total_input = sum(r.usage.input_tokens for r in self._records)
        total_output = sum(r.usage.output_tokens for r in self._records)

        by_agent: Dict[str, float] = {}
        by_model: Dict[str, float] = {}
        for r in self._records:
            by_agent[r.agent_name] = by_agent.get(r.agent_name, 0.0) + r.cost
            by_model[r.model] = by_model.get(r.model, 0.0) + r.cost

        return {
            "total_cost": self.total_cost,
            "total_requests": len(self._records),
            "total_tokens": total_tokens,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "session_cost": self.session_cost,
            "task_cost": self.task_cost,
            "daily_cost": self.daily_cost,
            "by_agent": by_agent,
            "by_model": by_model,
        }

    def export(self, format: str = "json") -> Any:
        """Export cost records."""
        if format == "json":
            return [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "cost": r.cost,
                    "usage": {
                        "input_tokens": r.usage.input_tokens,
                        "output_tokens": r.usage.output_tokens,
                        "total_tokens": r.usage.total_tokens,
                    },
                    "agent_name": r.agent_name,
                    "model": r.model,
                    "task_id": r.task_id,
                    "session_id": r.session_id,
                }
                for r in self._records
            ]
        else:
            raise ValueError(f"Unknown format: {format}")

    def reset(self) -> None:
        """Reset all tracking."""
        self._records = []
        self._task_costs = {}
        self._session_costs = {}
        self._daily_costs = {}
        self._current_task_id = None
        self._current_session_id = None
