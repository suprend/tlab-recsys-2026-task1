# Wave069 B — exact incremental calculation

Actual UTC: 2026-10-16 12:12:44 UTC. Scheduled12:00; next12:45 unchanged.

**Dedupe first:** HYP046/TLAB005/016 already cover shared calculations; waves024/025 cover panes/refcounts/latest-occurrence DISTINCT;031 covers paid views; rounds040/073 cover category clocks and complete batched005 comparison. **Zero new IDs; optional refinement only.**

**Observed:** pinned manual_features.py batches by grain/anchor, semi-joins daily user/item domains, and scans full observed prefixes for recency/first-seen/metadata. Calling this one scan per feature would weaken the control.

**Sources:** [DBToaster2012](https://www.vldb.org/pvldb/vol5/p968_yanifahmad_vldb2012.pdf), §§3–5, supports signed multiplicities/higher-order deltas but warns about auxiliary-view overhead. [F-IVM](https://arxiv.org/pdf/2303.08583), §§3/5/7/9.4, separates preprocessing, updates, enumeration; its constant-time guarantees have query/ring assumptions. Neither measures this SQL.

**Mechanism:** retain existing exact 24/168h count/DISTINCT maintenance, with a separate append-only observed-state branch. At query t, incorporate only complete global timestamp groups s<t; read before every peer at t. Expire s<t−h, retain s=t−h, including no-arrival days. DISTINCT needs multiplicities or existing conditional latest-occurrence specialization: immutable monotone replay, NULL operands excluded.

Do not expire first_seen or observed action-last timestamps with counts. Latest category needs the entire latest global past bucket: one non-NULL category/no NULL resolves; mixed NULL or multiple categories is ambiguous; all-NULL is missing but not ambiguous. Never backfill older known category or re-key historical event-category counters. Same-time chunks must merge before resolution. Domains newly entering C require retained history or paid backfill. Retained observed keys can grow with historical domain.

**Counterhypothesis:** daily sparse outputs make maintenance/global state/backfill more costly than batched005; join factorization offers little here.

**Prediction/minimum UNRUN toy:** ≤24 events, four midnight anchors, ≤8 C rows: duplicates expire2→1→0; exact24/168h boundaries; no-arrival expiry; global peers; NULL/known and all-NULL latest ties; an item enters C after168h while preserving old first_seen/recency. Permuting peers/chunks and adding future suffix must preserve keyed complete B41+chosen3 values, masks, support, coverage and existing numeric policy.

**Budget UNKNOWN; no execution/grant. Accept** semantic equivalence only after independent literal/current005 comparison. Reject any mismatch. Physical benefit requires a later measured complete comparison charging sorting/authentication, source scans, retained keys, indices/queues, backfill, output, failures and process CPU/wall/RSS/spill; bounded memory/speedup remain unknown. **Task1 benefit:** potentially cheaper exact feature calculation; no ranking-gain claim.
