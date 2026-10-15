# MAIN018 independent actual full-source output review

**No supported output finding within the authorized typed9 source-prefix scope.** The original full-source worker and owner completed exit0; this independent byte/metadata review also completed exit0. The retained outputs are eligible for Root's source-acceptance decision. No acceptance flag or original report was rewritten.

Root's import terminal evidence is session65471/chunk`a5ea08`, exit0, bound by `/tmp/tlab-root-full-source018-external-lifetime-receipt.json` SHA256 `6418c99510bd993a85afe11e31c787798adcd7d0aa79b4939a4eb516f9726b62`. Review terminal evidence is session82476/chunk`7b56f2`, exit0. The first review submission timed out in automatic permission approval before process creation; verified absence of cache/log/ledger files preceded the permitted exact retry. Only that retry read the large files.

## Actual byte pass and freshness

Small metadata was frozen before semantic and large-file checks in `/tmp/tlab-full-source018-independent-output-review-inputfreeze.json`, SHA256 `f2e70cbce743cdaa2d7ab2e473be4251d9f8d00aac51a9073f8fe08acc1faaff`. The scope contains32 small metadata/source files and five distinct large physical files. No large file was copied.

The review read **17,094,598,000 large-file bytes**, once per physical device/inode, with63 later cache hits and no second large read:

| Existing file | Bytes | SHA256 |
| --- | ---: | --- |
| new `kernel/events.duckdb` | 1,509,437,440 | `4168068b05a5f7033876c05427037732322abe77fd2f97eef3ceca59d42ba786` |
| raw `kernel/source.csv` | 5,668,612,855 | `fedd938409b5f836ec89b39c861b13dad99fc7cd9beb1fddd97a2d50488b5b80` |
| owned `kernel/source.csv.gz` | 1,741,928,540 | `8ebca1ad741295297368f2cf0315e3f36853a1a11768fb16babf8c9b83838147` |
| canonical `kernel/validated.csv` | 6,432,690,625 | `e58ae129792ed9ce848644343d75698a506c0c2bcc5b2da6a30db283e85db4c2` |
| original `data/raw/2019-Oct.csv.gz` | 1,741,928,540 | `8ebca1ad741295297368f2cf0315e3f36853a1a11768fb16babf8c9b83838147` |

All hashes and sizes match the request, kernel evidence, worker output map and owner fingerprints. The original gzip and owned snapshot have separate inodes and identical bytes. The new DB is bound to this consumed run's fixed output path; the historical DB was not opened, hashed or compared.

The cache records37 physical files, each with one original hash acquisition. Final freshness compares device/inode/size/mtime/ctime against the frozen and hash-time states, rather than rereading the large files. All37 states and the output namespace remain unchanged. No failure marker, claim failure, WAL or retained spill file exists. Worker spill evidence remains retained_files0/retained_bytes0 with peak_measured=false.

## Complete owner, worker and kernel association

The staged request stays SHA17edb3954caed6cd409765e870ef8ec547bfc407e30f0e47f5d1df92f553219c and execution id `oct2019-full-018-20261015-once`. Its exact18-entry owner fingerprint closure was independently reconstructed and checked, including17 nested reference checks and37 fingerprint/output/Root-metadata checks. Request, exclusive claim, issued context, worker consumption, kernel consumption, worker receipt, reap boundary and owner report agree on the original namespace, identity, source profile and paths.

The unchanged owner5df50bb2…, kernel7d7ed34b…, driver3f28305f… and V6 supervisor449d9875… match their issued pins. The process receipt binds the exact isolated/no-pyc owner CLI and expected request SHA. The worker's fixed context/claim/request associations, original owner PID, start/finish/reap clocks and absolute deadline are consistent. All clocks lie in the original lifetime. The recorded worker reaped exit0/owned-group-gone boundary and actual590.733361s inclusive worker CPU bound the worker's583.883824s receipt. Parent/outer CPU observations are ordered nested cross-checks, not extra charges.

The original episode remains7200CPU/10800wall, outer7190CPU/10790wall and8GiB sampled job RSS. Worker allocation is7182CPU,7GiB RSS and original deadline minus10s cleanup reserve. Its actual kernel fence is soft7181/hard7182. Runtime evidence agrees with the unchanged lock: Python3.12.14, DuckDB1.5.6, Darwinarm64, two threads,2GB engine memory and8GiB spill setting. No runtime/model/bootstrap operation was performed by this review.

Worker/owner/kernel report fit_attempt_count0 and labels_created=false; worker descendants CPU0. Existing source_acceptance_issued=false, worker_complete_unaccepted, completed_source_import_pending_external_source_acceptance, kernel pending-source-acceptance and internal full-exit requirements remain unchanged. The external driver's nested-ledger/source-acceptance/full-exit-acceptance flags remain false; its original exit-tail-measured flags remain false/null.

## Typed source and original EDA aggregates

The authenticated schema has all nine original ordered fields: event_time TIMESTAMP, event_type VARCHAR, product/category/user keys BIGINT, category_code/brand/user_session VARCHAR and price DECIMAL(12,2). The source profile is the fixed project-observed October2019 identity, not a publisher-signed checksum.

The actual kernel summary agrees exactly with the original bounded EDA `artifacts/eda-october/run.json` and `quality.json` for:

- **42,448,764 rows**:40,779,399 view,926,516 cart,742,849 purchase.
- Time range2019-10-01T00:00:00Z through2019-10-31T23:59:59Z; original EDA reports zero outside-month/unknown-action rows.
- NULL counts: category_code13,515,609; brand6,113,008; user_session2; all other fields0.
- Original compressed identity/size and full raw-spool byte count.

The accepted pinned kernel code strictly validates each raw CSV token under the typed9 contract, emits its validated token stream using QUOTE_ALL, and directs the explicit native typed reader to that canonical file. Existing evidence records native_reader_used=true, all-fields quoting and Python_csv_strict. Native schema/count/action/NULL/min/max conformance is checked against the Python summary in that code path; the canonical witness and new DB bytes now match the independent hashes. Gzip complete-member EOF/CRC/ISIZE validation is recorded by the accepted kernel; the review did not repeat decompression.

**This review does not independently compare every DB cell or the complete DB bag to raw source.** Its acceptance basis is exact byte binding plus the accepted strict kernel validation and native schema/aggregate conformance. No DB connection, SQL, gzip decompression, independent row oracle, model, fit, queryY or evaluation was run. Full-month raw purchase events are source data, not a constructed query target/evaluation grant. Fresh-environment reproduction and complete018/model/history bootstrap remain unproven; they do not block this narrowly defined source-prefix review.

## Actual review cost and retained resource limits

The review installed a kernel CPU fence soft179/hard180 before any large read, a295s wall alarm and165CPU/285wall persistence guards; sampled self RSS was guarded at1GiB. Full external review timing was **7.92s wall,5.74s user +2.15s system =7.89s rounded CPU**, conservative rounding upper7.91CPU/7.94wall. External review MAXRSS was34,799,616B. Internal final observation was7.890286CPU/7.885376wall and34,766,848B peak before exit; these are separate measurements. The actual terminal0 closes this review process.

The original import's retained external timing remains586.10s wall/609.87s rounded CPU, plus staging0.02wall/0.01CPU. Its combined Root upper609.92CPU/586.14wall and conservative622CPU prefix are unchanged. Adding this review's7.91CPU upper gives629.91CPU against7200; nested worker/owner/supervisor CPU is not added again. Import external MAXRSS1,915,109,376B stays distinct from sampled aggregate peak1,944,485,888B. Sampled RSS is not a hard aggregate-memory guarantee.

The original source acceptance decision belongs to Root. No native job was repeated, no helpers were spawned, and the review wrote only temporary review artifacts. The actual ledger, cache, final freeze/freshness and raw time log preserve these bounds and limitations.
