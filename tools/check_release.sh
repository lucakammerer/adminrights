#!/bin/sh
# Release check (I8, docs/RULES.md §9): package audit, unit tests, agent.json. Green = exit 0.
set -e
cd "$(dirname "$0")/.."
python3 tools/audit_package.py $(ls bench/.ci/logs/*.log 2>/dev/null)
uv run --project agent --no-sync python -m unittest discover -s tests
python3 - <<'PY'
import json
spec = json.load(open("agent/agent.json"))
assert spec["setup"] and spec["run"], "agent.json needs setup and run"
assert set(spec["models"]) <= {"qwen", "clef"}, f"unknown models {spec['models']}"
assert isinstance(spec["browsers"], int) and 1 <= spec["browsers"] <= 4, "browsers must be 1-4"
print("agent.json ok")
PY
echo "release check green"
