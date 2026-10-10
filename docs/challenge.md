# Challenge

Quellen: [rfq.md](https://ehl-challenge.atira.ai/challenges/rfq.md), [scoring](https://ehl-challenge.atira.ai/docs/scoring.md),
[fair play](https://ehl-challenge.atira.ai/docs/fair-play.md), [run contract](https://ehl-challenge.atira.ai/docs/run-contract.md),
[submitting](https://ehl-challenge.atira.ai/docs/submitting.md). Bei Widerspruch gelten die Quellen und der Brief des Runs.

## Rahmen

| | |
| --- | --- |
| Gewerteter Lauf | 20 min; Setup davor bis 5 min mit Netz, zählt nicht |
| Testlauf | bis 2 h, bis zu 4 gleichzeitig, Punkte pro Feld |
| Einreichung | eine zur Zeit, Review durch KI vorab |
| Browser | bis 4 (`"browsers"` in `agent.json`), Tabs frei, keine eigenen Browser |
| Sandbox | 4 vCPU, 8 GB, 1280×800; nur Plattform, Websites und Modell-Proxy erreichbar |
| Antwort | im Konfigurator des Vergabeportals, signiert mit TAN aus dem Postfach |

## Modelle

| Modell | Preis (simuliert) | Limit | Einsatz |
| --- | --- | --- | --- |
| Qwen3.8-Flash-Next | $0.15/M in, $0.016/M cached, $0.47/M out | 32 gleichzeitig/Team | alles |
| Cloudflare Clef | $0.24/M in | 16 gleichzeitig/Team | ungenutzt, nur wenn messbar schneller |

## Scoring (Bid)

Entscheidung 5, Referenz 5, Rabatt 5, Summe 5, Arithmetik 5, falls vorhanden: zurückgezogene Q&A 5, Metallindex
nach Datum 5. Rest auf die Positionen verteilt: Material 20 %, Menge 15 %, Basispreis 15 %, Zuschlag, Verpackung,
Projektbonus, Endpreis, Lieferzeit je 10 %. Zusätzliche oder doppelte Positionen kosten je einen Positionsanteil.

No-Bid: Entscheidung 75, Referenz 5, keine Positionen 5, Summe 0 15.

## Ranking und Gewinner

Lauf: zulässig → Qualität → Kosten × Zeit (Kosten mindestens $0.01, Zeit mindestens 1 s).
Leaderboard: beste Einreichung. Finale: **letzte** bestandene Einreichung, auf privatem Datensatz, optional Best of 3.
Gewinner: privater Datensatz → öffentlicher Datensatz → Eleganz.
