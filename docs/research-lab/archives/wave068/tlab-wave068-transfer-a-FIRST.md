# Wave068 A FIRST — Instacart cannot synchronize customers

**Dedupe.** One new source instance; **0 new mechanisms**. Refine HYP-002 and TLAB-014/016/018/019 capability work. Existing004/052/070 cover missing clocks; Instacart supplies a concrete customer-relative-clock counterexample absent from047/063.

**Primary evidence.** The [publisher release](https://tech.instacart.com/3-million-instacart-orders-open-sourced-d40d29ead6f2) describes sampled orders and relative time, declares noncommercial use, and excludes products failing its multi-customer/multi-retailer privacy filter. Linked detailed terms, immutable release bytes and current corpus access remain **UNKNOWN**. The [publisher dictionary](https://gist.github.com/jeremystan/c3b39d947d9b88b3ccff3147dbcf6c6b) supplies customer/item IDs, order sequence, weekday/hour, and elapsed days capped30; no absolute date/timezone. Read2026-10-16; no corpus opened.

**Mapping/mechanism.** Nominal user/item keys and ordered basket-prefix count/distinct can transfer. Count order-product memberships, not units or raw purchase events. Cart position is not a timestamped cart channel; views are absent. Aisle/department joins need a declared static-taxonomy policy; historical availability is unknown. Exact24/168h windows, global peers, dailyUTC Q, globally past candidate C and purchase-fullY24 are unsupported. Even a complete released basket is not all production purchases. Capability rejection precedes generation; any sequence-only protocol has a separate identity, not currentB41 approval.

**Counterhypothesis.** Weekday/hour plus relative gaps uniquely reconstruct shared event time.

**Falsifiable prediction / minimal experiment — UNRUN.** Manually specify four invented orders/four basket lines in two compatible calendar embeddings. Hold U fixed; shift V's entire two-order history by seven days, preserving IDs, order numbers, weekday/hour and relative gaps. V's second basket containsX: at anchorT=U's second order it occurs atT+1h versusT−167h. Released relations are identical, but globalX purchase-membership count168h is0 versus1; per-user order-prefix counts agree. Accept only identical released projections, differing calendar oracle and explicit global-clock refusal while preserving sequence outputs. Reject any claimed exact shared-calendar reconstruction. This is a logical witness, not eligible REESQ or executed adapter proof.

**Budget/benefit.** Zero fits; fixture/source review only, unrun. Actual preparation/scan/state/verification/runtime/RSS costs remainUNKNOWN, with no reservation. Task1 gains a precise portability limit for automation; no dataset-quality claim, new mandatory gate, grant or admission.

