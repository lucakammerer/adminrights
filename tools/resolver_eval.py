"""Resolver eval: `requirements` and `commercials` on recorded evidence, as recorded and changed the way a private
dataset might (eval/mutations.py), each answer scored against public-1's facts as the change leaves them. No browser:
it costs model calls only, so a prompt change is measured in minutes, several times over for the model's variance.

With `atira models proxy` running and `source tools/dev-env.sh` done:
    uv run --project agent --no-sync python tools/resolver_eval.py [FIXTURE] [--repeat 3] [--only NAME]
FIXTURE defaults to eval/fixtures/resolvers, the kept evidence of one public-1 recording. A new one comes from
tools/stress/run_agents.py --agents tender_portal,supplier_portal,webmail (its tender_portal.json, supplier_portal.json
and webmail.json); nothing may run while a scored submission runs.
"""
import argparse
import asyncio
import copy
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "agent"), str(ROOT / "eval"), str(ROOT / "tools/stress")]

import llm  # noqa: E402
import run as contract  # noqa: E402
from agents.resolvers import agent as resolvers  # noqa: E402
from mutations import CASES  # noqa: E402
from run_agents import _chat, commercials_score, requirements_score  # noqa: E402

AGENTS = ("tender_portal", "supplier_portal", "webmail")
PARALLEL = 10  # passes at once; each makes three calls, and the team shares 32 concurrent Qwen calls


async def attempt(task, results, facts, gate) -> list[str]:
    """One pass of both resolvers; the score rows it got wrong."""
    tender, spec, mail = (results[name] for name in AGENTS)
    async with gate:
        requirements, commercials = await asyncio.gather(resolvers.requirements(task, tender, spec, mail),
                                                         resolvers.commercials(task, tender, mail),
                                                         return_exceptions=True)
    if isinstance(requirements, BaseException) or isinstance(commercials, BaseException):
        return [f"failed: {requirements if isinstance(requirements, BaseException) else commercials}"]
    rows = requirements_score(requirements, facts) + commercials_score(commercials, facts)
    return [name for name, ok in rows if not ok]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path, nargs="?", default=ROOT / "eval/fixtures/resolvers")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--only")
    args = parser.parse_args()
    llm.chat, llm.log = _chat, lambda *_: None  # run_agents' call timing and the log lines would drown the table
    task, _ = contract.load_run()
    recorded = {name: json.loads((args.fixture / f"{name}.json").read_text())["result"] for name in AGENTS}
    facts = json.loads((ROOT / "eval/public-1/gather-facts.json").read_text())
    cases = [c for c in CASES if not args.only or c.name == args.only]
    gate = asyncio.Semaphore(PARALLEL)

    async def run(case):
        results, want = case.apply(copy.deepcopy(recorded)), case.expect(copy.deepcopy(facts))
        return case, await asyncio.gather(*(attempt(task, results, want, gate) for _ in range(args.repeat)))

    worst = 0
    for case, misses in await asyncio.gather(*(run(c) for c in cases)):
        clean = sum(not m for m in misses)
        worst = max(worst, args.repeat - clean)
        wrong = Counter(row for m in misses for row in m)
        print(f"{clean}/{args.repeat}  {case.name}: {case.about}")
        for row, count in wrong.most_common():
            print(f"       {count}x {row}")
    return 1 if worst else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
