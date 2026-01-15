"""
Agent primitive for the Autonomi SDK.

An Agent wraps an LLM with instructions, tools, and constraints.

Example:
    from autonomi import Agent, tool

    @tool
    def search(query: str) -> str:
        '''Search the web.'''
        return f"Results for: {query}"

    agent = Agent(
        name="researcher",
        instructions="You are a research assistant.",
        tools=[search]
    )

    result = await agent.execute("Find information about AI agents")
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from autonomi.types import (
    Message,
    Role,
    ToolCall,
    Usage,
    ExecutionContext,
    ConfidenceScore,
    ConfidenceTier,
)
from autonomi.tool import Tool, ToolResult
from autonomi.providers.base import Provider, ProviderConfig, ProviderResponse


@dataclass
class AgentConfig:
    """Configuration for an Agent."""
    name: str
    instructions: str = ""
    model: str = "claude-sonnet-4-20250514"
    provider: Optional[Provider] = None
    tools: List[Tool] = field(default_factory=list)
    constitution: List[str] = field(default_factory=list)
    max_tokens: int = 4096
    temperature: float = 0.7
    max_turns: int = 10
    max_tool_calls: int = 50
    confidence_threshold: float = 0.0


@dataclass
class AgentResult:
    """Result of an agent execution."""
    success: bool
    output: str
    messages: List[Message] = field(default_factory=list)
    tool_calls_made: List[Dict[str, Any]] = field(default_factory=list)
    usage: Optional[Usage] = None
    cost: float = 0.0
    duration_ms: int = 0
    confidence: Optional[ConfidenceScore] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success_result(
        cls,
        output: str,
        messages: List[Message],
        **kwargs: Any
    ) -> "AgentResult":
        """Create a successful result."""
        return cls(success=True, output=output, messages=messages, **kwargs)

    @classmethod
    def failure(cls, error: str, **kwargs: Any) -> "AgentResult":
        """Create a failed result."""
        return cls(success=False, output="", error=error, **kwargs)


class Agent:
    """
    An Agent wraps an LLM with instructions, tools, and constraints.

    Agents can:
    - Execute tasks using natural language
    - Call tools to interact with external systems
    - Hand off to other agents
    - Self-critique using constitutional principles
    """

    def __init__(
        self,
        name: str,
        instructions: str = "",
        model: str = "claude-sonnet-4-20250514",
        provider: Optional[Provider] = None,
        tools: Optional[List[Union[Tool, Callable[..., Any]]]] = None,
        constitution: Optional[List[str]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        max_turns: int = 10,
        max_tool_calls: int = 50,
        confidence_threshold: float = 0.0,
        **kwargs: Any,
    ):
        """
        Initialize an Agent.

        Args:
            name: Unique identifier for the agent
            instructions: System prompt / behavioral instructions
            model: Model identifier (e.g., "claude-sonnet-4-5")
            provider: LLM provider instance
            tools: List of tools the agent can use
            constitution: Principles for self-critique
            max_tokens: Maximum response tokens
            temperature: Sampling temperature
            max_turns: Maximum conversation turns
            max_tool_calls: Maximum tool calls per execution
            confidence_threshold: Minimum confidence to execute
        """
        self.name = name
        self.instructions = instructions
        self.model = model
        self._provider = provider
        self.constitution = constitution or []
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_turns = max_turns
        self.max_tool_calls = max_tool_calls
        self.confidence_threshold = confidence_threshold

        # Convert callables to Tools
        self.tools: List[Tool] = []
        if tools:
            for t in tools:
                if isinstance(t, Tool):
                    self.tools.append(t)
                elif callable(t):
                    from autonomi.tool import tool as tool_decorator
                    self.tools.append(tool_decorator(t))

        # Tool lookup by name
        self._tools_by_name: Dict[str, Tool] = {t.name: t for t in self.tools}

        # Extra config
        self._extra = kwargs

    @property
    def provider(self) -> Provider:
        """Get or create the provider."""
        if self._provider is None:
            # Default to Anthropic if no provider specified
            import os
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            self._provider = Provider.anthropic(api_key=api_key, model=self.model)
        return self._provider

    def _build_system_prompt(self) -> str:
        """Build the full system prompt including instructions and constitution."""
        parts = []

        if self.instructions:
            parts.append(self.instructions)

        if self.constitution:
            parts.append("\n\nPrinciples you must follow:")
            for i, principle in enumerate(self.constitution, 1):
                parts.append(f"{i}. {principle}")

        if self.tools:
            parts.append("\n\nYou have access to the following tools:")
            for tool in self.tools:
                parts.append(f"- {tool.name}: {tool.description}")

        return "\n".join(parts)

    async def execute(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        messages: Optional[List[Message]] = None,
        **kwargs: Any,
    ) -> AgentResult:
        """
        Execute a task.

        Args:
            prompt: The task to execute
            context: Additional context (variables, files, etc.)
            messages: Existing conversation history
            **kwargs: Additional options

        Returns:
            AgentResult with output and metadata
        """
        start_time = datetime.now()
        context = context or {}

        # Build initial messages
        conversation: List[Message] = []

        # System message
        system_prompt = self._build_system_prompt()
        if context:
            system_prompt += f"\n\nContext:\n{json.dumps(context, indent=2)}"
        conversation.append(Message(role=Role.SYSTEM, content=system_prompt))

        # Add existing messages
        if messages:
            conversation.extend(messages)

        # Add user prompt
        conversation.append(Message(role=Role.USER, content=prompt))

        # Track usage and tool calls
        total_usage = Usage(input_tokens=0, output_tokens=0, total_tokens=0)
        tool_calls_made: List[Dict[str, Any]] = []
        tool_call_count = 0

        try:
            # Agentic loop
            for turn in range(self.max_turns):
                # Get completion
                response = await self.provider.complete(
                    messages=conversation,
                    tools=self.tools if self.tools else None,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    **kwargs,
                )

                # Track usage
                if response.usage:
                    total_usage.input_tokens += response.usage.input_tokens
                    total_usage.output_tokens += response.usage.output_tokens
                    total_usage.total_tokens += response.usage.total_tokens

                # Handle tool calls
                if response.has_tool_calls:
                    # Add assistant message with tool calls
                    conversation.append(Message(
                        role=Role.ASSISTANT,
                        content=response.content,
                        tool_calls=[{
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            }
                        } for tc in response.tool_calls],
                    ))

                    # Execute each tool call
                    for tc in response.tool_calls:
                        if tool_call_count >= self.max_tool_calls:
                            break

                        tool = self._tools_by_name.get(tc.name)
                        if tool:
                            result = await tool.execute(**tc.arguments)
                            tool_calls_made.append({
                                "name": tc.name,
                                "arguments": tc.arguments,
                                "result": result.output if result.success else result.error,
                                "success": result.success,
                            })

                            # Add tool result to conversation
                            conversation.append(Message(
                                role=Role.TOOL,
                                content=str(result.output) if result.success else f"Error: {result.error}",
                                tool_call_id=tc.id,
                            ))
                        else:
                            # Unknown tool
                            conversation.append(Message(
                                role=Role.TOOL,
                                content=f"Error: Unknown tool '{tc.name}'",
                                tool_call_id=tc.id,
                            ))

                        tool_call_count += 1

                    # Continue loop to get next response
                    continue

                # No tool calls - we have the final response
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

                return AgentResult.success_result(
                    output=response.content,
                    messages=conversation,
                    tool_calls_made=tool_calls_made,
                    usage=total_usage,
                    cost=self.provider.calculate_cost(total_usage),
                    duration_ms=duration_ms,
                )

            # Max turns reached
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return AgentResult.failure(
                error=f"Max turns ({self.max_turns}) reached",
                messages=conversation,
                tool_calls_made=tool_calls_made,
                usage=total_usage,
                cost=self.provider.calculate_cost(total_usage),
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return AgentResult.failure(
                error=str(e),
                messages=conversation,
                tool_calls_made=tool_calls_made,
                usage=total_usage,
                duration_ms=duration_ms,
            )

    def execute_sync(self, prompt: str, **kwargs: Any) -> AgentResult:
        """
        Execute a task synchronously.

        Convenience method for scripts and simple use cases.
        """
        return asyncio.run(self.execute(prompt, **kwargs))

    async def stream(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Stream a response.

        Note: Streaming doesn't support tool use in this implementation.
        For tool use, use execute() instead.
        """
        context = context or {}

        # Build messages
        conversation: List[Message] = []

        system_prompt = self._build_system_prompt()
        if context:
            system_prompt += f"\n\nContext:\n{json.dumps(context, indent=2)}"
        conversation.append(Message(role=Role.SYSTEM, content=system_prompt))
        conversation.append(Message(role=Role.USER, content=prompt))

        async for chunk in self.provider.stream(
            messages=conversation,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            **kwargs,
        ):
            yield chunk

    async def handoff(
        self,
        to_agent: "Agent",
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        reason: str = "",
    ) -> AgentResult:
        """
        Hand off execution to another agent.

        Args:
            to_agent: The agent to hand off to
            prompt: The task to hand off
            context: Context to pass
            reason: Reason for handoff

        Returns:
            Result from the receiving agent
        """
        handoff_context = {
            "handoff_from": self.name,
            "handoff_reason": reason,
            **(context or {}),
        }

        return await to_agent.execute(prompt, context=handoff_context)

    # Builder pattern methods
    def with_instructions(self, instructions: str) -> "Agent":
        """Set instructions (builder pattern)."""
        self.instructions = instructions
        return self

    def with_model(self, model: str) -> "Agent":
        """Set model (builder pattern)."""
        self.model = model
        return self

    def with_tools(self, *tools: Union[Tool, Callable[..., Any]]) -> "Agent":
        """Add tools (builder pattern)."""
        for t in tools:
            if isinstance(t, Tool):
                self.tools.append(t)
                self._tools_by_name[t.name] = t
            elif callable(t):
                from autonomi.tool import tool as tool_decorator
                tool_obj = tool_decorator(t)
                self.tools.append(tool_obj)
                self._tools_by_name[tool_obj.name] = tool_obj
        return self

    def with_constitution(self, *principles: str) -> "Agent":
        """Add constitutional principles (builder pattern)."""
        self.constitution.extend(principles)
        return self

    def build(self) -> "Agent":
        """Finalize the agent (builder pattern)."""
        return self

    def __repr__(self) -> str:
        return f"Agent(name='{self.name}', model='{self.model}', tools={len(self.tools)})"
