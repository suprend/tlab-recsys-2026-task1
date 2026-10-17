# Wave103: independent primary-source / hand-math check

**Verdict:** the literal population counterexample is correct under its stated full-list, binary-gain, equal-query/pair-weight assumptions.

Let t=1/log2(3), p=9/20 and q=11/20. The discount vector is (1,t,1/2); K>=3 includes every member of C={a,b,c}. IDCG is 1 for Y={a}, and 1+t for Y={b,c}. Hence, for any fixed permutation pi,

E[NDCG(pi,Y)] = p D(rank(a)) + q/(1+t) [D(rank(b))+D(rank(c))].

The coefficients are (p,q/(1+t),q/(1+t)). Since 1<log2(3)<2, t>1/2; therefore q/(1+t)<11/30<9/20=p. Swapping any inverted unequal coefficients increases the expectation, so every optimal permutation places a first; b and c may be exchanged. This is also the normalized-expected-gain ordering in Ravikumar et al., Definition 1, Lemma 4 and Corollary 5. For example, the exact expected advantage of a,b,c over b,c,a is (p-q/(1+t))/2>0.

For ordinary unweighted per-item BCE, the marginal positive probabilities are (p,q,q). Strict propriety follows directly: differentiating -r log(z)-(1-r)log(1-z) gives (z-r)/(z(1-z)); its unique optimum is z=r. Thus BCE orders b,c above a.

The pinned CatBoost PairLogit definition is weighted mean negative log sigmoid(score_positive-score_negative). With full positive-negative pairs, {a} produces (a,b),(a,c), while {b,c} produces (b,a),(c,a). Put u=sa-sb, v=sa-sc, and h(x)=log(1+exp(x)). Equal total pair weight per query gives

R = (1/2){p[h(-u)+h(-v)]+q[h(u)+h(v)]}.

Each contrast minimizes independently: derivative of p h(-u)+q h(u) is (q exp(u)-p)/(1+exp(u)). Its strictly positive second derivative establishes the unique contrast optimum u=v=log(p/q)=log(9/11)<0. Consequently sb=sc>sa; equality of b,c need not be assumed. Common score shifts remain unidentified. Summing instead of averaging the two equally weighted pairs only multiplies R by a positive constant.

**Scope and limits:** X means the same observed candidate feature list across future outcomes; the score-vector argument permits candidate-specific coordinates. Literally identical, indistinguishable features for all three candidates would require an additional representability assumption. This establishes disagreement between unrestricted conditional population objectives on one fixed list. It proves neither trained-model quality gain nor finite-sample, optimization, architecture, dataset, or deployment performance.

**Primary sources actually consulted:** [Ravikumar et al. PDF](https://proceedings.mlr.press/v15/ravikumar11a/ravikumar11a.pdf), extracted Definition 1 and Section 3.1 Lemma 4/Corollary 5; [CatBoost v1.2.10 ranking losses](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/docs/en/concepts/loss-functions-ranking.md), PairLogit formula and generated-pair paragraph. Exact tool exposure and limitations are in the adjacent pins JSON. No author FIRST, repository/data/Git/private artifacts, code execution, tests, models, or experiments were consulted or run.
