# Second independent SOURCE review — feature boundaries / cleanup fix

**SOURCE PASS within the stated boundaries; no supported new code or fixture defects found. Runtime remains UNRUN.** Candidate manifest SHA256 `a759aa17a9ae881db994ebd69f8f4a42998e547d3ba63f69d3ac0bec9314b785`, frozen baseline `c538de4097322715fccac494e2b2becc3279e8e1`. Locations below refer to exact `candidate/` files, mapped to original repository paths by pins. My FIRST/R2 remain immutable.

## Cleanup failure semantics

Reviewed all four changed run boundaries: `scripts/manual_features.py:398-423`, `anchor_pilot.py:359-381`, `candidate_pilot.py:262-283`, `heuristic_baselines.py:357-381`.

Each body now catches `BaseException`, retains the identical primary object and uses bare re-raise. Finally calls close once in a guarded block. A close fault sets failed and records `cleanup_errors`; it updates `error_type/error` only when no body error exists. With healthy subsequent operations/sinks, receipt persistence runs before any close-only exception is re-raised. With a primary exception, the final conditional does not raise cleanup, so the original pending exception exits unchanged. This closes the previously confirmed missing-child-receipt and top-level-primary replacement branches, including the ordinary KeyboardInterrupt class.

Successful export followed by failed close therefore leaves exported artifacts plus a **failed** receipt, not complete acceptance. Manual/anchor/candidate write their existing run manifest; heuristic retains its established identity/report format. No retry, reconnect, deletion, acceptance change or resource-limit change appears in the diffs. This preserves output evidence rather than claiming that a failed native close released resources.

Remaining explicit boundaries are appropriate: timer cancellation still precedes guarded close; measurement, receipt/manifest sink and printing faults can interrupt finalization or replace the primary. Process termination and pre-try/open failures are also outside this narrow repair. The handoff does not promise unconditional failure persistence under these compound cases. In particular, the outward-primary guarantee is conditional on healthy finalization sinks/operations, consistent with my R2 scope.

## Written tests exercise the actual route

`tests/test_runner_cleanup_receipts.py:38-58` builds/seals toy DB/Q/Y/C before faulting connections. The reused fixture creates synthetic provenance tokens (`tests/test_heuristic_baselines.py:241-277`); these are not claimed as real source authentication. Test execution invokes actual four run entry points (`:65-72`), not an extracted control-flow facsimile. The proxy delegates SQL/profile/interrupt methods, closes the real toy connection once, then raises (`:19-34`). For double faults, wrappers call the actual compiler/builder/ranking evaluator before raising the selected primary (`:90-109`); core receipt writers are not stubbed.

Assertions cover identical raised object, one connection/close, closed toy resource, readable failed receipt, body and cleanup causes, timing/resource fields, expected manifests, preserved successful-body exports, manual KeyboardInterrupt, and four healthy controls (`:110-161`). These are meaningful proposed regressions; none was executed here. They establish closure only for a proxy that closes before throwing, not for arbitrary native failed-close behavior. BaseException injection is written for manual only; the other three share the independently inspected implementation pattern.

## Namespace / old matrix behavior

`manual_features.py:49-76` checks the complete emitted namespace, including automatic missing flags, against both retrieval names. Direct age and `retrieval_last_event` roots producing `_missing` reject; plain pair count root remains legal. `train_baselines.py:189-198` checks safe physical names, duplicate inputs and the final projection after appending retrieval fields. It neither reorders nor deduplicates surviving inputs. Literal B41 assertions and collision controls are independent of implementation (`test_feature_projection_reserved_names.py:13-83`).

Stdlib AST comparison confirms the five existing files change only the four run functions, registry validator and projection helper among named definitions. Aggregate formulas, candidate generation, target construction, FLOAT/NaN conversion and matrix loading are unchanged. Frozen `program_model_data.py:119-152` still copies B41 and appends exactly three keyed columns; existing B41→44 parity tests remain required runtime controls, not newly passed evidence.

All seven candidates parse, five baselines equal frozen bytes, and candidate/diff/freeze hashes match. The prior child source review was read after my own analysis and agrees; its disclosed TMP `git diff --no-index` deviation is not my activity or runtime evidence. I used no Git, project imports, tests, SQL/native/ML or data reads. Next: separately authorized bounded toy tests and preserved controls; then independent runtime/output review and explicit public-recipe pin refresh before integration. Freeze/readback then STOP.
