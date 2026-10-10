# Calculation

No model. `agent/calc.py`: `facts` merges the agents' results, `compute` calculates. Every value a model supplied is read
through `d`/`number`, so text like "7 pieces" or "3 weeks" cannot crash the run, and every object or list through
`record`/`records`, so null, a string or a missing key counts as empty; `facts` and `compute` run outside `safe`.

## Rules

3 (no bid), 4, 6, 7, 8, 15, 16, 18, 22–27.

## facts

Per position, from requirement, commercial terms and ERP: quantity, material, scales (`number`: a number that shows
its own format, with both separators or one repeated, wins over the condition's format hint), price unit, currency and
rate (`lookup`: FX key first, then currency), surcharge mass in kg (`grams_to_kg`) × metal index (`lookup` by index
key), setup fee from mail and ERP, discount rule, stock, lead times, delivery commitment, carton size and price, pool
and bonus membership, allocation mass. Plus reference, discount, pool fee, bonus bands.

## compute

1. Any position the ERP agent reported as `no_match`: `no_bid`, no positions, total 0; a conditional approval → 0 %.
   Positions without material or a quantity are unfinished: left out of the answer and returned as `omitted`, so the
   submit agent omits them in the form (rule 9). A material without prices is still submitted: its base price (and
   the bonus of a bonus member) is left out of the row, everything else is calculated, and its unit price lacks the
   base; the trace marks it `MISSING price`.
2. Base price = scale price (highest scale reached, `scale_price`) / price unit × rate, to the cent.
3. Order value before discount = Σ quantity × base over the priced positions. Below `min_order_value` → 0 %.
4. Sum demand per material across positions (shared stock, delivery commitment).
5. Split the setup pool by quantity × allocation mass; compute the project bonus over marginal bands
   (`bonus_credit`) and split it by goods value. Both via `allocate`: floor to cents, leftover cents to the largest
   remainders, ties by position.
6. Final price = base (discounted per rule) + surcharge (discounted only for `base_and_surcharge`)
   + (setup + pool share + packaging − bonus) / quantity, HALF_UP once.
7. Lead time: commitment if the material matches and demand ≤ ceiling; else stock if stock ≥ demand; else production.
8. Total = Σ quantity × final price, to the cent. Plus a calculation trace (`trace`) for the logs; a position priced
   without its FX rate or metal index is marked `MISSING` there.

Tests: `tests/test_calc.py` (public-1 golden test from `tests/fixtures/facts.json`, values written as text, model
output in other shapes, parsing).

Reported fields: base, surcharge per piece (mass + setup, before discount), packaging per piece, bonus per position.
