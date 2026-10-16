# Tiny CLI fixture: фактический Q/Y/C milestone принят

16 октября2026. Один ordinary no-fit запуск выполнил реальные `run_phase` для train и selection и остановился в `waiting_for_shard_review`. Wrapper и child завершены/reaped с exit0; повторов не было. [Production receipt](evidence/native-cli-tiny-QYC-result/originals/root-production-acceptance.json) сохраняет исходный момент до семантической приёмки; [поздняя Root adoption](evidence/native-cli-tiny-QYC-result/originals/root-semantic-adoption.json) фиксирует принятие строк после независимого review.

| Фаза | Q | Full-Y pairs | C pairs | Coverage rows |
|---|---:|---:|---:|---:|
| Train, anchor08октября2019 | 2 | 1 | 3 | 2 |
| Selection, anchor18октября2019 | 3 | 3 | 3 | 3 |

[Независимое semantic review](evidence/native-cli-tiny-QYC-result/originals/independent-semantic-review.md) проверило все20 экспортированных строк из восьми физических Parquet: типы, порядок колонок, NULL, query/item keys, literal Q/C/Y, coverage и lineage. Все восемь SHA/bytes/modes связаны с исходным worker inventory; [reference map](evidence/native-cli-tiny-QYC-result/physical-artifact-bindings.json) содержит только ссылки и метаданные, не Parquet.

В selection сохранены positive user4 с fullY={77} и пустым C, user5 с пустым Y, а также user3 с fullY={10,99}, где99 находится вне C. Off-C targets77/99 не добавлены в кандидаты и не исключены из fullY. Знаменатель positive-fullY остаётся2, all-query-zero —3. Train сохраняет overlap popular/recent для user2; recent timestamp tie у user3 разрешён10 затем20. Empty-Y coverage имеет нулевые totals и NULL в шести optional outcome breakdowns; positive empty-C query имеет реальную outcome-строку.

При production stop созданы52 новых файла, всего82; Root сверил их SHA/bytes/modes. Позднее, после semantic review, Root отдельно выдал genuine Q/Y/C shard acceptances и проверил metadata: проект84файла включает два новых приватных acceptance input. Это отдельные управляющие входы; их тела и control receipts в пакет не включены. Сохранённые state/pending receipts описывают время исходного stop и не переписаны задним числом.

Физический export выполнил один read-only проход:8 Parquet SELECT и2 in-memory SET, без открытия source DB. Semantic reviewer читал уже готовый export и отдельно связал восемь физических файлов; собственного DuckDB/SQL у reviewer не было. Построение исходной DB наследуется от принятого ten-event builder, без независимого повторного raw DB scan.

| Измерение | CPU, сек | Wall, сек | Наблюдавшийся peak RSS |
|---|---:|---:|---:|
| Q/Y/C child, полный reaped scope | 1.146204 | 1.581156875 launch→reap | 132349952 B |
| Read-only export, до JSON/tail | 0.697748 | 0.664992667 guard→profile | 114475008 B |

Parent SELF CPU0.048086сек измерен до JSON; его tail не включён. Эти scopes не складываются в точный whole-project/whole-host total. RSS — наблюдение процесса, не hard64MB engine bound; tool wait-wall не подменяет полный lifetime. [Сырые малые результаты и карта копий](evidence/native-cli-tiny-QYC-result/publication.json) сохраняют исходные статусы и численные наблюдения.

F, aggregation, prepared matrix, collection, verifier, native CLI, fit и inference этим запуском не выполнялись. Следующий F worker имеет SOURCE proposal и независимое review в работе; его выполнение или результат не принят. Этот fixture не доказывает actual October incidence/completeness, sampling truncation, exact target endpoints, missing-category semantics или качество модели. Новых scientific IDs/grants/gates нет; science/native allocations закрыты, исторический остатокUNKNOWN и прежние метрики неизменны. Ordinary CLI adaptive/native callback-abort остаются UNRUN.

Это TMP SOURCE-предложение отдельного датированного результата. Установка — только после Root review и отдельного coordinator checkpoint; current4 здесь не изменяются. Runtime-control plans, runners, approvals/acceptance bodies, DB, Parquet и полный набор28профилей исключены.
