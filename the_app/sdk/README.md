# Autonomi SDK

Quality-first multi-agent framework with built-in safety.

## Installation

```bash
pip install autonomi-sdk
```

## Quick Start

```python
from autonomi import Agent, tool

@tool
def search(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"

agent = Agent(
    name="researcher",
    instructions="You are a research assistant.",
    tools=[search]
)

result = await agent.execute("Find information about AI agents")
print(result.output)
```

## Features

- **6 Core Primitives**: Agent, Tool, Guardrail, Memory, Orchestrator, Session
- **Multi-Provider**: Anthropic, OpenAI, Google, Ollama, and any OpenAI-compatible API
- **Built-in Safety**: Input/output guardrails, secret scanning, injection detection
- **Quality Gates**: Configurable validation pipelines
- **Memory System**: Persistent learning across sessions
- **Cost Tracking**: Budget controls and usage monitoring
- **Human-in-the-Loop**: Interrupt and approval workflows

## Core Primitives

### Agent

```python
from autonomi import Agent

agent = Agent(
    name="backend",
    instructions="You are a backend engineer.",
    model="claude-sonnet-4-20250514",
    tools=[read_file, write_file],
    constitution=[
        "Never commit secrets to code",
        "Always write tests for new functions",
    ]
)

result = await agent.execute("Add a /health endpoint")
```

### Tool

```python
from autonomi import tool

@tool
def read_file(path: str) -> str:
    """Read contents of a file.

    Args:
        path: Absolute path to the file

    Returns:
        File contents as string
    """
    with open(path) as f:
        return f.read()
```

### Guardrails

```python
from autonomi import Agent, InjectionDetector, SecretScanner

agent = Agent(
    name="secure",
    input_guardrails=[InjectionDetector()],
    output_guardrails=[SecretScanner()],
)
```

### Orchestrator

```python
from autonomi import Orchestrator, OrchestratorMode

# Router pattern - select agent based on task
orchestrator = Orchestrator(mode=OrchestratorMode.ROUTER)
orchestrator.add_agent(frontend_agent, role="frontend")
orchestrator.add_agent(backend_agent, role="backend")

# Pipeline pattern - sequential execution
pipeline = Orchestrator(mode=OrchestratorMode.PIPELINE)
pipeline.add_agent(planner, stage=1)
pipeline.add_agent(implementer, stage=2)
pipeline.add_agent(reviewer, stage=3)
```

### Memory

```python
from autonomi import Agent, Memory

memory = Memory(backend="sqlite", path=".autonomi/memory.db")

agent = Agent(
    name="learning",
    memory=memory,
)
```

### Human-in-the-Loop

```python
from autonomi import interrupt, Command

approval = await interrupt(
    "Delete all user data?",
    channels=["slack", "console"]
)

if approval.approved:
    return Command(goto="delete")
else:
    return Command(goto="cancel")
```

## Providers

```python
from autonomi import Provider

# Anthropic (Claude)
provider = Provider.anthropic(api_key="sk-ant-...")

# OpenAI (GPT)
provider = Provider.openai(api_key="sk-...")

# Ollama (local)
provider = Provider.ollama(model="llama3.2")
```

## Cost Tracking

```python
from autonomi import CostTracker, Budget

budget = Budget(
    per_task=5.00,
    per_session=50.00,
    per_day=100.00,
    on_exceed="PAUSE"
)

tracker = CostTracker(budget=budget)
```

## License

Apache 2.0
