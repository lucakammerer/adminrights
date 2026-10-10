"""The brief's bid arithmetic over facts the models established. No website values live here: only the rules."""
import re
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from math import ceil

CENT = Decimal("0.01")


def d(value) -> Decimal:
    """Models sometimes write numbers as text ("1.2345 EUR"): read the number in it."""
    if isinstance(value, str):
        value = number(value.split("=")[-1])  # "1 USD = 1.2345 EUR": the rate is right of "="
    return Decimal(str(value if value is not None else 0))


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def allocate(amount: Decimal, weights: dict[str, Decimal]) -> dict[str, Decimal]:
    """Split an amount in cents by weight: floor each share, hand the leftover cents to the largest remainders,
    ties by ascending position id."""
    total = sum(weights.values())
    if not weights or total <= 0:
        return {key: Decimal(0) for key in weights}
    units = int((amount / CENT).to_integral_value(rounding=ROUND_HALF_UP))
    exact = {key: Decimal(units) * weight / total for key, weight in weights.items()}
    floors = {key: int(value.to_integral_value(rounding=ROUND_FLOOR)) for key, value in exact.items()}
    left = units - sum(floors.values())
    for key in sorted(weights, key=lambda k: (-(exact[k] - floors[k]), k))[:left]:
        floors[key] += 1
    return {key: Decimal(value) * CENT for key, value in floors.items()}


def scale_price(scales: list[dict], quantity: int) -> Decimal:
    reached = [s for s in scales if d(s["min_quantity"]) <= quantity]
    if not reached:
        reached = sorted(scales, key=lambda s: d(s["min_quantity"]))[:1]
    return d(max(reached, key=lambda s: d(s["min_quantity"]))["price"])


def bonus_credit(total: Decimal, bands: list[dict]) -> Decimal:
    credit = Decimal(0)
    for band in bands:
        low = d(band.get("from"))
        high = d(band["to"]) if band.get("to") not in (None, "") else None
        portion = (min(total, high) if high is not None else total) - low
        if portion > 0:
            credit += portion * d(band["percent"]) / 100
    return cents(credit)


def compute(facts: dict) -> dict:
    """facts: from `facts` below. Returns the answer in the challenge's format, the positions left unfinished (to omit
    in the form, rule 9) and a calculation trace."""
    positions = facts["positions"]
    reference = facts["tender_reference"]
    approval = facts.get("discount") or {}
    percent = d(approval.get("percent"))
    threshold = approval.get("min_order_value")

    if any(p.get("no_match") for p in positions):
        if threshold not in (None, ""):
            percent = Decimal(0)
        return {"answer": {"tender_reference": reference, "decision": "no_bid", "currency": "EUR",
                           "discount_percent": float(percent), "positions": [], "total_net": 0},
                "omitted": [], "trace": "a position has no matching active material: no_bid"}
    # a known material without prices is still submitted: material, quantity, surcharge, packaging and lead time
    # keep their own points (rule 9), the base price and a bonus that depends on it stay blank
    omitted = [p["position"] for p in positions if not p.get("material_number") or p["quantity_pieces"] <= 0]
    positions = [p for p in positions if p["position"] not in omitted]

    rows = {}
    for p in positions:
        qty = int(d(p["quantity_pieces"]))
        unit = d(p.get("price_unit") or 1)
        fx = d(p.get("fx_eur_per_currency_unit") or 1) if (p.get("currency") or "EUR") != "EUR" else Decimal(1)
        base = cents(scale_price(p["scales"], qty) / unit * fx) if p.get("scales") else None
        mass = d(p.get("surcharge_mass_kg_per_piece")) * d(p.get("metal_index_eur_per_kg"))
        rows[p["position"]] = {"p": p, "qty": qty, "base": base, "mass": mass}
    priced = {k: r for k, r in rows.items() if r["base"] is not None}

    order_value = cents(sum((r["qty"] * r["base"] for r in priced.values()), Decimal(0)))
    if threshold not in (None, "") and order_value < d(threshold):
        percent = Decimal(0)
    rate = percent / 100

    demand: dict[str, int] = {}
    for r in rows.values():
        demand[r["p"]["material_number"]] = demand.get(r["p"]["material_number"], 0) + r["qty"]

    pool = allocate(d(facts.get("setup_pool_fee")),
                    {k: r["qty"] * d(r["p"].get("allocation_mass")) for k, r in rows.items() if r["p"].get("setup_pool_member")})
    bonus_rows = {k: r["qty"] * r["base"] for k, r in priced.items() if r["p"].get("project_bonus_member")}
    bonus = allocate(bonus_credit(sum(bonus_rows.values(), Decimal(0)), facts.get("project_bonus_bands") or []),
                     bonus_rows)

    answer_rows, total, trace = [], Decimal(0), [f"order value before discount {order_value}, discount {percent} %"]
    for key, r in rows.items():
        p, qty, base, mass = r["p"], r["qty"], r["base"], r["mass"]
        material = p["material_number"]
        rule = p.get("discount_applies_to") or "base"
        base_net = (base or 0) * (1 - rate) if rule in ("base", "base_and_surcharge") else (base or 0)
        mass_net = mass * (1 - rate) if rule == "base_and_surcharge" else mass
        setup = d(p.get("setup_fee")) + pool.get(key, Decimal(0))
        per_carton = int(d(p.get("pieces_per_carton")))
        cartons = ceil(qty / per_carton) if per_carton else 0
        packaging = cartons * d(p.get("carton_price"))
        rebate = bonus.get(key, Decimal(0))
        unit_price = cents(base_net + mass_net + (setup + packaging - rebate) / qty)
        commitment = p.get("delivery_commitment") or {}
        ceiling = commitment.get("max_pieces", commitment.get("max_pooled_pieces"))
        if (commitment.get("material_number") or commitment.get("material")) == material and ceiling is not None \
                and demand[material] <= d(ceiling):
            weeks = int(d(commitment["weeks"]))
        elif d(p.get("stock")) >= demand[material]:
            weeks = int(d(p["lead_time_stock_weeks"]))
        else:
            weeks = int(d(p["lead_time_production_weeks"]))
        total += qty * unit_price
        row = {"position": key, "material_number": material, "quantity": qty,
               "unit_price": float(unit_price), "lead_time_weeks": weeks,
               "base_unit_price": float(base) if base is not None else None,
               "surcharge_per_unit": float(cents(mass + setup / qty)),
               "packaging_per_unit": float(cents(packaging / qty)),
               "rebate_total": None if base is None and p.get("project_bonus_member") else float(rebate)}
        answer_rows.append({k: v for k, v in row.items() if v is not None})
        trace.append(f"{key}: {qty} pcs {material} base {base} mass {mass} rule {rule} setup {setup} "
                     f"cartons {cartons} packaging {packaging} rebate {rebate} -> {unit_price} x {qty}, {weeks} weeks"
                     + "".join(f" MISSING {gap}" for gap in (p.get("gaps") or []) + ["price"] * (base is None)))
    return {"answer": {"tender_reference": reference, "decision": "bid", "currency": "EUR",
                       "discount_percent": float(percent), "positions": answer_rows, "total_net": float(cents(total))},
            "omitted": omitted, "trace": "\n".join(trace + [f"omitted (unfinished): {omitted}"] * bool(omitted))}


def number(text, fmt: str = "") -> float:
    """A number as shown. When the number itself shows its format (both separators, or one repeated), that wins;
    a single separator follows the format hint (de-DE: decimal comma), else a lone comma is decimal."""
    match = re.search(r"-?\d[\d.,]*", str(text))
    if not match:
        return 0.0
    s = match.group(0).rstrip(".,")
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
    elif s.count(",") > 1 or s.count(".") > 1:
        decimal = ""
    elif fmt:
        decimal = "," if re.search(r"\bde[-_]de\b|^de\b", fmt.strip(), re.I) else "."
    else:
        decimal = "," if "," in s else "."
    if decimal == ",":
        return float(s.replace(".", "").replace(",", "."))
    return float(s.replace(",", "") if decimal == "." else s.replace(",", "").replace(".", ""))


def grams_to_kg(text) -> float:
    """A mass as shown, in g or kg. Grams carry no decimals in practice, so "2.125 g" and "2,125 g" are 2125 g."""
    s = str(text)
    if re.search(r"\d\s*(g|gr|gramm|grams?)\b", s, re.I) and not re.search(r"kg|kilo", s, re.I):
        return number(re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", s)) / 1000
    return number(s, "de-DE" if re.search(r"\d,\d", s) else "en-US")


def lookup(table: dict | None, *keys):
    """A rate by its key as two models wrote it ("FX 6282" vs "fx-6282 (USD)"): exact match first, then one key
    containing the other; a table with a single rate needs no key."""
    def norm(key) -> str:
        return re.sub(r"[^0-9A-Z]", "", str(key or "").upper())

    rates = {norm(k): v for k, v in (table or {}).items()}
    wanted = [k for k in map(norm, keys) if k]
    for match in (lambda k, w: k == w, lambda k, w: k and (w in k or k in w)):
        for key in wanted:
            for k, v in rates.items():
                if match(k, key):
                    return v
    return next(iter(rates.values())) if len(rates) == 1 else None


def facts(tender, requirements, commercials, erp: dict) -> dict:
    by_pos = {c["position"]: c for c in commercials.get("positions", [])}
    positions = []
    for req in requirements.get("positions") or []:
        key = req.get("position")
        if not key:
            continue
        e = erp.get(key) or {}
        c = by_pos.get(key, {})
        pc = e.get("price_condition") or {}
        fmt = pc.get("number_format") or ""
        currency = (pc.get("currency") or "EUR").upper()
        fx = None
        if currency != "EUR":
            fx = lookup(commercials.get("fx_rates"), pc.get("fx_key"), currency)
        index = lookup(commercials.get("metal_indices"), e.get("price_index_key"))
        positions.append({
            "position": key, "quantity_pieces": int(d(req.get("final_quantity_pieces"))),
            "material_number": e.get("material_number") or None, "no_match": e.get("no_match") is True,
            "scales": [{"min_quantity": s["from_quantity"], "price": number(s["price_as_shown"], fmt)}
                       for s in pc.get("scales") or []],
            "price_unit": pc.get("price_unit_pieces") or 1, "currency": currency,
            "fx_eur_per_currency_unit": fx,
            "surcharge_mass_kg_per_piece": grams_to_kg(e.get("surcharge_mass") or 0),
            "metal_index_eur_per_kg": index or 0,
            "setup_fee": float(d(c.get("setup_fee")) + d(e.get("setup_fee"))),
            "discount_applies_to": c.get("discount_applies_to") or "base",
            "stock": e.get("available_stock_pieces") or 0,
            "lead_time_stock_weeks": e.get("lead_time_stock_weeks") or 0,
            "lead_time_production_weeks": e.get("lead_time_production_weeks") or 0,
            "delivery_commitment": c.get("delivery_commitment"),
            "pieces_per_carton": e.get("pieces_per_carton"), "carton_price": c.get("carton_price") or 0,
            "setup_pool_member": bool(c.get("setup_pool_member")),
            "allocation_mass": grams_to_kg(e.get("allocation_mass") or 0) * 1000,
            "project_bonus_member": bool(c.get("project_bonus_member")),
            "gaps": [gap for gap, missing in (("FX rate", currency != "EUR" and fx is None),
                                              ("metal index", e.get("surcharge_mass") and index is None)) if missing],
        })
    reference = commercials.get("tender_reference") or tender.get("tender_reference") or ""
    return {"tender_reference": reference, "discount": commercials.get("discount") or {},
            "positions": positions, "setup_pool_fee": commercials.get("setup_pool_fee") or 0,
            "project_bonus_bands": commercials.get("project_bonus_bands") or []}
