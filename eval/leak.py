"""Fail if agent/ contains a public-1 value: every string and larger number in eval/expected.json, plus the ids
and names seen in run logs passed as arguments.

usage: python eval/leak.py [--agent DIR] [run.log ...]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDS = r"\b[A-Z]{1,4}-\d{3,}(?:-\d+)?\b"


def values(logs: list[str]) -> set[str]:
    found: set[str] = set()

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str) and len(x) >= 4:
            found.add(x)
        elif isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) >= 100:
            found.add(str(x))

    walk(json.loads((ROOT / "eval/expected.json").read_text()))
    for log in logs:
        text = Path(log).read_text(errors="ignore")
        found |= set(re.findall(IDS, text))
        found |= set(re.findall(r"https?://([\w.-]+)", text))
        found |= set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text))
    return found


def main():
    args, agent = sys.argv[1:], ROOT / "agent"
    if args[:1] == ["--agent"]:
        agent, args = Path(args[1]), args[2:]
    found = values(args)
    leaks = [(str(p.relative_to(agent)), v) for p in sorted(agent.rglob("*"))
             if p.is_file() and ".venv" not in p.parts and p.suffix != ".lock"
             for v in found if v in p.read_text(errors="ignore")]
    for path, value in leaks:
        print(f"{path}: {value}")
    print(f"{len(leaks)} leaks")
    sys.exit(1 if leaks else 0)


if __name__ == "__main__":
    main()
