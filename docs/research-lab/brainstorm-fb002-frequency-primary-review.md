# Independent FB-05 source and literal review

Reviewed the frozen FB-05 section, original lines 7–19, in `preserved-review-inputs/tlab-brainstorm-features-b-round-002.md`. Snapshot SHA-256: `d6fc8db181277765e7de4384e78273c3dc51aaa117428959e9c67f3bff1c8b16`. No source data, SQL, labels, model execution, fits, weights or shared-file edits were used. Only public source text and stdlib arithmetic were inspected/executed.

Disposition: retain as an explicitly local, fit-free roughness feature with a literal gate. No supported paper-attribution defect. Useful support, ranker gain and physical feasibility remain unknown.

## Primary-source match

WEARec v2 is dated 26 November 2025; the author repository identifies the work as AAAI 2026. Its learned mechanism combines adaptive Fourier filtering with Haar decomposition, detail rescaling and reconstruction of item/position embeddings along the sequential item dimension. This supports line 9 and the explicit distinction from the proposed count scalar. [Paper, §§3–4](https://arxiv.org/html/2511.07028v2), [author repository](https://github.com/xhy963319431/WEARec).

In current author `wearec.py`, `wavelet_transform` is single-level: approximation/detail are `0.5*(even ± odd)`; a learned tensor rescales details, then reconstruction interleaves positions. The forward method also applies `rfft/irfft` and mixes both branches. FB-05's second scale, wall-clock bins, squaring and N² normalization are its own adaptation. [Author implementation, `wavelet_transform` and `forward`](https://raw.githubusercontent.com/xhy963319431/WEARec/master/src/model/wearec.py).

The BSARec reproduction v1, 19 December 2025, reports comparable DSP/residual results with overlapping error bands in its sequence-length study and material padding effects. Its own hyperparameters were reused across sequence lengths. It supports a caution about mechanism attribution, not an expected effect for FB-05 or a prescription to mirror/fabricate unavailable history. [Reproduction, §§5–6.4](https://arxiv.org/html/2512.17442v1).

## Refinements before any source pilot

1. **Physical scan accounting, original line 19:** one million *matched* history rows does not cap rows/bytes physically read while obtaining those matches, metadata joins, coverage proofs or repeated anchor replay. A full global-history scan could produce few matches. Require a bounded read plan and charge scanned rows/bytes, sorting/index creation, replay and materialization; include a wall-time limit because CPU limits alone do not bound blocked I/O. This is a feasibility-readiness gap, not evidence that an implementation already exceeded the cap. A 32-bin vector for each of 100,000 keys is 3.2 million counts (25.6 MB in packed uint64); this raw size does not prove total RSS or scan feasibility.

2. **Narrow the nonalias evidence, original line 15:** the printed four-bin pair proves nonalias to its matched totals/support/recencies, but does not explicitly hold the incumbent's decay/trend fixed. The coordinator supplied a stronger independently verified fixture: ages `(6d,4d,2d,1h)` map to bins `(4,13,22,31)`; counts A=`(3,0,2,1)`, B=`(1,3,1,1)`. Both have total 6, 24h count 1, first/last times 6d/1h, and category decay with a 2-day half-life `11/8 + 2^(-1/48)`. Both energy numerators are 14 for A versus 12 for B, yielding `(7/18,7/18)` versus `(1/3,1/3)`. Product assignments A=`{x,y,z};{};{x,y};{x}`, B=`{x};{x,y,z};{y};{x}` also preserve product totals x3/y2/z1 and distinct support. This establishes that particular category-decay nonalias; it does not hold arbitrary fine-window grids or candidate-item-specific decay fixed.

3. **Keep the coefficient semantics explicit, original lines 11–17:** for nonnegative counts and N>0 each E lies in [0,1] and is invariant to multiplying every count by the same positive factor. Under orthonormal Haar normalization, actual level-one and level-two coefficient energies divided by N² are E1/2 and E2/4. Thus the proposed E values are normalized contrasts, not percentages of total signal energy. “Haar-like” and “roughness” already avoid an unsupported periodicity claim.

4. **Equalize source masks, original lines 13,17:** the count-contrast arm needs the same complete-source and N>0 eligibility mask. A complete empty interval is observed silence, whereas an incomplete source interval is unavailable history; both proposed energies may be missing but their support reasons remain distinct. Freeze candidate-category NULL/unknown handling and historical as-of category semantics. Different candidate metadata coverage must not silently become zero activity.

5. **Require exact anchor-relative edges, original lines 11,19:** use bins j=0…31 with width 18,900 seconds and half-open intervals, equivalently `j=floor((event_time-(t-604800))/18900)` for included events. A coarse calendar bin count cannot generally re-bin arbitrary anchors exactly. All same-second peers and candidate metadata must respect the stated `<t` rule. Relative-time translation is invariant; shifting bin phase alone is deliberately a different representation, already acknowledged in the draft.

## Executed literal evidence and limits

`brainstorm-fb002-frequency-literal.json` records stdlib `Fraction` assertions. The draft example gives E1=5/18 versus 1/18 and E2=0 in both cases. A flat histogram has both energies 0. A single event has both energies 1 regardless of its bin, showing a strong sparse-support effect. Uniform duplication preserves both energies; concentrated duplicate logging can change them.

A one-second boundary can move one of two events from a neighboring bin and change `(E1,E2)` from `(0,1)` to `(1/2,0)` without changing the total. This confirms the prespecified phase/jitter diagnostic is necessary; it does not invalidate a deliberately phase-specific feature. The 2-day-decay fixture above also passed. No runtime throughput, real coverage or quality inference was made. Only the supplied frozen version was reviewed; the parent coordinator owns original-file freshness verification.
