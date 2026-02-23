# Smoke Test Report: v5.52.1
**Date**: 2026-02-22
**Tester**: Claude Code (Opus 4.6)
**API Key Available**: NO

## Pre-Flight Check

- `loki --version`: Loki Mode v5.52.1
- `loki doctor`: All PASS except bash version WARN (v3.2.57 < 4.0 recommended)
  - Node.js v25.2.1, Python 3.14.2, jq 1.7, git 2.50.1, curl 8.7.1
  - Claude CLI v2.1.50, Codex CLI v0.98.0, Gemini CLI v0.27.3
  - All 3 skill installs detected (Claude, Codex, Gemini)

## PRD Smoke Tests

SKIPPED: No ANTHROPIC_API_KEY available. B2-B4 tests (todo-app, saas-dashboard, microservices-platform) not executed.

## Infrastructure Tests

| Test | Result | Details |
|---|---|---|
| loki --version | Loki Mode v5.52.1 | OK |
| loki doctor | PASS (1 WARN) | bash v3.2.57 < 4.0 recommended |
| Dashboard /health | `{"status":"healthy","service":"loki-dashboard"}` | OK |
| Dashboard /api/status | working | status=stopped, version=5.52.1, db_connected=true |
| OpenAPI spec | 113 paths | Title: Loki Mode Dashboard API |
| API v2 /tenants | working | Returns empty array `[]` (no tenants created) |
| A2A Agent Card | NOT FOUND | `{"detail":"Not Found"}` at /.well-known/agent.json |
| MCP tools | 15 | All 15 loki_* tools found via AST parse (mcp pip package not installed) |
| Node module imports | 8/9 passing | FAIL: src/integrations/linear (module not found) |
| Python module imports | 6/6 passing | knowledge_graph, sycophancy, calibration, classifier, composer, event_bus |
| Python SDK | OK | AutonomiClient imports successfully |
| TypeScript SDK | OK | 5 exports |
| npm test | 38/38 passing | All checks passed, duration 71ms |
| pytest | 631/631 passing | 3 Pydantic deprecation warnings (class-based config) |
| Shell tests (hooks) | 10/10 passing | Fork bomb detection confirmed |
| Helm lint | PASS | 1 chart linted, 0 failed (icon recommended warning) |

## MCP Tools Found (15)

- loki_agent_metrics
- loki_checkpoint_restore
- loki_consolidate_memory
- loki_memory_retrieve
- loki_memory_store_pattern
- loki_metrics_efficiency
- loki_phase_report
- loki_project_status
- loki_quality_report
- loki_start
- loki_start_project
- loki_state_get
- loki_task_queue_add
- loki_task_queue_list
- loki_task_queue_update

Note: MCP tools counted via AST parsing because `mcp` pip package is not installed in system Python.

## Issues Found

### Minor Issues (non-blocking)
1. **A2A Agent Card missing**: `/.well-known/agent.json` returns 404. Route may not be registered.
2. **Linear integration missing**: `src/integrations/linear` module cannot be found (other integrations jira/slack/teams work).
3. **Pydantic deprecation warnings**: 3 warnings about class-based `config` in `dashboard/server.py` and `collab/api.py`. Should migrate to `ConfigDict`.
4. **MCP pip dependency**: `mcp` pip package not installed; tools exist but runtime MCP server requires it.
5. **Bash version**: macOS ships bash 3.2.57; loki doctor recommends >= 4.0.

### No Critical Issues
All core functionality (dashboard, API, SDKs, test suites, module imports) works correctly.

## Recommended Demo Path

1. Start with `loki --version` and `loki doctor` to show system readiness
2. Show dashboard at localhost:57374 -- /health, /api/status, and OpenAPI spec (113 endpoints) are reliable
3. Demonstrate module ecosystem: 38 Node tests, 631 Python tests, 10 shell tests all passing
4. Show MCP tools (15 tools) and SDK imports (Python + TypeScript)
5. For PRD execution demo, ensure ANTHROPIC_API_KEY is set beforehand
6. Avoid demonstrating: A2A agent card (404), Linear integration (missing)
