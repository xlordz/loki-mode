#!/bin/bash
# Loki Mode PostToolUse Hook - Metrics Tracking
# Tracks tool usage for efficiency metrics (async)

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))")
CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))")

# Log to metrics file
METRICS_DIR="$CWD/.loki/metrics"
mkdir -p "$METRICS_DIR"

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "{\"timestamp\":\"$TIMESTAMP\",\"tool\":\"$TOOL_NAME\",\"event\":\"PostToolUse\"}" >> "$METRICS_DIR/tool-usage.jsonl"

exit 0
