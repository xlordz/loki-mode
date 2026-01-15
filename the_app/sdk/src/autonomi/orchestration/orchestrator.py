"""
Orchestrator for coordinating multiple agents.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from autonomi.agent import Agent, AgentResult
from autonomi.types import ConfidenceScore, Usage


class OrchestratorMode(str, Enum):
    """Orchestration modes."""
    ROUTER = "router"      # Single agent selected based on task
    PARALLEL = "parallel"  # Multiple agents work simultaneously
    PIPELINE = "pipeline"  # Agents execute in sequence
    SUPERVISOR = "supervisor"  # Manager agent delegates to workers


@dataclass
class OrchestratorResult:
    """Result from orchestrator execution."""
    success: bool
    output: str
    agent_results: List[AgentResult] = field(default_factory=list)
    agents_used: List[str] = field(default_factory=list)
    total_usage: Optional[Usage] = None
    total_cost: float = 0.0
    duration_ms: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRole:
    """An agent with its role in the orchestrator."""
    agent: Agent
    role: str
    stage: int = 0  # For pipeline mode


class Orchestrator:
    """
    Coordinates multiple agents for complex tasks.

    Supports four orchestration patterns:
    - Router: Select single agent based on task
    - Parallel: Multiple agents work simultaneously
    - Pipeline: Sequential execution through stages
    - Supervisor: Manager agent delegates to workers
    """

    def __init__(
        self,
        mode: OrchestratorMode = OrchestratorMode.ROUTER,
        max_concurrent: int = 4,
        timeout: float = 300.0,
    ):
        """
        Initialize the orchestrator.

        Args:
            mode: Orchestration mode
            max_concurrent: Max concurrent agents (for parallel mode)
            timeout: Timeout in seconds
        """
        self.mode = mode
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self._agents: List[AgentRole] = []
        self._routing_strategy: Optional[Callable[[str], str]] = None

    def add_agent(
        self,
        agent: Agent,
        role: str = "",
        stage: int = 0,
    ) -> "Orchestrator":
        """
        Add an agent to the orchestrator.

        Args:
            agent: The agent to add
            role: Role identifier (for routing)
            stage: Pipeline stage (for pipeline mode)
        """
        self._agents.append(AgentRole(
            agent=agent,
            role=role or agent.name,
            stage=stage,
        ))
        return self

    def set_routing_strategy(
        self,
        strategy: Callable[[str], str],
    ) -> "Orchestrator":
        """
        Set the routing strategy for router mode.

        Args:
            strategy: Function that takes task and returns role
        """
        self._routing_strategy = strategy
        return self

    async def run(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> OrchestratorResult:
        """
        Execute a task using the configured orchestration pattern.
        """
        start_time = datetime.now()

        try:
            if self.mode == OrchestratorMode.ROUTER:
                result = await self._run_router(task, context, **kwargs)
            elif self.mode == OrchestratorMode.PARALLEL:
                result = await self._run_parallel(task, context, **kwargs)
            elif self.mode == OrchestratorMode.PIPELINE:
                result = await self._run_pipeline(task, context, **kwargs)
            elif self.mode == OrchestratorMode.SUPERVISOR:
                result = await self._run_supervisor(task, context, **kwargs)
            else:
                raise ValueError(f"Unknown mode: {self.mode}")

            result.duration_ms = int(
                (datetime.now() - start_time).total_seconds() * 1000
            )
            return result

        except Exception as e:
            return OrchestratorResult(
                success=False,
                output="",
                error=str(e),
                duration_ms=int(
                    (datetime.now() - start_time).total_seconds() * 1000
                ),
            )

    async def _run_router(
        self,
        task: str,
        context: Optional[Dict[str, Any]],
        **kwargs: Any,
    ) -> OrchestratorResult:
        """Route task to single agent."""
        if not self._agents:
            return OrchestratorResult(
                success=False, output="", error="No agents configured"
            )

        # Determine which agent to use
        selected_role: Optional[str] = None
        if self._routing_strategy:
            selected_role = self._routing_strategy(task)

        # Find agent by role
        agent_role: Optional[AgentRole] = None
        if selected_role:
            for ar in self._agents:
                if ar.role == selected_role:
                    agent_role = ar
                    break

        # Fall back to first agent
        if agent_role is None:
            agent_role = self._agents[0]

        # Execute
        result = await agent_role.agent.execute(task, context=context, **kwargs)

        return OrchestratorResult(
            success=result.success,
            output=result.output,
            agent_results=[result],
            agents_used=[agent_role.agent.name],
            total_usage=result.usage,
            total_cost=result.cost,
            error=result.error,
        )

    async def _run_parallel(
        self,
        task: str,
        context: Optional[Dict[str, Any]],
        **kwargs: Any,
    ) -> OrchestratorResult:
        """Run multiple agents in parallel."""
        if not self._agents:
            return OrchestratorResult(
                success=False, output="", error="No agents configured"
            )

        # Create tasks for all agents
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def run_with_semaphore(ar: AgentRole) -> AgentResult:
            async with semaphore:
                return await ar.agent.execute(task, context=context, **kwargs)

        tasks = [run_with_semaphore(ar) for ar in self._agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        agent_results: List[AgentResult] = []
        agents_used: List[str] = []
        outputs: List[str] = []
        total_cost = 0.0
        total_usage = Usage(input_tokens=0, output_tokens=0, total_tokens=0)

        for i, result in enumerate(results):
            agent_name = self._agents[i].agent.name
            agents_used.append(agent_name)

            if isinstance(result, Exception):
                agent_results.append(AgentResult.failure(str(result)))
            else:
                agent_results.append(result)
                if result.success:
                    outputs.append(f"[{agent_name}]: {result.output}")
                total_cost += result.cost
                if result.usage:
                    total_usage.input_tokens += result.usage.input_tokens
                    total_usage.output_tokens += result.usage.output_tokens
                    total_usage.total_tokens += result.usage.total_tokens

        # Combine outputs
        combined_output = "\n\n".join(outputs)
        success = any(r.success for r in agent_results if isinstance(r, AgentResult))

        return OrchestratorResult(
            success=success,
            output=combined_output,
            agent_results=agent_results,
            agents_used=agents_used,
            total_usage=total_usage,
            total_cost=total_cost,
        )

    async def _run_pipeline(
        self,
        task: str,
        context: Optional[Dict[str, Any]],
        **kwargs: Any,
    ) -> OrchestratorResult:
        """Run agents in sequence (pipeline)."""
        if not self._agents:
            return OrchestratorResult(
                success=False, output="", error="No agents configured"
            )

        # Sort by stage
        sorted_agents = sorted(self._agents, key=lambda x: x.stage)

        agent_results: List[AgentResult] = []
        agents_used: List[str] = []
        current_context = context or {}
        current_task = task
        total_cost = 0.0
        total_usage = Usage(input_tokens=0, output_tokens=0, total_tokens=0)

        for ar in sorted_agents:
            agents_used.append(ar.agent.name)

            # Pass previous output as context
            if agent_results:
                current_context["previous_output"] = agent_results[-1].output
                current_context["previous_agent"] = agents_used[-2] if len(agents_used) > 1 else None

            result = await ar.agent.execute(
                current_task, context=current_context, **kwargs
            )
            agent_results.append(result)

            total_cost += result.cost
            if result.usage:
                total_usage.input_tokens += result.usage.input_tokens
                total_usage.output_tokens += result.usage.output_tokens
                total_usage.total_tokens += result.usage.total_tokens

            # Stop on failure
            if not result.success:
                return OrchestratorResult(
                    success=False,
                    output=result.output,
                    agent_results=agent_results,
                    agents_used=agents_used,
                    total_usage=total_usage,
                    total_cost=total_cost,
                    error=result.error,
                )

        # Return final output
        final_result = agent_results[-1] if agent_results else None
        return OrchestratorResult(
            success=True,
            output=final_result.output if final_result else "",
            agent_results=agent_results,
            agents_used=agents_used,
            total_usage=total_usage,
            total_cost=total_cost,
        )

    async def _run_supervisor(
        self,
        task: str,
        context: Optional[Dict[str, Any]],
        **kwargs: Any,
    ) -> OrchestratorResult:
        """
        Run with supervisor pattern.

        First agent is the supervisor, others are workers.
        Supervisor decides which workers to invoke.
        """
        if len(self._agents) < 2:
            return OrchestratorResult(
                success=False,
                output="",
                error="Supervisor mode requires at least 2 agents",
            )

        supervisor = self._agents[0]
        workers = self._agents[1:]

        # Build worker descriptions for supervisor
        worker_info = "\n".join(
            f"- {w.role}: {w.agent.name} - {w.agent.instructions[:100]}..."
            for w in workers
        )

        supervisor_context = {
            **(context or {}),
            "available_workers": worker_info,
            "instruction": (
                "You are a supervisor. Analyze the task and decide which "
                "worker(s) to delegate to. Respond with the worker roles "
                "to use and the subtasks for each."
            ),
        }

        # Get supervisor decision
        result = await supervisor.agent.execute(
            task, context=supervisor_context, **kwargs
        )

        # For now, just return the supervisor's output
        # A full implementation would parse the response and delegate to workers
        return OrchestratorResult(
            success=result.success,
            output=result.output,
            agent_results=[result],
            agents_used=[supervisor.agent.name],
            total_usage=result.usage,
            total_cost=result.cost,
            error=result.error,
        )
