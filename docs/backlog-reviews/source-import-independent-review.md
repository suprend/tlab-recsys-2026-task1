# Typed9 source-import kernel: independent review v1

15 October 2026. **CHANGES REQUIRED: one P1 parser-conformance defect.** Review applies only to the three frozen files below. No real REES46 archive, actual source hash stream/import, Q/Y, CBM, prediction, fit or Git operation was performed. All runtime probes used new temporary roots and at most two artificial event rows each; the largest text boundary fixture contains one 65536-character multibyte field. The child contract reviewer inspected code/docs only and ran nothing.

## Blocking finding

**P1 — native CSV parsing silently changes a lexically validated string.** In `scripts/source_import.py:153`, DuckDB reads the original decompressed CSV independently after Python's `csv.reader(strict=True)` lexical pass. With a raw brand token containing exactly space, quote, x, quote, space (` "x" `), Python treats both quotes and spaces as literal text because the quoted field did not begin at the field boundary. The lexical pass accepts this nonempty string. DuckDB instead interprets the whitespace-surrounded quote pair and imports `x`. The kernel returns `import_kernel_complete_pending_external_source_acceptance`.

This is an actual value-preservation failure, not a request for a stronger hostile-writer model or a counterfactual native mock. It needs no callback mutation, monkeypatch, SQL from the lifetime callback, concurrent write or real source data. `scripts/source_import.py:155–158` cannot detect it: row/action/NULL/time aggregates are identical. The same parsing path handles category_code and user_session too; only brand was exercised by the decisive red. Source-import.md's nonempty-string/raw-bag semantics are therefore not satisfied for all currently accepted lexical inputs.

The unchanged decisive test method is `test_validated_literal_space_quote_string_survives_native_import` in `source-import-independent-v1-corrected.py`; its failure is saved in `source-import-independent-v1-corrected.txt`: expected literal ` "x" `, actual `x`. `tlab-source-import-exploratory-v1.json` separately records the same discrepancy among seventeen literal-string cases, including successful quoted commas/newlines/CRLF/unicode/NULL strings.

A robust repair consistent with the declared API is to write a separately owned canonical CSV stream from the Python-validated token rows using `csv.writer(QUOTE_ALL)`, then make the native loader read only that stream. Keep the original decompressed snapshot/hash separate, retain the new canonical snapshot/hash, and charge its write/import/repins to the original external owner. Empty tokens must still become NULL only in the declared nullable fields, while literal NULL/NA, whitespace, literal quotes and multiline strings remain text. Rejecting this one token or all quote-containing strings would narrow the current contract and miss the underlying two-parser problem. A complete independently streamed typed-value comparison is another possible repair if its cost and raw-bag/order semantics are explicitly designed. No repair was made by this review.

## Evidence and test accounting

- All three original SHA/byte pairs matched freeze-v1 before and after all probes; copies are retained under `preserved-v1-original/`.
- Author scope: **23 unique methods PASS 0.206s**, once, `tlab-source-import-independent-author-v1.log`.
- Independent scope: **17 unique methods, 16 PASS / 1 genuine FAIL, 0.275s**, `source-import-independent-v1-corrected.txt`.
- Combined: **40 unique methods, 39 PASS / 1 FAIL**. Repeated execution and seventeen exploratory cases are not added to that count.
- First independent execution also had a probe-harness failure: macOS temporary `/var` paths were compared textually against the kernel's resolved `/private/var` source path, so the source-open monitor saw zero matches. The original script/log remain `source-import-independent-v1.py` and `.log`. The corrected copy resolves the fixture root before comparison. Every `test_*` method AST, including the genuine red body, is unchanged; only fixture setup path normalization and the output hash filename differ. This was a harness error, not a second production defect.

Independent passing coverage includes exact all-nine-column comparison for signed64 extrema, signed zero, DECIMAL range, NULLs, literal NULL, whitespace, unicode, doubled quotes and multiline strings; raw duplicate bags and CRLF; concatenated gzip members split within a UTF8 code point and CSV record; corruption/truncation of the second member; nongzip trailing payload; 65536-character multibyte success/65537-character rejection with csv global-limit restoration; NUL and blank-record rejection; consumed marker presence before the first source read; committed partial DB and original error preservation on CHECKPOINT failure; original persisted-evidence digest enforcement; primary evidence-storage failure with a secondary failure-writer exception; known late failed marker; and invalid profile rejection before source open/work-root creation.

Fault wrappers exercise native CHECKPOINT/storage failures only. Positive cases use real locked DuckDB. The lifetime callback only increments a counter; no finding relies on violating its trusted non-SQL contract.

## Scope and future-owner requirements

No other substantive kernel defect was established. The aggregate check is not a general full typed-row equivalence oracle; successful tiny cases do not prove all inputs or full-source throughput. The consumed marker is written outside the main try: if its initial creation/fsync itself fails, a work root may remain without a report.failed marker. No source bytes have been read at that point, and existing-root refusal prevents same-root reuse, so this is a pre-paid failure-handling/documentation edge, not another correctness blocker. The external owner must record that startup failure/attempt too.

The kernel intentionally does not supply source/execution authority, installed-package authentication, a CLI, an OS resource fence, final full-lifetime receipt or downstream source acceptance. A future owner must consume its original allowance before invoking paid source reads, authenticate the production profile/code/input and original archive destination, supervise total CPU/wall/RSS/spill/disk including every copy/hash/canonical pass and cleanup, forbid implicit retries under renamed roots, retain partials/failed receipts, and independently bind closed DB/snapshot/evidence identities and actual exit/lifetime before handing the DB to bootstrap. No current tiny test authorizes an actual import or closes TLAB-018.

## Immutable reviewed identities

| File | SHA256 | Bytes |
|---|---|---:|
| scripts/source_import.py | 16e1a225ef86bb40efdfa1b5ebc1e42ebf128040c634e4b4f27dc90b509aaa12 | 13073 |
| tests/test_source_import.py | 116496e68662b9c620c40a8a126be4630a11bf7ed0afc56cab65003e7f3169cc | 11200 |
| docs/experiments/source-import.md | 48c5ac56414c3ac3a4059fd12730adcd9df7992b471b08817ec4773142781acc | 6972 |

Machine-readable evidence: `source-import-independent-v1-results.json`; exact pre/post maps: `tlab-source-import-independent-pre-hashes.json` and `tlab-source-import-independent-corrected-post-hashes.json`. Interpreter Python3.12.14 / DuckDB1.5.6.
