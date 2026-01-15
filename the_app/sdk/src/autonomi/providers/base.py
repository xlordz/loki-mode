"""
Base provider interface for the Autonomi SDK.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from autonomi.types import Message, ToolCall, Usage
from autonomi.tool import Tool


@dataclass
class ProviderConfig:
    """Configuration for a provider."""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 120.0
    max_retries: int = 3
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderResponse:
    """Response from a provider."""
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    usage: Optional[Usage] = None
    stop_reason: Optional[str] = None
    model: str = ""
    raw_response: Optional[Any] = None

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0


class Provider(ABC):
    """
    Abstract base class for LLM providers.

    Implementations should handle:
    - Authentication
    - Message formatting
    - Tool schema conversion
    - Streaming
    - Error handling and retries
    """

    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @abstractmethod
    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """
        Generate a completion for the given messages.

        Args:
            messages: Conversation history
            tools: Available tools
            **kwargs: Provider-specific options

        Returns:
            ProviderResponse with content and optional tool calls
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Stream a completion for the given messages.

        Args:
            messages: Conversation history
            tools: Available tools
            **kwargs: Provider-specific options

        Yields:
            String chunks as they arrive
        """
        pass

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        This is a rough estimate; providers may have different tokenizers.
        """
        # Rough estimate: ~4 characters per token
        return len(text) // 4

    def calculate_cost(self, usage: Usage) -> float:
        """
        Calculate cost for the given usage.

        Override in subclasses with actual pricing.
        """
        return usage.cost_estimate

    @classmethod
    def anthropic(cls, api_key: str, model: str = "claude-sonnet-4-20250514", **kwargs: Any) -> "Provider":
        """Create an Anthropic provider."""
        from autonomi.providers.anthropic import AnthropicProvider
        config = ProviderConfig(api_key=api_key, model=model, **kwargs)
        return AnthropicProvider(config)

    @classmethod
    def openai(cls, api_key: str, model: str = "gpt-4o", **kwargs: Any) -> "Provider":
        """Create an OpenAI provider."""
        from autonomi.providers.openai import OpenAIProvider
        config = ProviderConfig(api_key=api_key, model=model, **kwargs)
        return OpenAIProvider(config)

    @classmethod
    def ollama(cls, model: str = "llama3.2", base_url: str = "http://localhost:11434", **kwargs: Any) -> "Provider":
        """Create an Ollama provider."""
        from autonomi.providers.ollama import OllamaProvider
        config = ProviderConfig(model=model, base_url=base_url, **kwargs)
        return OllamaProvider(config)
