# TLAB-009: полная дневная выгрузка metadata/price

Статус: новый исполнитель и 23 синтетические проверки реализованы. Независимые reviews запросили изменения; исправления проходят повторную проверку. Разрешения на полный расчёт ещё нет, реальные полные addon-файлы не рассчитаны, новых моделей нет. Принятый 100Q producer остаётся неизменным. [Его source/cost проверка](../backlog-reviews/tlab009-100q-source-verification.md) подтвердила 370548 значений, 20586 строк provenance и 1603114 строк reference на 13 anchors.

## Входы и происхождение

`prepare_export_plan` только предлагает identity. Он повторно проверяет внешние accepted train/selection collections, положительный model availability gap, одинаковые base schema/source/registry/policies и 93pins принятого 100Q результата. Точный scope source acceptance: `reviewed_metadata_price_100q`. Имена и содержимое sealed approval не переписываются.

Обязательный scope 100Q выводится заново из фактического принятого train bundle, файла spec и frozen `prepare_gate_plan`, а не из списка fingerprints внутри проверяемого manifest. Fresh-resealed отсутствие source, candidate code или spec file отвергается даже после обновления runID и всех зависимых hashes.

К accepted008 mechanical verifier добавлена строгая проверка 14 канонических pins каждого Q/Y/C approval: union code anchor/candidate, source, полные anchor/candidate seals включая query_coverage. Feature inputs обязаны содержать эти 14pins, registry, approval и единственную selection definition. Consumed runIDs в candidate/feature reports проверяются отдельно. Synthetic fresh-reseal тест удаляет Q/C dependencies, обновляет все hashes/IDs/seals: legacy transport ещё пропускает bundle, новая проверка отвергает. Текущие реальные 6shards имеют полные 14maps и прошли read-only проверку; их ранее подтверждённые source values не ставятся под сомнение.

Новая identity связывает точные acceptance refs, все actual inputs/code, неизменённый spec, sourcegateID, обе collectionIDs, partition policy и limits. Нужен отдельный внешний execution approval scope `metadata_price_development_export` с exact runID/fingerprints. Самоподготовленный digest не является разрешением.

## Одна дневная партия вместо полной Python-матрицы

Для каждого accepted UTCday загружаются все его Q и только fixedbaseF keys/category flags. Изменения Q/Y/C/baseF отсутствуют, labels не разбираются. Reviewed core рассчитывает отдельные 20columns (2keys,3nominal,15numeric), source provenance иполный R; результат немедленно экспортируется в отдельный immutable day directory. Следующий день заменяет временные SQLtables.

Whole-row schema/key/reference/provenance gates работают по всей дневной таблице. Дополнительно для каждого product ID доказывается, что все запросы одного дня получили один и тот же metadata tuple. После этого каждая уникальная дневная строка проходит accepted float32/UTF8/mask validator в отдельной небольшой connection; countcap проверяется **до** fetchall/arrayallocation. Это проверка границы представления модели, не source oracle.

На accepted inputs максимум 6811 уникальных товаров в train day и 6437 в selection day. Полные phase cover checks сравнивают multiset keys выгрузок с accepted Q/F, включая запросы с emptyC; только равенства count недостаточно. Parent manifest сохраняет refs/SHA/counts/schema каждого файла. Failed preparation/partial days остаются в audit, никакого автоматического refill/retry нет.

## Ресурсы и приёмка

Один producer ограничен 1200wallseconds,900actualprocessCPU seconds,2threads, cooperativeRSS8GiB, spill≤2GiB,≤2000Q/440000pairs и≤22000 уникальных model rows на день. CPU user+system записывается отдельно от wall; nested stages inclusive, их нельзя суммировать поверх process total. DuckDBrequestedmemory/spill2GB не являются hardRSS guarantee. Финальные guards охватывают connection close, manifest и audit writes; первоначальная ошибка сохраняется при secondary cleanup, counter или writer failure. Недоступные counters записываются как NULL с причиной. При неисправном writer выполняется best-effort запись отдельного failed receipt; если файловая система недоступна, сохранение на диск не обещается, первоначальная ошибка и in-memory evidence сохраняются.

CPU snapshot включает close, manifest serialization и первую запись summary. Минимальная повторная запись окончательного receipt находится после snapshot и явно названа в `cpu_accounting_boundary`; родительский ledger учитывает этот tail. Guard повторяется после receipt, поэтому переполнение при его сохранении не превращается в accepted complete run.

Первая summary имеет status `finalizing`; complete status записывается только в окончательном receipt. Consumer также отвергает наличие `report.failed.json` до чтения output manifest: сохранённый stalecomplete report нельзя принять через fresh hashes поверх известного failed receipt. Failed marker не является output, который разрешено удалить ради повторной приёмки; нужен независимый review, автоматический retry отсутствует.

Combined producer+independent source oracle должен оставаться внутри prospective30CPUminutes и существующего 009budget. Исторические неизмеренные CPU затраты не превращаются в выдуманный остаток. Source/cost acceptance полного экспорта выдаётся **отдельно**: oracle строит universe из acceptedQ/C, проверяет каждый distinct(anchor,item) независимым resolver/direct-peer-listmean, затем сравнивает каждую физическую addonrow, включая NULL/masks/nominalexact и объявленный numeric tolerance. Полные R и provenance проверяются отдельно; domain не выводится из producer addon.

Actualfull26000encodedcardinality здесь diagnostic. Значение>4096 не запрещает единственный 009ablation на 6000Q автоматически: у него отдельный actualselected6000encoder gate. Для 019full26000 оно относится к заранее принятому population/resource decision. Selection unseen values не являются причиной обучать encoder на selection.

Phase diagnostic считает точный union UTF8-encoded значений каждого nominal столбца по всем дням, включая sentinels. Это не максимум daily cardinalities: две дневные vocabulary размера 1 с разными значениями дают phase cardinality 2.

`verify_accepted_export` потребляет последующий external source acceptance (`reviewed_metadata_price_development_export`), проверяя exact scope/inputs/dailycover/outputpaths и заново связывая identity с actual acceptedinput plan. Дополнительно он читает сами Parquet: реальные schema, counts и sizes, все поля Q против accepted Q/day, точный F/provenance key cover, reference schema/keys/value boundary и membership. Каждый уникальный дневной item проходит model boundary; phase vocabulary union сверяется с report. Проверка выполняется дневными партиями в отдельной connection с 2threads/2GB и запрещённым spill, вызывает внешний budget callback. Она не заменяет независимый source-formula oracle и не создаёт approval. Только после независимой полной сверки возможны отдельный mixed loader и один Logloss50ablation на прежних 6000train/4000selectionQ/C/fullY.

## Синтетическая проверка

23 tests покрывают actualtiny acceptedproducer lineage, fresh-resealed missingQ/C и 100Q source/code/spec dependencies, daily exports/wholekeycover/acceptedconsumption, immutable retry, wrongexecutionapproval, terminalinputmutation, close-timeoverrun, actualCPUcap/counterfailure/primary+secondaryerrors, every-item invariance и 22000capbeforeallocation. Новые regression cases отвергают freshly resealed wrong query, missing nominal column, dropped pair, false reference membership и stalecomplete с failed marker; проверяют phase union, CPU manifest/summary cost, finalizing status и failed evidence при writer fault. Full runtime transport mocks отмечены: они не подменяют source oracle, который уже отдельно проверял core и будет повторён для full exports. Сбой fixture из-за macOS `/var`↔`/private/var` alias исправлен `.resolve()` до relative checks.


## Code acceptance — 15 октября 2026

[Final narrow review](../backlog-reviews/tlab009-full-export-final-rereview.md) принимает3a255515…10d8d после23author tests и independent original faults/marker regressions. Initial [fourP1/P2](../backlog-reviews/tlab009-full-export-code-review.md) и subsequent [failed-receipt finding](../backlog-reviews/tlab009-full-export-code-rereview.md) сохранены. Actual full export/source acceptance ещё не выполнены.

Независимый [source audit CLI](../../tests/oracles/metadata_export_audit.py) запускается только отдельным freshprocess из корня проекта после external execution approval и успешного producer receipt:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tests.oracles.metadata_export_audit artifacts/metadata-price-development/RUN_ID
```

RUN_ID — placeholder; этот пример не разрешает новый расчёт. Audit пишет temporary attempt evidence и не создаёт acceptance. Expecteddomain из acceptedQ/C, everyphysicalrow comparison и fullR независимы от producer. NullableBIGINT transport исправлен **до** pandas inference, [12independent typed cases](../backlog-reviews/tlab009-full-source-oracle-rereview.md) и [knownfailed-marker gate](../backlog-reviews/tlab009-full-source-oracle-marker-rereview.md) приняты; source execution и900actualCPU allowance остаются отдельным решением. Последний receipt/stdout tail явно отделён от snapshot CPU, parent invocation ledger нужен для полной стоимости. Linux RSS conversion реализована, Linux execution не заявляется.
