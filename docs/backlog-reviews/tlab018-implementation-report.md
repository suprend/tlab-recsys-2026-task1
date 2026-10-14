# TLAB-018 first iteration: frozen implementation handoff

15 октября2026. **Готово к независимому code/fault review, не принято и не запущено на реальных данных.** Изменены ровно три назначенных новых файла: [verifier](../../scripts/verify_development.py), [scoped tests](../../tests/test_verify_development.py), [workflow](../experiments/verification-workflow.md). Git/dependencies/005/008/017/009 code и реальные artifacts/acceptances не менялись.0fits,0real source scans,0real acceptance writes. Fixtures и их synthetic mock approvals существуют только во временных каталогах тестов.

Frozen SHA256:

- script `9d0e30c61def76206f150054566399433357e401c22a0a7a9f870e5ba7282bb6`;
- tests `5373fe2d99e0cca215f2b34df1cbd2bbf6809a38f97e36fb8ebdd7a7b2988c5d`;
- documentation `4398525b95544e5c7ac320af61e7df6d60becfb73246031279a4db855fc53507`.

## Actual result

Только `unittest` discovery pattern `test_verify_development.py`, repo venv/PYTHONDONTWRITEBYTECODE=1: **25PASS11,813s, exit0**. Измеренная stdlib resource invocation:11,851276s wall,13,015154s processCPU,151306240bytes process peakRSS. Это всё tiny source/Q/Y/C/F и fault fixtures, без CatBoost или моделей. DuckDB connections тестов и verifier явно threads2. Полный suite не запускался; чужие WIP не проверялись.

Первоначальные23scoped PASS10,480s/152338432bytes не являются приёмкой final version. Внешняя `/usr/bin/time -l` после другого успешного23-test child run завершилась ошибкой sandbox sysctl; финальные показатели выше получены стандартными process counters с exit0, не предположены по wrapper error.

## Публичный scope

Readonly API `verify(project_root,expectations_path)` и CLI с обязательными project-root/expectations, optional exclusive evidence-out. Existing external scope reviewed_development_collection — input expectation, не созданный fresh hash approval. Все пути confined, включая symlink escape; machine root не зашит. Default не пишет файлы. Explicit evidence не перезаписывает существующий файл. Acceptance/regeneration/pre-acceptance source mode отложены: flags их не имитируют.

Поддержка ровно reviewed protocolv1 clock24h/[t,t+H), train/selection, точная typed manual18 registry. Confirmation/final/009/newgrammar unsupported. Exact phase/shard cover, identity↔physical source/registry/code/phase pins, child QYC→F lineage/selection definition, manifests/seals/external shard approval, exact schema/types, final rehash. Loaded/installed DuckDB совпадают с lock; shared validator code совпадает с pinned code, собственный verifier SHA записан в evidence.

Expected Q/Y/C вычисляются независимым прямым source SQL: past eligibility/bottomSHA до labels, diagnostics/coverage/maturity, fullY/cold targets, buyer popularity/recent ties/no-refill. Bidirectional EXCEPT ALL, unique/orphan/exact-range checks exhaustive. F rowset/retrieval columns exact/exhaustive;18numeric formulas и17metadata/support/mask/coverage/age values проверяются только на deterministic source-row samples. Counts/strata/uncovered empty support и tolerance явные; sampled numeric F не называется exhaustive. Production materializer/helpers и legacy temporary scripts не вычисляют expected values.

## Material audit и meaningful faults

TDD RED→GREEN зафиксировал missing module, отсутствие проверки fresh-resealed aggregate counts, отсутствие явного population evidence и runtime-version check. Сохранены fresh-resealed bad F value/category denominator вне C, потеря Y/zero-purchase Q, cold Y вне C, rank/type/mask/duplicate F faults; шесть resealed plan/typed-registry subcases отказывают. Golden complex source включает mixedNULL global bucket, historical category move, offC category denominator, strict peers, lower-bound expiry/fullprefix recency; reordered peers/future suffix проходят. Fresh root с пробелами не зависит от прежнего root. Zero-Y и empty-C Q сохранены.

Перед freeze coordinator нашёл P1 в первой версии script9310433…: success выставлялся до cleanup и final resource measurement. Actual fault tests подтвердили fakeclose wall+700/CPU+700/RSS>512MiB→false verified, escaping closeOSError и отсутствие гарантированного failed evidence при counter failure. **Исправлено:** status verified выставляется после cancel/close/postcleanup budget check/summary/final check. Close/summary errors дают VerificationError с failed partial evidence; недоступные counters null/partial_unavailable, не0. Все пять новых fault subcases проходят без sleep/реального превышения памяти. Исходный finding сохранён в workflow audit; final SHA отличается.

Обнаруженная upstream017 граница не исправлялась: fully empty raw source приводит aggregate_collection к `Missing or duplicate daily report coverage`. Regression проверяет, что такой failed/incomplete bundle не получает verified018 evidence. Положительный complete-empty fixture не подделан; это отдельная future bugtask. Accepted nonempty train/selection не менялись.

## Remaining gates

Independent review/fault reproduction018 до любого real execution. Tiny≤5min/512MiB resource evidence не benchmark реальных collections;128MB engine setting и cooperative guards не OS hard cap. All-source numeric F, source logging completeness, clean-environment install, real regeneration/portability и009/extensions не доказаны. Existing-sealed workflow сознательно уже будущего round008 proposal; следующий acceptance-writing mode требует отдельно reviewed decision binding exact policy/evidence/pins, не свежей печати producer. Общий research/model budget не расширен.
