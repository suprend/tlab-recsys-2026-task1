# TLAB-008: независимый повторный review CPU smoke runner

15 октября 2026. **Вердикт: material changes requested по новому invariant согласованности collection plan.** Два исходных P1 исправлены и независимо воспроизведены как отказы; исходный [audit](tlab008-training-review.md) сохраняется. Новый review не разрешает real fits или confirmation. Проверены фактические [runner](../../scripts/train_baselines.py), [tests](../../tests/test_train_baselines.py), [config](../../configs/models/cpu-smoke.json), [документация](../experiments/boosting-baselines.md). Repo/Git/code/deps/data не менялись. Дополнительные native fits — tiny synthetic; поддельные approvals использовались исключительно внутри временных синтетических fixtures, без real collection/artifact approval.

## Frozen версия и actual tests

SHA-256 совпали с handoff:

- runner `660cc62268093e0aa81e23ec4c46761a1487ef0997d8db32eb1ec679cd97543e`;
- tests `c0be599ec226de4a188695e23d14009670599d2983b8fb63f7abfef18bb1e9ee`;
- config `d8140e4581e6aa769af75f3638a697bb7224943ce1f6dcd1c5cd4588ed27c14a`;
- documentation `245e6e2e6e434f46e918b2754d0c80efa50b5b043154e8875aa84d9111855129`.

Repo venv, PYTHONDONTWRITEBYTECODE=1, `unittest discover -s tests -p test_train_baselines.py -v`: **19 PASS, 1,192 секунды, exit0**. Full suite142, заявленный owner, не повторялся; прочие WIP вне scope. Ни real fitting, ни real collection scans не выполнялись.

## Исходные P1 закрыты

Canonical global `artifacts/fit-claims/run_id.json` создаётся O_EXCL до fit, fsync, не удаляется после ошибки; смена output root не даёт дополнительные слоты. Независимый повтор исходного repro: первый synthetic run завершает два actual tiny native fit, второй root получает FileExistsError, fit_attempt_count0; байты первого report и global claim неизменны. После actual native callback TimeoutError первый run имеет failed/attempts1/no CBM; тот же approval в другом root также отвергнут до fit. Это закрывает relocated-success и relocated-partial replay без ручной порчи ledger.

Первый validated config теперь сравнивается с verified plan до approval и claim; effective config берётся из manifest. Независимая замена iterations1→2 между первым parse и verified plan заканчивается ValueError `Config changed between initial parse and verified fit plan`, failed audit, fits0/claims0. Второй fault меняет config после `_config_snapshot` внутри настоящего `prepare_fit_plan`: отказ `Config changed during fit-plan preparation`, claims0. Snapshot вычисляет SHA из тех же прочитанных bytes. Исполненный config, identity и approval больше не расходятся данным способом.

Budget fault: preparation спит1,05с при wall_seconds1; весь run завершается TimeoutError до fit, failed/attempts0, claim сохранён, measured elapsed1,078с. Actual native callback fault останавливает первый fit и не начинает второй. Guard остаётся cooperative: проверки до/после SQL/Pool/predict/export и между native iterations, без OS hard kill. Peak/RSS и реальная full-size стоимость этим не измерены.

## Новый material invariant: свежая печать не доказывает внутреннюю согласованность

В [verify_collection](../../scripts/train_baselines.py#L94) canonical identity digest проверяется, каждый physical execution pin проверяется, exact approval scope проверяется. Однако отсутствует связь между тремя представлениями одного input: identity, execution_inputs и physical phase body. В частности, source_sha256/registry_sha256/code_hashes из identity не сравниваются с pins, phase не сравнивается с содержимым phase_path, множество execution input keys не ограничено canonical producer set.

Независимый repro использует настоящий synthetic017 lifecycle из CollectionAcceptanceTests. После получения complete fixture меняется ровно один declarative input, canonical collection_id пересчитывается, копии plan/state размещаются под новым ID, report/approval IDs и соответствующие physical hashes обновляются. Child manifests, данные, их seals и действительные source bytes не меняются. Все пять отдельных случаев **ACCEPTED** actual `verify_collection`:

1. `identity.source_sha256 = "a" * 64`, при прежнем source_path и его прежнем actual pin.
2. `identity.registry_sha256 = "b" * 64`, при прежнем registry file/pin.
3. `identity.code_hashes["scripts/manual_features.py"] = "c" * 64`, при прежнем actual code/pin и child lineage.
4. `identity.phase.name` заменён, тогда как pinned physical phase file содержит исходное имя; shard protocols остаются допустимыми.
5. В execution fingerprints добавлен произвольный synthetic unrelated file, и тот же pin включён во внешний approval.

Это не демонстрация обхода чужой криптографической подписи: approvals здесь обычные внешние JSON, намеренно созданные только для fault injection. Материальная проблема — verifier не отвергает внутренне противоречивый принятый документ. Train/selection source equality сейчас сравнивает именно declarative identity; поэтому одинаковое неверное значение в обеих identity не устанавливает общий actual source. Повторный hash противоречивого плана подтверждает его bytes, не заявленный lineage. Текущие реальные017 artifacts не объявляются неверными: coordinator отдельно сверял их source/plan, но reusable008 API должен fail closed независимо от этой внешней удачи.

**Минимальный fix:** потребовать exact execution_inputs keys phase_path/source_path/fingerprints; derive canonical producer inputs из PRODUCER_CODE плюс phase_path/source_path/base_protocol/feature_registry/pyproject.toml — для текущей схемы14 уникальных paths. Identity code_hashes должны иметь ровно producer code keys и совпадать с этими pins; source_sha256/registry_sha256 — с pins соответствующих paths; physical validated phase body — с identity.phase. Отсутствующие и лишние execution pins отвергать. Уже проверяемые actual hashes и external approval остаются обязательными. Добавить независимые regressions перечисленных inconsistent/resealed cases; valid complete lifecycle должен сохраняться.

## Граница acceptance

После исправления этого invariant нужны actual freeze, scoped suite и повтор перечисленных пяти faults. Затем возможен code-only accept; real fit требует отдельно принятой017 train/selection lineage и конкретного external fit approval с remaining compute budget. Env snapshot сверяет loaded и installed CatBoost/DuckDB/NumPy с uv.lock; это не аудит всех transitive packages.

Full-Y metrics, deterministic product-ID ties, BCE all-mature versus PairLogit informative-group populations и fixed final checkpoint сохраняют прежние проверенные semantics. Два smoke fit не устанавливают strong tuned B. Confirmation остаётся закрытой: selection labels available24Oct00 совпадают с first confirmation24Oct00; будущая decision availability и положительный prospective gap требуют отдельного решения.
