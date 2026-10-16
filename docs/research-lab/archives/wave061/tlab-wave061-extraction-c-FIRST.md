Wave061 C — temporal-safe extraction cost; blind FIRST, 2026-10-16 05:55:03 UTC.

Decision: one optional refinement of existing TLAB-013; zero new IDs/admissions. TLAB-014/016 automation and quality claims stay unchanged.

Source finding: manual_features.py already groups all non-ratio expressions by grain and identical anchor, using filtered aggregates and one materialized table per grain. feature_programs.py adds typed expressions to that same compiler; generated columns do not imply a separate event scan each. A proposal merely to batch same-grain features therefore duplicates the implemented control.

Narrow opportunity: the final validator independently executes one invalid-count query per core feature, then one already-batched missing-count query (manual_features.py:245–257). Fuse these counters into one conditional-aggregate result over the same immutable manual_features table; interpret results in original registry order so the first error name and NULL behavior remain identical.

Prediction: passing B with 18 cores changes 19 validator SQL invocations to 1; this is not a measured reduction in physical scans, CPU, wall time or memory. Failing inputs currently short-circuit, so that count prediction applies only to passing inputs.

Nearest finite future CODE canary, UNRUN: four tiny, hand-authored complete tables (empty, valid boundaries, NULLs, multiple violations), fixed registry and immutable table. Compare old/fused invalid and missing counters, first registry-order exception, exact all41 values/order/types/nulls plus retrieval fields; count validator invocations. Include zero counts, ratios 0/1 and NULL, positive/zero recency, negative counts and ratio >1. No event/source regeneration, labels, fits, model selection or metric look. Q/C/fullY, off-C/zero-Y populations and retrieval remain identical.

No cross-anchor cache or window reuse is proposed: strict-past boundaries, expired windows and latest-category timestamp-peer ambiguity remain in the existing extraction.

Goal benefit: potentially cheaper correctness checks while preserving the accepted pipeline. Counterhypothesis: table scans are already cheap/statistics-pruned, or evaluating all counters before the first failure costs more; real extraction may dominate. An optional future paired full-sink benchmark would be needed for resource claims, not warranted now.

All scientific allocations CLOSED/remainder UNKNOWN; consumed helper 50CPU/65wall cannot fund this. Original 06:00 and next 06:45 UTC grid preserved. Stop after freeze.
