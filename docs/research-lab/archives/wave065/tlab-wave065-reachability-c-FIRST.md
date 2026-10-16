# Wave065 authorC FIRST — actual retrieval reachability

Source-only, 2026-10-16; 0 new mechanisms/IDs/admissions/grants/gates. Refines existing022/036/040/043/047;013/014/019 remain unchanged. OriginalTask1/deadline25Oct23:59 (timezone unspecified), CLOSED science/native allowance, UNKNOWN remainder and next09:45UTC remain unchanged.

**Conclusion:** empty C is analytically reachable for current schema-permitted raw Q; it is impossible under the stronger assumption that an eligible user has at least one nonNULL-product eligibility event. No actual-source incidence is claimed.

[typed9 parser](/Users/mdpospelov/tlab-recsys-2026/scripts/source_import.py:60) permits product_id=NULL while requiring clock/action; [eligibility](/Users/mdpospelov/tlab-recsys-2026/scripts/anchor_pilot.py:166) counts supported events with nonNULL user_id without requiring product_id. Witness: sole row at t−1h, view, user7, product=NULL. At t=2019-10-08T00:00Z, user7 is eligible; no purchases means popular∅ and recent excludes NULL products, hence C∅. Calendar coverage/maturity are declared synthetic assumptions, not observed completeness.

Conversely, fixed [48h protocol](/Users/mdpospelov/tlab-recsys-2026/configs/protocols/clock-48h.json) gives eligibility actions⊆recent actions and48h⊆168h. One eligible nonNULL product implies recent≥1: positive quota20 retains some product; union/dedup cannot remove the last one. Prior purchases are retained. [Candidate code](/Users/mdpospelov/tlab-recsys-2026/scripts/candidate_pilot.py:38) does not filter on metadata/stock. Positive caps, max_unique equality and budget overflow rejection cannot silently produce empty C. Different windows/actions would change this argument.

NULL product is permitted, not malformed; NULL user creates no eligible Q. Float/exponent/out-of-range IDs are parser rejections; signed64 zero/negative IDs are allowed. Unknown action is invalid. Empty supplied-C projections remain useful stress cases but do not establish retrieval reachability. Dropping event rows/keys is different from optional-field deprivation; missing physical columns violate the fixed schema.

**Mechanism/prediction:** preserving the event bag and keys while nulling category/code/brand/price/session leaves Q/C unchanged; [left feature joins](/tmp/tlab-wave065-frozen-context-v1/9-manual_features.py:213) preserve C, with category features unknown rather than deleted rows.

Nearest finite experiment: future UNRUN 0-fit six-row-total canary across four fixtures: NULL-product view; valid-product view; NULL-product view plus another user's valid purchase; valid-product view before/after optional-field deprivation. Expected user7 C:∅,{p},{r},{p} unchanged. Any mismatch identifies the specific parser/retrieval/adapter boundary to correct. Resources UNKNOWN/ungranted. Task1 benefit: reproducible population preservation and narrower transfer claims; no quality/arrival/stock guarantee or publication gate.
