# FA002 independent source/math helper review

2026-10-15. Scope: frozen FA05/FA06 report and ledger; primary-source browser reads; tiny standard-library timestamp/complex-arithmetic literals only. No real data, SQL, labels, models, weights, predictions, fits, native sessions, paid calls, source downloads or repository edits. No child agents.

**Disposition:** retain FA06 as a design-only proposal. Its source attribution and printed equal-coherence arithmetic pass. Before implementation, clarify the numerical/coverage contract and summary-key bound below. The broad historical nonalias conclusion requires the coordinator's separate baseline audit; this helper did not reread the historical registry.

## Source support and limits — pass

[CycleNet v1, §3.1](https://arxiv.org/html/2409.18479v1#S3.SS1) models a learned recurrent table with a supplied cycle length, aligns/repeats it at sequence positions, removes it before forecasting, and adds it back afterward. Its reported tasks are long-term time-series forecasting. The [arXiv version record](https://arxiv.org/abs/2409.18479) dates v1 to 2024-09-27; the [official proceedings](https://proceedings.neurips.cc/paper_files/paper/2024/hash/bfe7998398779dde03cad7a73b1f81b6-Abstract-Conference.html) confirm NeurIPS 2024.

In the [author code, `RecurrentCycle.__init__/forward` and `Model.forward`](https://github.com/ACAT-SCUT/CycleNet/blob/main/models/CycleNet.py), `self.data` is a trainable zero-initialized table, the gather uses index modulo cycle length, and the forecast subtracts then restores aligned table values. The [browser-readable raw source](https://raw.githubusercontent.com/ACAT-SCUT/CycleNet/refs/heads/main/models/CycleNet.py) agrees. `main` is mutable; inspected 2026-10-15, not executed. No paper/code discrepancy affects the narrowly cited claim.

FA06's fixed harmonic moment is an adaptation, not CycleNet replication. It has no learned recurrent table or residual forecaster. CycleNet supplies conceptual motivation for aligned periodic structure, not evidence for purchase-ranking gains, for a first Fourier moment, or for this chosen 24-hour period. Frozen report lines 11 and 47 correctly keep those limits explicit. A harmonic clock kernel is also distinct from monotone decay with event age.

## Exact literal and invariances — pass

Frozen report lines 37–45 define the following correctly. At 00:00 UTC the phasor is 1; at 18:00 it is −i. Thus `U1=I=(2−i)/3` and `U2=(1−2i)/3`. Both squared magnitudes are 5/9, so both coherence products are 5/9. Alignment is `Re((2−i)(2+i))/9=5/9` in H1 and `Re((1−2i)(2+i))/9=4/9` in H2. The stdlib literal reproduced these values.

In general, `a=Re(U conjugate(I))` equals the mean cosine of all user-view/item-purchase phase differences, and `r=|U||I|`. Therefore `−r≤a≤r≤1`. A shared origin shift multiplies both moments by the same unit phasor and cancels; independently rotating users/items does not. Tiny literal origin shifts 0, 12345, 43200 and 86399 seconds agreed within floating-point error. This is an origin change with the event membership fixed, not a claim that changing the physical query anchor leaves membership unchanged.

The older event moves within one UTC day, far from the last 24-hour boundary, and stays in the 168-hour window. Earliest/latest events, distinct products and unweighted counts remain fixed; item purchases are untouched. This supports nonalias to the stated count/distinct/first/latest-recency/ratio family and anchor-calendar values. It does not preserve arbitrary event-clock histograms or an existing temporal decay: for example a 24-hour half-life sum changes from 0.8877714153 to 0.9090774412. The coordinator separately reported that pinned W contains no learned decay/hour histogram. That is separate baseline evidence, not this helper's independent verification. Do not generalize the printed witness to every conceivable calendar/decay basis.

## Required implementation clarifications

1. **Numerical zero and bounds (refine before a source gate).** Positive support with zero mathematical resultant is a valid zero, not missing. However equally weighted opposite phases produced an approximately `−1.6e−16 i` residual in the tiny float calculation. Specify accumulation/output dtype and fixed comparison tolerances for cancellation, rotation invariance and `|a|≤r≤1`; never test floating sums for exact zero or make their tiny residual a missingness decision. Float32 accumulated over many events needs particular care. The diversity admission gate also needs this fixed numerical comparator so rounding noise alone cannot count as distinct alignment. A fixed numerical convention is not a searched feature threshold.

2. **Coverage and denominator integrity (refine before a source gate).** Missing is exactly `Nu=0 or Ni=0` after complete source coverage; an absent/truncated state is not a known-empty entity. Count retained raw multiplicity and require the raw-window counts to equal W's `user_view7d` and R2's all-user `item_purchase7d`. A mismatch, nonfinite state or cap exhaustion must abort rather than emit zero/NULL. The shared flag and two NULLs are coherent once that integrity condition holds. User views must include off-C products and purchases must include all users.

3. **Absolute hours and expiry (clarify, mathematical method passes).** The sparse key must include entity type, entity id and the absolute UTC hour, not only hour-of-day. Store count plus sine/cosine sums computed from each actual timestamp. A midnight `[t−168h,t)` window selects exactly the 168 completed absolute hours: retain the exact lower edge, exclude the exact upper edge/global peer bucket, and expire hours leaving the window. Do not replace raw timestamps by hour centers. Tiny literals with seconds within hours, both edges, a future suffix, repeated timestamps and later midnight anchors matched direct raw-event sums within tolerance. A bin-center calculation differed. Arbitrary anchors still need the newly declared partial-hour contract identified by the author.

4. **22,100 summaries (clarify grain, cap can be valid).** Across 100 query anchors/22,000 candidate rows, there are at most 100 demanded `(user,anchor)` moments and 22,000 demanded `(item,anchor)` moments. That supports 22,100 demanded summaries, even if entities change across days. Materializing every distinct item at every anchor could instead reach 2.2M item summaries. Restrict materialization to demanded entity/anchor pairs or reuse resident summaries while processing anchors. The 1M absolute-hour-key cap and 4GiB/30 CPU-minute limits are stop ceilings, not guaranteed sufficient capacity. The proposal correctly charges actual examined physical rows even if pruning fails and does not infer scan cost from state size.

## Matched control and apparent FA05 issues

FA06's `W+r+m` versus `W+a+r+m` comparison correctly isolates the new alignment scalar in a shared amplitude/missingness basis. A different number of columns is intentional here. Both fits must remain on identical Q/C/fullY/weights/settings/checkpoint and also be compared against frozen W; a fixed outcome-blind per-item phase scramble preserves r/support and must consume declared diagnostic work. Do not rotate by timestamp-dependent hash if the intended control is a single preserved item moment.

FA05's printed fixed-C cart swap is mathematically sound: user/category totals and item totals are preserved, while focal i's same-category rival max changes 1→0. Tied maxima require product identity/self-exclusion; with two equal maxima the remaining rival still contributes that maximum, while a singleton group emits 0. Tiny literals confirmed these cases. Category permutation within a group cannot serve as the proposed placebo. No additional FA05 blocker was established here. Its pooled control remains a historical event-attached-category statistic, whose known-subset/missing semantics must stay explicit when compared to current-category rival groups; do not silently backfill historical categories.

## Preservation and checks

At review start, both author files and both frozen copies matched the manifest:

- Report: 12141 bytes; SHA-256 `852c7b2f52a25f47777b9613a8daf21803f56d07e99f9bf718d3ad1c20d808f3`.
- Ledger: 13058 bytes; SHA-256 `e71c138b85012d78725103960b7c2290567b17bc0d37e4ca2d111f6fd3ad72c5`.

The final preservation check is recorded below. Only this `/tmp` review note was written by this helper. Literal checks test analytical contracts, not implementation, scientific power or empirical ranking quality.

- Final author preservation: `brainstorm-fa002.md` — manifest byte length and SHA-256 MATCH.
- Final snapshot preservation: `/var/folders/gb/j1q8qm811b3gjd3gk93fh22h0000gn/T/tlab-fa002-review-snapshot-cc95xipf/tlab-brainstorm-features-a-round-002.md` — manifest byte length and SHA-256 MATCH.
- Final author preservation: `brainstorm-fa002-ledger.json` — manifest byte length and SHA-256 MATCH.
- Final snapshot preservation: `/var/folders/gb/j1q8qm811b3gjd3gk93fh22h0000gn/T/tlab-fa002-review-snapshot-cc95xipf/tlab-brainstorm-features-a-round-002-ledger.json` — manifest byte length and SHA-256 MATCH.
