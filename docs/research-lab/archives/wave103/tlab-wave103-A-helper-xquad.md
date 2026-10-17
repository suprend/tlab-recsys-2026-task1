# xQuAD primary-source check — wave103 A helper

Read-only research. Created 2026-10-17, UTC. Only the two requested /tmp outputs were written. No repository, local data, peer drafts, DB/Q/C/Y/models, actual coverage, imports, tests, SQL, fits, Git or network mutations were used. No claims about REES46.

## Citation correction and source reading

The requested attribution «Santos/Macdonald/Ounis, Explicit Search Result Diversification, SIGIR 2010» was **not verified**. The author-linked primary paper is **Santos, Peng, Macdonald, Ounis, “Explicit Search Result Diversification through Sub-Queries”, ECIR 2010**, DOI 10.1007/978-3-642-12275-0_11. [Author PDF](https://ir.dcs.gla.ac.uk/terrier/publications/ecir2010_rodrygo_div.pdf); [author publication listing](https://www.dcs.gla.ac.uk/~craigm/publications.shtml).

Inspected source scope: PDF zero-based pages 0–8, specifically abstract/introduction; §2; §3, Algorithm 1, §3.1, §3.2; §4.1–4.4; opening of §5 through the text preceding Table 1. The mechanism check relies on §2 and §3/Algorithm 1. Tables, later findings and conclusions were not reviewed.

## Source-supported mechanism and assumptions

Algorithm 1 selects greedily from the initial pool R(q). With b(d)=r(d,q), a_i(d)=r(d,q_i), w_i=i_X(q_i,q), its score is

    score(d | S) = b(d) [Σ_i w_i a_i(d) / m_i(S)]^ω
    after selecting d*: m_i ← m_i + a_i(d*) for every aspect i.

Thus already represented aspects lose weight through inverse accumulated relevance mass. One document can update several aspects. Explicit subqueries, aspect importance and relevance estimates are inputs; quality depends on the aspects. Original-query relevance supplies a common comparison basis when subquery scores differ. §2 explicitly contrasts this with predetermined aspect shares and with MMR’s pairwise similarity. **Algorithm 1 does not show initial m_i values**: a positive initial mass/smoothing is an implementation choice, not a verified prescription. This early paper does **not** establish the familiar residual-product formula or its probability/conditional-independence assumptions.

## Independent mathematical interpretation, not an empirical result

Under nonnegative b, a_i, w_i, positive m_i and ω>0, enlarging S weakly decreases each aspect-specific contribution w_i a_i(d)/m_i(S). This is a precise diminishing-novelty mechanism. It does not by itself prove the implemented multiplicative score is the exact marginal of a submodular set objective, or supply an approximation guarantee. Avoid those stronger claims.

A single fixed prefusion pool is compatible with this distinction: selection still changes its aspect state. Fixed quotas change eligibility or allocation by counts/targets; this formula continuously discounts each represented aspect using relevance mass. Ordinary fixed-weight RRF is a static per-document rank sum; without prefix-dependent weights it has no analogous update. Standard max-similarity MMR is also prefix-dependent, but its penalty is pairwise against selected documents; an explicit mass vector need not be recoverable from the maximum pairwise similarity.

These are mechanism distinctions, **not identifiability from the final list alone**. Degenerate aspect scores, ω=0, dominant relevance, pool restrictions or ties can yield identical output. A specially adapted MMR or dynamically weighted fusion may emulate the ranking. Therefore the honest refinement for fusion11 is conditional: specify explicit aspect memberships/scores, positive mass initialization and per-selection mass updates; label the early ECIR formula correctly; contrast against *fixed* quotas/RRF and a precisely specified MMR. The primary reading supports no claim that this improves any local dataset, and no new gate or experiment is proposed here.
