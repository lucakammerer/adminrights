# Bid-Regeln → Umsetzung

Die Regeln stehen vollständig im Brief jedes Runs und auf der [Challenge-Seite](https://ehl-challenge.atira.ai/challenges/rfq.md#bid-rules).
Hier nur, wer sie umsetzt. **Sammeln** = welcher Agent die Belege holt, **Entscheiden** = wer die Regel anwendet.

| # | Regel | Sammeln | Entscheiden | Status |
| --- | --- | --- | --- | --- |
| 1 | Menge: Tender, überschrieben von neuester Klarstellung | tender | resolve_requirements | ✅ |
| 2 | Anforderung aus der als aktuell markierten Revision | spec | resolve_requirements | ✅ |
| 3 | Material: aktiv, alle 5 Attribute exakt gleich; sonst no_bid | erp | run_erp_position, calc | ⚠️ siehe [calc](agents/calc.md#offen) |
| 4 | Preis: Kondition gültig am Stichtag, höchste erreichte Staffel, Rabatt, HALF_UP | erp | extract_erp, calc | ✅ |
| 5 | Rabatt: neueste Freigabe des Vertriebsleiters für exakt diese Referenz, sonst 0 % | mail | resolve_commercials | ✅ |
| 6 | Lieferzeit: Lager, wenn Bestand reicht, sonst Produktion | erp | calc | ✅ |
| 7 | Summe: Σ Menge × Stückpreis, HALF_UP | – | calc | ✅ |
| 8 | Entscheidung: bid mit allen Positionen oder no_bid | – | calc | ✅ |
| 9 | Teilabgabe: unfertige Positionen auslassen, trotzdem signieren | – | submit | ❌ fehlt |
| 10 | Datensätze finden: ERP nach Kataloggruppe, Mail mit Referenz + Thema | erp, mail | Aufträge | ✅ |
| 11 | Ein Modell wählt Navigation, Suchen, Dokumente | alle | Architektur | ✅ |
| 12 | Konditionsgruppe aus Q&A, Bedeutung aus Konditionsregeln-Mail | tender, mail | resolve_commercials | ✅ |
| 13 | Zurückgezogene Q&A-Antworten ignorieren | tender | resolve_requirements | ✅ |
| 14 | Technische Änderungen nur für die genannte Revision und Anforderung | tender | resolve_requirements | ✅ |
| 15 | Gemeinsamer Bestand je Material über alle Positionen | erp | calc | ✅ |
| 16 | Bedingte Freigabe: Mindestbestellwert inklusiv, sonst 0 % | mail | resolve_commercials, calc | ✅ |
| 17 | Einheiten: Satz → Stück über Stück pro Satz der Revision | tender, spec | resolve_requirements | ✅ |
| 18 | Optionale Preisfelder: Basis, Zuschlag, Verpackung, Bonus | – | calc | ✅ |
| 19 | Gleiche Regeln für public und private | – | – | – |
| 20 | Nutzbarer Weg: Änderungen, dann + 2 × Reserve aus Technikfreigabe | spec, mail | resolve_requirements | ✅ |
| 21 | Autorität und Zeit: neuester gültiger Datensatz, exakte Referenz, berechtigter Absender | mail | resolve_commercials | ✅ |
| 22 | Währung: Preiseinheit normalisieren, Staffel, Kurs, HALF_UP | erp, mail | extract_erp, resolve_commercials, calc | ✅ |
| 23 | Verpackung: ceil(Stück / Kartongröße) × Tarif | tender, erp, mail | resolve_commercials, calc | ✅ |
| 24 | Lieferzusage: nur bei passendem Material und Bedarf ≤ Obergrenze | tender, mail | resolve_commercials, calc | ✅ |
| 25 | Gemeinsame Rüstkosten nach Menge × Allokationsmasse | tender, erp, mail | resolve_commercials, calc | ✅ |
| 26 | Projektbonus: marginale Staffeln, Verteilung nach größten Resten | mail | resolve_commercials, calc | ✅ |
| 27 | Endpreis aus ungerundeten Komponenten, einmal runden | – | calc | ✅ |
| 28 | Metallindex: Kurs, dessen Fenster den Stichtag enthält | mail | resolve_commercials | ✅ |
| 29 | Punkteschema | – | – | – |

✅ umgesetzt, ⚠️ umgesetzt mit bekannter Lücke, ❌ fehlt. „Umgesetzt“ heißt im Code vorhanden, nicht verifiziert.
Verifiziert wird gegen die Referenzlösung in `eval/` und die Punkte pro Feld aus Testläufen.
