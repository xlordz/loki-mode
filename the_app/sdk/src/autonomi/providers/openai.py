"""
OpenAI provider for the Autonomi SDK.

Supports GPT models with function calling and streaming.
"""

import json
from typing import Any, AsyncIterator, Dict, List, Optional

from autonomi.providers.base import Provider, ProviderConfig, ProviderResponse
from autonomi.types import Message, Role, ToolCall, Usage
from autonomi.tool import Tool

# Pricing per 1K tokens (as of 2025)
OPENAI_PRICING = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "o1": {"input": 0.015, "output": 0.06},
    "o1-mini": {"input": 0.003, "output": 0.012},
}


class OpenAIProvider(Provider):
    """OpenAI GPT provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client: Optional[Any] = None

    @property
    def name(self) -> str:
        return "openai"

    @property
    def client(self) -> Any:
        """Lazy-load the OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "openai package not installed. "
                    "Install with: pip install openai"
                )

            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
            )
        return self._client

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert messages to OpenAI format."""
        openai_messages: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.role == Role.TOOL:
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })
            elif msg.role == Role.ASSISTANT and msg.tool_calls:
                openai_messages.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": msg.tool_calls,
                })
            else:
                openai_messages.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })

        return openai_messages

    def _convert_tools(self, tools: List[Tool]) -> List[Dict[str, Any]]:
        """Convert tools to OpenAI format."""
        return [t.to_openai_schema() for t in tools]

    def _parse_tool_calls(self, tool_calls: Optional[List[Any]]) -> List[ToolCall]:
        """Parse tool calls from OpenAI response."""
        if not tool_calls:
            return []

        parsed: List[ToolCall] = []
        for tc in tool_calls:
            try:
                arguments = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, AttributeError):
                arguments = {}

            parsed.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=arguments,
            ))
        return parsed

    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Generate a completion using GPT."""
        openai_messages = self._convert_messages(messages)

        request_kwargs: Dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
        }

        if tools:
            request_kwargs["tools"] = self._convert_tools(tools)

        response = await self.client.chat.completions.create(**request_kwargs)
        choice = response.choices[0]

        # Extract content
        content = choice.message.content or ""

        # Parse tool calls
        tool_calls = self._parse_tool_calls(choice.message.tool_calls)

        # Build usage
        usage = None
        if response.usage:
            usage = Usage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

        return ProviderResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            stop_reason=choice.finish_reason,
            model=response.model,
            raw_response=response,
        )

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a completion using GPT."""
        openai_messages = self._convert_messages(messages)

        request_kwargs: Dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "stream": True,
        }

        if tools:
            request_kwargs["tools"] = self._convert_tools(tools)

        stream = await self.client.chat.completions.create(**request_kwargs)

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def calculate_cost(self, usage: Usage) -> float:
        """Calculate cost using OpenAI pricing."""
        model = self.config.model
        pricing = OPENAI_PRICING.get(model, OPENAI_PRICING.get("gpt-4o", {}))

        input_cost = (usage.input_tokens / 1000) * pricing.get("input", 0.005)
        output_cost = (usage.output_tokens / 1000) * pricing.get("output", 0.015)

        return input_cost + output_cost
