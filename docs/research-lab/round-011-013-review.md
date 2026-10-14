# Independent critic rounds011/013

15 октября2026. **ACCEPT research direction with two bounded clarifications before implementation.** Read-only проверены обе записки/backlog и первичные Woodwork/Featuretools/RelBench/SQL источники. Новых experiments, raw scans, fits, code/dependency/budget changes нет. HYP111/112 правильно оставлены reserved: multiplicity/availability proof obligations уточняют002/046, не создают отдельный predictive mechanism.

## Проверенные пределы type/schema claims

Round011 корректно различает physical/logical/semantic type и declared relationship. Woodwork удаляет standard tags у index; Featuretools1.31.0 явно исключает numeric foreign keys при primitive input matching. Это защита **аннотированных** columns, не автоматическое распознавание всех numeric IDs и не доказательство FK membership/бизнес-grain. [Woodwork](https://woodwork.alteryx.com/en/stable/guides/logical_types_and_semantic_tags.html), [tagged DFS](https://github.com/alteryx/featuretools/blob/v1.31.0/featuretools/synthesis/deep_feature_synthesis.py#L959-L971).

Round013 правильно требует full sealed-input/enforced constraint вместо sample uniqueness. Слова011 «из схемы можно проверить FK/cardinality» читать как возможность отдельного QA, не как вывод из inferred types или отсутствия ошибок в100Qsample. Даже настоящий PK(product,version) не доказывает unique(product) после temporal join. Отдельно проверяются orphan/null policy и уникальность **фактических join keys**. DuckDB PK запрещаетNULL, UNIQUE сам по себе этого не делает; nullable equality join и NULL-safe join требуют разных contracts. [Constraints](https://duckdb.org/docs/current/sql/constraints).

RelBench Table constructor действительно сохраняет declarations без собственной проверки uniqueness; upto использует≤timestamp, untimed table возвращается целиком. Записка честно ограничивает наблюдение данным constructor/main-кодом, не всем benchmark preprocessing. [Author Table](https://github.com/snap-stanford/relbench/blob/main/relbench/base/table.py). Для последующей implementation evidence закрепить commit/hash: main URL не immutable version.

## Пять counterexamples: арифметика принята, scope уточнить

1. Sibling2×2 действительно даёт4joined rows против independent2/2; DISTINCT payload теряет легальный duplicate view и даёт1. Нельзя лечить fanout удалением source bag multiplicity.
2. Global bucket A@1, {B,NULL}@2 даёт ambiguous category вquery3; A1/B1 остаются historical counts, NULL event сохраняет raw mass. **Уточнение:** user_view=3 верно, только если все три события принадлежат одному u. Для cross-user peers задать явных users: например A/B уu1 иNULL уu2 дают user counts2/1 при той же global ambiguity. Иначе будущий hand oracle может смешать global и user population.
3. Два ID с одним code дают exact-ID share1/2 и code share1. Обратный code→IDs join размножает bag; это разные grains, recovery не делает mapping обратимым.
4. Ancestor counts2/2/1 суммируются в5при двух events; child1+STOP1 образуют partition родителя, но users1+1 нельзя сложить вparent union1. Намеренное event→ancestor membership допустимо. Запрет fanout относится к незаявленному enrichment; нельзя запретить всю taxonomy expansion. Для каждого фиксированного node canonical membership уникален, raw event duplicates сохраняются; bridge edges дедуплицируются до event join, не DISTINCT всего payload.
5. LEFT JOIN пустой history создаётNULL-extended row иcount(*)=1. Агрегация source bag доjoin даёт correct knownempty0; count(nullable product) может терять реальные события безproduct. Unknown category/zero denominator остаютсяNULL.

SQL semantics подтверждает каждый matching pair уINNER иNULL-extended row уLEFT. SEMI не увеличивает left cardinality, ASOF даёт≤1match, но это не доказательство выбора всех global ties. [PostgreSQL](https://www.postgresql.org/docs/current/queries-table-expressions.html), [DuckDB joins](https://duckdb.org/docs/current/sql/query_syntax/from).

## Второе уточнение: temporal uniqueness не равна temporal truth

Приняты011 strict event/availability endpoints и раздельныеvalid/knowledge времена. Featuretools source подтверждает primary cutoff toggle и secondary mask≥cutoff; masking не восстанавливает прошлые versions. [Tagged EntitySet](https://github.com/alteryx/featuretools/blob/v1.31.0/featuretools/entityset/entityset.py#L1277-L1325).

Для proposed cache/resolved relation `(anchor,product)` достаточно только **внутри одного frozen policy/source context**. Полный identity дополнительно содержит source/version, schema adapter, availability/metadata/multiplicity policy. Две версии valid одновременно могут дать несколько matches даже при PK; нужно явное conflict/ambiguity resolution, не произвольная сортировка или ASOF winner. Late correction не переписывает past output; будущий suffix invariant относится к неизменному context и событиям/versions, ещё недоступным наcutoff. Это уточнение существующего046 cache contract, не новый механизм.

Оба текста правильно не объявляют synthetic adapter gate quality generalization, installed-library proof, поддержку taxonomy005/018 или новый compute allowance. Числа пяти fixtures — ручная проверка логики; полноценное выполнение и independent source oracle ещё не проведены. Центральный016 generation/selection против frozen tunedB сохраняет отдельные gates; эти research refinements не должны задерживать готовые approved components.
