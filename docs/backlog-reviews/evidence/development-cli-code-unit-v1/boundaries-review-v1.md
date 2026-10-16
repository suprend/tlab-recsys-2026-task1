# Development CLI V1 — independent boundaries review

**Changes requested: one supported P2.** Exact candidate `scripts/train_development.py` SHA `464a92ac64d7132223d2286ac0fa23142b9236a54bc46a8f8520c02920f01b5d`; packet SHA `cb0b0530871ac62578dab64fdca30dd089539d6d0199b204c219faf65e60941d`.

## P2 CLI-B-001 — failure telemetry can replace the primary exception

Future canonical `scripts/train_development.py:216–218` catches the original fit/save/guard exception, then evaluates `str(error)`, `budget.observation()` and `report.update` **outside** the best-effort `try` at lines219–223. If telemetry itself fails (for example RUSAGE_SELF observation raises OSError after an existing fit/save error, or a secondary allocation fails while handling MemoryError), that secondary exception escapes before the bare raise, replacing the original cause and bypassing failed-report persistence. The protected write and add_note below do not cover this path. This is a static conditional witness, not a claim that the failure occurred in this review. Existing failure tests only inject fit/save errors while telemetry succeeds.

Keep telemetry/formatting/report preparation inside the same contained best-effort failure path, retaining the caught exception as primary even if telemetry or persistence fails; use a minimal failed report when optional observation is unavailable. Add a focused fake telemetry-failure case asserting original exception identity and no retry. No native test or additional framework is needed.

## Scope checked

The four candidates and relevant actual contracts were read, including `verify_collection`, `validate_training_phases`, `prepare_dataset`, helper and selector. Accepted collection roles/lineage, validated phase maturity and train-cutoff→checkpoint→selection chronology precede preparation/fit. Confirmation/final inputs are rejected by the existing verifier/phase rules. Validation uses `max_queries=None`; the loader retains full Y separately from C and preserves off-C/empty-C/negative queries. Matrix overflow refuses instead of truncating. One helper dispatch performs per-model prefix selection; persistence parity scores the full model at selected k, then the selected copy/reload, without scoring at the ceiling by default.

Fresh directory creation is exclusive; existing/dangling output refusal precedes backend load. The conservative helper-attempt marker precedes dispatch, with no implicit retry/resume. Source/data pins are rechecked around fit/persistence. Resource claims accurately distinguish SELF CPU/peak RSS/run-entry wall and cooperative overshoot from external startup/blocking/tree/cleanup/exit supervision; inherited DuckDB 2GB memory/temp settings are disclosed. No zero-descendant or hard disk/RSS guarantee is claimed.

README/doc changes provide an ordinary supported entry point, preserve the historical fixed-300 route, and explicitly keep new nine fake dispatch tests and native CLI end-to-end **UNRUN**. Tests exercise orchestration/helper/accounting/phase validation but mock collection verification/data loading and selector/native serialization; they do not prove those integrations. The unanswered human50CPU/65wall proposal concerns the separate helper native test and grants nothing here.

All22 inputs and copies matched final hashes. Candidate imports/tests/fixtures/native/SQL/ML/data/models/Y/jobs/helpers/Git/network/canonical edits/coordinator contact: zero. No installation or runtime authority is issued. Root owns adoption and any bounded later execution.
