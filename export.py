"""Push anonymous per-session results to a GitHub repository."""
import base64
import json
import time
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from logic import GameState
    
from logic import save_local_result

def push_result(state, secrets):
    """Push to GitHub; fallback to local. Returns True if ANY save succeeded."""
    
    # 1. Try GitHub first
    github_success = False
    try:
        github = secrets["github"]
        token = github["token"]
        repo = github["repo"]
        branch = github.get("branch", "main")
        folder = github.get("folder", "results")
        
        payload = {
            "schema_version": 1,
            "session_id": state.session_id,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "score": state.score,
            "trials": state.trials,
            "correct": state.correct,
            "accuracy_pct": round(state.correct / state.trials * 100) if state.trials else 0,
            "lives_left": state.lives,
            "rounds": state.rounds,
        }

        content = base64.b64encode(json.dumps(payload, indent=2).encode()).decode()
        resp = requests.put(
            f"https://api.github.com/repos/{repo}/contents/{folder}/{state.session_id}.json",
            json={"message": f"session {state.session_id[:8]}", "content": content, "branch": branch},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=10,
        )
        
        if resp.status_code in (200, 201):
            github_success = True
            
    except Exception:
        pass

    # 2. If GitHub failed, save locally
    if not github_success:
        save_local_result(state)
        return True
    return True
