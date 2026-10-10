"""Score an RFQ answer against eval/expected.json (docs/scoring.md, bid case).

usage: python eval/compare.py answer.json [expected.json]
"""
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

# Checks that exist in public-1: Q&A 8153 withdraws the quantity change for 01.05,
# and the MET-4607 index is chosen by date, which feeds every surcharge_per_unit.
WITHDRAWN_POSITIONS = ["01.05"]
METAL_FIELD = "surcharge_per_unit"

FIELDS = [
    ("material_number", 0.20, "text"),
    ("quantity", 0.15, "int"),
    ("base_unit_price", 0.15, "money"),
    ("surcharge_per_unit", 0.10, "money"),
    ("packaging_per_unit", 0.10, "money"),
    ("rebate_total", 0.10, "money"),
    ("unit_price", 0.10, "money"),
    ("lead_time_weeks", 0.10, "int"),
]


def cents(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def same(kind, got, want):
    if got is None or got == "":
        return False
    if kind == "money":
        return cents(got) == cents(want)
    if kind == "int":
        return int(got) == int(want)
    return str(got).strip() == str(want).strip()


def score(ans, exp):
    rows = []
    add = lambda part, pts, max_pts, note="": rows.append((part, pts, max_pts, note))

    add("decision", 5 * (ans.get("decision") == exp["decision"]), 5, ans.get("decision"))
    ref_ok = ans.get("tender_reference") == exp["tender_reference"]
    add("tender_reference", 5 * ref_ok, 5, ans.get("tender_reference"))
    disc = ans.get("discount_percent")
    add("discount_percent", 5 * (disc is not None and Decimal(str(disc)) == Decimal(str(exp["discount_percent"]))), 5, disc)
    add("total_net", 5 * same("money", ans.get("total_net"), exp["total_net"]), 5, f"{ans.get('total_net')} vs {exp['total_net']}")

    got = {}
    extras = 0
    for p in ans.get("positions") or []:
        if p.get("position") in got or p.get("position") not in {e["position"] for e in exp["positions"]}:
            extras += 1
        else:
            got[p["position"]] = p
    own_sum = sum((Decimal(p["quantity"]) * cents(p["unit_price"]) for p in ans.get("positions") or []), Decimal(0))
    arith = len(got) == len(exp["positions"]) and same("money", ans.get("total_net"), own_sum)
    add("arithmetic", 5 * arith, 5, f"sum(q*unit)={cents(own_sum)}")

    ok = all(same("int", got.get(e["position"], {}).get("quantity"), e["quantity"])
             for e in exp["positions"] if e["position"] in WITHDRAWN_POSITIONS)
    add("withdrawn_qa_quantity", 5 * ok, 5, ",".join(WITHDRAWN_POSITIONS))
    ok = all(same("money", got.get(e["position"], {}).get(METAL_FIELD), e[METAL_FIELD]) for e in exp["positions"])
    add("metal_index", 5 * ok, 5, f"all {METAL_FIELD}")
    checks = 10

    share = Decimal(75 - checks) / len(exp["positions"])
    pos_total = Decimal(0)
    for e in exp["positions"]:
        a = got.get(e["position"], {})
        for field, weight, kind in FIELDS:
            pts = share * Decimal(str(weight)) * same(kind, a.get(field), e[field])
            pos_total += pts
            add(f"  {e['position']}.{field}", pts, share * Decimal(str(weight)), f"{a.get(field)} vs {e[field]}")
    if extras:
        pos_total -= share * extras
        add("extra/duplicate positions", -share * extras, 0, str(extras))
    add("positions", max(pos_total, Decimal(0)), 75 - checks)

    top = [r for r in rows if not r[0].startswith("  ") and r[0] != "extra/duplicate positions"]
    total = sum(Decimal(str(r[1])) for r in top)
    return rows, total, ref_ok


def main():
    ans = json.loads(Path(sys.argv[1]).read_text())
    exp_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).with_name("expected.json")
    exp = json.loads(exp_path.read_text())
    rows, total, eligible = score(ans, exp)
    for part, pts, max_pts, note in rows:
        mark = "✓" if Decimal(str(pts)) >= Decimal(str(max_pts)) and max_pts else ("✗" if max_pts else "-")
        print(f"{mark} {part:<34} {float(pts):6.2f} / {float(max_pts):5.2f}  {note}")
    print(f"\nquality {float(total):.2f} / 100 · eligible: {'yes' if eligible else 'no'}")


if __name__ == "__main__":
    main()
