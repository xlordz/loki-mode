#!/bin/bash
# Loki Mode SessionStart Hook
# Loads memory context and initializes session state

set -euo pipefail

# Read input JSON from stdin
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))")
CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))")

# Initialize .loki directory if needed
mkdir -p "$CWD/.loki/state" "$CWD/.loki/memory" "$CWD/.loki/logs"

# Load memory context
MEMORY_CONTEXT=""
if [ -f "$CWD/.loki/memory/index.json" ]; then
    MEMORY_CONTEXT=$(python3 -c "
import json
import sys
sys.path.insert(0, '$CWD')
try:
    from memory.engine import MemoryEngine
    engine = MemoryEngine('$CWD/.loki/memory')
    stats = engine.get_stats()
    print(json.dumps({'memories_loaded': stats}))
except Exception as e:
    print(json.dumps({'error': str(e)}))
" 2>/dev/null || echo '{}')
fi

# Output session initialization info
cat << EOF
{
  "continue": true,
  "systemMessage": "Loki Mode initialized. Session: $SESSION_ID. Memory context loaded."
}
EOF

exit 0
