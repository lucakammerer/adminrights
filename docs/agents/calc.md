# Calculation

No model. `agent/agent.py` `build_facts` merges the results, `agent/calc.py` `compute` calculates.

## Rules

3 (no bid), 4, 6, 7, 8, 15, 16, 18, 22–27.

## build_facts

Per position, from requirement, commercial terms and ERP: quantity, material, scales (parsed in the condition's
number format, `number`), price unit, currency and rate, surcharge mass in kg (`grams_to_kg`) × metal index, setup fee
from mail and ERP, discount rule, stock, lead times, delivery commitment, carton size and price, pool and bonus
membership, allocation mass. Plus reference, discount, pool fee, bonus bands.

## compute

1. Any position without a material: `no_bid`, no positions, total 0; a conditional approval → 0 %.
2. Base price = scale price (highest scale reached, `scale_price`) / price unit × rate, to the cent.
3. Order value before discount = Σ quantity × base. Below `min_order_value` → 0 %.
4. Sum demand per material across positions (shared stock, delivery commitment).
5. Split the setup pool by quantity × allocation mass; compute the project bonus over marginal bands
   (`bonus_credit`) and split it by goods value. Both via `allocate`: floor to cents, leftover cents to the largest
   remainders, ties by position.
6. Final price = base (discounted per rule) + surcharge (discounted only for `base_and_surcharge`)
   + (setup + pool share + packaging − bonus) / quantity, HALF_UP once.
7. Lead time: commitment if the material matches and demand ≤ ceiling; else stock if stock ≥ demand; else production.
8. Total = Σ quantity × final price, to the cent. Plus a calculation trace (`trace`) for the logs.

Reported fields: base, surcharge per piece (mass + setup, before discount), packaging per piece, bonus per position.

## Open

- Step 1 doesn't distinguish "no material" from "ERP agent failed" (see [erp.md](erp.md#open)). In the second case
  the position should be omitted instead of `no_bid`; a no bid in a bid scenario loses almost all position points.
