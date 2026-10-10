# Mail-Agent

## Auftrag

Im Vertriebspostfach jede Nachricht sichern, die die Regeln für exakt diese Referenz brauchen, in Posteingang und
Archiv. Auch überholte und bedingte Freigaben sichern, damit der Resolver die gültige wählen kann.

## Regeln

Sammelt für 5, 12, 16, 20, 21, 22, 23, 24, 25, 26, 28. Die Themen stammen aus dem Brief (Regel 21 nennt Betreffe und
Absender), nicht aus public-1.

## Eingang / Ausgang

- Eingang: Brief, Login des Postfachs.
- Ausgang `MAIL_RESULT`: `kept` (eine Zeile, was gesichert ist), `own_address` (eigene Postfachadresse, für das
  Kontaktfeld im Konfigurator), `other_relevant_facts`, plus `evidence`. Die eigentlichen Inhalte sind die Belege.

## Implementierung

`agent/agent.py` `run_mail` → `llm.investigate`, Tag `mail`, max. 60 Schritte, Deadline Phase 1.
Suche immer „Referenz + ein Themenwort“, weil die Suche Wörter mit UND verknüpft. Jede Nachricht über ihre eigene
URL sichern, damit Absender, Datum und Text vollständig sind. TAN-Mails überspringen, die holt `get_tan`
([submit.md](submit.md)).

## Fallen

- Ähnliche Freigaben für andere Ausschreibungen, etwa Referenz mit Suffix.
- Überholte Freigaben, Archivordner, Paging.

## Offen

- Die Themenliste steht fest im Auftrag. Ändert der private Brief Betreffe oder Absender, muss sie aus dem Brief
  abgeleitet werden.
