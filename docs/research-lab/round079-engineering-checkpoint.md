# Инженерный checkpoint: волны 078–079 и исправление метаданных

SOURCE-срез 2026-10-16 20:11:51 UTC. Исправление принято по исходному коду и CODE-проверкам; локальная установка этого пакета ещё не разрешена и не выполнена.

Воспроизводимый конвейер и полный повтор на Mac работают. Финальный NDCG фиксированного сравнения составил 0.459825 для B и 0.464947 для W; доверительный интервал разницы пересекает ноль, поэтому надёжный выигрыш не установлен. В проекте принято 14 из 19 задач, четыре optional эксперимента отложены. Адаптивное число деревьев исследовано отдельно на повторно использованной validation; это не новое подтверждение качества.

Точный коммит 476dfd65fa46178956486ea791eba23cbf404cfd опубликован в закрытой research-ветке, описание draft PR №1 обновлено и фактически принято Root. Это выполненное разрешение не распространяется на позднейшие локальные коммиты, данный пакет или будущий push. Прежний один native CLI attempt завершился ошибкой до подготовки матрицы и входа в fit: child 23.271678 CPU / 23.609122 wall, exit 1, reaped, без timeout. Сохранённый консервативный CLI-счётчик равен нулю, независимые native-счётчики недоступны. Разрешение 50 CPU / 65 wall использовано и закрыто. Native CLI с исправленной версией и callback-abort ещё UNRUN; новый native-бюджет не выделен.

## Исправление и фактическая CODE-приёмка

В helper сохранён прежний legacy-формат по умолчанию. Явный kernel-вариант, не требующий lazy subprocess в platform.platform(), выбирает только development CLI; исторические потребители остаются на legacy. Четыре точных публичных кандидата — train_baselines.py, train_development.py, существующий test_train_development.py и новый test_environment_snapshot.py. Они проверены тремя независимыми SOURCE-review; сами проверки приведены ниже дословно.

Root принял итог V4: 12 уникальных unit-методов обычного CODE-прогона прошли без fail/error/skip, все обязательные терминальные защитные assertions прошли, application denials и application process/network events равны нулю, actual load-runtime calls равны нулю. Child reaped; CPU 0.33142 s, launch-to-reap wall 0.382212583 s. Это фактическая orchestration CLI/helper на synthetic model/selector/data doubles и настоящем NumPy; environment helper в этом прогоне stubbed. Python 3.12.14 / NumPy 2.5.4 описывают среду CODE-проверки, а не доказательство совпадения с lock.

Отдельный публичный stdlib-тест проверяет AST извлечённого настоящего helper с version doubles: kernel-путь без запрещённых событий, холодный Darwin legacy/devnull witness, dependency-mismatch проверки. Он даёт ещё один уникальный метод. Итого 13 уникальных CODE-методов, а не сумма повторных запусков. Ранние V1–V3 завершились ошибками guard/harness, сохранены как ошибки и не засчитаны дополнительными успешными тестами. V4 принят по raw report, receipt, полному stderr с 12 OK и свежести исходников; это не native/данные/модель/quality доказательство.

Четыре изменённых source-файла меняют provenance: старые pins 120-file native worker нельзя повторно использовать для исправленного CLI. Исторический helper flat-eight toy сохраняет прежний ограниченный смысл и не доказывает native-интеграцию исправленного CLI. Любой будущий native attempt потребует свежего фактического source binding и отдельного разрешённого конечного бюджета; сейчас такого разрешения нет.

## Принятые исследовательские выводы

Волна 078: три независимых FIRST, затем отдельный скептик; Root NEW 0 / REFINE 2 / MERGE 1 / ADMIT 0. Уточняются существующие направления поддержки CLI: event-first выбор до нормализации путей и ограниченная terminal-диагностика без повторного рабочего check. Кэш классификации не заменяет проверку изменяемого namespace/ROOT/caller. Доля observer в фактических 23.271678 CPU-секундах неизвестна; ускорение, достаточность бюджета и будущие dispatcher/terminal-oracles не проверены. Будущие свидетели UNRUN, стоимость UNKNOWN, бюджет не выделен.

Волна 079: два независимых FIRST, затем новый скептик; Root NEW 0 / REFINE 2 / ADMIT 0. Дополнительного обязательного пробела в принятом ограниченном Task1 не найдено. Генерация определений, replay на 12 синтетических входных строках и полный Mac-повтор — разные слои доказательств, не подтверждение сдачи, оценки или завершения общей цели. Адаптивные B1189/W403 выбраны на повторно использованной validation с 73 положительными запросами и 2400 зависимыми проверками. Selector выбирает самый ранний prefix в абсолютной полосе 1e-12 от наблюдаемого глобального максимума. Это не независимое улучшение, точный максимум без допуска или экономия обучения: обе модели обучены до 1200.

Исходная сетка сохранена: 078 due 18:45, контекст 18:53:02.950493 и верхняя граница dispatch 18:53:54.070609; индивидуальные старты неизвестны. Для 079 due 19:30, Root authors-readback 19:31:20.741576. Сохранённая исходная точка — 20:15 UTC; более поздний live dispatch этим срезом не проверялся. Операционные диагностические авторы не считаются исследовательской волной. Новых IDs, задач, обязательных gates, научных экспериментов или grants нет.

## Форма сохранения и ограничения плана

Это один сводный отчёт вместо новых raw-archive файлов 078/079. Ниже дословно включены семь безопасных FIRST/скептических текстов и три SOURCE-review текста, затем два Root-disposition JSON и новая Root CODE-adoption. Их исторические статусы читаются по собственным cutoff: прежнее UNRUN полной suite не отменяет более поздний принятый результат выше. Все 13 встроенных оригиналов сохраняют точные bytes/SHA; source-pin/freezes/context identities даны компактной metadata-картой.

Тела private worker/guard/control/stdlib/source-inputs, policy/skill, grants, человеческих ответов, данных и моделей исключены; их пути/SHA могут присутствовать только как references. TMP-оригиналы остаются привязанными по SHA. Отдельные canonical raw-archive пути для 078/079 не заявляются. Полные отчёты guard-прогонов и control runners не копируются: безопасная Root CODE-adoption ниже сохраняет итог и их exact references.

LOCAL40 V1, первоначальный отказ LOCAL36 и его zero-write readback сохранены. Новый показанный план содержит ровно 41 путь: прежние 40 и этот отчёт. У четырёх current docs добавлен датированный префикс, весь прежний candidate body сохранён. Фактического согласия на LOCAL41 пока нет: install, stage, commit, escalation и внешняя публикация не выполнены. SOURCE-проверки и будущий нормальный staged whitespace check различаются; последний ещё UNRUN. Старые научные пределы, фиксированный report, deadline и одна очередь/один владелец сохраняются.

## Полные исходные тексты

### Волна 078: tlab-wave078-observer-a-FIRST.md

Источник: `/tmp/tlab-wave078-observer-a-FIRST.md`; SHA256 `a0c85b9ba5b06f3957f7862316abd8af12af80a9b2af8ff1587e10bd76aae7fd`; 2634 bytes.

````markdown
# Wave 078 — observer cost, independent FIRST

Source facts (80 words): The private worker resolves each callback frame’s filename before checking its event; only call/return branches use the result (worker L178–214). Profiling surrounds `runpy.run_path` (L394–405). Deferred module/source/ROOT verification is separate, including immediately before native getters/fit (L136–146, L225). [Python 3.12 sys.setprofile documentation](https://docs.python.org/3.12/library/sys.html#sys.setprofile) lists Python and C call/return/exception events; tracing is suspended inside a profiling callback. The fetched documentation identifies 3.12.15; it is not runtime evidence for installed 3.12.14.

Mechanism: callback-wide path normalization pays work for unrelated Python frames and C events that none of the subsequent branches consume. This is event-volume amplification, without recursive profiling of the resolver itself. It could increase pre-fit CPU expenditure; the share of the actual approximately 23 CPU seconds is UNKNOWN, with no event counters or phase measurements.

Prediction: an event-first dispatch can skip all C events; a lazy CLI-identity check can avoid resolution on other irrelevant frames. Preserve forbidden-call checks and exact original-fit code identity on every Python call, plus all selected return observations and independent source/ROOT checks.

Counter: the actual failure occurred on the reported metadata/subprocess guard path before preparation/fit. Observer work may be small relative to legitimate import/metadata work; resolving fewer paths does not establish budget adequacy or repair that guard failure.

Minimal future native-free oracle, not executed: paired dispatcher evaluation over fixed fake-frame/event records, with a counting resolver sentinel. Include unrelated Python calls/returns, all C events, selected helper returns, genuine CLI candidates, and same-name wrong-file CLI candidates. Baseline must request one resolution per record; candidate must avoid irrelevant resolutions while preserving actions, counts, and rejections. Equal resolver counts falsify the proposed reduction; any behavioral difference rejects the optimization. No timings or project/native imports are needed.

Budget: UNKNOWN and unallocated; the fresh 50/65 attempt is consumed CLOSED, without retry/residual authorization. Benefit: cheaper trustworthy CLI validation supports the original automated-feature and chronological future-purchase baseline. Dedupe: adaptive/development-training/CLI support and continuous TLAB014 refinement, with no new gate, scientific-gap, quality, or acceptance claim.
````

### Волна 078: tlab-wave078-telemetry-b-FIRST.md

Источник: `/tmp/tlab-wave078-telemetry-b-FIRST.md`; SHA256 `d97ea5c0d02700ab047c38ff24907ea89fa2b1f18465e342d7b7484921a192be`; 2695 bytes.

````markdown
Wave 078 B — blind FIRST; SOURCE inference only.

Source facts: Worker failure-writing reuses `write_new`, which calls the CPU<22 work check; its secondary exception is swallowed before bare re-raise ([worker](/tmp/tlab-native-cli-tiny-native-e2e-worker-proposal-v2/run_native_e2e.py:433), lines 61–64,112–120,433–439). CLI failure handling retains its conservative helper-attempt counter ([CLI](/Users/mdpospelov/tlab-recsys-2026/scripts/train_development.py:224), lines 155–156,194–196,224–236). Actual evidence records primary ValueError, CLI counter 0, missing worker receipt and unavailable observer counters ([failure](/tmp/tlab-root-native-cli-tiny-native-e2e-actual-failure-v1.json:27), lines 27–55). Runner starts cached calls at null and captures primary separately ([child](/tmp/tlab-native-cli-tiny-native-e2e-runner-proposal-v1/child.py:105), lines 105–114,158–202).

Mechanism/invariants: Requiring unused work budget before failure emission makes exhaustion erase telemetry. A proposed one-way work→terminal transition should freeze only cached primitive counters and primary identity; native getters, retry and subsequent work remain forbidden. Distinguish conservative CLI helper attempts from observed forwarded/original calls. Missing observations stay null with provenance. Secondary reporting/cleanup failures must never replace primary. Minimal terminal emission should avoid the work check, dynamic error formatting, new hashing/inventory and success validation; unperformed verification stays unknown. A bounded preopened sink still needs finalization resources reserved prospectively inside an authorized total allowance; exhaustion creates no extra allowance.

Prediction/counter: An exhausted-work sentinel failure should retain the same primary and cached counts while rejecting new work. A hard kill or unavailable sink can still prevent output; consumed markers plus missing=unknown remain necessary, and absence never implies zero or success.

Near-future oracle: Specify an isolated Python-only harness with fake expired clock, sentinel primary, raising formatter/sink/cleanup and booby-trapped work/getter hooks. Require zero hook calls, unchanged primary identity, counter snapshot fidelity and bounded terminal attempts; inject sink failure and verify unknown reporting. Not executed; budget UNKNOWN/unallocated.

Benefit/dedupe: Better diagnosis and no false count claims, within existing CLI validation/development support and continuous TLAB014; no new scientific gate. The one 50CPU/65wall attempt is FAILED/consumed/CLOSED, with no retry or residual grant. Exact476 publication is fulfilled. No repair or runtime acceptance claimed.
````

### Волна 078: tlab-wave078-provenance-c-FIRST.md

Источник: `/tmp/tlab-wave078-provenance-c-FIRST.md`; SHA256 `543e7cbba9b13f33a8823f70050de0350afa92e2875e87c701f72c43633005ce`; 2750 bytes.

````markdown
# Wave 078 C — independent FIRST

Source facts. Worker:178–213 resolves frame filenames before dispatch; CLI counts require filename, module and name. Worker:136–146 checks module set, path/hash and ROOT; 217–260 checks caller and live CLI namespace before its getter inspection/forwarded fit. Public CLI:194–196 increments its conservative attempt count before helper entry; public helper:35–37 already calls getters earlier. The actual failure receipt records failed/attempt-count0 and unavailable observer counters. [Python 3.12 documentation](https://docs.python.org/3.12/library/sys.html#sys.setprofile) includes C events and exception returns with None. Sources and actual read scope are pinned separately.

Mechanism/inference. Rejecting irrelevant event types before filename resolution can reduce classification work. Any code-object filename cache must remain classification, not cached acceptance of mutable globals, ROOT or route. Preserve forbidden-call checks, exact original-fit code accounting, successful-return observations and exception handling. Retain full module/source/ROOT checks, immediate helper→CLI frame chain, live __main__ namespace identity, run-code/global ownership, and Prepared/Pool/callback identity before the forwarder's getters/original fit. Final counts cannot replace this temporal boundary.

Adversarial witness. An unexecuted descriptor with `__name__='__main__', co_name='run', co_filename='elsewhere.py'` must not acquire CLI credit through a module/name cache, in either cache-fill order. Stronger counterexample: canonical CLI code reused with a separate globals dictionary retains filename/name but fails live namespace ownership. Matching path/hash does not prove that disk source supplied every executed function or external dependency.

Prediction/counterhypothesis. A correct optimization preserves both rejections and route failures while reducing irrelevant resolutions. A pure event guard may already satisfy this; no speedup magnitude, phase-cost share or current hostile-code containment is established.

Minimal future native-free oracle, NOT RUN: a literal decision table for authentic, wrong-file and separate-globals rows, both cache orders, wrong ROOT, broken caller chain and exceptional return; require unchanged count/route decisions and rejection before a marked getter boundary. No project imports or native objects are needed for that proposed oracle.

Benefit/dedupe. This refines existing development-training/CLI validation support and continuous TLAB014; no new scientific gate. Budget UNKNOWN/unallocated. The 50/65 attempt is FAILED/consumed/CLOSED; no retry/residual/new grant. Exact476 publication is fulfilled. No runtime acceptance or budget-adequacy claim.
````

### Волна 078: tlab-wave078-skeptic-v1.md

Источник: `/tmp/tlab-wave078-skeptic-v1.md`; SHA256 `5ac30a63808132b58c7afeed21b25f2ca188b7ac4b27d2b5923e8a28ce5c92c1`; 3202 bytes.

````markdown
Wave 078 distinct skeptic — SOURCE only, after all three FIRST freezes.

Bindings pass: common context, Root readback and all nine author artifacts match their pins. FIRST counts A/B/C are 327/296/327 words; source-fact paragraphs are 70/65/79, within 350/100. A labels its paragraph “80 words”; this harmless count discrepancy does not breach the cap. Declared blind scope and freeze order are consistent; hashes do not independently prove authors' prior reading history.

A/C identify real unconditional filename resolution before event dispatch (worker 178–213), a plausible overhead mechanism. Neither has measured its share of actual 23.271678 CPU seconds or demonstrated budget adequacy. Recursive callback profiling is not the default: the [official Python page](https://docs.python.org/3.12/library/sys.html#sys.setprofile) describes the shared tracing mechanism and disabled tracing during callbacks. Current 3.12.15 documentation is not installed 3.12.14 runtime evidence. Skipping C events must retain every forbidden Python-call check, exact original-fit code accounting, selected returns and exception handling. Cheap classification must never cache mutable namespace/ROOT acceptance.

The strongest weakness is the proposed oracle. A's fake records can falsify resolver-count reduction, conditional on actually exercising the dispatcher; they cannot establish live profiler/call-chain behavior. C's literal decision table is a specification, not executable evidence of rejection before getters. Wrong-file and separate-globals rows are useful adversarial requirements, but hand-assigned expected results would merely restate the design. Any separately authorized future oracle must exercise the checked seam and challenge cache order, mutated globals/ROOT, broken callers, exceptional returns and observer errors; otherwise rejection timing remains UNKNOWN. All oracles are UNRUN, cost UNKNOWN/unallocated.

B's work→terminal proposal correctly avoids treating exhausted telemetry as zero counts. Current write_new calls check(), while the runner's finally still hashes/inventories sources. A future bounded terminal path needs prospective reserve inside its authorized total, cached primitive snapshots with null provenance, bounded sink attempts, no work/getters/hash/retry and no replacement of primary by formatter/sink/cleanup failures. A preopened sink guarantees neither completion nor survival of hard kill. There is no free cleanup allowance.

C correctly limits full checks to before the forwarder's getters/original fit (worker 217–261). Public helper 36–37 already calls is_fitted/get_params; do not generalize this to all getters. Actual failure preceded Prepared/model/fit: conservative CLI attempt 0 is observed; lost observer counters are not observed native 0.

These are existing development/CLI-support and continuous TLAB014 refinements, not a new main/scientific gap/ID/gate. Actual 50/65 grant is consumed CLOSED; exact 476 publication fulfilled. Metadata-fix V1 CODE proof/source V2 testbuilder is separate, unread work; no repair/runtime acceptance follows. Due 18:45 was delayed to common context 18:53+; next 19:30 original grid remains unchanged.
````

### Волна 079: tlab-wave079-deliverable-a-FIRST.md

Источник: `/tmp/tlab-wave079-deliverable-a-FIRST.md`; SHA256 `1362b7d8cc60e21a54b0894aba49489925edae5cf59f68a0f5053fb31792a481`; 1948 bytes.

````markdown
# Wave079 A — use the existing short demonstration

**Recommendation: NEW0; no additional Task1 evidence gate.** Start with the executed `automation-walkthrough.md`: committed schema/templates generate L02/L06 definitions, an automatic missing flag and B41+3 columns. The adjacent public `manual18-small` ranking replay provides a 12-row synthetic demonstration. Full reproduction already has the accepted TLAB-018 raw→fresh collections→two fixed300 B/W fits→comparison route on a new locked Mac environment; another native adaptive run is unnecessary to establish that original deliverable.

**Mechanism/prediction:** the walkthrough exposes human-bounded generation directly; L02 yields three counts, L06 two core definitions plus a missing flag, with allocation permission false. Ranking replay preserves off-candidate full targets and positive empty candidates. A reviewer can understand the automation and ranking contract without repeating expensive training.

**Counter/claim boundaries:** SOURCE artifacts exist; this review executed nothing. Synthetic CODE/demo evidence does not establish raw-data quality, native training or speedup. Accepted018 provides scoped native/data reproduction evidence separately. The new ordinary adaptive CLI attempt failed before fit; candidate metadata repair and partial FakeML results cannot establish its E2E. Neither path establishes significant quality gain: fixed300 final CI crosses zero.

**Missing fact / nearest future check:** none mandatory for the bounded original Task1. The adaptive CLI's successful native E2E remains an extension fact; do not convert it into a submission prerequisite or request a replacement grant here. Reuse existing walkthrough, report and018 receipts; remove redundant replay/audit work. Future runtime cost **UNKNOWN/unallocated**. Benefit: a shorter reviewable public explanation. Dedupe: TLAB-016/018, ongoing014; no new ID, task or scientific hypothesis.
````

### Волна 079: tlab-wave079-inference-b-FIRST.md

Источник: `/tmp/tlab-wave079-inference-b-FIRST.md`; SHA256 `89b4136b01c67dca244e3c419dfd71ea9cc191e6dab9c69f2c4d22d2cd208499`; 1884 bytes.

````markdown
# Wave079 author B — bounded scientific inference

**Justified statement.** Fixed300 final26–31 reports W−B +0.005122 NDCG with paired-user95% CI [−0.010433,+0.018561]: superiority is unestablished; equality, practical equivalence and absence of benefit are also unestablished. This inference remains conditional on that frozen study and estimand.

Adaptive B1189/W403 are best observed prefixes within1–1200 on reused22–23 validation:73positiveQ,2400 dependent checks. Their respective same-fit300 improvements (+0.001597,+0.000943) describe development selection, not new independent quality evidence. Separately selected W−B0.005438 confounds feature differences with tree counts. Both full fits reached1200; no early-stop savings or global optimum follows.

**Mechanism/prediction.** Maximization over reused, dependent measurements can select favorable noise;2400 checks are not2400 independent replications. Consequently a genuinely prospective comparison need not reproduce the maximizing counts or apparent gains. This is a directional risk prediction, not an estimated correction.

**Counter.** A real small feature benefit and different complexity needs remain compatible with these observations; the CI cannot resolve them. Mechanical reproduction cannot settle that scientific uncertainty.

**Nearest useful check / benefit.** Source-only claim discipline: retain final uncertainty and exploratory labeling when presenting the existing artifacts. Cost UNKNOWN/unallocated; science CLOSED, remainder UNKNOWN. No new comparison is recommended or admitted. Another tree/feature comparison would refine existingTLAB-019; protocol sensitivity already belongs to optional deferredTLAB-013. No distinct hypothesis requiring a newID is established. Choosing no new task preserves the original deliverable boundary without disguising uncertainty as a mandatory gate.
````

### Волна 079: tlab-wave079-skeptic-v1.md

Источник: `/tmp/tlab-wave079-skeptic-v1.md`; SHA256 `182f5ecca41c7a05fb0c92ed41ac40706714d110e7d7a5f5e9e2d8e3342b3217`; 2570 bytes.

````markdown
# Wave079 skeptic — bounded no-new-gap disposition

**NEW0 / ADMIT0; MERGE A+B.** The inspected record supports “no additional mandatory evidence gap found” for the bounded Task1 automation route: requirements permit automation, audit071 records its matched experiment/report, and accepted018 covers the former reproduction gap. This is conditional on those accepted scopes, not certification of submission, grading or goal completion.

**REFINE A:** preserve three separate evidence layers. The executed walkthrough generates definitions/dependencies from committed schema/templates; construction permission=false provides no ranking/native/quality proof. The public ranking replay has **12 synthetic input rows**, not 12 queries, and tests supplied-score/full-target semantics. Accepted018 separately documents raw→fresh collections→two fixed300 B/W fits→comparison on a new locked Mac environment, without exhaustive independent formula proof or universal portability. Neither lightweight demonstration substitutes for018, nor requires another adaptive native run.

**REFINE B:** fixed300 ΔNDCG +0.005122, CI [−0.010433,+0.018561] establishes neither superiority, equivalence nor absence of benefit. Selector source chooses the **earliest prefix with value ≥ global observed maximum−absolute1e-12**, not necessarily an exact maximizing tree. Adaptive1189/403 used reused73-positive-Q validation and2400 dependent checks; separately selected W−B mixes representation and complexity. Both fits reached1200: no early-stop savings, global optimum or economic proof.

**Mechanism/prediction/counter:** repeated selection can favor noise, so prospective best counts/gains need not repeat; that is an unquantified risk, not evidence against a real small benefit. Conflating demonstration, native reproduction and independent quality would either invent a prerequisite or overstate completion.

**Cheapest useful future check:** presentation-only consistency of these scopes/tolerance; no new execution gate or comparison admitted. Any later scientific comparison refines existing019/optional013. Runtime budget **UNKNOWN/unallocated**; science CLOSED/remainder UNKNOWN.

**SOURCE facts:** all six author FIRST/pins/freezes match Root readback hashes. Critical cited documents match author pins; no metrics recomputed. Shared currentness says476 publication fulfilled, native attempt failed closed, local36 rejected without writes, four-file repair uninstalled; historical pending questions/UNRUN wording cannot override it. No new IDs, gates or grants.
````

### Проверка исправления: tlab-native-metadata-fix-independent-review-v1.md

Источник: `/tmp/tlab-native-metadata-fix-independent-review-v1.md`; SHA256 `973bd92f9a803cc9f763db7cd0998229b1e4cc02e5426611a8b9b987f5413fd8`; 3182 bytes.

````markdown
# Independent CODE review: explicit kernel metadata

**PASS — no supported actionable findings in the proposed fix or recorded bounded helper proof.** This review covers the actual three candidate files, complete diff, regression source and recorded proof artifacts. Consumer compatibility has a separate reviewer; no whole-CLI/native success is inferred.

All frozen inventory SHA256/bytes/regular0644 modes match. The actual three-file diff exactly matches the supplied diff; canonical originals retain their pinned bytes. The change keeps the dependency-validation block and legacy default, adds an explicit kernel format and unknown-format error, routes the CLI through that keyword, and adjusts the existing environment double accordingly.

The regression exercises the AST-extracted actual function rather than a reimplementation. Its red calls real cold stdlib platform code with no reset/priming. The recorded denial is an O_RDWR open of /dev/null with actual platform.from_subprocess and Popen/_get_devnull frames. This distinguishes the original failure from an invented exception or mocked negative. The kernel branch is checked against real os.uname metadata under the same writable-open/process audit, ending with an empty forbidden-event list. Legacy dispatch uses a separately labeled return double after kernel checks; it is not presented as the real red evidence.

Marked duckdb/NumPy/CatBoost modules and the metadata.version double bypass package bodies. The stdlib import allowlist, final double-identity checks and project-module absence check support the declared unit seam. Lock/installed mismatches for each package, missing/duplicate catboost entries, malformed TOML, missing package key, PackageNotFoundError, absent-uname fallback and unknown-format behavior have concrete negative assertions. Exact messages and the final forbidden-event check prevent a caught audit denial from masquerading as a successful dependency-error case. CLI keyword routing is actual-source AST inspection only.

Source hashes agree across consumption marker, child output, parent before/after receipt and frozen inventory. Recorded phase order is red4986b1 exit1 → candidate9823bf exit0 → green df3fa7 exit0; both children are reaped, untimed-out, with empty stderr. The runner has exclusive consumption markers and no retry. Resource observations describe the bounded CODE children and parent-to-receipt scope, not whole native startup/cleanup containment or future budget sufficiency.

The 12-test FakeML suite remains UNRUN after revision; its source change is necessary for the new keyword. Whole-module/CLI identity, native/package execution, model/selection/serialization, callback abort and historical replay remain unverified here. Root-reported native failure0dc7c649… remains consumed/CLOSED and was not reproduced or reopened. Fresh provenance is still needed before any later execution of changed source.

Canonical36dbe783/tree/index/CLEAN remain unchanged. Only assigned TMP review outputs were written; no tests, imports, native/model/SQL/data, Git/canonical/network mutation or agents. No installation, publication or native authority is issued. STOP.
````

### Проверка исправления: tlab-native-metadata-fix-compatibility-review-v1.md

Источник: `/tmp/tlab-native-metadata-fix-compatibility-review-v1.md`; SHA256 `dc2c20859818a8c35b3a1a4f05f37c9c5ca668dff68ad65d0e0c4955e5e9dc1d`; 3781 bytes.

````markdown
# Independent compatibility review

Qualified PASS: no supported compatibility defect found in the frozen three-file candidate. This is a source review, not CLI/native acceptance. No other reviewer's new findings were read before this freeze.

Scope: manifest SHA256 `ff3579e5b0b262f633d7f6f7ad2b4b97b80ad2f6d0c5b2cff579e30dc40da51b`, diff SHA256 `0408d8316df46a558506fb60c53e7519f8a5da319f9a62421641597506567902`. Candidate files and canonical originals match the manifest's hashes and byte lengths at review freeze. Only named source and bounded evidence/metadata were read.

The [helper](/tmp/tlab-native-metadata-fix-proposal-v1/candidate/scripts/train_baselines.py:395) keeps no-argument/default and explicit `legacy` on the original `platform.platform()` route. Its existing Python string, loaded-packages dictionary, TOML parsing, loaded/installed/locked version checks, short-circuit order and mismatch exception text are retained. Supported-mode failures still propagate; unrecognized formats raise `ValueError` after dependency verification. Explicit `kernel` derives a string from direct uname attributes; the absent-API fallback is `sys.platform`. Reduced semantics are documented: this is kernel sysname/release/machine, not the legacy macOS marketing-version/processor/bitness string. No cache priming or audit exemption is introduced.

Historical consumers require preserving that distinction. [feature_program_experiment:301](/Users/mdpospelov/tlab-recsys-2026/scripts/feature_program_experiment.py:301) and [model oracle:725](/Users/mdpospelov/tlab-recsys-2026/tests/oracles/feature_program_model_audit.py:725) compare exact inherited macOS platform text. The strong-recovery oracle reconstructs that historical text at [109–132](/Users/mdpospelov/tlab-recsys-2026/tests/oracles/strong_recovery_audit.py:109). The unchanged metadata-ablation wrapper calls the helper without arguments and extends loaded_packages with verified pandas; strong-baseline stores that result. Baseline smoke and metadata export also retain no-argument callbacks. The new option therefore does not switch those consumers to kernel metadata. Historical cache logic was inspected only; it is not endorsed as a remedy for this attempt.

The [development CLI](/tmp/tlab-native-metadata-fix-proposal-v1/candidate/scripts/train_development.py:169) alone explicitly selects `kernel` at its original report assignment. Environment text does not enter the recipe directly; recipe fingerprints include the changed source, so a revision still changes identity. Selection, save/reload and score/ranking parity code are unchanged and do not compare platform text. The updated [FakeML double](/tmp/tlab-native-metadata-fix-proposal-v1/candidate/tests/test_train_development.py:151) accepts/requires the keyword and records it; the normal two-call test expects both kernel routes. Static inspection finds no introduced signature mismatch. The 12-test suite remains UNRUN.

The red/green receipts describe a reaped stdlib, AST-extracted helper seam with dependency doubles. They establish neither whole-module imports nor CLI identity, native fit/selection/serialization, broad containment or future budget adequacy. No runtime test, project/native import, model/data/SQL operation, Git action or canonical write was performed by this reviewer.

The original native attempt remains FAILED, consumed and closed; its conservative fit counter was 0 because failure preceded the fit counter increment. Legacy API compatibility does not preserve source hashes: old pinned artifacts/sources must stay immutable, and any future revised execution needs fresh honest inventory/provenance. Future execution budget remains UNKNOWN/unallocated. No new grant, attempt ID or mandatory scientific gate is requested.
````

### Проверка исправления: tlab-native-metadata-fix-v2-delta-independent-review-v1.md

Источник: `/tmp/tlab-native-metadata-fix-v2-delta-independent-review-v1.md`; SHA256 `cadebfafaf0a236b4e52bb1139f1b3bcaf4588fc1f85751c6edc848ca844ad70`; 2871 bytes.

````markdown
# Independent V2 delta review: public metadata unittest

**PASS — no supported actionable findings.** This is a targeted source/recorded-proof review of the new public unittest and proof wrapper. V1’s frozen review is reused for the unchanged helper, CLI and FakeML-test candidates; Root’s separate compatibility PASS is reused as a factual handoff.

All V1/V2 inventory SHA256/bytes/regular0644 modes match. The three V1 candidates compare byte-identical. The new test is absent canonically; actual V1-to-V2 diff is precisely its addition, and full candidate diff equals preserved V1 diff plus that addition. The four-file public candidate inventory is exact. Full new test, wrapper, handoff and proof artifacts were read; no test or project import was repeated.

The test derives repository/source paths from its own file and owns a TemporaryDirectory. It contains no hardcoded private/TMP paths or embedded native/control runner. Import/discovery applies no resource limits: CPU/alarm changes occur inside _metadata_child only. The separate Mac proof wrapper bounds its own parent. Public parent waits, kills on timeout and reaps; POSIX guards report unavailable when unsupported, with no Windows runtime claim.

The child extracts the actual helper AST body with explicit ROOT and marked dependency/version doubles, keeping package/project bodies unimported. Fixtures precede the writable-open/process audit. Kernel schema/syscall metadata, absent-uname fallback, nine lock/installed/loaded mismatches plus missing/duplicate entries and unknown-format rejection have meaningful assertions. Exact error messages and empty forbidden-event checks prevent swallowed audit failures from counting as successful negatives. Legacy dispatch is a separate mock. Only the final real cold default-denial witness is Darwin-scoped; elsewhere that case is NOT_APPLICABLE while kernel/mocked checks remain required.

Recorded d02e35 exit0 is one unittest PASS, with reaped child exit0,0.044037 CPU/0.046651833 launch-to-reap wall,3CPU/5wall guards. Proof source hashes match before/after, consumption marker, child/helper identity and frozen inventory; captured output hashes and closure metadata agree. Darwin’s real processor/Popen/devnull denial is the expected case, not another old-source/native attempt. Resource claims retain their child and parent-to-receipt scopes.

The 12-test FakeML suite, whole CLI/module identity, corrected native E2E, model/serialization/callback behavior, other-OS runtime and future startup-through-reap adequacy remain unverified. The original native attempt stays failed/consumed/CLOSED. Canonical code originals remain unchanged; no canonical/Git/network mutation, imports/tests/native/data/SQL or agents occurred. Only assigned TMP review artifacts were written. This PASS grants no installation, publication or native authority. STOP.
````

## Дословные Root-решения

### Root adoption волны 078

Источник: `/tmp/tlab-root-wave078-research-adoption-v1.json`; SHA256 `29134450c320cd6dc8ea39f70e2eb7a393e2801ea0f749b0c423e9594ffc6e21`; 7018 bytes.

````json
{
  "version": 1,
  "UTC": "2026-10-16T19:04:52.825441+00:00",
  "wave": 78,
  "status": "QUALIFIED_SOURCE_RESEARCH_ADOPTED_NO_EXPERIMENT_ADMITTED",
  "references": [
    {
      "path": "/tmp/tlab-wave078-shared-context-v1.json",
      "sha256": "d6b105d55f398854213afebeda5861e74ca3fa3aef229619a603b638b8f12418",
      "bytes": 4761
    },
    {
      "path": "/tmp/tlab-root-wave078-dispatch-v1.json",
      "sha256": "7042b78e03571cfa9a500973bcafed3413e9a312e752ccc942c217d24539b394",
      "bytes": 1056
    },
    {
      "path": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "sha256": "6a72c3e11f7ce68fc1164e6ea8fae0c724527831932d6d3b8985c9099fc450bf",
      "bytes": 2379
    },
    {
      "path": "/tmp/tlab-root-wave078-primary-manual-readback-v1.json",
      "sha256": "df1542e1df3c4ae895d7cc894bd5157aab0c3f3d3da8581baf7c25da527f4c05",
      "bytes": 2610
    },
    {
      "path": "/tmp/tlab-wave078-observer-a-FIRST.md",
      "sha256": "a0c85b9ba5b06f3957f7862316abd8af12af80a9b2af8ff1587e10bd76aae7fd",
      "bytes": 2634
    },
    {
      "path": "/tmp/tlab-wave078-observer-a-pins.json",
      "sha256": "c480827090fcfacb7dda2909766fe53335f0fa2e3250e55d332f86aa279ab803",
      "bytes": 1924
    },
    {
      "path": "/tmp/tlab-wave078-observer-a-freeze.json",
      "sha256": "141526e3cb87fa665176d2e78472e88f16a5035726c3bed9c6ae51ea03676978",
      "bytes": 960
    },
    {
      "path": "/tmp/tlab-wave078-telemetry-b-FIRST.md",
      "sha256": "d97ea5c0d02700ab047c38ff24907ea89fa2b1f18465e342d7b7484921a192be",
      "bytes": 2695
    },
    {
      "path": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "sha256": "fba42a8ccc705e0391ec8c106e42251b544ae1a2e467aaecb5d579ea5daedf7b",
      "bytes": 3341
    },
    {
      "path": "/tmp/tlab-wave078-telemetry-b-freeze.json",
      "sha256": "72092bda86c7629d682da2408fd4f0b902eb3252135787821c20161b7e1a4bd9",
      "bytes": 887
    },
    {
      "path": "/tmp/tlab-wave078-provenance-c-FIRST.md",
      "sha256": "543e7cbba9b13f33a8823f70050de0350afa92e2875e87c701f72c43633005ce",
      "bytes": 2750
    },
    {
      "path": "/tmp/tlab-wave078-provenance-c-pins.json",
      "sha256": "dd04f85fae69bc5bb0d2c550d9f5f773fc8d9fedef04df7714a6f2c19b2e284c",
      "bytes": 2796
    },
    {
      "path": "/tmp/tlab-wave078-provenance-c-freeze.json",
      "sha256": "16f3bd7e885796ca6a972fc904e98b2356a7ca8e3a677abc3dd4cb1829aa16e8",
      "bytes": 1113
    },
    {
      "path": "/tmp/tlab-wave078-skeptic-v1.md",
      "sha256": "5ac30a63808132b58c7afeed21b25f2ca188b7ac4b27d2b5923e8a28ce5c92c1",
      "bytes": 3202
    },
    {
      "path": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "sha256": "c8a2e68fa3b099923b8e919c93ee095a63d596761ab21fc17276997f13bf3c57",
      "bytes": 5680
    },
    {
      "path": "/tmp/tlab-wave078-skeptic-v1-freeze.json",
      "sha256": "6014991a11a34e804efe92d2e232f8a99c30dea9b1821a34770f4e034803bf30",
      "bytes": 1019
    }
  ],
  "independence": "ThreeNEWfork-noneblindauthors freeze beforeNEWdistinctskeptic. Attestednopeerreads; artifacthashesnotproofreadinghistory. Sharedsource/officialdocperspectivesnot3independentempiricalcorroborations.",
  "counts": {
    "NEW": 0,
    "REFINE": 2,
    "MERGE": 1,
    "ADMIT": 0
  },
  "dispositions": [
    {
      "author": "A",
      "status": "REFINE",
      "family": "developmentCLIvalidation+continuousTLAB014",
      "mechanism": "FilenamePath.resolveonallprofileeventsbeforeeventdispatch amplifiesSOURCEobserverwork.",
      "prediction": "Event-first/lazyclassification decreasesresolvercallcount whilepreservingforbiddenPythoncalls/originalfitcount/selectedreturns/exceptionhandling.",
      "counter": "No measuredshareofactual23CPU/budgetadequacy/speedup; actualprimarywasmetadataauditfailure. CeventskipmustretainmeaningfulPython events.",
      "nearest_future": "ExerciseREALcheckeddispatcherwithfakeframes/countingresolver sentinel, comparedecisions andbothcachefillorders; nothand-codedexpectedtableonly. UNRUN/costUNKNOWN/unallocated.",
      "benefit": "Cheaperhonestengineeringvalidation supportsoriginalbaselineautomation."
    },
    {
      "author": "B",
      "status": "REFINE",
      "family": "developmentCLIvalidation+continuousTLAB014",
      "mechanism": "Failurewriteusesexhaustedworkcheck, so telemetrycanvanish.",
      "prediction": "Prospectivelyboundedone-wayterminalpathfreezesprimitiveprimary/counterswithnullprovenanceandperformsnowork/getter/hash/retry; secondarysinkfailuremustnotreplaceprimary.",
      "counter": "Hardkill/unavailablesinkcanpreventoutput; no guarantee/freecleanupbudget. Currentrunnerfinallyalsohashes/inventories sofullterminaldesignmustrespectthat.",
      "nearest_future": "REALterminalseam expiredclock/sentinelprimary/raisingformatter-sink-cleanup/boobytrappedworkgetter probes, futureUNRUN/costUNKNOWN/unallocated.",
      "benefit": "Preservefailureevidencewithoutfalsezero/successcounts."
    },
    {
      "author": "C",
      "status": "MERGE",
      "family": "ExistingprovenanceboundariesandAobserverrefinement,TLAB014",
      "mechanism": "Classificationcachecannotcacheacceptanceofmutableglobals/ROOT/caller.",
      "prediction": "Wrongfilename/samecode-separatedglobals/wrongROOT/brokencaller/exceptionreturns remainrejectedatdeclaredboundary underoptimization.",
      "counter": "DescriptortruthtableisSPECIFICATION, notactualcallchain/timingproof. Sourcepath/hashnotuniversalexecutablesource/nativeclosure. GetterprotectiononlybeforeFORWARDERgetters/originalfit; publichelpergetters earlier.",
      "nearest_future": "Checkedpredicate/dispatcherboundary exercised withadversarialrecords/cacheorders, nottablealone; UNRUN/costUNKNOWN/unallocated.",
      "benefit": "AvoidsilentlyweakeningactualCLIprovenancewhileloweringobservercost."
    }
  ],
  "rejected_generalizations": "No attributionofentire23CPUtoobserver, nativebudgetadequacy/currenthostilecodecontainment/allgettersprotected/verifiedrepair/newscientificgap/newID/gate/grant. FIRSTA80wordlabelvsactual70 harmlesscapsissue preservedraw.",
  "actual_status": "Nativefreshone50/65ATTEMPTED_FAILED/consumedCLOSED, CLIobservedconservativeattempt0/observernativecountersunavailable. Exact476publicationfulfilledRootaccepted. MetadatafixordinaryCODE+V2publictest separate, notnewnativeacceptance.",
  "cadence": {
    "due_UTC": "2026-10-16T18:45:00Z",
    "context_UTC": "2026-10-16T18:53:02.950493+00:00",
    "dispatch_completed_upper_bound_UTC": "2026-10-16T18:53:54.070609+00:00",
    "individual_start_times": "UNKNOWN",
    "next_due_UTC": "2026-10-16T19:30:00Z",
    "delay": "Actualapprovednative/publication operations+failure/legacycompatibilityrepairfirst; noreset. Twooperationaldiagnosisauthorsnotcountedresearchwave."
  },
  "authority": "SOURCEarchive/TLAB014refinementonly. No oracle/test/projectnativeimports/data/model/SQL/canonical/Git/networkmutations/newgrants; privateworker/controls/stdlibbody+aliasesEXCLUDEDGit, refsmetadataonly. No newhumanquestionpending."
}
````

### Root adoption волны 079

Источник: `/tmp/tlab-root-wave079-research-adoption-v1.json`; SHA256 `d22978b0885ea8d70bac3e1da39b01945bb45048cf32bd8abf9ccd7f7782c5aa`; 4415 bytes.

````json
{
  "UTC": "2026-10-16T19:34:34.894657+00:00",
  "wave": 79,
  "status": "QUALIFIED_SOURCE_META_REVIEW_ADOPTED",
  "counts": {
    "NEW": 0,
    "REFINE": 2,
    "MERGE": 0,
    "ADMIT": 0
  },
  "skeptic_grouping": "Skeptic merges A+B presentation discipline; Root retains two existing-ID refinements, no fresh task.",
  "dispositions": [
    {
      "author": "A",
      "state": "REFINE",
      "existing": "TLAB016/018+continuous014",
      "mechanism": "Separate definition generation,12syntheticinputrow ranking replay, andraw018Macnative/data reproduction",
      "prediction": "Existing demonstration andscope explanation suffice without inventing another nativeadaptive prerequisite",
      "counter": "Not submission/grade/goal completion; synthetic demo not native/data/quality proof",
      "future": "Presentation consistency only, no newexecutiongate, runtimecostUNKNOWNunallocated",
      "benefit": "Avoid redundant evidencework; keep original task deliverable clear"
    },
    {
      "author": "B",
      "state": "REFINE",
      "existing": "TLAB019/optional013+continuous014",
      "mechanism": "Repeated dependent validation selection may favor noise; not quantified correction",
      "prediction": "Prospective best counts/gains may not repeat",
      "counter": "Real small gain remains compatible; finalCIcross0 neither superiority nor equivalence",
      "future": "No distinct newcomparisonrecommended; no heldoutreopen/native/sciencegrant",
      "benefit": "Preserve honest scientific inference"
    }
  ],
  "qualifications": "Earliestprefix within absolute1e-12 ofglobalobservedmaximum, not necessarily exactmax. 12rows not12queries. NativeCLIonefailedclosed;fix4uninstalled. Exact476fulfilled. LOCAL36 rejectedbeforecopy.",
  "independence": "TwoNEWforknoneblindFIRSTauthors frozen beforeNEWdistinctskeptic; attestations are not empirical reading-history proof. Shared sources do not make independent empirical confirmations.",
  "cadence": {
    "due_UTC": "2026-10-16T19:30:00Z",
    "next_due_UTC": "2026-10-16T20:15:00Z",
    "individual_starts": "UNKNOWN",
    "root_authors_readback_UTC": "2026-10-16T19:31:20.741576+00:00",
    "reason": "Bounded meta-review after repeated no-admission waves; mainfix/test/permission reconciliation remains execution priority; no grid reset"
  },
  "references": [
    {
      "path": "/tmp/tlab-wave079-shared-context-v1.json",
      "sha256": "621c41df250a1d0d54e50d1cee411e016493a874750c6e84c97159dfc5c1bcec",
      "bytes": 2569
    },
    {
      "path": "/tmp/tlab-root-wave079-authors-readback-v1.json",
      "sha256": "9224b3679cf7d07ab3ba8d8a91446fa933298e71ac244ea84ee1da58ad4c5e42",
      "bytes": 1237
    },
    {
      "path": "/tmp/tlab-wave079-deliverable-a-FIRST.md",
      "sha256": "1362b7d8cc60e21a54b0894aba49489925edae5cf59f68a0f5053fb31792a481",
      "bytes": 1948
    },
    {
      "path": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "sha256": "68fdb348faaf122b031cbf58e2ab45dcea921896f048f8e58ced4d03b0609121",
      "bytes": 6211
    },
    {
      "path": "/tmp/tlab-wave079-deliverable-a-freeze.json",
      "sha256": "1a744407a1d103df6d1eed4381e6921284e24ffba3474271d3e6ad3c908ad25b",
      "bytes": 497
    },
    {
      "path": "/tmp/tlab-wave079-inference-b-FIRST.md",
      "sha256": "89b4136b01c67dca244e3c419dfd71ea9cc191e6dab9c69f2c4d22d2cd208499",
      "bytes": 1884
    },
    {
      "path": "/tmp/tlab-wave079-inference-b-pins.json",
      "sha256": "82d0fb2cd45292af0d1441ee5d9bb0e9a78634b6f3bf56524fcd183518fced4b",
      "bytes": 2846
    },
    {
      "path": "/tmp/tlab-wave079-inference-b-freeze.json",
      "sha256": "e44d9c089f90ada659f57e1f001c9cfdf55eb7bf2444227f03de89f32add2b6c",
      "bytes": 559
    },
    {
      "path": "/tmp/tlab-wave079-skeptic-v1.md",
      "sha256": "182f5ecca41c7a05fb0c92ed41ac40706714d110e7d7a5f5e9e2d8e3342b3217",
      "bytes": 2570
    },
    {
      "path": "/tmp/tlab-wave079-skeptic-pins.json",
      "sha256": "a017ae712b27669215421f014254010ba98a90b2d6ca7199118ff165f057b267",
      "bytes": 8666
    },
    {
      "path": "/tmp/tlab-wave079-skeptic-freeze.json",
      "sha256": "8e5d5f3404abbb92f50d8b851e97af068c9a08d6320ae4974475121af11912e2",
      "bytes": 530
    }
  ],
  "authority": "SOURCE/TMP only; archivepending. No newID/gate/grant/native/science/test/Git/canonical/networkmutation. Original goal andlimitsunchanged."
}
````

## Компактная карта SHA и ссылок

```json
{
  "archive_form": "ONE_CONSOLIDATED_REPORT_NO_NEW_RAW_ARCHIVE_PATHS",
  "artifact_identities": [
    {
      "source": "/tmp/tlab-root-wave078-research-adoption-v1.json",
      "sha256": "29134450c320cd6dc8ea39f70e2eb7a393e2801ea0f749b0c423e9594ffc6e21",
      "bytes": 7018,
      "file_mode": 420,
      "kind": "ROOT_QUALIFIED_RESEARCH_DISPOSITION_METADATA"
    },
    {
      "source": "/tmp/tlab-wave078-shared-context-v1.json",
      "sha256": "d6b105d55f398854213afebeda5861e74ca3fa3aef229619a603b638b8f12418",
      "bytes": 4761,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-root-wave078-dispatch-v1.json",
      "sha256": "7042b78e03571cfa9a500973bcafed3413e9a312e752ccc942c217d24539b394",
      "bytes": 1056,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "sha256": "6a72c3e11f7ce68fc1164e6ea8fae0c724527831932d6d3b8985c9099fc450bf",
      "bytes": 2379,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-root-wave078-primary-manual-readback-v1.json",
      "sha256": "df1542e1df3c4ae895d7cc894bd5157aab0c3f3d3da8581baf7c25da527f4c05",
      "bytes": 2610,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-observer-a-FIRST.md",
      "sha256": "a0c85b9ba5b06f3957f7862316abd8af12af80a9b2af8ff1587e10bd76aae7fd",
      "bytes": 2634,
      "file_mode": 420,
      "kind": "SAFE_RESULT_TEXT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-observer-a-pins.json",
      "sha256": "c480827090fcfacb7dda2909766fe53335f0fa2e3250e55d332f86aa279ab803",
      "bytes": 1924,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-observer-a-freeze.json",
      "sha256": "141526e3cb87fa665176d2e78472e88f16a5035726c3bed9c6ae51ea03676978",
      "bytes": 960,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-telemetry-b-FIRST.md",
      "sha256": "d97ea5c0d02700ab047c38ff24907ea89fa2b1f18465e342d7b7484921a192be",
      "bytes": 2695,
      "file_mode": 420,
      "kind": "SAFE_RESULT_TEXT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "sha256": "fba42a8ccc705e0391ec8c106e42251b544ae1a2e467aaecb5d579ea5daedf7b",
      "bytes": 3341,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-telemetry-b-freeze.json",
      "sha256": "72092bda86c7629d682da2408fd4f0b902eb3252135787821c20161b7e1a4bd9",
      "bytes": 887,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-provenance-c-FIRST.md",
      "sha256": "543e7cbba9b13f33a8823f70050de0350afa92e2875e87c701f72c43633005ce",
      "bytes": 2750,
      "file_mode": 420,
      "kind": "SAFE_RESULT_TEXT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-provenance-c-pins.json",
      "sha256": "dd04f85fae69bc5bb0d2c550d9f5f773fc8d9fedef04df7714a6f2c19b2e284c",
      "bytes": 2796,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-provenance-c-freeze.json",
      "sha256": "16f3bd7e885796ca6a972fc904e98b2356a7ca8e3a677abc3dd4cb1829aa16e8",
      "bytes": 1113,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-skeptic-v1.md",
      "sha256": "5ac30a63808132b58c7afeed21b25f2ca188b7ac4b27d2b5923e8a28ce5c92c1",
      "bytes": 3202,
      "file_mode": 420,
      "kind": "SAFE_RESULT_TEXT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "sha256": "c8a2e68fa3b099923b8e919c93ee095a63d596761ab21fc17276997f13bf3c57",
      "bytes": 5680,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave078-skeptic-v1-freeze.json",
      "sha256": "6014991a11a34e804efe92d2e232f8a99c30dea9b1821a34770f4e034803bf30",
      "bytes": 1019,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-root-wave079-research-adoption-v1.json",
      "sha256": "d22978b0885ea8d70bac3e1da39b01945bb45048cf32bd8abf9ccd7f7782c5aa",
      "bytes": 4415,
      "file_mode": 420,
      "kind": "ROOT_QUALIFIED_RESEARCH_DISPOSITION_METADATA"
    },
    {
      "source": "/tmp/tlab-wave079-shared-context-v1.json",
      "sha256": "621c41df250a1d0d54e50d1cee411e016493a874750c6e84c97159dfc5c1bcec",
      "bytes": 2569,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-root-wave079-authors-readback-v1.json",
      "sha256": "9224b3679cf7d07ab3ba8d8a91446fa933298e71ac244ea84ee1da58ad4c5e42",
      "bytes": 1237,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave079-deliverable-a-FIRST.md",
      "sha256": "1362b7d8cc60e21a54b0894aba49489925edae5cf59f68a0f5053fb31792a481",
      "bytes": 1948,
      "file_mode": 420,
      "kind": "SAFE_RESULT_TEXT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "sha256": "68fdb348faaf122b031cbf58e2ab45dcea921896f048f8e58ced4d03b0609121",
      "bytes": 6211,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave079-deliverable-a-freeze.json",
      "sha256": "1a744407a1d103df6d1eed4381e6921284e24ffba3474271d3e6ad3c908ad25b",
      "bytes": 497,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave079-inference-b-FIRST.md",
      "sha256": "89b4136b01c67dca244e3c419dfd71ea9cc191e6dab9c69f2c4d22d2cd208499",
      "bytes": 1884,
      "file_mode": 420,
      "kind": "SAFE_RESULT_TEXT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave079-inference-b-pins.json",
      "sha256": "82d0fb2cd45292af0d1441ee5d9bb0e9a78634b6f3bf56524fcd183518fced4b",
      "bytes": 2846,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave079-inference-b-freeze.json",
      "sha256": "e44d9c089f90ada659f57e1f001c9cfdf55eb7bf2444227f03de89f32add2b6c",
      "bytes": 559,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave079-skeptic-v1.md",
      "sha256": "182f5ecca41c7a05fb0c92ed41ac40706714d110e7d7a5f5e9e2d8e3342b3217",
      "bytes": 2570,
      "file_mode": 420,
      "kind": "SAFE_RESULT_TEXT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave079-skeptic-pins.json",
      "sha256": "a017ae712b27669215421f014254010ba98a90b2d6ca7199118ff165f057b267",
      "bytes": 8666,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-wave079-skeptic-freeze.json",
      "sha256": "8e5d5f3404abbb92f50d8b851e97af068c9a08d6320ae4974475121af11912e2",
      "bytes": 530,
      "file_mode": 420,
      "kind": "REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-native-metadata-fix-independent-review-v1.md",
      "sha256": "973bd92f9a803cc9f763db7cd0998229b1e4cc02e5426611a8b9b987f5413fd8",
      "bytes": 3182,
      "file_mode": 420,
      "kind": "SAFE_SOURCE_REVIEW_TEXT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-native-metadata-fix-independent-review-v1-pins.json",
      "sha256": "85090d5de4115121f2c70bd0e241b819fcee0ad9cddeed3978788e7bc6093d36",
      "bytes": 16893,
      "file_mode": 420,
      "kind": "REVIEW_REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-native-metadata-fix-independent-review-v1-freeze.json",
      "sha256": "8a33f461aa3754d3fb73345963f1df9ddabbdc4995652bb9ed72cd3f3f60f4f8",
      "bytes": 1408,
      "file_mode": 420,
      "kind": "REVIEW_REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-native-metadata-fix-compatibility-review-v1.md",
      "sha256": "dc2c20859818a8c35b3a1a4f05f37c9c5ca668dff68ad65d0e0c4955e5e9dc1d",
      "bytes": 3781,
      "file_mode": 420,
      "kind": "SAFE_SOURCE_REVIEW_TEXT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-native-metadata-fix-compatibility-review-v1-pins.json",
      "sha256": "4932a03a0717336c95698f58880805b8e597102c878d55a9a468a390f959d77f",
      "bytes": 3247,
      "file_mode": 420,
      "kind": "REVIEW_REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-native-metadata-fix-compatibility-review-v1-freeze.json",
      "sha256": "b807a9c3ab594a198919c5fe6ffc6607996c697524e3f483e53c724ba88e1dfa",
      "bytes": 655,
      "file_mode": 420,
      "kind": "REVIEW_REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-native-metadata-fix-v2-delta-independent-review-v1.md",
      "sha256": "cadebfafaf0a236b4e52bb1139f1b3bcaf4588fc1f85751c6edc848ca844ad70",
      "bytes": 2871,
      "file_mode": 420,
      "kind": "SAFE_SOURCE_REVIEW_TEXT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-native-metadata-fix-v2-delta-independent-review-v1-pins.json",
      "sha256": "e9faec6738f4727abda4c3b3336a1cab8e59100c882ec8adb7acf03b60cad76a",
      "bytes": 12889,
      "file_mode": 420,
      "kind": "REVIEW_REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-native-metadata-fix-v2-delta-independent-review-v1-freeze.json",
      "sha256": "a6cc3fa7fe0f1f8b9afd81c63e7f7d2b69d59e7c415cd9006a1739ad70514ff6",
      "bytes": 1603,
      "file_mode": 420,
      "kind": "REVIEW_REFERENCE_METADATA_BODY_NOT_EMBEDDED"
    },
    {
      "source": "/tmp/tlab-native-metadata-fix-proposal-v2/manifest.json",
      "sha256": "9dd812c25e281869c455022ed353bbfc0a191da35af4709b3bc26b38468507fd",
      "bytes": 7413,
      "file_mode": 420,
      "kind": "HISTORICAL_OR_CANDIDATE_METADATA_REFERENCE_ONLY"
    },
    {
      "source": "/tmp/tlab-wave077-outcomes-LOCAL-execution-receipt-v1.json",
      "sha256": "7888ad3a5eda81588e45882b2205d8c762a5c0e2e5dac45cf6d77afcc6e78e42",
      "bytes": 2539,
      "file_mode": 420,
      "kind": "HISTORICAL_OR_CANDIDATE_METADATA_REFERENCE_ONLY"
    },
    {
      "source": "/tmp/tlab-wave077-outcomes-LOCAL-execution-v1/copy-approval-rejection.txt",
      "sha256": "00ebcf83626e2a8735b3b61ca7664202e217b11e4ba5e298b77a5327c2dd0bd2",
      "bytes": 850,
      "file_mode": 420,
      "kind": "HISTORICAL_OR_CANDIDATE_METADATA_REFERENCE_ONLY"
    },
    {
      "source": "/tmp/tlab-wave077-outcomes-LOCAL-execution-v1/rejection-actual-state.json",
      "sha256": "585f68342dde3f49ff691d6066e429b063b4dbc1fca01118a34b7c22237b1a2b",
      "bytes": 564,
      "file_mode": 420,
      "kind": "HISTORICAL_OR_CANDIDATE_METADATA_REFERENCE_ONLY"
    }
  ],
  "source_pin_reference_metadata_only": [
    {
      "artifact_origin": "/tmp/tlab-wave078-shared-context-v1.json",
      "json_location": "/references/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-worker-proposal-v2/run_native_e2e.py",
      "sha256": "dc92b55891acd8856062c30d17349a8be2db75c97ebc9c1f60c0bfa9d4b216e9",
      "bytes": 26388
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-shared-context-v1.json",
      "json_location": "/references/1",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/scripts/train_development.py",
      "sha256": "f4d19483532318b25c2adb51734ec347e772d3441edca944c5c91ce791cacde9",
      "bytes": 12640
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-shared-context-v1.json",
      "json_location": "/references/2",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-native-cli-tiny-native-e2e-actual-failure-v1.json",
      "sha256": "0dc7c6491a238e1a20cc56cd6e69d7e7e86d59dc61888fc9b001b6b3e18bcc1b",
      "bytes": 4584
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-shared-context-v1.json",
      "json_location": "/references/3",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-publication-476dfd6-final-actual-acceptance-v1.json",
      "sha256": "25e955ae8f6b45d21ba76eeb27748dd8931c57c5716753d26126477ff7b86b98",
      "bytes": 1724
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-dispatch-v1.json",
      "json_location": "/context",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-shared-context-v1.json",
      "sha256": "d6b105d55f398854213afebeda5861e74ca3fa3aef229619a603b638b8f12418",
      "bytes": 4761
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "json_location": "/authors/0/files/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-observer-a-FIRST.md",
      "sha256": "a0c85b9ba5b06f3957f7862316abd8af12af80a9b2af8ff1587e10bd76aae7fd",
      "bytes": 2634
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "json_location": "/authors/0/files/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-observer-a-pins.json",
      "sha256": "c480827090fcfacb7dda2909766fe53335f0fa2e3250e55d332f86aa279ab803",
      "bytes": 1924
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "json_location": "/authors/0/files/2",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-observer-a-freeze.json",
      "sha256": "141526e3cb87fa665176d2e78472e88f16a5035726c3bed9c6ae51ea03676978",
      "bytes": 960
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "json_location": "/authors/1/files/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-telemetry-b-FIRST.md",
      "sha256": "d97ea5c0d02700ab047c38ff24907ea89fa2b1f18465e342d7b7484921a192be",
      "bytes": 2695
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "json_location": "/authors/1/files/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "sha256": "fba42a8ccc705e0391ec8c106e42251b544ae1a2e467aaecb5d579ea5daedf7b",
      "bytes": 3341
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "json_location": "/authors/1/files/2",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-telemetry-b-freeze.json",
      "sha256": "72092bda86c7629d682da2408fd4f0b902eb3252135787821c20161b7e1a4bd9",
      "bytes": 887
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "json_location": "/authors/2/files/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-provenance-c-FIRST.md",
      "sha256": "543e7cbba9b13f33a8823f70050de0350afa92e2875e87c701f72c43633005ce",
      "bytes": 2750
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "json_location": "/authors/2/files/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-provenance-c-pins.json",
      "sha256": "dd04f85fae69bc5bb0d2c550d9f5f773fc8d9fedef04df7714a6f2c19b2e284c",
      "bytes": 2796
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "json_location": "/authors/2/files/2",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-provenance-c-freeze.json",
      "sha256": "16f3bd7e885796ca6a972fc904e98b2356a7ca8e3a677abc3dd4cb1829aa16e8",
      "bytes": 1113
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-primary-manual-readback-v1.json",
      "json_location": "/references/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-worker-proposal-v2/run_native_e2e.py",
      "sha256": "dc92b55891acd8856062c30d17349a8be2db75c97ebc9c1f60c0bfa9d4b216e9",
      "bytes": 26388
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-primary-manual-readback-v1.json",
      "json_location": "/references/1",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/scripts/development_training.py",
      "sha256": "9f7d9ab7c1f69fd0726d657791059b4a0c5270bf7a32da898602eaf84ccffcc9",
      "bytes": 5590
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave078-primary-manual-readback-v1.json",
      "json_location": "/references/2",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-native-cli-tiny-native-e2e-actual-failure-v1.json",
      "sha256": "0dc7c6491a238e1a20cc56cd6e69d7e7e86d59dc61888fc9b001b6b3e18bcc1b",
      "bytes": 4584
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-observer-a-pins.json",
      "json_location": "/local_reads/0",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/personal-agent-system/.agents/skills/research/SKILL.md",
      "sha256": "452334717864a950b44ec991b96bf65edeb2e263a2c098560e0b6d9fd31b2e34"
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-observer-a-pins.json",
      "json_location": "/local_reads/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-shared-context-v1.json",
      "sha256": "d6b105d55f398854213afebeda5861e74ca3fa3aef229619a603b638b8f12418"
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-observer-a-pins.json",
      "json_location": "/local_reads/2",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-worker-proposal-v2/run_native_e2e.py",
      "sha256": "dc92b55891acd8856062c30d17349a8be2db75c97ebc9c1f60c0bfa9d4b216e9"
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-observer-a-freeze.json",
      "json_location": "/first",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-observer-a-FIRST.md",
      "sha256": "a0c85b9ba5b06f3957f7862316abd8af12af80a9b2af8ff1587e10bd76aae7fd"
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-observer-a-freeze.json",
      "json_location": "/pins",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-observer-a-pins.json",
      "sha256": "c480827090fcfacb7dda2909766fe53335f0fa2e3250e55d332f86aa279ab803"
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "json_location": "/sources/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-shared-context-v1.json",
      "sha256": "d6b105d55f398854213afebeda5861e74ca3fa3aef229619a603b638b8f12418"
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "json_location": "/sources/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-worker-proposal-v2/run_native_e2e.py",
      "sha256": "dc92b55891acd8856062c30d17349a8be2db75c97ebc9c1f60c0bfa9d4b216e9",
      "bytes": 26388
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "json_location": "/sources/2",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/scripts/train_development.py",
      "sha256": "f4d19483532318b25c2adb51734ec347e772d3441edca944c5c91ce791cacde9",
      "bytes": 12640
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "json_location": "/sources/3",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-runner-proposal-v1/child.py",
      "sha256": "673454b27ce15016f3f4ce8691b0484d2d88318434688a3a6aba1e892c7bfa57",
      "bytes": 11366
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "json_location": "/sources/4",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-native-cli-tiny-native-e2e-actual-failure-v1.json",
      "sha256": "0dc7c6491a238e1a20cc56cd6e69d7e7e86d59dc61888fc9b001b6b3e18bcc1b",
      "bytes": 4584
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "json_location": "/sources/5",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-execution-20261016-once/child-result.json",
      "sha256": "b144bbc5fe356afaa416c1fb34d5f067c20e0cc46fa24c8cf63557f916437404",
      "bytes": 784
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "json_location": "/sources/6",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-execution-20261016-once/parent-result.json",
      "sha256": "1ef9aee9a1cded75382ea7309d270d869e5ded33a7deded03b463b296a028434",
      "bytes": 1388
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "json_location": "/sources/7",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-execution-20261016-once/attempt-consumed.json",
      "sha256": "1fb6062a3ed37494700d88af355e875f07a00c2ad5277e4b03635d1948f959c5",
      "bytes": 460
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "json_location": "/sources/8",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-execution-20261016-once/child-entry-consumed.json",
      "sha256": "185118551dab5a4759976a8678f17a9c009c426c054f14741b55e83837908090",
      "bytes": 218
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "json_location": "/sources/9",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-publication-476dfd6-final-actual-acceptance-v1.json",
      "sha256": "25e955ae8f6b45d21ba76eeb27748dd8931c57c5716753d26126477ff7b86b98",
      "bytes": 1724
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-freeze.json",
      "json_location": "/FIRST",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-telemetry-b-FIRST.md",
      "sha256": "d97ea5c0d02700ab047c38ff24907ea89fa2b1f18465e342d7b7484921a192be",
      "bytes": 2695
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-telemetry-b-freeze.json",
      "json_location": "/pins",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "sha256": "fba42a8ccc705e0391ec8c106e42251b544ae1a2e467aaecb5d579ea5daedf7b",
      "bytes": 3341
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-provenance-c-pins.json",
      "json_location": "/local/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-shared-context-v1.json",
      "sha256": "d6b105d55f398854213afebeda5861e74ca3fa3aef229619a603b638b8f12418"
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-provenance-c-pins.json",
      "json_location": "/local/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-worker-proposal-v2/run_native_e2e.py",
      "sha256": "dc92b55891acd8856062c30d17349a8be2db75c97ebc9c1f60c0bfa9d4b216e9",
      "bytes": 26388
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-provenance-c-pins.json",
      "json_location": "/local/2",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/scripts/train_development.py",
      "sha256": "f4d19483532318b25c2adb51734ec347e772d3441edca944c5c91ce791cacde9",
      "bytes": 12640
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-provenance-c-pins.json",
      "json_location": "/local/3",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/scripts/development_training.py",
      "sha256": "9f7d9ab7c1f69fd0726d657791059b4a0c5270bf7a32da898602eaf84ccffcc9",
      "bytes": 5590
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-provenance-c-pins.json",
      "json_location": "/local/4",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-native-cli-tiny-native-e2e-actual-failure-v1.json",
      "sha256": "0dc7c6491a238e1a20cc56cd6e69d7e7e86d59dc61888fc9b001b6b3e18bcc1b",
      "bytes": 4584
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-provenance-c-pins.json",
      "json_location": "/local/5",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-publication-476dfd6-final-actual-acceptance-v1.json",
      "sha256": "25e955ae8f6b45d21ba76eeb27748dd8931c57c5716753d26126477ff7b86b98",
      "bytes": 1724
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-provenance-c-freeze.json",
      "json_location": "/files/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-provenance-c-FIRST.md",
      "sha256": "543e7cbba9b13f33a8823f70050de0350afa92e2875e87c701f72c43633005ce",
      "bytes": 2750
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-provenance-c-freeze.json",
      "json_location": "/files/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-provenance-c-pins.json",
      "sha256": "dd04f85fae69bc5bb0d2c550d9f5f773fc8d9fedef04df7714a6f2c19b2e284c",
      "bytes": 2796
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/bindings/common",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-shared-context-v1.json",
      "sha256": "d6b105d55f398854213afebeda5861e74ca3fa3aef229619a603b638b8f12418",
      "bytes": 4761
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/bindings/root_readback",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-wave078-three-FIRSTs-readback-v1.json",
      "sha256": "6a72c3e11f7ce68fc1164e6ea8fae0c724527831932d6d3b8985c9099fc450bf",
      "bytes": 2379
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/bindings/peer_artifacts/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-observer-a-FIRST.md",
      "sha256": "a0c85b9ba5b06f3957f7862316abd8af12af80a9b2af8ff1587e10bd76aae7fd",
      "bytes": 2634
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/bindings/peer_artifacts/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-observer-a-pins.json",
      "sha256": "c480827090fcfacb7dda2909766fe53335f0fa2e3250e55d332f86aa279ab803",
      "bytes": 1924
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/bindings/peer_artifacts/2",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-observer-a-freeze.json",
      "sha256": "141526e3cb87fa665176d2e78472e88f16a5035726c3bed9c6ae51ea03676978",
      "bytes": 960
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/bindings/peer_artifacts/3",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-telemetry-b-FIRST.md",
      "sha256": "d97ea5c0d02700ab047c38ff24907ea89fa2b1f18465e342d7b7484921a192be",
      "bytes": 2695
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/bindings/peer_artifacts/4",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-telemetry-b-pins.json",
      "sha256": "fba42a8ccc705e0391ec8c106e42251b544ae1a2e467aaecb5d579ea5daedf7b",
      "bytes": 3341
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/bindings/peer_artifacts/5",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-telemetry-b-freeze.json",
      "sha256": "72092bda86c7629d682da2408fd4f0b902eb3252135787821c20161b7e1a4bd9",
      "bytes": 887
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/bindings/peer_artifacts/6",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-provenance-c-FIRST.md",
      "sha256": "543e7cbba9b13f33a8823f70050de0350afa92e2875e87c701f72c43633005ce",
      "bytes": 2750
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/bindings/peer_artifacts/7",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-provenance-c-pins.json",
      "sha256": "dd04f85fae69bc5bb0d2c550d9f5f773fc8d9fedef04df7714a6f2c19b2e284c",
      "bytes": 2796
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/bindings/peer_artifacts/8",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-provenance-c-freeze.json",
      "sha256": "16f3bd7e885796ca6a972fc904e98b2356a7ca8e3a677abc3dd4cb1829aa16e8",
      "bytes": 1113
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/sources/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-worker-proposal-v2/run_native_e2e.py",
      "sha256": "dc92b55891acd8856062c30d17349a8be2db75c97ebc9c1f60c0bfa9d4b216e9",
      "bytes": 26388
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/sources/1",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/scripts/train_development.py",
      "sha256": "f4d19483532318b25c2adb51734ec347e772d3441edca944c5c91ce791cacde9",
      "bytes": 12640
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/sources/2",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/scripts/development_training.py",
      "sha256": "9f7d9ab7c1f69fd0726d657791059b4a0c5270bf7a32da898602eaf84ccffcc9",
      "bytes": 5590
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/sources/3",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-native-cli-tiny-native-e2e-runner-proposal-v1/child.py",
      "sha256": "673454b27ce15016f3f4ce8691b0484d2d88318434688a3a6aba1e892c7bfa57",
      "bytes": 11366
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/sources/4",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-native-cli-tiny-native-e2e-actual-failure-v1.json",
      "sha256": "0dc7c6491a238e1a20cc56cd6e69d7e7e86d59dc61888fc9b001b6b3e18bcc1b",
      "bytes": 4584
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/sources/5",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-publication-476dfd6-final-actual-acceptance-v1.json",
      "sha256": "25e955ae8f6b45d21ba76eeb27748dd8931c57c5716753d26126477ff7b86b98",
      "bytes": 1724
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/instructions/0",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/personal-agent-system/.agents/skills/research/SKILL.md",
      "sha256": "452334717864a950b44ec991b96bf65edeb2e263a2c098560e0b6d9fd31b2e34"
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/instructions/1",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/personal-agent-system/docs/agents/coordination.md",
      "sha256": "0396d99b46adc00857f9b2f5623f8beb5e50acaed2aeb9acfed7d1b2dfa772fb"
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "json_location": "/instructions/2",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/personal-agent-system/docs/agents/verification.md",
      "sha256": "d84015a05b7ebc9c4bdc570e75e0a62fbcbe134217a367715fbf5e2acc1e69ec"
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-freeze.json",
      "json_location": "/files/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-skeptic-v1.md",
      "sha256": "5ac30a63808132b58c7afeed21b25f2ca188b7ac4b27d2b5923e8a28ce5c92c1",
      "bytes": 3202
    },
    {
      "artifact_origin": "/tmp/tlab-wave078-skeptic-v1-freeze.json",
      "json_location": "/files/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave078-skeptic-v1-pins.json",
      "sha256": "c8a2e68fa3b099923b8e919c93ee095a63d596761ab21fc17276997f13bf3c57",
      "bytes": 5680
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave079-authors-readback-v1.json",
      "json_location": "/references/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-deliverable-a-FIRST.md",
      "sha256": "1362b7d8cc60e21a54b0894aba49489925edae5cf59f68a0f5053fb31792a481",
      "bytes": 1948
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave079-authors-readback-v1.json",
      "json_location": "/references/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "sha256": "68fdb348faaf122b031cbf58e2ab45dcea921896f048f8e58ced4d03b0609121",
      "bytes": 6211
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave079-authors-readback-v1.json",
      "json_location": "/references/2",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-deliverable-a-freeze.json",
      "sha256": "1a744407a1d103df6d1eed4381e6921284e24ffba3474271d3e6ad3c908ad25b",
      "bytes": 497
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave079-authors-readback-v1.json",
      "json_location": "/references/3",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-inference-b-FIRST.md",
      "sha256": "89b4136b01c67dca244e3c419dfd71ea9cc191e6dab9c69f2c4d22d2cd208499",
      "bytes": 1884
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave079-authors-readback-v1.json",
      "json_location": "/references/4",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-inference-b-pins.json",
      "sha256": "82d0fb2cd45292af0d1441ee5d9bb0e9a78634b6f3bf56524fcd183518fced4b",
      "bytes": 2846
    },
    {
      "artifact_origin": "/tmp/tlab-root-wave079-authors-readback-v1.json",
      "json_location": "/references/5",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-inference-b-freeze.json",
      "sha256": "e44d9c089f90ada659f57e1f001c9cfdf55eb7bf2444227f03de89f32add2b6c",
      "bytes": 559
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-shared-context-v1.json",
      "sha256": "621c41df250a1d0d54e50d1cee411e016493a874750c6e84c97159dfc5c1bcec",
      "bytes": 2569
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-research-campaign-checkpoint-20261016-1927-v1.json",
      "sha256": "bbc33359583688dba71eeecece9e7d16b6c3979b44badc0c21dc07336ca48bae",
      "bytes": 2627
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/2",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog.md",
      "sha256": "23308555e780da9583b4061fc4eef0ca905518a1bfedda3542849bc0fdd425be",
      "bytes": 205254
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/3",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/progress-report.md",
      "sha256": "37df4772e3d4a106c87d0aba35208192bde2b7669688874ae027ee94ad5dd66d",
      "bytes": 30311
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/4",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/experiments/development-training.md",
      "sha256": "456535a47409567dbb104669a517bf731d156cdde89fd7fa6e8ec54b859808a0",
      "bytes": 11128
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/5",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/evidence/task1-deliverable-audit-071/tlab-task1-deliverable-audit-071.md",
      "sha256": "c958b022a3d8c515cd4b6737d193699bad696f915f3c758b6e311bbb8675742b",
      "bytes": 6557
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/6",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/evidence/task1-deliverable-audit-071/tlab-root-task1-deliverable-audit-071-adoption-v1.json",
      "sha256": "89eb747bd823e2ac2be2cb3925101de3ab3a9ed479b70988977ea3bf3825f252",
      "bytes": 1983
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/7",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/public018-complete-output-acceptance.md",
      "sha256": "16669dda3c3c58cc8969cb01ac3f30c545f452456aff501539fc8b68e6cda2d6",
      "bytes": 4018
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/8",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/native-cli-tiny-QYC-result.md",
      "sha256": "fd94a80660ba3420f6f278042c73b2d53724f0f05996103f71b741b7b4ab4a67",
      "bytes": 5374
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/9",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/native-cli-tiny-F-result.md",
      "sha256": "a3f2ce83e45dd4ec59cae67a54eac1f139c761b25d4b58e1d777b69e77295b96",
      "bytes": 6559
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/10",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/native-cli-tiny-verifier-result.md",
      "sha256": "b340d8a2a9a5b0bfc3635409a8c380549341ac802603979bf9a103655673f427",
      "bytes": 3548
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/11",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/README.md",
      "sha256": "8f7f07dfcfa458d6d0b2d64d9d1b712b26f9a4590e03f57289fed40f3ee5384e",
      "bytes": 21405
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/12",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/task1-requirements.md",
      "sha256": "643de5b7a11ccb5b6bb0f1b862b96457dbdf1d9342626ac5e015ef2547b53aeb",
      "bytes": 3638
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/13",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/experiments/automation-walkthrough.md",
      "sha256": "e64341e24a9ed62e8854db734f869f1b11b5614b738673e7e9d0578b09fabe2c",
      "bytes": 2824
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "json_location": "/source_pins/14",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/experiments/fresh-clone-reproduction.md",
      "sha256": "b45c55de96a8253aad4bdcd1693e4cae02c4a29d613a700f8af149b2e7359712",
      "bytes": 8968
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-freeze.json",
      "json_location": "/report",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-deliverable-a-FIRST.md",
      "sha256": "1362b7d8cc60e21a54b0894aba49489925edae5cf59f68a0f5053fb31792a481",
      "bytes": 1948
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-deliverable-a-freeze.json",
      "json_location": "/pins",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "sha256": "68fdb348faaf122b031cbf58e2ab45dcea921896f048f8e58ced4d03b0609121",
      "bytes": 6211
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-inference-b-pins.json",
      "json_location": "/source_pins/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-shared-context-v1.json",
      "sha256": "621c41df250a1d0d54e50d1cee411e016493a874750c6e84c97159dfc5c1bcec",
      "bytes": 2569
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-inference-b-pins.json",
      "json_location": "/source_pins/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-research-campaign-checkpoint-20261016-1927-v1.json",
      "sha256": "bbc33359583688dba71eeecece9e7d16b6c3979b44badc0c21dc07336ca48bae",
      "bytes": 2627
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-inference-b-pins.json",
      "json_location": "/source_pins/2",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog.md",
      "sha256": "23308555e780da9583b4061fc4eef0ca905518a1bfedda3542849bc0fdd425be",
      "bytes": 205254
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-inference-b-pins.json",
      "json_location": "/source_pins/3",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/progress-report.md",
      "sha256": "37df4772e3d4a106c87d0aba35208192bde2b7669688874ae027ee94ad5dd66d",
      "bytes": 30311
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-inference-b-pins.json",
      "json_location": "/source_pins/4",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/experiments/development-training.md",
      "sha256": "456535a47409567dbb104669a517bf731d156cdde89fd7fa6e8ec54b859808a0",
      "bytes": 11128
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-inference-b-pins.json",
      "json_location": "/source_pins/5",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/adaptive-tree-results.md",
      "sha256": "a13c7bd088eda0c23e9b63e4c81958a6beada0bfe9226364ad9ba724741cc807",
      "bytes": 8055
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-inference-b-freeze.json",
      "json_location": "/FIRST",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-inference-b-FIRST.md",
      "sha256": "89b4136b01c67dca244e3c419dfd71ea9cc191e6dab9c69f2c4d22d2cd208499",
      "bytes": 1884
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-inference-b-freeze.json",
      "json_location": "/pins",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-inference-b-pins.json",
      "sha256": "82d0fb2cd45292af0d1441ee5d9bb0e9a78634b6f3bf56524fcd183518fced4b",
      "bytes": 2846
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/author_bindings/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-deliverable-a-FIRST.md",
      "sha256": "1362b7d8cc60e21a54b0894aba49489925edae5cf59f68a0f5053fb31792a481",
      "bytes": 1948
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/author_bindings/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-deliverable-a-pins.json",
      "sha256": "68fdb348faaf122b031cbf58e2ab45dcea921896f048f8e58ced4d03b0609121",
      "bytes": 6211
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/author_bindings/2",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-deliverable-a-freeze.json",
      "sha256": "1a744407a1d103df6d1eed4381e6921284e24ffba3474271d3e6ad3c908ad25b",
      "bytes": 497
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/author_bindings/3",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-inference-b-FIRST.md",
      "sha256": "89b4136b01c67dca244e3c419dfd71ea9cc191e6dab9c69f2c4d22d2cd208499",
      "bytes": 1884
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/author_bindings/4",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-inference-b-pins.json",
      "sha256": "82d0fb2cd45292af0d1441ee5d9bb0e9a78634b6f3bf56524fcd183518fced4b",
      "bytes": 2846
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/author_bindings/5",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-inference-b-freeze.json",
      "sha256": "e44d9c089f90ada659f57e1f001c9cfdf55eb7bf2444227f03de89f32add2b6c",
      "bytes": 559
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/0",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-shared-context-v1.json",
      "sha256": "621c41df250a1d0d54e50d1cee411e016493a874750c6e84c97159dfc5c1bcec",
      "bytes": 2569
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/1",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-root-wave079-authors-readback-v1.json",
      "sha256": "9224b3679cf7d07ab3ba8d8a91446fa933298e71ac244ea84ee1da58ad4c5e42",
      "bytes": 1237
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/2",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/task1-requirements.md",
      "sha256": "643de5b7a11ccb5b6bb0f1b862b96457dbdf1d9342626ac5e015ef2547b53aeb",
      "bytes": 3638
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/3",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/experiments/automation-walkthrough.md",
      "sha256": "e64341e24a9ed62e8854db734f869f1b11b5614b738673e7e9d0578b09fabe2c",
      "bytes": 2824
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/4",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/public018-complete-output-acceptance.md",
      "sha256": "16669dda3c3c58cc8969cb01ac3f30c545f452456aff501539fc8b68e6cda2d6",
      "bytes": 4018
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/5",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/adaptive-tree-results.md",
      "sha256": "a13c7bd088eda0c23e9b63e4c81958a6beada0bfe9226364ad9ba724741cc807",
      "bytes": 8055
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/6",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/evidence/task1-deliverable-audit-071/tlab-task1-deliverable-audit-071.md",
      "sha256": "c958b022a3d8c515cd4b6737d193699bad696f915f3c758b6e311bbb8675742b",
      "bytes": 6557
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/7",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/README.md",
      "sha256": "8f7f07dfcfa458d6d0b2d64d9d1b712b26f9a4590e03f57289fed40f3ee5384e",
      "bytes": 21405
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/8",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/experiments/fresh-clone-reproduction.md",
      "sha256": "b45c55de96a8253aad4bdcd1693e4cae02c4a29d613a700f8af149b2e7359712",
      "bytes": 8968
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/9",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/real015-heldout-results.md",
      "sha256": "e74fc832710b8911ff986849d9457bffad88cf2b7f264f19c0f7a7c9f68017c8",
      "bytes": 4865
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/10",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/experiments/development-training.md",
      "sha256": "456535a47409567dbb104669a517bf731d156cdde89fd7fa6e8ec54b859808a0",
      "bytes": 11128
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/11",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/progress-report.md",
      "sha256": "37df4772e3d4a106c87d0aba35208192bde2b7669688874ae027ee94ad5dd66d",
      "bytes": 30311
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/12",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/docs/experiments/adaptive-tree-selection.md",
      "sha256": "333e3a503f129426af097b46320b61b92c9cbd8fe7698f6641fb9459a12f6e21",
      "bytes": 4446
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/13",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/scripts/adaptive_tree_selection.py",
      "sha256": "4adcde3add3bf878a16831c109b8dc3ee141932dbb7c50ab663adc8e6ad2ecf6",
      "bytes": 18580
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-pins.json",
      "json_location": "/source_pins/14",
      "reference_only_body_not_copied": true,
      "path": "/Users/mdpospelov/tlab-recsys-2026/scripts/development_training.py",
      "sha256": "9f7d9ab7c1f69fd0726d657791059b4a0c5270bf7a32da898602eaf84ccffcc9",
      "bytes": 5590
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-freeze.json",
      "json_location": "/report",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-skeptic-v1.md",
      "sha256": "182f5ecca41c7a05fb0c92ed41ac40706714d110e7d7a5f5e9e2d8e3342b3217",
      "bytes": 2570
    },
    {
      "artifact_origin": "/tmp/tlab-wave079-skeptic-freeze.json",
      "json_location": "/pins",
      "reference_only_body_not_copied": true,
      "path": "/tmp/tlab-wave079-skeptic-pins.json",
      "sha256": "a017ae712b27669215421f014254010ba98a90b2d6ca7199118ff165f057b267",
      "bytes": 8666
    }
  ],
  "source_reference_bodies_reverified_by_this_preparer": false,
  "reason": "Original review/adoption hashes are verified; referenced private/project bodies are not opened or embedded by this preparation.",
  "canonical_target": "docs/research-lab/round079-engineering-checkpoint.md",
  "historical_SOURCE_reviews_not_whole_CODE_or_native_acceptance": true
}
```

## Фактическая Root CODE-приёмка — новый итог

Источник: `/tmp/tlab-root-native-metadata-fix-v2-CODE-adoption-v1.json`; SHA256 `11a808e43205d8a6c69bf4d16472e8b0215db912069409e15b2ad6cdc3ee4ec5`; 5357 bytes.

````json
{
  "utc": "2026-10-16T20:06:43.625530+00:00",
  "status": "METADATA_FIX_V2_SOURCE_AND_13_UNIQUE_CODE_UNIT_METHODS_ACCEPTED_NOT_INSTALLED_NOT_NATIVE",
  "candidate_files": [
    {
      "V1_bytes_identical": true,
      "bytes": 35665,
      "path": "scripts/train_baselines.py",
      "sha256": "626addc85304d926611301c764f7010b4a2b42fedf313f5f319e20264b271d8b"
    },
    {
      "V1_bytes_identical": true,
      "bytes": 12664,
      "path": "scripts/train_development.py",
      "sha256": "2ec59f282a9d83e570b8642cabb4fc96b4cdf8ed5fb95248f93916df9d77d4c6"
    },
    {
      "V1_bytes_identical": true,
      "bytes": 20090,
      "path": "tests/test_train_development.py",
      "sha256": "34c8b794742e40c7d923d7d9d92ed3dc47a3795531241538a4f9895f3c74ec17"
    },
    {
      "bytes": 11687,
      "new_public_file": true,
      "path": "tests/test_environment_snapshot.py",
      "sha256": "38ef0a256ac6326d66acd79c930ce3f926c529afaaaed4206b88ec43b8fd3042"
    }
  ],
  "ordinary_CODE": {
    "root_actual_checks": "c4910dCLOSED0 verifies raw12stdout/receipt/report/hash/sourcefreshness; d21212 reads complete12OKstderr; priorb3c330 verified all16publicproof inventory",
    "terminal": "a4330bCLOSEDexit0",
    "unit_methods_unique": 12,
    "child_reaped": true,
    "application_denials": [],
    "actual_load_runtime_calls": 0,
    "process_network_events_application": 0,
    "child_CPU_seconds": 0.33142,
    "child_launch_to_reap_wall_seconds": 0.382212582975626,
    "python": "3.12.14",
    "numpy": "2.5.4",
    "real_ML_body_imports": false,
    "real_data_read": false,
    "scope": "ActualCLI/helper orchestration with syntheticmodel/selector/data doubles and actualNumPy; publicenvironmenthelper isstubbed here"
  },
  "public_regression": {
    "unique_methods": 1,
    "terminal": "d02e35CLOSED0",
    "actual_helper_AST": "Matchedrealfunctionbody, coldstdlibplatformcache, explicitversiondoubles; kernelno forbiddenevents, legacyactualDarwin/devnull witness; dependency11mismatchchecks",
    "scope": "No actualproject/MLmodulebodyimport; otherplatformnative/WindowsUNRUN"
  },
  "total_unique_unit_methods": 13,
  "prior_failures": "V1guardfalsepositive4pass1error7unrun;V2all12OKguardFAILnofinalreceipt;V3all12OKguardFAILprimitive30denials. Retainedfailures, notextraunique successes. V4repairedguardpassed.",
  "reviews": "Threeindependent source/compatibility/deltareviews ofpubliccandidate; narrowprivateguardrevisions independentlyreviewed; Rootactualfiles/rawresultschecked. No outstandingcodefindingwithinreviewedscope.",
  "native": "Historicalone50CPU65wall CLIattemptFAILEDknownclosedconsumed beforePrepared/fit; correctednativeE2E and callback-abortUNRUN. No retry/residual/nativegrant. No actual model quality/globaloptimum/earlystop or dependencylock witness byCODEtests.",
  "canonical_Git": "No install/stage/commit/network; codecandidate unchanged; local36autoreviewrejectbeforecopy stillunresolved. Rootauthorizes preparation ofreviewableLOCAL41only, notexecution orfuturepush.",
  "references": [
    {
      "path": "/tmp/tlab-native-metadata-fix-proposal-v2/manifest.json",
      "sha256": "9dd812c25e281869c455022ed353bbfc0a191da35af4709b3bc26b38468507fd",
      "bytes": 7413
    },
    {
      "path": "/tmp/tlab-native-metadata-fix-proposal-v2/proof-receipt.json",
      "sha256": "5ccc330d4697b0347f091d28fda745f67f11a0bbd9135c4a4097b1ab958a9afe",
      "bytes": 2218
    },
    {
      "path": "/tmp/tlab-native-metadata-fix-independent-review-v1.md",
      "sha256": "973bd92f9a803cc9f763db7cd0998229b1e4cc02e5426611a8b9b987f5413fd8",
      "bytes": 3182
    },
    {
      "path": "/tmp/tlab-native-metadata-fix-compatibility-review-v1.md",
      "sha256": "dc2c20859818a8c35b3a1a4f05f37c9c5ca668dff68ad65d0e0c4955e5e9dc1d",
      "bytes": 3781
    },
    {
      "path": "/tmp/tlab-native-metadata-fix-v2-delta-independent-review-v1.md",
      "sha256": "cadebfafaf0a236b4e52bb1139f1b3bcaf4588fc1f85751c6edc848ca844ad70",
      "bytes": 2871
    },
    {
      "path": "/tmp/tlab-metadata-fix-fakeml-code-check-v4/report.json",
      "sha256": "f684ce969b7f0340210a511feebdcfea53f2fdbfb618b0137470cfb45964f4fb",
      "bytes": 13841
    },
    {
      "path": "/tmp/tlab-metadata-fix-fakeml-code-check-v4/child-receipt.json",
      "sha256": "9cf021ecfcede9f5c00c90742a48aeb56a1f1f345c8247f141a91b90d1512ac3",
      "bytes": 5175
    },
    {
      "path": "/tmp/tlab-metadata-fix-fakeml-code-check-v4/raw-stderr.txt",
      "sha256": "a9f873e42b9ce95d77e15c84f6f8c0587596419a0c053b6daabb8f48892c4d10",
      "bytes": 2371
    },
    {
      "path": "/tmp/tlab-fakeml-guard-v4-independent-review-v1.md",
      "sha256": "25e1691c457492c417c4134bb9745f6867b56b4f01d539d5e15ca816d75e4850",
      "bytes": 2173
    },
    {
      "path": "/tmp/tlab-metadata-fix-fakeml-code-check-v1/freeze.json",
      "sha256": "f606a62ebcb930ed1af0e279512a83287ec7eee4a7e6be3a4d35ea239cc0b1dd",
      "bytes": 1988
    },
    {
      "path": "/tmp/tlab-metadata-fix-fakeml-code-check-v2/actual-freeze.json",
      "sha256": "344936f1642ff3bf4fd7ed2b1934eca44d6f32c437e058360c19803d710edae6",
      "bytes": 2335
    },
    {
      "path": "/tmp/tlab-metadata-fix-fakeml-code-check-v3/actual-freeze.json",
      "sha256": "c2127f102c8a55f130eb6824093928a3b130d1eadea25708ad32061b087e38fa",
      "bytes": 2647
    }
  ]
}
````
