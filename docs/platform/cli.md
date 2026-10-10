# The CLI

A command line for taking part: one JavaScript file for Node 24 that uses only Node's built-ins. It is made for
people and coding agents alike: every command takes `--json`, and exit codes tell outcomes apart. Everything it does
is plain HTTP, described in the [API guide](https://ehl-challenge.atira.ai/docs/api.md); you never need the CLI.

## Install

macOS and Linux:

```sh
export ATIRA_API=https://ehl-challenge.atira.ai
curl -fsSL "$ATIRA_API/install.sh" | sh
```

Windows, in PowerShell (5.1 or 7):

```powershell
$env:ATIRA_API = "https://ehl-challenge.atira.ai"
irm "$env:ATIRA_API/install.ps1" | iex
```

The script checks for Node 24 or newer. Where it is missing, it asks whether to install a private copy for atira
alone, the latest Node 24 from nodejs.org, checked against the release's `SHASUMS256.txt`. It needs no admin rights
and never changes the `node` on your `PATH`. Without a terminal to ask in, `ATIRA_INSTALL_NODE=1` says yes (`0`, no).
Then it downloads `/cli.mjs`, checks it against `/cli.mjs.sha256` and installs it for you alone, without sudo:

- macOS and Linux: the file in `~/.local/share/atira/atira.mjs`, Node (if needed) in `~/.local/share/atira/node`,
  and an `atira` command in `~/.local/bin`. It tells you when `~/.local/bin` is not on your `PATH`.
- Windows: the same under `%LOCALAPPDATA%\atira`, with `atira.cmd` in `%LOCALAPPDATA%\atira\bin`, which it adds to
  your user `PATH`. Open a new terminal afterwards.

The `atira` command runs your own Node when it is 24 or newer, else the private copy. Running the installer again
updates the CLI; it downloads Node again only when the private copy is older than 24. Read the script first, if you
like:

```sh
curl -fsSL "$ATIRA_API/install.sh" | less
```

To uninstall: `rm -rf ~/.local/share/atira ~/.local/bin/atira`, or on Windows
`Remove-Item -Recurse -Force "$env:LOCALAPPDATA\atira"`. Your sign-in stays in the config file (see below) until you
delete it.

Without installing anything, download the file and run it with Node; `node atira.mjs` works wherever this guide
says `atira`:

```sh
curl -fsSL "$ATIRA_API/cli.mjs" -o atira.mjs && node atira.mjs --help
```

The CLI talks to the server it was downloaded from. Set `ATIRA_API` to use another one. `atira upgrade` downloads the
server's current version, checks its SHA-256 and replaces the file; a download that does not match leaves the file
as it was.

## Sign in

```sh
atira login
```

The browser opens a page that asks you to sign in with GitHub, then whether to sign in the CLI on this computer.
Approve, and the browser returns to the CLI, which stores a personal token for you. The token acts as you, on the
team you are in at the time of each request: leave the team, or be removed, and it no longer reaches the team. It
lasts 90 days. Your team page lists your signed-in devices; revoke any of them there.

Where no browser can open (an SSH session, a container, a coding agent), sign in with a code instead:

```sh
atira login --device
```

It prints a link with the code filled in. Open it on any device, check that the code matches and approve; the CLI
waits and then stores the token. `atira login` switches to the code by itself when the browser cannot be opened, or
offers it when the browser has not answered after two minutes.

```sh
atira whoami                                  # who you are, your team, and when the token expires
atira token                                   # the token, for curl and scripts
curl -H "x-api-key: $(atira token)" "$ATIRA_API/v1/teams/me"
atira logout                                  # revoke the token on the server and forget it here
```

The token is kept per server in `~/.config/atira/config.json` (or `$XDG_CONFIG_HOME/atira/config.json`; on Windows
`%USERPROFILE%\.config\atira\config.json`), readable only by you (mode 0600). `ATIRA_TOKEN` overrides it, which suits
CI and agents: `export ATIRA_TOKEN=$(atira token)`.

## Commands

| Command | What it does |
| --- | --- |
| `login [--device] [--key <key>]` | Sign in through the browser, or with a code (`--device`), and store a personal token; `--key` stores a team key where there is no GitHub sign-in |
| `logout` | Revoke the stored token on the server and forget it |
| `whoami` | Who you are signed in as, your team, and when the token expires |
| `token` | Print the token in use, for `curl -H "x-api-key: $(atira token)"` |
| `upgrade` | Download the server's current CLI, check its SHA-256 and replace this file |
| `challenges` | The challenges, with their Markdown pages |
| `challenge <id>` | A challenge as Markdown: task, websites, rules, run contract, submitting, answer schema |
| `scout [--challenge <id>] [--env [--port <port>]]` | The published scouting logins for the public websites; `--env` prints them as shell exports for running your agent locally, with any hosted model's variables pointed at `atira models proxy`; use the same `--port` when the proxy runs on another port |
| `models proxy [--port <port>]` | Where the organizers host models: a local proxy to them on 127.0.0.1 (port 8765) that prints each model's base URL and key variables |
| `test-run <dir> [--challenge <id>] [--dry-run] [--follow] [--no-open]` | Pack a folder, run it once in the sandbox on the public dataset and open its run page; `--follow` prints its place in the queue, then streams its logs here |
| `submit <dir> [--challenge <id>] [--dry-run] [--follow] [--no-open]` | Pack a folder and submit it: review, then one scored run on the public dataset; opens your team page; `--follow` prints the review, each run's place in the queue and its end here |
| `cancel <run>` | Cancel a test or scored run that has not finished: its sandbox is removed and the run fails |
| `final [--best-of <1\|3>] [--challenge <id>]` | Read or change the final attempt choice before the final run starts |
| `status [<id>] [--challenge <id>]` | Your latest submissions and test runs, or one submission (`sub_...`), test run (`reh_...`) or run (`run_...`) |
| `logs <run> [--follow]` | A test or scored run's logs; `--follow` keeps polling until the run has ended |
| `package <id> [--out <dir>]` | The package a test run (`reh_...` or `run_...`), scored run or submission (`sub_...`) of your team used, as uploaded: agent.json and each file's size; `--out` saves the `.tar.gz` in a folder, checked against its SHA-256 |
| `leaderboard [--challenge <id>]` | The leaderboard |
| `mcp` | Serve MCP on stdio for your coding agent: list and debug runs (why one failed, logs by time, model calls, where the time went, a browser's screen at a time, recorded inputs, two runs compared), start and wait for test runs, and cancel a run or submit when you confirm ([MCP guide](https://ehl-challenge.atira.ai/docs/mcp.md)) |

Every command accepts `--json` (machine-readable output on stdout, errors included) and `--help`.
`--challenge` defaults to `ATIRA_CHALLENGE`, else the platform's first challenge. While `login` waits, it writes its
instructions to stderr, so `--json` output on stdout stays one JSON document.

### Develop locally, then test in the sandbox

Develop against the public websites on your own machine, then test the package in the sandbox:

```sh
atira scout                    # the scouting logins: each website, its URL, username and password
eval "$(atira scout --env)"    # the same as shell exports
uv run python agent.py         # your agent, on your machine, against the public websites (the starter kit's way)
atira test-run ./my-agent      # then one run in the sandbox, opened live in the browser
```

On Windows, `--env` and `models proxy` print PowerShell's `$env:NAME = '...'` instead; load them with
`atira scout --env | Out-String | Invoke-Expression`.

### Hosted models from your machine

Where the organizers host models, a run gets each one's base URL and key variables set for it, and the
Getting started page names them. On your machine, run the proxy in its own terminal: it prints the same variables,
pointed at itself, with `local` as the key (any non-empty value works through it).

```sh
atira login                    # once per computer
atira models proxy             # keep it running; it prints the exports
```

`eval "$(atira scout --env)"` sets the same variables with the scouting logins; it never exports your sign-in. The proxy
listens on 127.0.0.1 only. It holds a 30-minute inference token, good for model calls only and bound to an Ed25519 key
that never leaves the process, signs every call with that key and rotates the token before it expires. A copied token
works in no other client. Calls from your machine are free, recorded and never ranked. If port 8765 is in use, pick
the same port for the proxy and the scouting exports:

```sh
atira models proxy --port 8777                   # in a second terminal
eval "$(atira scout --env --port 8777)"
```

In PowerShell, the second line is `atira scout --env --port 8777 | Out-String | Invoke-Expression`. The proxy also
prints the command with its actual port, including when `--port 0` lets the operating system choose one.

`scout` needs no sign-in for the logins. It prints the logins the organizers published, how long they are valid,
and what happens to an answer: these are demo logins, so an answer entered on the website that takes it is
acknowledged without counting. For RFQ, a bid entered on the tender portal is acknowledged without counting. `--json` prints what
`GET /v1/challenges/<id>/scouting` returns: the logins as `access`, plus `submission`, `brief` and `answer_schema`,
shaped like a run's `/v1/runs/current`. `--env` prints:

| Variable | Value |
| --- | --- |
| `CHALLENGE_SCOUTING` | what `GET /v1/challenges/<id>/scouting` returned, as JSON: the brief, logins and answer format |
| `CHALLENGE_SCOUTING_URL` | `$ATIRA_API/v1/challenges/<id>/scouting`, the same without a token once the organizers publish the logins |
| `CHALLENGE_SITE_ACCESS` | the websites with the scouting logins, the JSON a run gets: `[{"siteId", "url", "credentials": {"username", "password"}}]` |
| `CHALLENGE_SITE_<ID>_URL` | each website's URL, its id upper-cased with `_` for other characters, e.g. `CHALLENGE_SITE_TENDER_PORTAL_URL` |
| `<MODEL>_BASE_URL`, `<MODEL>_API_KEY` | only when the platform hosts models: each one through `atira models proxy` on this computer, with `local` as the key. Keep the proxy running in another terminal, signed in with `atira login`. `atira scout --help` names them |

With `--env --json`, the same variables come as one JSON object. There is no run token: your agent calls other
models with your own key, directly or through the model proxy with your personal token (see
[LLM calls](https://ehl-challenge.atira.ai/docs/run-contract.md#llm-calls)). Calls through the proxy from your machine, a hosted model's included, are
recorded for your team and never ranked. A hosted model is free to use, never charged; each call counts toward your
run's cost at simulated API prices, so the cost ranking stays honest. Nothing done with these logins counts.
Locally there are no browsers from the platform (`CDP_URL`, `CDP_URLS`, `BROWSER_COUNT`, `DISPLAY`) and no egress
proxy: your agent starts its own browsers. When nothing is published yet, `scout` exits 4: organizers publish the scouting logins before the event.

### Test runs and submissions

```sh
atira test-run ./my-agent --dry-run   # what would be uploaded, and what is left out
atira test-run ./my-agent             # one run in the sandbox on the public dataset; opens its run page
atira test-run ./my-agent --follow    # the same, and its logs here until it ends
atira cancel run_...                  # stop a run that has not finished
atira submit ./my-agent               # review, then the scored run on the public dataset; opens your team page
atira status sub_...
```

`test-run` uploads the package, starts the test run and, when its output goes to a terminal, opens the run page in
the browser: the browser, the logs, the phases and the score with its full breakdown, live. `submit` opens your team
page instead, which shows the submission's review and then links each scored run as it starts: the run does not
exist until the review has passed, which takes minutes, so the CLI does not wait for it unless you pass `--follow`.
`ATIRA_BROWSER` picks the
command that opens the page (`none` only prints the link), `--no-open` skips it, and `--json` never opens anything.

`test-run --follow` then streams the run's logs as `logs --follow` does and exits 7 if the run failed or timed out.
While the run waits for a sandbox, it prints its place in the [fair queue](https://ehl-challenge.atira.ai/docs/api.md#the-run-queue) on stderr whenever
that changes ("Queued: 3 runs ahead of yours"). With `--json --follow`, the upload's result comes as one JSON line,
then one `{"at", "stream", "text"}` line per chunk. `submit --follow` prints the review's outcome, then each scored
run's place in the queue and its end, and exits 7 unless the submission completes; with `--json`, the final
submission follows the upload's line.

`cancel <run>` takes a run (`run_...`) or a test run (`reh_...`) of your team that has not finished. The run's sandbox
is removed and the run fails with the error "Cancelled by @you"; a queued run is cancelled before it starts. Your
team can start the next test run at once. A cancelled scored run leaves its submission not complete: the leaderboard
ignores that submission, and you can submit again. A run that
has already finished answers 409 (exit 6).

`test-run` and `submit` pack the folder into a gzipped tarball the way the platform reads it:

- `agent.json` must be at the folder's root, with `run` (and optionally `setup`) as arrays of strings.
- `.git`, `node_modules` and `.DS_Store` are always left out, and so is whatever `.gitignore` files exclude (in the
  folder and below: patterns, `*`, `?`, `**`, `[...]`, a leading `/`, a trailing `/` for folders, and `!` to
  include again). Symbolic links are left out too.
- The limits are checked before uploading: at most 2,000 files, 5 MB per file, 20 MB in total, and 20 MB
  compressed (or what the server announces).

### Logs, status and the leaderboard

`package <id>` shows exactly what a run ran: the package's SHA-256 and label, its `agent.json` and every file with
its size. A scored run ran its submission's package. `--out ./downloaded` also saves the `.tar.gz` there; unpack it
with `tar -xzf <file> -C <folder>`.

`logs <run>` prints what the run has written so far; `--follow` polls with a growing pause (1 s, up to 10 s) and
exits when the run has ended. `--json` prints one `{"at", "stream", "text"}` object per line. `status` without an id
shows your best result, your latest submissions and your latest test runs.

## Configuration

| Variable | Meaning |
| --- | --- |
| `ATIRA_API` | The platform; defaults to the server the file came from |
| `ATIRA_TOKEN` | A token to use instead of the stored one |
| `ATIRA_CHALLENGE` | The default challenge |
| `ATIRA_POLL_MS` | The first pause of `logs --follow`, in milliseconds (default 1000) |
| `ATIRA_BROWSER` | The command `login`, `test-run` and `submit` open pages with, or `none` to only print the link |
| `XDG_CONFIG_HOME` | Where `atira/config.json` lives (default `~/.config`) |

The config file holds `{"servers": {"<ATIRA_API>": {"token": "atp_...", "token_id", "expires_at", "login"}}}`.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Done |
| 1 | Network or server error |
| 2 | Usage: unknown command or option, a missing argument, a folder that does not exist |
| 3 | Not signed in, sign-in cancelled or expired, or the server refused the credential (401, 403) |
| 4 | Not found (404) |
| 5 | Invalid request or package: a missing `agent.json`, over a limit, a 400 or 413 |
| 6 | Busy: a submission already in evaluation, 3 test runs already waiting, a rate limit, or cancelling a finished run (409, 429) |
| 7 | `logs --follow` or `test-run --follow`: the run failed or timed out; `submit --follow`: the submission did not complete |

With `--json`, an error is printed as `{"error": {"code", "message", "status"}}` on stdout.

## Final private evaluation: one attempt or best of three

The final runs your latest passed submission once, or up to three times if you opt in to **Best of 3** on your team
page or with `atira final --best-of 3` before the final run starts. Your best attempt counts. Details:
[Answers and scoring](https://ehl-challenge.atira.ai/docs/scoring.md#final-private-evaluation-one-attempt-or-best-of-three).
