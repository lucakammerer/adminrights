"""Local dashboard of the team's Atira runs: what each run tested, where its time went and how to improve it.

usage: python3 tools/runs/serve.py [port]    then open http://127.0.0.1:8770
       DASHBOARD_HOST=10.0.0.1 python3 tools/runs/serve.py    bind elsewhere, e.g. behind a reverse proxy

Stops a test run on request; scored runs can't be stopped here. Uses the personal token (`atira token`, or
ATIRA_TOKEN) and the local git history: a run's package is matched to the commit whose agent/ tree it equals, or
to the closest one plus the files that differ, so every run shows the code it ran, with or without a label. Each
run is compared with the previous run that signed a bid: the commits since that change agent/, with their pull
requests.
"""
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API = os.environ.get("ATIRA_API", "https://ehl-challenge.atira.ai")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TOKEN = os.environ.get("ATIRA_TOKEN") or subprocess.run(
    ["atira", "token"], capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False).stdout.strip()
PHASE = re.compile(r"\[([a-z][\w-]*)(?::\S+)?\s+(\d+)s\]")
TARGET_MINUTES, TARGET_COST = 8, 0.10
OWNER = {"time": "Efficiency · Finn", "evidence": "Generalization · Yazan", "logic": "Quality & Release · Luca"}
FIELDS = ("material_number", "quantity", "base_unit_price", "surcharge_per_unit", "packaging_per_unit",
          "rebate_total", "unit_price", "lead_time_weeks")
PULL = re.compile(r"Merge pull request #(\d+)")
CANCEL = re.compile(r"/api/runs/([\w-]+)/cancel")
finished: dict[str, dict] = {}  # a finished run never changes, so it is built once
sources: dict[str, dict] = {}  # a run's package never changes either
ranges: dict[tuple[str, str, str], list[dict]] = {}


def get(path: str, raw: bool = False, method: str = "GET"):
    # the API refuses Python's default user agent
    request = urllib.request.Request(API + path, method=method,
                                     headers={"x-api-key": TOKEN, "user-agent": "adminrights-runs"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read() if raw else json.load(response)


def git(*args: str, stdin: str | None = None, index: str | None = None) -> str:
    env = {**os.environ, "GIT_INDEX_FILE": index} if index else None
    done = subprocess.run(["git", "-C", str(REPO), *args], input=stdin, capture_output=True, text=True, env=env, check=False)
    return done.stdout.strip()


GITHUB = re.sub(r"^git@github\.com:", "https://github.com/", git("remote", "get-url", "origin")).removesuffix(".git")


def package_tree(run_id: str) -> str:
    """The git tree hash of the uploaded package, comparable with `<commit>:agent`."""
    with tempfile.TemporaryDirectory() as tmp:
        files, index = os.path.join(tmp, "package"), os.path.join(tmp, "index")
        with tarfile.open(fileobj=io.BytesIO(get(f"/v1/runs/{run_id}/package", raw=True))) as tar:
            tar.extractall(files, filter="data")
        git(f"--work-tree={files}", "add", "-A", ".", index=index)
        return git(f"--work-tree={files}", "write-tree", index=index)


def ci_run(run_id: str) -> dict:
    """The CI loop's record of a run (label, agent tree), from any worktree of this clone."""
    for line in git("worktree", "list", "--porcelain").splitlines():
        state = Path(line.removeprefix("worktree ")) / "bench/.ci/state.json"
        if line.startswith("worktree ") and state.exists():
            try:
                record = json.loads(state.read_text())["runs"].get(run_id)
            except (ValueError, KeyError):
                continue
            if record:
                return record
    return {}


def closest_commit(tree: str) -> tuple[str, list[str]]:
    """The commit whose agent/ tree is the package, else the one with the fewest differing files, and those files."""
    commits = git("rev-list", "--branches", "--remotes", "--date-order", "--max-count=300").split()
    trees = git("cat-file", "--batch-check=%(objectname)", stdin="".join(f"{c}:agent\n" for c in commits)).split("\n")
    if tree in trees:
        return commits[trees.index(tree)], []
    best: tuple[str, list[str]] = ("", [])
    for commit, agent in zip(commits, trees):
        differ = git("diff", "--name-only", agent, tree).splitlines()
        if differ and (not best[0] or len(differ) < len(best[1])):
            best = (commit, differ)
    return best


def provenance(run: dict) -> dict:
    """What the run tested: its commit, files the package changes on top, the branches holding it, what it adds to main."""
    ci = ci_run(run["run_id"])
    label = run["package"].get("label") or ci.get("label")
    commit = git("rev-parse", "--verify", "--quiet", label.rsplit("@", 1)[-1]) if label and "@" in label else ""
    differs: list[str] = []
    if not commit:
        commit, differs = closest_commit(ci.get("tree") or package_tree(run["run_id"]))
    if not commit:
        return {"label": label, "commit": None}
    ahead = git("log", "--format=%h %s", "origin/main.." + commit).splitlines()
    return {
        "label": label,
        "commit": commit[:7],
        "subject": git("log", "-1", "--format=%s", commit),
        "branches": [b for b in (git("branch", "-r", "--contains", commit, "--format=%(refname:short)")
                                 or git("branch", "--contains", commit, "--format=%(refname:short)")).split()
                     if b != "origin" and not b.endswith("/HEAD")][:3],
        "on_main": not ahead,
        "ahead": ahead[:10],
        "files": git("diff", "--name-only", f"origin/main...{commit}", "--", "agent").splitlines(),
        "differs": differs,
    }


def pull_request(commit: str) -> int | None:
    """The pull request that brought a commit into main, if it is there yet."""
    merges = git("log", "--merges", "--ancestry-path", "--reverse", "--format=%s", f"{commit}..origin/main")
    return next((int(m[1]) for m in map(PULL.match, merges.splitlines()) if m), None)


def changes(base: str, head: str) -> list[dict]:
    """The package commits head has on top of base. Cached until main moves, since a merge gives a commit its PR."""
    key = (base, head, git("rev-parse", "origin/main"))
    if key not in ranges:
        ranges[key] = []
        for line in git("log", "--no-merges", "--format=%h %s", f"{base}..{head}", "--", "agent").splitlines():
            commit, subject = line.split(" ", 1)
            pr = pull_request(commit)
            ranges[key].append({"commit": commit, "subject": subject, "url": f"{GITHUB}/commit/{commit}",
                                "pr": pr and {"number": pr, "url": f"{GITHUB}/pull/{pr}"}})
    return ranges[key]


def compare(listed: list[dict]) -> None:
    """Point each run at the previous run that signed a bid and the commits since."""
    bids = [r for r in listed if r.get("has_answer") and r.get("score")]
    for run in listed:
        run["baseline"] = None
        base = next((b for b in bids if b["created_at"] < run["created_at"]), None)
        if base and base["source"].get("commit") and run["source"].get("commit"):
            a, b = base["source"], run["source"]
            same = not (a["differs"] or b["differs"] or git("diff", "--name-only", a["commit"], b["commit"], "--", "agent"))
            run["baseline"] = {"run_id": base["run_id"], "commits": changes(a["commit"], b["commit"]), "same": same}


def phases(run_id: str) -> list[dict]:
    """Each phase's first and last [tag  123s] log line (erp:<group> counts as erp). Phases that log once, when they
    are done (the resolvers, calc), have no start: they show as a point."""
    seen: dict[str, list[int]] = {}
    for line in get(f"/v1/runs/{run_id}/logs.jsonl", raw=True).decode().splitlines():
        entry = json.loads(line)
        if entry.get("stream") == "stdout":
            for tag, second in PHASE.findall(entry.get("text", "")):
                if tag not in ("run", "facts", "answer"):
                    seen.setdefault(tag, []).append(int(second))
    return sorted(({"phase": tag, "start": min(s), "end": max(s)} for tag, s in seen.items()),
                  key=lambda p: (p["end"], p["start"]))


def advice(run: dict, timeline: list[dict]) -> list[dict]:
    """Next steps from the score and the logs, each with its owner (triage rules: plan §14.3)."""
    tips = []

    def tip(area: str, text: str):
        tips.append({"owner": OWNER[area], "text": text})

    score = run["score"] if run["has_answer"] else None
    if run["failure_class"] == "agent_exit":
        tip("logic", f"The agent crashed ({run['error']}). The stderr log names the file; its owner fixes it.")
    elif not score:
        late = max(timeline, key=lambda p: p["end"], default=None)
        tip("time", "No bid was signed before the run ended"
            + (f"; the last phase still working was {late['phase']} at {late['end']} s" if late else "")
            + ". The watchdog has to sign what is entered before the budget ends.")
    if score:
        b = score["breakdown"]
        if b.get("decision", {}).get("points") == 0:
            tip("logic", f"Decision \"{b['decision'].get('got')}\" lost its points: an unfinished ERP search must "
                "omit its positions, never count as no match.")
        if b.get("decision", {}).get("got") != "no_bid" and b.get("discount_percent", {}).get("points") == 0:
            tip("logic", "Discount wrong: check which approval the commercials resolver picked (rules 5, 16, 21).")
        positions = [] if b.get("decision", {}).get("got") == "no_bid" else b.get("positions", [])
        missing = [p["position"] for p in positions if p.get("material_number", {}).get("got") is None]
        if missing:
            tip("evidence", f"No material for {', '.join(missing)}: the ERP agent kept no matching record in time.")
        wrong = [p["position"] for p in positions
                 if p["position"] not in missing and p.get("material_number", {}).get("points") == 0]
        if wrong:
            tip("logic", f"Wrong material for {', '.join(wrong)}: the evidence was there, the selection was not "
                "(bore, stroke, pressure, mounting, certification, status).")
        values = [f"{p['position']} ({', '.join(f.replace('_', ' ') for f in lost)})" for p in positions
                  if p["position"] not in missing + wrong
                  and (lost := [f for f in FIELDS[1:] if p.get(f, {}).get("points") == 0])]
        if values:
            tip("logic", f"Wrong values with the right material: {'; '.join(values)}. Compare calc's inputs with the "
                "kept pages: a wrong input is a resolver, a right input with a wrong result is calc.")
        if score["quality"] == 100:
            tip("logic", "Full score: a release candidate if it is faster or cheaper than our best submission.")
    if timeline and run["finished_at"] and run["started_at"]:
        total = (run["finished_at"] - run["started_at"]) / 1000
        slow = max(timeline, key=lambda p: p["end"] - p["start"])
        if total > TARGET_MINUTES * 60:
            tip("time", f"{total / 60:.1f} min against the {TARGET_MINUTES} min target; the longest phase is "
                f"{slow['phase']} ({slow['end'] - slow['start']} s).")
    cost = run["cost_micro_usd"] / 1e6
    if cost > TARGET_COST:
        tip("time", f"Cost ${cost:.2f} against the ${TARGET_COST:.2f} target, {run['input_tokens'] / 1e6:.1f} M "
            "input tokens: a cache-friendly history cuts most of it (I23).")
    return tips


def build(summary: dict) -> dict:
    run_id = summary["run_id"]
    run = {**get(f"/v1/runs/{run_id}"), "answer": None}
    if run_id not in sources:
        sources[run_id] = provenance(run)
    run["source"] = sources[run_id]
    if run["finished_at"]:
        run["phases"] = phases(run_id)
        run["advice"] = advice(run, run["phases"])
        finished[run_id] = run
    return run


def load(summary: dict) -> dict:
    """One run; a slow or failing API call shows on that run and is retried on the next refresh."""
    try:
        return finished.get(summary["run_id"]) or build(summary)
    except OSError as error:
        return {**summary, "source": {"commit": None}, "error": f"dashboard could not load this run: {error}"}


def runs() -> list[dict]:
    listed = get("/v1/runs")["runs"]
    if any(r["run_id"] not in sources for r in listed):
        git("fetch", "--quiet", "origin")
    with ThreadPoolExecutor(max_workers=3) as pool:
        loaded = sorted(pool.map(load, listed), key=lambda r: r["created_at"], reverse=True)
    compare(loaded)
    return loaded


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/runs":
            self.reply(200, json.dumps(runs()).encode())
        elif self.path == "/":
            self.reply(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self):
        match = CANCEL.fullmatch(self.path)
        if not match:
            self.send_error(404)
        elif not self.headers.get("x-dashboard"):  # a custom header forces a CORS preflight, so no other site can post
            self.send_error(403)
        else:
            try:
                if get(f"/v1/runs/{match[1]}")["kind"] != "rehearsal":
                    self.reply(403, b'{"error": "only test runs can be stopped from the dashboard"}')
                else:
                    self.reply(200, get(f"/v1/runs/{match[1]}/cancel", raw=True, method="POST"))
            except urllib.error.HTTPError as error:
                self.reply(error.code, error.read())

    def reply(self, status: int, body: bytes, kind: str = "application/json"):
        self.send_response(status)
        self.send_header("content-type", kind)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not TOKEN:
        sys.exit("no token: run `atira login` or set ATIRA_TOKEN")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    print(f"runs dashboard on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
