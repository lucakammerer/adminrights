"""Audit the package before it is uploaded (I8): no public-1 value anywhere in it (every string and larger number in
eval/expected.json, plus ids, hosts and addresses from run logs), and no browser of its own outside browsers.py.

usage: python tools/audit_package.py [--agent DIR | --package <run_|reh_|sub_ id>] [run.log ...]
"""
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDS = r"\b[A-Z]{1,4}-\d{3,}(?:-\d+)?\b"


def public_values(logs: list[str]) -> set[str]:
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
        found |= {host for host in re.findall(r"https?://([\w.-]+)", text) if "." in host}
        found |= set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text))
    return {value for value in found if len(value) >= 4}


def audit(agent: Path, logs: list[str]) -> list[str]:
    values = public_values(logs)
    problems = [] if (agent / "agent.py").is_file() else [f"no agent.py in {agent}"]
    for path in sorted(agent.rglob("*")):
        if not path.is_file() or ".venv" in path.parts or "__pycache__" in path.parts or path.suffix == ".lock":
            continue
        text = path.read_text(errors="ignore")
        name = str(path.relative_to(agent))
        problems += [f"{name}: public-1 value {value}" for value in values if value in text]
        if path.suffix == ".py" and path.name != "browsers.py" and re.search(r"\.launch(_persistent_context)?\(", text):
            problems.append(f"{name}: launches its own browser")
    return problems


def downloaded(package_id: str) -> Path:
    out = Path(tempfile.mkdtemp(prefix="audit-"))
    subprocess.run(["atira", "package", package_id, "--out", str(out)], check=True, capture_output=True,
                   stdin=subprocess.DEVNULL)
    for archive in out.glob("*.tar.gz"):
        with tarfile.open(archive) as tar:
            tar.extractall(out / "package", filter="data")
    return out / "package"


def main():
    args, agent = sys.argv[1:], ROOT / "agent"
    if args[:1] == ["--agent"]:
        agent, args = Path(args[1]), args[2:]
    elif args[:1] == ["--package"]:
        agent, args = downloaded(args[1]), args[2:]
    problems = audit(agent, args)
    print("\n".join(problems + [f"{len(problems)} problems in {agent}"]))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
