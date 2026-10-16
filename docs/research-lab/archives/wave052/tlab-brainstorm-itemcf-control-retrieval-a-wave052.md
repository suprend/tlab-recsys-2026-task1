# Wave052 blind FIRST B — strengthen the existing support control

Zero new mechanism/ID: refine [HYP-001's existing F0/F1 contrast](/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/itemcf-hyp001-refinement.md). Do not change 051's view-only extractor contract.

**Mechanism/prediction.** Add the same declared degree/activity block D to both arms: candidate external audience degree, retained-history degree summaries and query view activity, with missing flags. F0=eligible frozen B/W base+history_n+supported_pairs+defined_fraction+D; F1=F0+itemcf_mean. Incremental gain must survive this control; otherwise degree/support explanation remains viable. This tests beyond finite D, not every possible function of degrees.

**Invented witness, not quality evidence.** Other-viewer audiences are h={1,2,3,4}, a={1,2,3,4}, b={1,2,3,5}. Actors 1–3 view {h,a,b}; actor 4 {h,a,x}; actor 5 {b,x,y}: everyone has degree 3. Query actor views only h and is excluded. Candidate degrees=4, history degree=4, support-count=defined-fraction=1 for both. Existing threshold/shrinkage yields s(a,h)=2/7 versus s(b,h)=9/52. Past purchases can supply both candidates. Either future purchase remains possible. The witness proves non-aliasing of degrees/support summaries, not predictive value or information beyond exact overlaps.

**Future comparison — UNRUN.** Two fresh fits, identical Q/C/fullY, training/query weights, chronology, settings and selector; no restriction to supported or purchasing users. Primary paired fullY conditional-query NDCG retains off-C purchases; predeclare Recall guard and useful-effect threshold. An unmet decision rule means no admission; CI crossing zero is inconclusive, not proof of equivalence.

**Benefit/cost.** Avoid crediting compatibility for degree/activity effects. Pay full historical scans, warmup/postings, D, exact intersections, missingness/readback, failures and fits; at ceiling K, ≤2K dependent inner checks plus two outer model evaluations/one contrast. Total cost and remaining six-CPU-hour balance UNKNOWN. No current final reuse, grant or mandatory gate.
