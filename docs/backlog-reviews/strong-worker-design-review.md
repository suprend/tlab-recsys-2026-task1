# Independent019 worker-design review — CHANGES REQUESTED

2026-10-15. Read-only review `tlab019-worker-design.md` против canonical backlog019/009 policy. Код/execution ещё не реализованы/не приняты.0datasets, matrices, nativePool, fits, source scans, actual approvals. Current009 ONEfit/result не читались. Fresh-child orchestration принимается как направление; ниже обязательные уточнения **до exact implementation/execution approval**, отдельно от будущих tests.

## P1: proposed tie law меняет уже замороженную selection policy

Draft одновременно обещает сохранить agreed incumbent/grid policy и предлагает total symmetric-tree leaves→trees/depth→strongerL2→gridorder. Canonical `docs/backlog.md:314` уже фиксирует другой порядок: eligible set с score≥**global maximum−1e−12**, затем fewer trees, smaller depth, incumbent если остальное равно, configID. Leaf-count first может предпочесть150depth4=2400leaves вместо50depth6=3200leaves, хотя canonical предпочитает50trees. StrongerL2 также добавляет незаявленное преимущество и меняет incumbent tie.

Нужна явная замена draft tie paragraph точным canonical law. Не использовать попарное fuzzy comparison: сначала global maximum/tie set, затем deterministic complexity keys. Eligible incumbent — existing00850/6000 на rejected009 schema либо accepted00950/6000 на retained schema; без refit. Winner задаёт **те же** population/Q/C/Y/weights/features/settings/trees всем016I/R. None feasible→STOP/no refill. Новая tie policy могла бы быть отдельным решением, но данный orchestration seam не даёт её менять после freeze.

## P1: deadline/kill/reap contract ещё отсутствует

Фраза «child bounded by remaining wall» недостаточна для executor. [Python subprocess](https://docs.python.org/3/library/subprocess.html#subprocess.Popen.communicate) указывает, что timeout `Popen.communicate` сам не убивает child; `run(timeout=...)` убивает/ожидает прямого child, но из этого не следует cleanup всего descendant tree. До реализации зафиксировать:

- Один worker at a time, absolute parent deadline и child deadline=min(phase allowance,parent remaining), включая launch/import/cleanup.3600wall — **предложение нового stop boundary**, ещё не accepted value; это не замена60actualCPUmin.
- На deadline/interrupt/error — TERM в изолированную session/process group, заранее ограниченный grace, затем KILL, bounded drain/reap; cleanup в finally при любой parent exception. [start_new_session](https://docs.python.org/3/library/subprocess.html#subprocess.Popen) и [os.killpg](https://docs.python.org/3/library/os.html#os.killpg) дают POSIX primitives, не универсальную гарантию против escaping descendants.
- Worker не запускает OS subprocesses: DuckDB/CatBoost threads остаются в том же process accounting scope. Если descendants разрешены, нужны их cleanup **и** достоверный CPU scope; process-group kill сам по себе не делает orphan CPU учтённым parent CHILDREN. Unexpected/unreaped worker или неизвестный usage→failed/unknown/STOP, не нулевой cost и не accepted complete.
- stdout/stderr идут в bounded/file-backed evidence либо своевременно drain; unbounded capture не должен обходить RSS, заполненный PIPE не должен блокировать wait. Missing/corrupt receipt, negative signal exit и knownfailed marker fail closed; raw signal kill нельзя автоматически назвать OOM.

Grace/kill/reap/persistence cost остаётся внутри общего60min и disclosed wall boundary. Невозможность уложиться/измерить cleanup не даёт free tail или следующую попытку. Cooperative native checks могут заметить превышение поздно: сохранять фактическое превышение/failed result, не обещать математически hard CPU/RSS cap.

## CPU accounting и RSS: направление верно, scope нужно зафиксировать

Свежий gate child решает реальную проблему монотонного peakRSS: освобождение arrays не сбрасывает исторический high-water mark. Только после reap/receipt validation одного26000 matrix+Pool gate permitted resource/cardinality failure ведёт к6000; integrity/schema/NULL/API/pin failure→STOP. Новый full gate/поздний6000 fit fallback запрещены. GatePASS не гарантирует Newton/300tree fit feasibility.

[Python resource](https://docs.python.org/3/library/resource.html#resource.RUSAGE_SELF) подтверждает: SELF включает threads родителя, CHILDREN — terminated/waited-for children. В свежем dedicated parent допустим общий ledger `ΔSELF.user+system + ΔCHILDREN.user+system`; child self receipts — reconciliation/diagnostics, **не** ещё одно слагаемое. CHILDREN cumulative delta нельзя повторно прибавлять на каждом worker. Failed/killed/reaped child CPU оплачивается так же, imports/terminal tails включены в invocation total. Другие children того же parent недопустимы либо явно входят в тот же accounting scope.

Пока child жив, CHILDREN ещё не содержит его затрат. Поэтому remaining cap, выданный при launch, не является текущим global balance: parent polling/verification тоже расходует CPU. Зафиксировать parent+child cooperative checks/overrun policy, final measurement после reap, STOP до следующего launch при exhausted/unknown cap. Нельзя запускать fresh worker с новым900/3600CPU cap независимо от уже потраченного019total. Старый008 unknownCPU не вычитать из выдуманного остатка.

Draft явно задаёт8GiB **per worker**. Это не измерение aggregate parent+worker RSS. Parent должен оставаться bounded orchestration-only, без сохранения matrices/Pool/model между workers; публиковать parent и child peaks. Если прежний8GiB имел смысл всего simultaneous job, per-process8GiB alone его не обеспечивает: scope требует явного согласования, а не молчаливого resource expansion.

## P1 clarification: consumption и partial checkpoints

One project-wide claim/один gate/четыре non-refillable arm slots и максимум12новыхlooks сохранены. До реализации уточнить per-slot immutable allocation **до preparation/spawn** и per-look reservation перед fullY evaluation. При worker crash после50/150 scores уже увиденные looks остаются consumed, даже если receipt/output невалиден. Не объявлять failed worker нулёмlooks и не повторять его другим output root.

Canonical выбирает feasible completed checkpoints. Draft не определяет, eligible ли отдельно проверенный50tree prefix при последующем failure150/300. Нужен заранее фиксированный закон trusted checkpoint completeness; уже потреблённые looks/failures сохраняются при любом решении. Если требуется успешный полный300tree worker прежде всех scores, это тоже нужно назвать явно и не выбирать после результатов. Prefix save/copy/shrink не refit; должен сохраняться исходный300tree model, exact tree counts/prediction equality каждого prefix, budget на всё copy/predict/verify.

## Future implementation gates, не новые эксперименты сейчас

После исправленного design freeze потребуются tiny mocked lifecycle faults: gateRSSFAIL→fresh6000worker; gateintegrityFAIL→zero fits; import crash/TERM-ignoring child/receipt failure с reap+CPU; exhausted cap→unattempted remaining slots; non-transitive near ties→canonical global tie set; failed-later-checkpoint consumption; stale knownfailed receipt rejected; config/context tampering до data. Full plan/input/feature-choice/incumbent/env pins и exact external worker scope должны подтверждаться parent и child; standalone `--worker` не создаёт free fit без slot token. Source/formula verification и saved-prefix fidelity требуют отдельной substantive actual audit после code acceptance.

Retrospective22–23 development и decision availability после использованных labels24 изложены правильно. Actual2026 sealing до reserved25targets и simulated availability/positive compute gap остаются разными gates; старые collection availability поля adaptive019decision не удостоверяют. Дизайн не авторизует fit, не гарантирует power/quality и не расширяет4attempts/12looks/60actualCPUmin.
