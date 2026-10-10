"""Audit the package before it is uploaded (I8): no public-1 value anywhere in it (every string and larger number in
eval/expected.json, plus ids, hosts, site-specific path segments and addresses from run logs), no German word of the
public sites the brief doesn't tell every team, no browser of its own outside browsers.py, no API key.

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
        paths = re.findall(r"https?://[\w.-]+(/[^\s\"'?#]*)", text)
        found |= {seg for path in paths for seg in path.split("/") if re.search(r"\d|-", seg)}  # mm03, x-content
    return {value for value in found if len(value) >= 4}


def site_words() -> set[str]:
    """UI labels, error pages and status words typed from the public sites: German words from the quoted labels in the
    scouting notes and from the scouted Q&A. Words the brief or the challenge tell every team are allowed."""
    public = ROOT / "eval/public-1"
    told = set(re.findall(r"\w+", ((public / "run-brief.md").read_text() + (public / "challenge-rfq.md").read_text()).lower()))
    labels = re.findall(r'"([^"\n]+)"|„([^“\n]+)“|`([^`\n]+)`', (public / "scouting-notes.md").read_text())
    text = " ".join(part for label in labels for part in label) + (public / "scout-public-qa.txt").read_text()
    return {word for word in re.findall(r"[A-Za-zÄÖÜäöüß]{5,}", text)
            if word.lower() not in told and (word[0].isupper() or re.search("[äöüß]", word))}


def audit(agent: Path, logs: list[str]) -> list[str]:
    values, words = public_values(logs), site_words()
    problems = [] if (agent / "agent.py").is_file() else [f"no agent.py in {agent}"]
    for path in sorted(agent.rglob("*")):
        if not path.is_file() or ".venv" in path.parts or "__pycache__" in path.parts or path.suffix == ".lock":
            continue
        text = path.read_text(errors="ignore")
        name = str(path.relative_to(agent))
        problems += [f"{name}: public-1 value {value}" for value in values if value in text]
        problems += [f"{name}: public site word {word}" for word in sorted(words) if re.search(rf"(?<!\w){word}(?!\w)", text)]
        if path.suffix == ".py" and path.name != "browsers.py" and re.search(r"\.launch(_persistent_context)?\(", text):
            problems.append(f"{name}: launches its own browser")
        if re.search(r"\bsk-[A-Za-z0-9_-]{20,}|api[_-]?key\s*=\s*[\"'][^\"']{12,}", text, re.I):
            problems.append(f"{name}: looks like an API key")
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
