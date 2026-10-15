# Strict typed9 source-import kernel — code review pending

15 October2026. First narrow implementation increment for TLAB-018: an explicitly provided local gzip becomes a new nine-column events DB and aggregate import evidence. **This is a caller-owned kernel, not a ready execution CLI or source acceptance.** No actual REES46 archive/hash/import/download/EDA/Q/Y/model has run. The outer source/resource request, bounded fresh-process owner and independent source handoff remain unfinished;018 is not complete.

## Fixed source semantics

`scripts/source_import.py` exposes `validate_profile`, `parse_row`, `validate_csv` and `import_archive(archive,work_directory,profile,check=...)`. The latter requires a trusted lifetime callback and an entirely new work directory. It creates a0700 owned directory and an exclusive consumed marker before paid source reads. Existing DB/work roots, including partial or metadata-plausible DBs, are refused without reuse or overwrite. A different root is not a free retry authorization: the future external owner must bind the original execution allowance and all failed attempts.

The production profile pins the project's observed compressed SHA8ebca1ad741295297368f2cf0315e3f36853a1a11768fb16babf8c9b83838147,1741928540 compressed bytes,5668612855 full uncompressed bytes and42448764 raw rows. It is an observed project identity, **not a publisher-signed checksum**. Production values cannot be resealed through this API. Tiny tests use a separately named synthetic scope with their own fixture hashes; they never substitute the production source identity. No ignored download manifest is required.

Header order is exactly event_time,event_type,product_id,category_id,category_code,brand,price,user_id,user_session. Types are TIMESTAMP,VARCHAR,BIGINT,BIGINT,VARCHAR,VARCHAR,DECIMAL(12,2),BIGINT,VARCHAR. Literal UTC second timestamps must lie in [2019-10-01,2019-11-01); only view/cart/purchase is supported. Clock/action are required. The other seven fields explicitly permit empty→NULL; permitted NULL keys are retained and counted rather than dropped. This is a parser allowance, not a claim that missing keys occur in the actual archive.

CSV uses strict UTF8/comma/double-quote/doubled-quote rules, exact nine fields, no padding/error skipping, no NUL and at most65536 characters per field. Both quoted and unquoted empty values map to NULL only in declared nullable fields. Nonempty literal strings such as NULL/NA remain strings. Numeric keys require exact signed64 integer tokens with no float/exponent/intermediate rounding. Price requires an exact ordinary decimal token with at most two fractional places and magnitude≤9999999999.99. Zero and negative permitted prices are retained; zero is not missing. There is no clipping, deduplication or row-order causal interpretation.

## Paid data path and integrity

The kernel creates an exclusive0600 run-local compressed snapshot while hashing the actual consumed bytes and counting compressed size. It fully decompresses that owned snapshot to a0600 CSV spool, reaching gzip EOF and checking every member CRC/ISIZE. The separate full uncompressed byte counter is not modulo2³²; the gzip trailer alone cannot establish a5.67GB CSV size.

A streaming lexical Python CSV pass verifies header/types/period/actions/NULL policy and raw-bag row count before a native DB is created. It writes an exclusive0600 canonical validated.csv with every parsed field explicitly quoted and doubled internal quotes. Only bounded aggregate counters/time extrema plus the current row are held in memory. Native DuckDB reads only this canonical representation using explicit nine-column types, no auto-detection/error skipping/padding, fixed timestamp/null policies and a transaction. Exact schema plus full row/action/NULL/time aggregates must agree with the lexical pass. Duplicate rows and global timestamp peers are preserved. Four-row literal tests independently compare BIGINT>2^53 and2^53+1, full DECIMAL values, quoted strings/NULLs and duplicate multiplicity.

After COMMIT/CHECKPOINT/close, source/snapshot/raw-spool/canonical-spool identities are checked and a new physical DB SHA/size is recorded. The DB is a new derived identity and need not match the historical DB's bytes. Aggregate evidence is exclusive; input/DB/evidence snapshots are rechecked after persistence. A late DB mutation or failed marker prevents a successful return. On failure the original exception remains primary, cleanup/persistence failures become notes, and partials plus the consumed/failed markers remain.

This is intentionally multiple passes/copies, not a single-pass or free dry run. The owned files protect against accidental competing writes within the trusted caller lifecycle; they are not a hostile same-user writer lock. All copies, decompression, parsing, native import, hashes, persistence, failure and cleanup costs belong to the future original owner budget.

## Runtime and acceptance limits

Native connection settings are two threads,2GB engine memory and8GiB spill. These are prospective engine settings, not a proven full-process RSS/throughput bound. The callback runs between chunks/stages; it alone cannot interrupt a blocked native statement. A reviewed outer process supervisor/live resource fence is required before a real archive import. The kernel does not start subprocesses, install global CPU limits, authenticate installed packages or grant any execution allowance.

The returned status is `import_kernel_complete_pending_external_source_acceptance`, with original profile/hash/bytes, full gzip integrity evidence, typed schema/raw-bag aggregates, new DB identity, labels_created=false/fit_attempt_count0 and an explicit external-lifetime requirement. It does not prove marketplace logging completeness, availability delays, downstream feature correctness, historical numerical replay or a fresh collection/model seal. No raw identifiers are included in aggregate evidence; run-local snapshots/DB remain private artifacts.

## Actual tiny evidence

Twenty-six author methods PASS0.355s, covering the original23 plus the canonical-spool regressions on the locked local DuckDB1.5.6 environment. Fixtures contain at most four artificial event rows; variants reuse these small literal records. They cover exact typed9/BIGINT/DECIMAL/raw bags/peers/metadata NULL and quoted comma/quoted empty, header-only empty source, compressed hash/size and full uncompressed size, corrupted CRC/truncated gzip with matching synthetic compressed hashes, reordered/duplicate headers, incorrect field count, malformed quote/UTF8/oversized field, strict ID/price/time/action tokens, existing DB refusal, post-snapshot source substitution, guarded failure/no retry, primary cleanup failure and post-persistence DB mutation. No actual archive or model is needed.

These tests demonstrate kernel mechanics on tiny data. Independent substantive review, fresh-process outer owner/resource telemetry and full source/bootstrap handoff remain required before public reproduction instructions advertise a real runnable import command. Existing `eda.py` and all historical source/collection/model consumers remain unchanged.


## V1 parser disagreement and V2 repair

Independent tiny review found a real silent text change: Python strict CSV parses the unquoted brand spelling ` "x" ` as that exact text, whereas DuckDB interprets it as `x`. Row/action/NULL/time aggregates did not detect this. Original v1 files, failing tests and logs remain preserved. V2 makes the Python dialect authoritative and streams every validated row to an all-fields-quoted canonical CSV before native import. The raw decompressed identity remains separate. Canonical bytes/hash and reader policy appear in `validated_csv` evidence and are rechecked after persistence. This preserves the permitted value rather than silently changing or discarding it.

The extra canonical file/write/hash/read cost is paid and explicitly recorded. Raw snapshot/spool plus canonical spool are data artifacts, separate from the engine's spill setting;8GiB spill is not a total disk limit. A future owner must account for all those files and its full native/exittail lifetime. Regression covers the original space/quote value, quotes/newlines/Unicode/nonempty NULL strings and late canonical-file mutation. No actual source has been imported by this repair.
