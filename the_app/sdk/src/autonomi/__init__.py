"""
Autonomi SDK - Quality-first multi-agent framework with built-in safety.

The complete API in 6 primitives:

    from autonomi import (
        Agent,       # LLM with instructions, tools, and constraints
        Tool,        # Callable function with schema
        Guardrail,   # Input/output validation
        Memory,      # Persistent learning system
        Orchestrator,  # Multi-agent coordination
        Session,     # Conversation and state management
    )

Quick Start:

    from autonomi import Agent, tool

    @tool
    def greet(name: str) -> str:
        '''Greet a person by name.'''
        return f"Hello, {name}!"

    agent = Agent(
        name="greeter",
        instructions="You are a friendly assistant.",
        tools=[greet]
    )

    result = await agent.execute("Say hello to Alice")
"""

__version__ = "0.1.0"

# Core primitives
from autonomi.agent import Agent, AgentResult, AgentConfig
from autonomi.tool import tool, Tool, ToolResult, ToolError
from autonomi.guardrails import (
    Guardrail,
    InputGuardrail,
    OutputGuardrail,
    GuardrailResult,
    GuardrailAction,
    InjectionDetector,
    SecretScanner,
    PIIRedactor,
)
from autonomi.memory import Memory, MemoryConfig, MemoryEvent
from autonomi.orchestration import (
    Orchestrator,
    OrchestratorResult,
    OrchestratorMode,
    ConfidenceRouter,
)
from autonomi.session import Session, SessionConfig

# Providers
from autonomi.providers import (
    Provider,
    ProviderConfig,
    AnthropicProvider,
    OpenAIProvider,
    OllamaProvider,
)

# Human-in-the-loop
from autonomi.interrupt import interrupt, Command, Approval

# Cost tracking
from autonomi.telemetry import CostTracker, Budget, Telemetry

# Convenience re-exports
from autonomi.types import Message, Role, ConfidenceTier

__all__ = [
    # Version
    "__version__",
    # Core primitives
    "Agent",
    "AgentResult",
    "AgentConfig",
    "Tool",
    "tool",
    "ToolResult",
    "ToolError",
    "Guardrail",
    "InputGuardrail",
    "OutputGuardrail",
    "GuardrailResult",
    "GuardrailAction",
    "InjectionDetector",
    "SecretScanner",
    "PIIRedactor",
    "Memory",
    "MemoryConfig",
    "MemoryEvent",
    "Orchestrator",
    "OrchestratorResult",
    "OrchestratorMode",
    "ConfidenceRouter",
    "Session",
    "SessionConfig",
    # Providers
    "Provider",
    "ProviderConfig",
    "AnthropicProvider",
    "OpenAIProvider",
    "OllamaProvider",
    # Human-in-the-loop
    "interrupt",
    "Command",
    "Approval",
    # Cost tracking
    "CostTracker",
    "Budget",
    "Telemetry",
    # Types
    "Message",
    "Role",
    "ConfidenceTier",
]
