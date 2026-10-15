# Independent cross-review of learner/loss B by A

15 October2026. Reviewed the frozen MB report/ledger, canonical M001 and frozen MA draft. Primary papers and current author code were read through the browser; no project source relations, data, Y, model artifacts, heldout, dependency install/download, fitting or native model API was accessed. Author files were preserved. One tiny **stdlib-only scalar algebra** check used the existing `.venv/bin/python`; its literal evidence is `brainstorm-mb001-review-literal.json`. This is not a native model compatibility/gradient test. No new HYP IDs or execution authority are assigned.

|Candidate|Decision|Novelty disposition|Next cheapest step|
|---|---|---|---|
|MB01 PSL-tanh|**Refine, then needs-pilot**|Distinct loss-shape mechanism within existing pair/list family|Freeze paper-versus-code denominator, stable formula and bounded-score/gradient witnesses|
|MB02 TabM|**Reject as a new candidate; merge**|Exact duplicate M001-C3/MA01|One combined parameter/diversity/resource gate, no parallel duplicate budget|
|MB03 separated deployment head|**Refine; defer until support/chronology gate**|New narrow routing contrast within M001-C1 KD family; different from MA04 closure|Literal derivative-routing check plus teacher/student support allocation|
|MB04 joint item codes|**Defer**|Genuinely distinct joint tokenizer/decoder mechanism|Code-lineage/collision/negative-law and CPU plan before any encoder fit|

## MB01: real gradient-shape difference, but specify the actual objective

The [PSL paper, Eqs4.1–4.3/Lemma4.1](https://arxiv.org/html/2411.00163v1) supports activation replacement and explicitly limits its bounding argument to gaps in[-1,1]. Its theoretical catalog loss and the current [author optimizer](https://github.com/Tiny-Snow/IR-Benchmark/blob/main/src/itemrec/optimizer/optim_PSL.py) are not identical recipes: code constructs sampled negative gaps, uses cosine/score-temperature `tau`, then logsumexp of `log(1+tanh(d))/tau_star`. It does not add a self-positive1term. MB's full `Nq∪{p}` denominator is therefore an explicit adaptation, not a direct code replay. `.2` maps to robust-temperature `tau_star`; `.5*tanh(f)` replaces the author's score scaling. Pin a release/commit before later implementation; mutable main is evidence only.

**My algebra:** set `a(d)=1+tanh(d)` and `A=Σa(dj)^(1/τ)`. For a genuine negative j,

`∂L/∂dj = [a(dj)^(1/τ)/A] × (1−tanh(dj))/τ`.

Equivalently `log a(d)=d−log cosh(d)`. The additional varying derivative factor distinguishes it from changing a constant softmax temperature. Ordinary pairlogistic has no cross-negative logsumexp coupling; one negative plus self reduces exponential-softmax exactly to temperature-scaled pairlogistic, while PSL remains different away fromd=0. This is smooth pair-gap reshaping, not ordinary hard gradient clipping. A same-τ exponential control establishes that narrow difference; it does not prove PSL beats tuned temperatures, pairlogistic or matched clipping. Avoid the broader claim unless those controls receive separately paid attempts.

The literal five-gap finite-difference check passed with maximum error1.79e−10. For one negative+self,τ=.2,d=1: PSL gradient≈1.12567 versus exponential/pairlogistic≈4.96654; atd=0 both2.5. These are hand-selected scalar values, not REES46 evidence.

**Masks/negative law.** Enumerating all `Nq=Cq\Yq` is exact on declared C; no sampler/logQ is involved. Including self contributes1but has **zero score derivative**, since `sp−sp=0`. Other positives are excluded symmetrically for each p: singletonP agrees with the usual fullC exponential denominator, multipleP changes it. This avoids positive-positive competition but forfeits any automatic catalog-rank bound. Average perP then perinformativeQ; neither rawpositive count nor candidate count may silently reweight queries. WithNempty, losslog1=0; withPempty, no term. Both remain in evaluation. “Unpurchased in24h” is the observed label, not evidence of dislike/false-negative noise.

**Raw-margin caveat.** Raw `f(X)` is unbounded; only the emittedscore is in(-.5,.5), so gaps are in(-1,1). Both arms share this bound, but chain derivative `.5sech²(f)` can vanish. Translation invariance holds in emittedscore space; adding a constant before tanh generally changes gaps. A fixture should catch this distinction and stable `log a=d−logcosh(d)` transport. First future controls: same bounded MLP/normalization/exact negatives, plus strongB replay. FreshB fit is justified only when the declared training domain changes; otherwise reuse the sealedB and pay scoring. Any added PairLogit/clipping arm consumes a prospectively revised attempt slot, never a free control.

## MB02: merge all three independent rediscoveries

[TabM](https://arxiv.org/html/2410.24210v2) and the [official implementation](https://github.com/yandex-research/tabm) support shared matrices, member adapters, independently supervised heads and collective prediction. M001-C3, MA01 and MB02 propose precisely that on B41; k4versusk8 is a parameter choice, not new novelty. Keep one ledger record and one future comparison.

Same-width MLP does not match TabM's parameters or work. Equal epochs match example passes, not CPU budget; a common total cap alone does not allocate equal per-arm ceilings. Choose the scientific policy explicitly, then report updates/CPU/parameter counts. MA01's wideMLP and tied-adapter controls can strengthen the merged question, but count every fit. Tying only adapters does not eliminate diversity if heads remain independently initialized; a full identical-member null must tie every asymmetry. Missing masks/imputation must be identical in neural arms and disclosed as preprocessing versus CatBoost's native missing handling.

The `.812GiB` matrix arithmetic is correct for numeric values only; IDs, keys, masks, copies, quantization/optimizer/activations are extra. Never copy eight full input matrices. Dummy-label forward/backward is a paid synthetic/resource probe,0optimizer fits, not uncharged work. A two-epoch loss reduction or disagreement does not establish scarce-label generalization; failed single tiny configuration means this adaptation failed, not all TabM possibilities.

## MB03: useful new routing question, not complete bias isolation

The [Khani et al. source](https://arxiv.org/html/2408.14678v1) indeed separates hard/soft task logits and evaluates auxiliary versus direct distillation in proprietary multiobjective video systems. It does not provide a purchase-specific bias-removal theorem or an open fully reproducible REES46 implementation. MB accurately treats its source transfer as an adaptation.

M001-C1 manipulates teacher-prefix timing; MA04 manipulates student/teacher subset closure. MB03 instead manipulates where the **same** soft target enters the student. That is a distinct within-KD contrast worth retaining, without another generic “distillation helps” HYP. It also differs from HYP065's observed any-event target.

For `L=BCE(y,σ(wh·hθ))+λBCE(pt,σ(wt·hθ))`, teacher loss has zero direct derivative onwhbut generally nonzero derivative onθandwt. Consequently the deployed head remains affected through the trunk. The proposed two-head shifted-teacher fixture is the right cheap test; call the treatment separated logits, not complete teacher-bias isolation. Fix common query weights, λand teacher-score masks/coverage, same purchase updates and deployedhead/trunk capacity. The extra teacher head is part of the architecture; document its parameters or give the direct arm a dummy unused head to equalize declared size. A constant/shuffled teacher control would test whether any auxiliary pressure helps, but it needs a paid slot and is unnecessary for the narrow routing comparison.

The earlier-teacher/postavailability student rows are a legitimate deliberate protocol. All three students must share that later interval; positive teacher labels and negative labels must mature at the prefix cutoff. Teacher availability is a real timestamp, not its fit cutoff. Teacher-generated scores require only already-available X, but their target-purchase masks still obey24h maturity. All students finish before evaluation. A full-period strongB then has more training labels than the later student subset: acceptable as the external strong package reference, not as a matched-data causal comparison. Reject before fitting if an honest split leaves negligible purchase support. Five attempts are correctly visible, but five is a proposal requiring its own cap, not permission from this review. If only compression motivates it, first establish a B inference bottleneck.

## MB04: collaborative codes are possible; lifecycle and negative law remain unresolved

The [ETEGRec paper](https://arxiv.org/html/2409.05546v3) explicitly permits collaborative embeddings and reports SASRec initialization, residual quantization, code suffixes and alternating alignment. Missing text therefore does not block the source mechanism. Its next-item,5-core,per-user split evidence is materially different from our globally timed daily purchase sets. The [repository](https://github.com/RUCAIBox/ETEGRec) expects CUDA dependencies and supplied pretrained artifacts; these are neither free inputs nor a CPU completion guarantee.

The [trainer code](https://github.com/RUCAIBox/ETEGRec/blob/main/trainer.py) materially clarifies the proposal: it minimizes positive symmetric KL, regenerates item codes/collision suffixes and raises when a collision group exceeds `code_num`. Its contrastive branch deduplicates targetitemIDs, then uses in-batch cross-entropy. The rendered paper Eq15 appears with a leading minus on symmetricKL; copying that sign into minimization would maximize divergence. Use verified code/positiveKL semantics, not the rendered sign. Current code was read, not executed.

Joint token assignment is genuinely different from existing pooled/sequence/ALS scores. Still, “five jobs” hides potentially many optimizer stages: declare finite encoder/tokenizer epochs, alternation count, updates per component, full code regeneration and collision rebuild costs. Fixed versus joint decoder must have equal history/targets/initialization and a stated update-or-CPU matching policy; joint extra alignment changes objective as well as tokenizer state.

The paper's in-batch negatives cannot be imported silently for multi-positive dailysets. Define query/user/day sampling; mask sameitem repeats and every co-positive of the chosen query; say whether identical-user contexts in another batch row are negatives. Deduplication changes that law. Fix full token vocabulary normalization versus candidate-constrained normalization; equal-length code likelihood is valid fixedC scoring, but not purchase probability. A future item without a frozen code remains unavailable, not an oracle-inserted target. Twenty complete timestampbuckets may contain unbounded rawitems: specify peer-symmetric aggregation and account for retained raw work, rather than silently truncating equal-second events byID.

Cheapest falsifier: hand-trie with two colliding items,257items sharing a256-symbol suffix vocabulary, OOV item, a tokenizer code swap between stages, and an equal-second peer permutation. Require a jointly frozen vocabulary/code-map/decoder identity and correct positiveKL direction. Defer all encoder/pretraining fits until this design and measured CPU-only admission are accepted.

## Shared closeout

BSL singleton positive aggregation is exactly `−τ+log exp(sp/τ+)=−sp`; with multiple positives its derivative weights already-high scores more. This justifies deferring that positive-side mechanism, not declaring the entire BSL family identical: its remaining negative aggregation/temperature still exists, largely overlapping existing softmax axes.

For every retained candidate: no current heldout/currentW changes; use a newly reserved outcome population, one fixed checkpoint, paid preparation/inference/failures and strongB. A one-seed development win remains screening. All read papers support mechanisms and assumptions, never promised REES46 improvement. Recommended consolidation: mergeTabM; prioritize one PSL or existingSL@20 objective question after literal design; keep separated-headKD as a deferred family contrast; jointcodes stay deferred.
