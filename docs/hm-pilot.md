# H&M: протокол и результаты исследования

Дата начала: 18 октября 2026. Пользователь выбрал H&M как второй датасет для первой задачи T-Lab. REES46 и его исторические результаты сохранены отдельно. Ветка: `codex/hm-pilot`.

## Итог кампании — 2026-10-18T13:16:15.309456+00:00

Конечный H&M эксперимент завершён. На отложенной неделе16–22 сентября средний AP двух model seeds2026/2027 дал MAP@12 **M0.03442893 / selected0.03265247**. Δ selected−M **−0.00177647**, paired95% CI **[−0.00375881; +0.00007831]**. Выигрыш не установлен; интервал включает0, поэтому значимое ухудшение тоже не установлено. Точечный знак отрицателен на двух final seeds и двух development-срезах; это не доказательство универсальной бесполезности генератора или причин неудачи.

[Читаемый итоговый отчёт](hm-report.md) содержит метод, результаты, ограничения и сравнение с первичными чужими решениями. [Воспроизведение](hm-reproduce.md), [определения выбранных программ](hm-generated-programs.md), [очередь](backlog.md). Ниже сохранена история протокола и проверок.

Генератор60 программ→exactM-dedup58, all81, training-only PVC12, selected/random35; M23 выбран из конечной шестерки GPU-рецептов. Selection и диагностическая confirmation не показали выигрыша selector. Параметры выбраны для M и перенесены на расширенные модели без отдельного tuning. Final decision lockd47df2ac проверен/commit78a4d3d до final collection; sourcec46912d/config63db1ea3 оставались побайтно неизменными.

Все четыре final fits GPU500d8 завершены, source/metrics auditPASS и независимый saved-top12/fullY AP/Recall/three-CI replay≤1e-12. Q20000/Q+1905/Y5962; native omitted candidate scores заново не пересчитывались. 128 тестов H&M PASS; свежий clone/full repeat пока не проверен. Raw/DB/CBM/построчные outputs — необязательные локальные дополнения; необходимые определения/команды/выводы находятся в tracked материалах.

Тяжёлых процессов и pending receipts нет, новых моделей/волн не запланировано. Остановка обусловлена завершением конечного исследования, не достижением положительного результата. Изменения локальны, push/submission не выполнялись.

## Вопрос

Достаточно ли здесь историй и будущих покупок для устойчивого сравнения ручных и автоматически созданных признаков? Первый запуск проверяет данные и небольшой ручной CatBoost; он ещё не оценивает автоматизацию и не воспроизводит результат участника Kaggle.

## Источник

Оригинал — [H&M Personalized Fashion Recommendations](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations). [Правила, §7A](https://www.kaggle.com/c/h-and-m-personalized-fashion-recommendations/rules) разрешают некоммерческое исследование и обучение. Исходные таблицы хранятся только локально в ignored `data/raw/hm/`; данные и модели не перераспространяются. Это исследовательское использование, без регистрации в конкурсе или отправки submission.

Транспорт — [зеркало Microsoft](https://huggingface.co/datasets/microsoft/hnm-search-data), revision `ac68fe6c5372c7f0bbfe0b7a6510f9e17addc81f`. Используются только исходные `articles.csv`, `customers.csv`, `transactions_train.csv`. Синтетические `data/search/queries.csv` и `qrels.csv`, изображения и чужие processed-таблицы не используются. CDLA поисковых дополнений не заменяет условий исходных таблиц.

Размеры и LFS SHA256 зафиксированы в [source config](../configs/datasets/hm-source.json). Downloader проверяет каждый байт относительно этого зеркала; независимое побайтное равенство оригиналу Kaggle не проверено. Локальный `download.json` содержит фактическое завершение и hashes. Объявленные 31 788 324 покупки, 105 542 товара и 1 371 980 клиентов должны быть проверены по загруженным CSV, а не приняты на веру.

## Заранее заданный development-протокол

- На начало суток cutoff предсказываются **различные товары** в покупках `[cutoff, cutoff+7 дней)`. История и все признаки строго `t_dat < cutoff`. Внутри суток порядка событий нет.
- Train anchors: 2020-08-12, 08-19, 08-26, 09-02. Development: 2020-09-09…09-15. Период 09-16…09-22 зарезервирован для последующего final, сейчас не оценивается моделями. EDA может сообщать агрегированную пригодность календарных периодов; это не полностью невидимые данные.
- Eligibility — минимум одна покупка за 90 дней до cutoff. Пользователи детерминированно отбираются по ID, без знания будущих покупок. Начальный предел: 5000 train users на anchor, 20000 development users. Глобальные исторические агрегаты считаются по полной истории, а не только выбранным пользователям.
- C0: до 100 популярных товаров по числу различных покупателей за 7 дней плюс до 20 недавних различных покупок пользователя за 90 дней. Пересечения удаляются без дозаполнения. Повторные покупки разрешены; положительные товары из будущего в кандидаты не вставляются.
- MAP@12 и Recall@12 — query-macro по пользователям с непустым полным Y. Все будущие товары остаются в знаменателях, даже отсутствующие в C. Дополнительно сообщаются все запросы/positive queries, all-query-zero метрики, покрытие C и oracle-потолок AP. Холодные будущие покупатели и выбранная eligible-аудитория различаются.
- Один CatBoostClassifier: 150 деревьев, depth 6, learning_rate 0.05, l2_leaf_reg 10, seed 2026, CPU, 2 threads, Logloss; вес строки 1/|Cq|. Нет eval_set, early stopping, сетки или выбора префикса. Это **первый baseline**, не хорошо настроенный финальный контроль.
- Сравнение с фиксированными popularity и recency на той же development-популяции. После этого отдельно планируется сравнение manual/automatic, seeds и оценка неопределённости. Этот пилот не доказывает выигрыш автопризнаков.

## Границы признаков

Числа покупок и охватов, давности, исторические affinities user×тип товара; глобальные и парные окна используют только прошлое. Историческая цена, если используется, берётся из прошлых транзакций. `article_id` и `customer_id` остаются строковыми ключами; leading zeros сохраняются. Одинаковые строки транзакций не удаляются без основания: возможны покупки нескольких одинаковых единиц; labels всё равно состоят из различных товаров.

Семантические атрибуты articles (тип, цвет, отдел) рассматриваются как статические — это допущение, исторические версии каталога не опубликованы. Наличие в полном каталоге не доказывает историческую доступность товара. Клиентские snapshots `Active`, `FN`, membership/news и прочие текущие свойства не допускаются в модель. `sales_channel_id` остаётся исходным кодом без непроверенной расшифровки.

Отсутствуют показы и истинные отрицательные предпочтения: непокупка кандидата — отсутствие наблюдаемой покупки в горизонте, не дизлайк. Пользовательская подвыборка, собственный cutoff и кандидатный список отличаются от официального конкурса; локальный MAP нельзя напрямую сравнивать с leaderboard.

## Локальное окружение Windows

Отдельная `.venv` на Python 3.12.14; зависимости пилота фиксируются в `configs/datasets/hm-requirements.txt`. Это отдельная pip-сборка для Windows, не проверенное воспроизведение исторического REES46 `uv.lock`. Исходные raw CSV, DuckDB, scores, модели и подробные артефакты остаются в ignored `data/` и `artifacts/`.

Загрузка выполняется `scripts/hm_download.py --config configs/datasets/hm-source.json --output data/raw/hm`. Все входы проверяются до анализа; существующие отличающиеся исходники не перезаписываются. Окончательные команды, измерения и результаты добавляются после фактической проверки.

## Фактический результат первого запуска

18 октября 2026 загрузка всех трёх CSV завершилась с совпавшими размерами и SHA256. Полный EDA и единственный production fit пилота завершились exit 0.

Проверены 31,788,324 строк покупок, 105,542 товаров и 1,371,980 клиентов. Даты: 2018-09-20…2020-09-22. Ключи metadata уникальны, FK полны, отсутствующих дат и некорректных цен не найдено. Во всех 734 календарных днях есть покупки. Дополнительные 2,974,905 полностью одинаковые строки сохранены: они могут отражать одинаковые единицы покупки, а не ошибки загрузки.

Среди пользователей с покупками за весь период приблизительная медиана — 9 строк покупок, 8 различных товаров и 3 различных покупочных дня. Это не распределение активной pilot-когорты и не доказательство даты регистрации.

На 2020-09-09 до среза активны за 90 дней 537556 пользователей; 53384 из них покупают в следующие 7 дней (9.93%). В детерминированном validation sample 20,000 пользователей, из них 1,957 с покупками, 6,197 distinct user–article целей и 2,122,158 candidate rows. Обучение: 4×5000 запросов, 2124784 candidate rows, 734 положительных candidate rows; полный Y сохранён.

| Scorer, та же validation 09–15 сентября | Conditional MAP@12 | Conditional Recall@12 |
|---|---:|---:|
| Popularity | 0.00562780 | 0.02024742 |
| Recent purchases first | 0.02980929 | 0.05683748 |
| Manual CatBoost, 23 входа / 150 деревьев | 0.03064532 | 0.05817829 |

Точечная разница CatBoost−recency по MAP: 0.00083603, или 2.80% относительно recency. Описательный парный bootstrap по 1957 положительным validation-пользователям, 1000 повторов, seed 2026: 95% CI разницы [-0.00194130; 0.00374029], включает ноль. Уверенного превосходства над recency не показано. Интервал условен на фиксированные модель и неделю; вариацию обучения и времени он не учитывает. Это не tuned baseline и ещё не сравнение автоматических признаков.

C0 содержит 798/6197 целевых пар (12.88%); хотя бы одна цель найдена для 29.48% положительных запросов. Oracle MAP@12 для идеального порядка тех же C равен 0.14286232: это недостижимое знание будущих целей, не обещание качества обычного алгоритма. All-query-zero MAP CatBoost: 0.00299864; основная таблица исключает пустые Y, а не нулевые попадания.

Полный EDA занял 71.719 с внешнего wall; baseline — 221.984 с внешнего wall, включая подготовку, один fit и development-оценку. Это измерения на данной Windows-машине и этой sample, без обещания времени на другом оборудовании или полном населении.

Проверены 19 synthetic/unit tests и два независимых статических ревью. Отдельная независимая проверка загрузила сохранённую модель, построила ту же validation collection и пересчитала порядок, MAP, Recall, coverage и oracle другим кодом без обучения: максимальное расхождение 5.55e−17. Она переиспользует production collection builder, поэтому не является независимым source/formula oracle всех признаков.

Полные локальные агрегаты доступны в `artifacts/hm-eda-20261018/{summary.json,report.md}` и `artifacts/hm-baseline-20261018/{report.json,report.md}`; модель — `manual.cbm` рядом. Проверка метрик — `artifacts/hm-independent-metrics-20261018/audit.json` и `audit-bootstrap.json` рядом. Эти ignored файлы являются необязательными локальными дополнениями, недоступными в чистом clone; необходимые выводы и настройки приведены здесь. После клонирования источники восстанавливаются по source config, а результаты — CLI ниже.

## Воспроизведение нового пилота

После создания отдельного Python 3.12 окружения установите зафиксированные версии из `configs/datasets/hm-requirements.txt`. Ниже указаны аргументы проектного Python; каждый output должен отсутствовать. На текущей машине Python запускался через PersonalOS `pas.ps1` с отдельным project-venv subprocess, внешними timeout 1800 с для EDA и 1860 с для baseline.

```text
-m scripts.hm_download --config configs/datasets/hm-source.json --output data/raw/hm
-m scripts.hm_eda --raw-dir data/raw/hm --output artifacts/hm-eda-NEW
-m scripts.hm_baseline --database artifacts/hm-eda-NEW/audit.duckdb --output artifacts/hm-baseline-NEW --wall-seconds 1800
```

После первой оценки ближайший вопрос — улучшение покрытия кандидатов на development при сохранённом полном Y. Затем нужен более сильный ручной контроль и сопоставимое сравнение с автоматизацией. Сохранённый final 09-16…09-22 моделями не оценивался; EDA видел его общие счётчики.

## Контракт кампании H&M — 18 октября 2026

Статус: active; среда — текущий чат, координатор `/root` (`01a14e18-1e33-7d73-8f71-59f7a6194adb`). Запись контракта: 2026-10-18T09:35:05.493126+00:00, 12:35:05 МСК. Пользователь явно вызвал `research-campaign` и на вопрос о пределе ответил «нет пределп»: общего ограничения времени/раундов не задано. Остановка — достижение критериев ниже, явный stop пользователя либо невозможность полезного разрешённого шага после meta-review. Отдельный goal не запрашивался и не создавался; проверка текущего goal вернула null. Продолжение зависит от активного чата, расписание этой кампании не создаётся.

**Исходная цель:** получить содержательный воспроизводимый эксперимент первой задачи T-Lab на H&M: сильный ручной boosting-контроль, автоматическая генерация/отбор признаков и честное сравнение на общем протоколе. Проверенный отрицательный или inconclusive результат допустим; положительный gain не является обязательным обещанием.

**Критерии завершения:** (1) данные/временной протокол и source assumptions проверены; (2) retrieval и обучающая поддержка диагностированы, один C и training policy закреплены; (3) ручной контроль настроен в заранее описанном конечном поиске и сопоставлен с сильными простыми альтернативами; (4) исполняемый H&M generator действительно порождает определения из schema/templates, прошёл scalar/temporal тесты, сравнен с M на одинаковых Q/C/Y и условиях обучения; (5) выбранные варианты и процедура полностью заморожены до единственной отложенной оценки, неопределённость и seeds/временные ограничения раскрыты; (6) итоговый отчёт и воспроизведение проверены независимым агентом. Это критерии полезного исследования, не гарантия принятия в T-Lab или универсального SOTA.

**Первый полезный срез уже выполнен:** source+EDA+fixed150 pilot, 19 тестов, два code reviews и independent saved-model metrics/bootstrap. Последующие шаги фиксируются в существующем `docs/backlog.md` с ID HM-xxx; старые REES46 TLAB/HYP записи остаются историческими.

**Разрешённые действия и пути:** локальные H&M код/конфигурации/tests/docs этого repo и ignored `data/raw/hm/`, `artifacts/hm-*`; чтение первичных источников; local CPU fits и независимые проверки. Владелец raw/DB, общего backlog/journal и тяжёлых операций — root. Существующие исходники/результаты пилота сохраняются как исходный контроль; новые опыты получают новые output paths. Клиентские snapshots исключены; articles metadata имеет явное static assumption. Внешние записи, push/PR/submission, платные APIs и новые datasets не входят в этот запуск. Старый REES46 nightly contract не даёт новых полномочий.

**Исполнение и разведка:** до 2 исполнимых задач и 1 разведочной в WIP, до 6 READY; исследовательские авторы 2 и отдельный скептик, с сохранением независимых первых предложений. Тяжёлые SQL/fits — только1 процесс за раз. Действующее post-manual переопределение: runner SQL/train/predict4 потока, SQL memory_limit2GB/spill8GB; независимый audit/PVC selector2 потока. Целевой process RSS до8GiB без hard containment; внутренний automatic PVC CatBoost.fit использует default−1, поэтому жёсткого ограничения суммарного CPU нет. Известный pilot wall 221.984 с и observed RSS около 2.5 GiB — измерения одного прошлого запуска, не прогноз любого опыта; общий исторический CPU/token расход не измерен и не считается нулём.

**Стоимость и остановка операций:** общий расход/раунды сверху не ограничены пользователем. Каждый дорогой шаг получает конечный predeclared fit count, memory/disk preflight и отдельный timeout до отправки. Обычный fit-пилот начинается с cooperative wall 1800 с плюс внешнего subprocess timeout 1860 с; более дорогой шаг сначала оценивается и получает свой конечный envelope. В бюджете шага оставлять около 25% на verification/checkpoint; резерв — плановый, а не измеренное ускорение. После failed checker зависимые действия остановлены; unknown операция сначала сверяется с output/process/session, а не повторяется.

**Волны:** начальная HM-W001 и последующие после двух принятых экспериментальных раундов или через45 минут от последней принятой synthesis, что раньше. Root записывает конкретный UTC/MSK next_due при принятии волны. После двух раундов без нового доказательства — один meta-review, смена подхода в исходной цели либо остановка при отсутствии полезного шага.

**Состояние и роли:** `docs/backlog.md` — единственная исполнимая очередь; `docs/research-lab/brainstorm-log.md` — журнал волн/checkpoints; `docs/research-lab/hm-wave001.md` — исходные предложения и критика, не очередь; этот документ — протокол и evidence report; `docs/progress-report.md` — актуальный обзор. Mapping H&M: candidate→ready→running→review→done (accepted); rejected/inconclusive/deferred сохраняют свой смысл. Root единолично меняет общие документы.

**Receipts и восстановление:** новые тяжёлые операции получают op ID и запись в ignored `artifacts/hm-campaign/operations/` до запуска: prepared→submitted→succeeded/failed/unknown, owner/input/code IDs, стоимость, output и способ проверки. Исполнимое текущее состояние и pending IDs дублируются кратко в canonical journal, без private payload. Перед возобновлением сверить branch/dirty files, source hashes, фактические процессы, выходные статусы и владельцев; timestamp сам по себе не освобождает ресурс. На другой машине CSV/DB/CBM из ignored paths недоступны без восстановления; source config/requirements и нужные выводы доступны в repo.

### Checkpoint HM-R000

- Время: 2026-10-18T09:35:05.493126+00:00; active, кампания исполнения принята, текущая операция — начальная разведочная волна.
- Доказательства: исходный pilot и независимый аудит сохранены; CatBoost MAP .03064532 vs recency .02980929, CI разницы [−.00194130;+.00374029]; C coverage798/6197, oracleMAP .14286232; 734 training positive candidate rows. Это не доказательство доминирования retrieval: внутри C тоже есть запас.
- Владение: root владеет состоянием/DB/compute; проверка процессов hm_download/hm_eda/hm_baseline не показала действующих workers. Два read-only автора HM-W001 работают по независимым углам; production operations pending: none.
- Не закрыты: сильный M, H&M generator, fair comparison, final/report. Следующий разрешённый шаг — критика двух предложений и один predeclared development-only диагностический тест.

### Checkpoint HM-R000b — 2026-10-18T09:38:51.446582+00:00

HM-W001 synthesis accepted after two independentauthors and separatecritic; contract reviewed without findings. HM-003 no-fit Sep02 card frozen in [wave evidence](research-lab/hm-wave001.md), not yet run. Root owner/productionpending none. Newretrieval+featureengine code preparation disjoint; pilot unchanged. HM004merged,A01/A02retained; next_due 2026-10-18T10:23:51.446582+00:00 / 2026-10-18T13:23:51.446582+03:00 or2accepted empiricalrounds. Previous HM-R000 records earlierstate, not current workers.

### Подготовленный движок кампании (ещё не результат обучения)

`configs/datasets/hm-campaign.json` заранее фиксирует temporal selection/confirmation, конечную grid ручного контроля, sampler, generated pool/selector и random controls. `scripts/hm_feature_engine.py` строит registry без соединения с данными:5semantic dimensions×3windows(7/28/90)×4operations(count/share/recency/distinct_items)=60программ;7семантических aliases ручным формулам исключены. Итог87входов:23pilot,11manual additions,53generated. Например user×department share28 — число строк покупок того же отдела до cutoff за28дней, делённое на все строки покупок пользователя в том же окне; zero denominator→0. SQL compiler допускает только перечисленные роли/шаблоны и не получает labels. Это автоматическая генерация определений и расчёта; качество этих определений пока не измерено.

Сильный manual набор содержит нормированные type/colour/department affinities, department count, user-item repeatshare28, item demand7/28 ratio, historical price compatibility+missing/valid masks и type recency90. Shares/ratios существующих counts меняют представление, не обязательно добавляют новую информацию. Генератор дедуплицирован против этого полного ручного набора.

Независимое review feature engine:12synthetic tests, дополнительное сопоставление201candidate pairs с pilot — точное совпадение18numeric после исходногоfloat32 и5categorical. Scalar oracle отдельным Python-кодом проверяет87fields, missing, повторы, окна/границы и outside-cohort item aggregates. Это подтверждает небольшие проверенные сценарии, не production cost. `scripts/hm_experiment.py` связывает history-only retrieval/features, ignored hashed parquet collection, fullY и один фиксированный CatBoost fit;11synthetic tests и2независимых reviews без findings. Первый запуск frozen tests на C: корректно остановил2collectcases из-за<10GiB free; неизменённый snapshot на D: прошёл11/11.

### Внешний ориентир H&M

[Авторы45-го места из3006](https://github.com/Wp-Zhang/H-M-Fashion-RecSys) сообщают LB0.0292 и PB0.02996; одиночная retrieval strategy достигала0.0286, ensemble двух стратегий —0.0292. Они использовали4training weeks, в среднем50candidates/user и LightGBM ranker/classifier+DNN. Проверено по README первичного репозитория18октября2026. Это внешний ориентир архитектуры и затрат (авторы указывают50GBRAM), а не сопоставимый benchmark: наши даты, подвыборка historyeligible Q и candidate policy отличаются от Kaggle. Conditioning на futurepurchase само по себе соответствует официальному scoring rule, проверенному ниже. Совпадение численного масштаба с local conditional MAP не означает равное качество.

## HM-R001: retrieval diagnostic принят — 2026-10-18T09:53:35.840066+00:00

Sep02 historyeligible20000Q,2111positive queries,6654fullY targetpairs (6416new90,238repeat90), одинаковыеQ/Y во всех policies.

| Policy | Mean candidates | Micro target coverage | New90 coverage | Oracle MAP12 |
|---|---:|---:|---:|---:|
| HistoricalC0 |106.1709|.13510670|.10520574|.15888724|
| C0-Q120 |120|.14232041|.11268703|.16705158|
| C1-Q120 |120|.14006613|.11034913|.16124914|

PrimaryC1−C0-Q120 oracleΔ −.00580244, descriptive userbootstrap95%CI[−.01442813;+.00198348],2000draws seed2026. New90 pointcoverage тоже ниже; preregistered coveragegate не пройден. **C1 отклонён, C0-Q120 закреплён** для дальнейшего manual/generated experiment. Новые квоты на этой неделе не подбираются; два policyfits не допущены. Это отрицательный результат конкретной personalexpansion, не доказательство бесполезности всех персональных retrieval. Идентичное repeat90 coverage.94117647. HistoricalC0 secondary имеет меньшую длину, поэтому прирост C0-Q120 относительно него нельзя приписать иной персонализации.

ProductionHMOP002:49.594s externalwall, largestprocesspeak4,819,017,728B поWindowsJob (не aggregateconcurrentRSS/hardcap). IndependentHMOP003:22.312s, largestprocesspeak3,348,357,120B;91checksPASS, tolerance1e−12, source-rebuiltQ/fullY/repeat90, allperuser/aggregatemetrics+bootstrap, artifact/Q/C identities. Полное personalized ordering independently проверено наsyntheticoracle, не реконструировано изraw в audit. Локальные ignored artifacts: hm-retrieval-20261018-v4/report.json и hm-retrieval-independent-20261018/result/report.json. Протокол и необходимые выводы доступны здесь безэтих optionalprivatefiles.

ПредыдущийHMOP001 остановленrootчерез384.469s безqualityresults: EXPLAIN выявил2BLOCKWISE_NL_JOIN вfinalprovenance attachment. Эквивалентные equalityjoins переведенывHASH_JOIN;11tests иindependent680row allcolumn equalityPASS. Failedoutput сохранён, повторновыйoutputV4; sourcehashcode c0d174115592e32d95df31dd1b0e7369c884d80dc3456bfc30a2650a1d36a774. Launcher теперьиспользуетWindowsJobownership, atomicadmissionreceipt/exclusiveID; helper optionalmachine-local и не требуетсядляcanonicalCLI.

СледующийраундHM004:3fixed150d6 pilotfits наC0-Q120, trainAug12/Aug19/Aug26→Sep02fullC:5000all,5000sample20neg,20000sample20neg; highestSep02MAP thenfewerfitrows/armorder. Всеpositives/everyQ retained, inclusionweightsdeclared; no equivalenceclaim. Сначала4collections по20kusers с87label-freefeatures,3train+Sep02evaluation. Кодrunner review пройден,11fixturetests; DuckDBcapснижен2GB (4literalreplacements independentlyreviewed) из-за~6GiBavailableRAM; общийprocessRSSнеограничен, estimatedpandasallocationsseparate. Percollection1800/1860s,2threads,8GBspill,>=10GiBdisk; fits0duringcollection. После каждогошага rootпроверяетmanifest/receipt передследующим.

Checkpoint: active/rootowner, acceptedempiricalrounds1afterHM-W001; pendingnone atacceptance, nextdue10:23:51UTC/13:23:51MSK OR onefurtheracceptedround. Finaluntouched; no campaignmodelfitsyet.

### Уточнение официальной метрики/duplicates по первичному источнику

[Официальный Kaggle overview](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations) прямо исключает изscoring клиентов безпокупок вtestperiod; нашconditionalMAP согласован сэтим правилом, all-query-empty-zero остаётсядополнительнойметрикой. Отличиепопуляции сохраняется: Kaggle оценивает всех testbuyers вне зависимости отналичия history, мы — history90dactive sample20k наинойнеделе. Поэтому сходныечисла нельзяназывать прямымmedal/SOTAbenchmark. [Официальный data description](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/data) объясняетduplicate rows какmultiplepurchases того жеitem; сохранениеих висторическихcounts имеет прямоеоснование. Targetsпо-прежнему distinctarticles понашейявнойформулировке. Проверено18октября2026; syntheticmirrorsearch неиспользуется.

Дополнительныйпервичныйориентир: [автор142-гоместа](https://github.com/mike-chesnokov/kaggle_hm_recs_2022) сообщает publicMAP.02530/privateMAP.02554; его простаякомбинацияистории/frequentpairs/cold-start имелаpublic.02359, отдельныеkNN→LightGBMварианты≈.0242–.0243. Числаавторские, официальное местоотдельнонепересчитано; длянашейдругойнедели/active90cohort этонеbenchmark.

## HM-R002: training support принят — 2026-10-18T10:11:03.246994+00:00

FixedC0-Q120, trainAug12/Aug19/Aug26→selectionSep02.5000historyhash users являютсяnestedsubset20000; negativesampler2026/CBseed2026. Fullvalidation20kQ/2111Q+/6654Y/947coveredY неизменен.

| Arm | Train positive rows | Fit rows3anchors | MAP12 | Externalwall |
|---|---:|---:|---:|---:|
| A5000/allC |548|1,800,000|.03070694|178.500s|
| B5000/sample20negative |548|300,548|.03094879|78.922s|
| C20000/sample20negative |2434|1,202,434|.03389372|206.047s|
| Recency sameQ/C/Y |—|0|.02910562|no fit|
| Popularity sameQ/C/Y |—|0|.00843813|no fit|

B−A MAPΔ+.00024185,95%descriptiveCI[−.00220246;+.00275471]: equivalence не показана. C−A+.00318678CI[+.00038952;+.00607766]; C−B+.00294493CI[+.00071009;+.00523355]. C−recency+.00478810CI[+.00202140;+.00744776],+16.45%pointrelative. Bootstrap2000positiveusers seed2026, conditionalonfixedmodels/singleweek; неучитываетselectionmultiplicity/training/timevariation. Это development evidence пользы большегоtrainingcohort при данномsampler, не универсальныйпричинныйзакон оpositives.

**Закреплёнtrainingpolicy C:20000users/anchor, allnaturallyretrievedpositives +20deterministicnegative/Q, inverseπweights/originalC120, everyQinclfutureempty.** Выбор highestSep02pointMAP поpredeclaredrule. Samplemass perQ=1 поформуле; features/validation общие. Качествонаfinal ещёнеизвестно.

HMOP011 independent auditPASS15.922sexternal, tolerance1e−12: source-rebuiltQ/fullY, cachedkeys/counts/labels/weights/digests, allsavedtop12/perquery/aggregate metrics, independentcontrols andpairedbootstrap. Limitation:nativeall-candidate model scores не пересчитывались, порядок проверен внутриsavedtop12; featureformulas провереныотдельноsynthetics/pilotparity. SupplementalCvsB computedfrom independentlyrecomputed/hashedperqueryexports. Artifacts optionalprivate: artifacts/hm-campaign/audits/support/report.json,c-vs-b.json; fit/cachepaths содержатсявreceipts. Historicalmodelwrapper3d27... заменёнтолькоexplicitpredictionthread2 (99cb...4fb) послетрёхfits; все6manualgridrecipes будутобученызановона99, old150неreusedиз-заdifferentfitidentity.

СледующийHM005:6eligiblemanualrecipes pilot23/strong34 ×150d6/500d6/500d8, fixedlr.05/L2=10, trainingpolicyC, seed2026, sameSep02fullC/Y, noeval_set/earlystop. ВыборhighestMAP tie fewerfeatures→trees→depth→name. Perfit1800cooperative/1860externaltree,SQL2GB/spill8GB/2threads,oneheavyprocess,desiredprocessmemory8GiBwithoutRSScontainment. Past150fit206s не означаетлинейныйпрогноз500/depth8; eachnextstep checksactualreceipt/manifest. 6fitsfinite, thenindependentmetricreview; negative/inconclusivevalid. HM006 selectorreadybdbdc788/17tests+2reviews, no generatedfit yet.

AcceptedempiricalroundsafterHM-W001=2; HM-W002 triggerednow(twoindependentFIRSTauthors), separatecriticafterboth. Coordinatorroot; pendingnonebeforemanualgridlaunch. Goalremainsactive/nooveralllimit, finalSep16untouched.

### Техническое восстановление HM005 и границы стоимости

OP019 completed751.234s/peak4556374016B/500trees, MAP.03197486442/Recall.06538850. Полныйfit_identityf84cebef совпадает сOP014; observerтолькоprogress/traceback, noRNG/params/datachanges. Независимыйread-onlyreview rawreports/source/receipt подтвердилidentity и допустимость первогоcompleteкакисходногоrecipeпослеmetric audit. OP014nativecauseunknown, успешныйповторнеобъявляетсядоказаннымисправлением. OP018отдельноеtoolinterruptionбезрезультата, процессыпроверены/pendingresolved. Mневыбран, HM005неaccepted.

Rootsubmittedremainingfinitebatch OP015strong500d6→016pilot500d8→017strong500d8, session54743, source99/harnessc750, seed2026/policyC fixed. Передdepth8 назначенfinitewall3600/external3660: наблюдавшийся500d6=751.234s, глубина8имеет4xleaves/uncertaincost;500treesfixed/fullcheck/noearlystop. LocalJobwrapper единственнаяdelta max1860→3660 (5a5dc209), configd9be47ca задаётoverride иCPUscope. Independentreviewбезfindings; RSStarget8GiBнеhardcap, internalCatBoostautoPVCdefault−1раскрыт. Currentpendingreceiptsoleauthority.


### Предварительное объяснение MAP/Recall: существующие pilot150 и pilot500

Необязательное уточнение HM-W003 выполнено без нового обучения и без raw DB/полного frame: отдельный проход по двум сохранённым top12, полному Y и query exports. 6 synthetic witnesses и независимое read-only review пройдены; фактический проход 3.015 s (external3.468 s), observed largest-process peak704917504B, DuckDB512MB/1thread. Status PRELIMINARY_PASS до общего независимого grid audit; C-membership и covered counts здесь не устанавливаются заново. Script/report — необязательные локальные файлы ignored artifacts/hm-campaign/diagnostics/rank_components.py и rank-components-selection/report.json.

Разность pilot500d6−pilot150d6 на тех же2111Q+: MAP−.00191885510, Recall+.00477224713. Вклады по исходным позициям суммируются в эти разности:

| Ранги | Вклад в разность MAP | Вклад в разность Recall |
|---|---:|---:|
| 1–3 |−.00238504806|+.00014006205|
| 4–6 |+.00003882381|+.00092774172|
| 7–12 |+.00042736915|+.00370444335|

Для701пользователя с единственной будущей целью within-stratum MAPΔ−.00698548559; взвешенный вклад этой страты в общий MAPΔ−.00231967096. Остальные страты2–3/4–12/>12целей (795/577/38пользователей) вместе дают положительное смещение, частично компенсирующее этот отрицательный вклад. Общий macro восстанавливается по весам численности страт, не средним четырёх средних.

Это аддитивное описание конкретных предсказаний: AP использует общий precision-prefix и полный min(12,|Y|), Recall — полный |Y|. Увеличение раннего Recall само по себе не гарантирует рост раннего AP. Размер Y известен из будущего и используется только для этого описания, не для features/выбора M; bins выбраны после наблюдения результата. Переобучение, причинный механизм и статистически установленное ухудшение этим не доказаны, slice CI не вычислялись. Сетка/M/selector/final plan не меняются.

## HM-R003: ручная сетка принята, M зафиксирован — 2026-10-18T11:35:04.450936+00:00

Независимый audit OP020 PASS17.797s, source-rebuilt Q/fullY и все6savedtop12/perquery/aggregate/weight/hash проверки, tolerance1e-12. Общие20kQ/2111Q+/6654fullY/C120. Выбор highestMAP поpredeclaredtie rule, не поRecall.

| Features | Trees/depth | MAP12 | Recall12 |
|---|---:|---:|---:|
| Pilot23 |150/6|.03389372|.06061625|
| Strong34 |150/6|.03287392|.06120164|
| Pilot23 |500/6|.03197486|.06538850|
| Strong34 |500/6|.03323696|.06613373|
| Pilot23 |500/8|.03309838|.06368047|
| **Strong34 M** |**500/8**|**.03451448**|**.06672828**|

M−pilot150Δ+.00062076,descriptive95%CI[−.00179401;+.00304568]; M−recencyΔ+.00540886CI[+.00268669;+.00818414]. Оба интервала условны на фиксированных моделях/одной неделе; выбор trainingpolicy и M на Sep02 делает это development, не подтверждающий final. Лучший из шести recipes, не globaloptimum. Auditorlimitations (savedtop12ordering only/no fullnative re-predict) сохраняются. Optionalrankcomponents получают подтверждениеC-membership/metrics обычнымaudit; описательные/непричинные пределы сохраняются.

Историческая реализация двухпоточной сетки сохранена в локальномGit:22c99b4(data/baselines),7f69656(featurestudy/audits/guardSOURCE). 106H&Mtests/rootgitdiffcheck PASS доcommit; внешнихпубликаций нет.

### Операционное изменение до generated fits

После выбораM разрешён и независимо проверен переход2→4потока runnerSQL/train/predict: одинheavyworker,SQL2GB/spill8GB/desiredRSS8GiBбезhardcap, auditSQL/PVCselector остаются2. НаблюдавшийсяM2wall774.594s и14оставшихсяfixedfits с4/5trainanchors делают CPUэффективность существенной. Скорость и bitwiseidentity не обещаны. Научный рецептM Strong34/500d8/seed2026/20ksample20 фиксирован; свежийM4reference используется дальше независимо от егоMAP, **без повторного выбора manual recipe**. Все будущие M/all/selected/random/confirmation/final fits получаютодну новуюреализацию/4threads. Historicalmanual_tuning.fixed2 сохранён вconfig, явныйpost_manual_execution override фиксируетновыйэтап.

Reviewedfinalguardwiring включается вместе с этим изменением до freshM: defaultdevguard закрываетfinal, конкретногоdecisionlock ещёнет, finalquality неоценена. Sourceбудетзамороженпослеtests/review на весьstudy; purefeatureengine47/definitions/sampler/C/Y сохраняются. ФинальныеармыM/selected×2026/27 не меняются.


## HM-R004 technical reference и проверка GPU — 2026-10-18T11:53:23.330416+00:00

OP021 fresh M4 completed500trees/721.172s; MAP.03451447927572141 иRecall.06672827792680963 совпали с M2. OP022 independentauditPASS13.344s, reportSHAeddd172bd21d0c3a98cd8eea11dbc884bd3ecbe336b010705196ac688f9010e2. Совпадение этих метрик не доказывает универсальную эквивалентность backend/threadcounts. Generated fits ещё0, study/random names не frozen.

Пользователь спросил о GPU. Actual nvidia-smi: RTX3070/8192MiB,driver610.74,примерно2413MiBзанято. Primary CatBoost [GPU](https://catboost.ai/docs/en/features/training-on-gpu),[FAQ](https://catboost.ai/docs/en/concepts/faq) подтверждают поддержку, nondeterminism и различия defaults CPU/GPU. Installed nativebinary отклоняет usercallbacksGPU; GPUfit требует внешнего конечного Jobtimeout.

До GPUcostprobe зафиксирован operational gate: один training-only fit100d8/Strong34/3anchors/20ksample20, GPU0/thread4/gpu_ram_part.5/pinned256MiB/Bayesianbagging1/border128/Plain,0validation/predictions/qualityselection. ExternalJob600s,cooperative480до/послеnative, hardRSS/VRAMcap отсутствует. Успех для перехода: native100fit≤60s,total≤180s,полные100trees+save/freshreload/finite trainingPVCnoPoolPASS,noOOM. Если пройден — до generated outcomes объявляется повтор тех же конечных6manualrecipes наGPU и новыйM_GPU; если нет — продолжаетсяCPU. Выбор backend не по MAP. Это стоимость конкретного GPUrecipe, не причинное ускорение одного неизменного алгоритма: CPU defaults MVS/.8/254borders, GPU Bayesian/128.

Private optionalprobe sourcee3c083f4778c14f7bfbba68f11ea8d83615a35e7a449dbfbc3583e0a4b2e9bb6, независимое статическоеreviewPASS послеисправленияsave/reloadgap; actualnative покаUNRUN наэтомcheckpoint. Root soleheavyowner.

OP023 failed64.171s доnativeGPUfit: installedCatBoost1.2.10 parameter parser отклоняет int pinned_memory_size268435456. Exacterror сохранён; source data/probe result не менялись. No-fit nativeparameter checker подтвердил: int rejects, strings268435456/256mb PASS. Исправление только сериализации того же256MiB на string256mb, source33af0fbad9594e859fd7641dac30c3a3f895bfa58679bab9d9f25b6309ec7567; gate/recipe неизменны. Failedartifacts/receipt сохранены,pendingfalse; повтор только новыйOP024/outputпослеindependentreview. Это не GPUOOM/не отрицательный qualityresult.


### GPU backend принят по стоимости до quality fits — 2026-10-18T11:58:48.872283+00:00

OP024 completed100trees, nativefit12.062s, total73.344s/external73.671s; gatePASS. Prepare/load58.172s,Pool1.766s,save/freshreload.016s, trainingPVC34finitePASS безPool; 28nonzero. SavedCBM385840B/SHA87619d03ee5298cbf12eb6e875f734934c3413a47041e4a4469129f3f1a95993. ReportSHA01185a83e9fb94669dcc963a952234b97f1d10e0d99549c471adfecc6273d12d. GPUallocation observed~6023MiBtotalincludingotherapps~2325MiB; no hardVRAMcap claim.

Решение принято по training compatibility/cost, безvalidation/predict/quality: **GPU используется дальше независимо от его качества относительноCPU**. Повторяется ровно та же заранее конечная сетка6manualrecipes, теперь GPUBayesian1/border128/Plain/device0/gpu_ram_part.5/pinned256mb/thread4. Выбирается M_GPU прежним highestSep02MAP/tie rule и используется точный победившийfit без дополнительногоreference. Все generated/confirmation/final fits получают этот же GPUrecipe/backend. CPU34/500d8 остаётся отдельным историческим выбором; правило его неизменности относилось к CPU-этапу. Новой сетки сверх6GPUrecipes/поиска доpositivegain нет.

GPUнедетерминирован дажеприfixedseed; futuremodelseeds2026/27 и paired peruserbootstrap unchanged. Support/C0-Q120/Q/fullY/labels/weights/grammar неизменны, generated0 иfinaluntouched. `manual_tuning_gpu` config зафиксирован до первогоGPUqualityfit, post_manual_gpu_execution будетсоздан только после штатногоaudit/winner. Sourceintegration+GPUfake-flow tests+independent review нужны до запуска этой сетки.


### GPU quality source заморожен — 2026-10-18T12:06:33.683984+00:00

Локальный commitc46912d содержит optionalGPUrunner, строгиеbackend/frozenwinnerguards, portable stdlib`hm_job` и командывоспроизведения. Root128H&MtestsPASS36.517s; independent main56targeted+job8nativeWindowslifecyclePASS; UTF8LF/gitdiffcheckPASS. Источники GPUrunner864921a6...,selector a4ce7d56...,finalguard165286d0...,supervisor a8ca33c3...; pureengine47/baseline0b/retrievalc0d/audit e657/contrasts d17 неизменны.

Подготовлены и запущены конечные OP025–030 по порядкуconfig.manual_tuning_gpu.candidate_configs: manual_pilot150d6/500d6/500d8,strong_manual150d6/500d6/500d8. Каждыйfit GPU0/Bayesian1/border128/Plain/500or150trees/depth6or8,3trainanchors20k/sample20,S `2020-09-02`,безeval_set/earlystop. NativeGPUбезPythoncallback: canonicalinnerJob1860s,cooperative1800до/после, optionalouterreceipthelpersupervisorbackup1920s. Каждый output новый, source/params/runtime/inputs захешированы, whole-tree/resolvedGPU обязательны.

Все шесть результатов пройдут independentfullQCY/source/predictionaudit до выбора M; никакая pointMAP промежуточногоfit не меняет оставшиеся варианты. Решение оGPU принято ранее поcostgate, CPUqualityнеиспользуетсядлявыбораbackend. Наэтомcheckpoint finalещёнеоценён, generatedfits0.


## HM-R005: GPU-сетка принята, M_GPU зафиксирован — 2026-10-18T12:20:43.957810+00:00

Шестьfits OP025–030 заняли суммарно737.857s external. OP031 auditPASS18.109s (fullsourceQ/Y/cacheweights/labels/identity/top12/perquery/aggregate, tolerance1e-12), отдельныйread-onlyreviewPASS. ОбщиеQ20000/Q+2111/Y6654/C120; source864921a6/runtimeGPU4.

| Набор | Деревья/глубина | MAP12 | Recall12 | external s |
|---|---:|---:|---:|---:|
| Pilot23 |150/6|.03109780|.05781418|97.984|
| Pilot23 |500/6|.03306930|.06369612|129.859|
| **Pilot23 M_GPU** |**500/8**|**.03367563**|**.06322521**|**146.937**|
| Strong34 |150/6|.03215700|.05760557|88.140|
| Strong34 |500/6|.03145299|.06133960|131.031|
| Strong34 |500/8|.03161805|.05947629|143.906|

Победитель highestMAP по прежнемуtie rule; это лучшийизшестиGPUrecipes, неglobaloptimum. M−pilot150Δ+.00257782615,descriptive95%CI[+.00044097406;+.00472033503]; M−recencyΔ+.00457000868CI[+.00198921157;+.00731418808]. Bootstrap2000/seed2026/pairedpositiveuser, conditionalonfixedmodels/week; selection/supportнаэтойнеделенеучтеныинтервалом. CPU/GPUqualityсравнениенеиспользуетсядлявыбораbackend. Sourceauditlimitationnativeall-candidatescoresнепересчитываютсясохраняется.

Прямо reusedOP027:fitidentity1580d00433f323ae659f3f484b60c094ecb7a501a45d30c8c3fc0f5bd981021e/reportSHA5e5aeb2bd00a7cd31aa79c64bae2f5c6d795c65be5a33655d2843ea09d44e003. FixedM23/500d8/GPU_Bayesian1/border128/Plain/seed2026/train20k_sample20; post_manual_gpu_execution закреплёндоprepare/generatedfit. Pool58/all81/selected+random35. ПятьпрежнихStrong34aggregatealiasesкорректновозвращаютсявpoolотносительноточногоM23; [HM-W005](research-lab/hm-wave005.md) добавляеттолькоoptionallineagereporting,0fits/gates.


## HM-R006: автоматизация на selection — принятый отрицательный/неопределённый результат

Принято 2026-10-18T12:36:39.455322+00:00. Study OP032 до generated fit закрепил pool58, M23 и три random12 (seeds101/102/103). OP033 all81 обучен один раз; OP034 training-only PredictionValuesChange выбрал12. Независимый saved-CBM fresh load/PVC без validation Pool повторил все importance и имена. Selected35 и random35 OP035–038 завершены, каждый500 деревьев на GPU/seed2026 с тем же train20k/sample20; external150.563/147.985/146.891/157.516s. Успех этих проверок не означает выигрыша качества.

OP039 independent raw validation/cache/labels/weights/identity/top12/per-user audit: PASS,18.188s. OP040 fixed contrasts: completed,2.015s. Отдельный reviewer пересчитал все семь paired intervals из hashed per-user exports; совпадение≤1e-12. Root сверил actual source/backend/tree count/schema/config. ОбщиеQ20000/Q+2111/Y6654; MAP условен на пользователях с будущей покупкой, полный distinct Y включает цели вне C.

| Вариант | Число признаков | MAP@12 |
|---|---:|---:|
| M_GPU |23|0.03367563|
| M+all |81|0.02954207|
| M+selected12 |35|0.03096309|
| M+random101 |35|0.03328206|
| M+random102 |35|0.03148655|
| M+random103 |35|0.02803546|

| Фиксированный contrast | ΔMAP | 95% paired user CI |
|---|---:|---|
| selected−M |−0.00271254|[−0.00529108; +0.00008395]|
| mean(random3)−M |−0.00274094|[−0.00454407; −0.00094709]|
| selected−mean(random3) |+0.00002840|[−0.00217110; +0.00234514]|
| selected−random101 |−0.00231897|[−0.00518383; +0.00072087]|
| selected−random102 |−0.00052346|[−0.00300703; +0.00208672]|
| selected−random103 |+0.00292763|[+0.00038346; +0.00559705]|
| all−M |−0.00413356|[−0.00678723; −0.00162314]|

Среднее random3 — сначала среднее AP трёх фиксированных моделей внутри каждого пользователя, затем bootstrap2000/seed2026, не score ensemble и не выбор лучшего random. CI описательны для этой недели/моделей; не учитывают selection/multiple comparisons и вариативность нового обучения. Положительный selected−random103 отдельно не доказывает пользу selector. Улучшение selected над M или средним random не установлено. Не добавляем fits, не меняем программы или final по этим результатам. HM006 done; HM007 диагностическая confirmation→frozen final.

AuditSHA f5e2985dcad3f069b68ad5e65bea949588bc36b124f4f9b4fda8e63ea43d997a; contrastsSHA9e1f2f47fae063c96012d8e89498fe410d85955d5d783d762e099994e1d73ea2. Локальные необязательные inputs/results: artifacts/hm-campaign/{feature-study,feature-selection,generated,audits/selection,contrasts/selection}; команды и необходимые определения находятся в tracked [воспроизведении](hm-reproduce.md) и [program table](hm-generated-programs.md). Native omitted candidate scores аудитор не пересчитывает.

Операционное уточнение: C: заполнен на12:31UTC; модели, DB, данные — на D:. НачинаяOP039 TEMP/TMP и CUDA_CACHE_PATH задаются только дочерним процессам на D:/tlab-recsys-2026/artifacts/hm-campaign/{tmp,cuda-cache}. Source/config/параметры моделей не менялись; системные настройки и чужие файлы не затрагивались. Причина заполнения C полностью не установлена: pagefile30.93GB, recentTemp главным образом другая работа, нашиhm-*Temp3.55MB. Это не доказанный GPU/ML дефект.


## HM-R007: diagnostic confirmation принята — 2026-10-18T12:56:08.432579+00:00

OP041 collection64.235s, затем пять fixed GPU fits OP042–046: M196.515s,selected226.265s,random101205.250s,random102196.843s,random103217.422s. Train anchors12/19/26 августа и2 сентября,20k/sample20/cohort2026; все500 деревьев/depth8/GPU, source/config прежние. OP047 source/metrics auditPASS20.641s; OP048 six fixed contrastscompleted1.906s. Независимый reviewer воспроизвёл все6 contrasts/CI из hashed exports≤1e-12; Root сверил backend/trees/4anchors/chronology/config/no pending.

Q20000/Q+1957/Y6197; coverage0.1374858803, oracleMAP0.1533134285. MAP: M.031220688912; selected.029182691772; random101.028393695941; random102.029390474753; random103.026918951665. Selected−M−.002037997140 CI[−.004779038829;+.000618398083]; meanrandom3−M−.002986314793 CI[−.005234558083;−.000879516763]; selected−meanrandom3+.000948317652 CI[−.001736167599;+.003558416998]. Остальные три seed-specific random contrasts сохранены в полном report; ни один не используется для выбора лучшего random. Установленного выигрыша selected нет. Bootstrap2000/seed2026/pairedpositiveuser; diagnostic single-week/fixed-model scope, не независимый final.

AuditSHA ef712ae71179fbf93e7ce862f7c343c9d2ec744ba1552686f52fe3d038353bd3; contrastsSHA50af1e1c7aa2f0522f8b7ec157508a0a8e7bd978e606312c4d49782cc7d7a4ff. Shared new collection manifestSHA640ad4f4da7045b8364dc485d7713eec7df6b2a677edfe24f283654f8218550f; originalDB unchanged. Никаких пересмотров рецепта/списков/seeds по этим scores. [W006](research-lab/hm-wave006.md) принята после двух раундов, новые эксперименты0.

Дословный documented LockCode после PASSconfirmation создал configs/datasets/hm-final-lock.json; полный load_lockPASS, SHA d47df2aca05311a0e56aa645dbd5c20097ca9bcf656256dc4db8120059a05e80. Конкретное независимое ревью lock PASS: load_lock/authorize_collect, code/runtime/5trainrefs/featureorder/contrasts/outputabsence; безSQL/моделей/finalY. Локальный commit78a4d3d сохранён доfinalдоступа. OP049 finalcollectioncompleted61.204s, manifest прикрепил тот жеSHA lock; затем начат fixed4fitbatch OP050–055/session4383. Production source/configbytefrozen с начала generated study. Инструкция нового повтора использует отдельный hm-final-lock-repro.json; historical lock не перезаписывается.


## HM-R008: frozen final принят — 2026-10-18T13:16:15.309456+00:00

OP049 finalcollection61.204s, manifestSHA942fb1b6fc70735fea3974f12049df87514aeb2aa91ac2eee0f22155e857b2d4, прикреплён lockd47df2aca05311a0e56aa645dbd5c20097ca9bcf656256dc4db8120059a05e80. Lock/source/runtime/train identities повторно загружены Root после выполнения: PASS. Все049–055succeeded/pendingfalse, session4383exit0; процессов hm_experiment/hm_job/audit/contrasts при проверке не обнаружено.

| Final arm | MAP@12 | external s |
|---|---:|---:|
| M2026 |0.033396600580|237.187|
| M2027 |0.035461266265|217.860|
| selected2026 |0.032236435408|235.469|
| selected2027 |0.033068501328|230.719|

Основной per-user seed-mean: M0.0344289334226139 / selected0.03265246836780082; Δ−0.0017764650548130736, CI[−0.0037588076126727544;+0.00007830806703740478]. Seed2026Δ−0.0011601651720543112 CI[−0.0034024045312337397;+.0010497155756263978]; seed2027Δ−0.002392764937571837 CI[−.005416657565809625;+.0004495190973978777]. Bootstrap2000/2026 по1905положительным пользователям после среднего AP внутри пользователя. Не score ensemble/не user×seed pooled N; не распределение новых training/time seeds.

Q20000/Q+1905/fullY5962; C-positive894/5962=0.1499496813, oracleMAP0.1735293694. Средний RecallM0.06684442099/selected0.06626923015; all-query-zeroMAPM0.003279355909/selected0.003110147612. Train5anchors/20k/sample20/cohort2026,4233 естественных positive rows;500fulltrees/GPU commonparams, names/config/source unchanged.

OP054 auditPASS12.937s, SHA721c90494072656b1b1b4a92a9ab2c9535698ba4c7dfa363f879aa88fd68b772; raw history-only hashedQ/full distinctY rebuildPASS. OP055 contrastscompleted1.578s, SHAfd4cd34c176360250bcc1acfb3d7e609eab0c24e0139b87b65f40834e83559aa; spec ровно lock.CONTRASTS. Независимый reviewer заново посчитал AP/Recall из четырёх hashed saved-top12+fullY и все3 intervals из per-user exports≤1e-12; metadata/chronology/source/runtime/params/order/PASS. Root сверил actualJSON/identities/spec/pending/processes. Ограничение аудита: omitted native scores не пересчитываются, global ranking из них независимо не строится.

Четыре final fits921.235s внешнего времени;20 завершённых GPU quality fits3481.685s. Это не весь campaign cost: cachecollections/разработка/проверки/probe/CPUhistory исключены. Итог selected gain не подтверждён; истинная эквивалентность/универсальный вред не утверждаются. HM001–007done; W006counter1 после final, next_due отменён при завершении core, никакого поиска до положительного результата.

Диски на13:14:52UTC: Cfree11,903,180,800B,Dfree46,810,824,704B. Наших удалений/перемещений не было; причины изменения свободного места C не установлены. TEMP/TMP/CUDA cache будущих исполнявшихся child jobs перенаправлялись на D сOP039 без системных env изменений.
