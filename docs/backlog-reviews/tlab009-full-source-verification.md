# Полный блок metadata/price: независимая приёмка данных

15 октября 2026. **ACCEPT расчёта и происхождения данных.** Полный producer017e00dd…227a обработал26000train и4000selection запросов на15UTCanchors. Все6134207пар получили3nominal+15numeric добавочных полей. Это не результат нового обучения или доказательство пользы блока.

Независимый [public oracle](../../tests/oracles/metadata_export_audit.py) строит97891distinct(anchor,item) из acceptedQ/C, заново разрешает global latest timestamp ties/dictionary и прямые excluded-self peer lists из source. Затем проверяет **каждую физическую строку**:110415726metadata values,6134207provenance rows, все1858481reference rows. Values/keys/NULL/BOOLEAN/BIGINT/strings exact; DOUBLE absolute1e−12/relative1e−9. Все проверки прошли. Producer DISTINCT representatives не задают ожидаемый domain; compiler/resolver/sum-minus-self producer не вычисляют expected values. Для исходных18manual core числовых features сохраняется ранее описанная sampled source verification; эти18добавочных полей — другая группа.

| Исполнение | Wall,s | Actual process CPU,s | PeakRSS,bytes | Fits |
|---|---:|---:|---:|---:|
| Full producer, fresh parent |66.952068|89.558366|2406858752|0|
| Independent full oracle, fresh parent |54.458268|69.930734|1155579904|0|

Combined159.4891actualCPU seconds находятся внутри1800cap; импорты и final receipt tail учитываются parent receipt. Spill producer0; memory setting2GB не объявляется hardRSS cap. Отдельная новая proposal preparation24.390639wall/24.35399CPU и seal overhead0.657084wall/.656793CPU не превращаются в нулевую стоимость. Historical unmeasured CPU не пересчитывается изwall×threads.

[Агрегированный evidence](tlab009-full-source-aggregate.json) связывает code/oracle hashes, все counts и ресурсы. External source acceptance `reviewed_metadata_price_development_export` закрепляет176exactinput/output fingerprints; SHA77137bbcd5b4cb10bc9d47c0e562b8a6f949ba6879a8c7f26a9fc42d20b875cd. Producer report остаётся immutable complete_produced_unreviewed, внешний verdict его не переписывает. Approval/data/Parquet ignored.

Ранее доказанный nullableBIGINT pandas false acceptance исправлен до этого исполнения; known failed receipts отвергаются до source work. [Code acceptance](tlab009-full-export-final-rereview.md), [typed transport](tlab009-full-source-oracle-rereview.md), [marker observer](tlab009-full-source-oracle-marker-rereview.md) и [EOF-only publication correction](tlab009-full-publication-note.md) сохраняют историю ошибок.

Actual full train encoded vocabulary: brand1911/code126/categoryID562; selection1093/116/485. Это union diagnostic, а не actualselected6000 TRAIN gate перед native Pool. Модельный single-ablation gate и точное old008 BASEONLY/mixed-prefix equivalence ещё отдельны. Новые models/predictions/quality metrics на этом шаге отсутствуют.
