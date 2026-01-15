"""
Human-in-the-loop interrupts for the Autonomi SDK.

Enables pausing execution for human approval, input, or decisions.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class InterruptType(str, Enum):
    """Types of interrupts."""
    APPROVAL = "approval"     # Yes/no decision
    INPUT = "input"           # Free-form input
    CHOICE = "choice"         # Multiple choice
    REVIEW = "review"         # Review and modify


@dataclass
class Approval:
    """Result of an approval interrupt."""
    approved: bool
    reason: str = ""
    modified_value: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    approver: str = ""


@dataclass
class Command:
    """Command to control execution flow after interrupt."""
    goto: Optional[str] = None  # Jump to named step
    abort: bool = False         # Stop execution
    retry: bool = False         # Retry current step
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def continue_execution(cls, **data: Any) -> "Command":
        """Continue normal execution."""
        return cls(data=data)

    @classmethod
    def jump_to(cls, step: str, **data: Any) -> "Command":
        """Jump to a named step."""
        return cls(goto=step, data=data)

    @classmethod
    def stop(cls, reason: str = "") -> "Command":
        """Stop execution."""
        return cls(abort=True, data={"reason": reason})

    @classmethod
    def retry_step(cls) -> "Command":
        """Retry the current step."""
        return cls(retry=True)


# Global interrupt handler registry
_interrupt_handlers: Dict[str, Callable[..., Approval]] = {}


def register_interrupt_handler(
    channel: str,
    handler: Callable[..., Approval],
) -> None:
    """
    Register a handler for a notification channel.

    Args:
        channel: Channel name (e.g., "console", "slack", "email")
        handler: Function that handles the interrupt
    """
    _interrupt_handlers[channel] = handler


def get_interrupt_handler(channel: str) -> Optional[Callable[..., Approval]]:
    """Get handler for a channel."""
    return _interrupt_handlers.get(channel)


async def interrupt(
    message: str,
    interrupt_type: InterruptType = InterruptType.APPROVAL,
    channels: Optional[List[str]] = None,
    timeout: Optional[float] = None,
    default_response: Optional[Approval] = None,
    choices: Optional[List[str]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Approval:
    """
    Pause execution and wait for human response.

    Args:
        message: Message to display to human
        interrupt_type: Type of interrupt
        channels: Notification channels (default: ["console"])
        timeout: Timeout in seconds (None = wait forever)
        default_response: Response if timeout
        choices: Options for CHOICE type
        context: Additional context

    Returns:
        Approval with human's response
    """
    channels = channels or ["console"]
    context = context or {}

    # Find first available handler
    handler = None
    for channel in channels:
        handler = get_interrupt_handler(channel)
        if handler:
            break

    if handler is None:
        # Fall back to console handler
        handler = _console_handler

    # Create interrupt context
    interrupt_context = {
        "message": message,
        "type": interrupt_type.value,
        "choices": choices,
        **context,
    }

    # Call handler with timeout
    if timeout:
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await asyncio.wait_for(
                    handler(interrupt_context),
                    timeout=timeout,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, handler, interrupt_context
                    ),
                    timeout=timeout,
                )
        except asyncio.TimeoutError:
            if default_response:
                return default_response
            return Approval(
                approved=False,
                reason="Timeout waiting for response",
            )
    else:
        if asyncio.iscoroutinefunction(handler):
            result = await handler(interrupt_context)
        else:
            result = handler(interrupt_context)

    return result


def _console_handler(context: Dict[str, Any]) -> Approval:
    """Default console interrupt handler."""
    message = context.get("message", "Approval required")
    interrupt_type = context.get("type", "approval")
    choices = context.get("choices")

    print(f"\n{'='*50}")
    print(f"INTERRUPT: {message}")
    print(f"{'='*50}")

    if interrupt_type == "approval":
        while True:
            response = input("Approve? [y/n]: ").strip().lower()
            if response in ("y", "yes"):
                return Approval(approved=True)
            elif response in ("n", "no"):
                reason = input("Reason (optional): ").strip()
                return Approval(approved=False, reason=reason)
            print("Please enter 'y' or 'n'")

    elif interrupt_type == "input":
        value = input("Enter value: ").strip()
        return Approval(approved=True, modified_value=value)

    elif interrupt_type == "choice" and choices:
        print("Options:")
        for i, choice in enumerate(choices, 1):
            print(f"  {i}. {choice}")

        while True:
            try:
                idx = int(input("Select option number: ").strip())
                if 1 <= idx <= len(choices):
                    return Approval(
                        approved=True,
                        modified_value=choices[idx - 1],
                    )
            except ValueError:
                pass
            print(f"Please enter a number 1-{len(choices)}")

    elif interrupt_type == "review":
        print("Current value:", context.get("current_value", "N/A"))
        modify = input("Modify? [y/n]: ").strip().lower()
        if modify in ("y", "yes"):
            new_value = input("Enter new value: ").strip()
            return Approval(approved=True, modified_value=new_value)
        return Approval(approved=True)

    # Default
    return Approval(approved=True)


# Register default console handler
register_interrupt_handler("console", _console_handler)


class InterruptManager:
    """
    Manages interrupts for a workflow.

    Provides a way to define interrupt points and handle them.
    """

    def __init__(
        self,
        default_channels: Optional[List[str]] = None,
        default_timeout: Optional[float] = None,
    ):
        self.default_channels = default_channels or ["console"]
        self.default_timeout = default_timeout
        self._pending_interrupts: Dict[str, asyncio.Future[Approval]] = {}

    async def request_approval(
        self,
        message: str,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Approval:
        """Request approval from human."""
        return await interrupt(
            message,
            interrupt_type=InterruptType.APPROVAL,
            channels=self.default_channels,
            timeout=timeout or self.default_timeout,
            **kwargs,
        )

    async def request_input(
        self,
        message: str,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Approval:
        """Request input from human."""
        return await interrupt(
            message,
            interrupt_type=InterruptType.INPUT,
            channels=self.default_channels,
            timeout=timeout or self.default_timeout,
            **kwargs,
        )

    async def request_choice(
        self,
        message: str,
        choices: List[str],
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Approval:
        """Request choice from human."""
        return await interrupt(
            message,
            interrupt_type=InterruptType.CHOICE,
            channels=self.default_channels,
            timeout=timeout or self.default_timeout,
            choices=choices,
            **kwargs,
        )
