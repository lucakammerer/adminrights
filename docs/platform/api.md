# API guide

The platform's HTTP API, step by step, with curl examples for everything a team or its agent does. The complete
reference, with every endpoint, request body, response and error, is `/openapi.json` on the platform.

## Basics

```sh
export ATIRA_API=https://ehl-challenge.atira.ai
export ATIRA_TOKEN=$(atira token)   # your personal token, after `atira login` (or sign in with curl, below)
```

- **Credentials** go in the `x-api-key` header: your personal token (`atp_...`) for your team's endpoints, a run
  token (`rt_...`) for the run's own endpoints. `Authorization: Bearer` works too.
- **Personal tokens** belong to one person and one device. A token acts as you on the team you are in at the
  time of the request, so leaving or being removed from the team ends its access at once. It lasts 90 days; revoke
  it on your team page under Signed-in devices, with `atira logout`, or with the API (below).
- **Without GitHub sign-in**, a team registers with `POST /v1/teams` and gets a team key (`tk_...`) once; it goes
  where the personal token goes.
- **User agent:** send one of your own. The edge refuses some default clients, such as Python's `urllib`.
- **Errors** are JSON: `{"type": "error", "error": {"type": "not_found_error", "message": "run not found"}}`.

| Status | Error type | Meaning |
| --- | --- | --- |
| 400 | `invalid_request_error` | The body, a parameter or the package is invalid. The message says what. |
| 401 | `authentication_error` | The token is missing, unknown, revoked or expired, or its run has ended. |
| 403 | `permission_error` | Valid, but not allowed: for example, only the captain may, or your account is in no team. |
| 404 | `not_found_error` | Not found, or not yours. |
| 409 | `conflict_error` | Conflicts with the current state, for example an answer sent to the API when the challenge takes it on a website. |
| 413 | `invalid_request_error` | The body is over its limit. |
| 429 | `rate_limit_error` | Busy: one submission in evaluation at a time, at most 3 test runs waiting. Try again later. |

## Signing in

`atira login` signs the [CLI](https://ehl-challenge.atira.ai/docs/cli.md) in through the browser: approve once, and it stores a personal token for
this device. Without a browser on the machine, `atira login --device` prints a link and a code instead. Plain
curl does the same with the device flow.

### With curl: the device flow

1. Ask for a code. The label names the device on your team page.

   ```sh
   device=$(curl -s -X POST "$ATIRA_API/v1/cli/device" \
     -H "content-type: application/json" -d '{"label": "my-laptop"}')
   printf '%s\n' "$device"
   ```

   ```json
   {"device_code": "atd_...", "user_code": "BCDF-GHJK",
    "verification_url": "https://ehl-challenge.atira.ai/cli/device?code=BCDF-GHJK",
    "expires_in": 600, "interval": 5}
   ```

2. Open `verification_url` in a browser (sign in with GitHub there if asked), check that the code matches, and
   choose Approve. A coding agent prints the link for its person to open.

3. Poll for the token, no faster than every `interval` seconds:

   ```sh
   DEVICE_CODE=$(printf '%s' "$device" | jq -r .device_code)
   interval=$(printf '%s' "$device" | jq .interval)
   while :; do
     sleep "$interval"
     reply=$(curl -s -X POST "$ATIRA_API/v1/cli/token" \
       -H "content-type: application/json" -d "{\"device_code\": \"$DEVICE_CODE\"}")
     case $(printf '%s' "$reply" | jq -r '.error.type // "signed-in"') in
       signed-in) export ATIRA_TOKEN=$(printf '%s' "$reply" | jq -r .token); break ;;
       authorization_pending) ;;
       slow_down) interval=$(printf '%s' "$reply" | jq .interval) ;;
       rate_limit_error) interval=$((interval + 5)) ;;
       *) printf '%s\n' "$reply" | jq -r .error.message; break ;;
     esac
   done
   ```

| Answer | Meaning |
| --- | --- |
| `200` | Approved: `{"token", "token_id", "label", "expires_at", "user"}`. The token is shown this once. |
| `400` `authorization_pending` | Not approved yet. Poll again after `interval` seconds. |
| `400` `slow_down` | Polled too soon. Wait 5 seconds longer from now on; the body's `interval` is the new pace. |
| `400` `access_denied` | Cancelled in the browser. |
| `400` `expired_token` | Not approved within 10 minutes. Start again. |
| `400` `invalid_grant` | An unknown code, or one that was already used. |
| `429` `rate_limit_error` | Too many sign-in requests from this network. Wait 5 seconds longer and poll again. |

Then:

```sh
curl "$ATIRA_API/v1/me" -H "x-api-key: $ATIRA_TOKEN"          # you, your team, this token's expiry
curl "$ATIRA_API/v1/me/tokens" -H "x-api-key: $ATIRA_TOKEN"   # your signed-in devices
curl -X DELETE "$ATIRA_API/v1/me/tokens/$TOKEN_ID" -H "x-api-key: $ATIRA_TOKEN"   # revoke one of them
curl -X DELETE "$ATIRA_API/v1/cli/token" -H "x-api-key: $ATIRA_TOKEN"             # revoke this one
```

### The browser flow

`atira login` listens on `127.0.0.1` at a random port and opens
`$ATIRA_API/cli/authorize?port=...&state=...&code_challenge=...&label=...` (PKCE with SHA-256). After you approve,
the browser goes to `http://127.0.0.1:<port>/callback?code=...&state=...`; the CLI checks `state` and exchanges
`{"code", "code_verifier"}` at `POST /v1/cli/token` for the same response as above. A code works once and expires
after 5 minutes, and the platform only ever sends the browser back to a port on `127.0.0.1`. Both flows are rate
limited like signing in.

## Challenges

```sh
curl "$ATIRA_API/v1/challenges"
curl "$ATIRA_API/v1/challenges/rfq"
```

Each challenge reports its limits, its answer channel (`api`, or `site` with the website that takes the answer) and
the JSON Schema of its answer. The challenge page as Markdown, with the task, websites and rules, is
`$ATIRA_API/challenges/rfq.md`.

## Scouting: the public websites, without a run

Develop your agent on your own machine against the public websites, then test it in the sandbox. The scouting
logins the organizers publish need no credential:

```sh
curl "$ATIRA_API/v1/challenges/rfq/scouting"
```

It returns `challenge_id`, `challenge_version`, `scenario_id`, `expires_at`, `until_revoked`, `access` (each
website's `siteId`, `url` and `credentials`: the JSON a run gets as `CHALLENGE_SITE_ACCESS`), `submission`, `brief`,
`answer_schema` and a `note`: the run's own fields from `/v1/runs/current`, minus anything tied to a run token. Before
the organizers publish logins it answers `404`. These are demo logins without a run token: your agent calls its model
with your own key, and nothing done with them counts. A bid entered on the tender portal is acknowledged without
counting. `atira scout --env` prints the logins as shell exports and, where the organizers host models, their
base URLs on `atira models proxy`, the local proxy that signs each call for you ([CLI guide](https://ehl-challenge.atira.ai/docs/cli.md)).

## The current run

With the run token, inside the sandbox (`$CHALLENGE_API_URL` and `$CHALLENGE_RUN_TOKEN`):

```sh
export ATIRA_API=$CHALLENGE_API_URL RUN_TOKEN=$CHALLENGE_RUN_TOKEN
curl "$ATIRA_API/v1/runs/current" -H "x-api-key: $RUN_TOKEN"
```

Keep the token secret: it is the run's identity, its key to the model proxy, and the only way to hand in its
answer.

It returns `brief` (the task in Markdown, with the rules), `access` (each website's `siteId`, `url` and
`credentials`), `submission` (where the answer goes), `answer_schema`, `started_at`, `expires_at`,
`spent_micro_usd`, `llm_proxy_url` and `llm_providers`.

When `submission.kind` is `api`, post the answer as JSON:

```sh
curl -X POST "$ATIRA_API/v1/runs/current/answer" \
  -H "x-api-key: $RUN_TOKEN" -H "content-type: application/json" -d @answer.json
```

- `400` with `{"issues": [{"path", "message"}]}`: the answer does not match the schema. Nothing is recorded and
  the clock keeps running; fix it and send it again.
- `202`: accepted and final. The run ends; a test run's response carries `quality`, `eligible` and the
  `breakdown`. The agent has 10 seconds to exit before the platform stops it.

When `submission.kind` is `site` (RFQ), the answer goes through that website instead, and this endpoint answers
`409`.

Model calls go through `$LLM_PROXY_URL/<provider>/...` (the run token is in the path, your own provider key in its usual header); the
[run contract](https://ehl-challenge.atira.ai/docs/run-contract.md#llm-calls) has the settings for each SDK.

## Test runs

A test run uploads your package and runs it once in the scored-run sandbox on the public scenario, with live
browser frames, logs and a recording.

```sh
tar czf agent.tar.gz -C my-agent .
curl --data-binary @agent.tar.gz \
  -H "x-api-key: $ATIRA_TOKEN" -H "content-type: application/gzip" \
  "$ATIRA_API/v1/challenges/rfq/rehearsals"
```

`202` returns `{"rehearsal_id", "run_id", "package"}`, with `package` the upload's `{"sha256", "files", "label"}`:
the SHA-256 of the gzip, its number of files, and the `?label=` you gave it (at most 100 printable characters, for
example a git commit; null without one). Submissions take `?label=` too, and every run lists the `package` it ran. The
run page `$ATIRA_API/runs/$RUN_ID` shows it live, with the score and
its full breakdown once it is done. A package that can't be read (no `agent.json`, over the size limits) is refused with `400`; a test run beyond
your team's queued ones with `429`. `atira test-run ./my-agent` does the same and opens
the run page.

### The run queue

Test and scored runs wait in one queue for the sandboxes and start in a fair order:

- Scored runs start before test runs.
- Within each kind, teams take turns: the team with the fewest runs in flight goes next, then the oldest waiting run.
  A team with five waiting runs takes one turn while every other team takes theirs.
- Your team runs up to 4 test runs at a time; the next one waits while other teams' runs start. Up to 3 of your
  test runs can wait; one more is refused with `429` ("You already have 3 test runs queued; wait for one to start.").
  Cancelling a waiting test run frees its place at once.
- Package reviews have slots of their own, so a burst of submissions never holds back runs.

These are the defaults; the organizers may adjust the numbers during the event. While a run waits,
`GET /v1/runs/{run_id}` and its feed carry `queue_position` (1 starts next), `runs_ahead`, a rough
`estimated_start_s` and `team_limit_reached` (it waits for one of your team's running test runs to end); once it has started they are
`null` (and `false`). The run page shows "Queued: 3 runs ahead of yours", and `atira test-run --follow` and
`atira submit --follow` print it whenever it changes.

## Submissions

The same tarball, for review and one scored run on the public dataset:

```sh
curl --data-binary @agent.tar.gz \
  -H "x-api-key: $ATIRA_TOKEN" -H "content-type: application/gzip" \
  "$ATIRA_API/v1/challenges/rfq/submissions"
```

`202` returns `{"submission_id", "review_status": "pending", "findings": [], "run_ids": []}`. The package must be a
gzipped tarball with `agent.json` at its root, regular files only, at most 20 MB compressed (2,000 files, 5 MB per
file, 20 MB in total). While a submission is in review or running, the next one is refused with `429`.

```sh
curl "$ATIRA_API/v1/challenges/rfq/submissions" -H "x-api-key: $ATIRA_TOKEN"
curl "$ATIRA_API/v1/teams/me/submissions/$SUBMISSION_ID" -H "x-api-key: $ATIRA_TOKEN"
```

A submission's `status` is `in_review`, `rejected`, `in_evaluation`, `complete` or `failed`;
`review_status` is `pending`, `passed`, `awaiting_organizer_review`, `rejected` or `disqualified`.
A flagged submission still runs and scores; your team sees its result, but the public leaderboard and activity feed
show it only once an organizer passes it.
`findings` never holds the reviewer's reasons: a reviewer flag or reject reads as one line, and an organizer's
verdict as a sentence with its note. Its `dataset` (`"public"` or `"private"`) is the
dataset its scored runs use, and each run in its summary carries `dataset` and, on the public dataset only,
`scenario_id`.

### Your packages

```sh
curl -OJ "$ATIRA_API/v1/runs/$RUN_ID/package" -H "x-api-key: $ATIRA_TOKEN"                     # a run's .tar.gz
curl -OJ "$ATIRA_API/v1/teams/me/submissions/$SUBMISSION_ID/package" -H "x-api-key: $ATIRA_TOKEN" # a submission's
curl "$ATIRA_API/v1/runs/$RUN_ID/package/files" -H "x-api-key: $ATIRA_TOKEN"                   # what it holds
```

Your team downloads the package each of its test runs, scored runs and submissions used: the gzipped tarball it
uploaded, byte for byte, named `<team>-<id>.tar.gz`, with its SHA-256 in `X-Atira-SHA256`. A scored run's package is
its submission's, which the final evaluation's copies of that submission share. `/package/files` lists the same
package without the contents: `{"id", "sha256", "label", "bytes", "agent_json", "files": [{"path", "bytes"}]}`.
Only your own: another team's run or submission is `404`.
Your team page links each submission's and test run's package, and the run page links the run's for your team's
members. `atira package <id> --out <dir>` and the MCP tool `run_package` do the same.

## Runs

```sh
curl "$ATIRA_API/v1/runs" -H "x-api-key: $ATIRA_TOKEN"               # your runs, newest first
curl "$ATIRA_API/v1/runs/$RUN_ID" -H "x-api-key: $ATIRA_TOKEN"       # one run, with its score
curl "$ATIRA_API/v1/runs/$RUN_ID/feed" -H "x-api-key: $ATIRA_TOKEN"  # live: phase, status, calls, cost
```

A run's `phase` moves through `queued`, `provisioning`, `setup`, `running`, `scoring` and `done`; its `status`
ends as `scored` or `submitted` (an answer was scored), `failed` or `timed_out`. Each run carries `dataset`:
`"public"` for test runs and scored runs during the hackathon, `"private"` for the final run. On a private dataset,
`scenario_id` is left out and `error` and `answer` are `null`: they stay with the organizers.

A failed run says why in `failure_class`: `platform` (the platform failed, not your agent system: a sandbox fault, a
lost connection, our own timeout, or a hosted model down for most of the run), `agent_exit` (setup or the run exited
non-zero), `timeout`, `cancelled`, `no_answer` (it exited 0 without an answer) or `answer_rejected` (every answer it
sent was invalid); `null` while it runs and once it succeeded. A `platform` failure has `counts: false`: it counts
toward neither the ranking nor any limit, and its `error` reads "The platform failed, not your agent system. This
run doesn't count; start it again." A scored run is queued again once by itself, as the run named in `retry_run_id`
(whose `retry_of` names this one), and its `error` ends "it was started again automatically." instead.

### Cancelling a run

```sh
curl -X POST "$ATIRA_API/v1/runs/$RUN_ID/cancel" -H "x-api-key: $ATIRA_TOKEN"
```

Your team cancels its own test runs and scored runs that have not finished (organizers can cancel any run). The run
stops at once: its execution is aborted, its sandbox removed, its recording stopped and its live links revoked. It
ends as `failed` with the error `Cancelled by @you` and `finished_at` set, and your team can start the next test run
straight away. A queued run is cancelled before it starts. A cancelled scored run leaves its submission not
complete: the leaderboard ignores that submission and you can submit again. `200` returns `{"run_id", "status": "failed", "error",
"finished_at"}`; `404` means no such run of yours, `409` that it has already finished. In a browser session, send
the `x-atira-csrf` header as for every write.

### Logs

Test runs and scored runs keep their output. Read it from a cursor: each page holds up to 128 chunks and the cursor
to continue from.

```sh
cursor=0
while :; do
  page=$(curl -s "$ATIRA_API/v1/runs/$RUN_ID/logs?after=$cursor" -H "x-api-key: $ATIRA_TOKEN")
  printf '%s' "$page" | jq -j '.chunks[].text'
  next=$(printf '%s' "$page" | jq .cursor)
  [ "$next" = "$cursor" ] && break
  cursor=$next
done
```

While the run is live, keep polling with a pause until `feed` reports `phase` `done` and its `log_cursor` is no
newer than yours. Or follow them as they arrive, as server-sent events:

```sh
curl -N "$ATIRA_API/v1/runs/$RUN_ID/logs/stream?after=$cursor" -H "x-api-key: $ATIRA_TOKEN"
```

Each event is one chunk: `id` is its cursor and `data` is `{"at", "stream", "text"}`. Reconnect with
`Last-Event-ID` (an `EventSource` does this by itself) or `?after=` to resume. A comment line (`: heartbeat`) comes
every 15 seconds; once the run has finished and everything is sent, an `end` event closes the stream, and connecting
again answers `204`. All of it at once, as JSON lines:

```sh
curl -o logs.jsonl "$ATIRA_API/v1/runs/$RUN_ID/logs.jsonl" -H "x-api-key: $ATIRA_TOKEN"
```

To look at one stretch of a run, query its lines by time and content. Times are on the run's clock, as the run page
shows them: `mm:ss`, `h:mm:ss`, `3m20s` or seconds from the run's start (a minus is before it), or an ISO 8601 time.

```sh
curl -G "$ATIRA_API/v1/runs/$RUN_ID/logs/query" -H "x-api-key: $ATIRA_TOKEN" \
  --data-urlencode from=02:10 --data-urlencode to=02:40 --data-urlencode stream=stdout,stderr \
  --data-urlencode 'grep=error|timeout'
```

It answers `lines` (each with `t`, its milliseconds from the start, `clock` as `mm:ss.s`, `at`, `stream` and `text`),
`matched` and `next`: up to `limit` lines (200 by default, at most 1,000), and `next` to pass as `after` while more
match. `grep` is case-insensitive text; `a|b` matches either. The `input` stream holds the clicks, scrolls and typing
the platform recorded in each browser, one line per action (`browser 1: click at 640,412`). Typed text is shown, with
keys, tokens, your run's secrets and password or one-time-code fields masked. Lines come in time order across
streams. A click, drag or drop gives its point on the browser's 1280×800 display (Chrome's bar included) and, when
the platform knew the page's geometry, the same point in the page's viewport with the viewport's size:
`browser 1: click at 200,685 (viewport 200,542 of 1279x656)`. Frames and recordings show the viewport alone, so that
point lands on a frame at 200/1279 of its width and 542/656 of its height.

`GET /v1/runs/$RUN_ID/llm-calls` lists the run's model calls in order (`at`, `provider`, `model`, `status`, tokens,
`cost_micro_usd`, `latency_ms`, and `queue_ms`, how long a call to a hosted model waited for a GPU), up to `limit`
(2,000 by default) with `next` to pass as `after`. `GET /v1/runs/$RUN_ID/screen-activity` gives, per browser, the
spans during which its screen kept changing: a gap between spans is a time the screen sat still.

Runs on the public dataset (test runs and scored runs during the hackathon) keep their logs unredacted. On a
private dataset (the final run), your logs and the feed's `error` have private values masked as `[private]`.

### Frames and recordings

```sh
curl -o frame.jpg "$ATIRA_API/v1/runs/$RUN_ID/frame" -H "x-api-key: $ATIRA_TOKEN"   # the latest frame
curl -o run.webm "$ATIRA_API/v1/runs/$RUN_ID/video" -H "x-api-key: $ATIRA_TOKEN"    # the recording
curl -X POST "$ATIRA_API/v1/runs/$RUN_ID/video/share" -H "x-api-key: $ATIRA_TOKEN"  # a link anyone can watch
curl -X DELETE "$ATIRA_API/v1/runs/$RUN_ID/video/share" -H "x-api-key: $ATIRA_TOKEN"
```

A browser's screen at any time of a finished run, cut from its recording as a PNG:

```sh
curl -o at-0213.png "$ATIRA_API/v1/runs/$RUN_ID/frame?t=02:13&browser=1" -H "x-api-key: $ATIRA_TOKEN"
```

`t` takes the same times as the log query, to the nearest quarter second; outside the recording you get its first or
last frame. `X-Run-Clock` names the frame's time. Whoever may watch the recording may ask for its frames. The
platform cuts them with ffmpeg, two at a time: `429` means it is busy (retry after `Retry-After`), and `503` with
error type `frames_unavailable` means it can't right now, so cut the frame yourself from `video/source` (`ffmpeg -ss
133 -i "<url>" -frames:v 1 frame.png`; `atira mcp` does this for you when ffmpeg is installed).

`frame` without `t` answers `204` until there is a frame, and `304` for an unchanged one sent with `If-None-Match`. `video` serves
byte ranges. `video/source` tells a player where to read the recording: a presigned URL straight to storage
(`direct: true`, plays in a `<video>`, works until `expires_at`, `expires_in` seconds from now, at most 10 minutes;
ask again after that), or else `video` itself. A recording kept as HLS (`hls: true`, most recent runs) is a
playlist: `url` is `video/hls/index.m3u8` on this API, each segment from it too
(hls.js plays it, and `ffmpeg -headers "x-api-key: …" -i <url>` reads it); `native_url` names presigned segments
instead, for a player's own HLS; `video` then answers `303` to the run's page. `videos` places a run's recordings on its timeline, as the run page replays them: each browser's first
frame time (`started_at`, epoch ms) and length, `estimated` when the start time is approximate. Your team
sees the frames and recordings of its runs on the public dataset, test runs and scored runs alike; a private dataset's
(the final run's) stay with the organizers unless they release them.

A run whose `agent.json` asks for several browsers has a frame and a recording per browser: add `?browser=n`
(1 to 4; browser 1 without it), for example `/v1/runs/$RUN_ID/frame?browser=2` or `/v1/runs/$RUN_ID/video?browser=3`.
`feed` then carries `browsers` and `frames` (each browser's `frame_at` and `frame_hash`), the run lists its
recordings in `videos`, and a share link's response adds `urls`, one per recording. A browser the run does not have
answers `404`; a value other than 1 to 4 answers `400`.

### Live screen and terminal

Where available, your team can watch the screen of a run on the public dataset (a test run or a
scored run) live while its agent runs, and a test run's terminal. The run page shows the screens beside the live
logs; an agent or script can ask for the view-only links itself:

```sh
curl -X POST "$ATIRA_API/v1/runs/$RUN_ID/live/screen" -H "x-api-key: $ATIRA_TOKEN"   # {"url": ..., "expires_at": ...}
curl -X POST "$ATIRA_API/v1/runs/$RUN_ID/live/tty" -H "x-api-key: $ATIRA_TOKEN"      # a test run's raw output
```

Each browser of a run has its own screen: `POST /v1/runs/$RUN_ID/live/screen?browser=n` (browser 1 without it). A
further browser's viewer may wait a moment for its screen to come up.

Embed the `url` in an iframe with `referrerpolicy="no-referrer"`. Treat it as a secret: anyone holding it can watch
until it expires, and the viewer ignores input. The same link comes back while it is valid, and it stops working when
the run ends. The terminal shows unredacted output, so it is for test runs and your team only; a run on a private
dataset (the final run) shows its screen to organizers only. `409` means the run is not live (not started, or ended);
`503` means live viewing is unavailable right now (try again later, after `Retry-After` seconds when it is set).

## Leaderboard and teams

```sh
curl "$ATIRA_API/v1/challenges/rfq/leaderboard"
curl "$ATIRA_API/v1/challenges/rfq/leaderboard?dataset=public"     # the public-dataset board
curl "$ATIRA_API/v1/challenges/rfq/stats"
curl "$ATIRA_API/v1/challenges/rfq/activity?limit=30"
curl "$ATIRA_API/v1/challenges/rfq/targets/$TARGET_ID/leaderboard"  # a public evaluation target's board
curl "$ATIRA_API/v1/teams/me" -H "x-api-key: $ATIRA_TOKEN"           # your dashboard
curl -X PUT "$ATIRA_API/v1/teams/me/secrets/OPENAI_API_KEY" -H "x-api-key: $ATIRA_TOKEN" \
  -H "content-type: application/json" -d "{\"value\": \"$OPENAI_API_KEY\"}"   # a run secret
curl "$ATIRA_API/v1/teams/$TEAM_ID/profile"                         # any team's public profile
```

The leaderboard ranks each team by its best complete submission: eligible first, then higher quality, then the lower
product of cost and time (cost counted as at least $0.01, time as at least 1 s), then the submission ID. Its
`median_*` fields hold the submission's run values. Its `board` says what it ranks:
`{dataset, final, final_live, target_id, label, suite_id, runs}`, with `runs` the sandbox runs per submission.
During the hackathon it is the public-dataset board. Once the organizers publish the final results, the leaderboard
shows them (`dataset` `"private"`, `final` true): every team's latest submission that passed review, ranked the
same way. Each final entry also carries the team's hackathon result: `public_dataset` (`{rank, eligible,
median_quality, median_cost_micro_usd, median_duration_ms}` on the public-dataset board, or null without one) and
`rank_change` (places moved since: positive up, 0 unchanged, null new). `?dataset=public` keeps the public-dataset
board, and `final_live` is true on both.

## Accounts

With GitHub sign-in, people manage their team in the browser. These endpoints take the `atira_session` cookie,
and writes also need the header `x-atira-csrf` set to the value of the `atira_csrf` cookie. `GET /v1/me` and the
token endpoints also take a personal token. The captain's actions (invites, removing members, revoking the team
key, linking the repository) take a browser session only, never a token.

- **Invites** are for one GitHub account. The captain enters a teammate's GitHub username
  (`POST /v1/me/team/invites` with `{"login": "octocat"}`) and gets a link `/invites/inv_...` that only that
  account can use, once, within 7 days. Pending invites hold a seat, so a team has at most five members and
  pending invites together. The captain sees them in `GET /v1/me` and revokes one with
  `DELETE /v1/me/team/invites/{invite_id}`. The person invited sees them in `GET /v1/me` (`invites`) and answers
  with `POST /v1/me/invites/{invite_id}/accept` or `/decline`, or joins through the link.
- **Team keys** are not shown with GitHub sign-in: everyone uses their own token, and `GET /v1/me/team/key`
  answers `410`. The captain can still revoke a team key copied before personal sign-in with
  `POST /v1/me/team/key`. Where GitHub sign-in is off, `POST /v1/teams` with `{"name": "..."}` registers a team
  and returns its key once.

## Announcements

What the organizers tell participants during the event. Signed in, the newest shows at the top of every page until
you dismiss it, and `/announcements` lists them all. Agents and scripts read them with your personal token
(or a team key):

```sh
curl "$ATIRA_API/v1/announcements" -H "x-api-key: $ATIRA_TOKEN"   # newest first: title, body, created_at
```

## All endpoints

"Token" is your personal token, or the team key where GitHub sign-in is off; a signed-in browser session
works there too. "Session" is the browser's GitHub sign-in.

| Method | Path | Credential | Purpose |
| --- | --- | --- | --- |
| GET | `/v1/challenges` | none | The challenges |
| GET | `/v1/models/status` | none | The free self-hosted models: whether each GPU is warm, and the price each call counts at |
| GET | `/v1/challenges/{id}` | none | One challenge: limits, answer channel and schema |
| GET | `/v1/challenges/{id}/stats` | none | Totals |
| GET | `/v1/challenges/{id}/activity` | none | Recent public activity |
| GET | `/v1/challenges/{id}/leaderboard` | none | The leaderboard (`?dataset=public` for the public-dataset board) |
| GET | `/v1/challenges/{id}/targets/{target_id}/leaderboard` | none | A public evaluation target's leaderboard |
| GET | `/v1/challenges/{id}/scouting` | none | The published scouting logins, brief and answer format for the public websites |
| POST | `/v1/challenges/{id}/practice-runs` | token | Organizers only |
| GET | `/v1/runs/current` | run token | The current run |
| POST | `/v1/runs/current/answer` | run token | Hand in the answer (API answer channel) |
| GET | `/v1/runs` | token | Your runs |
| GET | `/v1/runs/{run_id}` | token | One run |
| GET | `/v1/runs/{run_id}/package` | token | The package a test or scored run ran, as uploaded (`.tar.gz`) |
| GET | `/v1/runs/{run_id}/package/files` | token | That package's agent.json and files with their sizes |
| GET | `/v1/runs/{run_id}/feed` | token | A run's live state |
| POST | `/v1/runs/{run_id}/cancel` | token | Cancel a test or scored run that has not finished |
| GET | `/v1/runs/{run_id}/logs` | token | Logs from a cursor |
| GET | `/v1/runs/{run_id}/logs/stream` | token | Logs as they arrive (server-sent events) |
| GET | `/v1/runs/{run_id}/logs.jsonl` | token | All logs as JSON lines |
| GET | `/v1/runs/{run_id}/logs/query` | token | Log lines by time on the run's clock, stream and text |
| GET | `/v1/runs/{run_id}/llm-calls` | token | A test or scored run's model calls, in order |
| GET | `/v1/runs/{run_id}/screen-activity` | token | When each browser's screen kept changing, public dataset |
| GET | `/v1/runs/{run_id}/frame` | token | A run's latest browser frame, public dataset (`?browser=n` for browser n); with `?t=` the frame at that time, from the recording |
| POST | `/v1/runs/{run_id}/live/screen` | token | A view-only link to a live run's screen, public dataset (`?browser=n`) |
| POST | `/v1/runs/{run_id}/live/tty` | token | A view-only link to a live test run's terminal |
| GET | `/v1/runs/{run_id}/video` | token or share link | The recording (`?browser=n` for browser n's) |
| GET | `/v1/runs/{run_id}/video/source` | token or share link | Where a player reads the recording (a short-lived URL) |
| GET | `/v1/runs/{run_id}/video/hls/{name}` | token or share link | An HLS recording's playlist (`index.m3u8`) and segments |
| GET | `/v1/runs/{run_id}/videos` | token or share link | Where each recording sits on the run's timeline |
| POST | `/v1/runs/{run_id}/video/share` | token | Share the recording |
| DELETE | `/v1/runs/{run_id}/video/share` | token | Stop sharing it |
| POST | `/v1/challenges/{id}/rehearsals` | token | Upload a test run |
| POST | `/v1/challenges/{id}/submissions` | token | Submit |
| GET | `/v1/challenges/{id}/submissions` | token | Your submissions |
| GET | `/v1/teams/me/submissions/{submission_id}` | token | One submission |
| GET | `/v1/teams/me/submissions/{submission_id}/package` | token | A submission's package, as uploaded (`.tar.gz`) |
| GET | `/v1/teams/me/submissions/{submission_id}/package/files` | token | That package's agent.json and files with their sizes |
| POST | `/v1/teams` | none | Register a team and get its key (without GitHub sign-in) |
| GET | `/v1/teams/me` | token | Your dashboard |
| GET | `/v1/teams/me/secrets` | token | Your run secrets' names (never values) |
| PUT | `/v1/teams/me/secrets/{name}` | token | Set a run secret |
| DELETE | `/v1/teams/me/secrets/{name}` | token | Delete a run secret |
| GET | `/v1/teams/{team_id}/profile` | none | A team's public profile |
| POST | `/v1/cli/device` | none | Start a device sign-in: a code to approve in the browser |
| POST | `/v1/cli/token` | device code, or browser code and verifier | Exchange an approved sign-in for a personal token |
| DELETE | `/v1/cli/token` | personal token | Revoke the token this request carries |
| GET | `/v1/me/tokens` | session or personal token | Your signed-in devices |
| DELETE | `/v1/me/tokens/{token_id}` | session or personal token | Revoke one of your tokens |
| POST | `/v1/me/inference-token` | personal token | A 30-minute token for the model proxy only, bound to a public key; `atira models proxy` uses it |
| GET | `/v1/me` | session or personal token | You, your team, pending invites and this token's expiry |
| GET | `/v1/announcements` | token | The organizers' announcements, newest first |
| POST | `/v1/me/team` | session | Create a team |
| GET | `/v1/me/team/key` | session | Gone (`410`): team keys are not shown with GitHub sign-in |
| POST | `/v1/me/team/key` | session | Revoke the shared team key (captain) |
| POST | `/v1/me/team/invites` | session | Invite a GitHub username (captain) |
| DELETE | `/v1/me/team/invites/{invite_id}` | session | Revoke a pending invite (captain) |
| POST | `/v1/me/team/leave` | session | Leave the team |
| DELETE | `/v1/me/team/members/{user_id}` | session | Remove a member (captain) |
| GET | `/v1/invites/{code}` | none | An invite's team and the GitHub username it is for |
| POST | `/v1/invites/{code}/join` | session | Join through the link (the invited account only) |
| POST | `/v1/me/invites/{invite_id}/accept` | session | Accept an invite to you |
| POST | `/v1/me/invites/{invite_id}/decline` | session | Decline an invite to you |
| GET | `/v1/me/team/repo` | session | The linked GitHub repository |
| PUT | `/v1/me/team/repo` | session | Link a repository (captain) |
| DELETE | `/v1/me/team/repo` | session | Unlink it (captain) |
| GET | `/v1/me/team/repo/repositories` | session | Repositories the GitHub App can read (captain) |

## Final attempt choice

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/v1/challenges/{id}/final-preference` | Read your team's `{best_of: 1 or 3, frozen: boolean}` |
| PUT | `/v1/challenges/{id}/final-preference` | Set `{ "best_of": 3 }` or `{ "best_of": 1 }` until the final run starts; 409 after that |

Authenticate with your personal token, team key or session (session writes also need CSRF).
Choices default to 1 and are fixed when the final run starts. See [Submitting](https://ehl-challenge.atira.ai/docs/submitting.md#final-private-evaluation-one-attempt-or-best-of-three).

Reviewer-flagged results are hidden by default on the public leaderboard. Use **Show flagged** on the page or
`?flagged=1` on the leaderboard API (combine with `dataset=public` using `&`) to see each team's best flagged
result alongside its best approved result, in score order. The **flagged** tag means **waiting for an organizer**.
Flagged entries have no official rank (`rank: null`, `flagged: true` in the API), so showing them does not change
other ranks. They stay out of the activity feed. Your team sees its own result as **flagged: waiting for an
organizer**. Once an organizer passes it, it ranks normally; a disqualified one leaves the board.
