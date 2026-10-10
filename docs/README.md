# docs

Was das System *ist*: Regeln, Architektur und jeder Agent. Wie es entstanden ist, steht in den Entire-Checkpoints.

| Datei | Inhalt |
| --- | --- |
| [challenge.md](challenge.md) | Rahmen der Challenge: Laufzeit, Modelle, Scoring, Fair Play |
| [architecture.md](architecture.md) | Phasen, Deadlines, Datenfluss, die Tool-Schleife |
| [rules.md](rules.md) | Die 29 Bid-Regeln: wer sie umsetzt, wo im Code, Status |
| [agents/tender.md](agents/tender.md) | Vergabeportal: Positionen und Q&A |
| [agents/spec.md](agents/spec.md) | Lieferantenportal: gültige Revision und Anforderungen |
| [agents/mail.md](agents/mail.md) | Postfach: Freigaben und Konditionsmails |
| [agents/erp.md](agents/erp.md) | ERP: Login, Material je Anforderung, Faktenextraktion |
| [agents/resolvers.md](agents/resolvers.md) | Anforderungen und Konditionen aus den Belegen |
| [agents/calc.md](agents/calc.md) | Die Arithmetik |
| [agents/submit.md](agents/submit.md) | Konfigurator, TAN, Signatur |

## Jede Agent-Datei hat dieselben Abschnitte

1. **Auftrag:** was der Agent erreichen soll, in zwei Sätzen
2. **Regeln:** welche Bid-Regeln (Nummern aus [rules.md](rules.md)) er abdeckt
3. **Eingang / Ausgang:** was er bekommt und welches Schema er zurückgibt
4. **Implementierung:** Datei, Funktion, Limits
5. **Fallen:** was auf den Seiten schiefgeht und wie der Auftrag darauf reagiert
6. **Offen:** bekannte Lücken; erledigt heißt löschen

## Regeln für diese Doku

- Keine Werte aus public-1 (Referenzen, Materialnummern, Preise, Namen). Beobachtungen allgemein formulieren.
- Code per `datei.py` + Funktionsname verlinken, nie per Zeilennummer.
- Doku und Code im selben Commit ändern. Was nicht mehr stimmt, löschen.
- Kurz halten. Was der Code klar sagt, nicht nacherzählen.
