# T-Lab RecSys 2026

Исследование для первой задачи отбора T-Lab: сильный бустинг с ручными признаками и эксперимент по автоматизации работы с признаками.

Датасет — **REES46 Multi-category**, октябрь 2019 года. Рабочий протокол: каждый день в 00:00 UTC ранжировать покупки следующих 24 часов для пользователей с наблюдаемой активностью за 48 часов. Кандидаты — до 200 популярных товаров по числу покупателей за 7 дней плюс 20 недавних товаров пользователя, без дополнения после пересечений. Все признаки используют историю строго раньше момента прогноза; метрики учитывают полный набор покупок, включая товары вне кандидатов.

Приняты train/selection данные и первые два CPU smoke-запуска: на 4000 selection-запросах conditional NDCG@20 составил 0.414448 для Logloss и 0.375197 для PairLogit; ориентир recent-source-first — 0.388390. [Результаты, ограничения и независимая проверка](docs/experiments/boosting-baselines.md). Это проверка исполнения, а не хорошо настроенный финальный контроль. Блок метаданных и цены прошёл независимую source-проверку, но [единственное сравнение снизило NDCG до 0.400414 и Recall до 0.545010](docs/backlog-reviews/tlab009-model-output-verification.md). По заранее принятому правилу блок отклонён; дальнейший контроль сохраняет исходные 41 вход. Ограниченный подбор ручного контроля (019) завершён: четыре заранее заданных fits и12 scoring checkpoints дали [проверенный development-контроль](docs/backlog-reviews/tlab019-strong-output-verification.md) с NDCG@20 **0.458611** и Recall@20 **0.585127**. Выбраны26000train queries, depth6, L2=30,300обученных деревьев и scoring prefix300. Четыре заранее выделенные ветви автоматизации (016) завершились: выбран R2 с NDCG@20 **0.464703** и Recall@20 **0.591977**. Это development-выбор; описательный интервал разности включает ноль, а случайная ветвь не доказывает превосходство осмысленного поиска. [Фактическая приёмка моделей](docs/backlog-reviews/tlab016-feature-program-model-verification.md). Неизменённая [отложенная проверка B/W завершена](docs/backlog-reviews/real015-heldout-results.md): final26–31 NDCG@20 B=0.459825, W=0.464947; разность+0.005122,95% интервал[−0.010433,+0.018561] включает ноль. Убедительное превосходство не установлено.

Текущие владельцы, проверки и бюджеты — в [backlog](docs/backlog.md). Весь месяц использован для EDA и проверки источника; confirmation/final query-level targets и метрики не использовались для выбора моделей. Решение заморожено до отложенной проверки; положительный доверительный интервал не получен.

## Публичный пример без исходных данных

После установки locked-окружения можно проверить ранжирование на 12 синтетических строках:

```bash
uv run --locked python -m scripts.replay_ranking_claim --package tests/fixtures/reproduction/manual18-small
```

[Рабочий отчёт](docs/progress-report.md) связывает исследования, результаты и ограничения. [Reproduction prefix](docs/experiments/fresh-clone-reproduction.md) отдельно описывает supplied-score replay; восстановление реальных коллекций и повторное обучение из чистого clone ещё не завершены. [Финальный экспериментальный отчёт](docs/experimental-report.md) принят; его исторический source ledger сохранён отдельным snapshot. Узкий [typed9 import kernel](docs/experiments/source-import.md) прошёл [независимый code review](docs/backlog-reviews/source-import-independent-rereview-v2.md) на tiny synthetic данных; [import owner v8](docs/backlog-reviews/source-import-owner-independent-rereview-v8.md) также CODE принят на53 author+11 targeted synthetic cases. Независимо приняты [фактический импорт четырёх синтетических строк в свежих процессах](docs/backlog-reviews/source-import-tiny-v5-output-verification.md) и [шестиролевая toy integration](docs/backlog-reviews/six-role-toy-v2-output-verification.md) с одной setup-моделью. Этот срез использует B=W и общее локальное окружение. [Полный typed9 source-prefix месяца принят](docs/backlog-reviews/full-source018-source-prefix-acceptance.md) после завершения исходной операции и независимой проверки байтов и метаданных; задача018 ещё выполняется. [Код однодневного повтора и условная оценка времени](docs/backlog-reviews/development-v2-and-conditional-wall-acceptance.md) приняты в узких scopes; [Исходный600CPU/900wall replay](docs/backlog-reviews/development-whole018-launch.md) завершился ошибкой до предсказаний; partialoutputs не приняты, [Причина локализована диагностикой](docs/backlog-reviews/native-param-diagnosis-and-cost.md), [точное V2 исправление и постоянные регрессионные тесты установлены](docs/backlog-reviews/native-param-v2-code-installation.md) после 8 проверок на отдельной копии; [фактическая проверка метаданных обеих сохранённых B/W-моделей принята](docs/backlog-reviews/native-bw-v2-validation.md), без предсказаний, обучения или целевых данных. [Oct22 source-to-fixed-scores slice принят](docs/backlog-reviews/018-accepted-oct22-slice.md), но полный публичный raw→freshcollections→frozenB/W training→comparison путь и воспроизведение из чистого clone ещё не завершены; [оригинальный real015 outer/controller остановился до ownerclaim](docs/backlog-reviews/real015-original-startup-failure.md) на проверке окружения; исходный OUT consumed. Последующая [узкая V4 проверка окружения принята](docs/backlog-reviews/real015-v4-environment-green.md), после отдельного Root решения [ограниченный FIRST-owner recovery отправлен](docs/backlog-reviews/real015-first-owner-recovery-launch.md), полные результаты и lifetime приняты отдельной Root receipt. Все7 дней предсказаний сверены и запечатаны до target gate; TLAB-015 done, complete018 остаётся; [финальный отчёт принят после независимого review](docs/backlog-reviews/experimental-report-heldout-v2.md).

## Воспроизведение EDA

Нужны Python 3.12, [uv](https://docs.astral.sh/uv/) и исходный архив в `data/raw/2019-Oct.csv.gz`. Источник, проверенные размеры, контрольная сумма и восстановление файла — в [docs/data.md](docs/data.md).

Из корня репозитория:

```bash
uv sync --locked
uv run python scripts/eda.py --input data/raw/2019-Oct.csv.gz --output artifacts/eda-october --db data/processed/october.duckdb
```

Скрипт читает архив непосредственно: предварительная распаковка в CSV не требуется. Исходный файл остаётся неизменным. Локальная DuckDB и результаты расчёта исключены из Git. Открыть [notebooks/01_eda.ipynb](notebooks/01_eda.ipynb) можно в Jupyter-совместимом редакторе с окружением `.venv`; notebook предназначен для просмотра агрегатов, графиков и интерпретации EDA.

Для первого запуска используем Mac с 36 ГБ RAM. Будущие серии обучения можно перенести на Windows-ПК с 32 ГБ RAM и RTX 3070 после замера времени; GPU для этого EDA не нужен. Размер архива не равен объёму оперативной памяти, необходимому анализу: запросы используют промежуточные данные на диске.

## Структура

```text
docs/data.md               источник, схема и ограничения данных
docs/experiment-plan.md    вопросы EDA и последующие точки решения
scripts/eda.py             воспроизводимый расчёт статистик
notebooks/01_eda.ipynb     графики и выводы по агрегатам
data/raw/                 локальные неизменяемые исходные файлы, ignored
data/processed/           локальная производная DuckDB, ignored
artifacts/                локальные агрегаты и графики, ignored
pyproject.toml, uv.lock    зафиксированное окружение
```

Проверка внешних названий категорий и ограничения найденного словаря — в [docs/category-recovery.md](docs/category-recovery.md). Исследование моделей: [текстовые эмбеддинги](docs/text-embeddings.md), [визуальные эмбеддинги](docs/image-embeddings.md). Эти embedding-ветви пока не обучались; принятые boosting smoke-модели описаны выше.

NLP: [план сравнений](docs/nlp-experiments.md), [BM25 и TF–IDF](docs/nlp-bm25.md), [токенизация категорий и брендов](docs/nlp-tokenization.md).

Исследования событийных признаков: [16 независимых записок, ревью и план отбора](docs/features/index.md).

Цель модели и протокол: [8 независимых исследований purchase ranking, два ревью и матрица решений](docs/target-research/index.md).

Исполняемая очередь: [единый backlog, владельцы, проверки и бюджеты](docs/backlog.md).

Поведенческие эмбеддинги: [ARGUS и общая идея](docs/argus.md), [компактные модели истории](docs/sequential-embeddings.md), [протокол сравнения с бустингом](docs/embedding-experiments.md).

## Границы исследования

Одна строка датасета — наблюдаемое действие, а не показ товара в рекомендательной выдаче. Отсутствие покупки нельзя автоматически считать отрицательным показом. История ограничена одним месяцем; отсутствие более ранних событий не доказывает, что пользователь новый.

В Git сохраняем код, notebook с агрегированными выводами, протокол и зависимости. Исходные события, отдельные пользовательские истории, идентификаторы пользователей и сессий в выводах, модели, локальные пути и секреты не публикуем. Данные восстанавливаются из авторского источника; репозиторий их не распространяет.

Рабочая постановка и следующие решения описаны в [плане экспериментов](docs/experiment-plan.md); окончательный protocol/model lock ещё не принят. Контекст выбора курсовой и личные заметки остаются отдельно от этого репозитория.


Исходный исследовательский портфель завершён: 58 независимых записок и 13 групповых ревью. Разделы: [user × item](docs/features/09-user-item/index.md), [candidate generation](docs/candidate-generation/index.md), [model selection](docs/model-selection/index.md), [loss selection](docs/loss-selection/index.md). В каждом index сохранены выводы, источники и расхождения.

Постоянная линия новых гипотез и первоисточников: [research lab и независимая критика](docs/research-lab/index.md).

Воспроизведение pipeline: [development collections](docs/experiments/development-collection.md), [CPU окружение](docs/experiments/cpu-environment.md), [manual18](docs/experiments/manual-features.md), [smoke training](docs/experiments/boosting-baselines.md). Первая версия [переносимой source-verification CLI (018)](docs/experiments/verification-workflow.md) принята на независимых synthetic fault checks для существующих sealed manual18 collections; полное восстановление и выдача новых approvals ещё не реализованы. Ignored данные/модели/approval-файлы не входят в clone, и новые hashes сами по себе не заменяют независимую проверку.

Текущий читаемый результат — [рабочий технический отчёт](docs/progress-report.md): ручной контроль 019 и четыре сравнения 016 приняты. На выборке подбора победил R2: ΔNDCG≈0.006092, описательный интервал включает 0. Отложенная проверка 25–31 октября ещё не выполнялась; полное воспроизведение от исходных данных из чистого clone пока не показано.


Автоматизация: [генератор программ признаков](docs/experiments/feature-programs.md) создаёт определения по человечески заданной схеме и шаблонам. Значения дополнительных признаков и четыре сопоставимые модели 016 независимо проверены; это не доказывает выигрыш на отложенной выборке или превосходство стратегии с ручными приоритетами. [Исполненный пример генерации без данных](docs/experiments/automation-walkthrough.md) показывает два блока и автоматически добавленную маску пропуска.
