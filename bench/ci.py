"""Continuous test runs: every new head of origin/p1/* and origin/p2/* is merged onto the base (origin/main plus this
checkout's HEAD) in a scratch worktree, passes the free gates, then goes to `atira test-run`. Finished runs are scored
with eval/compare.py and appended to bench/RUNS.md. Nothing is pushed. One call is one tick; /loop repeats it.

usage: python bench/ci.py            # one tick
       python bench/ci.py --dry-run  # everything except starting test runs
"""
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / "bench/.ci"
STATE = CI / "state.json"
SCRATCH = Path(tempfile.gettempdir()) / "adminrights-ci"
BRANCHES = ("p1/", "p2/")
MAX_ACTIVE = 2  # more parallel test runs distort the time measurement
RUN_ENDED = {"submitted", "failed", "timed_out", "cancelled"}
SUBMISSION_ENDED = {"complete", "failed", "rejected", "disqualified"}


def sh(*cmd, cwd=ROOT, check=True) -> str:
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and done.returncode:
        raise RuntimeError(f"{' '.join(cmd)}: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout.strip()


def atira(*args) -> dict:
    return json.loads(sh("atira", *args, "--json"))


def load() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"tested": {}, "runs": {}}


def candidates() -> list[tuple[str, list[str]]]:
    """(name, refs merged onto origin/main), in priority order: base, each branch, all branches together."""
    heads = sh("git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin").split()
    branches = sorted(h for h in heads if h.removeprefix("origin/").startswith(BRANCHES))
    base = [sh("git", "rev-parse", "HEAD")]
    out = [("base", base)] + [(b.removeprefix("origin/"), base + [b]) for b in branches]
    return out + [("all", base + branches)] * (len(branches) > 1)


def build(name: str, refs: list[str]) -> tuple[Path, str, str]:
    """A scratch worktree of origin/main with refs merged in. Returns (dir, agent tree hash, label)."""
    path = SCRATCH / re.sub(r"\W", "-", name)
    sh("git", "worktree", "remove", "--force", str(path), check=False)
    sh("git", "worktree", "add", "--detach", str(path), "origin/main")
    for ref in refs:
        if subprocess.run(["git", "merge", "--no-edit", "-q", ref], cwd=path, capture_output=True).returncode:
            sh("git", "merge", "--abort", cwd=path, check=False)
            raise RuntimeError(f"merge conflict with {ref}")
    label = f"{name}@{sh('git', 'rev-parse', '--short', refs[-1])}"
    return path, sh("git", "rev-parse", "HEAD:agent", cwd=path), label


def gates(path: Path) -> list[str]:
    """Free checks before a test run is spent. Returns the failures."""
    agent = path / "agent"
    failed = []
    if subprocess.run([sys.executable, "-m", "compileall", "-q", str(agent)], capture_output=True).returncode:
        failed.append("compile")
    logs = [str(p) for p in (CI / "logs").glob("*.log")]
    if subprocess.run([sys.executable, str(ROOT / "eval/leak.py"), "--agent", str(agent), *logs],
                      capture_output=True).returncode:
        failed.append("leak")
    own = [str(p.relative_to(agent)) for p in agent.rglob("*.py")
           if p.name != "browsers.py" and ".venv" not in p.parts and re.search(r"\.launch\(", p.read_text())]
    if own:
        failed.append(f"own browser in {own}")
    replay = subprocess.run([sys.executable, "-c", (
        "import json, sys; sys.path.insert(0, sys.argv[1]); import calc; "
        "print(json.dumps(calc.compute(json.load(open(sys.argv[2])))['answer']))"),
        str(agent), str(ROOT / "bench/fixtures/facts.json")], capture_output=True, text=True)
    answer = CI / "replay.json"
    answer.write_text(replay.stdout)
    scored = subprocess.run([sys.executable, str(ROOT / "eval/compare.py"), str(answer)], capture_output=True, text=True)
    if "quality 100.00" not in scored.stdout:
        failed.append("calc replay below 100")
    return failed


def collect(state: dict) -> list[str]:
    """Score test runs that ended since the last tick and append them to RUNS.md."""
    lines = []
    for run_id, info in state["runs"].items():
        if info.get("done"):
            continue
        detail = atira("status", run_id)
        if detail.get("phase") != "done" and detail.get("status") not in RUN_ENDED:
            continue
        log = CI / "logs" / f"{run_id}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(sh("atira", "logs", run_id, check=False))
        found = re.findall(r"^\[answer\s+\d+s\] (\{.*)$", log.read_text(), re.M)
        evaluated = "–"
        if found:
            (CI / "answer.json").write_text(found[-1])
            scored = sh(sys.executable, str(ROOT / "eval/compare.py"), str(CI / "answer.json"), check=False)
            evaluated = (re.findall(r"quality ([\d.]+)", scored) or ["–"])[0]
        score = detail.get("score") or {}
        platform = f"{score.get('quality', 0)}, {'eligible' if score.get('eligible') else 'not eligible'}"
        minutes = (score.get("duration_ms") or 0) / 60000
        cost = (detail.get("cost_micro_usd") or 0) / 1e6
        started = time.strftime("%Y-%m-%d %H:%M", time.gmtime((detail.get("started_at") or 0) / 1000))
        row = (f"| {started} | {run_id} | {info['label']} | {platform} | {evaluated} | {minutes:.0f} min | "
               f"${cost:.3f} | {detail.get('error') or 'TODO'} |")
        add_row(row)
        info.update(done=True, platform=platform, eval=evaluated, minutes=round(minutes, 1), cost=cost)
        lines.append(f"ended {run_id} {info['label']}: platform {platform}, eval {evaluated}, "
                     f"{minutes:.1f} min, ${cost:.3f}, log {log}")
    return lines


def add_row(row: str):
    runs = ROOT / "bench/RUNS.md"
    text = runs.read_text()
    head = "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
    runs.write_text(text.replace(head, head + row + "\n", 1))


def tick(dry: bool) -> list[str]:
    CI.mkdir(parents=True, exist_ok=True)
    state = load()
    sh("git", "fetch", "-q", "--prune", "origin")
    lines = collect(state)
    status = atira("status", "--challenge", "rfq")
    busy = [s["submission_id"] for s in status["submissions"] if s.get("status") not in SUBMISSION_ENDED]
    active = [r for r in status["test_runs"] if r.get("status") not in RUN_ENDED]
    if busy:
        lines.append(f"hold: submission {busy} is running")
    for name, refs in [] if busy else candidates():
        if len(active) >= MAX_ACTIVE:
            lines.append(f"wait: {len(active)} test runs active")
            break
        try:
            path, tree, label = build(name, refs)
        except RuntimeError as error:
            lines.append(f"skip {name}: {error}")
            continue
        if tree in state["tested"]:
            sh("git", "worktree", "remove", "--force", str(path), check=False)
            continue
        failed = gates(path)
        if failed:
            lines.append(f"gate failed {label}: {', '.join(failed)}")
            state["tested"][tree] = f"gates: {', '.join(failed)}"
        elif dry:
            lines.append(f"would test {label} (tree {tree[:10]})")
        else:
            started = atira("test-run", str(path / "agent"), "--challenge", "rfq", "--no-open")
            state["tested"][tree] = started["run_id"]
            state["runs"][started["run_id"]] = {"label": label, "tree": tree, "rehearsal": started["rehearsal_id"]}
            active.append(started)
            lines.append(f"started {started['run_id']} for {label}")
        sh("git", "worktree", "remove", "--force", str(path), check=False)
    STATE.write_text(json.dumps(state, indent=1))
    return lines or ["idle: nothing new"]


if __name__ == "__main__":
    print("\n".join(tick("--dry-run" in sys.argv)))
