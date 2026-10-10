"""Local dashboard of the team's Atira runs, in the spirit of GitHub Actions.

usage: python3 tools/runs/serve.py [port]    then open http://127.0.0.1:8770

Reads the runs with the personal token (`atira token`, or ATIRA_TOKEN) and never writes anything. A run's branch comes
from its package label, else from the CI loop's state (bench/.ci/state.json).
"""
import json
import os
import subprocess
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API = os.environ.get("ATIRA_API", "https://ehl-challenge.atira.ai")
HERE = Path(__file__).resolve().parent
CI_STATE = HERE.parents[1] / "bench/.ci/state.json"
TOKEN = os.environ.get("ATIRA_TOKEN") or subprocess.run(
    ["atira", "token"], capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()
finished: dict[str, dict] = {}  # a finished run never changes, so it is fetched once


def get(path: str) -> dict:
    # the API refuses Python's default user agent
    request = urllib.request.Request(API + path, headers={"x-api-key": TOKEN, "user-agent": "adminrights-runs"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def ci_labels() -> dict:
    try:
        return {run_id: run.get("label") for run_id, run in json.loads(CI_STATE.read_text())["runs"].items()}
    except (OSError, ValueError, KeyError):
        return {}


def runs() -> list[dict]:
    labels = ci_labels()
    out = []
    for run in get("/v1/runs")["runs"]:
        run_id = run["run_id"]
        if run_id not in finished:
            run = get(f"/v1/runs/{run_id}")
            if run["finished_at"]:
                finished[run_id] = run
        run = finished.get(run_id, run)
        out.append({**run, "answer": None, "label": run["package"].get("label") or labels.get(run_id)})
    return out


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/runs":
            body, kind = json.dumps(runs()).encode(), "application/json"
        elif self.path == "/":
            body, kind = (HERE / "index.html").read_bytes(), "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("content-type", kind)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not TOKEN:
        sys.exit("no token: run `atira login` or set ATIRA_TOKEN")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
    print(f"runs dashboard on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
