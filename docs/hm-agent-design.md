# H&M: перенос результата REES46 — рука MA (M23 + все колонки LLM-агента)

Контракт реализации. Составлен 2026-10-20 по `~/tlab-recsys-2026`, ветка `task1-v2`, на `f79914a`; якорь версии — коммит этого файла. В тот же вечер исправлен по независимому ревью (2 блокирующих замечания и 12 неблокирующих), затем по повторной проверке (1 и 8) и по третьей (0 и 5). В Git фиксируется до первой посылки M/E на Kaggle, поэтому правило чтения (раздел 4) записано раньше любого счёта Kaggle. Код пишется по этому контракту параллельно.
Исполнители ничего не решают сами. Всё, что здесь не названо, координатор решает письменно до начала реализации.

## 0. Рамка
- **Руки.** M — M23 из lock (18 numeric + 5 categorical). E — E46 из lock. MA — M23 плюс все колонки всех *валидных* предложений агента в замороженном порядке. Отбора по эффекту нет; механические фильтры из раздела 2 меток не видят и отбором не считаются.
- **Что проверяет MA.** Переносится утверждение «колонки LLM-агента без отбора поверх ручной базы». MA проверяет только агентскую половину H+, а не H+ целиком:
  - H+ в REES46 состоит из H (80 ручных признаков), 128 колонок DFS и 66 колонок агента. Его Hp−H в повторе 2020 (+0,0031 и +0,0029, около +2 %) — число H+, а не ожидание для MA.
  - Агентскую половину как добавку к базе на тесте REES46 не измерял. Есть только R 0,783 для одних таблиц агента как *замены* ручных признаков на B 2019 (`task1-v2-report.md`, таблица R). От DFS или от агента прирост H+, отчёт не знает.
  - Аналог H+ на H&M — «M + 58 программ + агент». DFS-подобная половина без отбора там уже дала −0,0041 (`hm-report.md`, All − M), поэтому эта рука не делается (D5).
  - База M23 (23 входа) слабее H (80 признаков), и размер эффекта между ними не переносится.
- **Неприкосновенно.** Locked-модули `hm_experiment`, `hm_retrieval`, `hm_feature_engine`, `hm_baseline`, `hm_eda` и `scripts/hm_kaggle.py` не меняются. Хеш `hm_kaggle.py` записан в `code` планов и fit-отчётов M/E, поэтому правка посреди прогона ломает resume у `score`. Новый код импортирует `scripts.hm_kaggle as kaggle` и вызывает функции через атрибут модуля (`kaggle.locked_recipe(...)`), чтобы patch'и фикстуры действовали.
- **Хранение.** Построчные выходы — только в ignored `artifacts/hm-agent/`. В Git: код, тесты, `configs/datasets/hm-agent-set.json`, `configs/datasets/hm-agent-prereg.json`, `configs/datasets/hm-agent-deviations.json`, `docs/hm-agent.md`, `docs/hm-agent-run/` (промпты, ответы, журнал; строк данных нет).
- **CLI как в `hm_kaggle`.** Запуск `.venv/bin/python -I scripts/<m>.py`, без `-I` отказ (`kaggle.isolated()`). В stdout одна JSON-строка, exit 0/1, сообщения native-библиотек маскируются. Используются:
  - из `scripts.hm_kaggle` (`kaggle.X`): `new_output`, `atomic_json`, `failure`, `isolated`, `code_identity`, `database_sources`, `read_collection`, `hold_lock`;
  - из `scripts.hm_experiment` (`experiment.X`): `Deadline` с методом `interrupt_sql`, `resource_preflight`, `canonical_digest`, `sha256_file`.

  Вызовы идут через атрибут модуля: фикстура патчит `experiment.Deadline`. `code` = `kaggle.code_identity()` + SHA-256 новых модулей и `hm_result_audit.py`. Набор ключей один и тот же у prereg, записей отклонений и всех артефактов.
- **Обозначения в командах.** `DB` = `artifacts/hm-kaggle/eda/audit.duckdb`, `$C` = `artifacts/hm-kaggle/collections` (как в docs/hm-kaggle.md), `E` = `artifacts/hm-agent/export`, `S` = `configs/datasets/hm-agent-set.json`.

## 1. Песочница и представления данных

### 1.1 Экспорт: один раз, после `eda`
`hm_agent_sandbox.py export --database DB --output E [--before YYYY-MM-DD]`
- **`tx/d=YYYY-MM-DD/*.parquet`** (`PARTITION_BY (d)`): `t_dat DATE, customer_id VARCHAR, article_id VARCHAR, price DOUBLE, sales_channel_id VARCHAR`. Все строки, дубли сохраняются. С `--before` пишутся только `t_dat < before` — срез для leakcheck.
- **`articles/articles.parquet`**, всё VARCHAR: `article_id`, `product_code` и пары код/имя `product_type_no/name`, `product_group_name`, `graphical_appearance_no/name`, `colour_group_code/name`, `perceived_colour_value_id/name`, `perceived_colour_master_id/name`, `department_no/name`, `index_code/name`, `index_group_no/name`, `section_no/name`, `garment_group_no/name`. Свободный текст (`prod_name`, `detail_desc`) не экспортируется.
- **`customers` не экспортируется.** Правило docs/hm-pilot.md:43 («прочие текущие свойства не допускаются в модель») распространяется и на `age`, и на `postal_code`.
- **`export.json`:** `format='hm-agent-export-v1'`, `status`, `before`, `database{sha256,bytes}`, `sources` (= `kaggle.database_sources`), `tx{rows,days,first,last,files{relpath:{sha256,rows}}}`, `articles{rows,sha256}`, `code`, `digest` = `experiment.canonical_digest` остальных полей. `read_export(path)` перепроверяет файлы; `digest` — identity экспорта во всех дальнейших манифестах.

### 1.2 `sandbox(export, anchor, keys_path, threads=4, memory='4GB')`
Новое in-memory соединение на каждую пару «якорь A + набор ключей», по образцу `task1/extra.py`:
1. `SET threads`, `memory_limit`, `enable_progress_bar=false`, `python_enable_replacements=false`; `temp_directory` — новый `mkdtemp(prefix='tlab-hm-sbx-')`, `max_temp_directory_size='8GB'`.
2. `SET allowed_directories` — только каталоги `tx/d=…` с `d < A` (со слешем в конце).
3. `CREATE VIEW tx AS SELECT <5 колонок> FROM read_parquet([файлы d<A], hive_partitioning=false) WHERE t_dat < DATE 'A'`. Барьеров два: каталоги и фильтр.
4. `CREATE TABLE articles AS SELECT a.* FROM read_parquet(<articles>) a SEMI JOIN (SELECT DISTINCT article_id FROM tx) USING(article_id)`. Остаются только товары, купленные до A: наличие в каталоге не доказывает, что товар тогда продавался.
5. `CREATE TABLE cand AS SELECT customer_id, article_id FROM read_parquet(keys_path)` (только ключи, без меток и источника); `CREATE TABLE users AS SELECT DISTINCT customer_id FROM cand`.
6. `SET enable_external_access=false; SET lock_configuration=true`.

Агенту видны только `tx`, `articles`, `cand`, `users`. Таймаут — `threading.Timer(t, con.interrupt)`. `agent_columns` получает ключи DataFrame'ом, пишет их в `keys.parquet` во временном каталоге песочницы и только потом вызывает `sandbox`; DataFrame в песочницу не регистрируется.

### 1.3 `check_sql(sql, level)` — второй слой защиты
- Ровно один оператор (`SELECT` или `WITH`), `;` только в конце. Комментарии (`--`, `/*`) запрещены.
- Якорь пишется только как `DATE '{A}'`. Другие `{…}` и литералы дат `'YYYY-MM-DD'` запрещены.
- FORBIDDEN (`re.I`, слово целиком):
  - данные: `transactions|customers|frame|labels?|targets?|hm_\w+|_hm_\w+`;
  - файлы и метаданные: `read_\w+|parquet_\w+|csv|json\w*|glob|getenv|query|query_table|duckdb_\w+|information_schema|pg_catalog|sqlite_master|pragma\w*`;
  - команды: `attach|detach|copy|export|import|install|load|set|reset|use|call|create|drop|insert|update|delete|alter`;
  - недетерминизм: `random|setseed|uuid|gen_random_uuid|now|today|current_date|current_time|current_timestamp|get_current_time|sample|tablesample`.
- При `level='article'` нельзя упоминать `cand` и `users`: значение не зависит от батча и кешируется на процесс.

### 1.4 Контракт вывода предложения
- **Формат:** `{"name","idea","level","sql"}`, `level ∈ {pair, customer, article}`.
- **Ключи:** `pair` → `customer_id, article_id` (⊆ `cand`); `customer` → `customer_id` (⊆ `users`); `article` → `article_id` (⊆ `articles`). VARCHAR, без NULL, уникальны. Ключ вне множества — ошибка, а не тихий фильтр: так запросы остаются узкими.
- **Значения:** 1–3 колонки `^ag_[a-z][a-z0-9_]{1,38}$`, уникальные среди принятых и не пересекающиеся с `feature_registry()` и `experiment.RESERVED`. Типы: целые, DECIMAL, FLOAT, DOUBLE, BOOLEAN. VARCHAR, DATE, TIMESTAMP — ошибка (даты переводить в дни до `{A}`). Других колонок нет.
- **Harness:** `CREATE TEMP TABLE _x AS <sql>` → проверки → `CAST(v AS DOUBLE)` → LEFT JOIN на ключи батча по уровню; строки в порядке `customer_id, article_id`.
- **NULL = «нет данных»:** нет строки, NULL, не конечное значение (±inf, NaN) или переполнение float32. В модели это NaN; CatBoost CPU по умолчанию `nan_mode='Min'`. Свои заглушки агент ставит сам через `COALESCE`.
- **Инвариантность к батчу.** Значение зависит только от `tx`, `articles` и своего ключа; `cand`/`users` — только фильтр. Окно `PARTITION BY customer_id` по `cand` допустимо (все 120 кандидатов клиента всегда в одном батче), агрегаты по `cand` поперёк клиентов — нет. Окна с полным tie-break (`…, article_id`). Нарушения ловятся механически (раздел 2).
- **Лимиты.** На пробе таймаут 20 с (pair/customer) и 60 с (article), вывод ≤ 20 млн строк. Бюджет набора на пробе: Σ времени валидных pair+customer ≤ 90 с, article ≤ 180 с. В рабочих прогонах таймаут запроса 900 с плюс `--wall-seconds` команды.

### 1.5 Промпт: `hm_agent_loop.render_prompt`, на английском
1. **Задача.** H&M, транзакции 2018-09-20..2020-09-22, якоря — среды. Метка — различные покупки клиента в `[A, A+7d)`. Метрика — MAP@12 по купившим.
2. **Кандидаты C0-Q120:** последние 20 различных покупок за 90 дней (дата DESC, затем id) плюс дополнение из топ-200 по различным покупателям за 7 дней, ровно до 120.
3. **Обучение.** CatBoost Logloss, 500 деревьев, depth 8. Недельные якоря 2020-08-12..09-16, по 20 000 клиентов: все позитивы + 20 hashed негативов с весами. Скоринг 2020-09-23 — все клиенты с покупкой за 90 дней.
4. **M23** с формулами из `feature_registry()` (`name: formula; missing`).
5. **Схемы** `tx`, `articles`, `cand`, `users`, правила 1.3–1.4, пример `t_dat >= DATE '{A}' - INTERVAL 28 DAY`.
6. **Статистики** `probe/stats.json`, только история до 2020-09-09: строки/клиенты/товары за 7/28/90/365 дней и всего; квантили покупок на клиента за 90 дней; доля клиентов с ≥ 2 днями покупок; квантили цены; доли `sales_channel_id`; кардинальности атрибутов и топ-10 значений (код + имя) по покупкам за 28 дней; среднее число recent-кандидатов и доля global.
7. **Предупреждение:** «Все валидные колонки войдут в модель без отбора. Лишние и шумные колонки вредят — нужны немногие сильные и неизбыточные сигналы. Customer-уровень работает только через взаимодействия».
8. **История попыток:** SQL, статус и причина, статистики валидности (без эффектов), остаток бюджета.
9. **Запрос:** «Propose N new features … Answer with a JSON list only: `[{"name","idea","level","sql"}]`».

Не входят: строки данных, id клиентов, метки и любые числа из недель меток (покупатели, покрытие, MAP).

## 2. Обратная связь: валидность и покрытие
**Решение: эффект на метках агенту не показывается.** Основания:
- Переносится утверждение «колонки агента без отбора» (раздел 0, «Что проверяет MA»), а не механизм отбора.
- Эффект одной колонки (~+0,0003 MAP) много меньше шума 09-16 (95 % CI ≈ ±0,0025 при 1 905 покупателях). Такая обратная связь — в основном шум, и агент под неё подстраивается: в REES46 предложения оказались подстроены под половину A.
- Цена: 30 предложений × CPU fit по 15–45 мин = 8–22 ч на один seed, до пятницы не помещается.
- Метки 09-16 агенту не показываются, поэтому для выбора колонок эта неделя свежая. Для M и E она не свежая: это финальная неделя v1 (`hm-report.md`, final 16–22 сентября). Неделя Kaggle свежа для обучения и для правил отбора, но не для знаний LLM (раздел 5).
- Ограничения пишутся в prereg:
  - в REES46 агент получал dNDCG. Если окажется MA ≤ M, отсутствие этого сигнала — одно из объяснений, и этот прогон его не отделит;
  - если окажется MA > M, одно из объяснений — знание LLM о решениях этого соревнования (раздел 5). Его прогон тоже не отделит.

**Проба:** `hm_agent_sandbox.py probe --database DB --export E --anchor 2020-09-09 --users 5000 --output artifacts/hm-agent/probe-2020-09-09`. Порядок: `kaggle.create_item_ranks(con, A)` → первые 5 000 клиентов с покупкой в `[A−90d, A)` по `sha256(id||':2026'), id` → `kaggle.create_chunk_candidates(con, 'probe_users', 5000)` → `build_features`. Файлы: `keys.parquet`, `sources.parquet` (ключи + source), `m23.parquet` (18 numeric), `stats.json` (п. 6 из 1.5), `probe.json` (identity). Метки не строятся.

**Запись по предложению** (`evaluate_proposal` → `log.jsonl`):
- `id, round, index, name, idea, level, sql, status (valid|invalid|budget), error (≤400 символов), seconds, rows`;
- по колонке: `name, non_null_share, non_null_share_recent, non_null_share_global, distinct, p01, p50, p99, max_abs_spearman, nearest`.
- Spearman — на фиксированной подвыборке пробы: 100 000 строк с наименьшим `sha256(customer_id||'|'||article_id)`, по строкам, где обе колонки не NULL. Если таких меньше 1 000 — `null`.

**Предложение атомарно** и невалидно, если хотя бы одно:
- ошибка SQL, нарушение контракта, таймаут или нехватка памяти DuckDB;
- у колонки меньше 2 различных не-NULL значений или меньше 100 не-NULL строк;
- `|ρ| ≥ 0.999` с колонкой M23, ранее принятой колонкой или соседней колонкой того же предложения;
- нарушена инвариантность: для первых 1 000 клиентов пробы значения из прогона на 5 000 против прогонов на двух половинах по 500; допуск `|x−y| ≤ 1e-9·(1+|x|)`, NULL == NULL;
- превышен бюджет — статус `budget`.

**Раунды.**
- 6 × 5 = 30 предложений, как в REES46.
- Вызов изолирован от настроек пользователя:
  - команда: `claude -p <prompt> --model claude-opus-5-5 --safe-mode --setting-sources project --tools '' --strict-mcp-config --disable-slash-commands --no-session-persistence --no-chrome --output-format stream-json --verbose`;
  - окружение — только `HOME`, `PATH`, `USER`, `LOGNAME`, `TMPDIR` и `LANG`, без переменных `CLAUDE_*`, `ANTHROPIC_*`, `MCP_*`;
  - cwd — новый пустой `mkdtemp(prefix='tlab-hm-agent-llm-')`, timeout 900 с.
- Строка init (`tools`, `mcp_servers`, `skills`, `slash_commands`, `plugins`, `model`, версия CLI) пишется в журнал и копируется в `docs/hm-agent-run/`. Вызов отклоняется как сбой, если `tools`, `mcp_servers`, `skills` или `slash_commands` не пусты, модель не та или есть плагин, кроме встроенного `agents-md@builtin`. Проверка 20.10 в 23:25 на claude 2.1.284 дала чистый init: из плагинов только `agents-md@builtin`.
- Повтор только при непарсимом ответе или сбое вызова, не больше одного на раунд. Лишние предложения отбрасываются, недостающие не добираются.
- Вызовов ≤ 12 (`--max-calls 12`; больше 40 код не принимает). Ожидается 6–8 вызовов, $2–5.
- Цикл в основном ждёт LLM: 1–2 ч по часам; проба с threads=3.
- **Один прогон агента.**
  - Повтор допустим только после технического сбоя: падение кода, сбой CLI, исчерпанный лимит повторов. Повтор идёт в новую папку `run-<id>`, причина записывается, предложения сбойного прогона в набор не входят.
  - Решение о повторе не опирается на содержание предложений.
  - Если замороженный набор пуст, MA не строится. Результат записывается как «агент не дал валидных колонок».

**Заморозка:** `hm_agent_loop.py freeze --run artifacts/hm-agent/run-<id> --output S`. В набор входят все `valid` в порядке (раунд, индекс, порядок колонок).

## 3. Точки соединения

### 3.1 Коллекции → сайдкары
`hm_agent_kaggle.py sidecar --database DB --export E --agent-set S --collection $C/<A>-c0q120 --output artifacts/hm-agent/sidecars/<A> --threads 4` — для 6 якорей 08-12..09-16. Коллекции не меняются.
- Коллекцию проверяет `kaggle.read_collection`. Отдельное соединение читает из `frame.parquet` только `customer_id, article_id` → `keys.parquet` (без меток, по ключам).
- `agent_columns(...)` → `agent.parquet`: `customer_id, article_id` + `S.columns` как DOUBLE; строк ровно столько, сколько ключей (2,4 млн), в порядке ключей.
- `manifest.json`: `format='hm-agent-sidecar-v1'`, `status`, `anchor`, `collection{manifest_sha256, frame_sha256, qcy_identity, candidate_identity, database}`, `agent_set{digest, sha256, columns}`, `export_digest`, `keys{rows, sha256}`, `files{agent.parquet}`, `non_null{col: n}`, `seconds{proposal_id: s}`, `code`, `runtime`. Обязательно `collection.database == export.database`.
- Цена: не больше 4 бюджетов пробы на якорь, ожидаемо 2–6 мин; RSS ≤ 6 ГБ.

### 3.2 Fit MA
`hm_agent_kaggle.py fit --seed {2026|2027} --train $C/<A>… --sidecars artifacts/hm-agent/sidecars --prereg configs/datasets/hm-agent-prereg.json [--validation $C/2020-09-16-c0q120] --output artifacts/hm-agent/{port|final}/MA<seed> --threads 8 --wall-seconds 14400`
1. `recipe = kaggle.locked_recipe('M', seed, threads)`. Проверки входов как в `kaggle.fit`: якоря различны, валидация после обучения, features и database общие.
2. Prereg должен существовать и совпадать по `agent_set.sha256` и `export_digest`. Хеши кода должны совпадать с prereg или с последней записью отклонений (раздел 4). Иначе отказ: ни одного числа MA до prereg.
3. Для каждой коллекции:
   - `frame, _, summary = experiment.load_part(con, path, manifest, M23, recipe['train_users'], recipe['negative_sample'])` — те же строки, метки, негативы и веса, что у M (выборка не зависит от имён);
   - блок: ключи `frame` JOIN `agent.parquet` USING ключи ORDER BY ключи; строк ровно `len(frame)`, ключи поэлементно равны;
   - `numbers = hstack(experiment.model_arrays(frame, M23num, M23cat)[0], agent_block(...))`. `agent_block` — float32 с NaN на не конечных, общий для fit и score. `model_arrays` к агентским колонкам не применяется: он требует конечных значений.
4. `experiment.model_pool(numbers, cats, M23num + S.columns, M23cat, labels, weights)`, `CatBoostClassifier(**recipe['hyperparameters'])` с той же wall-callback; проверяются `CHECKED_PARAMETERS` и число деревьев.
5. С валидацией: `load_part(..., None, None)` + блок 09-16 → `pilot.rank_collection`, `experiment.write_private_predictions` → `query-metrics.parquet`, `predictions-top12.parquet`.
6. `report.json` — поля `kaggle.fit`, плюс `format='hm-agent-fit-v1'` (`kaggle.load_fit` его не примет), `arm='MA'`, `features.numeric = M23num + S.columns`, `agent{digest, sha256, columns, export_digest, sidecars{anchor: manifest_sha256}}`.

Парность: `training_populations` и `inputs` MA обязаны совпадать с отчётом M на тех же train-коллекциях; это проверяет `contrast`.
Память: ~2,0 млн строк × (18 + ~70) float32 ≈ 0,7 ГБ плюс pandas, пик ≤ 10 ГБ. Время — в 2,5–4 раза больше, чем у M.

### 3.3 Скоринг на 2020-09-23
`hm_agent_kaggle.py score --database DB --export E --agent-set S --fits artifacts/hm-agent/final/MA2026 artifacts/hm-agent/final/MA2027 --control artifacts/hm-kaggle/final/M2026 --output artifacts/hm-agent/score-2020-09-23 --chunk-users {15000|30000} --threads 4 --wall-seconds 28800`
- **Цикл `kaggle.score` на его функциях:** `database_connection`, `create_item_ranks`, `hm_k_users` дословно той же SQL (порядок sha256, `(user_rank-1)//chunk_users`), `ordered_digest`, `create_chunk_candidates`, `build_features` с проверкой digest и ключей, `write_top12`, `check_chunk`, `hold_lock`, resume по квитанциям.
- **Чанк.** Ключи кадра → `agent_columns(E, A, keys, S, cache=article_cache)`. Article-уровень считается один раз на процесс. Ключ кеша — `(export digest, якорь, id предложения, sha256 SQL)`, поэтому значение одного экспорта или якоря не попадает в другой. Leakcheck работает без кеша (`cache=None`); это проверяет тест с article-утечкой. Блок выравнивается по ключам кадра (merge 1:1 с проверкой). Контроль M2026 — через `experiment.model_arrays`, как в `kaggle.score`; MA — M23 + блок.
- **Квитанции чанка** дополнительно содержат `nonfinite_scores` по моделям, `agent_non_null{колонка: n}` и `agent_rows` — для гейта (раздел 4).
- **Совместимость с `assemble`.** `plan.json` в формате `PLAN_FORMAT` с теми же ключами плюс `agent{digest, sha256, export_digest, columns}`. `models` — identity контроля (из `kaggle.load_fit`) и MA (из `load_agent_fit`, то же поле `name`). Квитанции — `CHUNK_FORMAT` плюс `agent_seconds`, `nonfinite_scores`, `agent_non_null` и `agent_rows`. Поэтому неизменённый `hm_kaggle.py assemble --scores artifacts/hm-agent/score-2020-09-23 --model MA2026` работает: `--model` свободный, `users_digest` пересчитывается из DB.
- **Контроль:** `hm_agent_kaggle.py control --agent-scores … --kaggle-scores artifacts/hm-kaggle/score-2020-09-23 --model M2026`. `(customer_id, rank, article_id)` совпадают точно, `|Δscore| ≤ 1e-9`. Печатаются счётчики и OK/DIFF; при DIFF MA не отправляется.
- **Оценки.**
  - Клиентов с историей ~0,5–0,7 млн (точно — `plan.users`). Чанк 15k = 1,8 млн строк.
  - Locked features и 3 predict — примерно как в `kaggle.score`. Агентский SQL — не больше 3 бюджетов пробы на чанк (≤ 4,5 мин, ожидаемо 1–2).
  - Итого 1,5–4 ч, пик RSS 6–12 ГБ. Если квитанции `kaggle.score` M/E показали пик < 8 ГБ при 15k, брать 30k: меньше проходов по `tx`.

## 4. Обучение и оценка
| | Обучение | Валидация | Fits |
|---|---|---|---|
| Port (dev) | 08-12..09-09 | 09-16: 20 000 клиентов, 1 905 покупателей | M2026, M2027, E2026, MA2026, MA2027 |
| Final | 08-19..09-16 | — | M, E, MA × 2026, 2027 |

Все 11 fits — CPU-рецепт lock: 500 деревьев, depth 8, lr 0.05, L2 10, Logloss, Bayesian, temperature 1, 128 borders, Plain, без eval_set. У всех `--threads 8`. M/E 20.10 обучены с 8 (`resources.threads` в `report.json`), хотя runbook `docs/hm-kaggle.md` показывает 4. `contrast` требует равных гиперпараметров, кроме `random_seed`, включая `thread_count`, поэтому MA тоже обучается с `--threads 8`.

**Prereg** — `configs/datasets/hm-agent-prereg.json`, коммитится до первого MA fit. Содержит:
- sha256 и digest набора, число колонок; `export_digest`, identity DB; хеши `hm_agent_*.py`, `hm_kaggle.py`, locked-модулей и `hm_result_audit.py`;
- руки, seeds, threads, якоря train/val, список fits; дев-контраст, гейт, правило отказа, правило чтения Kaggle; запасные варианты.

**Первое число MA** — первая метрика MA на метках, то есть MAP или AP port-fit на 09-16. Счётчики сайдкаров, leakcheck и доли не-NULL меток не видят, первым числом не считаются.
- После первого числа запрещено: удалять колонки, менять SQL, параметры и данные, перезапускать агента в любом режиме.
- До первого числа prereg можно перевыпустить (например, после исправления кода); причина видна в истории Git.
- После первого числа допустимы только технические исправления: таймаут, память, размер чанка, падение кода и ошибка кода, найденная гейтом или контролем. Данные, SQL, колонки и параметры модели при этом не меняются.
- Каждое исправление записывается в `configs/datasets/hm-agent-deviations.json`: id, время, причина, `prereg_sha256` и полный набор хешей кода после исправления (те же ключи, что в prereg) и список шагов, которые оно пересобирает. Файл коммитится до запуска, который им пользуется.
- `fit_ma`, `contrast` и `gate` принимают текущий код, только если он совпадает с prereg или с *последней* записью отклонений, и пишут в `report.json` id записи.
- `gate` дополнительно проверяет `code` в манифестах сайдкаров, отчёте leakcheck, `plan.json` скоринга и отчётах port/final MA. Каждый такой хеш-набор должен совпасть с prereg или с одной из записей отклонений. Наборы ключей у всех одинаковы (определение `code` в разделе 0); другой набор ключей — FAIL. Каждый артефакт пишет в манифест или отчёт поле `deviation`: id последней записи на момент запуска или null. Порядок шагов: leakcheck, sidecar, port, contrast, final, score, control, assemble. Артефакты шагов, перечисленных в записи, и всех шагов позже в этом порядке должны нести эту запись или более позднюю. Так исправления в `sidecar`, `score_ma` и `leakcheck` тоже связаны с prereg.

**Дев-контраст:** `hm_agent_kaggle.py contrast --reference port/M2026 port/M2027 --alternative port/MA2026 port/MA2027 --prereg … --output artifacts/hm-agent/dev-contrast.json`.
- `query-metrics.parquet` → у каждого пользователя среднее `ap12` по seeds руки → `hm_result_audit.paired_bootstrap(ref, alt, draws=2000, seed=2026)`. Дополнительно MAP каждого fit и MA−M по seeds; без округления.
- Парность: одна validation-коллекция, одинаковые `inputs`, `training_populations` MA == M.
- Роль описательная: при CI ±0,0025 эффект размера H+ (+2 %, ≈ +0,0007) не различим.

**Гейт отправки MA** — механический; меток касается только пол по популярности. Команда `gate` даёт OK, если выполнены все пункты:
- leakcheck OK;
- `control` OK;
- все оценки MA конечны (`nonfinite_scores` = 0 во всех квитанциях);
- паритет не-NULL: у каждой колонки агента доля не-NULL при скоринге 09-23 лежит в `[0,5·min, 2·max]` долей шести сайдкаров;
- MAP port каждого MA ≥ 0,0056 — уровень популярности (`hm-pilot.md`, Popularity 0,00562780). Этот пол ловит только поломку. Реальный вред от лишних колонок лежит далеко выше: у M+58 0,02954 при M 0,03368 (`hm-report.md`).

Как читается результат гейта:
- Дев-MAP выше пола на отправку и на вердикт не влияет. Вердикт выносится только по правилу чтения Kaggle.
- Если гейт не пройден, сначала ищется техническая причина; исправление идёт по правилу отклонений.
- Если технической причины нет, MA не отправляется и записывается как «MA не прошла гейт: <пункт>».
- В обоих случаях агент не перезапускается ни в каком режиме, колонки не удаляются.

**Правило отказа.**
- Предложение прошло пробу 09-09, но падает на сайдкаре, скоринге или leakcheck: ключ вне множества, дубль ключа, тип или таймаут.
  - Колонки не удаляются, SQL не правится, команда падает целиком с id предложения.
  - Технические исправления без смены данных, SQL и колонок (по списку раздела 4) допускаются по правилу отклонений.
  - Если так исправить нельзя, MA не выполнена; это записывается как результат.
- К сроку собран только один final MA: отправляется он один, а чтение идёт по случаю «один файл MA».

**Отправка.** Отправляет координатор через залогиненный Kaggle CLI, только после явного «да» пользователя на эти посылки (D1). Лимит — 5 посылок в сутки Kaggle (UTC, сброс в 03:00 МСК). Поэтому 4 файла M/E уходят в одни сутки, 2 файла MA — в ближайшие сутки, где есть место. По каждому файлу записываются private и public.

**Чтение Kaggle** — по private:
- «MA выше M на обоих seeds», если `min(MA) > max(M)` и `mean(MA) − mean(M)` больше размаха внутри каждой руки;
- «MA ниже M на обоих seeds» — симметрично; иначе «не различено».
- Это описание, а не установленный эффект. Пусть эффекта нет и четыре private-счёта перестановочны. Тогда первое условие выполняется с вероятностью 1/6 в каждую сторону, оба условия вместе — около 0,11 в каждую сторону, около 0,22 в любую (симуляция, 2 млн повторов). Эффект размера H+ правило не разрешает («Сколько seeds»).
- Один файл MA: правило не применяется. Записываются числа и вердикт «один seed — не читается».
- E−M читается тем же правилом как калибровка (локально E−M ≈ −0,001). На вердикт MA он не влияет.
- Разница разбавлена клиентами на популярном фолбэке — он одинаков во всех руках.
- Если MA выше M, одно из объяснений — знание LLM о решениях соревнования (раздел 5).

**Сколько seeds.**
- GPU M2026 и M2027 на 09-16 разошлись на 0,002.
- Чтобы разрешить разность средних d при разбросе s на seed, нужно `n ≥ 8·s²/d²` seeds на руку (2 SE). При d = 0,0005 (+2 %) и s = 0,0005–0,001 это 8–32.
- Два seeds — разумный максимум до пятницы. Эффект размера H+ Kaggle не разрешит. Разрешит только крупный эффект вроде −0,004 у «M + все 58».
- Вердикт по двум seeds окончательный. Дополнительные seeds возможны только под новым prereg, потому что lock и CLI допускают только 2026 и 2027. С этими двумя они не объединяются.

## 5. Проверка утечек
`hm_agent_kaggle.py leakcheck --database DB --export E --agent-set S --collections $C/2020-08-19-c0q120 $C/2020-09-16-c0q120 --users 2000 --output artifacts/hm-agent/leakcheck`
- Для каждого якоря A:
  - `export_history(DB, tmp/cut, before=A)`;
  - ключи первых 2 000 клиентов коллекции в порядке `users.parquet`;
  - `agent_columns` по полному экспорту и по срезу;
  - сравнение каждой ячейки: два NULL равны, иначе `|x−y| ≤ 1e-9·(1+|x|)`.
- Инвариантность финального набора: 2 000 клиентов одним батчем против 4 × 500.
- Печатаются по якорю строки, колонки, расхождения и OK/LEAK; значения — никогда. Exit 0 только если всё OK. Запуск до первого сайдкара.

**Юнит-тесты на синтетике:**
- канарейка будущего: покупка в день A и позже с ценой 999 и уникальным товаром не видна ни одному запросу;
- `read_parquet` будущей партиции падает даже в обход `check_sql`;
- Python-переменная `secret` вызывающего кода недоступна;
- отклоняются запрещённый SQL, два оператора, литерал даты, `{A}` вне `DATE`, article-запрос с `cand`;
- `count(*) OVER()` по `cand` получает `invalid` по инвариантности.

**Не ловится:**
- статические атрибуты articles — снимок 2020 года, то же допущение, что у M23;
- знания LLM о соревновании H&M.
  - Промпт называет H&M и даты (1.5). Лучшие решения подбирались по public LB той же тестовой недели и опубликованы вместе со счётами.
  - Поэтому private LB — не свежий тест для выбора колонок агентом, и смещение работает в пользу MA.
  - Утечкой строк данных это не является; MA — «агент с предметным знанием».
  - Если MA выше M, это одно из объяснений, и прогон его не отделит.

## 6. Файловый план
Правок `hm_kaggle.py` и locked-модулей нет. Три агента работают с непересекающимися файлами.

**Агент A — `scripts/hm_agent_sandbox.py` + `tests/test_hm_agent_sandbox.py`**
```python
EXPORT_FORMAT = 'hm-agent-export-v1'; SET_FORMAT = 'hm-agent-set-v1'
LEVELS = {'pair': ('customer_id', 'article_id'), 'customer': ('customer_id',), 'article': ('article_id',)}
class ProposalError(ValueError): ...
def export_history(database, output, before=None, threads=4) -> dict                    # 1.1
def read_export(export) -> dict                                                         # проверка, identity
def check_sql(sql, level) -> None                                                       # 1.3
def sandbox(export, anchor, keys_path, threads=4, memory='4GB')                         # 1.2 -> DuckDBPyConnection
def run_proposal(con, proposal, anchor, timeout_s) -> 'DataFrame'                       # 1.4: ключи + DOUBLE
def agent_columns(export, anchor, keys, agent_set, *, threads=4, timeout_s=900,
                  cache=None, deadline=None) -> tuple['DataFrame', dict]                # ключи по порядку + S.columns;
                  # кеш article: ключ (export digest, якорь, id, sha256 SQL); cache=None — без кеша
def read_agent_set(path) -> dict; def set_digest(proposals) -> str
def prepare_probe(database, export, anchor, users, output, threads=3) -> dict
def evaluate_proposal(probe, export, proposal, prior_values, threads=3) -> tuple[dict, 'DataFrame | None']
# prior_values — список values-кадров принятых предложений в порядке приёма (ключи уровня + ag_*);
# ошибка SQL, таймаут, нехватка памяти DuckDB и нарушение контракта — ProposalError (предложение invalid);
# прочее исключение цикл считает техническим сбоем
```
CLI: `export`, `probe`. Тесты: синтетическая DuckDB по `hm_eda.SCHEMAS` из `tests.test_hm_kaggle.purchases()`; все юнит-тесты раздела 5; по тесту на каждое правило 1.4; инвариантность и `agent_columns` на трёх уровнях.

**Агент B — `scripts/hm_agent_loop.py` + `tests/test_hm_agent_loop.py`**
```python
def render_prompt(stats, registry, history, n, budget) -> str
def parse_reply(text) -> list[dict]                           # только текст `result`; первый JSON-список; поля и типы;
                                                              # пустой список или непустой ответ без списка — непарсимый ответ
def ask_llm(prompt, model, timeout=900) -> tuple[list, dict]  # claude -p в изоляции (раздел 2); init и стоимость в meta
def run_loop(export, probe, output, rounds=6, proposals=5, model='claude-opus-5-5', max_calls=12, threads=3,
             ask=ask_llm, evaluate=hm_agent_sandbox.evaluate_proposal) -> dict
def freeze(run_dir, output) -> dict                           # hm-agent-set.json
```
Выход: `artifacts/hm-agent/run-<id>/{prompt-rN.txt, reply-rN.json, log.jsonl, values/<id>.parquet, run.json}`. Строки данных модуль получает только через `evaluate`.
Тесты с фальшивыми `ask` и `evaluate`: лимит вызовов и отказ свыше 40; повтор при непарсимом ответе; порядок и digest заморозки; в промптах нет 64-hex и 10-значных id из пробы; все имена M23 на месте; бюджет. Для `ask_llm` — на фальшивом выводе subprocess: чистый init принимается; посторонний плагин, непустые tools или mcp_servers и отсутствие init дают сбой; в окружении нет ключей `CLAUDE*`, `ANTHROPIC*`, `MCP*`.

**Агент C — `scripts/hm_agent_kaggle.py` + `tests/test_hm_agent_kaggle.py`**
```python
def sidecar(database, export, agent_set, collection, output, threads=4, wall_seconds=3600) -> dict
def fit_ma(seed, train_paths, sidecars, prereg, output, validation_path=None, threads=8, wall_seconds=14400,
           deviations=None) -> dict
def load_agent_fit(path, deadline) -> dict   # как kaggle.load_fit: name, model, numeric, categorical, identity(+agent digest)
def agent_block(frame, columns) -> 'np.ndarray'  # float32, NaN для не конечных; общий для fit и score
def score_ma(database, export, agent_set, fits, control, output, chunk_users=15000, threads=4, wall_seconds=28800) -> dict
def control(agent_scores, kaggle_scores, model='M2026') -> dict
def leakcheck(database, export, agent_set, collections, output, users=2000) -> dict
def contrast(reference, alternative, prereg, output, deviations=None) -> dict
def gate(prereg, leakcheck, sidecars, agent_scores, kaggle_scores, port_fits, output, model='M2026',
         deviations=None) -> dict    # раздел 4; для пола по популярности печатается только OK/FAIL
```
Тесты на цепочке фикстуры `tests/test_hm_kaggle.py` (eda, коллекции 09-02/09-09/09-16, `small_recipe`) с рукописным набором из 3 предложений (pair, customer, article):
- сайдкары строятся;
- `kaggle.fit('M')` и `fit_ma` на одних коллекциях дают равные `training_populations`;
- скоринг с 1000 и с 7 клиентами на чанк даёт одинаковые top-12;
- `control` OK, `kaggle.assemble(..., 'MA2026')` проходит;
- leakcheck OK, а посаженная утечка (`t_dat <= A` через patch), в том числе в article-предложении, даёт LEAK;
- `fit_ma` без prereg отказывает;
- отклонения: несовпадение кода без записи — отказ; совпадение с последней записью — принято и записано; запись с чужим `prereg_sha256` или совпадение только со старой записью — отказ;
- правило отказа: ключ вне множества на одном якоре роняет `sidecar` с id предложения;
- `gate`: каждый пункт падает на подделанном входе (LEAK, DIFF, один NaN, колонка без не-NULL при скоринге, MAP ниже пола, `code` артефакта не совпадает ни с prereg, ни с одной записью отклонений, артефакт пересобранного шага несёт более старую запись), на цепочке фикстуры всё OK.

**Общие интерфейсы фиксируются до старта:** схема `hm-agent-set.json`, сигнатуры `agent_columns` и `agent_block`, семантика уровней и NULL, `export.json`, `manifest.json` сайдкара.
```json
{"format": "hm-agent-set-v1", "run": {"id", "model", "rounds", "proposals_per_round", "calls", "cost_usd"},
 "probe": {"anchor": "2020-09-09", "users": 5000, "export_digest"},
 "proposals": [{"id": "r1p1", "round": 1, "index": 1, "name", "idea", "level", "sql", "columns": ["ag_…"], "probe_seconds"}],
 "attempts": [{"id", "status", "error"}], "columns": ["ag_…"],
 "budget": {"pair_customer_seconds", "article_seconds"},
 "digest": "canonical_digest([[id, level, sql, columns], …])"}
```
`run.rounds` — число фактически выполненных раундов, `budget` — фактически использованные секунды пробы; лимиты записаны в `run.json` цикла.
**Координатор:** этот контракт, `docs/hm-agent.md` (runbook), prereg, интеграционный прогон всех тестов (включая `tests.test_hm_kaggle`), запуски.
**Ревью:** независимые read-only агенты — один на A+B (песочница, промпт без строк), другой на C (парность, plan/receipt, resume). Исправления перепроверяются по тем же замечаниям.

## 7. Критический путь
Данные скачаны 20.10 в 20:12–20:16 через Kaggle CLI (правила соревнования пользователь принял сам). Тяжёлая задача всегда одна. Время в таблице — МСК, по файлам отчётов.

**Цикл агента идёт только при свободной тяжёлой очереди.**
- Таймауты (20/60 с) и бюджет пробы (90/180 с) отсекают колонки навсегда, а повтора агента нет. Нагрузка сместила бы набор против MA.
- Для диагностики каждая запись `log.jsonl` хранит `os.getloadavg()` на момент оценки.
- Отказы по таймауту и бюджету перечисляются в итоге как ограничение.

| # | Тяжёлая очередь | Оценка | Факт или ожидание |
|---|---|---|---|
| 1 | verify, eda | — | готово 22:47 |
| 2 | collect × 6; сверка 09-16: 20000 / 1905 / 5962 / 894 | — | готово 22:50 |
| 3 | port M2026, E2026, M2027; сверка 100000 / 4233 | — | 22:51–23:08 |
| 4 | final M, E × 2 | — | 23:08–23:28 |
| 5 | `kaggle.score` M/E (35 чанков × 12 с) → assemble × 4 | — | 23:28–23:37, **4 файла** |
| 6 | export + probe — после ревью A | 0,25 ч | |
| 6а | цикл агента → freeze → prereg-коммит | 1–2 ч + 0,25 ч | при свободной очереди |
| 7 | плацебо REES46 (отдельная задача, `task1/runs/placebo-2026-10-21`) | 3,8–4,5 ч | |
| 8 | leakcheck, sidecar × 6 | 0,5–0,8 ч | |
| 9 | port MA2026, MA2027 → contrast | 0,5–1,5 ч | |
| 10 | final MA × 2 | 0,5–1,5 ч | |
| 11 | `score_ma` → control → gate → assemble × 2 | 1,8–4,3 ч | **2 файла** |

- Шаги 6 и 8–11 ждут кода и ревью: A нужен к шагу 6, B — сразу после него, C — к шагу 8.
- Плацебо и ветка MA делят одну тяжёлую очередь. Порядок шагов 6–8 решает готовность кода, на результат он не влияет. Фактический порядок записывается в журнал.
- Fits M/E на CPU (7 штук: port × 3, final × 4) заняли 282–334 с каждый; fit MA ожидается в 2,5–4 раза дольше. Скоринг M/E — 415 с счёта при пике RSS 8,94 ГБ. Оценка шага 11 уточняется по этим квитанциям: основное время там займёт агентский SQL.
- Запасные варианты:
  - падение ветки MA не задерживает 4 файла M/E;
  - если к пятнице 23.10, 12:00 MA не готова, MA записывается как невыполненная, а отправленными остаются только M и E.

## Вопросы до реализации (все решены, см. D1–D8)
1. Kaggle: кто и когда отправляет 6 файлов, каков дневной лимит late submissions. Если он меньше 6, отправка займёт два дня.
2. `age` и `postal_code`: по умолчанию исключены правилом hm-pilot. Включение — это смена правила и отдельная рука.
3. Port M2027 и MA2027 (+1–3 ч): по умолчанию да, запасной вариант — только 2026.
4. Seeds сверх 2026/2027 после пятницы: нужен новый lock. По умолчанию нет.
5. Рука «MA+58» (аналог H+: база + DFS + агент): по умолчанию нет — M+58 дал −0.0041. В шесть файлов не входит.
6. Место в Git для набора, prereg и журнала: по умолчанию `configs/datasets/` и `docs/hm-agent-run/`.
7. Модель LLM: `opus`, как в REES46, или закреплённый id. Бюджет — 12 вызовов из 40.
8. Промпт не скрывает, что данные — H&M, а LLM знает решения этого соревнования. По умолчанию это принимается и записывается как ограничение.

## Решения координатора (20.10.2026, до реализации)
1. **Kaggle.** Отправляет координатор через залогиненный CLI (`kaggle competitions submit`), каждую посылку — только после явного «да» пользователя. Лимит соревнования — 5 посылок в сутки (`maxDailySubmissions`, сутки UTC). Поэтому сначала идут четыре файла M/E в одни сутки, затем два MA в следующие. На четыре посылки M/E пользователь дал «да» 20.10; для MA нужно отдельное «да».
2. **`age`, `postal_code`** исключены по правилу hm-pilot.
3. **Port M2027 и MA2027** — да.
4. **Seeds** — только 2026/2027, и вердикт по ним окончательный. Дополнительные seeds возможны только под новым prereg, с этими двумя они не объединяются.
5. **Рука MA+58** не делается.
6. **Git** — по умолчанию: `configs/datasets/hm-agent-set.json`, `configs/datasets/hm-agent-prereg.json`, `configs/datasets/hm-agent-deviations.json`, `docs/hm-agent.md`, `docs/hm-agent-run/`.
7. **Модель LLM** — закреплённый id `claude-opus-5-5` (`--model claude-opus-5-5`); записывается в набор и prereg. Default `model` в `run_loop` — этот id, а не алиас.
8. **Знание LLM о соревновании H&M** принимается и записывается в prereg как ограничение.
9. **Обратная связь агенту** — только валидность и покрытие (раздел 2). В prereg записывается как отличие от REES46, где агент видел dNDCG.
10. **Threads.** Все fits (M, E, MA, port и final) — `--threads 8`; `kaggle.score` M/E и `score_ma` — `--threads 4`.
11. **T0** — вторник 20.10, 22:47: verify и eda готовы. Шаги 1–5 раздела 7 закончены в 23:37, пока пишется код A, B, C.
12. **После ревью контракта** (20.10, вечер):
    - гейт MA сделан механическим, с полом по популярности вместо 0,0300;
    - утверждение сужено до агентской половины H+;
    - добавлены правило отказа, правило отклонений и определение первого числа;
    - записаны вероятность ложного вердикта и случай одного файла MA, смещение от знаний LLM, изоляция `claude -p`, ключ кеша;
    - уточнены отправитель и лимит Kaggle, threads, критический путь.
