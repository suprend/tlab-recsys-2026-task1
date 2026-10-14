# Первый CPU boosting эксперимент

15 октября 2026. TLAB-008: зависимости приняты, training runner реализован и проходит независимое ревью. **Настоящие модели ещё не обучались.** Синтетические CPU fits проверяют API и поведение pipeline; не являются качеством baseline. До первого реального fit нужны принятые коллекции017 train/selection и отдельный coordinator approval ровно двух fit attempts.

## Проверяемая постановка

Для одного query `(user,t)` сортируются существующие кандидаты C по raw model score. Метка — принадлежность полному future purchase-set Y из принятого v1 протокола `[t,t+24h)`. Покупки вне C остаются retrieval misses. Отсутствие покупки не объявляется dislike или отказом после показа; вероятностная калибровка classifier не заявляется.

Используются одни и те же выбранные train query-days, C, числовые признаки и full Y. Train subset — до 6000 query-days по заранее заданному `sha256(query_id),query_id` до чтения labels; selection сохраняется целиком. Все зрелые query с непустым C обучают Logloss с object weights `1/|Cq|`. PairLogit использует только информативные training groups `p>0,n>0`, явные все `p*n` пары и pair weights `1/(p*n)`; веса строк сюда не переносятся. Группы без пары и пустой C отдельно посчитаны и остаются в evaluation. Это различие loss и training support, не одинаковая популяция градиентов. Вставки будущих positives и искусственных negatives нет.

Матрица float32 включает core manual18, имеющиеся missing flags, observed-age/coverage/context и retrieval signals. Raw query/user/product/category IDs не являются числовыми признаками; timestamps служат только ключами либо преобразуются в strict-past age. Last user event age и missing flag добавляются явно. Числовой NULL остаётся NaN; fitted imputer/target encoder/CTR отсутствует. Данные сортируются по group index/product ID; подготовка заранее проверяет предел числа строк. Размер матрицы учитывается отдельно от полного процесса и CatBoost Pool.

## Принятые данные и контроль происхождения

`verify_collection` требует внешний документ version1 с scope `reviewed_development_collection`, collection ID, именем complete attempt report и точными fingerprints. Обязательный набор путей выводится из plan/state/shards/manifests: state, plan, complete report, source/config/code/lock inputs плана, все Q/Y/C/F seals, approvals частей и все producer input/code paths, включая specification selection005. Отсутствующие и лишние pins отвергаются; все фактические файлы проверяются. Статус `complete_produced_unreviewed` производителя сам по себе не приёмка: coordinator выдаёт approval после независимой проверки источника/формул. В model identity включается сам acceptance файл.

Для train/selection сверяются source/registry/base semantics, candidates/history/target/seed и model timing. Train labels доступны к fit cutoff; checkpoint имеет положительный compute gap и доступен до первой selection query. Runtime budget, включая подготовку, fit и evaluation, не превышает этот gap. Это историческая симуляция доступности; фактическое время выполнения в 2026 году записано отдельно. Confirmation и final holdout runner не принимает. Хронология selection decision → confirmation проверяется отдельным поздним gate.

`prepare_fit_plan` создаёт только предложение эксперимента. Coordinator после code/data review выдаёт отдельный approval scope `cpu_smoke_two_fits` с точным run ID и fingerprints. Ровно две попытки: Logloss, PairLogit. Глобальный atomic consumption claim в artifacts/fit-claims учитывает identity независимо от выбранной папки вывода. Повтор той же identity сохраняет прежний результат и отказывает до fit; восстановление упавшего эксперимента требует рассмотрения оставшегося бюджета, а не бесплатного повторного подбора.

## Фиксированный smoke

[Конфигурация](../../configs/models/cpu-smoke.json): CPU, 2 threads, Plain, bootstrap No, seed2026, depth6, learning rate0.05, L2=3, **50 фиксированных деревьев**, максимум6000 train Q /1.32m matrix rows /2m explicit pairs. Общий wall budget3600s, cooperative RSS ceiling8GiB. CatBoost callback проверяет deadline/RSS между iterations; подготовка, predict, экспорт и hashes проверяются до/после этапов. Это не OS kill, пик внутри одного этапа может быть обнаружен позже.

Native `eval_set`, overfitting detector и best-model selection не используются; `use_best_model=False`. Checkpoint — заранее объявленная последняя iteration. Число деревьев сверяется с планом. Полный selection Y оценивает независимый evaluator006: conditional/all-query и query/user macro, nonempty fraction, Recall/NDCG/AP/MRR@20. Порядок при равных raw scores — product ID ASC. PairLogit−Logloss user-cluster bootstrap имеет screening interpretation; smoke не выбирает окончательную модель и не даёт confirmatory promotion.

Выходы: immutable model identity, stage/error/cost report, фактические model parameters, support/weight/pair accounting, два CBM, scores NPZ для всех C и SHA каждого файла. Ошибки и прерванные fit attempts оплачиваются, `complete` не выставляется. Перед завершением ещё раз проверяются все входы против принятого bundle.

## Проверки и текущий результат

22 scoped checks прошли, включая настоящие tiny CatBoost CPU fits обеих целей и полный двухмодельный smoke/export. Проверены query mass и pair mass, all-negative/all-positive/mixed/empty-C/retrieval-miss groups, remapped pair indices, cap до выделения pair arrays, contiguity, raw ID exclusion, float32 и missing semantics, выбор train Q независимо от изменения Y, full-Y IDCG и tie order, callback timeout, checkpoint availability/compute gap, strict external collection/fit approval, missing/extra/tampered pins, отказ повторного immutable fit. Тесты используют маленькие синтетические данные и не дают оценки качества на REES46.

Фикстуры разработки потребовали явного Python int при передаче NumPy int32 в DuckDB и исправления тестового примера на действительно нарушенную contiguity; итоговый scoped run22PASS. Source/feature/code acceptance tests проходят на настоящем synthetic017 lifecycle, а не на одном mocked hash.

Первый реальный017 Q/Y/C pass пока ожидает source review: train26000 Q /619 full targets /5317058 C /496 positive queries; selection4000 Q /96 targets /817149 C /73 positive queries. Обе коллекции теперь содержат полные признаки: train5317058 и selection817149 строк; механические проверки точного C/F покрытия прошли. Финальная независимая приёмка численных source spotchecks ещё ожидается, обучение закрыто. Малое число положительных selection queries ограничивает силу сравнений; bootstrap не исправляет подгонку по development. Эти counts — producer aggregates, не завершённая приёмка коллекций.

Следующий этап после smoke — **отдельный заранее ограниченный подбор сильного ручного baseline**, с реальным выбором checkpoint/config по внешнему full-Y критерию и общим ledger. Затем центральное сравнение задания: автоматизация feature generation/calculation против хорошо настроенного ручного контроля при одинаковых C, histories, split и бюджете. Два стартовых fit не заменяют этот контроль.

Независимое code review выявило два дефекта до реальных fits. Во-первых, смена output_root обходила локальный guard и позволяла заново потратить те же две попытки. Добавлен общий project-level O_CREAT|O_EXCL claim, который не удаляется при сбое; новый destination или failed-first не открывает новый budget. Во-вторых, первая локально прочитанная конфигурация могла отличаться от позднее проверенного плана. Теперь config snapshot и hash берутся из одних bytes, изменение файла внутри подготовки отвергается, а effective config до approval/claim обязана совпасть с verified plan. Regression cases проверяют оба сценария без новых fit и без ложной приёмки. Дополнительно loaded/installed CatBoost, NumPy и DuckDB сверяются с uv.lock, версии Python/platform сохраняются. Исправления ожидают повторного независимого review; настоящих моделей по-прежнему нет.

Повторное независимое ревью подтвердило ещё один integrity gap: заново упакованный plan мог содержать claims о source/registry/code/phase, не соответствующие его же принятым входам. Теперь verifier проверяет точную схему plan/identity/execution inputs, точный producer bundle, равенство source/registry/code hashes фактическим execution pins, actual phase body и соответствие каждому child producer. Пять fault-подслучаев заново создают согласованные новые collection IDs/reports/state/approval hashes, но меняют один смысловой binding; все отвергаются. Это не замена внешней семантической приёмки, а дополнительная механическая проверка. Исправление ожидает scoped re-review.

Перед реальными fits root self-review дополнительно обнаружил, что Pool и predict имеют thread_count=-1 по умолчанию, несмотря на thread_count=2 в fit params. Теперь оба Pool constructor и обе native predict ветви явно получают2. Реальные tiny fits с перехватом Pool kwargs и отдельные predict call-argument assertions проверяют бюджет на этих стадиях; output shape/finite/fixed-tree checks сохранены. Это уточнение resource enforcement, а не новый fit или tuning budget.

Дополнительный независимый финальный reviewer нашёл P1 в повторённой child-lineage проверке008: freshly resealed child мог исключить registry dependency, обязательный manual_features code hash или accepted Q/Y/C approval input. Теперь008 вызывает неизменённые строгие017 _check_cached и candidate/feature lineage gates, сохраняя проверку полного внешнего pin scope и actual plan bindings. Три fault-подслучая полностью перепаковывают child manifests/report/state/approval hashes и отвергаются; физические production artifacts не затрагивались. Исправление направлено на targeted independent re-review, реальные модели пока не обучены.


## Принятый measured smoke — 15 октября 2026

Позднейшая [независимая codeприёмка](../backlog-reviews/tlab008-final-independent-rereview.md) закрыла все findings выше;017train/selection приняты отдельно. [Independent model/output audit](../backlog-reviews/tlab008-smoke-output-verification.md) принял ровно2actualCPU50treefits. [AggregateJSON](../backlog-reviews/tlab008-smoke-aggregate.json) содержит полный ledger/effectiveparams/metrics/200bootstrapdraws.

| Fixed scorer/model | Conditional query NDCG20 | Conditional query Recall20 | All-query zero NDCG20 | All-query zero Recall20 |
|---|---:|---:|---:|---:|
| Popularity007 |0.105936|0.233855|0.001933|0.004268|
| Recent-source-first007 |0.388390|0.571429|0.007088|0.010429|
| Logloss50trees |0.414448|0.581213|0.007564|0.010607|
| PairLogit50trees |0.375197|0.571429|0.006847|0.010429|

Все строки относятся к темже4000selectionQ/73positiveQ/96fullYtargets/817149C; последнийview007 совпал сrecentaggregate. Loglossвышеrecentна.026058NDCG в этом screening, но отдельный uncertaintycontrast противэвристики невычислялся и превосходство неутверждается. PairminusLogloss Δ=-.039250,95%CI[-.085000,-.000891],200userdraws; developmentCI неconfirmation.

Trainbottomhash6000Q даёт1227213rows/114fullYpositiveQ,92informativegroups/101retrievedpositive rows. BCE обучилвсе6000nonemptyCgroups (5908allnegative); Pair18989rows/20741pairs,querymass92. Это loss+supportpolicycomparison. Всего41numericfloat32feature, matrix201262932bytes, rawIDsисключены. FullYoutsideC остаётсяmisses.

Run195c89b9a8500b7977d1840d2ef3a6c7acb8f9cf043e1ca407ac718b22f846b6:22.663335swall/RSS1788100608bytes,2completedattempts/50treesкаждая. Independentreplay всехrawscores/4estimands/bootstrap PASS;1.961741s/2.307942actualCPU s/RSS987611136. ProductionCPUотдельнонеизмерен, его нельзяподменятьwall×2. NativePool/predict/fit explicitly2threads, resourcecheckscooperative.

Для009 единственныйablationobjective=Logloss по заранее выбранномуexternalfullYNDCG rule; сохраняютсяparams/C/Y, изменяетсяодинreviewedmetadata/priceblock. Это рабочийscreeningвыбор, нетunedBclaim. Перед016обязателенотдельныйboundedstrongtuning среальнымfullYcheckpointselection, prospectivecalendar/CPUledger иfreeze. Modelartifacts/NPZ/per-userrows некоммитятся.
