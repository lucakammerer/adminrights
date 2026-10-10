"""Stress level S1 for the site-role assignment (I3): renamed and reordered sites must still get the same roles.

Every site id and URL in the scouting run is replaced by a neutral one, in `access`, in the submission target and
in the brief, and the order of `access` is shuffled. Pass: resolvers.sites gives each role the same (renamed) site as
on the original run, every time.

Run from the repo root, with `atira models proxy` running and the scouting logins loaded (tools/dev-env.sh):
    uv run --project agent --no-sync python tools/stress/s1_sites.py [attempts]
"""
import asyncio
import copy
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from agents.resolvers import agent as resolvers  # noqa: E402


def renamed(task: dict, seed: int) -> tuple[dict, dict]:
    """The task with neutral site ids and URLs, its access list shuffled; returns (task, old id -> new id)."""
    rng = random.Random(seed)
    old_ids = [s["siteId"] for s in task["access"]]
    labels = rng.sample(range(1, 100), len(old_ids))
    new_id = {old: f"site-{n}" for old, n in zip(old_ids, labels)}
    new_url = {s["url"].rstrip("/"): f"https://{new_id[s['siteId']]}.example" for s in task["access"]}
    t = copy.deepcopy(task)
    brief = t["brief"]
    for old, new in new_url.items():
        brief = brief.replace(old, new)
    for old, new in new_id.items():
        brief = brief.replace(f"`{old}`", f"`{new}`")  # ids appear in backticks; plain words stay untouched
    t["brief"] = brief
    for s in t["access"]:
        s["url"] = new_url[s["url"].rstrip("/")]
        s["siteId"] = new_id[s["siteId"]]
    rng.shuffle(t["access"])
    submission = t.get("submission") or {}
    if submission.get("siteId") in new_id:
        submission["siteId"] = new_id[submission["siteId"]]
        submission["url"] = f"https://{submission['siteId']}.example"
    return t, new_id


async def main(attempts: int) -> int:
    task = json.loads(os.environ["CHALLENGE_SCOUTING"])
    original = {role: entry["siteId"] for role, entry in (await resolvers.sites(task)).items()}
    print(f"original: {original}")
    failures = 0
    for seed in range(attempts):
        t, new_id = renamed(task, seed)
        expected = {role: new_id[site] for role, site in original.items()}
        got = {role: entry["siteId"] for role, entry in (await resolvers.sites(t)).items()}
        ok = got == expected
        failures += not ok
        print(f"seed {seed}: {'PASS' if ok else 'FAIL'}  order {[s['siteId'] for s in t['access']]}  got {got}")
    print(f"\nS1 site roles: {attempts - failures}/{attempts} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)))
