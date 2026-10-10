"""The brief's bid arithmetic over facts the models established. No website values live here: only the rules."""
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from math import ceil

CENT = Decimal("0.01")


def d(value) -> Decimal:
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
    """facts: see FACTS_SCHEMA in agent.py. Returns the answer in the challenge's format plus a calculation trace."""
    positions = facts["positions"]
    reference = facts["tender_reference"]
    approval = facts.get("discount") or {}
    percent = d(approval.get("percent"))
    threshold = approval.get("min_order_value")

    if any(not p.get("material_number") for p in positions):
        if threshold not in (None, ""):
            percent = Decimal(0)
        return {"answer": {"tender_reference": reference, "decision": "no_bid", "currency": "EUR",
                           "discount_percent": float(percent), "positions": [], "total_net": 0},
                "trace": "a position has no matching active material: no_bid"}

    rows = {}
    for p in positions:
        qty = int(p["quantity_pieces"])
        unit = d(p.get("price_unit") or 1)
        fx = d(p.get("fx_eur_per_currency_unit") or 1) if (p.get("currency") or "EUR") != "EUR" else Decimal(1)
        base = cents(scale_price(p["scales"], qty) / unit * fx)
        mass = d(p.get("surcharge_mass_kg_per_piece")) * d(p.get("metal_index_eur_per_kg"))
        rows[p["position"]] = {"p": p, "qty": qty, "base": base, "mass": mass}

    order_value = cents(sum(r["qty"] * r["base"] for r in rows.values()))
    if threshold not in (None, "") and order_value < d(threshold):
        percent = Decimal(0)
    rate = percent / 100

    demand: dict[str, int] = {}
    for r in rows.values():
        demand[r["p"]["material_number"]] = demand.get(r["p"]["material_number"], 0) + r["qty"]

    pool = allocate(d(facts.get("setup_pool_fee")),
                    {k: r["qty"] * d(r["p"].get("allocation_mass")) for k, r in rows.items() if r["p"].get("setup_pool_member")})
    bonus_rows = {k: r["qty"] * r["base"] for k, r in rows.items() if r["p"].get("project_bonus_member")}
    bonus = allocate(bonus_credit(sum(bonus_rows.values(), Decimal(0)), facts.get("project_bonus_bands") or []),
                     bonus_rows)

    answer_rows, total, trace = [], Decimal(0), [f"order value before discount {order_value}, discount {percent} %"]
    for key, r in rows.items():
        p, qty, base, mass = r["p"], r["qty"], r["base"], r["mass"]
        material = p["material_number"]
        rule = p.get("discount_applies_to") or "base"
        base_net = base * (1 - rate) if rule in ("base", "base_and_surcharge") else base
        mass_net = mass * (1 - rate) if rule == "base_and_surcharge" else mass
        setup = d(p.get("setup_fee")) + pool.get(key, Decimal(0))
        cartons = ceil(qty / int(p["pieces_per_carton"])) if p.get("pieces_per_carton") else 0
        packaging = cartons * d(p.get("carton_price"))
        rebate = bonus.get(key, Decimal(0))
        unit_price = cents(base_net + mass_net + (setup + packaging - rebate) / qty)
        commitment = p.get("delivery_commitment") or {}
        ceiling = commitment.get("max_pieces", commitment.get("max_pooled_pieces"))
        if (commitment.get("material_number") or commitment.get("material")) == material and ceiling is not None \
                and demand[material] <= int(ceiling):
            weeks = int(commitment["weeks"])
        elif d(p.get("stock")) >= demand[material]:
            weeks = int(p["lead_time_stock_weeks"])
        else:
            weeks = int(p["lead_time_production_weeks"])
        total += qty * unit_price
        answer_rows.append({"position": key, "material_number": material, "quantity": qty,
                            "unit_price": float(unit_price), "lead_time_weeks": weeks,
                            "base_unit_price": float(base), "surcharge_per_unit": float(cents(mass + setup / qty)),
                            "packaging_per_unit": float(cents(packaging / qty)), "rebate_total": float(rebate)})
        trace.append(f"{key}: {qty} pcs {material} base {base} mass {mass} rule {rule} setup {setup} "
                     f"cartons {cartons} packaging {packaging} rebate {rebate} -> {unit_price} x {qty}, {weeks} weeks")
    return {"answer": {"tender_reference": reference, "decision": "bid", "currency": "EUR",
                       "discount_percent": float(percent), "positions": answer_rows, "total_net": float(cents(total))},
            "trace": "\n".join(trace)}
