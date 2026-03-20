# .claude/hooks/block_server_commands.py
import json, sys

payload = json.load(sys.stdin)
cmd = payload.get("tool_input", {}).get("command", "")

blocked = ["uvicorn", "npm run dev", "npm start"]
if any(b in cmd for b in blocked):
    print(json.dumps({
        "decision": "block",
        "reason": "Server management is handled by the developer. Never start or stop servers."
    }))
else:
    print(json.dumps({"decision": "approve"}))
