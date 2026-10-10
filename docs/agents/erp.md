# ERP-Agents

Drei Teile: Login vorwärmen, Material je Anforderung finden, Fakten aus den Belegen lesen.

## Auftrag

Für jede unterschiedliche Anforderung das aktive Material finden, dessen Bohrung, Hub, Druck, Befestigung und
Zertifizierung exakt passen, und alle Seiten mit seinen Fakten sichern. Gibt es keins, das begründet melden.

## Regeln

3, 4, 6, 10, 15, 22, 23, 25 (Material, Preiskondition, Lieferzeiten, Bestand, Währung, Kartongröße, Massen).

## Eingang / Ausgang

- `run_erp_login`: Login, Ausgang `{ok}`.
- `run_erp_position`: Eingang eine Anforderung aus `resolve_requirements` (5 Attribute + `catalogue_group`).
  Agent-Ausgang `{material_number, why}`.
- `extract_erp`: macht daraus `ERP_RESULT`: Status, Attribute, `available_stock_pieces` (nur frei verwendbar),
  Lieferzeiten Lager/Produktion, `pieces_per_carton`, `allocation_mass`, `surcharge_mass`, `price_index_key`,
  `setup_fee`, `price_condition` (Gültigkeit, Währung, FX-Schlüssel, Preiseinheit, Zahlenformat, Staffeln wie angezeigt).

## Implementierung

- `agent/agent.py` `run_erp_login`: Tag `erp-login`, max. 20 Schritte, Phase 1. Nur Sitzung aufwärmen.
- `agent/agent.py` `run_erp_position`: Tag `erp:<Kataloggruppe>`, max. 40 Schritte, Deadline end − 6 min.
  `main` dedupliziert Anforderungen und startet je eine in einem eigenen Tab desselben Browsers.
- `agent/agent.py` `extract_erp`: läuft als `check` beim `finish`. Ein `ask_json` liest die Fakten **nur aus den
  gesicherten Seiten**. Fehlen Pflichtfelder oder Staffelpreise, wird `finish` abgelehnt mit einer Liste, was fehlt.

## Fallen

- SAP-artige Transaktionscodes, F4-Suchhilfe, Statuscodes, kurzer Session-Timeout.
- Leere oder zu breite Suchen listen nichts; auf höchstens 20 Treffer eingrenzen.
- Staffelpreise oft nur in einer eigenen Ansicht der Kondition; mehrere Konditionen mit Gültigkeitszeiträumen.
- Bestand nach Lagerort und Bestandsart; gesperrter Bestand zählt nicht.

## Offen

- „Kein passendes Material“ und „Agent gescheitert“ sehen gleich aus (`material_number` leer). Beides führt zu
  `no_bid`. Der Agent muss den Unterschied melden, damit `calc` im zweiten Fall die Position auslässt.
- Wartet auf Phase 2, obwohl nur die Anforderungen gebraucht werden.
