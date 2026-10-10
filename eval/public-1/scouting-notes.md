# Scouting notes: public scenario (public-1)

Scouted 2026-10-10 with the scouting logins. Tender **VG-2027-7093** (Stadt Buchenstadt, Verkehrsbetriebe), bidder
Linden Hydraulik und Komponenten GmbH, scenario date **2027-01-25T09:00:00Z**. Raw extracts next to this file: `scout-public-qa.txt`,
`run-brief.md`, `scouting.json`. Expected answer (test oracle, never ship it): `../oracle.py`.

The private dataset uses *different sites, layouts and navigation*, so treat the traps below as categories of
problems the agent must handle generically, not as selectors to hardcode.

## Traps seen on every site

| Trap | Where | Handling |
| --- | --- | --- |
| Cookie wall after login | all 4 | click "Notwendige Cookies akzeptieren" |
| Modal `<dialog>` popups ("Kurze Umfrage", "Wartungshinweis", "Postfachhinweis"); Escape is blocked; the big "Akzeptieren und fortfahren" link navigates away (survey / home) | all | close via the small `button[data-close]` × (or `dialog.close()`) |
| 3 look-alike buttons ("Öffnen", "MM03", "Original öffnen"): one works, one says "Funktion nicht verfügbar", one goes to a survey/tools page; order is shuffled | tender docs, ERP menu, mail | prefer the `<a>` whose href is the real target |
| Zero-width spaces in identifiers (`V​G​-​2​0​2​7…`) | all | read `aria-label` of `[role=img]`, or strip `​` |
| Values drawn on `<canvas>` (receipt numbers, bore, Q&A quantities) | all | canvas `aria-label` / fallback text holds the value |
| Values inside tooltips (`[role=tooltip]`, shown on hover of "Eingang"/"Freigabestand"/"Prüfvermerk") | tender Q&A dates, spec status + certification, ERP status key | read tooltip text from DOM |
| Hidden decoy text (`aria-hidden`, `display:none`), e.g. "Zertifizierung: ISO 9001; Hub: 999 mm" | spec | drop hidden nodes before extraction |
| Mixed number formats, tagged `(de-DE)` / `(en-US)`: "64,853 (en-US)" = 64853; "181.429 (de-DE)" = 181429 | spec, ERP prices | parse per tag |
| Mixed date formats `05/01 (TT/MM)` vs `01/17 (MM/TT)` | spec revisions, mail list | parse per tag; prefer full dates |
| Timezones: tender portal shows Europe/Athens (UTC+2), mail Europe/Berlin, ERP UTC | | compare in UTC |
| Flaky "Dienst vorübergehend nicht verfügbar" pages | ERP (frequent) | retry |
| Pagination: few rows per page (3 Q&A per page, 1 doc per page) + "Weitere laden" | tender list, Q&A, spec, docs, mail | follow "Nächste Seite" until absent |
| Hover-only menus (`:hover`/`:focus-within`) | tender "Verfahrensakte ▾", portal "Dokumente ▾" | use the hrefs directly |
| Nested iframes | Q&A (`questions-frame` → `questions-content`), spec viewer, mail reading pane | open the iframe URL directly |

## 1. Tender portal (`tender-portal`)

- Login → cookie consent → search list (16 tenders, 6 pages). Our tender: `/tenders/VG-2027-7093`.
- Tabs: `?tab=documents` (Unterlagen), `?tab=questions` (Bieterfragen). ZIP of all docs at `/documents.zip`
  (hidden behind "Aktionen" context menu).
- Documents `/tenders/<ref>/documents/{0,1,2}`: Leistungsverzeichnis.csv (original quantities), Leistungsbeschreibung
  (names spec **LH-VG-2027-7093**, "current revision applies"), Positionsübersicht.
- Bill of quantities: 01.01 24 Stk A-1 · 01.02 29 Stk A-2 · 01.03 16 Stk A-2 · 01.04 21 Stk A-4 · 01.05 22 **Satz** A-5.
- Q&A at `/tenders/<ref>/questions-content?page=N` (6 pages, newest first, numbers not in date order). Each row:
  number (aria-label), date tooltip "25.01.2027, 10:00 · 2027-01-25T08:00:00Z", question summary, answer in `<details>`.
  Kinds of answers seen:
  - quantity changes (01.01: 26 → 25; 01.05: 26 Satz, then 32 Satz **withdrawn** by 8153)
  - technical amendments to a named revision + requirement (R-6156 A-2 stroke 485 → 482)
  - Konditionsgruppe per position (01.02 K-3650, 01.03 K-2264, 01.05 K-9018)
  - one-off setup costs (01.03 85.00, 01.05 57.50; not discounted)
  - per-position keys: packaging tariff VP-1134 (all), delivery commitment TZ-xxxx, Rüstpool RP-5730 and project
    bonus PB-1474 (01.03, 01.04, 01.05)
- Submission wizard `/tenders/<ref>/submission` ("Angebotsabgabe"), one POST form, `revision` counter:
  1. Bieterdaten: company, USt-IdNr. (DE811234567), contact e-mail
  2. Angebotsart: select `kind` = bid | secondary | no_bid. **Defaults to `secondary`**: must change.
  3. One step per position, **shuffled order**: cascading selects bore → stroke → mounting → certification →
     material (press `configure` after each), quantity, net unit price, optional base_price / surcharge / packaging /
     rebate, lead (weeks). Buttons: skip (Position auslassen), add, next, back. Form text: "Zuschläge = Materialzuschlag
     + anteilige Rüstkosten, auf Cent gerundet"; packaging and bonus reported separately.
  4. Not yet scouted: total, document acknowledgement, summary, TAN request (TAN via mail, valid 5 min, a new request
     invalidates the old), browser `confirm()` dialog "Angebot verbindlich abgeben". Prices in German number format.

## 2. Supplier portal (`customer-portal`)

- Login → cookie consent. Register `/documents?page=1..4` (1 doc per page); spec at `/documents/specification`.
- Access gate before the spec: radio `purpose` = **reference** ("Verbindliche Unterlagen zur Kenntnis genommen"; archive
  and preview are traps), receipt number from a canvas ("Belegnummer"), checkbox, "Leseberechtigung anfordern".
- Opens the **oldest** revision. Revision history (`<details>`): status in tooltip; **R-6156 = gültig**; R-4034,
  R-9711 = ersetzt.
- Viewer iframe `/documents/specification/viewer?revision=R-6156&page=1..5` (one requirement per page). The
  "Originalwortlaut" `<details>` holds the full requirement text, including the **Kataloggruppe**, "nutzbarer Weg" notes
  with end-reserve keys, and pieces per set.
- R-6156: A-1 80/200/210 Schwenkauge EN 1493 GR-8923 · A-2 63/489 (usable) /250 Flansch EN 1493 GR-5152, ER-4001 ·
  A-3 unused · A-4 50/576 (usable) /210 Schwenkauge none GR-6617, ER-9526 · A-5 125/300/250 Flansch none GR-4287,
  1 Satz = 5 Stück.

## 3. ERP (`erp`, SAP-style, times in UTC)

- Login → cookie consent → (sometimes "Dienst nicht verfügbar") → **gate**: slider to 100 + "Ich bin kein Roboter"
  unlocks a fieldset; type receipt "PRD-xxxxxx" from canvas, tick checkbox, "Weiter".
- Transactions: MM03 material, MMBE stock, VK13 conditions. F4 search: `/search?transaction=MM03&q=<Kataloggruppe>`
  (empty or broad queries return nothing; max 20).
- Search rows/description: dimensions, Kataloggruppe, Packinhalt (pieces per carton), Umlagegewicht (allocation mass,
  for Rüstpool), Zuschlagsmasse (surcharge mass, × metal index), Preisindex key.
- MM03 tabs: `tab=technical` (bore, stroke, pressure, mounting, certification in tooltip), `tab=planning` (Materialstatus
  01 freigegeben / **03 gesperrt**, lead time from stock / production).
- MMBE: plant total includes inspection stock. `&level=stock` gives "Verfügbarer Gesamtbestand" (0001 Fertigwaren
  only; 0099 Prüfbestand is not available).
- VK13: `&page=N&view=header` (validity, currency + FX key, **price unit 1 or 100 ST**, number format) and
  `&view=scales` (scale from qty → net price per price unit). Several condition records with different validity
  (2026 vs 2027).
- Candidates: GR-8923 HZ-8405 (**blocked**) / HZ-1609 · GR-5152 HZ-2170 (63/500) · GR-6617 HZ-3916 Schwenkauge /
  HZ-4889 Flansch · GR-4287 HZ-3567 (125/325) / HZ-6932 (125/300).

## 4. Webmail (`mail`, mailbox vertrieb@linden-hydraulik.example)

- Folders `?folder=inbox` and `?folder=archive`; search `?folder=…&q=…` ANDs words: use "<ref> <topic>". Message
  page `/messages/<id>`. List also holds signing-TAN mails ("Signatur-TAN <ref> · Anforderung N").
- Each message shows a decoy "Lokale Vorschau / nicht versandter Entwurf · Entwurfswert 99 % · Keine Freigabe" block;
  the real body is under "Nachrichtentext (Original)" (behind another slider + robot gate in the UI, plain in DOM).
- Look-alikes: reference `VG-2027-7093-A`, wrong senders (vertrieb@ requests), "Angebotsprüfung … keine
  Rabattfreigabe", future-dated records (Devisenfixing 26.01 > scenario date).
- Found (all exact reference, dated ≤ scenario date):
  - leitung@ 24.01 17:00: **5 %**, conditional on undiscounted order value ≥ 1.00 EUR (newest; older 4 %, 5 %)
  - kalkulation@ Konditionsregeln: K-3650 base only · K-2264 nothing discounted · K-9018 base + surcharge
  - technik@ Technikfreigabe: ER-4001 = 9 mm per end, ER-9526 = 12 mm per end (revision R-6156)
  - logistik@ Verpackungstarife: VP-1134 = 13.25 EUR per started carton
  - logistik@ Terminfreigabe: TZ keys → material + 3 weeks if pooled demand ≤ ceiling
  - finanzen@ Devisenfixing: FX-6282 1 USD = 1.0873 EUR
  - kalkulation@ Rüstpools: RP-5730 = 517.25 EUR, allocate by qty × Umlagegewicht, cents largest remainder
  - finanzen@ Projektbonus PB-1474: marginal bands 0–5000 0 %, 5000–15000 2 %, >15000 5 %
  - kalkulation@ Preisindizes: MET-4607 windows; **3.15 EUR/kg** for 25.01–28.02.2027

## Derived public answer (from `../oracle.py`)

| Pos | Qty (pcs) | Material | Base EUR | Surcharge | Packaging | Rebate | Unit price | Lead |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 01.01 | 25 | HZ-1609 | 2743.58 | 6.69 | 1.59 | 0.00 | 2614.68 | 2 |
| 01.02 | 29 | HZ-2170 | 705.15 | 5.91 | 4.57 | 0.00 | 680.37 | 3 |
| 01.03 | 16 | HZ-2170 | 753.23 | 12.57 | 4.97 | 580.41 | 734.49 | 11 |
| 01.04 | 21 | HZ-3916 | 2107.18 | 5.25 | 1.26 | 2131.11 | 1906.85 | 3 |
| 01.05 | 130 | HZ-6932 | 1866.15 | 8.06 | 1.94 | 11683.58 | 1692.74 | 3 |

Discount 5 %, total_net **356 949.62 EUR**. Unverified by the platform (it doesn't publish answers). A test run
will tell us how close this is.

## Implications for the agent

- Most of the difficulty is in **reading** (traps above) and **calculating** (rules 12–28). Navigation per site is short.
- Split it up: a model chooses pages, searches and documents, and extracts facts into a typed structure. A
  deterministic Python calculator applies the rules (rounding, cent allocation, bands), and a form-filler with model
  oversight enters the bid. This satisfies the fair-play rule: helpers may extract, calculate and fill forms.
- A good HTML→text cleaner (drop hidden nodes, expand aria-labels/tooltips/canvas, tag number formats) does most of
  the reading work and is site-agnostic.
- The 4 sites can be worked in parallel (up to 4 browsers); a 20-minute limit and the cost × time ranking reward it.
