# Independent forensic review: existing chosen3 W44 v3 worker outputs

**The existing six worker outputs are consistent within the synthetic R2/L05 scope. The whole operation remains FAILED, consumed, external exit1.** This is read-only forensic acceptance of retained worker artifacts, not promotion of the outer harness, a replacement success receipt or a new job grant.

The immutable Root failure receipt is SHA256 `d32348f7a3831216aa2efdac8c22da53216cc53f696c7dd349f351ef645ed789`. Its external terminal chunk `e70f0b` reports exit1. The retained controller traceback identifies `TypeError: dict() got multiple values for keyword argument 'metric_delta_required_nonzero'` in candidate v3's terminal `verify_results` return. That key occurs in DISCLOSURES and again in the constructor. All six workers had already completed, but no `integration-result.json` or `harness-ledger.json` was created. Both `integration.failed.json` and `integration-supervision.failed.json`, the failed supervision record and their original `unknown_active_work=true` flags are preserved. The workers' own `role_complete_unaccepted` and owner `verified_reporting_pending_external_lifetime_acceptance` states are also preserved.

## Frozen bytes and authenticated workers

Snapshot: `/tmp/tlab-chosen3-v3-worker-output-review-inputfreeze.json`, SHA256 `92742e9f3eb5f14a922b0086ed7cf3619e7a3b37a02f5dfdbca4d3a3de5bcb75`. It freezes239 existing files, including all189 regular files in `/tmp/tlab chosen3 W44 integration 20261015`, exact v3/base/supervisor/public source, four raw external log files and six explicitly referenced original synthetic B provenance/model files. All239 initial/final hashes and the189-file namespace match in `/tmp/tlab-chosen3-v3-worker-output-review-finalfreeze.json`; the sole shared `.venv` symlink is unchanged. The scope was completed before semantic checks; the initial narrower manifest is separately retained.

Candidate v3 stays `b40060a970546ea749291695bd60585b06ad7f1facdbf2388e6bfb1371f43a6d`, draft freeze `fc3a44a40b00b90dc0df7ddff0a5492772d3bfb802533a9523fb439c81737c8e`. The copied31 public dependency/config files match the frozen project bytes and copy receipts. No V4 source was inspected or substituted.

Recursive authentication checked149 unique file pins,544 reference occurrences and1063 fingerprint/output-map occurrences. Request/claim/proposal identity, lock, model/source refs, six contexts/slots/launches/consumptions/receipts, worker logs and reap boundaries agree. Each role uses its exact fixed public CLI entry and issued context SHA; slots keep ordinals0–5. All six reaped exit0, first four labels=false, last two labels=true, all six fit=0 and descendant CPU=0. Only predictions and prediction_oracle have native calls:10 each, exactly2×five nonempty-C dates. All worker logs are empty, role failure markers are absent, and original issue/start/finish/deadline clocks are ordered.

Four exact gate closures were independently reconstructed: initial51 pins, source96, prediction129, target131. They retain the fixed role order and disclosed self-issued synthetic authority. Producer and independent metric target/fullY UTC clocks follow both seals strictly, and their monotonic clocks lie inside their original receipt lifetimes. No historical439 authentication is established by these gates.

Synthetic DB SHA256 `2ecaa23045ef2f534221f648e2f297645d29322ba2c1b9abdb08e4d2c98182c1` is bound to all source users. It was byte-hashed only. Reused B CBM remains `fd9254c9d4d165c32d533cec07ddbfea3aba98f1137c169ba445fe5c5baf915a`, exactly matching its original synthetic source; copied original B spec is byte-identical. New W CBM is `4cf91160b5f4405f4c7ae1f3a55b689e0774079db892ffad6abade693312f654`. The locked specs/producer descriptors bind B41 and W44 with the identical first41 feature order, exact three L05 suffixes, common captured effective parameters and prefix300. Models and B/W score artifacts are distinct. CBMs were never deserialized or scored by this review; actual native-state/replay evidence comes from the authenticated unchanged worker code and its existing receipts.

## Independent source, score and metric reconstruction

There is no source-events JSON in this root. The independent fixture uses eleven typed literal events, separately transcribed and checked against the exact frozen base `toy_events` AST. This proves the expected fixture's provenance; it does not independently inspect DB table contents. DB/source behavior is supported by its byte pin and the six worker/source-oracle records, without new SQL.

All seven saved Q/C domains were checked against that fixture. Q counts are `[1,2,3,2,3,2,0]`; C counts `[0,3,6,4,7,5,0]`:13 queries/25 candidate pairs. Day25 retains its eligible positive with empty C, while day31 retains empty Q/C. Exact integer IDs, including values beyond floating-point precision, stay in typed int64 transports.

A small bounded reader hand-parses existing flat Parquet CompactProtocol/plain/RLE pages using Python3.14's standard `compression.zstd`; no parquet, SQL, inference or model library is imported. It directly checks all75 exported chosen scalars and all seven extra schemas/key domains. The expected values use distinct non-null users and strict-past windows: item view24h, cart168h, purchase24h. All actual saved values match:

| Selected field | Distribution over25 actual C rows |
| --- | --- |
| item view distinct users24h | zero20, one2, two3 |
| item cart distinct users168h | zero18, one7 |
| item purchase distinct users24h | zero17, one8 |

The source oracle's per-day/global3×C totals, chosen_columns3, exhaustive selected-formula flag, mismatch0 and `all_selected3_values_every_C_row` agree. B18 remains explicitly sampled/nonexhaustive. The reader is temporary forensic tooling for these existing tiny artifacts, not a project dependency or general framework.

All14 existing B/W NPZs were decoded with `zipfile`/`struct`, verifying typed all-Q/user/anchor/maturity/group/item/finite-score vectors and identical B/W Q/C domains. Every raw-score-derived deterministic ranking matches all26 existing B/W JSONL rows. W has two distinct raw scores, approximately−2.308331823 and+2.308331823. All25 B/W score pairs differ, and two query rankings differ. These are observable transport differences, not evidence of improved recommendations or a new native replay.

The actual saved full-target Parquet contains exactly two distinct pairs and equals the independent fullY fixture calculation. Duplicate anchor purchases deduplicate; the Day25 target remains unretrieved, and the final window has one retrieved target. The decoded Q/C/extra/target exports and NPZ/JSONL keys close exactly.

All64 recall/NDCG/AP/RR scalar fields under four estimands/two models/two windows, and all1600 paired-user bootstrap draw values were independently recalculated from the retained rankings. Producer, metric oracle and owner aggregates agree. All eight W−B NDCG estimates are zero even though some rankings differ. Final conditional query/user estimands retain67 null draws each and133 defined zeros; other cases retain200 defined zeros. No undefined draw is replaced. This supports actual synthetic worker arithmetic only.

## Failure cost and retained boundaries

| Stage | Exit | External rounded CPU | External wall | External MAXRSS | Sampled aggregate RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| W setup | 0 | 0.55s | 1.05s | 127,418,368B | 159,432,704B |
| Integration | 1 | 3.53s | 3.84s | 160,972,800B | 298,467,328B |

The additional attempt consumed **one new eight-row W44 fit, zero new B fits and zero study fits**, plus the six existing roles. Inclusive external totals charge4.08 rounded CPU seconds/4.89 rounded wall seconds once; role CPU and internal child subtotals are cross-checks, not extra addends. The original paid B fit is not charged again. Raw external time logs agree with Root receipts; authenticating the actual terminal tool history remains Root's responsibility.

Resource observations remain below the finite60CPU/120wall and1/2GiB sampled limits, but failure is still failure. External MAXRSS remains distinct from aggregate sampled RSS. Internal exact-tail fields stay null/false; integration supervision stays `failed_unknown_cleanup` because exit1, with unknown_active_work=true. Its observed terminal survivor list is empty; that does not justify rewriting the flag or promoting the operation. Sampled RSS is not a hard aggregate-memory fence, and production capacity is not proven.

## Executed review and limits

The final bounded pure checker passed in0.098292 CPU seconds/0.124701375 wall seconds. It used only existing frozen bytes, stdlib arithmetic/decoding and temporary reviewer files. No worker, native fit/predict/load, database connection/SQL, historical consumer, claim/grant, network/API, new root, real data or project write occurred. No helpers were spawned. Initial reviewer tooling assumptions about the standard decompression API, empty Parquet footer boundary and original-B-relative reference context were corrected before the final passing check; no stored worker evidence or actual failure was altered.

Machine ledger: `/tmp/tlab-chosen3-v3-independent-worker-output-review-ledger.json`. Raw checker log: `/tmp/tlab-chosen3-v3-independent-worker-output-checker.log`. The scope remains existing synthetic R2/L05/shared-runtime workers. It provides no real016, historical, fresh-environment, capacity, scientific-quality or whole-harness success claim.
