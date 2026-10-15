# Independent resource/output subreview — frozen six-role v2

No supported actionable findings in the resource/accounting output scope. This is a read-only review of existing synthetic outputs, not another execution or general capacity acceptance.

## Frozen inputs and verification

Reviewed manifest: `/tmp/tlab-six-role-v2-independent-output-review-inputfreeze.json`, SHA256 `76ee1f53917bf37a3153f09c48b615ce978f7f377f98434bddc170326037e321`. Read mapped snapshot bytes only. All 236 captured files match their manifest SHA256 and byte sizes. This verifies captured identity, not substantive review of all 236 files. The manifest SHA was rechecked unchanged at the end.

Substantively inspected frozen raw setup/integration external timing and stdout logs, Root external lifetime receipt, operation receipt, harness freeze/proposal/plan/run instructions, setup/integration supervision, consumption/setup result, integration result and harness ledger, six worker receipts/reaped records, and relevant static supervisor/controller accounting code. All 138 integration evidence fingerprints also resolve to matching frozen bytes. Used only Python standard-library byte hashing, JSON/regex parsing, arithmetic and static text reads. No project import, execution, SQL, backend, native call, model operation or harness test ran. An initial convenience source-line printing range exceeded EOF; this read-script error was corrected and the final bounded pure verification exited 0.

## Resource evidence

| Stage | External wall (rounded seconds) | External user + system CPU (rounded seconds) | Conservative CPU rounding upper | External MAXRSS (bytes) | Sampled aggregate job peak (bytes) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Setup | 0.60 | 0.39 + 0.10 = 0.49 | 0.51 | 127008768 | 158744576 |
| Integration | 3.92 | 2.72 + 0.53 = 3.25 | 3.27 | 159268864 | 295141376 |

Raw timing logs have all 18 captured Darwin timing lines, including the closing peak-memory-footprint field, and no timing/sysctl error. Exact raw-log/stdout pins, freeze/operation pins, supervision pins, model/setup outputs, integration output and harness-ledger pins match the Root receipt. Each external stage is below the frozen 60 CPU / 120 wall ceilings, including rounding allowance. Sampled aggregate peaks are below setup 1 GiB / integration 2 GiB thresholds. The receipt keeps external MAXRSS separate from sampled aggregate RSS and retains sampled-not-hard-limit disclosure.

External full-stage totals are charged once: 3.74 rounded CPU seconds and 4.52 rounded wall seconds. No role CPU is added again. Internal conservative CPU upper bounds are separately named: setup 2.497457, integration 5.250048, total 7.747505 seconds; these include the unmeasured tail reserve and are not relabeled exact actual cost.

All six reaped records declare original exit0. Their CPU sum equals controller reaped-child CPU 2.684751 seconds. Controller SELF 0.462176 plus those children equals its intermediate total 3.146927. The outer integration wait4 boundary is larger at 3.171571 seconds and its observed supervisor-inclusive CPU is 3.250008 seconds, consistent with the later inclusive boundary. Setup wait4 child CPU is 0.438197 seconds versus intermediate builder CPU 0.403475. Internal SELF values differ by 7/10 microseconds across separately captured snapshots; frozen supervisor lines 574/583 explicitly take separate reads, so exact algebraic equality between those snapshots is not required.

Both stage receipts show normal reaping, exit0, no errors/intervention/terminal survivors and unknown_active_work=false. They preserve actual_total_cpu_seconds=null and supervisor_exit_tail_measured=false. The harness ledger preserves exact_supervisor_exit_tail_measured=false. Its full_owner_exit_tail_verified=true refers to the reaped controller boundary (controller lines 396–426); Root external_full_supervisor_exit_tail_verified=true remains a separate later claim. Setup/integration flags consistently retain one eight-row synthetic setup fit, zero study fits, W=B, historical stub/self-issued gates, and no chosen3/bootstrap/quality/production-resource claim.

## Evidence limits

Parent supplied actual reaped tool chunks setup `39b20a` and integration `ec7144`, each exit0. I can cross-check that these are the identifiers recorded in the frozen Root receipt; a JSON file or timing log alone cannot authenticate execution-tool history or Root’s intervening setup acceptance. External lifetime closure is supported only together with that parent-supplied actual terminal evidence. Rounded external timings do not provide exact microsecond lifetime cost.

No native/backend rerun was performed. Sampled RSS/process discovery does not establish a hard aggregate-memory ceiling, unique physical-memory use, arbitrary descendant containment or capture of never-observed orphans. Success remains isolated synthetic shared-runtime B-only integration; it proves no real reserved-source/fullY access, historical 438/439 authentication, fresh environment/bootstrap, chosen3 native integration, full production capacity or recommendation quality.
