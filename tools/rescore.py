"""The logged facts of past runs through today's calc, scored against public-1: a calc change checked without a test run.

usage: uv run --project agent --no-sync python tools/rescore.py [run.log ...]   # default: bench/.ci/logs/*.log
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "agent"), str(ROOT / "eval")]

import calc  # noqa: E402
import compare  # noqa: E402

EXPECTED = json.loads((ROOT / "eval/expected.json").read_text())


def last(tag: str, text: str):
    found = re.findall(rf"^\[{tag}\s+\d+s\] (\{{.*)$", text, re.M)
    try:
        return json.loads(found[-1]) if found else None
    except ValueError:  # cut by the log line limit
        return None


for path in sys.argv[1:] or sorted((ROOT / "bench/.ci/logs").glob("*.log")):
    text = Path(path).read_text()
    facts, answer = last("facts", text), last("answer", text)
    if facts is None:
        print(f"{Path(path).stem}: no complete facts line")
        continue
    then = compare.score(answer, EXPECTED)[1] if answer else "–"
    result = calc.compute(facts)
    print(f"{Path(path).stem}: logged {then}, now {compare.score(result['answer'], EXPECTED)[1]}, "
          f"omitted {result['omitted']}")
