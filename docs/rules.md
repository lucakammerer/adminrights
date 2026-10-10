# Bid rules → implementation

The full rules are in every run's brief and on the [challenge page](https://ehl-challenge.atira.ai/challenges/rfq.md#bid-rules).
This only says who implements them. **Gather** = which agent collects the evidence, **decide** = who applies the rule.

| # | Rule | Gather | Decide | Status |
| --- | --- | --- | --- | --- |
| 1 | Quantity: tender, overridden by the latest clarification | tender_portal | resolvers.requirements | ✅ |
| 2 | Requirement from the revision marked current | customer_portal | resolvers.requirements | ✅ |
| 3 | Material: active, all 5 attributes equal; otherwise no bid | erp | erp.run, calc | ✅ |
| 4 | Price: condition valid on the scenario date, highest scale reached, discount, HALF_UP | erp | erp.extract, calc | ✅ |
| 5 | Discount: latest sales director approval for this exact reference, else 0 % | mail | resolvers.commercials | ✅ |
| 6 | Lead time: from stock if stock covers it, else production | erp | calc | ✅ |
| 7 | Total: Σ quantity × unit price, HALF_UP | – | calc | ✅ |
| 8 | Decision: bid with every position, or no bid | – | calc | ✅ |
| 9 | Partial submission: omit unfinished positions, still sign | erp | calc, submit | ⚠️ unfinished positions omitted; no watchdog |
| 10 | Finding records: ERP by catalogue group, mail by reference + topic | erp, mail | missions | ✅ |
| 11 | A model chooses navigation, searches, documents | all | architecture | ✅ |
| 12 | Condition group from Q&A, meaning from the condition-rules mail | tender_portal, mail | resolvers.commercials | ✅ |
| 13 | Ignore withdrawn Q&A answers | tender_portal | resolvers.requirements | ✅ |
| 14 | Technical amendments only for the named revision and requirement | tender_portal | resolvers.requirements | ✅ |
| 15 | Shared stock per material across all positions | erp | calc | ✅ |
| 16 | Conditional approval: minimum order value inclusive, else 0 % | mail | resolvers.commercials, calc | ✅ |
| 17 | Units: set → pieces via the revision's pieces per set | tender_portal, customer_portal | resolvers.requirements | ✅ |
| 18 | Optional price fields: base, surcharge, packaging, bonus | – | calc | ✅ |
| 19 | Same rules for public and private | – | – | – |
| 20 | Usable stroke: amendments, then + 2 × reserve from the technical release | customer_portal, mail | resolvers.requirements | ✅ |
| 21 | Authority and time: latest valid record, exact reference, authorized sender | mail | resolvers.commercials | ✅ |
| 22 | Currency: normalize price unit, scale, rate, HALF_UP | erp, mail | erp.extract, resolvers.commercials, calc | ✅ |
| 23 | Packaging: ceil(pieces / carton size) × tariff | tender_portal, erp, mail | resolvers.commercials, calc | ✅ |
| 24 | Delivery commitment: only for the matching material and demand ≤ ceiling | tender_portal, mail | resolvers.commercials, calc | ✅ |
| 25 | Shared setup by quantity × allocation mass | tender_portal, erp, mail | resolvers.commercials, calc | ✅ |
| 26 | Project bonus: marginal bands, largest-remainder allocation | mail | resolvers.commercials, calc | ✅ |
| 27 | Final price from unrounded components, rounded once | – | calc | ✅ |
| 28 | Metal index: the rate whose window contains the scenario date | mail | resolvers.commercials | ✅ |
| 29 | Scoring | – | – | – |

✅ implemented, ⚠️ implemented with a known gap, ❌ missing. "Implemented" means present in the code, not verified.
Verification happens against the reference solution in `eval/` and the per-field points of test runs.
