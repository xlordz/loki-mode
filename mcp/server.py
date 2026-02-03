#!/usr/bin/env python3
"""
Loki Mode MCP Server

Exposes Loki Mode capabilities via Model Context Protocol:
- Task queue management
- Memory retrieval
- State management
- Metrics tracking

Usage:
    python -m mcp.server                    # STDIO mode (default)
    python -m mcp.server --transport http   # HTTP mode
"""

import sys
import os
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging to stderr (critical for STDIO transport)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger('loki-mcp')

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    logger.error("MCP SDK not installed. Run: pip install mcp")
    sys.exit(1)

# Initialize FastMCP server
mcp = FastMCP(
    "loki-mode",
    version="5.16.0",
    description="Loki Mode autonomous agent orchestration"
)

# ============================================================
# TOOLS - Functions Claude can call
# ============================================================

@mcp.tool()
async def loki_memory_retrieve(
    query: str,
    task_type: str = "implementation",
    top_k: int = 5
) -> str:
    """
    Retrieve relevant memories for a task using task-aware retrieval.

    Args:
        query: Search query describing what you're looking for
        task_type: Type of task (exploration, implementation, debugging, review, refactoring)
        top_k: Maximum number of results to return

    Returns:
        JSON array of relevant memory entries with summaries
    """
    try:
        from memory.retrieval import MemoryRetrieval
        from memory.storage import MemoryStorage

        base_path = os.path.join(os.getcwd(), '.loki', 'memory')
        if not os.path.exists(base_path):
            return json.dumps({"memories": [], "message": "Memory system not initialized"})

        storage = MemoryStorage(base_path)
        retriever = MemoryRetrieval(storage)

        context = {"goal": query, "task_type": task_type}
        results = retriever.retrieve_task_aware(context, top_k=top_k)

        return json.dumps({
            "memories": results,
            "task_type": task_type,
            "count": len(results)
        }, default=str)
    except Exception as e:
        logger.error(f"Memory retrieval failed: {e}")
        return json.dumps({"error": str(e), "memories": []})


@mcp.tool()
async def loki_memory_store_pattern(
    pattern: str,
    category: str,
    correct_approach: str,
    incorrect_approach: str = "",
    confidence: float = 0.8
) -> str:
    """
    Store a new semantic pattern learned during this session.

    Args:
        pattern: Brief description of the pattern
        category: Category (api, testing, security, performance, architecture, etc.)
        correct_approach: The correct way to handle this situation
        incorrect_approach: What to avoid (optional)
        confidence: Confidence level 0.0-1.0

    Returns:
        Pattern ID if successful
    """
    try:
        from memory.engine import MemoryEngine
        from memory.schemas import SemanticPattern

        base_path = os.path.join(os.getcwd(), '.loki', 'memory')
        engine = MemoryEngine(base_path)
        engine.initialize()

        pattern_obj = SemanticPattern(
            id=f"pattern-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            pattern=pattern,
            category=category,
            conditions=[],
            correct_approach=correct_approach,
            incorrect_approach=incorrect_approach,
            confidence=confidence,
            source_episodes=[],
            usage_count=0,
            last_used=None,
            links=[]
        )

        pattern_id = engine.store_pattern(pattern_obj)
        return json.dumps({"success": True, "pattern_id": pattern_id})
    except Exception as e:
        logger.error(f"Pattern storage failed: {e}")
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def loki_task_queue_list() -> str:
    """
    List all tasks in the Loki Mode task queue.

    Returns:
        JSON array of tasks with status, priority, and description
    """
    try:
        queue_path = os.path.join(os.getcwd(), '.loki', 'state', 'task-queue.json')
        if not os.path.exists(queue_path):
            return json.dumps({"tasks": [], "message": "No task queue found"})

        with open(queue_path, 'r') as f:
            queue = json.load(f)

        return json.dumps(queue, default=str)
    except Exception as e:
        logger.error(f"Task queue list failed: {e}")
        return json.dumps({"error": str(e), "tasks": []})


@mcp.tool()
async def loki_task_queue_add(
    title: str,
    description: str,
    priority: str = "medium",
    phase: str = "development"
) -> str:
    """
    Add a new task to the Loki Mode task queue.

    Args:
        title: Brief task title
        description: Detailed task description
        priority: Priority level (low, medium, high, critical)
        phase: SDLC phase (discovery, architecture, development, testing, deployment)

    Returns:
        Task ID if successful
    """
    try:
        queue_path = os.path.join(os.getcwd(), '.loki', 'state', 'task-queue.json')
        os.makedirs(os.path.dirname(queue_path), exist_ok=True)

        # Load existing queue or create new
        if os.path.exists(queue_path):
            with open(queue_path, 'r') as f:
                queue = json.load(f)
        else:
            queue = {"tasks": [], "version": "1.0"}

        # Create new task
        task_id = f"task-{len(queue['tasks']) + 1:04d}"
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "priority": priority,
            "phase": phase,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

        queue["tasks"].append(task)

        with open(queue_path, 'w') as f:
            json.dump(queue, f, indent=2)

        return json.dumps({"success": True, "task_id": task_id})
    except Exception as e:
        logger.error(f"Task add failed: {e}")
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def loki_task_queue_update(
    task_id: str,
    status: str = None,
    priority: str = None
) -> str:
    """
    Update a task's status or priority.

    Args:
        task_id: ID of the task to update
        status: New status (pending, in_progress, completed, blocked)
        priority: New priority (low, medium, high, critical)

    Returns:
        Updated task if successful
    """
    try:
        queue_path = os.path.join(os.getcwd(), '.loki', 'state', 'task-queue.json')
        if not os.path.exists(queue_path):
            return json.dumps({"success": False, "error": "Task queue not found"})

        with open(queue_path, 'r') as f:
            queue = json.load(f)

        # Find and update task
        for task in queue["tasks"]:
            if task["id"] == task_id:
                if status:
                    task["status"] = status
                if priority:
                    task["priority"] = priority
                task["updated_at"] = datetime.utcnow().isoformat() + "Z"

                with open(queue_path, 'w') as f:
                    json.dump(queue, f, indent=2)

                return json.dumps({"success": True, "task": task})

        return json.dumps({"success": False, "error": f"Task {task_id} not found"})
    except Exception as e:
        logger.error(f"Task update failed: {e}")
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def loki_state_get() -> str:
    """
    Get the current Loki Mode state including phase, metrics, and status.

    Returns:
        JSON object with current state information
    """
    try:
        state_path = os.path.join(os.getcwd(), '.loki', 'state', 'autonomy-state.json')
        continuity_path = os.path.join(os.getcwd(), '.loki', 'CONTINUITY.md')

        state = {
            "initialized": os.path.exists(os.path.join(os.getcwd(), '.loki')),
            "autonomy_state": None,
            "continuity_exists": os.path.exists(continuity_path),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        if os.path.exists(state_path):
            with open(state_path, 'r') as f:
                state["autonomy_state"] = json.load(f)

        # Get memory stats
        try:
            from memory.engine import MemoryEngine
            engine = MemoryEngine(os.path.join(os.getcwd(), '.loki', 'memory'))
            state["memory_stats"] = engine.get_stats()
        except Exception:
            state["memory_stats"] = None

        return json.dumps(state, default=str)
    except Exception as e:
        logger.error(f"State get failed: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
async def loki_metrics_efficiency() -> str:
    """
    Get efficiency metrics for the current session.

    Returns:
        JSON object with token usage, tool calls, and efficiency ratios
    """
    try:
        metrics_path = os.path.join(os.getcwd(), '.loki', 'metrics', 'tool-usage.jsonl')

        if not os.path.exists(metrics_path):
            return json.dumps({"message": "No metrics collected yet", "tool_calls": 0})

        tool_counts = {}
        total_calls = 0

        with open(metrics_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    tool = entry.get("tool", "unknown")
                    tool_counts[tool] = tool_counts.get(tool, 0) + 1
                    total_calls += 1
                except json.JSONDecodeError:
                    continue

        return json.dumps({
            "total_tool_calls": total_calls,
            "tool_breakdown": tool_counts,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
    except Exception as e:
        logger.error(f"Metrics get failed: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
async def loki_consolidate_memory(since_hours: int = 24) -> str:
    """
    Run memory consolidation to extract patterns from recent episodes.

    Args:
        since_hours: Process episodes from the last N hours

    Returns:
        Consolidation results with patterns created/merged
    """
    try:
        from memory.consolidation import ConsolidationPipeline
        from memory.storage import MemoryStorage

        base_path = os.path.join(os.getcwd(), '.loki', 'memory')
        storage = MemoryStorage(base_path)
        pipeline = ConsolidationPipeline(storage)

        result = pipeline.consolidate(since_hours=since_hours)
        return json.dumps(result, default=str)
    except Exception as e:
        logger.error(f"Consolidation failed: {e}")
        return json.dumps({"error": str(e)})


# ============================================================
# RESOURCES - Data that can be read
# ============================================================

@mcp.resource("loki://state/continuity")
async def get_continuity() -> str:
    """Get the current CONTINUITY.md content"""
    continuity_path = os.path.join(os.getcwd(), '.loki', 'CONTINUITY.md')
    if os.path.exists(continuity_path):
        with open(continuity_path, 'r') as f:
            return f.read()
    return "# CONTINUITY.md not found"


@mcp.resource("loki://memory/index")
async def get_memory_index() -> str:
    """Get the memory index (Layer 1)"""
    index_path = os.path.join(os.getcwd(), '.loki', 'memory', 'index.json')
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            return f.read()
    return json.dumps({"topics": [], "message": "Index not initialized"})


@mcp.resource("loki://queue/pending")
async def get_pending_tasks() -> str:
    """Get all pending tasks from the queue"""
    queue_path = os.path.join(os.getcwd(), '.loki', 'state', 'task-queue.json')
    if os.path.exists(queue_path):
        with open(queue_path, 'r') as f:
            queue = json.load(f)
            pending = [t for t in queue.get("tasks", []) if t.get("status") == "pending"]
            return json.dumps({"pending_tasks": pending, "count": len(pending)})
    return json.dumps({"pending_tasks": [], "count": 0})


# ============================================================
# PROMPTS - Pre-built prompt templates
# ============================================================

@mcp.prompt()
async def loki_start(prd_path: str = "") -> str:
    """Initialize a Loki Mode session with optional PRD"""
    return f"""You are now operating in Loki Mode - autonomous agent orchestration.

RARV Cycle: Reason -> Act -> Reflect -> Verify

Current PRD: {prd_path or 'None specified'}

Steps:
1. Analyze the PRD and extract requirements
2. Break down into actionable tasks
3. Execute tasks following RARV cycle
4. Verify completion against acceptance criteria

Use loki_* tools to manage tasks and memory.
Begin by analyzing the requirements."""


@mcp.prompt()
async def loki_phase_report() -> str:
    """Generate a status report for the current phase"""
    return """Generate a comprehensive status report including:

1. Current SDLC Phase
2. Tasks Completed / In Progress / Pending
3. Quality Gate Status
4. Key Decisions Made
5. Blockers or Risks
6. Next Steps

Use loki_state_get and loki_task_queue_list to gather data."""


# ============================================================
# MAIN
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Loki Mode MCP Server')
    parser.add_argument('--transport', choices=['stdio', 'http'], default='stdio',
                       help='Transport mechanism (default: stdio)')
    parser.add_argument('--port', type=int, default=8421,
                       help='Port for HTTP transport (default: 8421)')
    args = parser.parse_args()

    logger.info(f"Starting Loki Mode MCP server (transport: {args.transport})")

    if args.transport == 'http':
        mcp.run(transport='http', port=args.port)
    else:
        mcp.run(transport='stdio')


if __name__ == '__main__':
    main()
