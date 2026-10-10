# RULES: the reference for the RFQ challenge

> The single source of truth for **what we must deliver and how it is judged**. Every design decision, PR and
> submission is checked against this file. If something here is wrong or unclear, fix this file first, then the code.
>
> Sources: `challenge-rfq.md` (challenge page), `run-brief.md` (the brief a run receives), `fair-play.md`,
> `run-contract.md`, `building-an-agent.md`, `submitting.md`, `scoring.md` (all in `docs/`, fetched 2026-10-10),
> plus our own scouting (`scouting-notes.md`).

---

## 0. How to read this file

Rules are ranked from **strictest** to **most lenient**. Each rule has an ID that code, tests and PRs cite.

| Tier | Name | Breaking it means | Default check |
| --- | --- | --- | --- |
| **T0** | BLOCKER | package rejected, flagged or team disqualified: the run never counts | automated pre-submit gate + human review |
| **T1** | HARD | run scores 0 or is ineligible | runtime guard + end-to-end test |
| **T2** | SCORE | loses specific quality points | unit tests on the calculator + local scorer |
| **T3** | RANK | worse tie-breaker (cost × time) | run metrics dashboard |
| **T4** | CRAFT | worse "elegance", slower team, harder debugging | code review |

Wording: **MUST** / **MUST NOT** = no exceptions. **SHOULD** = default, deviations need a written reason in the
PR. **MAY** = free choice.

---

## 1. What we deliver

| # | Deliverable | Where it counts |
| --- | --- | --- |
| D1 | An **agent package**: gzipped tarball, `agent.json` at its root, ≤ 20 MB compressed | review, every run |
| D2 | A **signed bid** entered in the tender portal's configurator within the run's time limit (20 min scored) | quality, eligibility, cost, time |
| D3 | A **scored submission** on the public dataset (leaderboard, ranks by best submission) | winners criterion 2 |
| D4 | Our **latest submission that passed review** at hackathon end runs on the **private dataset** (once, or best of 3 if we opt in) | winners criterion 1 (weighs most) |
| D5 | An **elegant system**: clear architecture, readable code, honest README | winners criterion 3 |

Winner order: **private-dataset performance → public-dataset performance → elegance.**
Ranking inside a dataset: **eligible → quality ↓ → cost × time ↑** (cost floor $0.01, time floor 1 s).

---

## 2. T0: BLOCKERS (fair play and platform)

| ID | Rule | Check |
| --- | --- | --- |
| **T0.1** | MUST NOT hardcode any value copied from the public scenario or its websites: tender references, material numbers, keys (K-/VP-/TZ-/RP-/PB-/ER-/FX-/MET-…), prices, quantities, totals, discounts, dates, logins, TANs, receipt numbers. This covers code, config, prompts, few-shot examples, notes, defaults and fallbacks. | `tools/audit_hardcode.py`: denylist built from `docs/scouting-notes.md` + `docs/scout-public-expected.py`, grep over the package. **Blocks the release.** |
| **T0.2** | MUST NOT ship site-specific navigation: no public-site URLs, paths (`/mm03`, `/documents/specification`…), element ids or click sequences. Navigation targets come from the model at run time. Generic heuristics (e.g. "a modal dialog with a close button") are fine. | audit greps for site hostnames and known paths; code review |
| **T0.3** | A **language model** MUST choose navigation targets, searches and relevant documents from observations at run time, and make the important decisions. | architecture (see plan §4); review checklist |
| **T0.4** | Helpers MAY: extract a page the model selected, parse a document the model selected, paginate a result set the model selected, calculate, validate, retry, fill forms. Helpers MUST NOT autonomously discover and traverse the sites to assemble the evidence before model-directed investigation (**no crawler**, **no fixed script with the model as fallback**). | code review: every navigation call traces back to a model decision in the run trace |
| **T0.5** | MUST NOT pre-solve: no answer computed by us (or by an AI assistant) shipped in the package. `docs/scout-public-expected.py` is a dev-only oracle and MUST NOT be in the package. | package is built from `agent/` only; audit checks file list |
| **T0.6** | Model calls MUST go only through the platform proxy (`*_BASE_URL`, `LLM_PROXY_URL`). MUST NOT bundle or run a local model. Own keys only as **team secrets**, never in the package. | grep for API keys; config reads env only |
| **T0.7** | MUST NOT contact hosts other than the platform API and the 4 challenge websites. MUST NOT exfiltrate data. | no outbound code except proxy + site URLs from `access` |
| **T0.8** | MUST NOT start browsers in the sandbox. Use only `CDP_URLS` (≤ 4, declared via `"browsers"` in `agent.json`). Tabs and contexts inside them are fine. Locally we may launch our own. | `browser/pool.py` launches only when `CDP_URLS` is unset |
| **T0.9** | MUST NOT attack the platform, the websites, the sandbox or other teams; MUST NOT share scored-run data. | team agreement |
| **T0.10** | MUST NOT put text in the package that tries to steer the AI reviewer's verdict. Factual README is fine. | review |
| **T0.11** | Facts the brief states for every scenario (company name, VAT id, the sales director's mailbox pattern, authorized subject/sender pairs, rules) MAY be used, but SHOULD be **read from the run's brief at run time**, not typed into code. | brief compiler reads them; audit |

## 3. T1: HARD (run validity and eligibility)

| ID | Rule | Check |
| --- | --- | --- |
| **T1.1** | `agent.json` valid: `setup`, `run`, `models` ⊆ hosted ids (`qwen`, `clef`), `browsers` integer 1–4. | `tools/check_package.py` |
| **T1.2** | `setup` finishes in < 5 min with network only for installs; no credentials there. | test run log |
| **T1.3** | The run MUST submit an answer before `expires_at` (scored: 20 min). No answer = 0 and ineligible. **Always submit something.** | Time Keeper deadline ladder (plan §8); chaos test with injected slowness |
| **T1.4** | **Eligibility = exact tender reference.** Read it from the brief and confirm it on the portal (clean value: `aria-label` / zero-width characters stripped). Never the look-alike (`…-A`). | ledger validator: reference equals brief reference, character for character |
| **T1.5** | Exactly **one** submission; submitting ends the run. The final "verbindlich abgeben" step MUST be executed once, only after the answer passes all validators. | Notary state machine has a single terminal transition |
| **T1.6** | The answer MUST match `answer_schema` (read from the run, not hardcoded). Money as numbers, quantity and lead time as integers, currency `EUR`, ≤ 100 positions, `notes` ≤ 4000 chars. | `jsonschema` validation before signing |
| **T1.7** | The site form takes **German number format** for prices and total ("2.614,68"). | formatter unit test |
| **T1.8** | Signing: TAN from the webmail, valid **5 min**; a new TAN request invalidates the previous one. Request the TAN **only** when every field is entered; use the newest TAN for the exact reference that arrived after our request. | Notary/mail handshake test |
| **T1.9** | Saving alone is not scored: the bid MUST be **signed and submitted**, including when positions are omitted. | end-to-end test asserts a receipt |
| **T1.10** | Read the run from `GET /v1/runs/current` with `x-api-key`; send our own User-Agent (the edge refuses Python's default urllib agent). | starter-kit `run.py` |
| **T1.11** | Session expiry loses unsaved entries; "Zurück" (back) clears later wizard steps. The Notary MUST NOT go back after later steps exist unless it re-enters them. | Notary design |

## 4. T2: SCORE (the bid rules, formalized)

### 4.1 Points (what each rule is worth)

**Bid case (100 points):**

| Part | Points |
| --- | --- |
| Decision (`bid`) | 5 |
| Tender reference | 5 |
| Discount percent | 5 |
| Total net (to the cent, consistent with positions) | 5 |
| Arithmetic consistency (each position + total = sum) | 5 |
| Withdrawn-Q&A quantity check *(when present)* | 5 |
| Dated metal-index check *(when present)* | 5 |
| **Positions** (75 minus present checks, split evenly per position) | 65 in public (both checks present) |

Per position: **material 20 %, quantity 15 %, base price 15 %, surcharge 10 %, packaging 10 %, project bonus 10 %,
final unit price 10 %, lead time 10 %.** Every field scores on its own. Money is compared **to the cent**. Positions
are matched by number; **extra or duplicate positions cost one position's share each.**

**No-bid case (100 points):** decision **75**, tender reference 5, no positions 5, total 0 → 15. A wrong decision
costs its points but leaves other fields their credit.

> **Consequence:** the bid/no-bid decision is the single most valuable judgement (75 points when no_bid is right,
> and a wrong no_bid throws away ~75 position points in a bid case). It gets a **proof requirement** (T2.3b).

### 4.2 Notation

- `S` = scenario datetime (from the brief, UTC). `T` = tender reference (exact). `D` = bidder mailbox domain.
- `r2(x)` = round **HALF_UP** to 0.01. All money in `Decimal`, never float, until the final JSON.
- **`LATEST(kind, key)`** = among records of that kind and key that are (a) for **exactly** `T`, (b) from the
  **authorized sender** for that subject (local part from the brief + `@D`), (c) dated **≤ S**, the one with the newest
  datetime. Newer replaces older. Records for other references and future-dated records **never** apply. A failed
  condition does **not** revive an older record.

### 4.3 The rules

| ID | Rule (precise) | Pitfalls seen in public | Check |
| --- | --- | --- | --- |
| **T2.1 Quantity** | `q_unit = BoQ quantity`, overridden by the **latest dated** Q&A answer (≤ S) that changes **that** position, ignoring **withdrawn** answers (a later answer withdraws an earlier one by its number). Then `q = q_unit × pieces_per_set` if the unit is *Satz* (pieces per set from the **governing** spec), else `q = q_unit`. Bid quantities are always **pieces**. Carton rounding never changes `q`. | Q&A numbers are not in date order; the latest change (32) was withdrawn → 26 Satz × 5 = 130; dates in Athens time; quantity also drawn on canvas | calc tests: withdrawal, unit conversion, ordering by date, not by number |
| **T2.2 Governing revision** | The specification revision **marked current** (status "gültig"/current), **not** the first shown and not by number. Superseded revisions never apply. | portal opens the oldest revision first; status only in a tooltip; dates in mixed DD/MM vs MM/DD | ledger validator: exactly one current revision |
| **T2.3 Requirement + amendments** | Requirement attributes from the governing revision; then apply Q&A **technical amendments that name that revision and that requirement**, only the named attributes, the latest dated (≤ S) per attribute. Amendments to other revisions never apply. | two amendments for the same attribute (485 → 482) | calc tests |
| **T2.3a Derivation** | If a requirement's stroke is a *nutzbarer Weg* (usable stroke): nominal = amended usable + **2 ×** end reserve, from `LATEST(Technikfreigabe/technik, end-reserve key)` for **that revision**. Other attributes unchanged. | 482 + 2×9 = 500; 576 + 2×12 = 600 | calc tests |
| **T2.3b Material** | Search the ERP by the requirement's **Kataloggruppe** (narrow, ≤ 20 hits). Candidate qualifies iff bore, (nominal) stroke, pressure, mounting, certification are **all exactly equal** and its status is **active** (blocked = status "gesperrt"). If **any** position has no qualifying material → **no_bid** for the whole tender. **Proof rule:** no_bid requires an *absence proof* (the group search listed and every candidate checked, plus one independent search) and the Auditor's sign-off; bid requires a *presence proof* per position. | identical-looking blocked material; Flansch vs Schwenkauge; 125/325 vs 125/300; certification in a tooltip | ledger validator + no-bid mutation test |
| **T2.4 Price condition** | The condition **valid at S** (both endpoints inclusive). Normalize by its **price unit** (per 1 or per 100 pieces), choose the scale with the **highest minimum quantity ≤ q** of **this position** (not the material sum). If the currency is not EUR, convert with `LATEST(Devisenfixing/finanzen, FX key)` (EUR per currency unit) and **r2**. This EUR value is `base_unit_price` and is used everywhere after (threshold, bonus, final price). | 2026 vs 2027 conditions; price unit 100; "64,853 (en-US)" = 64 853 per 100 pcs; "181.429 (de-DE)" = 181 429 per 100; future-dated FX decoy | number-parser tests + calc tests |
| **T2.5 Discount** | `LATEST(approval, leitung@D)` for exactly `T`. If it states a **minimum undiscounted net order value**: `V = r2(Σ q × base_unit_price)` (no surcharges, no setup, no packaging); `V ≥ threshold` (inclusive) → its percentage, else **0 %**, no fallback to older approvals. No approval → 0 %. For no_bid a conditional approval yields 0 %. | look-alike ref `…-A`; requests from vertrieb@ are not approvals; "Angebotsprüfung" is not an approval; a decoy "draft value 99 %" block in every mail | calc tests |
| **T2.6 Clause** | A position's *Konditionsgruppe* (from Q&A) is resolved in `LATEST(Konditionsregeln, kalkulation@D)`. Its prose maps to **one of three**: `BASE_ONLY`, `BASE_AND_SURCHARGE`, `NONE`. No group → `BASE_ONLY`. Setup fees are **never** discounted. The order-level percentage and threshold don't change. | three prose variants | interpreter tests (prose → enum) + calc tests |
| **T2.7 Metal surcharge** | `surcharge_mass_kg × rate`, rate from the latest exact-reference *Preisindizes* message from kalkulation@D; if it lists validity windows, use the window that **contains S** (inclusive), not the last listed. Mass is the **surcharge mass** (Zuschlagsmasse), not the allocation mass. | look-alike ref; 3 windows | worth an extra 5-point check |
| **T2.8 Setup** | Ordinary setup per position (from Q&A, one-off EUR) + allocated **shared setup pool** (Rüstpools): one pool fee from `LATEST(Rüstpools/kalkulation)`, allocated over pool members by weight `q × allocation mass` (Umlagegewicht, ≠ surcharge mass) using the mail's cent rule: floor to cents, remaining cents to the largest remainders, ties by ascending position id. | two different masses on each material | allocation tests |
| **T2.9 Packaging** | Tariff key from Q&A → `LATEST(Verpackungstarife/logistik)`. `cartons = ceil(q / pieces_per_carton)` **per position** (no pooling). Never discounted. `packaging_per_unit = r2(cartons × tariff / q)`. | look-alike ref with a different tariff | calc tests |
| **T2.10 Project bonus** | Plan key from Q&A → `LATEST(Projektbonus/finanzen)`. Eligible base `B = Σ q × base_unit_price` over member positions (undiscounted, no surcharges/packaging). Credit = Σ over **marginal** bands of `rate × portion in band`, **r2 once**. Allocate cents proportional to each member's `q × base` by largest remainder (ties ascending id). `rebate_total` = the position's allocated credit (**whole position, not per piece**); non-members `0.00`. Never discounted again. | marginal, not flat | allocation tests |
| **T2.11 Final unit price** | `unit = r2( base·(1−d·[clause covers base]) + sur·(1−d·[clause covers surcharge]) + (setup + pool_alloc + carton_cost − bonus_alloc) / q )` using **unrounded** components and rounding **once**. Never feed rounded report fields back in. | | golden test vs oracle |
| **T2.12 Lead time** | If the position has a delivery commitment key: `c = LATEST(Terminfreigabe/logistik, key)`; apply `c.weeks` iff `c.material == selected material` **and** the pooled demand (Σ q over all positions selecting that material) ≤ `c.ceiling` (inclusive). Otherwise shared stock: if **available** stock (unrestricted only, not inspection/blocked stock) ≥ pooled demand → from-stock lead time for **all** those positions, else production lead time for all. No partial allocation. | physical stock includes inspection stock (99 vs 31 available) | calc tests |
| **T2.13 Total** | `total_net = r2(Σ q × unit)`. MUST equal the sum of the submitted positions (arithmetic points). | | validator |
| **T2.14 Report fields** | `base_unit_price` = T2.4; `surcharge_per_unit = r2(metal surcharge + (ordinary setup + pool alloc)/q)` **before discount**, excluding packaging and bonus (confirmed by the form text and `scoring.md`); `packaging_per_unit` = T2.9; `rebate_total` = T2.10. `0.00` for a known zero; blank = unanswered. | | golden test |
| **T2.15 Decision shape** | bid → one entry per tender position, identified by its position number, currency EUR. no_bid → `positions: []`, `total_net: 0`, choose *Verzichtserklärung*. Never extra or duplicate positions. | form defaults to *Nebenangebot* (secondary) → must choose *Hauptangebot* | Notary test |
| **T2.16 Time and authority** | "Latest" compares **UTC datetimes** (portal shows Athens time, mail Berlin time, ERP UTC); records after `S` never apply. Authorized subject/sender pairs come from the brief: Technikfreigabe/technik, Verpackungstarife/logistik, Terminfreigabe/logistik, Devisenfixing/finanzen, Rüstpools/kalkulation, Projektbonus/finanzen, Konditionsregeln/kalkulation, Preisindizes/kalkulation, discount/leitung. | future-dated 26.01 FX decoy | resolver tests |
| **T2.17 Partial credit** | Each field scores independently. A position with a best-effort value still earns its correct fields; an **omitted** position earns nothing. Policy: **never omit** a position for which we know the material; fill unknown optional breakdown fields **blank** rather than guessing; still keep `total = Σ q × unit`. Omit only when we cannot configure the material at all. | | policy test in Notary |

### 4.4 Ambiguity register (our interpretation, to confirm with test-run breakdowns)

| ID | Question | Our choice | How we confirm |
| --- | --- | --- | --- |
| A1 | "No later than the scenario date": date or datetime? | datetime ≤ S (brief gives a timestamp). Log every record on the same calendar day after S. | test-run breakdown on public (8153 at 08:00Z < 09:00Z is consistent) |
| A2 | EUR price with price unit 100 giving > 2 decimals | normalize, then r2 | none seen yet; log if it occurs |
| A3 | Unconditional approval in a no_bid case | discount_percent = approval % (rule only zeroes conditional ones) | log; low frequency |
| A4 | Two active materials both match exactly | pick the one the Auditor confirms with the tighter evidence; flag in `notes` | log; should not happen |
| A5 | surcharge_per_unit rounding | r2 of (metal surcharge + setup/q), unrounded parts | confirmed by form text |

## 5. T3: RANK (cost × time)

| ID | Rule | Target |
| --- | --- | --- |
| T3.1 | Quality first: never trade a quality point for speed or cost. | — |
| T3.2 | Time = run start → accepted answer. Work the 4 sites **in parallel** (4 browsers). | p50 ≤ 6 min, p95 ≤ 10 min, hard stop 18 min |
| T3.3 | Cost = metered LLM usage. Default to hosted **Qwen** ($0.15/M in, $0.016/M cached, $0.47/M out) and **Clef** ($0.24/M in) for yes/no checks. Frontier models only if they buy quality, per call site, behind a flag. | ≤ $0.25 per run |
| T3.4 | Keep model inputs small: page digests, not raw HTML; stable system prompts first for caching. | ≤ 6k tokens per call p50 |
| T3.5 | `agent.json` `"models"`: list only what we call (shorter warm-up waits don't count, but listed models must be warm). | `["qwen", "clef"]` or `["qwen"]` |

## 6. T4: CRAFT (elegance and team hygiene)

| ID | Rule |
| --- | --- |
| T4.1 | One package dir (`agent/`), small modules with one job each; the calculator is a pure function of the ledger. |
| T4.2 | Every claim in the ledger carries provenance (site, URL, verbatim quote, record date). Every decision is in the run trace. |
| T4.3 | Tests run in < 60 s locally (`uv run pytest`); CI runs tests + hardcode audit + package check on every PR. |
| T4.4 | Release train: only `main` builds submissions; every submission is a tagged commit with its test-run score in the tag message. |
| T4.5 | **The final run takes the latest passed submission, not the best.** No experimental submissions after the freeze (plan §12). |
| T4.6 | README explains the architecture honestly (no reviewer-steering language, T0.10). |

## 7. Generic trap catalogue (what the private sites will throw at us in a different skin)

Handle these as **categories**, never via public-site specifics:

1. Cookie walls / consent pages after login.
2. Modal dialogs whose big button navigates away; Escape blocked; small close control.
3. Look-alike controls: several identical labels, one works (others: "not available", survey, tools page).
4. Flaky error pages ("Dienst vorübergehend nicht verfügbar") → retry.
5. Session timeout → back to login → re-login and resume.
6. Human-check gates: slider to 100 + "I'm not a robot" checkbox unlocking a fieldset; a code shown on a canvas to retype.
7. Hidden values: canvas (aria-label/fallback), tooltips, `<details>`, hover menus, iframes (nested), ZIP, CSV, TXT (maybe PDF).
8. Hidden decoys: `aria-hidden`/`display:none` text with poison values; "draft/not sent" blocks in mails.
9. Zero-width characters inside identifiers.
10. Mixed number locales (tagged), price units ≠ 1, mixed date formats (tagged), several timezones.
11. Pagination with tiny pages, "load more", ordering not by date.
12. Superseded documents shown first; look-alike references (`…-A`); wrong senders; future-dated records; requests vs approvals.
13. Search engines that refuse empty/broad queries and AND their words.
14. Wizard forms: default values that are wrong, cascading selects, back clears later steps, browser confirm dialog at the end.

## 8. Definition of Done for a submission

A package may be submitted only if **all** hold:

- [ ] `tools/audit_hardcode.py` passes (T0.1, T0.2, T0.5, T0.6)
- [ ] `tools/check_package.py` passes (T1.1, size, file list)
- [ ] `uv run pytest` green, including calculator golden tests and no-bid mutation test
- [ ] Last local end-to-end run on public: answer equals oracle on ≥ 95 % of local-scorer points, signed in dry-run mode
- [ ] Last sandbox **test run**: eligible, score recorded in the tag message, time < 10 min
- [ ] Commit is on `main`, tagged `sub-NN`, changelog line written
- [ ] Before freeze only: it is at least as good as the previous submission on the test-run breakdown
