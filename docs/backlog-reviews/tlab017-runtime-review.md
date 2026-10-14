# TLAB-017 runtime: независимая проверка frozen increment

15 октября 2026. **Вердикт: material changes requested; producer approval не выдавать до исправления resume.** Scope — actual runtime [development_collection.py](../../scripts/development_collection.py), scoped [tests](../../tests/test_development_collection.py), [runtime documentation](../experiments/development-collection.md), связи с принятыми producers001–007. Root008 training files не проверялись и не менялись. Production, исходный October DuckDB, train/selection/confirmation данные не запускались/не читались. Все дополнительные faults выполнены на маленьких изолированных synthetic fixtures; repo/Git/code/deps не изменялись.

## Проверенная версия и actual tests

SHA-256 runtime: `1a9c5a588b0b00512a467696134bac864cbc6bdd7073775664ed478adf72f422`.

SHA-256 tests: `ee4d634c5b60dc2f9a2cc2cee11a49556c853be94af87b5147e871d1dd672712`.

Оба fingerprints совпали с handoff и повторной проверкой после review. Scoped запуск через repo venv, с отключённой записью bytecode: `python -m unittest discover -s tests -p test_development_collection.py -v` — **17 PASS, 1,503 секунды, exit0**. Заявленные 120 total отдельно не запускались: другие WIP не входят в scope. Успешные scoped tests не закрывают finding ниже.

## P1: recoverable child failure делает обычный resume невозможным

Точное место: [produce](../../scripts/development_collection.py#L469) вызывает operation повторно при отсутствии `entry[kind]`; entry появляется только после полного child return и parent seal. Для F передаётся прежний [output directory](../../scripts/development_collection.py#L555). Между тем принятый [manual_features producer](../../scripts/manual_features.py#L343) сохраняет identified run и запрещает создавать тот же deterministic run заново.

Независимый repro использует actual DevelopmentRuntimeTests fixture и actual producers, меняя только transient runtime fault:

```python
fixture.execute()                  # waiting_for_shard_review
fixture.approve_shards()            # synthetic external approvals
with patch.object(manual_features, "create_manual_features",
                  side_effect=TimeoutError("independent recoverable F fault")):
    fixture.execute()              # TimeoutError после создания identified F run
fixture.execute()                  # обычный unpatched resume
```

Actual result: первый сбой оставляет state `failed`, все C seals сохранены, F entries отсутствуют, compute cost положительный, runtime lock снят. Следующий вызов снова передаёт тот же feature output root и получает **FileExistsError: Existing identified run is preserved**. Он также расходует cumulative budget, но не может продвинуть коллекцию. Это не crash-lock/manual recovery case: ошибка штатно поймана, lock очищен, inputs/approvals неизменны и бюджет ещё достаточен.

Проблема общая для unsealed child retries. Anchor/candidate producers тоже создают deterministic identified directory с `exist_ok=False`; после ошибки до сохранения parent entry остаётся тот же конфликт. Existing integration test проверяет partial cost и отсутствие fake complete, но не пробует восстановление после удаления временного fault.

**Необходимое минимальное исправление в owned017:** для каждого нового child invocation без сохранённого seal выбирать отдельный attempt output namespace; передавать именно его operation и последующей `_verify_run`. Сохранять старые partial/complete-but-unsealed child runs. Не удалять immutable artifacts и не переписывать принятые005/004/003. Альтернатива — явно проверяемый recovery mechanism, но не автоматическая приёмка partial output по свежему hash. Сохранённый entry по-прежнему должен идти через прежний `_check_cached`, а не производиться заново.

Обязательная регрессия: waiting→external approvals→fault после identified child creation→обычный resume без fault→complete_produced_unreviewed; Q/Y/C lineage и исходные seals сохранены, старый failed child существует, elapsed обоих вызовов оплачены. Проверить как минимум F и один Q/C producer. Код reviewer не исправлял.

## Что фактически выдержало проверку

Producer approval обязателен и имеет отдельный scope `reviewed_producers_and_phase_plan`: prepare возвращает proposals, не генерирует approval. Exact bundle содержит source DB, phase/base/registry, pyproject, uv.lock и producer code. Changed pins или иной scope не превращаются в новую автоматическую приёмку. Cache сопоставляется с предыдущим seal, не только с текущим содержимым. Внешний Q/Y/C approval проверяется до F; при отсутствии хотя бы одного нужного approval features не производятся.

Lineage проверяет exact anchor inputs source→Q/Y, candidate входы exact Q/Y manifests/reports/Parquet и feature inputs с acceptance SHA/registry. Aggregate требует полный ordered shard cover, daily report coverage, totals report↔Parquet, уникальные Q/user-days/пары, maturity/range, no orphan/null pairs, exact C↔F и сохранение восьми retrieval columns/user/anchor. Diagnostic feature subset отвергается. Это механическая integrity, не independent oracle всех feature values; финальный статус правильно `complete_produced_unreviewed`, collection acceptance остаётся отдельной.

Дополнительные независимые faults дали ожидаемый отказ:

- RSS выше8GiB до preparation: failed report с MemoryError, prepare/source не вызваны, state не создан.
- Изменённый synthetic uv.lock: producer fingerprints reject, child calls0.
- External shard approval `approved=False`: features calls0, state failed.
- Остаток cumulative budget10ms и preparation30ms: TimeoutError до child, весь elapsed начислен; бюджет не сброшен.
- Producer возвращает диагностический F subset1 query: reject до feature seal, complete не заявлен.

Parent attempt audit создаётся до preparation, costs сохраняются при штатных сбоях; review wait между invocations явно исключён. Deadline persistent, SQL aggregate interrupt предусмотрен, child получает remaining time. RSS guard cooperative и high-water, не OS hard limit; requested DuckDB2GB/spill2GB не равны peak RSS. Производительная пригодность пяти реальных train shards и реальные counts/bytes/time этим review не измерены.

## Gates после исправления

После revised code scoped tests и повторного failure→resume repro можно принять runtime code scope и отдельно выдать approval конкретному producer/phase/source/dependency bundle. Это ещё не017done и не разрешение008 realfit: реальные Q/Y/C требуют independent source reconciliation, F — numeric spotchecks и collection acceptance. Новая lock/code lineage требует нового approval; старые artifacts не переобозначаются.

Confirmation runtime сейчас правильно отказывает до source fingerprints/read даже при schema-valid lock. Будущий gate должен доказать availability именно selected decision/metrics, не только baseline checkpoint22октября. Selection labels доступны24октября00:00, и первый confirmation anchor тоже24октября00:00: положительного промежутка для вычисления metrics и freeze сейчас нет. До открытия confirmation нужно согласовать реальный decision gap либо явно обоснованную и проверяемую instant-decision assumption; одно schema `available_at≤frozen_before≤first_query` этого не доказывает. Final holdout закрыт. Strong tuned B и automation evidence по task1 остаются будущими, два smoke fits не заменяют их.
