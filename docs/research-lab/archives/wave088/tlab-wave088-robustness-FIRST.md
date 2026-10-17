# Wave088 C FIRST — contribution grain and collision units

SOURCE-only independent author C. Current-wave088 peers were unread, undiscussed; helpers: 0. First clock observation: 2026-10-17 02:21:23 UTC (not an exact research-start claim). Original due 02:15 UTC was missed by dispatch; next 03:00 UTC remains unchanged. No raw/DB/Parquet/model access, project imports, SQL, tests or experiments. NEW 0 / REFINE 2 / proposed MERGE 2 / ADMIT 0.

**A — REFINE→MERGE FB-02 / wave021 bounded contributions, TLAB-005/013/016/018; HYP-002/046 construction context.**

Mechanism: existing `Σᵤ min(nᵤᵢ,2)` bounds one actor–item cell; one actor can still contribute 2 to arbitrarily many items. [Mayfly §4](https://arxiv.org/html/2412.07962v1#S4) instead describes clipping a user's entire histogram by its L1 norm before cross-user summation. This source distinction motivates a **comparator**, not a claim of DP or recommendation improvement: `Jᵢ=Σᵤ nᵤᵢ min(1,2/Nᵤ)`, where `Nᵤ=Σⱼnᵤⱼ` covers all raw views in the same strict-past 7d window, including items outside C. Known-empty contributes 0; unknown actors/incomplete applicability inherit wave021's declared masks/coverage. No threshold fitting or row deletion.

Prediction: with U:A and V:A, both aggregates for A equal 2. Add U:B and U:C: A's raw count, distinct audience and cell-cap remain 2, while J_A becomes 5/3. A broad burst changes the global weighting even without a new A action. Uniformly duplicate U's three-row histogram: J_A remains 5/3, but cell-cap A becomes 3. Expiring B/C can increase J_A without an A event. Thus per-cell and per-user robustness are different; selective duplication and ID splitting remain uncontrolled.

Counterhypothesis: broad legitimate shopping is predictive; global clipping suppresses useful demand and couples unrelated items. Correct existing cell-cap needs no repair. Audience-profile normalization already exists elsewhere, so this is an aggregation-grain refinement, not a new normalization family.

Minimal UNRUN witness: five worlds—base 2 rows; breadth 4; uniform-U replication 7; breadth-source 4 with B/C expired at a later anchor; breadth plus one peer-at-t row 5. Total 22 invented input-row occurrences, 2 actors, 3 items. Put B/C at t−W+1, U:A at t−1, V:A at t−2; expiry anchor t+2. Keep A in fixed C and B/C outside. Two independently written list reducers each emit 5×3×2=30 aggregate cells: **60 scalar results / 30 paired comparisons**, including zeros. Wrong candidate-restricted Nᵤ and subtract-only expiry must disagree with literal gold. Passing narrows the semantics; it does not select J for production.

Task1 utility: make automated nested aggregation and its maintenance dependency explicit before claiming heavy-user robustness. Full-history retrieval/state, reverse updates, closure and any later quality comparison remain separately unmeasured.

**B — REFINE→MERGE FB-02 concentration / outliers8A, TLAB-005/013/016. REJECT a new independent-information or confidence-correction claim.**

Mechanism: existing `h=Σnᵤ²/N²` describes actor collision when two raw row indices are sampled with replacement. Excluding self-pairs gives `q=Σnᵤ(nᵤ−1)/(N(N−1))=(Nh−1)/(N−1)`, N>1. [Simpson's primary paper](https://people.wku.edu/charles.smith/biogeog/SIMP1949.pdf) derives the pair statistic under a random-sample model; repeated ecommerce logs do not establish that model.

Prediction: histograms (1,1) and (2,2) have the same h=1/2, but q=0 and 1/3. Raw replication therefore preserves h while changing q. Counterhypothesis: h already intentionally represents empirical concentration, with N/support retained; no correction is needed. Because q is determined by h and N, adding it provides no new information, though a finite learner can respond differently.

Minimal UNRUN witness: exactly four vectors [], [1], [1,1], [2,2] (5 integer entries). Two independent calculations emit N,h,q: **24 scalar results / 12 paired comparisons**. Empty h and N<2 q are missing; reject zero-filling, erroneous replication invariance for q, and unbiasedness/independent-audience claims without assumptions.

Task1 utility: prevent a generated feature alias or logging multiplicity from being sold as new robust evidence.

**Shared proposed budget:** one future source-free pass ≤15 CPU-s /30 wall-s /128 MiB, 0 fits/native/SQL/data/Y; generation, oracle, failures, readback and cleanup included. Execution **UNRUN**, actual cost/adequacy **UNKNOWN**, budget **NOT GRANTED**. No new ID, mandatory gate, reopened final, or original-goal extension.
