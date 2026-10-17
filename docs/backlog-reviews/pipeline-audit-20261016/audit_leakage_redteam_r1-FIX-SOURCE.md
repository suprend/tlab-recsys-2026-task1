# FIX SOURCE review — empty development days

**SOURCE-only: no actionable defects found in the frozen repair. Pending Root's bounded CODE check; no runtime acceptance is implied.** Candidate `scripts/development_collection.py` SHA256 `0aaf7a53236863540a86a77730215d1c5e106bf29f9440402a8527a03e717736`; new test SHA256 `24531193cfdd593b88074061675002afea13e648dfb24586dd644d63894adb80`. Base HEAD `c538de4097322715fccac494e2b2becc3279e8e1`.

Inspected exact candidate diff, changed aggregate/unchanged caller and authentication paths, all139 new test lines, existing real producer fixture106–215, and previously frozen anchor/C/F/protocol boundaries. SHA256/readback checks passed; a stdlib text diff reconstructed from the two targets equals the supplied complete `candidate.diff`. No other integration changes were present. The handoff's independent-review statement was not used as correctness evidence; no independent child review artifact was read.

## Boundary assessment

- Candidate `scripts/development_collection.py:339–343` still authenticates cached child reports and their Q/Y/C/F lineage **before** calendar inspection. `_verify_run:263–279` still hashes actual dependencies and every physical output; `_check_cached:291–295` still compares the exact original seal.
- `:346–355` constructs the calendar from the planned shard interval, requires authenticated `population` anchors to match it exactly and requires nonnegative exact-int `sampled_queries`. Missing, duplicate, reordered or outside dates fail. This uses the producer's per-day population, not a fabricated outcome relation or inferred min/max observed source time.
- `:358–364` requires outcome dates to equal precisely the population dates with sampled Q>0 and reconciles their query counts. An absent outcome row is therefore allowed only for a declared zero-Q day; a missing nonempty outcome, a spurious zero-day outcome, or count disagreement fails. `:361,374–381` now retains the full phase calendar. Existing physical aggregate/count, maturity, uniqueness, orphan and C/F identity checks remain unchanged (`:393–434`). All-nonempty population produces the same outcome sums and output schema as before.
- True missing/duplicated shard checks remain at `:331–338` and runtime `:534–540`. Zero-row files remain mandatory physical artifacts: removing an empty Q parquet fails its original seal/hash read, before any population allowance. There is no rule treating an absent file as an empty relation.

## Test-source assessment

The five new methods instantiate the existing `DevelopmentRuntimeTests` fixture rather than mocking `aggregate_collection` or replacing coverage reports (`tests/test_development_empty_days.py:12–16`). The reused fixture calls actual `run_phase` and real anchor/C/F producers; only external approvals are simulated through their existing pinned fixture mechanism (`tests/test_development_collection.py:169–193`). Source/config mutations get a fresh collection plan/producer approval (`new tests:18–35`). Each positive case performs production, explicit approval, then ordinary resume (`:37–51`).

Written cases cover the one-event empty-first-day witness and cached resume (`:58–68`), off-C fullY product20 versus C product10 using actual exported parquet references (`:70–92`), all-empty typed outputs plus cached resume (`:94–104`), empty/nonempty dates inside one two-day shard (`:106–116`), and absent/duplicated state entries plus physically absent empty-Q file (`:118–135`). These target the actual upstream cause. The original nonempty producer/resume test is unchanged. The declared source/lookback/maturity assumptions remain valid; no query or label is invented to fill the calendar.

Coverage limitation: new malformed-population/missing-nonempty-outcome guard branches are checked statically here and have no direct new regression method. The five methods have been **read, not run**; child production, SQL behavior, resource sufficiency and compatibility with the later combined recipe remain unverified. Root owns CODE and integration, including the public recipe's dependency pin.

Verification: source/text and metadata hashes only. **No project/source imports, tests, SQL, data reads, native packages, models or producers were executed.** FIRST/R2 and canonical repository files were not modified. STOP after freeze/readback.
