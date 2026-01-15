"""
Ollama provider for the Autonomi SDK.

Supports local models via Ollama with tool use and streaming.
"""

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from autonomi.providers.base import Provider, ProviderConfig, ProviderResponse
from autonomi.types import Message, Role, ToolCall, Usage
from autonomi.tool import Tool


class OllamaProvider(Provider):
    """Ollama local model provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def base_url(self) -> str:
        return self.config.base_url or "http://localhost:11434"

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-load the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.config.timeout,
            )
        return self._client

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert messages to Ollama format."""
        ollama_messages: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.role == Role.TOOL:
                # Tool results as user messages
                ollama_messages.append({
                    "role": "user",
                    "content": f"Tool result: {msg.content}",
                })
            else:
                role = msg.role.value
                if role == "system":
                    role = "system"
                elif role == "assistant":
                    role = "assistant"
                else:
                    role = "user"

                ollama_messages.append({
                    "role": role,
                    "content": msg.content,
                })

        return ollama_messages

    def _convert_tools(self, tools: List[Tool]) -> List[Dict[str, Any]]:
        """Convert tools to Ollama format (OpenAI-compatible)."""
        return [t.to_openai_schema() for t in tools]

    def _parse_tool_calls(self, message: Dict[str, Any]) -> List[ToolCall]:
        """Parse tool calls from Ollama response."""
        tool_calls: List[ToolCall] = []

        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                try:
                    arguments = tc.get("function", {}).get("arguments", {})
                    if isinstance(arguments, str):
                        arguments = json.loads(arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}

                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=tc.get("function", {}).get("name", ""),
                    arguments=arguments,
                ))

        return tool_calls

    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Generate a completion using Ollama."""
        ollama_messages = self._convert_messages(messages)

        request_body: Dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            },
        }

        if tools:
            request_body["tools"] = self._convert_tools(tools)

        response = await self.client.post("/api/chat", json=request_body)
        response.raise_for_status()
        data = response.json()

        message = data.get("message", {})
        content = message.get("content", "")

        # Parse tool calls
        tool_calls = self._parse_tool_calls(message)

        # Build usage (Ollama provides token counts)
        usage = None
        if "prompt_eval_count" in data or "eval_count" in data:
            input_tokens = data.get("prompt_eval_count", 0)
            output_tokens = data.get("eval_count", 0)
            usage = Usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )

        return ProviderResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            stop_reason=data.get("done_reason"),
            model=data.get("model", self.config.model),
            raw_response=data,
        )

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a completion using Ollama."""
        ollama_messages = self._convert_messages(messages)

        request_body: Dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            },
        }

        if tools:
            request_body["tools"] = self._convert_tools(tools)

        async with self.client.stream("POST", "/api/chat", json=request_body) as response:
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
                    except json.JSONDecodeError:
                        continue

    def calculate_cost(self, usage: Usage) -> float:
        """Ollama is free (local)."""
        return 0.0

    async def list_models(self) -> List[str]:
        """List available models in Ollama."""
        response = await self.client.get("/api/tags")
        response.raise_for_status()
        data = response.json()
        return [m["name"] for m in data.get("models", [])]

    async def pull_model(self, model: str) -> None:
        """Pull a model from Ollama library."""
        await self.client.post("/api/pull", json={"name": model})
