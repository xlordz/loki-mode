"""
Anthropic provider for the Autonomi SDK.

Supports Claude models with tool use, streaming, and extended thinking.
"""

import json
from typing import Any, AsyncIterator, Dict, List, Optional

from autonomi.providers.base import Provider, ProviderConfig, ProviderResponse
from autonomi.types import Message, Role, ToolCall, Usage
from autonomi.tool import Tool

# Pricing per 1K tokens (as of 2025)
ANTHROPIC_PRICING = {
    "claude-opus-4-5-20251101": {"input": 0.015, "output": 0.075},
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-haiku-3-5-20241022": {"input": 0.0008, "output": 0.004},
    # Aliases
    "claude-3-opus": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
}


class AnthropicProvider(Provider):
    """Anthropic Claude provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client: Optional[Any] = None

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def client(self) -> Any:
        """Lazy-load the Anthropic client."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. "
                    "Install with: pip install anthropic"
                )

            self._client = AsyncAnthropic(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
            )
        return self._client

    def _convert_messages(self, messages: List[Message]) -> tuple[str, List[Dict[str, Any]]]:
        """Convert messages to Anthropic format, extracting system prompt."""
        system_prompt = ""
        anthropic_messages: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.role == Role.SYSTEM:
                system_prompt = msg.content
            elif msg.role == Role.TOOL:
                # Tool results in Anthropic format
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }],
                })
            else:
                role = "user" if msg.role == Role.USER else "assistant"
                anthropic_messages.append({
                    "role": role,
                    "content": msg.content,
                })

        return system_prompt, anthropic_messages

    def _convert_tools(self, tools: List[Tool]) -> List[Dict[str, Any]]:
        """Convert tools to Anthropic format."""
        return [t.to_anthropic_schema() for t in tools]

    def _parse_tool_calls(self, content: List[Any]) -> List[ToolCall]:
        """Parse tool calls from Anthropic response."""
        tool_calls: List[ToolCall] = []
        for block in content:
            if hasattr(block, "type") and block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))
        return tool_calls

    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Generate a completion using Claude."""
        system_prompt, anthropic_messages = self._convert_messages(messages)

        request_kwargs: Dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": anthropic_messages,
        }

        if system_prompt:
            request_kwargs["system"] = system_prompt

        if tools:
            request_kwargs["tools"] = self._convert_tools(tools)

        # Add temperature if not using extended thinking
        if "temperature" not in kwargs.get("extra", {}):
            request_kwargs["temperature"] = kwargs.get("temperature", self.config.temperature)

        response = await self.client.messages.create(**request_kwargs)

        # Extract content
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        # Parse tool calls
        tool_calls = self._parse_tool_calls(response.content)

        # Build usage
        usage = Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
        )

        return ProviderResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            stop_reason=response.stop_reason,
            model=response.model,
            raw_response=response,
        )

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a completion using Claude."""
        system_prompt, anthropic_messages = self._convert_messages(messages)

        request_kwargs: Dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": anthropic_messages,
        }

        if system_prompt:
            request_kwargs["system"] = system_prompt

        if tools:
            request_kwargs["tools"] = self._convert_tools(tools)

        request_kwargs["temperature"] = kwargs.get("temperature", self.config.temperature)

        async with self.client.messages.stream(**request_kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    def calculate_cost(self, usage: Usage) -> float:
        """Calculate cost using Anthropic pricing."""
        model = self.config.model
        pricing = ANTHROPIC_PRICING.get(model, ANTHROPIC_PRICING.get("claude-3-sonnet", {}))

        input_cost = (usage.input_tokens / 1000) * pricing.get("input", 0.003)
        output_cost = (usage.output_tokens / 1000) * pricing.get("output", 0.015)

        return input_cost + output_cost
