# Loki Mode - OpenClaw Integration

Run Loki Mode autonomous SDLC sessions from any OpenClaw channel (Slack, Discord, Teams, web).

## Installation

1. Install Loki Mode CLI:
   ```bash
   npm install -g loki-mode
   # or
   brew install asklokesh/tap/loki-mode
   ```

2. Copy skill to OpenClaw workspace:
   ```bash
   cp -r integrations/openclaw/ ~/.openclaw/workspace/skills/loki-mode/
   ```

3. Configure API keys in the OpenClaw environment (ANTHROPIC_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY).

## Usage

From any connected channel, the agent will invoke Loki Mode when:
- You ask it to "build" or "implement" something from a PRD
- You say "loki mode" with a project reference
- You provide requirements for autonomous development

## Architecture

```
Channel (Slack/Discord/Web)
    |
    v
OpenClaw Gateway --> Agent routes to loki-mode skill
    |
    v
loki start --bg --yes <prd>  (background process)
    |
    v
Poll loop: loki status --json (every 30s)
    |
    v
Progress messages back to channel
```

## Helper Scripts

Two helper scripts are provided in `scripts/` for structured status polling and formatting:

- `poll-status.sh [workdir]` -- Calls `loki status --json` and enriches the output with budget and council data from `.loki/` flat files. Returns a single JSON object.
- `format-progress.sh` -- Reads the JSON output from `poll-status.sh` via stdin and produces a human-readable multi-line progress message suitable for channel posting.

Example pipeline:
```bash
./scripts/poll-status.sh /path/to/project | ./scripts/format-progress.sh
```

## Configuration

| Env Var | Description | Default |
|---------|-------------|---------|
| LOKI_PROVIDER | AI provider (claude/codex/gemini) | claude |
| LOKI_BUDGET_LIMIT | Cost limit in USD | unlimited |
| LOKI_MAX_PARALLEL_AGENTS | Max concurrent agents | 10 |
| LOKI_COMPLEXITY | Force complexity tier (simple/standard/complex) | auto |
| LOKI_DASHBOARD_PORT | Dashboard HTTP port | 57374 |

## Status JSON Schema

The enriched JSON from `poll-status.sh` contains:

| Field | Type | Description |
|-------|------|-------------|
| status | string | inactive, running, paused, stopped, completed, unknown |
| phase | string/null | BOOTSTRAP, DISCOVERY, ARCHITECTURE, DEVELOPMENT, QA, DEPLOYMENT |
| iteration | number | Current iteration count |
| tasks_completed | number | Tasks finished successfully |
| tasks_total | number | Total tasks discovered |
| tasks_failed | number | Tasks that errored |
| tasks_pending | number | Tasks not yet started |
| elapsed_minutes | number | Minutes since session start |
| provider | string | Active AI provider |
| version | string | Loki Mode version |
| pid | number/null | Session process ID |
| dashboard_url | string/null | Dashboard URL if running |
| budget_used | number/null | USD spent so far |
| budget_limit | number/null | USD budget cap |
| council_verdict | string/null | Completion council decision |
