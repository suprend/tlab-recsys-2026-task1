# R3 batching regression v3 — fresh independent SOURCE review

**SOURCE PASS for the amended finite fixture; no supported defect found. Runtime/mutant behavior UNRUN.** Test SHA256 `fe287023fb5f852702288637a04125226dec97e288911d355258d6ee7eb0f8f5`; manifest SHA256 `9d0ede50373160328b6935fb1e5b81a560bebab262c58cabd30d10a9f06de8d4`. V1/V2 source and my reviews/freezes remain immutable. Full V3 test and metadata read; textual/AST delta from V2 independently checked. Candidate line references below.

## Supported delta and protocol

V3 adds only D/user999 at FIRST with D/OUTSIDE90, includes D exactly once in each schedule, adds D's literal row and strengthens the candidate-denominator mutant comparison (`:50-72,160-165,279-293`). EVENTS AST, independent `expected_extra`, compiler schedule implementation and both mutation mechanisms are unchanged. No producer source is edited.

FIRST now has A/D/C-empty:3 unique user-days. SECOND has B:1. Two-day daily cap3 requires6 anchors and6×220=1320 pairs, matching both sections (`:209-211,263-265`) and previously inspected protocol validator. Actual4Q/6C remain below those declarations. Empty-C Q is retained in every schedule and asserted by exact query multiplicity. The fixture contains22 event rows (below24),4Q/6C, or32 total relation inputs; these bounds must remain distinct in any run contract.

## Same-anchor counterexample is now substantive

At FIRST the whole compiler batch's candidate-item set includes ITEM/OTHER/COLD/**OUTSIDE90**. Singleton A contains ITEM/OTHER/COLD and excludes90. This is actual variation of the day-item domain used by the patched category aggregate; it closes the prior specific coverage gap.

Independent arithmetic: category100 has ITEM's one view plus OUTSIDE's three in-window views, hence A numerator1/denominator4/share0.25; D numerator3/denominator4/share0.75. OUTSIDE's fourth older row falls before the seven-day lower bound. The normal compiler should preserve those values across all schedules.

The candidate-conditioned mutant executes the actual compiler twice under a local `_grain_sql` patch (`:270-283`). Whole A remains denominator4/share0.25; singleton A becomes denominator1/share1.0. Four explicit numerical assertions verify that exact mechanism before both complete keyed equality **and** literal-core checks must reject it (`:286-293`). The outputs share the same six keys, so a changed row universe cannot substitute for the required A discrepancy. This is a genuine SQL/domain fault; neither expected output nor final vectors are fabricated.

The stale metadata control remains valid with D present: first-anchor metadata still resolves ITEM100; preserving that real TEMP table at SECOND yields B100/denominator2/share0.5, explicitly checked before rejecting expected200/0.25 (`:297-323`). The new OUTSIDE candidate does not alter those two historical category100 views in B's window.

## Independent extras and limits

All eight extras still use the separate row/set interpreter with each query's actual user/anchor (`:75-96,237-242`), including D and its absent cart/purchase histories. Exact type checks distinguish bool/int; schema/NULL/key checks and complete B45 preservation remain (`:130-151,234-242`). Whole/split/singleton schedules reverse insertion order and reuse private TEMP state across successive calls. No Y relation/model loader/fit is invoked; fixed Q/C remain supplied inputs, not retrieval or source acceptance proof.

Full B45 equality is metamorphic plus selected independent literals, not an exhaustive independent arithmetic/future-suffix/pre-source proof of every field. Previously stated coverage qualifications otherwise remain. Proposed work bounds are consistent:9 variants×(1+2+4)=63 normal compiler calls; candidate mutants1+4 plus stale1 give69 total;89 anchor batches/30 sequential connections. Costs CPU/wall/RSS/cleanup UNKNOWN; the90CPU/120wall proposal is not execution authority.

AST/hash/readbacks verified for V3, dependencies and preserved prior artifacts. No imports/tests/SQL/native/ML/real data or canonical/Git mutations performed. Next permitted preparation is Root's separate concrete bounded toy CODE contract and subsequent actual-output review. This source PASS does not establish runtime success. Freeze/readback then STOP.
