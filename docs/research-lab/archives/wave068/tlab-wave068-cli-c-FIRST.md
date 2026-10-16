# Wave068 C FIRST — native CLI failure lifecycle

Actual UTC: 2026-10-16T11:26:55Z. Independent source-only author; no peer068 FIRST/review/message consumed.

Outcome: zero new hypotheses; one optional TLAB018 lifecycle-test refinement under TLAB014. TLAB019 selection mechanics remain unchanged.

Observed primary sources: train_development.py:197–220 saves full/selected models before adding curve/support/hash metadata, then writes complete_produced_unreviewed; :221–235 subsequently rechecks inputs and attempts a best-effort failed-report replacement. main:239–242 prints outside that handler. development_collection.py:197–202 uses temporary-write/replace. Existing test_train_development.py:322–336 covers terminal-writer input mutation only when the failure writer succeeds. Its fit/save failure test fails before writing any model, not midway through serialization.

Mechanism/risk: a late input invalidation followed by failed-report I/O failure leaves the prior complete_produced_unreviewed JSON beside unusable evidence, although the original exception propagates. Conversely, summary-output failure can produce nonzero exit beside valid produced-but-unreviewed artifacts. Status, file existence and filesystem timestamps cannot distinguish these cases. No UTC start/completion fields exist in this report; model availability remains declared input chronology, not file mtime. This is a conditional consumption/recovery risk, not an observed invalid acceptance.

Counterhypothesis: documented unreviewed status, best-effort failure reporting and independently checked terminal exit already prevent consumption; no downstream report-only consumer was established. Preserve failed outputs and never infer a retry grant.

Falsifiable prediction / minimal UNRUN experiment: extend the existing terminal-writer-mutation FakeML filesystem fixture so its writer rejects the subsequent failed-report write. Assert the same primary ValueError escapes, one fake helper/fit attempt and zero native fits occur, and the on-disk report still says complete_produced_unreviewed. Inspect artifact inventory and curve presence without loading models; no new framework or native callback test.

Accept the optional test refinement if that distinct persisted-status/exception combination reproduces; reject a production-defect claim absent a consumer that ignores exit/review. Existing018 covers the mechanism family; no new ID, mandatory gate or admission. CPU/wall cost UNKNOWN; science/native grants CLOSED and no execution proposed here. Task1 benefit: truthful reproducibility evidence and avoiding unjustified artifact reuse or budget-consuming refits.
