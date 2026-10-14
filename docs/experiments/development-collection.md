# Расширение development-данных отдельными фазами

15 октября 2026. TLAB-017, первая итерация: контракт, конфигурации и план коллекции. 9 synthetic checks прошли; plan scope принят независимым ревью. **Исполнитель реальной коллекции пока не реализован, новые обучающие данные не рассчитаны.** TLAB-017 ещё не завершён.

Принятые temporal/protocol/anchor/candidate модули не изменяются. Вместо одного увеличенного v1-пилота фазовый контракт составляет несколько обычных v1 shards по 1–3 дня. Каждый shard сохраняет те же eligibility, seed, endpoints, candidates и сырой history policy. Это позволяет сохранить исходные ограничения и проверять стоимость каждой части.

| Фаза | Query anchors UTC | Labels доступны до | Назначение |
|---|---|---|---|
| Train | 8–20 октября включительно | 21 октября 00:00 | Обучающие строки |
| Selection | 22–23 октября | 24 октября 00:00 | Выбор настроек, loss, блоков и автоматизации |
| Confirmation | 24–25 октября | 26 октября 00:00 | Одна проверка заранее замороженного решения |
| Final holdout | с 26 октября | Здесь не используется | Отдельный заключительный этап |

План train: 13 дней × максимум 2 000 пользователей = 26 000 query-days. Пять shards имеют caps 6 000 / 6 000 / 6 000 / 6 000 / 2 000; суммарный предел кандидатов — 5 720 000. Это арифметические ограничения, не измеренные counts или скорость. Selection и confirmation имеют отдельные caps по 4 000 запросов / 880 000 пар.

Планируемый checkpoint обучается на данных до 21 октября и считается доступным к 22 октября. Это явно заданный промежуток для обучения. Для train model_timing описывает будущий выход, а не признаки ранних обучающих строк. Для selection/confirmation он описывает входной компонент, который обязан существовать до первого запроса. Фактические model artifacts, fit cutoffs и hashes будут проверяться training runner; текущий контракт не объявляет модель обученной.

Confirmation закрыта по умолчанию. Для допуска нужен проверенный lock с временем заморозки и SHA как сильного baseline, так и выбранной ветви. Одна победа над support-control не заменяет сравнения с сильным baseline. Проверка схемы lock сама по себе не подтверждает содержимое checkpoints: будущий исполнитель должен сверить реальные файлы и приёмку. Новые гипотезы не открывают использованную confirmation повторно.

[Контракт](../../scripts/development_collection.py) проверяет UTC, границы source/final holdout, maturity последнего target, timing, caps и согласованность фаз. [Train](../../configs/development/train.json), [selection](../../configs/development/selection.json), [confirmation](../../configs/development/confirmation.json) — версионируемые конфигурации. build_collection_plan создаёт identity со статусом planned_not_executed, содержащую точный план shards и fingerprints источника, реестра и кода.

9 проверок покрывают точное непрерывное покрытие train shards, неизменность v1-семантики, output/input timing, maturity при разных endpoints, защиту final holdout и confirmation, обязательный сильный контроль в lock, несовместимые фазы, неизвестные поля/границы/лимиты и устойчивость identity. Реальный source не читается.

До исполнения остаются runtime review и отдельная согласованная установка CPU CatBoost и новая воспроизводимая dependency-lineage. Старые fingerprints не переписываются. Затем исполнитель должен сохранять отдельные принятые shard manifests/артефакты, проверять совпадение source/registry/policies, отсутствие дублированных query-days и пропусков диапазона, согласованность totals и incomplete status при частичном сбое. Признаки экспортируются частями; вся широкая коллекция не накапливается в одной 2GB temp relation.

Первое обучение остаётся smoke. Для критерия задания нужен отдельный ограниченный подбор сильного ручного baseline и честное сравнение автоматизации при одинаковом бюджете и протоколе.

Ревью первой итерации обнаружило, что lock мог предшествовать доступности checkpoint. Добавлено требование available_at≤frozen_before≤first_confirmation_query и regression для lock20октября при доступности модели22октября;9testsPASS. Это ещё не доказательство хронологии выбора победителя: будущий runtime отдельно проверит завершение selection и доступность её labels до решения, а также реальные model artifacts и приёмку.


## Independent plan acceptance — 15 октября 2026

[Peer review/fix audit](../backlog-reviews/tlab-017-plan-verification.md) принял только phase validator/planner scope:9synthetic testsPASS0.016s. Исправлен lock chronology: checkpoint available_at≤frozen_before≤first_confirmation. Planned identity не становится actual collection manifest. Runtime shard lineage/counts/completeness, фактические source/code/output pins и selected-decision availability ещё не проверены.017 неdone, confirmation не открыта; следующийruntime изменяется отдельным reviewed increment.
