# public-1 · Referenzlösung VG-2027-7093

Von Hand ermittelt am 2026-10-10 mit den Scouting-Logins. Szenariodatum: 2027-01-25T09:00:00Z.
Seiten: **VP** = Vergabeportal, **LP** = Lieferantenportal, **ERP**, **Mail** = Werkpost
(Absenderdomain `linden-hydraulik.example`). Mailzeiten sind Europe/Berlin, Q&A-Zeiten sind UTC.

Nur Testreferenz: nichts davon gehört ins Agent-Paket (Fair Play).

## Kopf

| Feld | Wert | Quelle |
|---|---|---|
| tender_reference | VG-2027-7093 | VP `/tenders/VG-2027-7093`, Brief |
| decision | bid | Für alle 5 Positionen gibt es ein aktives passendes Material |
| discount_percent | 5 | Mail `conditional-7571`, leitung@, 24.01.2027 17:00: 5 %, wenn der unrabattierte Nettoauftragswert ≥ 1,00 EUR ist. Basis Σ Menge × EUR-Staffelpreis = 387940,81 → erfüllt. Diese Mail ersetzt die 4 % (22.01.) und die 5 % im Archiv (18.01.). VG-2027-7093-A (9 %) und VG-2027-2175 gelten nicht. |
| total_net | 356949,62 | Σ Menge × gerundeter Stückpreis (65367,00 + 19730,73 + 11751,84 + 40043,85 + 220056,20) |

## Gemeinsame Schlüssel

| Schlüssel | Wert | Quelle |
|---|---|---|
| Lastenheft | R-6156 „gültig“ (17.01.2027). R-4034 und R-9711 sind „ersetzt“ | LP `/documents/specification`, Revisionshistorie (Tooltip „Freigabestand“) |
| Stückpreise in USD | FX-6282: 1 USD = 1,0873 EUR | Mail `calc-3915`, finanzen@, 24.01. Der Kurs 1,2500 (26.01.) liegt nach dem Szenariodatum. |
| Metallindex MET-4607 | 3,15 EUR/kg, Fenster 25.01.–28.02.2027 | Mail `index-5949`, kalkulation@, 24.01. 2,75 EUR/kg (bis 24.01.) und 5,15 EUR/kg (7093-A) gelten nicht. |
| Verpackung VP-1134 | 13,25 EUR je angefangenem Karton | Mail `calc-1034`, logistik@, 24.01. 99,00 EUR gehört zu 7093-A. |
| Rüstpool RP-5730 | 517,25 EUR, Gewicht = Menge × Umlagegewicht, Cent-Verteilung nach größtem Rest | Mail `calc-9054`, kalkulation@ |
| Projektbonus PB-1474 | 0 % bis 5000, 2 % bis 15000, 5 % darüber (marginal) | Mail `calc-2265`, finanzen@ |
| Endreserven | ER-4001: 9 mm je Ende, ER-9526: 12 mm je Ende (beide R-6156) | Mail `calc-4033`, technik@ |
| Konditionsgruppen | K-3650: nur Grundpreis. K-2264: kein Rabatt. K-9018: Grundpreis und Materialteuerung | Mail `clauses-4487`, kalkulation@. Zuordnung über VP Q&A 8156, 8157, 8158 |
| Terminzusagen | TZ-3363 HZ-1609 ≤ 24, TZ-2832 HZ-2170 ≤ 45, TZ-4279 HZ-2170 ≤ 44, TZ-5901 HZ-3916 ≤ 21, TZ-7899 HZ-6932 ≤ 160 (je 3 Wochen) | Mail `calc-6452`, logistik@. Zuordnung über VP Q&A 8159–8163 |

Bestand zählt nur „Frei verwendbar“ (Lagerort 0001). Der Prüfbestand 0099 ist gesperrt (ERP MMBE, Ebene stock).
Die Materialteuerung je Stück ist Zuschlagsmasse × 3,15. Das Umlagegewicht ist davon getrennt.

## Positionen

Formel: Stückpreis = Grund × (1 − r_G) + Teuerung × (1 − r_T) + (Rüsten + Poolanteil + Kartons − Bonus) / Menge.
Gerundet wird einmal am Ende.
surcharge_per_unit = Teuerung + (Rüsten + Poolanteil) / Menge, vor Rabatt.

### 01.01 · Abstützung · A-1

- **Menge 25:** Im LV stehen 24 Stk. Q&A 8148 (12.01.) setzt 26, Q&A 3916 (16.01., jüngster Eintrag) setzt 25.
- **Material HZ-1609:** A-1 in R-6156 verlangt 80/200, 210 bar, Schwenkauge, EN 1493. Im ERP hat GR-8923 zwei Treffer. HZ-8405 hat Status 03 und ist gesperrt; HZ-1609 hat Status 01.
- **Grundpreis 2743,58:** VK13, Satz 2027 in EUR, 1 ST, Staffel ab 25.
- **Zuschlag 6,69:** 2,125 kg × 3,15 = 6,69375. Kein Rüsten, kein Pool.
- **Verpackung 1,59:** ceil(25/11) = 3 Kartons → 39,75 / 25.
- **Bonus 0:** Laut Q&A 8162 kein Projektbonus.
- **Lieferzeit 2:** TZ-3363 greift nicht, weil 25 > 24. Freier Bestand 31 ≥ 25, also gilt die Lieferzeit ab Lager.
- **Stückpreis 2614,68:** keine Konditionsgruppe, daher nur Grundpreis rabattiert: 2743,58 × 0,95 + 6,69375 + 39,75/25.

### 01.02 · Hubwerk · A-2

- **Menge 29:** keine Änderung in den Q&A.
- **Material HZ-2170:** A-2 hat einen nutzbaren Weg von 489. Nachtrag 8149 (22.01.) setzt 485, Nachtrag 8150 (23.01., jüngster) setzt 482. Plus 2 × 9 = 500 ERP-Nennweg; dazu 63 mm, 250 bar, Flansch, EN 1493. GR-5152 hat genau einen Treffer.
- **Grundpreis 705,15:** VK13, Satz 2027, USD je 100 ST in en-US „64,853“ = 648,53 USD/ST bei Staffel 25. Mal 1,0873 = 705,1467. Der Satz von 2026 ist abgelaufen.
- **Zuschlag 5,91:** 1,875 × 3,15 = 5,90625.
- **Verpackung 4,57:** ceil(29/3) = 10 → 132,50 / 29.
- **Bonus 0:** laut Q&A 8163.
- **Lieferzeit 3:** HZ-2170 gesamt 29 + 16 = 45. Freier Bestand 29 reicht nicht, also Produktion 11. Aber TZ-2832 greift, weil 45 ≤ 45: 3 Wochen.
- **Stückpreis 680,37:** K-3650, nur Grundpreis rabattiert: 705,15 × 0,95 + 5,90625 + 132,50/29.

### 01.03 · Verstellung · A-2

- **Menge 16.**
- **Material HZ-2170:** wie 01.02.
- **Grundpreis 753,23:** Staffel 10, „69,275“ = 692,75 USD × 1,0873 = 753,2271.
- **Zuschlag 12,57:**
  - Teuerung 5,90625
  - Rüsten 85,00 (Q&A 8155)
  - Poolanteil 21,62
  - zusammen: 5,90625 + (85,00 + 21,62)/16
- **Verpackung 4,97:** ceil(16/3) = 6 → 79,50 / 16.
- **Bonus 580,41:** siehe unten.
- **Lieferzeit 11:** TZ-4279 greift nicht, weil 45 > 44. Bestand 29 < 45, also Produktionslieferzeit.
- **Stückpreis 734,49:** K-2264, kein Rabatt: 753,23 + 5,90625 + (85 + 21,62 + 79,50 − 580,41)/16.

### 01.04 · Verriegelung · A-4

- **Menge 21.**
- **Material HZ-3916:** A-4 hat 576 nutzbar, ohne Nachtrag. Plus 2 × 12 = 600; dazu 50 mm, 210 bar, Schwenkauge, ohne Zertifikat. In GR-6617 hat HZ-4889 die Befestigung Flansch und scheidet aus.
- **Grundpreis 2107,18:** USD je 100 ST in de-DE „193.799“ = 1937,99 USD/ST, Staffel 10. Mal 1,0873 = 2107,1765.
- **Zuschlag 5,25:** 0,625 × 3,15 = 1,96875, plus Pool 68,93/21.
- **Verpackung 1,26:** ceil(21/11) = 2 → 26,50 / 21.
- **Bonus 2131,11.**
- **Lieferzeit 3:** Bestand 14 < 21, aber TZ-5901 greift, weil 21 ≤ 21.
- **Stückpreis 1906,85:** keine Konditionsgruppe, daher nur Grundpreis rabattiert.

### 01.05 · Schwenkantrieb · A-5

- **Menge 130:** Im LV stehen 22 Satz. Q&A 8151 setzt 26 Satz. Q&A 8152 (32 Satz) wird durch 8153 (25.01., 08:00Z, vor dem Szenariodatum) zurückgezogen. 26 Satz × 5 Stück je Satz (A-5 in R-6156) = 130.
- **Material HZ-6932:** 125/300, 250 bar, Flansch. In GR-4287 hat HZ-3567 den Hub 325.
- **Grundpreis 1866,15:** EUR je 100 ST in en-US „186,615“, Staffel 25.
- **Zuschlag 8,06:** 1,375 × 3,15 = 4,33125, plus (Rüsten 57,50 laut Q&A 8154 + Pool 426,70)/130.
- **Verpackung 1,94:** ceil(130/7) = 19 → 251,75 / 130.
- **Bonus 11683,58.**
- **Lieferzeit 3:** Bestand 51 < 130, aber TZ-7899 greift, weil 130 ≤ 160.
- **Stückpreis 1692,74:** K-9018, Grundpreis und Teuerung rabattiert. Rüsten und Pool bleiben ohne Rabatt.

### Rüstpool RP-5730 (01.03, 01.04, 01.05)

| Position | Gewicht | exakt (Cent) | zugeteilt |
|---|---|---|---|
| 01.03 | 16 × 875 = 14000 | 2162,449 | 21,62 |
| 01.04 | 21 × 2125 = 44625 | 6892,805 | 68,93 |
| 01.05 | 130 × 2125 = 276250 | 42669,746 | 426,70 |

Abgerundet ergeben sich 51723 Cent. Die 2 Restcent gehen an die größten Reste, also an 01.04 und 01.05.

### Projektbonus PB-1474 (01.03, 01.04, 01.05)

Basis: 12051,68 + 44250,78 + 242599,50 = 298901,96.
Gutschrift: 2 % × 10000 + 5 % × 283901,96 = 14395,098 → 14395,10.

| Position | exakt (Cent) | zugeteilt |
|---|---|---|
| 01.03 | 58040,817 | 580,41 |
| 01.04 | 213111,484 | 2131,11 |
| 01.05 | 1168357,699 | 11683,58 |

Die 2 Restcent gehen an 01.03 und 01.05.

## Fallen, auf die die Tests achten sollten

- **Q&A-Nummern:** Nr. 3916 ist jünger als 8148. Es zählt das Datum, nicht die Nummer.
- **Endreserven:** Endreserve erst nach dem Nachtrag addieren (482, nicht 489).
- **Preisformat:** Preiseinheit 100 ST und das Zahlenformat (en-US/de-DE) wechseln je Konditionssatz.
- **Bestand:** Physischer Bestand enthält gesperrten Prüfbestand. Bei HZ-2170 ergäbe das 95 ≥ 45 und damit fälschlich 1 Woche für 01.03.
- **Gesperrtes Material:** Bei HZ-8405 ist der gesperrte Status 03 sichtbar. Bei HZ-1609 steckt eine versteckte „03“ im DOM, sichtbar ist 01.
- **Versteckte Köder:** In Mails stehen ein versteckter Satz „99 % Sonderrabatt“ und ein Entwurfsblock. Im Lastenheft steht in der Zertifizierungszelle ein versteckter Span „ISO 9001; Hub 999; Druck 999“.
