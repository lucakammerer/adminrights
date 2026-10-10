# Submit-Agent

## Auftrag

Das berechnete Angebot im Konfigurator des Vergabeportals eintragen, mit einer TAN aus dem Postfach signieren und
verbindlich abgeben. Ohne Abgabe gibt es 0 Punkte.

## Regeln

8, 9, 18 und der Abschnitt „Submission“ des Briefs.

## Eingang / Ausgang

- Eingang: Antwort aus `calc.compute`, Spezifikation je Position (für die Konfigurator-Auswahl), eigene
  Postfachadresse aus dem Mail-Agent (Kontaktfeld), Login des Portals, der Mail-Tab für die TAN.
- Ausgang `{confirmation}`: was das Portal bestätigt hat.

## Implementierung

- `agent/agent.py` `run_submit` → `llm.investigate`, Tag `submit`, max. 70 Schritte, Deadline end − 20 s.
  Werte im deutschen Format mit zwei Nachkommastellen (`german`). Ganze Formularseiten per `form` in einem Aufruf.
- Zusatz-Tool `get_tan`: startet einen eigenen `investigate` im Mail-Tab, Tag `tan`, max. 12 Schritte, höchstens
  2 min. Sucht die neueste TAN-Mail zur gerade gestellten Anfrage.
- Feste Leitplanken im Auftrag: keine zusätzlichen Positionen, keine auslassen, keine eigenen AGB ankreuzen, TAN
  genau einmal anfordern (neue Anfrage macht die alte ungültig, 5 min gültig), Netto statt Brutto.

## Fallen

- Positionen erscheinen in beliebiger Reihenfolge; pro Seite prüfen, welche gemeint ist.
- Formulare mit Reset-Knopf zuerst: gezielt klicken statt Enter.

## Offen

- Keine Teilabgabe (Regel 9). Ist die Zeit knapp oder fehlt eine Position, wird nicht ausgelassen und trotzdem
  signiert. Gebraucht wird ein Watchdog, der spätestens bei end − 3 min mit dem aktuellen Stand abgibt.
- Lokal dauert die Abgabe etwa 275 s; mit Deadline end − 6 min für das ERP bleibt wenig Puffer.
