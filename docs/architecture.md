# Architektur

Modelle sammeln und entscheiden, Code rechnet. Ein Durchlauf in `agent/agent.py` `main`:

```
main (Budget = min(Restzeit, 19 min), end = Start + Budget)
 ├─ Phase 1, parallel, je ein Browser, Deadline end − 9 min
 │   tender · spec · mail · erp-login
 ├─ Phase 2, parallel, kein Browser
 │   resolve_requirements · resolve_commercials
 ├─ Phase 3, parallel in ERP-Tabs, Deadline end − 6 min
 │   run_erp_position je unterschiedlicher Anforderung
 ├─ Phase 4, Code
 │   build_facts → calc.compute
 └─ Phase 5, Deadline end − 20 s
     run_submit (+ get_tan im Mail-Tab)
```

Gibt es weniger als 4 Browser, öffnet `main` die übrigen Seiten als Tabs in Browser 1.

## Die Tool-Schleife (`agent/llm.py` `investigate`)

Jeder Browser-Agent ist dieselbe Schleife. Er unterscheidet sich nur durch Auftrag, Ergebnis-Schema, Deadline und
`max_steps`.

- **Sicht:** `Tab.read` liefert die Seite als Text (`agent/reader.js`): versteckte Köder raus, Labels, Tooltips,
  eingeklappte Details und gleiche-Origin-iframes rein, jedes Bedienelement als `[n:kind "label"]`. Max. 14 000
  Zeichen pro Lesen, Rest per `offset`.
- **Tools:** `read`, `goto`, `click`, `fill`, `select`, `check`, `press`, `back`, `form` (ganze Formularseite nach
  sichtbaren Labels), `fetch` (URL lesen ohne Navigation, öffnet PDFs und ZIPs), `save_evidence`, `note`, `finish`.
- **Belege:** `save_evidence` speichert eine Seite wörtlich. Nur diese Belege sehen Resolver und `extract_erp`.
- **Kontext klein halten:** Tool-Ergebnisse der letzten 4 Schritte bleiben ganz (`KEEP_STEPS`), ältere werden auf
  300 Zeichen gekürzt. Was der Agent behalten will, schreibt er mit `note` fest.
- **`check`:** optionaler Prüfer beim `finish`. Meldet er ein Problem, wird `finish` abgelehnt und der Agent arbeitet
  weiter (genutzt vom ERP-Agent).
- **Zeit:** 60 s vor der Deadline kommt „call finish now“; danach wird `finish` per `tool_choice` erzwungen.
- **Modell:** `AGENT_MODEL`, Standard Qwen3.8-Flash-Next über `QWEN_BASE_URL`. `chat` versucht es bis zu 6-mal.

Der gemeinsame System-Prompt `SYSTEM` in `agent/agent.py` beschreibt die Fallen der Seiten allgemein: Cookie-Wall,
Popups mit irreführendem „Weiter“, falsche Toolbars, Entsperr-Slider, veraltete Versionen zuerst, Paging, 503,
Zahlenformate. Er nennt keine Seite und keinen Wert.

## Resolver (`agent/llm.py` `ask_json`)

Ein Aufruf mit `response_format=json_object`, bis zu 3 Versuche bei ungültigem JSON. Eingang ist der Brief plus die
Belege der Agents, Ausgang ein festes JSON-Schema im Prompt.

## Logs

`main` schreibt pro Phase eine Zeile: `[tender]`, `[spec]`, `[mail]`, `[requirements]`, `[commercials]`, `[erp]`,
`[facts]`, `[calc]`, `[answer]`, `[submit]`. Jeder Agent-Schritt erscheint als `[tag] n: tool {args}`.
