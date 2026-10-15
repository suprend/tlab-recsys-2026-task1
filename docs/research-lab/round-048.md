# Round048: RelBench как temporal interface, а не готовый adapter

**Source-only research, без clone/install/data/jobs/models или новых budgets.** Прочитан [NeurIPS2024 paper](https://cs.stanford.edu/~jure/pubs/relbench-neurips24.pdf) и официальный Python source. Важно различать версии: текущий [official repository](https://github.com/stanford-star/relbench) уже описывает v3/Hub loading, тогда как paper относится к первоначальному benchmark. Ниже source findings относятся к прочитанному `main`15Oct2026, не установленной/pinned версии; перед будущим использованием нужен immutable commit. API commit endpoint не дал readable response, поэтому SHA не выдумывается.

## Что задаёт benchmark

Paper определяет relational tables с primary/foreign keys и некоторыми row timestamps; predictive task — entity ID, seed time и target. Общие validation/test timestamps задают chronological split. RDL превращает rows в nodes и PK/FK links в edges, обучая graph/tabular representations. Это другой механизм, чем explicit DFS/manual aggregate AST, а не автоматическое исполнение нашей grammar. Сам paper отдельно возлагает предотвращение time leakage на designers и рекомендует temporal sampling implementation.

[Текущий Table API](https://github.com/stanford-star/relbench/blob/main/relbench/base/table.py) хранит `pkey_col`, `fkey_col_to_pkey_table` и optional `time_col`. `upto(t)` использует **timestamp≤t**; table без time column возвращается без temporal filtering. Это конкретный inclusive contract, а не наше `<t` с исключением всех global peers. Наличие timestamp не означает ingestion availability или validity interval каждого property field.

[Dataset API](https://github.com/stanford-star/relbench/blob/main/relbench/base/dataset.py) по умолчанию обрезает DB только по `test_timestamp`; ключи должны быть consecutive row indices, dangling references могут статьNULL. Поэтому default DB не является snapshot каждого historical training seed. Отдельный builder/sampler обязан ограничить history для каждого query. Frozen DB на одном test cutoff также не является автоматическим rolling update истории последующих daily queries.

## Новые temporal API findings

[BaseTask](https://github.com/stanford-star/relbench/blob/main/relbench/base/task_base.py) документирует target horizon **(t,t+δ]**. Train seeds идут назад отval−δ сшагомδ, validation начинается вval; проверяется test−val≥δ и достаточный max timestamp для horizon. Это полезные safeguards, но max timestamp какой-либо таблицы сам по себе не доказывает полноту event coverage или известный delivery delay. В interface нет нашей отдельной maturity policy с availability_delay/positive decision compute.

| Boundary | Прочитанный RelBench contract | Отличие нашего протокола |
|---|---|---|
| Source history | Table.upto включаетt; untimed tables остаются | Events строго<t; unknown field availability не угадывается |
| Target endpoints | BaseTask horizon(t,t+δ] | FullY имеет[t,t+H): событие ровноt меняет роль |
| Per-seed history | Global test cutoff плюс temporal neighbor sampling | Exact source predicates проверяются для каждого UTC anchor |
| Recommendation population | Фильтруются dangling destinations и пустые target lists | Cold/out-ofC Y остаются misses, mature zeroY Q сохраняются |
| Test label hiding | Mask возвращаемого test table | До prediction seal запрещено само query-levelY opening |

Последние две строки подтверждаются [RecommendationTask](https://github.com/stanford-star/relbench/blob/main/relbench/base/task_recommendation.py): destination IDs вне DB удаляются, а строки с пустым оставшимся target list исключаются. Сейчас recommendation evaluation поддерживает один eval timestamp. Это legitimate benchmark definition, но не наш fullY denominator/zero-query policy. Перенос evaluator изменил бы estimand, даже если название recommendation совпадает.

BaseTask.get_table сначала получает полную task table, затем применяет masking; regeneration path вычисляет labels до удаления columns из результата. Default evaluate самостоятельно получает unmasked test targets. Следовательно, «returned table безtarget» не доказывает наш access-seal protocol. Это source interface finding, не утверждение, что кто-либо открыл наш heldout; никаких loaders здесь не вызывалось.

## Sampler и learned-state clocks

[Official GNN example](https://github.com/stanford-star/relbench/blob/main/examples/gnn_entity.py) передаёт `time_attr` и per-seed `input_time` в NeighborLoader. [PyG2.8.1 docs](https://pytorch-geometric.readthedocs.io/en/2.8.1/_modules/torch_geometric/loader/neighbor_loader.html) гарантируют earlier-or-equal timestamps. Поэтому одного temporal loader недостаточно для strict global-peer exclusion. Sampling также не доказывает точные raw counts: truncated neighborhood и полный bag — разные вычислительные объекты.

Example optional label-as-feature tables сдвигает timestamp наseed+δ и не добавляет test labels. Это пример явной label readiness, но не дополнительного ingestion delay или времени training/decision computation. Полученная availability assumption не должна backdate fitted state кстарымanchors.

[Modeling utils](https://github.com/stanford-star/relbench/blob/main/relbench/modeling/utils.py) переводит datetime черезinteger division1e9, а integer timestamps оставляет integer. Значит, seconds precision и входные units требуется проверять отдельно: Unix milliseconds нельзя автоматически считать преобразованными, subsecond ordering может исчезнуть. Type proposals по sample не устанавливают semantic role/clock. Materialized encoding statistics/cache имеют собственный fit scope; timestamp sampling не удостоверяет их availability.

## EventFact, Query и PropertyState

EventFact можно представить rows сFK наuser/item, сохранив каждую точную duplicate row отдельным node/index. Искусственный transport index не становится stable event order для timestamp peers. Query соответствуетentity/seedtime table, но C и полныйY необходимо хранить отдельно и не получатьQ population изpositive labels.

PropertyState нуждается в отдельном declared resolver: latest eligible per-field update, conflict/NULL bucket, available_at и carry-forward. Untimed product row с сегодняшнейcategory не заменяет historical event category; row creation time не гарантирует знание всех будущих fields. Current005 использует embedded event metadata/global bucket, поэтому RelBench schema сама не реализует Retailrocket property adapter040. FK graph задаёт связи, но не observational multiplicity, full category denominator или membership expansion semantics.

## Один оправданный будущий tiny drill

Proposal только для interface conformance:≤32literal rows,0fits, без внешнего dataset. Event witnesses вT−1,T,T+H должны различить оба endpoint contracts. Дваduplicates сохраняют rawcount2/distinct1; global peersknown+NULL даютunknown. Propertyknown-later, untimed futurefield и subsecond pair проверяют clocks/precision. ZeroY query и cold destination не должны пропасть из нашей retained-Q/fullY relation. Label loader spy обязан различать return masking и фактическое Y access доseal.

Accept такого будущего drill означает правильный declared adapter/rejection, не benchmark score, actual source approval или quality transfer. Budget/implementation approval отдельно; current016 не меняется. Dataset license, size и download access здесь не исследовались и не выводятся из repository license или marketing overview. RelBench полезен как явный task/schema interface и набор counterexamples; его RDL результаты не заменяют наш matched boosting experiment и не дают автоматических speed/human-hours claims.

## Version-pin amendment

[Official releases](https://github.com/stanford-star/relbench/releases) показывают tagv3.0.2/shortcommit8fb84d2. [BaseTask наv3.0.2](https://github.com/stanford-star/relbench/blob/v3.0.2/relbench/base/task_base.py) отдельно прочитан: horizon/endpoints, split bounds иmask-after-table соответствуют описанию. Остальные ссылкиmain не объявляются byte-identical этомуtag: частьtag URLs недоступна, commit API/history вернули unavailable/429. FullSHA не установлен. Это различия contracts, не библиотечныеbugs; strictadapter должен явно задавать endpoints, target completeness/access lifecycle иavailability untimedfields. Установка/download не выполнялись.
