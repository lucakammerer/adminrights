# Spec-Agent

## Auftrag

Im Lieferantenportal die technische Spezifikation des Käufers finden, die als gültig markierte Revision bestimmen
(nicht die, die zuerst aufgeht) und jede Anforderung dieser Revision vollständig sichern.

## Regeln

Sammelt für 2, 3, 17, 20 (gültige Revision, Attribute fürs Material-Matching, Stück pro Satz, nutzbarer Weg).

## Eingang / Ausgang

- Eingang: Brief, Login des Portals.
- Ausgang `SPEC_RESULT`: `document`, `current_revision`, `revisions[]` (`revision`, `date`, `status`),
  `requirements[]` (`requirement`, `position`, `bore_mm`, `stroke_mm`, `pressure_bar`, `mounting`, `certification`,
  `catalogue_group`, `original_wording`), `other_relevant_facts`, plus `evidence`.

## Implementierung

`agent/agent.py` `run_spec` → `llm.investigate`, Tag `spec`, max. 40 Schritte, Deadline Phase 1.
`original_wording` bleibt wörtlich, weil dort „nutzbarer Weg“ mit Reserve-Schlüssel oder Stück pro Satz stehen kann.

## Fallen

- Öffnet zuerst die älteste Revision.
- Verschachtelte Dokumentenbetrachter, Anforderungstabellen über mehrere Seiten.

## Offen

- Die ERP-Suche wartet auf beide Resolver, braucht aber nur dieses Ergebnis plus Änderungen aus den Q&A. Früher
  starten spart Zeit.
