# AGENTS.md

Wir bauen für den Atira-Hackathon ([Challenge `rfq`](https://ehl-challenge.atira.ai/challenges/rfq.md)) ein
Agenten-System, das aus einer öffentlichen Ausschreibung ein signiertes Angebot macht. Vier Websites, 20 Minuten,
kein Mensch im Loop. Das hier ist für dich als Coding-Agent, nicht für Menschen; die steht in `README.md`.

## Was nicht verhandelbar ist

- **Ein Modell entscheidet.** Wohin navigiert wird, was gesucht wird und welche Dokumente zählen, wählt zur Laufzeit
  ein Modell. Code darf lesen, parsen, rechnen, Formulare füllen und paginieren, aber keine festen Klickpfade und
  keinen Crawler bauen. Sonst lehnt der Reviewer das Paket ab.
- **Keine Werte aus den Websites im Paket.** Keine Referenzen, Materialnummern, Preise, Rabatte, Logins oder TANs,
  auch nicht als Default, Fallback, Beispiel oder in Prompts. Was der Brief jedem Team sagt, ist erlaubt.
- **Der private Datensatz zählt am meisten.** Andere Software, andere Navigation, andere Seitennamen, Infos anders
  verteilt. Nichts darf voraussetzen, wie public-1 aussieht.
- **Rechnen macht Code.** Jede Arithmetik der Bid-Regeln gehört in `agent/calc.py` (Decimal, HALF_UP), nie ins Modell.
- **Fakten nur aus Belegen.** Werte kommen aus Seiten, die ein Agent mit `save_evidence` gesichert hat, nicht aus dem
  Gedächtnis eines Modells.
- **Ranking:** zulässig (richtige Tender-Referenz) → Qualität → Kosten × Zeit. Ohne Antwort: 0 Punkte.

## Wo was liegt

- `agent/` ist das Paket, nur das wird hochgeladen. Alles außerhalb (`docs/`, `eval/`, `bench/`) bleibt lokal.
- `agent/agent.py`: Aufträge der Agents, Resolver, Orchestrierung (`main`)
- `agent/llm.py`: die eine Tool-Schleife (`investigate`) und `ask_json`
- `agent/browser.py`, `agent/reader.js`: Browser-Tools, Seite als Text mit `[n:kind "label"]`
- `agent/calc.py`: die Bid-Arithmetik
- `agent/run.py`, `agent/browsers.py`: Run-Vertrag und Browser (Starter-Kit)
- `docs/`: Regeln und Implementierung je Agent, Einstieg `docs/README.md`

## Befehle

```sh
atira models proxy                                  # Terminal 1, offen lassen
cd agent && eval "$(atira scout --env)"             # Terminal 2: Scouting-Logins, Modell-Variablen
HEADLESS=1 uv run --no-sync python agent.py         # ein lokaler Durchlauf, zählt nie
atira test-run .                                    # Sandbox, Punkte pro Feld, zählt nicht fürs Leaderboard
atira submit .                                      # nur nach Freigabe durch Luca
```

## Glossar

- **Run:** ein Versuch an einem Szenario; Brief, Logins und Schema kommen aus `GET /v1/runs/current`.
- **Brief:** die Aufgabe mit den 29 Bid-Regeln, pro Run geliefert. Quelle der Wahrheit für Regeln.
- **Agent:** eine `investigate`-Schleife mit eigenem Auftrag und Ergebnis-Schema auf einem Tab.
- **Resolver:** ein `ask_json`-Aufruf ohne Browser, der Regeln auf gesicherte Belege anwendet.
- **Beleg (evidence):** eine wörtlich gesicherte Seite. Nur Belege erreichen Resolver und `extract_erp`.
- **Testlauf / Einreichung:** Testlauf zeigt Punkte pro Feld und zählt nicht; Einreichung wird reviewt und gewertet.
  Die *letzte* bestandene Einreichung geht ins Finale, nicht die beste.

## Ways to hurt yourself

- Ein Agent gibt `finish` als String statt Objekt zurück, `json.loads` scheitert, das Ergebnis landet als
  `{"text": ...}`. Dann fehlen Felder wie `tender_reference`, ohne dass etwas abstürzt.
- Eine Position ohne Material führt in `calc.compute` zu `no_bid`, auch wenn der ERP-Agent nur in den Timeout lief.
- `main` setzt feste `siteId`s voraus (`tender-portal`, `customer-portal`, `mail`, `erp`).
- Werte aus public-1 als Beispiel in einen Prompt schreiben, „nur zur Orientierung“: das ist Hardcoding.
- Dev-Skripte, die einen eigenen Chromium starten, im Paket lassen: Der Reviewer sieht sie.
- Ein Testlauf ohne Antwort am Ende sieht aus wie ein Modellfehler, ist aber meist ein Zeitproblem: erst die
  Phasen-Deadlines in `main` prüfen.

## Doku pflegen

Ändert sich das Verhalten eines Agents, ändert sich `docs/` im selben Commit. Verweise auf Code per Datei und
Funktionsname, nie per Zeilennummer. Veraltetes löschen statt markieren. Wie es dazu kam, steht in den
Entire-Checkpoints, nicht in `docs/`.
