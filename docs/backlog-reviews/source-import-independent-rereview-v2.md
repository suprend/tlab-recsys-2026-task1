# Typed9 source-import kernel: independent rereview v2

15 October 2026. **CODE ACCEPT for the narrow import kernel.** The original P1 string-preservation defect is closed by the unchanged decisive red test; no blocking finding remains in the reviewed delta. This is not source/runtime acceptance, a CLI implementation, a full-source import, a TLAB-018 completion claim or permission to read actual heldout targets.

## What changed and why the repair closes P1

I read the three frozen v2 files and their full delta against the preserved v1 copies before testing. `validate_csv` now emits a new owned `validated.csv` during the Python lexical validation pass. The writer quotes every field, doubles literal internal quotes, preserves the original parsed token strings, and uses explicit UTF8/newline semantics. It retains only the current row and aggregate counters; it does not accumulate the archive in memory. The native DuckDB reader receives only this canonical file, never the ambiguous raw decompressed spelling.

The raw decompressed CSV identity remains separate from the canonical identity. `validated_csv` evidence includes its actual SHA/bytes and the all-fields-quoted/Python-parser/native-reader policy. The canonical witness is taken before native import and checked after native close and again after evidence persistence. Canonical creation is O_EXCL0600 inside the new0700 work root. ExitStack closes both source/output handles on lexical/writer failure; the csv field limit is restored in finally. Paid canonical writes, initial hash, native read and repins are explicitly described as part of the future owner's original budget. No actual resource/throughput guarantee is inferred.

The original passive counterexample now retains exact brand text ` "x" ` instead of native `x`. Every original independent test method AST, including this red body, is unchanged from the v1 corrected probe. The v2 copy changes only freeze/output filenames. Fresh tests also establish exact preservation for the analogous whitespace/quote spelling simultaneously in category_code, brand and user_session, and intercept the real DuckDB call to prove its sole read_csv argument is the canonical path.

## Actual evidence

- **26 author methods PASS0.363s**, `source-import-independent-author-v2.txt`.
- **17 unchanged independent methods PASS0.295s**, `source-import-independent-v2.py` and `.log`. This includes the original P1 test, all-nine-column extrema/DECIMAL/NULL/unicode/quote/multiline checks, raw bags, gzip member integrity, lexical bounds, consumption and native/storage failure cases.
- **7 fresh independent methods PASS0.194s**, `source-import-independent-v2-fresh.py` and `.log`.
- **50 unique methods PASS** overall for this v2 evidence. The v1 runs, exploratory cases, method subcases and repeated tests are not added to this count.

The seven fresh methods verify: (1) all three text fields' original ambiguous spellings plus the actual native input path; (2) raw/canonical content, distinct original witnesses, exact canonical bytes against independently constructed QUOTE_ALL output, file modes and observed file_hash pass counts; (3) canonical fsync failure before DB creation with primary error/consumed+failed markers preserved and same-root retry refused; (4) malformed second-row retention of only the already validated canonical prefix with no DB/evidence; (5) refusal to overwrite an explicitly existing canonical destination; (6) canonical substitution after its witness but before real native import rejected before any successful evidence; and (7) a wrong expected total count leaving canonical partials without promoting them to native DB/evidence.

The observed module file_hash calls on the tiny positive fixture were canonical3, original archive2, compressed snapshot2, raw spool2, DB2 and evidence1. These exclude the snapshot copy/decompression/native read and do not claim physical full-source throughput or a one-pass import. All positive native behavior used actual locked DuckDB. Failure wrappers target I/O/native boundary failures only; lifetime callbacks do no SQL or mutation. The canonical-substitution test is an explicit accidental-writer fault probe, not a claim of protection against a hostile same-user writer.

All fixtures are artificial and temporary: independent fixtures contain at most two event rows; author fixtures at most four. No actual REES46 archive/hash/import, real Q/Y, native model load/predict/fit, download or Git operation occurred. Python3.12.14 / DuckDB1.5.6.

## Identities and preservation

The exact v2 SHA/byte pairs matched before and after all tests; original v1 copies still match their original freeze. V2 copies are preserved under `preserved-v2-original/`. V1's original red scripts/logs and the disclosed initial path-monitor harness failure remain intact.

| File | V1 SHA256 | V2 SHA256 | V2 bytes |
|---|---|---|---:|
| scripts/source_import.py | 16e1a225ef86bb40efdfa1b5ebc1e42ebf128040c634e4b4f27dc90b509aaa12 | 7d7ed34b336294bd18d822b9798a7b644f45dc72f8c1f6edeb6d518b55284236 | 14444 |
| tests/test_source_import.py | 116496e68662b9c620c40a8a126be4630a11bf7ed0afc56cab65003e7f3169cc | 97cf28b827a8dc1f56ab128320993b27ad29f7e2ec82777e3ac6e81b8da7b073 | 13098 |
| docs/experiments/source-import.md | 48c5ac56414c3ac3a4059fd12730adcd9df7992b471b08817ec4773142781acc | 98466edae086ac3f5ac0e14b0a71a093306b7a618c0789fc50f7cd9a233265dc | 8397 |

Machine-readable result `source-import-independent-v2-results.json`; exact pre/post maps `tlab-source-import-independent-v2-pre-hashes.json`, `tlab-source-import-independent-v2-post-hashes.json` and `tlab-source-import-independent-v2-fresh-post-hashes.json`.

## Remaining boundary

Code acceptance covers the supplied local gzip→strict typed9/new DB kernel under a trusted caller, and its honest evidence/failure mechanics on tiny data. Aggregate native checks alone still are not a general full-row equivalence oracle; the canonical representation removes the observed dialect disagreement without claiming an exhaustive independent value audit of every imaginable input or actual dataset.

The future outer owner must still consume/authenticate its original paid allowance and code/source identity, authenticate installed packages, supervise total CPU/wall/RSS/spill/disk and complete cleanup/exit tail, record startup failures (including a consumed-marker I/O failure before the kernel's main try), forbid free retry by renaming a root, and independently accept closed snapshots/DB/evidence plus actual process lifetime before a bootstrap handoff. Raw/canonical snapshots are separate paid disk artifacts;8GiB spill is not total disk capacity. No real run or resource capacity was authorized or demonstrated here.
