# COVERAGE-SOURCE-v2 — narrow P3 rereview

**SOURCE sufficient for the concrete appended-matrix float32 P3; CODE remains pending.** No new production finding.

Authenticated v2 manifest `7b14188c…`, freeze `6274cc13…`, all8 source `8b0e0fa9…` and unchanged typed9 source `22e4f41a…`. Byte comparison against immutable v1 proves the only candidate-source change is `tests/test_feature_programs_all_bundles_rich.py:330`: `projected.x.dtype == np.dtype('float32')`, inside every all8 projection iteration. Removing that exact line reproduces v1 byte-for-byte; typed9 bytes are identical. Full hashes are in companion pins.

The original static witness—correct float32 B41 but value-identical float64 B44—now fails this explicit assertion. Existing B41 x/group/item dtype assertions at287–289 remain. Per-B44 group/item dtype assertions are still implicit through unchanged shared loader allocation and base checks; v2 does not add those optional strengthening checks. Accordingly this closes the concrete float64-X omission, without claiming every suggested type guard was added.

Independent literal schemas/CSV bytes, rich nonzero all8 values, NULL masks, exact keys and label-free projection logic are unchanged; prior SOURCE scope and limitations stand. Category expectations still come from the handwritten-history interpreter, not new literal category gold. No native ML/E2E/real-data claim follows.

Next: Root must freeze the combined isolated checkout, revalidate changed dependency hashes and run exactly the two named methods under its issued bounded ordinary CODE contract. Test outcome, startup/import/cleanup cost and the hypothetical mutant's observed failure remain UNRUN/UNKNOWN. This rereview executed text/byte/hash/readback only—no project imports, tests, SQL, native/models or data execution. Earlier reports and both candidate versions remain immutable. STOP.
