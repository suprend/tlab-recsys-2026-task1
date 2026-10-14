# TLAB-017: независимая проверка additive phase plan

15 октября 2026. **Verdict: accept только для plan/validator scope. TLAB-017 не done; executor и actual collection не приняты.** Прочитаны actual [development_collection.py](../../scripts/development_collection.py), [tests](../../tests/test_development_collection.py), три [phase configs](../../configs/development/train.json), [документация](../experiments/development-collection.md), additive schema brief и canonical reservation gate. Все owned файлы были untracked, поэтому проверено полное содержимое, а не сделан вывод по пустому diff. Reviewer не менял repo/Git/code/data/deps и не запускал collection/train. TLAB-008 dependency work и uv.lock не ревьюировались.

## Фактическое исполнение

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_development_collection.py -v
```

**Exit0; Ran9 tests in0.016s; OK.** Только scoped synthetic017; реальные source/shard/model artifacts не читались. Входные hashes tests — синтетические декларации, не fingerprints рассчитанных данных.

## Проверенный план и временной контракт

[validate_phase](../../scripts/development_collection.py#L30) требует точные поля/версию, поддержанные roles, UTC second-resolution timestamps, midnight boundaries, project-relative config/registry paths, явный confirmation lock policy и integer caps. Unknown/missing fields, bool вместо shard-days/budget, неподдержанный test-role и несовместимые ranges отвергаются по коду. Source/final bounds проверяются, максимальный label horizon — принятым001 maturity rule с endpoint и availability delay.

Train anchors `[Oct8,Oct21)` дают13 дней и **cap**, а не observed total:26000 Q и5720000 candidate pairs. Последний target `[Oct20,Oct21)` зрел при доступности `<Oct21`; right-closed target при том же cutoff отвергается. `fit_data_cutoff=Oct21`, planned `available_at=Oct22`: positive availability gap проверяется. Для train timing описывает **выходную будущую модель**, а не разрешённый learned feature ранних train rows. Для selection/confirmation та же timing запись описывает уже доступный входной checkpoint и должна удовлетворять ready≤first query.

[shard_protocols](../../scripts/development_collection.py#L83) создаёт exact contiguous cover train: `[8,11)`, `[11,14)`, `[14,17)`, `[17,20)`, `[20,21)`. Caps6000/6000/6000/6000/2000; outer candidate cap сходится. Source/query/target/candidates/history исходного v1 протокола не изменяются, каждый shard заново проходит v1 validator. Это не oversized26000-row v1 run.

Selection `[Oct22,Oct24)` и confirmation `[Oct24,Oct26)` имеют caps4000Q/880000 pairs каждая; labels доступны доOct24 иOct26 соответственно. Final holdout сOct26 в этих configs не открывается. [validate_phase_set](../../scripts/development_collection.py#L101) требует ровно три разных roles, общий protocol/registry/model timing/final boundary и отсутствие overlaps/недоступных selection labels перед confirmation. Преднамеренный train→selection gap сохранён; непрерывность требуется внутри каждой planned phase, не через этот fit gap.

## Сохранённый finding/fix audit: confirmation freeze

Coordinator сообщил воспроизводимый дефект первоначальной версии: `authorize_phase_execution` принимал `frozen_before='2019-10-20T00:00:00Z'` при declared checkpoint availability22 октября. Это противоречило требуемому `available_at≤frozen_before≤first_confirmation`.

**Исправление уже присутствовало к первому чтению reviewer.** Исходный buggy snapshot reviewer заново не исполнял, поэтому исходное воспроизведение атрибутируется coordinator. В actual revised [authorization](../../scripts/development_collection.py#L125) есть обе проверки: freeze раньше availability и позже первого confirmation query отвергается. Hashes сильного baseline и выбранной ветви обязательны; approval/version/hex SHA проверяются. В [исполненном regression](../../tests/test_development_collection.py) явно есть freeze20 октября, late freeze24 октября+1секунда, approved=False и malformed strong-baseline hash; все rejected, timely lock принимается. Known finding закрыт для declared checkpoint timing.

## Identity и смысл acceptance

[build_collection_plan](../../scripts/development_collection.py#L153) включает phase, точные generated shard protocols, declared source/registry hashes и code hashes в canonical SHA-256 identity. Требует uv.lock/module hashes; одинаковые inputs дают тот же ID, registry change — другой. `status='planned_not_executed'` сохранён; measured query count или accepted actual shard IDs не выдумываются. Наличие planned source hash не доказывает совпадение реального файла; это обязанность будущего executor.

## Обязательные будущие runtime gates

1. **Decision availability.** Planned checkpoint readiness22 октября не доказывает доступность выбранного после selection решения. До открытия confirmation executor проверяет actual strong-B/selected-model/decision artifacts и их accepted hashes, fitted-state цепочки и `max(actual_model_available_at, selected_decision_available_at)≤frozen_before≤first_confirmation`. Использование selection labels допустимо только после их maturity/availability. Если решение невозможно заморозить вовремя, запрещено задним числом датировать lock или переименовывать reused screening в confirmation. Схема lock пока не хранит эти факты — это явно остаётся runtime gate, не закрытый этим accept.
2. **Approved calendar/protocol.** Приняты именно эти phase configs с final boundary26 октября. Будущий executor должен сверить accepted config/code/registry/source fingerprints; caller-supplied другой `final_holdout_start` не становится автоматически разрешением изменить reserved holdout. Generic validator проверяет согласованность declared boundary, не authority на её перенос.
3. **Actual shard completeness/lineage.** Нужны реальные accepted manifests/outputs каждого shard, совпадение semantic policies/source/registry, exact range cover, отсутствие duplicate query-days/IDs, reconciliation row counts/labels/candidates/features и outer incomplete status при partial failure. Текущий модуль конструирует planned cover, но не проверяет собранную actual collection. Caps не равны6000 фактически sampled Q в каждом shard без измерения.
4. **Resources/training.** Partitioned feature exports, bounded shape/typed matrix/group validation, measured preparation/fit/scoring costs, persistent deadline/RSS/spill и partial reports; не собирать всю wide collection в одной2GB relation. Dependency/uv.lock migration требует новой честной lineage, без переписывания старых accepted pins. Это отдельная работа, здесь не выполненная. Два smoke fits не доказывают tuned strong B или эффект016.

**Материальных незакрытых defects в actual plan-only scope не найдено.** Можно продолжать отдельную реализацию executor с перечисленными gates; принимать017 как исполненную коллекцию или открывать confirmation по одному schema-valid lock этим review нельзя.
