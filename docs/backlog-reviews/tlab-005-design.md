# TLAB-005: короткое независимое prereview дизайна

15 октября 2026. Проверены design brief, [feature index](../features/index.md), [review 01–04](../features/review-01-04.md), [review 05–08](../features/review-05-08.md) и [TLAB-005](../backlog.md). **MVP принят для реализации с уточнениями ниже; production остаётся blocked до acceptance TLAB-004.** Это проверка проекта, не принятие будущего кода. Репозиторий, Git, dependencies, raw data и tests не изменялись/не запускались.

## Существенные условия перед реализацией

1. **Category denominator нельзя ограничивать queried products.** Оптимизация «bounded queried products/relevant categories» должна иметь разные predicates: item/pair states ограничены нужными товарами, category denominator — всеми исходными views нужной категории. Воспроизводимый дефект: кандидат A и отсутствующий в C товар B имеют по одному view категории c; ограничение source по C даст ratio=1 вместо 1/2. Минимальное решение: отдельная category aggregation без product shortlist filter.

2. **Per-day batch не заменяет exact anchor t.** Для разных timestamps одного UTC-дня общая дневная агрегация может включить события после раннего anchor. Например, view в 11:00 запрещён для t=10:00 и разрешён для t=12:00. Batch может делить scan, но joins/filters/state snapshot используют точный t. Альтернатива для первого MVP — явно принимать только единый timestamp каждого batch и отклонять unsupported anchors. Это незакрытый seam дизайна, не утверждение о баге ещё не написанного кода.

3. **Исторические категории не переклассифицируются.** Текущая as-of категория кандидата c выбирает исторические строки `(item=i, event.category_id=c)` для numerator и `event.category_id=c` для denominator. Нельзя переназначить все старые views товара его текущей категории. Registry должен назвать numerator именно item×category count; при category move это отличается от общего item-view7d. Latest-second conflict resolver обязан учитывать NULL: обычный distinct nonnull count не различает `{c}` и `{c,NULL}`.

## Принятый MVP

Сохраняется ровно 18 числовых признаков: user4, pair5, item3, user-category3, item-category3. Добавлять новые признаки этим review не требуется. User-category share использует user-view7d denominator; known key/empty history даёт count0, unavailable category — conditional NULL, denominator0 — ratio NULL. Безымянные numeric IDs работают независимо от code.

Candidate category — последняя глобально наблюдённая секунда `<t`; конфликт разных IDs/known+NULL даёт unavailable с ambiguity flag, без отката к более старой удобной строке. Counts raw; exact distinct дедуплицирует membership, не складывает daily uniques. Pair/category recency и user/item first-past age используют полный `[S,t)`, не только 7d. Source coverage определяется S, независимо от первого события сущности. Retrieval input block фиксирован одинаково во всех ветвях и сохраняется отдельно от registry18.

## Обязательные проверки и ресурсы

- Hand golden плюс независимый bounded SQL oracle: `t−W` включён, `t` исключён; перестановка глобальных peers и future suffix сохраняют values/metadata/masks.
- Category fixtures: два IDs одного code, unnamed ID; latest-second `{c,c}`, `{c,NULL}`, `{NULL}`, `{c,d}`, затем чистая новая секунда. При move A→B старые A-views не попадают в B numerator. Некандидат той же категории участвует в denominator; known category без views даёт counts0/ratioNULL.
- Distinct expiry: повтор A в 0/4 и B в3 при W10: t10=3/2, t11=2/2, t14=1/1, t15=0/0. Raw duplicate увеличивает count, сохраняет distinct.
- Событие старше7d сохраняет recency/first-past age при нулевых window counts; cart-only history определяет возраст, не view recency. Нет прошлого — age/recency NULL, coverage отдельно; при секундном strict-past определённая recency>0.
- Результат сохраняет ровно все уникальные `(q,i)` из C; joins не размножают строки. NULL допустим, finite defined ratios в `[0,1]`; ни daily grouping, ни candidate filter не меняют смысл.

Tiny→100 label-independent queries→reviewed pilot: 2 threads, DuckDB2GB/spill, ≤60 минут, peak RSS≤8GiB. До масштабирования фиксировать scan bounds/rows, state keys, spill/disk, elapsed/RSS, registry/source/Q/C/code hashes. Output cap не ограничивает full-prefix scans. При превышении gate — partial cost report и остановка run; batch/sample уменьшается без скрытой смены окон/distinct/category semantics.
