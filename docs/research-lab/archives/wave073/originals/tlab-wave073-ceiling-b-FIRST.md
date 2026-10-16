# Wave073 ceiling-B FIRST

**NEW0 / REFINE1 / ADMIT0.** Independent FIRST; no peer073 material consumed. Source-only reasoning, no external papers needed.

**Mechanism.** For mature full-positive queries Q+, let m=|Yq|, h=|Yq∩Cq| and G(n)=Σ(j=1..n)1/log₂(j+1), G(0)=0. Fixed-C binary oracle ceilings are UN=G(min(K,h))/G(min(K,m)) and UR=min(K,h)/m. These bound ideal reordering, not attainable model quality or retrieval improvement. Off-C targets remain in m/IDCG; positive empty-C queries have both ceilings zero. Mature zero-Y queries remain in the separately declared all-query-zero cohort, outside conditional Q+.

For UN>0 define e=NDCG/UN. Then ΣNDCG/ΣUN is a ceiling-weighted mean of e, not the unweighted mean among retrieved-positive queries. Zero total ceiling makes that ratio undefined. Neither diagnostic replaces the existing full-Y primary metric.

**One finite MANUAL symbolic toy, UNRUN.** K=2, d=1/log₂3, A=1+d:

|q|full Y|C / ranked order|NDCG, UN|
|---|---|---|---|
|1|{a}|[a,x]|1,1|
|2|{b,c}|[y,b]|d/A,1/A|
|3|{e}|[]|0,0|
|4|∅|[z]|0,0 by all-query convention|

Prediction: conditional ratio-of-means=(1+2d)/(2+d), whereas mean supported e=(1+d)/2; unequal despite identical underlying rankings. Conditional Recall ceiling=(1+1/2+0)/3=1/2 and actual Recall equals it. Query3 must remain in Q+; query4 remains in all-query accounting. No arithmetic/program/data experiment was executed.

**Counterhypothesis/utility.** This distinction may already be sufficiently documented and have no decision value. Potential task1 benefit is preventing candidate-support composition from masquerading as changed ranking efficiency; no quality claim follows. Empirical utility, runtime and implementation cost: **UNKNOWN**.

**Dedup/decision.** The ceiling formula already exists in `refinement-post-heldout-retrieval-priority.md`; target03/evaluation05, candidate06/09/12 and TLAB004/006/007 cover denominators/caps. HYP069/070 UserCF remains deferred; TLAB013/014/015/019 and frozen final stay unchanged. Adopt only a clarified existing diagnostic if independently checked; merge as refinement. Reject a new hypothesis/pilot/gate or any retrieved-positive filtering of the primary cohort. All science/native permissions remain unchanged.
