# Wave065 author B — matched-capacity transport

**Disposition:** zero new mechanisms; refinement of TLAB-013/014/016/019, round 005 and waves 037–038. UNRUN/ungranted; no mandatory CV gate.

**Hypothesis.** Frozen R2/L05 provides a positive matched-capacity effect; per-arm prefix search contributes a separately measurable selection term. On future selection block A, lock kB=argmax B(k), kW=argmax W(k), with the existing earliest/tolerance rule. For any evaluation block X:

Δmatched(X)=M(W,kB,X)−M(B,kB,X);
L(X)=M(W,kW,X)−M(W,kB,X);
Δadaptive(X)=Δmatched(X)+L(X).

The decomposition is exact; L(A)≥−1e−12 is selection arithmetic, not evidence of usefulness. Prediction: feature usefulness yields positive Δmatched on fresh audit B even if L shrinks. Prefix-noise rival predicts an apparent A advantage concentrated in L, then L≤0/rank reversal on B. Temporal drift can also reverse ranks: one audit cannot uniquely identify noise.

**Nearest future experiment.** Predeclare B41, R2, hyperparameters/one seed, primary Δmatched and fixed-300/adaptive secondary contrasts. Exactly two new fits to ceiling 1200, at most 6000 label-independently sampled training Q/1320000 candidate rows each; 2400 dependent prefix metric looks on A. Training labels mature before A anchors; mature A labels and freeze k before B anchors. B permits at most five model-prefix metric looks: B300/W300/BkB/WkB/WkW. No B-driven choice, refits, ceiling expansion or replacement attempts. Within each block, arms share Q/C/full Y, weights and temporal feature policy; retain off-C/empty-C positives. Report all contrasts, rank reversals and support; tiny support can remain inconclusive. This tests the declared smaller training population, not the original 26000-Q procedure.

Proposed all-in ceiling: 3600 tree-CPU-s/3600 wall/8 GiB, including source, complete fits, every look, oracle, startup/cleanup and failures; adequacy unknown. Current SELF-only guards require reviewed whole-tree containment first. Failed attempts consume caps; no free retry.

**Unavailable now:** no genuinely fresh development reservation exists; November fragments were inspected, reused 73 positive Q are dependent screening, and 25–31 stay closed. Both models already trained 1200; 1189/403 selection establishes no savings or independent superiority. Final CI crosses zero. Task1 benefit: distinguish a fixed program's transported contribution from capacity-selection lift without claiming search-policy superiority. Original deadline and 09:45 UTC grid unchanged; no publication delay or grant.
