# Wave071 B — category labels versus identity

UTC: 2026-10-16T13:35:58Z. **REFINEMENT of TLAB-010/HYP-003 and existing category-text controls; NEW=0.** Independent FIRST; peer071 drafts/reviews/messages unread.

REES46 has nine fields, no titles/descriptions/images. Sparse `category_code` is taxonomy text; filled numeric IDs cannot recover unobserved names.

**Mechanism.** In this bag-of-words regime, complete weighted code histograms, masks and frozen mapping determine lexical scores: compression/regularization can help, but adds no information to that state. Reduced candidate-ID/ancestor counts can miss cross-branch word sharing, allowing `coffee` to pool rare-category evidence. This is lexical transfer, not established language understanding. BM25 frequency/length scaling can instead re-express activity normalization ([Stanford IR](https://nlp.stanford.edu/IR-book/html/htmledition/okapi-bm25-a-non-binary-model-1.html)). Counterhypothesis: identity, hierarchy and nonlinear count normalization explain everything.

**Minimal manual experiment — UNRUN.** Freeze vocabulary/IDF, event weights and candidate `a.coffee_machine`. Compare one equally timed past view of `b.coffee_grinder` versus `b.paper_shredder`. Prediction: candidate/exact-code and candidate-ancestor counts tie; words split at `.`/`_` yield different overlap. Complete histograms differ, so this cannot demonstrate information beyond complete counts. Hand-tabulate:

- Two numeric IDs sharing one code: identical text scores, distinct ID signals.
- Bijective token renaming preserving membership: unchanged BM25/TF-IDF. Permuting complete lexical vectors among code strings with identity/hierarchy frozen tests alignment, without isolating meaning from taxonomy geometry.
- Text-only deprivation: numeric-ID baseline survives; text is unavailable with masks, never a shared `unknown` token. Joint metadata deprivation is a separate contrast; preserve noncategory values, Q/C and history support.

Any mapping uses only observations before `t`, the entire latest global product timestamp bucket, and explicit code availability: NULL/conflict stays unknown; no older clean backoff or future taxonomy fill. Historical categories retain their event-time meaning. Vocabulary/IDF precede the first anchor; OOV/missing remain separate.

The witness can establish representational discrimination only. Predictive benefit and full cost for Task1 remain **UNKNOWN**; the current same-`synthetic.item` fixture and F270 review establish no text utility or ambiguous-category coverage. Keep 014 continuous and 010 optional/deferred; no new IDs, gates, pilots, models, downloads, fits or grants.
