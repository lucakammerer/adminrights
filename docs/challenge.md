# Challenge

Sources: [rfq.md](https://ehl-challenge.atira.ai/challenges/rfq.md), [scoring](https://ehl-challenge.atira.ai/docs/scoring.md),
[fair play](https://ehl-challenge.atira.ai/docs/fair-play.md), [run contract](https://ehl-challenge.atira.ai/docs/run-contract.md),
[submitting](https://ehl-challenge.atira.ai/docs/submitting.md). If anything here contradicts them or the run's brief,
they win.

## Frame

| | |
| --- | --- |
| Scored run | 20 min; setup before it up to 5 min with network, not counted |
| Test run | up to 2 h, up to 4 at once, points per field |
| Submission | one at a time, AI review first |
| Browsers | up to 4 (`"browsers"` in `agent.json`), any number of tabs, no browsers of our own |
| Sandbox | 4 vCPU, 8 GB, 1280×800; only the platform, the websites and the model proxy are reachable |
| Answer | entered in the tender portal's configurator, signed with a TAN from the mailbox |

## Models

| Model | Price (simulated) | Limit | Use |
| --- | --- | --- | --- |
| Qwen3.8-Flash-Next | $0.15/M in, $0.016/M cached, $0.47/M out | 32 concurrent per team | everything |
| Cloudflare Clef | $0.24/M in | 16 concurrent per team | unused; only if measurably faster |

## Scoring (bid)

Decision 5, reference 5, discount 5, total 5, arithmetic 5, when present: withdrawn Q&A 5, dated metal index 5. The
rest is split across positions: material 20 %, quantity 15 %, base price 15 %, surcharge, packaging, project bonus,
final unit price, lead time 10 % each. Extra or duplicate positions cost one position's share each.

No bid: decision 75, reference 5, no positions 5, total of 0 15.

## Ranking and winners

Run: eligible → quality → cost × time (cost at least $0.01, time at least 1 s).
Leaderboard: best submission. Final: **latest** passed submission, on the private dataset, optionally best of 3.
Winners: private dataset → public dataset → elegance.
