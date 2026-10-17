# FIRST — anchors, targets, temporal split

Frozen snapshot: HEAD `c538de4097322715fccac494e2b2becc3279e8e1`; manifest SHA256 `7e2e871f148beac5b9fce3aa23970b370db0c8fdc9eac89958fb6342a4d2a41a`. Independent FIRST; no peer FIRST read.

## 1. Exact scope and caller paths

Fully inspected: `scripts/{anchor_pilot,temporal_contract,protocol_manifest,development_collection,heldout_contract}.py`; corresponding five `tests/test_*.py`; both `configs/protocols/clock-*.json`, three `configs/development/*.json`, `configs/heldout/reporting-only-v1.json`; experiment docs anchor-pilot/development-collection/heldout-contract and target-research01/02/06. Supporting, deliberately partial inspection: candidate_pilot24–194, manual_features146–248, heldout_source1–142, heldout_evaluation74–108, train_baselines90–187; searched training/adaptive/model-data callers and backlog/index/README for chronology/dedup. Pins enumerate every inspected/search-matched file and distinguish full from partial coverage. This is not all632-file coverage.

Traced `build_pilot→create_queries→create_labels`; `run_phase→anchor/C/F producers→aggregate_collection`; `heldout_source.build_day→past-only Q/C/F/calendar maturity`, and heldout full-Y construction. Training phase validation was traced through train_development/train_baselines references and the actual timing validator.

## 2. Confirmed actionable defect

**P2 — Preserve zero-query calendar days when aggregating development shards.** Original `scripts/development_collection.py:346–347,363–364`; upstream `scripts/anchor_pilot.py:259–276`. The collector derives observed calendar coverage solely from `ar['daily_outcomes']`, but that report groups actual Q and contains no row for a valid day with zero eligible users. `create_queries` separately retains the day in `population` (191–192). Empty Q/Y exports and typed zero-row F are supported, so an empty day is not a missing shard. Nevertheless aggregation raises `Missing or duplicate daily report coverage`, after accepted child production, preventing completion and spending the remaining collection budget on a permanently failing resume.

Concrete proposed witness: adapt the existing two-day, one-day-per-shard runtime fixture to phase `[2019-10-08,2019-10-10)`, with only `(Oct08 12:00,view,product10,user1)` and `(Oct09 12:00,purchase,product20,user1)` events. Day08 has Q=Y=C=F=0; day09 has one Q and a full-Y positive outside C. Each actual child is structurally valid; the final `expected_daily` is `[Oct09]` against `[Oct08,Oct09]`. Expected: complete collection with explicit zero counts for day08, retaining empty-Q semantics and still rejecting a physically missing shard. Current actual behavior is statically entailed by the report/grouping and equality check; this witness was **not executed**. The existing empty-source anchor test explicitly expects `daily_outcomes=[]` (`tests/test_anchor_pilot.py:176–181`); runtime tests lack a zero-Q day. No claim that accepted October collections were affected: their documented daily samples are nonempty.

## 3. Boundaries, assumptions and non-findings

- Eligibility is strict-past globally (`anchor_pilot.py:172`); deterministic sample serialization/hash/order precedes labels (182–190). Appending future purchasers cannot select earlier Q on this path. Labels deduplicate identified product IDs, retain off-C/off-catalog purchases, and diagnose first sightings only after sampling. The max-anchor scan still compares first_seen with each query anchor; no supported future-catalog leak found.
- History excludes all anchor-second peers; targets include anchor and exclude end in current configs. Generic endpoint/maturity code also distinguishes right-closed targets and delay. Censored Q remain Q with no fabricated negative labels. Fixed current configs reject immature pilot horizons upfront.
- Source completeness and instantaneous event-time availability are declared assumptions, not measured from max timestamps. NULL-product purchases are explicitly excluded from identified Y and documented; actual incidence/loss remains UNKNOWN. These are not newly found implementation defects.
- Old017 confirmation24–25 has zero decision-compute gap; the development doc explicitly discloses it and runtime refuses confirmation before source reads (205–214). Heldout policy supersedes it with decision24Oct12 and reserved25 onward. Structural supplied-clock/receipt validation cannot establish actual historical completeness/authenticity by itself.
- Protocol schema permits a smaller `max_unique`, while candidate generation explicitly rejects a cap below source-quota sum; the dedicated candidate test requires that rejection. I treat this as a deliberate narrower generator boundary, not silent truncation/leakage.
- Reused selection/adaptive checks after historical final opening are explicitly exploratory (`adaptive_tree_selection.py:1–3` and current backlog). No independent test reservation or unbiased quality claim can be inferred; no reopened final was read here. Ordinary native CLI and callback-abort remain outside this audit.

## 4. Quality hypotheses / dedup

**0 new quality hypotheses.** Searches of backlog and research/target/candidate indexes identify existing HYP-004 (candidate quota/no-refill comparison) and TLAB-013/015 support/uncertainty/reservation work. Repeating those as new ideas would not add a discriminating mechanism. Future experiment cost remains UNKNOWN; no new fit, data access, gate or ID is admitted.

## 5. Most discriminating independent check

After a separate bounded engineering authorization, run the actual synthetic development producer/approval/resume path on the two-day witness above, plus an entirely empty phase. Accept a repair only if both complete with exact explicit calendar coverage, zero counts preserved, C=F, off-C Y retained, and a genuinely absent/duplicated shard still fails. A unit test that fabricates zero report rows would miss the upstream integration fault. No tests, project imports, SQL, raw events, models, native code or scientific experiments were run. Verification here consists of source/text inspection and metadata SHA256/readback only; it proves neither runtime execution nor complete absence of leakage.
