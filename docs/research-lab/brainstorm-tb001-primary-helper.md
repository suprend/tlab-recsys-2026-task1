# TB-B002 / TB-B003 primary-source audit by A

15 October 2026. Read-only research helper; no implementation or pilot. Reviewed the frozen draft and ledger, c-STG arXiv v2 (7 June 2024), WRI arXiv v1, and relevant author code through browser pages. Author-code links resolve to `main` as observed today, not a pinned release. No source data, labels, database, model artifacts, fits, downloads, installs, native APIs or jobs were accessed. Only small-document SHA256 checks and stdlib arithmetic on declared literals were executed. No children were spawned.

Input fingerprints match the parent's freeze:

- Draft SHA256: `3bc0ba8345b83f53f42c950824602c3b8b7b18fd29afed3b772827ea7eb555a5`.
- Ledger SHA256: `f266c5dac95f6cf52108e14edd8629252155252829b431af7501fcecf6a883ba`.

## Recommendation

| Candidate | Decision now | Required correction before any prospective pilot |
|---|---|---|
| TB-B002 | **refine**; defer empirical admission | Distinguish continuous attenuation from binary feature abstention; freeze the actual gate, regularizer, direct-context path, ranking surrogate and negative weights. |
| TB-B003 | **refine**; conditionally accept-needs-pilot after correction | Use one explicitly defined conditional query population for both gains and context masses; require positive-query support; narrow the claim to common-mixture mean stability and expose conditional cancellation. |

Neither receives measured REES46 support, a current execution grant, or a causal/transfer theorem. Canonical novelty/duplicate status was not independently adjudicated because this helper was restricted to these two draft entries and their primary sources.

## TB-B002: what the sources actually specify

c-STG begins with independent conditional Bernoulli inclusion variables. Its implemented mathematical relaxation learns **μ(z)**, trains `s=clip(μ(z)+ε,0,1)` with fixed Gaussian `ε~N(0,σ²)`, and penalizes expected nonzero gates by `λ Σj Φ(μj(z)/σ)`. The paper says noise is needed only in training. Its dense and population-selector benchmarks include explanatory features concatenated with context. Weighted c-STG additionally produces contextual feature coefficients; that is a separate extension. [Paper §§3.1, 3.3, 4](https://arxiv.org/html/2312.14254v2), [ICML publication record](https://proceedings.mlr.press/v235/sristi24a.html).

The author sigmoid selector explicitly multiplies noise by `self.training`, then clamps to `[0,1]`; evaluation therefore gives **clip(μ(z),0,1)**, without a binary threshold. Its hypernetwork ends in Sigmoid, so finite, unsaturated outputs ordinarily remain strictly positive. The same file's regularizer uses `erf((x/σ)*sqrt(2))`. This disagrees with the CDF required by the paper, `erf(x/(σ*sqrt(2)))`. These are observations of this file, not a claim that every author experiment uses it. [Author selector, lines 38, 60–69](https://github.com/Mishne-Lab/Conditional-STG/blob/main/models/fc_stg_layered_parametric_modular_sigmoid.py#L38).

There are further reasons not to treat the repository as a drop-in implementation. The non-sigmoid modular file references `z` after its assignment is commented out, and uses a shifted clamp. [Alternate author selector](https://github.com/Mishne-Lab/Conditional-STG/blob/main/models/fc_stg_layered_parametric_modular.py#L45). The XOR2 script also uses the first CDF expression, passes μ directly into it, and averages the regularizer over features and examples, whereas the paper displays a feature sum. [Author XOR2 script](https://github.com/Mishne-Lab/Conditional-STG/blob/main/main_XOR2.py).

### Concrete corrections and cheap falsifiers

1. Replace “learn π and emit the deterministic frozen gate” with the actual chosen μ-based training and inference equations. At μ=.25, inference returns .25, not an inclusion bit and not `P(s>0)`. Binary rejection needs a prospectively frozen threshold or another hard-gating construction; both are explicit adaptations requiring evaluation. A feature gate is also not query-level confidence abstention.
2. Do not promise local sparsity from the unmodified sigmoid selector. On a literal input of value 1 with μ=.25, its evaluation contribution is .25. This is the cheapest no-fit falsifier of a claimed hard local exclusion. Structural validity must remain an external rule, independent of learned attenuation.
3. Resolve the regularizer seam before a pilot. Stdlib literal evaluation at σ=.5 yields:

   | μ | Paper CDF Φ(μ/σ) | Displayed sigmoid-code expression |
   |---|---:|---:|
   | 0 | .500000000000 | .500000000000 |
   | .25 | .691462461274 | .841344746069 |
   | .5 | .841344746069 | .977249868052 |

   A paper-faithful implementation should use the first column and state whether λ multiplies a feature sum or mean. This arithmetic was executed without any learned parameters or model package.
4. Keep the dense `f,z` control. Give all compared neural predictors the same declared direct-context channel if the purpose is to isolate gating. The author sigmoid model only concatenates context in its `elif` branch when gates are disabled; copying it literally therefore changes more than feature selection. [Author forward path](https://github.com/Mishne-Lab/Conditional-STG/blob/main/models/fc_stg_layered_parametric_modular_sigmoid.py#L119). A source-free architecture adversary is `x≡0, y=z`: a predictor receiving only gated x cannot recover z, while a dense predictor receiving z can. This diagnoses the control's information path, not performance on the recommendation task.
5. The draft's balanced-bit switching example is correct and already refutes an expressivity advantage over a dense tree with the same inputs. Novelty, if retained, is a practical conditional-sparsification admission rule at fixed cost, not a new expressive function class or new knowledge about unavailable data.
6. Freeze a trainable ranking surrogate **L**, query/candidate normalization, treatment of nonpurchase candidates, positive/negative weights, zero-positive training-query behavior and negative sampling before fitting. The primary method supplies a generic supervised loss, not a recommendation sampling rule. Without exposure data, nonpurchase rows support only a declared offline surrogate. Different negative weights can change learned gates; all controls must share the objective and row policy. In particular, averaging candidate rows gives larger candidate sets more total influence unless normalized per query.

**Finite future ceiling:** retain the draft's four fits, four development looks, ≤2,000 Q/split, ≤220 C/Q, ≤4,096 gate parameters and inclusive ≤60 CPU minutes only after naming exact neural widths, epoch/step caps, boosting rounds, seed, λ, σ, regularizer normalization and direct-context path. Count feature extraction, optimization, failures and inference. Exceeding the cap yields an incomplete/negative pilot, not a tuning extension. No current fits are authorized. A binary-threshold variant would replace a declared arm, not silently add a fifth fit/look.

## TB-B003: correct mathematics, missing estimand boundary

WRI uses weights satisfying `α(xinv)p1(xinv)=β(xinv)p2(xinv)`. Density weights `α=p2, β=p1` give a common pseudo-distribution proportional to `p1 p2`; the corresponding risks are initially unnormalized. Its theorem needs the causal coupling assumption, linear regression with squared loss, more environments than spurious dimensions, and general position. Density-ratio general position is proved; the paper conjectures the extension for other weighting choices. Practical WRI learns representations and densities by alternating optimization, adds ERM, a squared risk discrepancy and a negative-log density term; convergence is not guaranteed. [WRI §§2.2, 3.1–3.4](https://arxiv.org/html/2407.18428v1).

The author implementation multiplies per-example cross-entropy by the other environment's density, and scales the squared discrepancy using running average densities and loss. It is not the proposed post-score bin-standardized NDCG operator. [Author WRI implementation](https://github.com/ginawong/weighted_risk_invariance/blob/main/multidim_simulation/algorithms.py). Calling the proposal an **adaptation** is correct; no density learner, representation learner or WRI theorem is inherited by the proposed arithmetic.

### Population and normalization corrections

Define `Ue` as the exact primary evaluation population: prospectively fixed eligible queries whose outcome windows are mature and whose **fullY is nonempty**. Then define both terms on that population:

`pe(z) = P(Z=z | query∈Ue)`

`δe(z) = E[NDCG(B+f)−NDCG(B) | Z=z, query∈Ue]`

For fixed, predeclared bins, let `τ=Σz p1(z)p2(z)>0`, `q(z)=p1(z)p2(z)/τ`, and `Ge=Σz q(z)δe(z)`. Equivalently, `Ge=E_Ue[pother(Z) Δ]/τ`. The unnormalized cross-density total is `τ Ge`; reporting it as a mean can conceal a small τ. The draft's `Σmin(p1,p2)` overlap coefficient is distinct from τ and from the effective sample size.

Context Z must remain pre-T. Conditioning an evaluation estimand on mature nonempty fullY does not make Z label-derived. It does mean the claim concerns this buyer-query population. If the proposal instead assigns zero NDCG to empty-fullY queries, it must explicitly switch **both** p and δ to that all-query-zero estimand. Mixing all-query p with positive-query δ has no stated population interpretation and can manufacture a composition effect.

The minimum support must be **20 mature, nonempty-fullY queries per retained bin per environment**, not 20 total Q. A bin can contain thousands of total queries and zero valid conditional outcomes. Its δ is undefined; it must not be imputed as zero. Freeze support filtering and renormalization rules in advance and return unknown when the primary support criterion fails. Repeated user/session queries also do not create 20 independent statistical units automatically; the criterion remains descriptive unless uncertainty accounts for dependence.

The coordinator supplied sparse summaries (619 fullY-positive queries among about 26k Q; 96 selectionY-positive queries). These were not inspected or independently verified here. A selection pool with 96 positives cannot furnish eight bins ×20 positive queries even before separating two environments. The proposed eight-bin budget is a maximum, not evidence of feasibility or an excuse to relax support after observing gains.

### Literal checks and novelty limits

- The draft arithmetic is correct: `p1=(.9,.1), p2=(.1,.9)` gives τ=.18, overlap=.2 and q=(.5,.5). With equal conditional gains `(.2,.05)`, raw gains are .185/.065 and both normalized common gains are .125. These values were executed with literals only.
- **Stronger cheapest falsifier:** let q=(.5,.5), `δ1=(.2,−.1)` and `δ2=(−.1,.2)`. Both common gains are **+.05**, and their discrepancy is zero, yet each context changes sign across environments. Therefore the proposed scalar gate can support only common-mixture **mean** stability. It cannot certify conditional usefulness stability. If that stronger claim is intended, predeclare binwise sign/discrepancy checks and their uncertainty; keep them within the same fixed looks.
- The existing zero-gain and disjoint-support probes remain necessary. τ=0 means undefined q/unknown, never zero-risk or positive admission.
- Freeze exact bins, not merely “≤8 bins.” Splitting one of two equally probable bins into two equal sub-bins changes its aggregate product-mixture mass from 1/2 to 1/3. This is an original arithmetic consequence of the chosen q, so post-outcome bin refinement changes the target population.
- A useful additional control is a binwise conditional-gain report on the same artifacts and looks. Otherwise any gain over pooled/unweighted admission may come from choosing a favorable mixture while hiding local harm. The novel operator remains descriptive standardization plus explicit abstention; it does not discover invariant features or validate external-dataset transfer.

**Finite future ceiling:** the formula audit costs zero fits and can use these declared vectors. A later empirical pilot may retain two environments ×≤2,000 Q, ≤8 frozen bins, one bounded post-score pass and ≤60 CPU seconds, plus an inclusive ≤60 CPU-minute source/fit/inference reservation. Two fits suffice only for **one fixed B/B+f pair shared by both evaluation environments** and trained before their cutoffs; independently fitting a pair per environment costs four fits. The draft's 880,000 saved rows must mean paired candidate records with two score columns: `2×2,000×220=880,000` records, or **1,760,000 scalar model scores**. Fix that schema and count inference in the inclusive cap. The controls reuse the same artifacts and outcome looks; no extra fitting is implicit.

## Verification boundary

The report contains source/code inspection and literal mathematics, not execution of either repository. The CDF discrepancy and the alternate selector's undefined local variable are static source observations; no claim is made that a particular published checkpoint or experiment used those paths. The temporary author draft and ledger were not edited. Any amended proposal must be reviewed again against its actual final equations, population and costs.
