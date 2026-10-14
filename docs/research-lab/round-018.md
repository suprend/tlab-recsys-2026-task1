# Round018: property tests compiler и expected-value transport

15 октября2026. **Research/design-only: без исполнения tests, repro, fits, raw scans, downloads datasets или изменений repo/Root WIP.** Прочитаны actual[005tests](../../tests/test_manual_features.py), [018scope](../experiments/verification-workflow.md) и rounds[013](round-013.md)–[017](round-017.md). HYP121/122 reserved: refinement verification, без новой hypothesis quota. Следующий generator — предложение, не реализованный framework или новый бюджет.

## Четыре первичных источника

Hypothesis задаёт bounded integer/float strategies, composite generation и shrinking; float width32 отдельно ограничивает представимые значения. Это полезные механизмы построения маленьких counterexamples, не доказательство абсолютной корректности. Установку библиотеки или изменение зависимостей здесь не предлагаю. [Официальные strategies](https://hypothesis.readthedocs.io/en/latest/reference/strategies.html).

NoREC сравнивает число строк WHERE-query с отдельным вычислением истинности predicate на строках, уменьшая пространство optimizer transformations. Авторы не гарантируют отсутствия любых optimizations или общих ошибок двух путей. Такой SQL crosscheck дополняет независимый Python oracle, но не определяет правильную feature formula. [Rigger–Su, NoREC](https://www.manuelrigger.at/preprints/NoREC.pdf).

TLP разбивает relation по `p`, `NOT p`, `p IS NULL`. Правильная composition зависит от operator: bag UNION ALL для исходных строк отличается от DISTINCT union. Наш scalar distinct нельзя получить суммой uniques partitions, где один entity встречается в нескольких частях. [Rigger–Su, TLP](https://www.manuelrigger.at/preprints/TLP.pdf).

Pandas прямо предупреждает: integer с missing values может стать float, а некоторые identifiers не представимы точно. Рекомендуется explicit nullable Int64 при construction; Series/array inference различается. Это primary подтверждение класса transport риска, не проверка конкретной версии coordinator harness. [Nullable integers](https://pandas.pydata.org/docs/user_guide/integer_na.html).

## Три независимые seams

**Absolute source oracle.** Маленькие literal tables фиксируют ожидаемые counts/NULL/flags/metadata IDs, direct-list formulas вычисляются без production helpers. Existing005 tests уже покрывают18core, category moves/mixed buckets, expiry, future suffix и peers. Property generator расширяет этот критический набор, а не заменяет его миллионами зеркальных assertions. Frozen018 по-прежнему проверяет numeric F только на sample; новые tests не переименовывают этот scope в exhaustive.

**Metamorphic relations.** Они утверждают связь результатов при преобразовании input. Constant-zero compiler выдержит многие invariance checks; следовательно, metamorphics не заменяют literal expectations. NoREC/TLP тоже могут пропустить общий semantic defect или порчу данных до обоих SQL путей.

**Typed expected transport.** По сообщению coordinator новый full oracle принимал rounded expected BIGINT: nullable `2^60+1` становился float64 ещё в DataFrame inference, последующий SQL CAST сохранял уже неверное число. Здесь этот repro не запускался; fix explicit nullable Int64 **до DataFrame** остаётся под review. Проверка transport обязательна независимо от правильности direct-list formulas: одинаково испорченные producer/expected values могут false-accept.

## Минимальная transport fixture

Предлагаемый exact vector содержит `−2^63`, `2^60+1`, `2^63−1`, NULL; standalone transport проверяет signed BIGINT range, не разрешает отрицательные ID вопреки business contract. Вне диапазона `−2^63−1`/`2^63` — явный reject, без wraparound. Bool/Boolean, BIGINT, timestamp и float остаются отдельными physical types.

Сравнить Python integer literals→explicit Int64→DataFrame→DuckDB BIGINT→Parquet→readback по точным значениям/null bitmap/schema. Создание Int64 **после** inferred float не считается исправлением. Нужны all-NULL column, смешанная nullable column и пустой typed table. Отдельный mutant intentionally округляет expected ID и freshly reseals fingerprints: literal equality обязана отвергнуть его. Model float32 — следующая declared encoding seam, где collisions допустимы по своему contract; она не легализует округление join keys или source expectations.

## Bounded generator — proposal

Один набор:≤32 cases, каждый≤24raw events/4anchors/16candidate pairs. AST только из существующего005 vocabulary: шесть grains, view/cart/purchase, count, exact distinct, observed recency, два matching-count shares с dependency closure. Windows берутся из принятой grammar; отдельные validator rejection cases могут покрывать valid compiler bounds. Log/threshold/nested operators не становятся legal благодаря тесту.

Deterministic edge bank гарантирует lower-bound/cutoff witnesses, exact duplicates без eventID, repeated distinct entity, full-prefix recency старше7d, zero denominator, unknown conditional key, mixed-NULL global latest bucket и off-C category denominator. Остальные маленькие cases генерируются по pinned seed/version; shrinking сохраняет invalidity/failing property, UTC boundaries и metadata witness. Не подбирать seed по model quality. Hypothesis optional после отдельного dependency решения; первый generator возможен в существующем окружении без нового package.

## Metamorphic obligations с preconditions

- Перестановка **глобальных** same-second peers не меняет keyed values. Нельзя вводить rowid как event order или выбирать первый metadata row.
- Suffix сevents≥t не меняет F на фиксированном anchor t/context. Поздние anchors и Y в будущем horizon вправе измениться; инвариант не относится ко всему Q/Y/C/F bundle автоматически.
- Копия существующего raw event увеличивает соответствующие raw counts, но не exact distinct entities; recency и metadata set этого bucket не меняются. Ratios могут измениться. Expiry предпоследней копии сохраняет distinct, последней — уменьшает.
- Bijection non-NULL IDs сохраняет equality-based features после обратного key mapping. Она может изменить SHA query sampling, product-ID tie breaks, row order, rankings и trained predictions; эти объекты не получают invariance promise. NULL не переименовывается в обычный ID.
- Общий time shift сохраняет relative windows/recencies только при совместном сдвиге source bounds/anchors/availability. Для daily clock сохранять UTC midnight; day-count требует целых UTC суток. Date-dependent SHA sampling всё равно может измениться, поэтому pure calculation проверяется на фиксированных mapped Q/C.
- TLP partitions должны покрывать TRUE/FALSE/NULL bag. Counts складываются; distinct пересчитывается по union projected keys, shares — из восстановленных numerator/denominator, не средней partition ratios.

## Mutants и следующий gate

Обязательные tiny witnesses должны обнаружить: `<t`→`≤t`; исключение lower boundary; sum daily uniques; unknown conditional NULL→0; metadata first-row/backoff; expected-domain INNER JOIN, теряющий known-empty key; representative Frow вместо every-row comparison; float64 transport и denominator0→0. Mutant rejection должен указывать semantic/type gate, а не случайный stale hash; synthetic dependent seals обновляются намеренно.

Prospective correctness gate требует exact keys/types/integers/NULL/flags, заранее объявленной float tolerance, нуля literal mismatches и обнаружения всех названных non-equivalent mutants. Evidence хранит actual case/operator/boundary coverage, seeds, minimized witnesses и uncovered scopes; passed random cases не доказывают universal equivalence. Preparation, generation/shrinking, failures и cleanup входят в существующий будущий verification ledger; cap не увеличивается автоматически. Acceptance/production/новые fits этим исследованием не открываются.
