# Runs

One row per finished test run or submission, newest first. Platform = quality the platform scored; eval = the
logged answer scored by `eval/compare.py` (what the bid would have scored if signed). Time and cost from the platform.

| Date (UTC) | Run | Commit | Platform | Eval | Time | Cost | Outcome and top problem (owner) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-10 13:25 | run_20006bcd3b22b010 | aee8fa5 | 0, not eligible | 59.2 | 18 min | $0.240 | Not signed. ERP check for one requirement hung in `extract` until the phase cut (end − 6 min), so 1 position omitted and submit started at 784 s; submit agent needed > 300 s for 4 positions and ran out (P1, P2). |
| 2026-10-10 13:03 | run_6229f3f11bd1f820 | b370911 | 0, not eligible | 37.1 | 19 min | $0.192 | Not signed. Requirements resolver done at 711 s, 3 of 5 positions unfinished, submit got 7 s (P1). |
| 2026-10-10 12:39 | run_cd5e913b64e54387 | 849e84d | 5, eligible | – | 15 min | $0.228 | Signed no_bid: an ERP `finish` arrived as a broken string, the empty result became no_bid. Fixed in b370911 and f79fc7f. |
| 2026-10-10 12:25 | run_937708e521482d3f | pre-849e84d | 0, not eligible | – | 13 min | $0.214 | Crash in the number parser on a price with a trailing minus. Fixed in 6b70077. |
