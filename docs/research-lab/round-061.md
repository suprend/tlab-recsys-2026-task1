# Round061 — что пользователь получает от typed automation016

**Deductive/source assessment, 15 октября2026.** Прочитаны опубликованные [feature-programs design](../experiments/feature-programs.md), [symbolic module](../../scripts/feature_programs.py), [symbolic code acceptance](../backlog-reviews/tlab016-programs-code-review.md), [source-producer code rereview](../backlog-reviews/tlab016-source-collection-code-rereview.md) и [selection contract](../experiments/feature-program-selection.md). Actual source outputs, формулы на real data, модели, WIP runners и reserved targets не инспектировались. По полученному статусу producer выполняется; **formula/quality acceptance этой note не предоставляется**. Никаких запусков, новых HYP, framework или задач.

## Три разные автоматизации

Первое — **symbolic generation**: `generate_pool(contract,base_registry)` строит definitions в циклах parameterized families, выводит opposite entity projection из typed grain, создаёт имена, signatures и physical schema. Восемь готовых registries не перечислены в конфиге. Это содержательное отличие от ручного выбора списка feature JSON.

Второе — **calculation**: полученный registry передаётся существующему005 compiler. Один и тот же reviewed vocabulary выполняет count/distinct/observed recency с query context, masks, coverage и заданными temporal predicates. Генератор не рассчитывает SQL, не читает labels и не удостоверяет source values. Принятие source-producer code подтверждает проверенные lifecycle/lineage rejection paths, но не успешность текущего actual source run.

Третье — **quality selection**: отдельный протокол сравнивает B с четырьмя frozen additions и выбирает W по development metrics. Это supervised model choice, даже если generation и numeric features не используют labels. Он не обучает proposer и не адаптивно порождает следующие AST после feedback. Название «автоматический selector» допустимо для применения фиксированного правила; «learned intelligent feature search» — нет.

## Переиспользуемость без преувеличения

Current contract принимает точные поля user_id/product_id/event_time/event_type/category_id, actions view/cart/purchase, окна24/168h и конкретные bindings. `_validate_contract` требует каноническую schema, а `generate_pool` сверяет exact expected bindings. Это deliberate bounded implementation: редактирование произвольного поля в JSON не превращает модуль в generic adapter.

Следовательно, переиспользуемы функции и semantics при иных допустимых event bags/Q/C внутри того же schema/context, а не произвольные новые datasets. Human-authored остаются annotation ролей, availability assumption, raw-bag grain, strict-past/global-peer policy, окна, families, binding choices, I priorities и random law. Они входят в identity, а не исчезают после генерации. Nominal entity IDs не становятся numeric model signals; отсутствующий action нельзя подменить наблюдённым нулём.

[DFS2015](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf) и [официальный Featuretools tutorial](https://featuretools.alteryx.com/en/stable/getting_started/afe.html) используют relational entities/relationships и primitives; depth задаёт stacking. Это первичное основание separation schema/definitions/calculation, а не основание приписать016 DFS recursion или произвольные relationships. [ExploreKit](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf) содержит learned candidate ranking и wrapper selection; [OpenFE](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf) — supervised FeatureBoost/pruning. Эти механизмы здесь не реализованы. Концептуальная близость не воспроизводит их benchmarks, cost или quality claims.

## Конкретный user-facing пример без private acceptance state

Для README достаточно **одного** source-free symbolic walkthrough и существующего tiny correctness fixture, отдельно от real rerun. Пример должен называть реальные interfaces:

1. Прочитать committed automation-pool contract и manual-18 registry; вызвать `generate_pool`.
2. Показать family/binding→L02 definitions: pair count(view,24h), count(cart,24h), count(purchase,24h), их exact generated names и BIGINT physical columns.
3. Вызвать `allocate_slots`, показать actual saved allocation L02/L06/L01/L05, state/version identities и collision-consumed policy; это0fits и не durable execution claim.
4. Через `registry_for_slot(...,'I1')` получить B+definitions; показать B41-first model order отдельно от SQL physical order и ровно3-column delta.
5. На уже проверенном literal fixture показать expected values и ссылку на accepted test/source audit; не запускать неподтверждённый real source command ради демонстрации.

Иллюстрация semantics, **не выполненный тест**: у пары(U,I) view вT−1h, cart вT−2h и purchase ровноT. L02 наT даёт(1,1,0). Добавление exact duplicate view повышает только view count до2; purchase peer остаётся исключён. Это наглядно объясняет raw-bag count и глобальное `<T`, не выдавая observed source age за exposure. Отдельный recency example нужен, чтобы увидеть value+automatic mask как physical closure, а не «три новых core features».

Current module предоставляет Python API, standalone CLI отсутствует. Поэтому reproduction wording должен либо дать точный короткий API example с expected output, либо ссылаться на реально существующий entrypoint/test; нельзя выдумать `feature_programs --run` или обещать fresh source acceptance из одного pool_id. Это уточнение уже существующего README/reproduction scope, **не новая framework-задача**. Symbolic replay доступен без ignored approvals; real Q/Y/C/F/control/016 rerun требует существующего внешнего verification/bootstrap workflow и новой execution identity.

## Evidence ladder и возможные исходы

| Evidence | Максимально честный вывод |
|---|---|
| Accepted symbolic/tiny | Ограниченные schema/templates порождают legal distinct programs с exact closure; выбранные additions проверены на adversarial fixtures |
| Future independently accepted source export | Selected12 рассчитаны корректно на конкретном accepted Q/C/source; сохранён oldB на каждой physical row |
| Future four matched fits | Измерено влияние четырёх объявленных добавлений при той же accepted019 learning procedure |
| Future reserved evaluation после seals | Оценён frozen W−B на объявленном heldout population; не универсальная search-strategy superiority |

OldB equality против принятого F — preservation, не exhaustive source formula proof всех41columns. Symbolic eight closures — не numeric oracle всех24potential additions; вычисляется только selected union12. Нельзя смешать эти уровни в «все автоматически созданные признаки полностью доказаны».

Если W=B после complete valid comparison: генерация/расчёт реализованы и экспериментально проверены, но заданные additions не вытеснили контроль. Если W=random: возможный measured gain принадлежит смешанной bounded typed-automation процедуре; static-I superiority не доказана. Если W=I: выигрывает конкретная заранее фиксированная программа; двух I и двух R недостаточно для learned-intelligence/general-strategy claim. В любом случае selection gain не равен untouched holdout gain, а no-positive/undefined estimand, resource-incomplete и integrity-invalid outcomes сообщаются отдельно.

Task1 automation route допускает этот инженерно-экспериментальный результат без обязательного превосходства B, но не даёт гарантии формальной оценки задания. Strongest claim требует завершённых существующих source/model/repro gates. Экономия human-hours, ускорение против уже batched005, переносимость качества и автономное semantic discovery остаются вне evidence. **No-add outcome:** ясный README walkthrough и scoped final wording; новые задачи, fits, operators и framework не нужны.
