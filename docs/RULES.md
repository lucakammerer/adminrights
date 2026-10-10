# Rules

> **What we must deliver, every rule we are judged by, and where each bid rule lives in the code.** One reference for
> the whole team: code, PRs and submissions are checked against it. Source of truth stays the run's brief and the
> platform docs ([challenge](https://ehl-challenge.atira.ai/challenges/rfq.md),
> [fair play](https://ehl-challenge.atira.ai/docs/fair-play.md),
> [run contract](https://ehl-challenge.atira.ai/docs/run-contract.md),
> [scoring](https://ehl-challenge.atira.ai/docs/scoring.md)); if this file contradicts them, they win, and this file
> gets fixed. Frame, models and the points table: [challenge.md](challenge.md). No public-1 values in this file.

---

## 0. How to read this file

| Tier | Breaking it means | IDs |
| --- | --- | --- |
| **T0 Blocker** | package rejected, flagged or disqualified: nothing counts | T0.1–T0.11 |
| **T1 Hard** | the run scores 0 or is ineligible | T1.1–T1.12 |
| **Bid rules** | specific quality points are lost | **1–29**, numbered as in the brief and on the challenge page; agent READMEs cite these numbers |
| **T3 Rank** | worse tie-breaker (cost × time) | T3.1–T3.5 |
| **T4 Craft** | worse elegance, slower team | T4.1–T4.7 |

**MUST / MUST NOT** = no exceptions. **SHOULD** = default; a deviation needs a reason in the PR. **MAY** = free.
Status: ✅ in the code · ⚠️ in the code with a known gap · ❌ missing. "In the code" is not "verified": verification is
`eval/compare.py` on a dry run and the per-field points of a test run. `F#` = finding in
[PLAN_COMPARISON.md](PLAN_COMPARISON.md) §2.6, `I#` = increment in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) §12.

**Last full dry run (2026-10-10, `main` `3accb38`):** the resolver outputs matched the reference for every rule they
decide (1, 2, 5, 12–14, 16, 17, 20–26, 28); the run still failed on time (T1.3) and on rule 3 (a timed-out search
became a no-bid). PR #5 has since added site roles from the brief and hard phase cuts; the statuses below
include it.

---

## 1. What we deliver

| # | Deliverable | Counts for |
| --- | --- | --- |
| D1 | The package: `agent/` as a gzipped tarball, `agent.json` at its root, ≤ 20 MB | review, every run |
| D2 | One signed bid entered in the tender portal's configurator before the run expires (scored run: 20 min) | quality, eligibility, cost, time |
| D3 | Scored submissions on the public dataset: our **best** one holds the leaderboard place | winners, 2nd criterion |
| D4 | Our **latest** submission that passed review runs on the private dataset at the end (once, or best of 3 if opted in) | winners, 1st criterion (weighs most) |
| D5 | An elegant system: clear architecture, readable code, honest docs | winners, 3rd criterion |

---

## 2. T0: Blockers (fair play and platform)

| ID | Rule | Check |
| --- | --- | --- |
| T0.1 | MUST NOT put values from the public scenario or its websites into the package: references, material numbers, keys of any kind, prices, quantities, totals, discounts, dates, logins, TANs, receipt numbers. Applies to code, config, prompts, few-shot examples, notes, defaults and fallbacks, **and to the agent READMEs, which are uploaded with the package**. | `tools/audit_package.py` (I8); 0 hits on `main` `3accb38` |
| T0.2 | MUST NOT ship site-specific navigation: no site URLs, paths, element ids or click sequences. Generic heuristics are fine. | audit; review |
| T0.3 | A model MUST choose navigation targets, searches and relevant documents from what it observes at run time, and make the important decisions. | every navigation step is a model tool call in the log |
| T0.4 | Helpers MAY extract a page the model chose, parse a document it chose, page through a result set it chose, calculate, validate, retry and fill forms. They MUST NOT discover and traverse the sites on their own to assemble the evidence (no crawler, no fixed script with the model as a fallback). | review |
| T0.5 | MUST NOT ship a pre-solved answer. Reference answers (`eval/`) stay outside `agent/`. | package = `agent/` only |
| T0.6 | Model calls only through the platform proxy; no bundled or local model; own keys only as team secrets. | audit (API-key patterns); env-only config |
| T0.7 | MUST NOT contact hosts other than the platform API and the challenge's websites, or move data out of the sandbox. | review |
| T0.8 | MUST NOT start browsers in the sandbox: use the ones in `CDP_URLS` (≤ 4, `"browsers"` in `agent.json`); tabs and contexts are free. No dev scripts that launch a browser inside the package. | `browsers.connect` launches only without `CDP_URLS` |
| T0.9 | MUST NOT attack the platform, the websites, the sandbox or other teams; MUST NOT share scored-run data. | team agreement |
| T0.10 | MUST NOT address the AI reviewer to steer its verdict. Plain, honest docs are fine. | review |
| T0.11 | Facts the brief states for every scenario (company, VAT id, mailbox local parts, authorized subjects and senders, submission steps) MAY be used, and SHOULD be read from the run's brief at run time rather than typed into code. | ⚠️ mail topics fixed in the mission (F10 → I12) |

## 3. T1: Hard (run validity and eligibility)

| ID | Rule | Status |
| --- | --- | --- |
| T1.1 | `agent.json` valid: `setup`, `run`, `models` ⊆ hosted ids, `browsers` an integer 1–4. | ✅ |
| T1.2 | `setup` finishes in < 5 min; it has network but no credentials. | ✅ (`uv sync`) |
| T1.3 | **Always answer before `expires_at`.** No answer = 0 and ineligible. Every stage gets its own budget when it starts (never negative), model calls are bounded by it, and a watchdog signs what is entered. | ⚠️ hard phase cuts since PR #5 bound every stage; no start-time budgets or watchdog yet; before the cuts, the dry run answered only at 1029 s (F3, F4, F5, F19 → I2, I4, I6) |
| T1.4 | **Eligibility = the exact tender reference:** from the brief, confirmed on the portal, invisible characters removed; never a look-alike (suffix or other number). | ✅ |
| T1.5 | Exactly one binding submission; it ends the run. | ✅ |
| T1.6 | The answer matches the run's `answer_schema` (read from the run, not copied). | ⚠️ not validated before signing (→ I11) |
| T1.7 | Money in the form in German number format, two decimals. | ✅ `agents/submit` `german` |
| T1.8 | Signing: request one TAN only when everything is entered; use the newest TAN mail for the exact reference after that request; valid 5 min; a new request invalidates the old TAN. | ✅ `get_tan` |
| T1.9 | Saving is not submitting: sign and submit, also when positions are omitted. | ⚠️ no watchdog (F5 → I6) |
| T1.10 | Read the run from `GET /v1/runs/current` with `x-api-key` and our own User-Agent (Python's default is refused). | ✅ `run.py` |
| T1.11 | Wizards: going back clears later steps; an expired session loses unsaved entries. Move forward step by step, saving each. | ✅ in the mission |
| T1.12 | Site roles and the submission target come from the run (`access`, `submission`), never from assumed ids; an unknown id must not crash the run. | ✅ roles assigned by a model from the brief (PR #5); the `submission` target pins the tender portal, and an unclear assignment falls back by elimination instead of crashing (I3) |

---

## 4. Bid rules 1–29

### 4.1 Notation and shared definitions

- `S` = the scenario datetime from the brief; `T` = the exact tender reference; `D` = the bidder's mailbox domain.
- `r2(x)` = round half up to 0.01. Money is `Decimal` from parsing to the answer; never round an intermediate value
  unless a rule says so.
- **Times:** compare in UTC. Convert each site's local times with the timezone the site states; prefer an explicit
  UTC/ISO value when the page shows one. Date formats come with their order (day/month vs month/day): read the hint.
- **Numbers:** parse by the format the page states (`de-DE` `12.345,67`, `en-US` `12,345.67`); a form like `12,345` or
  `12.345` without a hint is ambiguous and MUST NOT be guessed.
- **`LATEST(subject, key)`**: among records of that subject (and key) that are for **exactly `T`**, come from the
  **authorized sender** (local part from the brief + `@D`) and are dated **≤ `S`**, the newest one. A newer record
  replaces older ones; a failed condition does not revive an older one; records for other references and future-dated
  records never apply; unsent drafts, previews, requests and reviews are not records.
- **Unfinished is not absent:** a search or stage that didn't complete (forced finish, deadline, crash) yields
  *unfinished*, never a negative result.

### 4.2 What the points imply

The points table is in [challenge.md](challenge.md); it leads to four rules for us:

- In a no-bid case the decision alone is worth 75: the material decision (rule 3) needs proof both ways.
- Every field scores on its own: a submitted position with some fields right beats an omitted one (rule 9).
- Money is compared to the cent: `Decimal`, rounding only where the rules say.
- Extra or duplicate positions cost a position's share each: exactly one entry per tender position (rule 8).

### 4.3 The rules

**1 · Quantity.** The position's tender quantity, replaced by the latest dated clarification (≤ `S`) that changes
**that** position; withdrawn answers don't count (13); then converted to pieces (17).
Traps: clarification numbers aren't in date order; times in site-local zones; values drawn as images.
Gather tender_portal · Decide `resolvers.requirements` · ✅ · Check: dry-run score; select tests (I18)

**2 · Requirement.** The position's requirement in the specification revision **marked current** by its status: not
the one that opens first, not the newest date, not the highest number. Superseded revisions never apply.
Traps: the oldest revision opens first; the status is only in a tooltip; dates in mixed formats.
Gather supplier_portal · Decide `resolvers.requirements` · ✅ · Check: dry-run score (material and quantity fields)

**3 · Material.** An **active** material whose bore, stroke, pressure, mounting and certification all **exactly**
equal the governing requirement (after amendments, 14, and derivation, 20). Blocked materials never qualify. If any
position has none, the decision is **no_bid** for the whole tender. Proof both ways: `bid` needs one active exact match
per position, checked in code; `no_bid` needs a completed search (the group's result list in the evidence, every
candidate compared) and an independent confirmation. An unfinished search is never "no match" (4.1).
Traps: look-alike materials that differ in one attribute or only in status.
Gather erp · Decide `erp.run`, `calc` · ⚠️ a search cut by its hard deadline is omitted (PR #5), but one forced to
finish just before the cut can still report no match → false no-bid (F9, F16 → I1, I11) · Check: validate tests with look-alike, blocked and unfinished candidates

**4 · Unit price.** Take the price condition **valid at `S`** (both validity endpoints inclusive), normalize it by its
**price unit** (per 1 or per n pieces), and choose the scale with the **highest minimum quantity ≤ the position's
final pieces** (per position, never the material's sum, 15). Converted by 22, this is `base_unit_price`. The approved
discount applies to it per the position's clause (12) inside the final price (27).
Traps: several conditions with different validity; price units other than 1; mixed number formats.
Gather erp · Decide `erp.extract`, `calc` · ⚠️ ambiguous numbers guessed without a hint (F7 → I10) · Check: number and
calc tests (I10, I14)

**5 · Discount.** `LATEST(discount approval, sales director)` for exactly `T`; none → 0 %. Conditions: 16.
Traps: approvals for look-alike references; requests from our own mailbox; reviews that are explicitly no approval;
superseded approvals; draft blocks inside messages; inbox and archive.
Gather webmail · Decide `resolvers.commercials` · ⚠️ search wording taken from a public mail subject (F10 → I12) · Check:
dry-run score; select tests (I18)

**6 · Lead time.** The from-stock lead time when **available** (unrestricted) stock covers the pooled demand (15);
otherwise the production lead time. A delivery commitment can override (24).
Traps: physical totals include inspection or blocked stock.
Gather erp · Decide `calc` · ✅ · Check: calc tests (I14)

**7 · Total.** `total_net = r2(Σ final quantity × rounded final unit price)`; it MUST equal the sum of the submitted
positions.
Gather – · Decide `calc` · ✅ · Check: validate (I11), calc tests (I14)

**8 · Decision.** `bid`: one entry per tender position, identified by its position number, currency EUR, never extra
or duplicate positions. `no_bid` (rule 3): no positions, total 0. In the form: the main offer for a bid, the waiver for a
no-bid; the form's preselected offer kind may be wrong.
Gather – · Decide `calc` · ✅ · Check: validate (I11)

**9 · Partial submission.** Positions can be explicitly omitted in the form (no position points; the other positions
keep their credit), and the bid must still be signed. Our policy: **omit a position only if its material cannot be
configured**; with a known material, submit it with every field we have, optional fields we don't know left blank,
and keep rule 7. A missing active material is no_bid (3), never an omission; an unfinished search is an omission (or a
retry), never no_bid.
Gather erp · Decide `calc`, `submit` · ⚠️ positions without prices or with a cut search are omitted; no watchdog (F5,
F14 → I6, I15) ·
Check: calc tests, short-budget dry run

**10 · Finding records.** The spec names a catalogue group per requirement: search the ERP for it and compare the
candidates' attributes. Empty or over-broad searches list nothing: narrow to ≤ 20 hits. Mail search ANDs its words:
use the reference plus one subject or topic; read inbox **and** archive, every result page. Helpers may extract opened
pages and page through chosen result sets; sites and positions may be investigated in parallel.
Gather erp, webmail · Decide missions · ⚠️ each agent looks only on "its" site (F11 → I16); fixed mail topics (F10 → I12)
· Check: gap-sweep test (I16)

**11 · Agent requirement.** See T0.3 and T0.4.

**12 · Commercial clauses.** A Q&A answer may assign a position to a *Konditionsgruppe*. Resolve it in
`LATEST(Konditionsregeln, kalkulation)` for exactly `T`. Its prose maps to exactly one of: **base only**, **base and
mass surcharge**, **neither**. Setup fees are never discounted. A group overrides the default even when two positions
select the same material; positions without a group are **base only**. The order-level percentage and its threshold
(16) don't change.
Gather tender_portal, webmail · Decide `resolvers.commercials` · ✅ · Check: dry-run score; prose → class tests (I18)

**13 · Withdrawn answers.** A Q&A answer may withdraw an earlier one by its number: ignore the withdrawn answer's
quantity change; the latest remaining change applies, else the tender quantity.
Gather tender_portal · Decide `resolvers.requirements` · ✅ · Check: dry-run score; select tests (I18)

**14 · Scoped amendments.** After choosing the governing revision (2), apply the Q&A technical amendments that name
**that revision and that requirement**: only the named attributes, the latest dated (≤ `S`) per attribute.
Amendments to other revisions never apply.
Gather tender_portal · Decide `resolvers.requirements` · ✅ · Check: dry-run score; select tests (I18)

**15 · Shared stock.** Sum the final quantities of all positions that select the same material. Stock must cover the
whole sum for those positions to deliver from stock; otherwise all of them use production. No partial allocation.
Price scales stay per position.
Gather erp · Decide `calc` · ✅ · Check: calc tests (I14)

**16 · Conditional discount.** If the governing approval (5) sets a minimum undiscounted net order value:
`V = r2(Σ final quantity × base_unit_price)` (valid per-position scale prices in EUR, before discount, without mass
surcharges, setup fees or packaging). `V ≥ threshold` (inclusive) → its percentage, else **0 %**, with **no fallback**
to older approvals. For no_bid, a conditional approval yields 0 %.
Gather webmail · Decide `resolvers.commercials`, `calc` · ✅ · Check: calc tests (I14)

**17 · Units.** Tender and Q&A quantities are in the position's stated unit. Sets convert to pieces with the
governing spec's pieces per set. Price scales, stock, allocation weights and bid quantities are all in final pieces.
Carton rounding affects packaging cost only, never the quantity.
Gather tender_portal, supplier_portal · Decide `resolvers.requirements` · ✅ · Check: dry-run score; select tests (I18)

**18 · Pricing breakdown.** Optional fields with independent credit, all net EUR: `base_unit_price` (rule 4, per
piece); `surcharge_per_unit = r2(metal surcharge + (ordinary setup + allocated pool share) / q)` per piece, **before
discount**, without packaging and bonus; `packaging_per_unit` (23, per piece); `rebate_total` (26, the **whole
position's** credit). `0.00` for a known zero; blank = unanswered. Rounded report fields never feed back into 27.
Gather – · Decide `calc` · ✅ · Check: calc golden test (I14)

**19 · Same rules everywhere.** The calculation rules apply to the practice and the private dataset alike; missing
calculation fields lose only their own points (9). Nothing may depend on what public-1 looks like (T0.1, T0.2, T1.12).

**20 · Technical derivation.** For a requirement whose stroke is a usable stroke (*nutzbarer Weg*): apply its scoped
amendments (14), then add **2 ×** the per-end reserve of its key from `LATEST(Technikfreigabe, technik)` **for that
revision**. Match the resulting nominal stroke in the ERP; other attributes stay unchanged.
Gather supplier_portal, webmail · Decide `resolvers.requirements` · ✅ · Check: dry-run score; select tests (I18)

**21 · Authority and time.** Every key is resolved with `LATEST` (4.1). Authorized subject/sender pairs (local part +
`@D`), as the brief states them: Technikfreigabe/technik, Verpackungstarife/logistik, Terminfreigabe/logistik,
Devisenfixing/finanzen, Rüstpools/kalkulation, Projektbonus/finanzen; plus the director's approval (5),
Konditionsregeln (12) and Preisindizes (28), both from kalkulation. Read them from each run's brief (T0.11).
Gather webmail · Decide `resolvers.commercials` · ⚠️ correct in the dry run, but nothing checks the model's selection
(F6 → I18) · Check: select tests per trap category (§8)

**22 · Currency.** The valid condition names its currency and FX key. Normalize the price unit, choose the
per-position scale (4), convert with EUR per currency unit from `LATEST(Devisenfixing, finanzen, key)`, and `r2`. This
EUR value is `base_unit_price`, used in every later step (16, 26, 27).
Gather erp, webmail · Decide `erp.extract`, `resolvers.commercials`, `calc` · ⚠️ an unmatched FX key silently takes the
only rate (F8 → I15) · Check: calc tests (I14)

**23 · Packaging.** The Q&A assigns the tariff key; `LATEST(Verpackungstarife, logistik, key)` gives the price per
started carton; the ERP gives pieces per carton. `cartons = ceil(final pieces / carton size)` **per position**, never
pooled, never discounted; the quantity is not increased. `packaging_per_unit = r2(cartons × tariff / q)`.
Gather tender_portal, erp, webmail · Decide `resolvers.commercials`, `calc` · ✅ · Check: calc tests (I14)

**24 · Delivery.** The Q&A assigns a commitment key; `LATEST(Terminfreigabe, logistik, key)` names a material, weeks
and a ceiling. Apply it only if its material is the selected one **and** the pooled demand for that material ≤ the
ceiling (inclusive); otherwise shared-stock delivery (6, 15). Commitments may differ by position for the same material.
Gather tender_portal, webmail · Decide `resolvers.commercials`, `calc` · ✅ · Check: calc tests (I14)

**25 · Shared setup.** The Q&A names the pool members; the ERP gives each material's **allocation mass** (not the
surcharge mass); `LATEST(Rüstpools, kalkulation)` gives the one pool fee and the cent rule: weights = final pieces ×
allocation mass; floor to cents, leftover cents to the largest remainders, ties by ascending position id. Each share
adds to the position's ordinary setup fee (from the Q&A); reported in the surcharge (18).
Gather tender_portal, erp, webmail · Decide `resolvers.commercials`, `calc` · ✅ · Check: allocation tests (I14)

**26 · Project bonus.** `LATEST(Projektbonus, finanzen)` gives marginal bands. Eligible base `B = Σ final pieces ×
base_unit_price` over member positions (EUR, before discount, without surcharges and packaging). Credit = Σ over
bands of rate × the part of `B` inside the band, `r2` once; allocated to members in proportion to their goods value by
largest remainder in cents (ties ascending position id). `rebate_total` = the position's allocation; `0.00` for
non-members. Independent of discount clauses; never discounted again.
Gather webmail · Decide `resolvers.commercials`, `calc` · ✅ · Check: band and allocation tests (I14)

**27 · Final price.**
`unit = r2( base·(1 − d·[clause covers base]) + mass surcharge·(1 − d·[clause covers surcharge]) + (ordinary setup + pool share + carton cost − bonus share) / q )`
with unrounded components and one rounding at the end; `d` from 5 and 16, clauses from 12.
Gather – · Decide `calc` · ✅ · Check: calc golden test (I14)

**28 · Metal indices.** `LATEST(Preisindizes, kalkulation)` for exactly `T`; if it lists validity windows, use the
rate whose inclusive window contains `S`, not the last one listed. Mass surcharge per piece = surcharge mass (kg) ×
that rate (the material's index key selects the index).
Gather erp, webmail · Decide `resolvers.commercials` · ⚠️ an unmatched index key silently takes the only index (F8 →
I15) · Check: dry-run score; select tests (I18)

**29 · Scoring.** The points per part and per position field: [challenge.md](challenge.md); what they imply: 4.2.

---

## 5. T3: Rank (cost × time)

| ID | Rule | Target |
| --- | --- | --- |
| T3.1 | Quality first: never trade a quality point for cost or time. | — |
| T3.2 | Time runs from the start of the run command to the accepted answer: work the sites in parallel; start the submission early. | answer < 8 min, then toward 5 |
| T3.3 | Cost is metered model usage. Default to the hosted Qwen; other models only behind a flag and only where they buy quality. The team shares 32 concurrent Qwen calls across all runs. | ≤ $0.25 per run |
| T3.4 | Keep model inputs small: page text, not HTML; older reads trimmed; static prompt parts first (cached input is cheaper). | — |
| T3.5 | `agent.json` `"models"` lists only the models we call. | `["qwen"]` |

## 6. T4: Craft

| ID | Rule |
| --- | --- |
| T4.1 | `agent/` is the only package dir; one folder per agent with its `agent.py` and `README.md`; code calculates, models gather and decide. |
| T4.2 | Facts come only from kept evidence; decisive values carry the quote they came from; every decision appears in the log. |
| T4.3 | Tests run locally in under a minute; every change ships with its test or a scored dry run. |
| T4.4 | Submissions only from `main`, tagged `sub-NN` with their test-run score. |
| T4.5 | The final run takes the **latest** passed submission: no experimental submissions in the last 3 hours. |
| T4.6 | Docs say plainly what the system does (T0.10). |
| T4.7 | Docs follow `AGENTS.md` "Keeping docs current" and the conventions in [README.md](README.md). |

---

## 7. Ambiguity register

Interpretations we chose where the rules leave room. Confirm each with a test-run breakdown; update this table.

| ID | Question | Our choice |
| --- | --- | --- |
| A1 | "No later than the scenario date": calendar date or datetime? | datetime ≤ `S` (the brief gives a time); log records on the same day after `S` |
| A2 | A per-piece price with more than two decimals after normalizing (EUR condition) | keep it unrounded until `r2` makes it `base_unit_price` |
| A3 | An unconditional approval in a no-bid case | its percentage stands (the rule only zeroes conditional ones) |
| A4 | Two active materials both match exactly | take the one with the clearer evidence; say so in `notes` |
| A5 | Rounding of `surcharge_per_unit` | `r2` of the unrounded sum (confirmed by the form text and the scoring doc) |
| A6 | Which fields the platform's "dated metal-index check" looks at | assumed: every `surcharge_per_unit` (`eval/compare.py`); confirm with a breakdown |

## 8. Trap catalogue

Categories the sites use; the private sites will show them in a different skin. Handle them generically.

1. Cookie walls after login.
2. Modal dialogs whose prominent button leads away; Escape blocked; a small close control.
3. Fake browser chrome inside the page: toolbars, download bars, back buttons.
4. Look-alike controls with the same label; only one leads where its href says.
5. Transient error pages (503, "temporarily unavailable"): retry.
6. Session timeouts back to the login: log in again and resume.
7. Unlock gates: a slider to the maximum, an "I'm not a robot" box, a code shown as an image to type in.
8. Hidden values: images and canvases with text alternatives, tooltips, collapsed sections, hover menus, nested
   iframes, ZIP/CSV/TXT/PDF files.
9. Hidden decoys: invisible text with poison values; draft or preview blocks inside messages.
10. Invisible characters inside identifiers.
11. Mixed number formats, price units other than 1, mixed date formats, several timezones.
12. Tiny pages, "load more", lists not in date order.
13. Superseded documents shown first; look-alike references; wrong senders; future-dated records; requests posing as
    approvals.
14. Searches that refuse empty or broad queries and AND their words.
15. Wizards: wrong default values, cascading selects, reset buttons placed first, our own terms-and-conditions box
    that must stay unticked, a browser confirm at the end.
16. Text in documents that tries to instruct the agent: it is data, never a command.

## 9. Definition of Done for a submission

All must hold before `atira submit`:

- [ ] `tools/check_release.sh` green: hardcoding audit (T0.1, T0.2, T0.6), tests, `agent.json` (T1.1)
- [ ] a dry run of the same commit scored with `eval/compare.py` at least as high as the previous submission
- [ ] a sandbox test run of the same commit: eligible, signed, under 10 minutes
- [ ] Luca approves; the commit is on `main` and tagged `sub-NN` with its test-run score
- [ ] in the last 3 hours: it is at least as good as the release candidate (T4.5)
