#!/bin/sh
# One local dry run against the scouting sites, scored per field against eval/expected.json (I7).
# Needs `atira models proxy` in another terminal. Stops before the submission (DRY_RUN=1).
set -e
cd "$(dirname "$0")/.."
. tools/dev-env.sh
log="${TMPDIR:-/tmp}/adminrights-dry-run.log"
start=$(date +%s)
(cd agent && DRY_RUN=1 HEADLESS=1 uv run --no-sync python agent.py) 2>&1 | tee "$log"
grep -E '^\[answer +[0-9]+s\] ' "$log" | tail -1 | sed -E 's/^\[answer +[0-9]+s\] //' > "${log%.log}.answer.json"
python3 eval/compare.py "${log%.log}.answer.json"
echo "time to answer: $(grep -oE '^\[answer +[0-9]+s\]' "$log" | tail -1 | grep -oE '[0-9]+')s (wall $(( $(date +%s) - start ))s) · log $log"
