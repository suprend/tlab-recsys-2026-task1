# Red team: что именно автоматизировано и какой итог можно защищать

15 октября2026. Read-only audit [требований task1](../task1-requirements.md), [progress report](../progress-report.md), accepted symbolic generator, fixed pool/allocation/selector и recent research. Actual models, private Y/scores, heldout и artifact jobs не открывались; новых jobs/fits/looks/code/Git changes нет. Ниже критика научных формулировок, не execution acceptance и не гарантия оценки комиссии. Нынешние policy/selection/budgets сохраняются.

Observed public snapshots: progress-report SHA256 `cd4626e25f11f77f0a7ea1664afb2ae7420b543c26326be9579f3c020cfb2c89`; generator `afaefd6b2a608870d952c0782d2ca9fcbd685f9650afe6229ee74772bab92bf7`; pool `ef34f45d244bb0458c2af7928c0dad7f57d178d397abee1a9e87e419457cbbb3`; selector config `3bb1e4f63f32160135daaee95d257f571f394af25f4b74378ba2785be12b5ac0`. Статус в прочитанном report: source принят, model comparison/heldout ещё впереди. Активное исполнение этим не проверялось; будущий final report должен ссылаться на окончательные accepted evidence.

## Сильнейшие добросовестные возражения

**1. «Это восемь заранее придуманных блоков, а не открытие признаков».** Существенно верно. В [коде](../../scripts/feature_programs.py) `_validate_contract` требует exact canonical REES schema, а `expected_bindings` — конкретные bindings. Человек выбрал roles, actions,24/168h, три template families, companions и static I priorities. Ответ не должен отрицать эту зависимость. Однако definitions действительно создаются программно по bindings, выводятся projection, names/signatures, registries и physical closure; восемь готовых feature-JSON списков не просто загружаются. Честное название — **schema-validated generation по human-bounded templates**, не autonomous schema discovery или generic relational search.

**2. «Основной calculation уже делал005; новая генерация лишь снимает boilerplate».** Да: общий compiler существовал для ручного registry. Вклад016 — проверяемый переход contract→generated definitions→legal closure→bounded allocation→same compiler и experimentally matched use. Это инженерная автоматизация конкретной операции, не доказанный новый алгоритм AFE. Чтобы reviewer видел отличие от ручного JSON, нужен один существующий API walkthrough: `generate_pool`→L02 definitions→`allocate_slots`→`registry_for_slot`, с actual names/types/automatic mask, без bespoke per-feature SQL. Новый CLI или generic framework для доказательства не обязателен.

**3. «Термин intelligent прикрывает ручной выбор двух программ».** Static I1=L02/I2=L06 используют human semantic prior; proposer не обучается. R1/R2 — два seeded draws с replacement из того же восьмиэлементного pool, collision consumed/no redraw. Это четыре opportunities, не четыре независимых repetitions стратегии. Даже победа I не устанавливает преимущество intelligent search; random winner нельзя приписывать rule guidance. Primary frozen W−B включает любой из четырёх arms и B; best-I−best-R остаётся descriptive screening.

**4. «Equal width не делает arms равноценными по информации и работе».** Три физических columns включают masks; L06 имеет два cores+mask, другие bundles — три cores. Distinct state отличается от scalar count, shared export не делает per-arm fit бесплатным. Cap12 ограничивает выбранный union, а не означает обучение B+12. «Выбраны лучшие12 из24» неверно:24 потенциальных widths не материализованы и не отранжированы по labels; allocated четыре whole bundles. Ledger показывает actual shared-once и marginal costs, не равенство CPU или speedup над batched005.

**5. «Набор и настройки придуманы после просмотра development».** Это важное уточнение отчёта. Program definitions/formulas не читают Y, allocation заморожена до016 scores. Но авторы знали007/008/009 результаты;019 выбирал B и его procedure на том же development. Поэтому **before016 outcomes ≠ before any validation feedback**. Четыре016 fits/looks описывают текущий stage, не полную историю исследования. Нужна прямая фраза об этой истории, помимо scattered audit links. [Cawley–Talbot](https://jmlr.org/papers/v11/cawley10a.html) показывают риск переоптимизации конечного selection criterion; ledger делает его видимым, не устраняет автоматически.

**6. «Случайная программа могла бы выиграть, а fixed learner недонастроен под новые признаки».** Вторая часть ограничивает estimand, не делает comparison нечестным. Все B+3 наследуют одну accepted019 procedure/population/weights/trained iterations/prefix; это conditional effect добавлений при фиксированной процедуре. Он не равен эффекту оптимального совместного retuning features+learner. Отдельная nested tuning study потребовала бы нового fit/look budget и reservation; нынешний отрицательный результат нельзя спасать таким retuning постфактум.

## Primary prior art: сходство механизма, граница новизны

[DFS2015, §§II–III](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf) строит features вдоль relational paths, поддерживает stacking и отдельно Data Science Machine с ML/autotuning.016 не воспроизводит рекурсивный DFS или весь DSM. [ExploreKit2016, IV](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf) обучает ranking classifier на ранее разобранных datasets и выполняет classifier evaluation; static priorities016 не такой meta-learner. [OpenFE2023, Algorithms2–4](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf) содержит supervised residual FeatureBoost и pruning/attribution; это реальные дополнительные fits/cost, отсутствующие здесь. Ни paper benchmark gains, ни их human-effort discussion не подтверждают наши ranking gain/speed/hours.

Сильнейший novelty claim сегодня: собственная ограниченная реализация generation/legality/closure и независимого temporal/source verification для выбранного purchase-ranking protocol. Это конкретный project contribution, а не новая теория, SOTA или доказанный general-purpose feature discovery.

## Evidence нельзя повышать одним общим словом «проверено»

| Evidence | Что можно утверждать | Чего оно не устанавливает |
|---|---|---|
| Accepted symbolic/tiny review | Восемь legal closures; selected additions проходят adversarial literals/list oracle | Numeric source correctness всех восьми bundles/всех возможных schema |
| Accepted selected12 source proof, опубликованный в report | Все73,610,484 выбранных дополнительных значения и row keys сверены; old45 сохранены | Новый exhaustive source proof всех старых B41; baseline numeric proof остаётся sampled |
| Future accepted matched model/output evidence | Exact procedure, scores/rankings/fullY metrics/selector и paid attempts воспроизведены | Untouched holdout gain или across-seed robustness |
| Future reporting-only evaluation после всех prediction seals | Frozen W−B на declared reserved Q/date policy | Adaptive model improvement после25, online causal lift или whole-user-population effect |

Источник может быть правильным при бесполезных features; model acceptance может быть корректным при отрицательной метрике. Small positive support73 queries ограничивает uncertainty; user-cluster bootstrap200/seed2026 условен на fitted models/dates и сохраняет query-macro estimand, не превращая его в user-macro. Crossing0 означает неопределённость, не equivalence. W=B даёт primary contrast0 по выбору, не доказательство равенства всех четырёх альтернатив. Resource-failed/ineligible arm не является «метод проиграл»; integrity/unknown failure остаётсяSTOP.

## Минимальный финальный отчёт по automation route

Согласно проверенному парафразу task1, автоматизация generation/calculation — самостоятельная исследовательская ветвь; для alternative-method route требуется превосходство tuned boosting. Обязательный выигрыш, LLM, GPU, universal schema adapter или измеренные human-hours в условии не зафиксированы. Поэтому valid no-improvement outcome может быть честным automation result, но одно чтение условия не гарантирует формального соответствия сдачи.

Минимум — понятная связь семи вещей: выбранный observable purchase target/Q/C/fullY; bounded manual tuning и все prior looks; human contract и один generated-program example; exact8→4→union12→fourB+3→W0/3 flow; complete arm/status/metric/cost table по accepted evidence; explicit negative/uncertain/incomplete interpretation и обе clocks; runnable reproduction boundaries с входами/versions/кто выдаёт fresh external decisions. Финальные числа добавляются только из accepted outputs. Нельзя заменить таблицу эксперимента положительным source audit или одним W без проигравших/failed slots.

Готовая честная формулировка после completion:

> «Мы реализовали ограниченную генерацию программ признаков по человечески заданной схеме, templates и окнам, с автоматической проверкой типов, exact aliases и физических зависимостей. Четыре заранее allocated программы сравнивались с bounded tuned manual control при одной learning procedure. Correct calculation и numerical replay проверены отдельно. Результат [не установил добавочного выигрыша / дал положительный observed contrast в указанном scope / остался неопределённым]; learned strategy superiority, generic portability, экономия труда и speedup не установлены. История development feedback и все attempts раскрыты».

## Submission-critical против future ideas

**Критично до итогового claim:** accepted actual016 model/output evidence вместо draft future tense; окончательные reserved-period/source/inference/target seals если заявляется heldout result; воспроизводимый reviewer prefix и честный fresh-run/private-artifact handoff018/README. Current report правильно признаёт, что clone без ignored Q/C/Y/models/approvals не numerical-replays historical study; hashes удостоверяют identity, но не доставляют отсутствующие значения. Existing018 phase2 уже адресует этот gap, отдельная задача не нужна. Невыполненный полный rerun нельзя назвать продемонстрированным.

**Не требуется расширять нынешний pipeline:** HYP002 adapter conformance может опровергнуть generic-transfer claim маленькими metadata/unknown-action fixtures; HYP001 support-controlled ItemCF проверил бы compatibility сверх степени; HYP046 same-AST/full-sink comparison опроверг бы speed claim при отсутствии экономии относительно unchanged005. Эти followups уже специфицированы, требуют отдельного approval/ресурсов/label reservation и не являются условиями завершения текущего эксперимента. Новых HYP, mandatory runs, fit/look allowances или post-outcome rule changes этот audit не предлагает.

## Definition-only walkthrough для преподавателя: existing API, без исполнения здесь

Рекомендация для README после проверки владельцем documentation. Из корня repository, в уже подготовленном locked environment, следующий существующий API читает только два committed JSON и печатает definitions/closure/allocation. Команда **в этом audit не исполнялась**; SQL, feature materialization, model/Pool/fit и approvals она не вызывает. Это demonstration generation, не historical metrics replay.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import json
from pathlib import Path
from scripts.feature_programs import generate_pool, allocate_slots, registry_for_slot

contract = json.loads(Path('configs/features/automation-pool.json').read_text())
base = json.loads(Path('configs/features/manual-18.json').read_text())
pool = generate_pool(contract, base)
allocation = allocate_slots(pool)
for bundle in pool['identity']['bundles']:
    if bundle['bundle_id'] in ('L02', 'L06'):
        print(json.dumps({
            'bundle': bundle['bundle_id'],
            'generated_definitions': bundle['programs'],
            'physical_delta': bundle['physical_delta'],
            'model_width': len(bundle['model_feature_order']),
        }, indent=2))
print(json.dumps(allocation['identity']['slots'], indent=2))
registry = registry_for_slot(pool, allocation, 'I2')
print('I2 core definitions:', len(registry['features']) - len(base['features']))
print('execution_approved:', allocation['identity']['execution_approved'])
PY
```

Статически ожидаемый смысл: L02 порождает три pair-count24h definitions, L06 — cart recency плюс item-cart-count24h, а physical delta L06 содержит ещё automatic BOOLEAN missing flag. У каждого model width44=B41+3; I2 добавляет **два core definitions**, не три. Allocation показывает I1/L02,I2/L06,R1/L01,R2/L05, `native_fits_started=0`, `execution_approved=false`. Physical order count/recency/mask не обязан совпадать с prose order; authoritative список печатается из pool. Human bindings видны в исходном JSON, generated definitions — в output; metric-based W selection этой демонстрацией не производится. Так reviewer непосредственно видит полезную автоматизацию и её границу без private acceptance state или выдуманного generic CLI.


## Publication scope appendix — 15 October 2026

Original note SHA256 481b7bc90829d64cb753b99f3f54a8aa9219568f4301166dc93dfb8d0b66e8be. This retained research snapshot predates the locally accepted actual016 model evidence in the current [progress report](../progress-report.md). Its future tense is historical scope, not the current canonical execution status. No new hypothesis execution, resource grant, fit, source download or reserved-target access is authorized by publication. Current accepted development winner is R2; this does not establish guided-strategy superiority or heldout improvement.
