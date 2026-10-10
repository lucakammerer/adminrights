"""Hand-derived expected answer for the PUBLIC scenario (public-1, VG-2027-7093), from manual scouting on 2026-10-10.

A test oracle for local development only. It must never be copied into the agent package: the agent has to derive
everything from the websites at run time (fair-play rules), and the private dataset differs anyway.
Facts and their sources are in eval/public-1/scouting-notes.md.
"""
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal as D
from math import ceil
import json

C = D("0.01")
r2 = lambda x: x.quantize(C, ROUND_HALF_UP)

DISCOUNT = D("5")          # leitung@ conditional-7571, 24.01 17:00, min order value 1.00 EUR -> met
FX_USD = D("1.0873")       # finanzen@ calc-3915 (26.01 decoy is future-dated)
MET = D("3.15")            # MET-4607 window 25.01-28.02.2027 contains the scenario date
CARTON_FEE = D("13.25")    # VP-1134, logistik@ calc-1034 (the 99.00 one is for VG-2027-7093-A)
POOL_FEE = D("517.25")     # RP-5730
BANDS = [(D("0"), D("5000"), D("0")), (D("5000"), D("15000"), D("0.02")), (D("15000"), None, D("0.05"))]

# position: qty in pieces, material, price/unit-normalised scale price, currency, surcharge mass g, alloc mass g,
#           carton size, clause, setup, pool, bonus, stock, lead stock, lead prod, commitment (ceiling)
P = {
    "01.01": dict(q=25, mat="HZ-1609", price=D("2743.58"), cur="EUR", sm=2125, am=3100, carton=11, clause="base",
                  setup=D("0"), pool=False, bonus=False, stock=31, ls=2, lp=7, tz=24),
    "01.02": dict(q=29, mat="HZ-2170", price=D("648.53"), cur="USD", sm=1875, am=875, carton=3, clause="base",
                  setup=D("0"), pool=False, bonus=False, stock=29, ls=1, lp=11, tz=45),
    "01.03": dict(q=16, mat="HZ-2170", price=D("692.75"), cur="USD", sm=1875, am=875, carton=3, clause="none",
                  setup=D("85.00"), pool=True, bonus=True, stock=29, ls=1, lp=11, tz=44),
    "01.04": dict(q=21, mat="HZ-3916", price=D("1937.99"), cur="USD", sm=625, am=2125, carton=11, clause="base",
                  setup=D("0"), pool=True, bonus=True, stock=14, ls=3, lp=8, tz=21),
    "01.05": dict(q=130, mat="HZ-6932", price=D("1866.15"), cur="EUR", sm=1375, am=2125, carton=7, clause="base+surcharge",
                  setup=D("57.50"), pool=True, bonus=True, stock=51, ls=1, lp=12, tz=160),
}


def allocate(total_cents, weights):
    """Proportional cent allocation: floor, remaining cents to largest remainders, ties by ascending position."""
    wsum = sum(weights.values())
    raw = {k: D(total_cents) * D(w) / D(wsum) for k, w in weights.items()}
    out = {k: int(v.to_integral_value(ROUND_DOWN)) for k, v in raw.items()}
    rest = total_cents - sum(out.values())
    for k in sorted(raw, key=lambda k: (-(raw[k] - out[k]), k))[:rest]:
        out[k] += 1
    return {k: D(v) / 100 for k, v in out.items()}


for p in P.values():
    p["base"] = r2(p["price"] * FX_USD) if p["cur"] == "USD" else p["price"]
    p["sur"] = D(p["sm"]) / 1000 * MET

pool = allocate(int(POOL_FEE * 100), {k: p["q"] * p["am"] for k, p in P.items() if p["pool"]})
bonus_base = {k: p["q"] * p["base"] for k, p in P.items() if p["bonus"]}
tb = sum(bonus_base.values())
credit = r2(sum((min(tb, hi) - lo) * rate for lo, hi, rate in [(lo, hi or tb, r) for lo, hi, r in BANDS] if tb > lo))
bonus = allocate(int(credit * 100), {k: int(v * 100) for k, v in bonus_base.items()})

demand = {}
for p in P.values():
    demand[p["mat"]] = demand.get(p["mat"], 0) + p["q"]

f = 1 - DISCOUNT / 100
positions, total = [], D(0)
for k, p in P.items():
    q = p["q"]
    base_d = p["base"] * (f if p["clause"] in ("base", "base+surcharge") else 1)
    sur_d = p["sur"] * (f if p["clause"] == "base+surcharge" else 1)
    setup = p["setup"] + pool.get(k, D(0))
    pack = ceil(q / p["carton"]) * CARTON_FEE
    reb = bonus.get(k, D(0))
    unit = r2(base_d + sur_d + (setup + pack - reb) / q)
    d = demand[p["mat"]]
    lead = 3 if d <= p["tz"] else (p["ls"] if p["stock"] >= d else p["lp"])
    total += q * unit
    positions.append(dict(position=k, material_number=p["mat"], quantity=q, unit_price=float(unit), lead_time_weeks=lead,
                          base_unit_price=float(p["base"]), surcharge_per_unit=float(r2(p["sur"] + setup / q)),
                          packaging_per_unit=float(r2(pack / q)), rebate_total=float(reb)))

print(json.dumps(dict(tender_reference="VG-2027-7093", decision="bid", currency="EUR", discount_percent=float(DISCOUNT),
                      positions=positions, total_net=float(r2(total))), indent=1))
