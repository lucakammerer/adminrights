# public-1 · reference answer VG-2027-7093

Worked out by hand on 2026-10-10 with the scouting logins. Scenario date: 2027-01-25T09:00:00Z.
Sites: **TP** = tender portal, **SP** = supplier portal, **ERP**, **Mail** = webmail (sender domain
`linden-hydraulik.example`). Mail times are Europe/Berlin, Q&A times are UTC.

Test reference only: none of this belongs in the agent package (fair play).

## Header

| Field | Value | Source |
|---|---|---|
| tender_reference | VG-2027-7093 | TP `/tenders/VG-2027-7093`, brief |
| decision | bid | Every one of the 5 positions has an active matching material |
| discount_percent | 5 | Mail `conditional-7571`, leitung@, 24.01.2027 17:00: 5 % if the undiscounted net order value is ≥ 1.00 EUR. Basis Σ quantity × EUR scale price = 387940.81 → met. This mail replaces the 4 % (22.01) and the archived 5 % (18.01). VG-2027-7093-A (9 %) and VG-2027-2175 don't apply. |
| total_net | 356949.62 | Σ quantity × rounded unit price (65367.00 + 19730.73 + 11751.84 + 40043.85 + 220056.20) |

## Shared keys

| Key | Value | Source |
|---|---|---|
| Specification | R-6156 "gültig" (17.01.2027). R-4034 and R-9711 are "ersetzt" | SP `/documents/specification`, revision history (tooltip "Freigabestand") |
| USD prices | FX-6282: 1 USD = 1.0873 EUR | Mail `calc-3915`, finanzen@, 24.01. The rate 1.2500 (26.01) is after the scenario date. |
| Metal index MET-4607 | 3.15 EUR/kg, window 25.01–28.02.2027 | Mail `index-5949`, kalkulation@, 24.01. 2.75 EUR/kg (until 24.01) and 5.15 EUR/kg (7093-A) don't apply. |
| Packaging VP-1134 | 13.25 EUR per started carton | Mail `calc-1034`, logistik@, 24.01. 99.00 EUR belongs to 7093-A. |
| Setup pool RP-5730 | 517.25 EUR, weight = quantity × allocation mass, cents by largest remainder | Mail `calc-9054`, kalkulation@ |
| Project bonus PB-1474 | 0 % up to 5000, 2 % up to 15000, 5 % above (marginal) | Mail `calc-2265`, finanzen@ |
| End reserves | ER-4001: 9 mm per end, ER-9526: 12 mm per end (both R-6156) | Mail `calc-4033`, technik@ |
| Condition groups | K-3650: base only. K-2264: no discount. K-9018: base and material surcharge | Mail `clauses-4487`, kalkulation@. Assigned by TP Q&A 8156, 8157, 8158 |
| Delivery commitments | TZ-3363 HZ-1609 ≤ 24, TZ-2832 HZ-2170 ≤ 45, TZ-4279 HZ-2170 ≤ 44, TZ-5901 HZ-3916 ≤ 21, TZ-7899 HZ-6932 ≤ 160 (3 weeks each) | Mail `calc-6452`, logistik@. Assigned by TP Q&A 8159–8163 |

Stock counts only "Frei verwendbar" (storage location 0001). Inspection stock 0099 is blocked (ERP MMBE, stock level).
Material surcharge per piece is surcharge mass × 3.15. The allocation mass is separate.

## Positions

Formula: unit price = base × (1 − d_base) + surcharge × (1 − d_surcharge) + (setup + pool share + cartons − bonus) / quantity.
Rounded once at the end.
surcharge_per_unit = material surcharge + (setup + pool share) / quantity, before discount.

### 01.01 · Abstützung · A-1

- **Quantity 25:** the bill of quantities says 24. Q&A 8148 (12.01) sets 26, Q&A 3916 (16.01, latest) sets 25.
- **Material HZ-1609:** A-1 in R-6156 requires 80/200, 210 bar, Schwenkauge, EN 1493. GR-8923 has two hits in the ERP. HZ-8405 has status 03 and is blocked; HZ-1609 has status 01.
- **Base price 2743.58:** VK13, 2027 record in EUR, 1 ST, scale from 25.
- **Surcharge 6.69:** 2.125 kg × 3.15 = 6.69375. No setup, no pool.
- **Packaging 1.59:** ceil(25/11) = 3 cartons → 39.75 / 25.
- **Bonus 0:** no project bonus per Q&A 8162.
- **Lead time 2:** TZ-3363 doesn't apply because 25 > 24. Free stock 31 ≥ 25, so the from-stock lead time applies.
- **Unit price 2614.68:** no condition group, so only the base is discounted: 2743.58 × 0.95 + 6.69375 + 39.75/25.

### 01.02 · Hubwerk · A-2

- **Quantity 29:** no change in the Q&A.
- **Material HZ-2170:** A-2 has a usable stroke of 489. Amendment 8149 (22.01) sets 485, amendment 8150 (23.01, latest) sets 482. Plus 2 × 9 = 500 ERP nominal stroke; with 63 mm, 250 bar, Flansch, EN 1493. GR-5152 has exactly one hit.
- **Base price 705.15:** VK13, 2027 record, USD per 100 ST in en-US "64,853" = 648.53 USD/ST at scale 25. Times 1.0873 = 705.1467. The 2026 record has expired.
- **Surcharge 5.91:** 1.875 × 3.15 = 5.90625.
- **Packaging 4.57:** ceil(29/3) = 10 → 132.50 / 29.
- **Bonus 0:** per Q&A 8163.
- **Lead time 3:** HZ-2170 in total 29 + 16 = 45. Free stock 29 doesn't cover it, so production 11. But TZ-2832 applies because 45 ≤ 45: 3 weeks.
- **Unit price 680.37:** K-3650, only the base is discounted: 705.15 × 0.95 + 5.90625 + 132.50/29.

### 01.03 · Verstellung · A-2

- **Quantity 16.**
- **Material HZ-2170:** as 01.02.
- **Base price 753.23:** scale 10, "69,275" = 692.75 USD × 1.0873 = 753.2271.
- **Surcharge 12.57:**
  - material surcharge 5.90625
  - setup 85.00 (Q&A 8155)
  - pool share 21.62
  - together: 5.90625 + (85.00 + 21.62)/16
- **Packaging 4.97:** ceil(16/3) = 6 → 79.50 / 16.
- **Bonus 580.41:** see below.
- **Lead time 11:** TZ-4279 doesn't apply because 45 > 44. Stock 29 < 45, so production lead time.
- **Unit price 734.49:** K-2264, no discount: 753.23 + 5.90625 + (85 + 21.62 + 79.50 − 580.41)/16.

### 01.04 · Verriegelung · A-4

- **Quantity 21.**
- **Material HZ-3916:** A-4 has 576 usable, no amendment. Plus 2 × 12 = 600; with 50 mm, 210 bar, Schwenkauge, no certification. In GR-6617, HZ-4889 is mounted by Flansch and drops out.
- **Base price 2107.18:** USD per 100 ST in de-DE "193.799" = 1937.99 USD/ST, scale 10. Times 1.0873 = 2107.1765.
- **Surcharge 5.25:** 0.625 × 3.15 = 1.96875, plus pool 68.93/21.
- **Packaging 1.26:** ceil(21/11) = 2 → 26.50 / 21.
- **Bonus 2131.11.**
- **Lead time 3:** stock 14 < 21, but TZ-5901 applies because 21 ≤ 21.
- **Unit price 1906.85:** no condition group, so only the base is discounted.

### 01.05 · Schwenkantrieb · A-5

- **Quantity 130:** the bill of quantities says 22 sets. Q&A 8151 sets 26 sets. Q&A 8152 (32 sets) is withdrawn by 8153 (25.01, 08:00Z, before the scenario date). 26 sets × 5 pieces per set (A-5 in R-6156) = 130.
- **Material HZ-6932:** 125/300, 250 bar, Flansch. In GR-4287, HZ-3567 has stroke 325.
- **Base price 1866.15:** EUR per 100 ST in en-US "186,615", scale 25.
- **Surcharge 8.06:** 1.375 × 3.15 = 4.33125, plus (setup 57.50 per Q&A 8154 + pool 426.70)/130.
- **Packaging 1.94:** ceil(130/7) = 19 → 251.75 / 130.
- **Bonus 11683.58.**
- **Lead time 3:** stock 51 < 130, but TZ-7899 applies because 130 ≤ 160.
- **Unit price 1692.74:** K-9018, base and material surcharge discounted. Setup and pool stay undiscounted.

### Setup pool RP-5730 (01.03, 01.04, 01.05)

| Position | Weight | exact (cents) | allocated |
|---|---|---|---|
| 01.03 | 16 × 875 = 14000 | 2162.449 | 21.62 |
| 01.04 | 21 × 2125 = 44625 | 6892.805 | 68.93 |
| 01.05 | 130 × 2125 = 276250 | 42669.746 | 426.70 |

Floored this gives 51723 cents. The 2 leftover cents go to the largest remainders, 01.04 and 01.05.

### Project bonus PB-1474 (01.03, 01.04, 01.05)

Basis: 12051.68 + 44250.78 + 242599.50 = 298901.96.
Credit: 2 % × 10000 + 5 % × 283901.96 = 14395.098 → 14395.10.

| Position | exact (cents) | allocated |
|---|---|---|
| 01.03 | 58040.817 | 580.41 |
| 01.04 | 213111.484 | 2131.11 |
| 01.05 | 1168357.699 | 11683.58 |

The 2 leftover cents go to 01.03 and 01.05.

## Traps the tests should watch

- **Q&A numbers:** No. 3916 is newer than 8148. The date counts, not the number.
- **End reserves:** add them after the amendment (482, not 489).
- **Price format:** price unit 100 ST and the number format (en-US/de-DE) change per condition record.
- **Stock:** physical stock includes blocked inspection stock. For HZ-2170 that would give 95 ≥ 45 and wrongly 1 week for 01.03.
- **Blocked material:** HZ-8405 shows status 03. HZ-1609 hides a "03" in the DOM; the visible status is 01.
- **Hidden decoys:** mails contain a hidden "99 % Sonderrabatt" sentence and a draft block. The specification's certification cell has a hidden span "ISO 9001; Hub 999; Druck 999".
