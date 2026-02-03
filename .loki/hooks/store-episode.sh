#!/bin/bash
# Loki Mode SessionEnd Hook - Episode Storage
# Stores session as episodic memory

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))")
CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))")
TRANSCRIPT_PATH=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))")

# Store episode if memory system available
if [ -d "$CWD/memory" ]; then
    python3 << EOF
import sys
sys.path.insert(0, '$CWD')
try:
    from memory.engine import MemoryEngine
    from memory.schemas import EpisodeTrace
    from datetime import datetime
    import json

    engine = MemoryEngine('$CWD/.loki/memory')

    # Create minimal episode from session
    episode = EpisodeTrace(
        id='$SESSION_ID',
        task_id='session-$SESSION_ID',
        timestamp=datetime.utcnow(),
        duration_seconds=0,
        agent='loki-mode',
        phase='session',
        goal='Session completed',
        action_log=[],
        outcome='completed',
        errors_encountered=[],
        artifacts_produced=[],
        git_commit=None,
        tokens_used=0,
        files_read=[],
        files_modified=[]
    )
    engine.store_episode(episode)
    print('Episode stored: $SESSION_ID')
except Exception as e:
    print(f'Episode storage failed: {e}', file=sys.stderr)
EOF
fi

exit 0
