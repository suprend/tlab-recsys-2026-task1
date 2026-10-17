# Objective canary — source-only proposal v1

This optional prototype belongs to the existing TLAB-008/HYP035/loss-selection03/wave028/059 contrast. It creates no new hypothesis, required gate, task, budget or execution authority. The independent C FIRST remains unchanged.

`canary.py` has not been executed, syntax-compiled, imported or tested. Source inspection and file hashes are the only readiness evidence. Root may choose one future run after separate source review and queue selection.

## Declared mathematical domain

- One fixed observed context X and fixed distinct candidate list C=(a,b,c); candidate identities can differ within X, but X is identical across future outcomes. This is a literal list, not output from the project retriever.
- Binary full-future-purchase sets are already mature in the hypothetical population. Basket mixture: Y={a} with probability 9/20 and Y={b,c} with probability 11/20. Singleton control: Y={a} with probability 9/20 and Y={b} with probability 11/20.
- Every target is in C, so m=|Y|=h=|Y∩C|. Both sets are nonempty and have at least one positive and one negative. No undefined zero-IDCG or zero-pair case is silently handled.
- K=20 exceeds |C|=3: ordinary binary NDCG@20 is the entire three-item list, with zero contribution after its end. Discount is 1/log2(rank+1); full-Y IDCG uses min(K,|Y|), independent of the predicted permutation.
- BCE coefficients are marginal purchase probabilities, the Bayes minimizers for unrestricted per-item BCE scores at this fixed X. Equal 1/|C| query normalization does not change them. No classifier is trained.
- PairLogit risk is sum over positive×negative pairs of `weight*softplus(s_negative-s_positive)`, with each outcome's pair weights summing to one. Expected directed coefficients are calculated from the two outcomes before scoring. There is no negative sampling.
- Only for the basket mixture, symmetry permits s_b=s_c=0. The script derives win/lose masses from the pair coefficients and computes d*=log(win/lose). It also evaluates the full expected pair risk from the directed-pair table at d*, zero and -d*. A common shift is irrelevant. The singleton control does not impose b=c; its never-positive c can have an unbounded negative optimum, so no finite full optimum is claimed there.

For positive win and lose masses, the declared one-dimensional risk has derivative `-win/(1+exp(d)) + lose/(1+exp(-d))` and strictly positive second derivative. Its unique minimum is therefore at `log(win/lose)`; comparison with two sampled alternatives alone would not prove a global minimum. This argument is analytical, not a performed numerical test.

The script independently enumerates all six permutations and evaluates each from the original expected binary NDCG formula. It separately reports normalized-gain coefficients, BCE marginal coefficients, directed pair coefficients, m/h and coverage ratios. It outputs numbers and options, with no hard-coded passing verdict or acceptance boolean.

## Prospective interpretation

Source-level prediction, unexecuted: the basket mixture's NDCG coefficient for a is 9/20, while those for b/c are (11/20)/(1+1/log2(3)); BCE prefers b/c, and symmetric PairLogit has d*<0. The coverage multiplier equals one in both outcomes. In the singleton control IDCG is one, so normalized-gain and BCE coefficients agree. These are narrow algebraic claims; they do not establish current CatBoost behavior, finite-sample learnability, a REES46 effect, exposure correction or real quality gain.

For a future review, accept the witness only if independent arithmetic reproduces the six NDCG values, relevant orderings, pair-risk minimum within the declared symmetric family and singleton control. Any incompatible formula or normalization rejects this witness until corrected. No runtime result is claimed now.

## One possible future Root run

Proposed inclusive envelope: one standard-library Python process, at most 5 CPU seconds / 8 wall seconds / 128 MiB RSS / 64 KiB captured stdout+stderr, including startup and failure. This script contains no process/resource controller; Root must impose that envelope externally, or decline the run. Its literal finite report is expected to fit well below the output ceiling, but that estimate has not been measured.

If separately authorized, an existing standard-library Python interpreter may execute the absolute `canary.py` path once, with isolated mode and bytecode writing disabled. No project environment, package installation, external input, data file, project import, native library, fit, network, Git action or repository write is needed. The script only prints its JSON report. Do not interpret this README as authorization to execute it or as a reason to delay primary Task1 work.
