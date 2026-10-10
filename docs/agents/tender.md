# Tender-Agent

## Auftrag

Im Vergabeportal die Ausschreibung mit der exakten Referenz aus dem Brief finden und alles sichern, was die Regeln
aus dem Portal brauchen: Leistungsverzeichnis und jede Bieterfrage wörtlich. Die Angebotsabgabe startet er nicht.

## Regeln

Sammelt für 1, 12, 13, 14, 17, 23, 24, 25 (Menge, Konditionsgruppe, Rückzüge, technische Änderungen, Einheiten,
Verpackungstarif, Lieferzusage, Rüstpool). Entschieden wird in [resolvers.md](resolvers.md).

## Eingang / Ausgang

- Eingang: Brief (bis „## Site access“), Login des Portals, Referenz per Regex aus dem Brief.
- Ausgang `TENDER_RESULT`: `tender_reference`, `title`, `positions[]` (`position`, `description`, `quantity`,
  `unit`), `clarifications[]` (`number`, `date`, `question`, `answer`), `other_relevant_facts`, plus `evidence`.

## Implementierung

`agent/agent.py` `run_tender` → `llm.investigate`, Tag `tender`, max. 45 Schritte, Deadline Phase 1.
Gibt Interesse ab („Teilnahme bekunden“), falls Dokumente dahinter liegen. Sichert Leistungsverzeichnis und jede
Q&A-Seite mit `save_evidence`.

## Fallen

- Cookie-Wall, instabile Fehlerseiten, Dokumente hinter Interessensbekundung, iframes, ZIPs.
- Q&A über mehrere Seiten; Antworten ändern Mengen, ziehen frühere zurück oder vergeben Schlüssel.
- Frist in anderer Zeitzone.

## Offen

- `finish` kam im lokalen Lauf als String mit ungültigem JSON zurück (wörtliche Q&A-Texte). `investigate` macht
  daraus `{"text": ...}`, `tender_reference` fehlt dann in `build_facts`. Fix: Referenz aus dem Brief nehmen und ein
  kaputtes `finish` an das Modell zurückgeben.
- Sucht nur im Vergabeportal. Liegen Q&A im privaten Datensatz woanders, fehlen sie.
