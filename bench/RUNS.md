# Runs

One row per finished test run or submission, newest first. Platform = quality the platform scored; eval = the
logged answer scored by `eval/compare.py` (what the bid would have scored if signed). Time and cost from the platform.

| Date (UTC) | Run | Commit | Platform | Eval | Time | Cost | Outcome and top problem (owner) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-10 15:19 | run_c375163ce77eeeac | base@521effe | 42.1, eligible | 42.10 | 16 min | $0.200 | Signed with 2 of 5 positions. Requirements now right (01.05 = 130, withdrawn answer handled; Luca 2fc3d2a works); verify_summary called. Phase 1 ran to 533 s: the tender agent's finish step alone took 132 s writing positions and every Q&A word for word (Finn I5, Yazan: tender finish schema), so the ERP phase had 2 min and 3 searches were forced before stock and prices were kept (Finn: budgets I4). |
| 2026-10-10 15:11 | run_92b5cd73ec344361 | base@e30753d | 0, not eligible | – | 1 min | $0.000 | Crashed at 4 s: the first page.goto to the mailbox timed out (30 s) and the exception ended the run (Finn: agent.py; fixed in 92affb8: `first load failed` is now logged and the agent opens the URL itself). |
| 2026-10-10 14:46 | run_b3273156b4f8a14f | base@8d23e00 | 70.1, eligible | 70.05 | 17 min | $0.219 | First signed bid, all 5 positions, answer at 643 s. Requirements took 01.05 at the tender quantity (110 instead of 130): it trusted the tender agent's summary, which dropped a valid change after a withdrawn answer; cascades into pool and bonus of 01.03–01.05 (Luca: prompt fixed in 2fc3d2a; Yazan: tender summary incomplete). Requirements took 179 s (slow model). |
| 2026-10-10 14:15 | run_49c614eb0548f71d | base@e8f4da3 | 0, not eligible | 50.10 | 21 min | $0.151 | Not signed. Two ERP agents cut at end − 6 min (2 positions omitted); one submit model call hung 371 s (llm timeout 360 s), submit ran out at 1253 s (Finn: fixed on main by a227bb6, deadline-bounded calls). Requirements with all mail: 66 s instead of 34 s, correct (Luca: back to technical mail, c0ccfec). |
| 2026-10-10 13:25 | run_20006bcd3b22b010 | aee8fa5 | 0, not eligible | 59.2 | 18 min | $0.240 | Not signed. ERP check for one requirement hung in `extract` until the phase cut (end − 6 min), so 1 position omitted and submit started at 784 s; submit agent needed > 300 s for 4 positions and ran out (P1, P2). |
| 2026-10-10 13:03 | run_6229f3f11bd1f820 | b370911 | 0, not eligible | 37.1 | 19 min | $0.192 | Not signed. Requirements resolver done at 711 s, 3 of 5 positions unfinished, submit got 7 s (P1). |
| 2026-10-10 12:39 | run_cd5e913b64e54387 | 849e84d | 5, eligible | – | 15 min | $0.228 | Signed no_bid: an ERP `finish` arrived as a broken string, the empty result became no_bid. Fixed in b370911 and f79fc7f. |
| 2026-10-10 12:25 | run_937708e521482d3f | pre-849e84d | 0, not eligible | – | 13 min | $0.214 | Crash in the number parser on a price with a trailing minus. Fixed in 6b70077. |
