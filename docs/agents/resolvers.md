# Resolver

Zwei `ask_json`-Aufrufe ohne Browser, parallel nach Phase 1. Sie wenden die Regeln auf die Belege an und liefern
typisierte Fakten für `calc`. Hier steckt die Auslegung: welcher Datensatz gilt, was eine Klausel bedeutet.

## resolve_requirements

**Regeln:** 1, 2, 13, 14, 17, 20.

**Eingang:** Brief, Belege von tender, spec und mail (aus mail nur die Technikfreigaben).

**Ausgang je Position:** `final_quantity_pieces` (+ `quantity_reasoning`), `requirement`, `bore_mm`, `stroke_mm`,
`pressure_bar`, `mounting`, `certification`, `catalogue_group` (+ `requirement_reasoning`).

**Logik im Prompt:**
- Menge: Tender-Menge, ersetzt durch die neueste datierte Klarstellung, zurückgezogene ignorieren, Satz in Stück.
- Anforderung: gültige Revision, darauf nur die Änderungen, die genau diese Revision und Anforderung nennen, nur die
  genannten Attribute.
- Nutzbarer Weg: zum Hub 2 × die Reserve aus der neuesten Technikfreigabe für diese Revision addieren.

## resolve_commercials

**Regeln:** 5, 12, 16, 21, 22, 23, 24, 25, 26, 28.

**Eingang:** Brief, Belege von tender und mail.

**Ausgang:**
- `discount`: `percent`, `min_order_value` (oder null), `source`
- je Position: `discount_applies_to` (`base` | `base_and_surcharge` | `none`), `carton_price`,
  `delivery_commitment` (`material_number`, `max_pieces`, `weeks`) oder null, `setup_pool_member`,
  `project_bonus_member`, `setup_fee`
- global: `fx_rates` (EUR je Fremdwährungseinheit nach FX-Schlüssel), `metal_indices` (EUR/kg am Stichtag),
  `setup_pool_fee`, `project_bonus_bands`

**Logik im Prompt:** exakte Referenz, berechtigter Absender, neuester Datensatz bis zum Stichtag, neuer ersetzt
alten, zukünftige gelten nie. Ohne Konditionsgruppe gilt `base`.

## Implementierung

`agent/agent.py` `resolve_requirements`, `resolve_commercials`, System-Prompt `RESOLVE`. `agent/llm.py` `ask_json`:
JSON-Modus, bis zu 3 Versuche.

## Offen

- Beide hängen an einem einzigen Modellaufruf. Ein Fehler hier trifft viele Felder auf einmal. Die `*_reasoning`-Felder
  in den Logs sind der erste Ort zum Debuggen.
- `build_facts` greift bei FX-Kurs und Metallindex auf den einzigen vorhandenen Wert zurück, wenn der Schlüssel nicht
  passt. Das kann bei mehreren Indizes falsch zuordnen.
