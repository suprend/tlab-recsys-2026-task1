# FB-07 independent source/accounting check

Reviewed the frozen FB002 report lines 35–43 and its ledger, read-only, on 15 October 2026. Recommendation: retain the deferred acquisition idea; no supported arithmetic defect in the stated **16 opportunity slots**, provided logical exposure and physical computation are recorded separately. This is a proposal review, not execution approval.

## Primary-source facts

The original method uses a variational **Bayesian neural network**, not exact Bayesian linear regression. Its encoding concatenates `text-embedding-3-small` with a binary used-column vector. Utility is downstream learner refit/re-evaluation. UCB uses predicted mean plus scaled standard deviation. Optional pairwise feedback considers the top two UCB candidates; interval overlap and an uncertainty/cost condition trigger querying, and a probit likelihood incorporates the response. The confidence argument assumes a linear representation and standardized sub-Gaussian error; it does not establish calibration for arbitrary local AST descriptors. These facts support the report’s mechanism summary and its separation of adaptation from source. [Paper v1, 28 January 2026, §§3.1–3.3](https://arxiv.org/html/2601.21060v1).

ICLR 2026 publication is confirmed by the first author. [Author publication page](https://xfleezy.github.io/zhuoyanli/). No official implementation was found within bounded paper/author-page/exact-title searches. The paper specifies the OpenAI embedding model; API protocol, actual call count, cache behavior and refit implementation were not verified from author code. Treat “embedding API” as an operational inference, not inspected implementation evidence.

## Own accounting analysis

For UCB and random, each arm receives six initial scores and two acquisition opportunities. Thus `2 × (6 + 2) = 16` is correct as the sum of policy-level opportunities/information exposures. With six physically shared initial probes, there are at most `6 + 2 + 2 = 10` distinct physical candidate-proxy evaluations before failures/retries; overlap between the arms can reduce this number. A baseline proxy estimator, fitted bins, history materialization and posterior work have their own physical costs. They are not additional AST opportunities unless the declared protocol chooses to charge them that way.

Preserve two ledgers: (1) policy requests, failures, cache hits and observed scores; (2) unique physical computations with their costs. Cache hits still consume an arm’s declared opportunity; there is no refill to obtain two new successes. Freeze the shared six-score initial information set. An arm must not inspect scores obtained solely by the other arm’s later selections before deciding its own next program. Physical reuse of an overlapping request is legitimate after that request is fixed. A globally visible cache can otherwise turn the nominal six-plus-two comparison into unequal feedback histories.

The report correctly says encoding collision is not semantic equality. A physical-result cache needs the exact typed AST plus proxy/conditioning definition, data cut, bin/encoding versions, closure/missingness semantics and relevant seed. Distinct AST identities with equal descriptor vectors must remain separately evaluable. They can receive identical predictions from a linear surrogate, which is a representation limitation rather than permission to merge their observed scores.

## Own literal algebra executed

Used only Python standard-library `Fraction` and `sqrt`; no data, learner, real proxy or API was touched. With prior covariance `I`, known observation variance 1, six zero observations at descriptor `(1,0)` give posterior mean `(0,0)` and covariance `diag(1/7,1)`. Unseen descriptors `(1,0)` and `(0,1)` have equal means and variances `1/7` versus `1`. For positive fixed UCB multiplier 1, UCB chooses coordinate 2; a frozen greedy tie rule can choose coordinate 1. Assigning the uncertain candidate true gain +1 or −1 supplies the report’s benefit and harm worlds. These worlds test exploration, not probability calibration or real quality. Simple distinct string AST cache keys were also verified to coexist under equal descriptor vectors; no production cache was exercised.

Before a source pilot, define the frozen proxy, Gaussian prior/noise model, descriptor scaling, UCB multiplier/ties, failed-evaluation rule, information-sharing timing and cache provenance. “Exact posterior” is exact only for that specified linear-Gaussian model. Two final fits mean one frozen final closure per arm; using NDCG as the six initial scores would add at least six distinct learner fits, plus acquisition fits, and violate a two-fit total ceiling. The existing deferred status at report line 47 appropriately acknowledges the unresolved proxy/information contract.

## Scope and freshness

Frozen report SHA-256: `d6fc8db181277765e7de4384e78273c3dc51aaa117428959e9c67f3bff1c8b16`.
Frozen ledger SHA-256: `a46c05b08809c5ddca737d8b37b59c58b5ee966c8b39882a5c8d6667695b705d`.
The frozen copies matched the coordinator manifest when checked. Final checking of moving original files belongs to the coordinating reviewer. A nested independent reader was attempted but the 17-agent limit was full. No author/reviewer/shared file was changed.
