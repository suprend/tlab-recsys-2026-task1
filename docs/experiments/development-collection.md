# Расширение development-данных отдельными фазами

15 октября 2026. TLAB-017: первая итерация контракта и плана принята; вторая добавляет исполнение с независимой приёмкой каждой части. **Runtime code и реальные train/selection collections приняты независимо; TLAB-017 завершён.** Это не обученный boosting и не открытие confirmation.

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

Runtime review принят отдельно; до model fits остаётся независимая приёмка реальных коллекций. CPU CatBoost установлен отдельным принятым изменением; новая dependency-lineage не переписывает старые fingerprints. Исполнитель сохраняет отдельные shard manifests/артефакты и проверяет совпадение source/registry/policies, отсутствие дублированных query-days и пропусков диапазона, согласованность totals и incomplete status при частичном сбое. Признаки экспортируются частями; при объединении используются Parquet views и узкие проверки ключей, вся широкая коллекция не накапливается в одной temp relation.

Первое обучение остаётся smoke. Для критерия задания нужен отдельный ограниченный подбор сильного ручного baseline и честное сравнение автоматизации при одинаковом бюджете и протоколе.

Ревью первой итерации обнаружило, что lock мог предшествовать доступности checkpoint. Добавлено требование available_at≤frozen_before≤first_confirmation_query и regression для lock20октября при доступности модели22октября;9testsPASS. Это ещё не доказательство хронологии выбора победителя: будущий runtime отдельно проверит завершение selection и доступность её labels до решения, а также реальные model artifacts и приёмку.


## Independent plan acceptance — 15 октября 2026

[Peer review/fix audit](../backlog-reviews/tlab-017-plan-verification.md) принял только phase validator/planner scope:9synthetic testsPASS0.016s. Исправлен lock chronology: checkpoint available_at≤frozen_before≤first_confirmation. Planned identity не становится actual collection manifest. Runtime shard lineage/counts/completeness, фактические source/code/output pins и selected-decision availability ещё не проверены.017 неdone, confirmation не открыта; следующийruntime изменяется отдельным reviewed increment.

## Runtime: производство и внешняя проверка

Исполнитель `run_phase` сначала требует отдельный producer approval со scope `reviewed_producers_and_phase_plan`. Координатор выдаёт его после ревью кода и конкретного phase plan: совпадают collection ID и полный bundle fingerprints исходного DuckDB, phase/base/registry, pyproject, uv.lock и девяти модулей/lock. Функция подготовки плана возвращает предложенные hashes; она не создаёт approval и не объявляет выходы принятыми.

Первый проход составляет точные v1 shards и производит независимые Q/Y, затем C. Полные manifests, reports, объявленные входы/код и физические выходы проверяются и сохраняются в cache seal. При отсутствии внешних shard approvals статус — `waiting_for_shard_review`; признаки не считаются ни для одной части. Координатор отдельно проверяет sampling/targets/retrieval по источнику и выдаёт строгие approvals принятого формата 004/007 с fingerprints фактических выходов. Это внутренняя проверка агентами, не запрос разрешения человеку.

Повторный проход сверяет прежние cache seals и внешние approvals, а затем вызывает неизменённый 005 producer. Feature manifest обязан содержать точные принятые Q/Y/C pins, registry и approval, report — правильные anchor/candidate ID; diagnostic subset запрещён. Hash, заново вычисленный после изменения файла, не заменяет прежний seal или независимую приёмку.

Внешний итог проверяет точный непрерывный набор shards/дней, counts по полным producer reports и фактическим Parquet, отсутствие дублированных query IDs/user-days/пар, зрелость и границы Q, отсутствие orphan/null пар, точное C↔F покрытие, неизменность всех восьми retrieval columns, user/anchor и физическую feature schema. Итоговый статус — `complete_produced_unreviewed`: численные spotchecks и отдельная collection acceptance ещё обязательны до обучения. Эти проверки целостности не доказывают сами по себе правильность каждой формулы.

Каждый запуск создаёт audit report до чтения источника, содержит stages/errors и расход времени, включая подготовку и проверку cache. Бюджет wall seconds суммируется между продолжениями; ожидание ревью между вызовами явно исключено. Monotonic deadline проверяется перед/после этапов, дочерние producers получают остаток; SQL финальной проверки прерывается таймером. RSS ceiling 8 GiB проверяется совместно с deadline, это cooperative guard, не лимит ОС. DuckDB memory request 2 GB и spill 2 GB не объявляются жёсткой границей полного RSS. Atomic state и exclusive runtime lock защищают от одновременных запусков; оставшийся после гибели процесса lock требует проверки частичного расчёта и стоимости, а не автоматического сброса. Неизменные child runs сохраняются, частично упавшие выходы не принимаются как полные.

Confirmation runtime пока отказывает до fingerprint/чтения source даже при валидной схеме lock: ещё нет проверяемых model artifacts и proof доступности selection decision. Final holdout этим модулем не исполняется.

Вторая итерация добавила одиннадцать integration checks с настоящими producers на маленьком синтетическом DuckDB: ожидание внешних approvals → resume → полный F → проверенный cache; отсутствие/неверный scope approval; изменённые source/code/config; tampered complete output; child timeout и partial cost; исчерпанный cumulative budget и crash lock; пропущенные/дублированные shards; закрытая confirmation до чтения source; восстановление после identified failure каждого из трёх producers с сохранением частичных артефактов. Вместе с девятью plan checks: 20 PASS. Во время разработки исправлены нормализация symlink пути macOS в fixture и ошибочное ожидание label_is_mature в F: maturity хранится и проверяется в Q, feature producer остаётся независимым от labels.

Для запуска после приёмки runtime: `.venv/bin/python -m scripts.development_collection --phase configs/development/train.json --producer-approval artifacts/acceptance/<producer>.json --shard-acceptance-dir artifacts/acceptance/development-shards`. Первое исполнение ожидаемо останавливается на внутреннем ревью Q/Y/C. Реальные counts, время и memory здесь пока не заявляются.

Независимое runtime review обнаружило блокировку resume после identified child failure: прежний immutable run занимал детерминированную папку, и следующий вызов отказывал FileExistsError. Исправлено общим invocation namespace для каждого нового anchor/candidate/feature вызова без seal. Путь попытки записывается в state до вызова; старые failed reports не переписываются. Три regression сценария вызывают настоящую ошибку после identified directory creation, снимают fault и достигают waiting/complete обычным resume; cumulative cost увеличивается. Новый фикс ожидает повторного независимого review.


## Runtime code acceptance и конкретный producer gate — 15 октября 2026

[Первый independent review](../backlog-reviews/tlab017-runtime-review.md) нашёл generic unsealed-child retry blocker. [Повторный review](../backlog-reviews/tlab017-runtime-rereview.md) принял исправление: fresh child invocation namespace для anchor/C/F, immutable failed/complete-but-unsealed artifacts сохранены, sealed cache не пересоздаётся. Independent faults до parent seal и обычный resume прошли Q4/Y2/C8/F8; B2 scoped20PASS2.116s, coordinator20PASS2.177s. Результат проверяет восстановление, не качество модели.

Coordinator отдельно сверил текущие source/code/config/new-lock pins и выдал14-pin producer approvals: train collection5fdc4dce…8b918 (5shards), selectionc2c6ba09…81b74 (1shard). Разрешён только bounded pass до waiting_for_shard_review. Actual Q/Y/C source reconstruction, затем F numeric spotchecks/complete collection acceptance ещё обязательны. Source DB совпал с предыдущим accepted SHA; старые acceptance pins не перезаписаны. Currentuv.lock4675021…85eab — новая lineage. Approvals/data artifacts ignored.

Confirmation runtime закрыт. Decision-compute gap после selection labels24Oct00 до firstconfirmation24Oct00 не обеспечен; до freeze требуется prospectively reviewed schedule change/actualdecision availability. Producer approval не разрешает confirmation и не выдаёт017done/008fit автоматически.


## Реальные collection outputs приняты — 15 октября 2026

[Полный source/formula/provenance audit](../backlog-reviews/tlab017-collection-verification.md): train26000Q/619Y/5317058C=F, selection4000Q/96Y/817149C=F. Все Q/Y/C реконструированы независимо;90sourcepairs×18core=1620numericchecks прошли.82/30-pin externalcollectionapprovals выданы, старыеpins сохранены. Production invocation wall99.363/19.768s, peakRSS2.52/1.97GiB, spill0; enginehighwater вышеrequested2GB, hardcapclaimнет. Confirmation закрыт;008code/fitpermit иtunedB/automation ещёотдельныеgates.
