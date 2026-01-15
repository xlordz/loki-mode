"""
Telemetry system for the Autonomi SDK.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class EventType(str, Enum):
    """Types of telemetry events."""
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    GUARDRAIL_CHECK = "guardrail_check"
    HANDOFF = "handoff"
    ERROR = "error"
    MEMORY_STORE = "memory_store"
    MEMORY_RETRIEVE = "memory_retrieve"


@dataclass
class TelemetryEvent:
    """A telemetry event."""
    type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    agent_name: str = ""
    session_id: str = ""
    task_id: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[int] = None
    parent_id: Optional[str] = None
    span_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "data": self.data,
            "duration_ms": self.duration_ms,
            "parent_id": self.parent_id,
            "span_id": self.span_id,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class Telemetry:
    """
    Telemetry system for observability.

    Supports:
    - Event logging
    - Trace visualization
    - Export to OpenTelemetry, JSON Lines, etc.
    """

    def __init__(
        self,
        enabled: bool = True,
        backend: str = "memory",
        export_path: Optional[str] = None,
        service_name: str = "autonomi",
        on_event: Optional[Callable[[TelemetryEvent], None]] = None,
    ):
        """
        Initialize telemetry.

        Args:
            enabled: Whether telemetry is enabled
            backend: Backend type ("memory", "file", "otlp")
            export_path: Path for file export
            service_name: Service name for traces
            on_event: Callback for each event
        """
        self.enabled = enabled
        self.backend = backend
        self.export_path = export_path
        self.service_name = service_name
        self.on_event = on_event

        self._events: List[TelemetryEvent] = []
        self._spans: Dict[str, TelemetryEvent] = {}
        self._file_handle: Optional[Any] = None

        if backend == "file" and export_path:
            os.makedirs(os.path.dirname(export_path) or ".", exist_ok=True)
            self._file_handle = open(export_path, "a")

    def emit(self, event: TelemetryEvent) -> None:
        """Emit a telemetry event."""
        if not self.enabled:
            return

        self._events.append(event)

        if self.on_event:
            self.on_event(event)

        if self.backend == "file" and self._file_handle:
            self._file_handle.write(event.to_json() + "\n")
            self._file_handle.flush()

    def start_span(
        self,
        name: str,
        event_type: EventType,
        agent_name: str = "",
        session_id: str = "",
        task_id: str = "",
        parent_id: Optional[str] = None,
        **data: Any,
    ) -> str:
        """
        Start a new span.

        Returns span_id for ending the span later.
        """
        import uuid
        span_id = str(uuid.uuid4())[:8]

        event = TelemetryEvent(
            type=event_type,
            agent_name=agent_name,
            session_id=session_id,
            task_id=task_id,
            data={"name": name, **data},
            parent_id=parent_id,
            span_id=span_id,
        )

        self._spans[span_id] = event
        self.emit(event)

        return span_id

    def end_span(
        self,
        span_id: str,
        success: bool = True,
        **data: Any,
    ) -> None:
        """End a span and record duration."""
        if span_id not in self._spans:
            return

        start_event = self._spans.pop(span_id)
        duration = int(
            (datetime.now() - start_event.timestamp).total_seconds() * 1000
        )

        end_event = TelemetryEvent(
            type=start_event.type,
            timestamp=datetime.now(),
            agent_name=start_event.agent_name,
            session_id=start_event.session_id,
            task_id=start_event.task_id,
            data={
                **start_event.data,
                "success": success,
                "end": True,
                **data,
            },
            duration_ms=duration,
            parent_id=start_event.parent_id,
            span_id=span_id,
        )

        self.emit(end_event)

    def log_agent_start(
        self,
        agent_name: str,
        task: str,
        session_id: str = "",
        task_id: str = "",
    ) -> str:
        """Log agent execution start."""
        return self.start_span(
            name=f"agent:{agent_name}",
            event_type=EventType.AGENT_START,
            agent_name=agent_name,
            session_id=session_id,
            task_id=task_id,
            task=task,
        )

    def log_agent_end(
        self,
        span_id: str,
        success: bool,
        output: str = "",
        cost: float = 0.0,
        tokens: int = 0,
    ) -> None:
        """Log agent execution end."""
        self.end_span(
            span_id,
            success=success,
            output=output[:500],  # Truncate
            cost=cost,
            tokens=tokens,
        )

    def log_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_name: str = "",
        parent_span: Optional[str] = None,
    ) -> str:
        """Log a tool call."""
        return self.start_span(
            name=f"tool:{tool_name}",
            event_type=EventType.TOOL_CALL,
            agent_name=agent_name,
            parent_id=parent_span,
            tool_name=tool_name,
            arguments=arguments,
        )

    def log_tool_result(
        self,
        span_id: str,
        success: bool,
        result: Any = None,
        error: Optional[str] = None,
    ) -> None:
        """Log tool result."""
        self.end_span(
            span_id,
            success=success,
            result=str(result)[:500] if result else None,
            error=error,
        )

    def log_error(
        self,
        error: str,
        agent_name: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an error."""
        event = TelemetryEvent(
            type=EventType.ERROR,
            agent_name=agent_name,
            data={"error": error, "context": context or {}},
        )
        self.emit(event)

    def get_events(
        self,
        event_type: Optional[EventType] = None,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[TelemetryEvent]:
        """Get filtered events."""
        events = self._events

        if event_type:
            events = [e for e in events if e.type == event_type]

        if agent_name:
            events = [e for e in events if e.agent_name == agent_name]

        if session_id:
            events = [e for e in events if e.session_id == session_id]

        return events[-limit:]

    def get_agent_stats(self, agent_name: str) -> Dict[str, Any]:
        """Get statistics for an agent."""
        events = [e for e in self._events if e.agent_name == agent_name]

        agent_events = [
            e for e in events
            if e.type in (EventType.AGENT_START, EventType.AGENT_END)
        ]
        tool_events = [
            e for e in events
            if e.type in (EventType.TOOL_CALL, EventType.TOOL_RESULT)
        ]

        total_duration = sum(
            e.duration_ms or 0
            for e in agent_events
            if e.data.get("end")
        )

        success_count = sum(
            1 for e in agent_events
            if e.data.get("end") and e.data.get("success")
        )
        total_count = sum(1 for e in agent_events if e.data.get("end"))

        return {
            "agent_name": agent_name,
            "total_invocations": total_count,
            "success_rate": success_count / total_count if total_count else 0,
            "total_duration_ms": total_duration,
            "avg_duration_ms": total_duration / total_count if total_count else 0,
            "tool_calls": len([e for e in tool_events if e.type == EventType.TOOL_CALL]),
        }

    def export(self, format: str = "jsonl") -> Any:
        """Export events."""
        if format == "jsonl":
            return "\n".join(e.to_json() for e in self._events)
        elif format == "json":
            return [e.to_dict() for e in self._events]
        else:
            raise ValueError(f"Unknown format: {format}")

    def clear(self) -> None:
        """Clear all events."""
        self._events = []
        self._spans = {}

    def close(self) -> None:
        """Close telemetry."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
