# Как воспроизвести задачу 1

Инструкция ведёт от сырых файлов REES46 до чисел [отчёта](task1-v2-report.md). Условие задачи — [task1-requirements.md](task1-requirements.md).

Все команды выполняются из корня репозитория на ветке `task1-v2`. Python — `.venv/bin/python`. Каталоги `data/` и `artifacts/` исключены из Git: их содержимое создают команды ниже. Тест уже запускался один раз, для проверки отчёта его повторять не нужно.

Под Git лежат итоги, на которые ссылается отчёт:
- `task1/runs/test.json` — результат теста, копия `artifacts/task1/v2/final/test.json`;
- `task1/runs/exp-runs.jsonl` — сводка всех прогонов на валидации;
- `task1/runs/final.json` — спецификация теста, замороженная до него;
- `task1/runs/dfs-select.json` — колонки, отобранные DFS;
- `task1/runs/agent_night20/` — лог, промпты и итог агента; `p5-feature.sql` — SQL принятого признака.

Порядок шагов:
1. окружение и данные;
2. выгрузка событий и таблицы дней;
3. проверка утечек;
4. таблицы дополнительных признаков: пакет из брейншторма, DFS, признак агента;
5. прогоны на валидации и числа половины B;
6. проверка финального пути на val. Тест — только один раз;
7. после теста: сетка, повтор на 2020, плацебо, перенос на H&M, Tinkoff и СберМаркет (раздел «После теста»);
8. совет агентов на REES46 2020, Tinkoff и СберМаркете и побочные проверки H6, H8–H11, H13 (раздел «Совет агентов»).

Термины. Якорь t — 00:00 UTC дня, от которого ранжируются товары следующих 24 часов. Train — якоря 15.10–7.11, val — 8–13.11, test — 18–28.11 (2019). Val делится по хешу `user_id` на половины A (выбор) и B (подтверждение). Песочница — отдельное подключение DuckDB для дополнительных признаков (`task1/extra.py`): SQL признака видит в нём только события до якоря и пользователей, активных за 48 часов до него.

## Что воспроизводится точно, а что нет

- **Таблицы дней.** У `row_number` и `arg_max` сборки есть tie-break ([спецификация признаков](task1-baseline-features.md), §1, п. 6). Исключение — бренд товара за день в `task1/data.py`, `arg_max(brand, event_time)`. На данных автора двух брендов с одинаковым временем последнего события нет ни в одном из 3 807 760 товаро-дней. Поэтому запросы, метки, кандидаты и ранги от запуска не зависят. Побитовое совпадение пересобранных таблиц с таблицами автора не проверялось.
- **Обучение.** На тех же таблицах с той же конфигурацией и зёрнами результат повторяется. База раунда агента — модель раунда без нового признака: конфигурация базы плюс признаки, принятые раньше. В раундах 1–5 принятых признаков ещё не было. На машине автора базы раундов 1–5 дали ту же NDCG@20 на A, что и прогон `q2_d8` той же конфигурации, до шестого знака: 0.151081. Метрики запросов `agent_night20_r5_base` и `q2_d8` совпадают на всей val.
- **Бутстрап** использует фиксированное зерно: 2000 повторов, зерно 2026. По тем же parquet CI повторяются точно.
- **Другая машина.** Совпадение до последнего знака на другом процессоре или ОС не проверялось.
- **LLM-часть агента недетерминирована.** Повторный запуск — новый эксперимент с другими предложениями. Принятый признак восстанавливается без LLM из закоммиченного SQL (раздел «Агент»). В этом SQL два `ROW_NUMBER` без tie-break по `product_id`: выбор пяти товаров пользователя и 30 соседей товара. При равных значениях выбор может отличаться, поэтому побитовое совпадение таблицы признака не гарантируется.

## Окружение

```bash
uv sync --locked
```

- Python 3.12 (`.python-version`; у автора 3.12.14).
- Версии зафиксированы в `pyproject.toml` и `uv.lock`: catboost 1.2.10, duckdb 1.5.6, pandas 3.0.6, numpy 2.5.4.
- Машина автора: Apple M3 Pro, 12 CPU, 36 ГБ памяти, macOS 26.3. На других машинах путь не проверялся.
- Потоки: сборка дней и CatBoost — 10, песочница — 8.
- Память. Пул обучения на train + val из `days6` — 16.6 млн строк, 9.3 ГБ, из `days` — 8.4 ГБ. Пик памяти процесса при чтении — 29.6 ГБ ([журнал экспериментов](task1-night-2026-10-20.md)). Меньший объём памяти не проверялся.
- Диск у автора (`du -sh`, в ГиБ): архивы 1.6 + 2.7, база DuckDB 4.3, выгрузка событий 3.8, `days` 3.7, `days6` 6.9, `extra` 1.5; прогоны и тест — десятки МиБ. Всего ≈25 ГиБ без временных файлов DuckDB.
- Агенту нужен CLI `claude` (Claude Code) с выполненным входом. Его вызовы платные.

## Данные

Откуда скачать архивы `2019-Oct.csv.gz` и `2019-Nov.csv.gz`, их размеры и SHA-256 — в [паспорте данных](data.md).

`task1.data` сверяет каждый архив с записью проверки `data/raw/<месяц>.download.json`. Эти записи исключены из Git вместе с данными. На новой машине их нужно создать. Программа читает из них только `sha256`, `compressed_bytes` и `source`; значения ниже взяты из паспорта данных. Существующие записи скрипт не перезаписывает.

```bash
mkdir -p data/raw data/processed
for m in 2019-Oct 2019-Nov; do
  curl --fail --location --continue-at - --output data/raw/$m.csv.gz https://data.rees46.com/datasets/marketplace/$m.csv.gz
done
.venv/bin/python - <<'EOF'
import json
from pathlib import Path

KNOWN = {
    '2019-Oct': (1741928540, '8ebca1ad741295297368f2cf0315e3f36853a1a11768fb16babf8c9b83838147'),
    '2019-Nov': (2890421023, '7d9932fdf2667f3d800655f55a623d7f71b22ff8d606da55bf93cfc307ebf213'),
}
for month, (size, sha) in KNOWN.items():
    path = Path(f'data/raw/{month}.download.json')
    if not path.exists():
        path.write_text(json.dumps({'source': f'https://data.rees46.com/datasets/marketplace/{month}.csv.gz',
                                    'compressed_bytes': size, 'sha256': sha}, indent=1) + '\n')
EOF
.venv/bin/python -m task1.data
```

Каталог `data/processed` нужен заранее: DuckDB не создаёт недостающие каталоги. `task1.data` создаёт `data/processed/rees46.duckdb` с таблицами:
- `events` — 109 820 004 события октября и ноября 2019 без полностью совпадающих строк;
- `pair_first` — первое касание и первая корзина или покупка каждой пары пользователь–товар;
- `item_static` — категория товара по первому событию;
- `item_brand_day` — бренд товара по дням;
- `ingest_metadata` — исходные файлы и их SHA-256.

Если база уже есть, команда не запустится: базу нужно удалить явно. Временные файлы DuckDB пишутся в `data/tmp/duckdb`.

## Выгрузка событий для песочницы

Через песочницу считаются пакет признаков из брейншторма, DFS и признаки агента. SQL признака видит в ней две таблицы: `hist` (события строго до якоря) и `active_users` (пользователи с событиями за 48 часов до якоря). Песочница читает не базу, а выгрузку событий по дням:

```bash
.venv/bin/python -m task1.extra --export-events
```

Команда пишет `artifacts/task1/v2/events_by_day/d=<дата>/*.parquet`: 61 день, 109 820 004 строки. У автора число строк сверено с базой.

## Таблицы дней

Таблица дня — один parquet на якорь: запросы, кандидаты, метки и признаки.

### 6 источников

```bash
.venv/bin/python -m task1.build --start 2019-10-15 --end 2019-11-13 --out artifacts/task1/v2/days6
.venv/bin/python -m task1.build --start 2019-11-18 --end 2019-11-28 --out artifacts/task1/v2/days6
```

Это база отчёта: 6 источников кандидатов, 80 признаков, 41 день — якоря train, val и теста. Дни 14–17.11 не якоря, их ничто не читает, и у автора они не собирались. Это дни распродажи: время и память их сборки не проверены.

### 4 источника

Таблицы `artifacts/task1/v2/days` (4 источника, 76 признаков) нужны базе на 4 источниках: очередям q1 и q6, ветке `base_4src` теста и эвристикам `task1.baseline`. Текущий `build.py` их не строит: источники с тех пор расширены. Их строит код коммита e875b84. Данные и артефакты не в Git, поэтому общие для всех коммитов. Окружение (`pyproject.toml`, `uv.lock`) и `task1/data.py` с e875b84 не менялись.

```bash
git status --short   # в отслеживаемых файлах не должно быть изменений
git switch --detach e875b84
.venv/bin/python -m task1.build --start 2019-10-15 --end 2019-11-13 --out artifacts/task1/v2/days
.venv/bin/python -m task1.build --start 2019-11-18 --end 2019-11-28 --out artifacts/task1/v2/days
git switch -
```

В коде e875b84 этот каталог и так стоит по умолчанию, здесь он задан явно.

## Проверка утечек

```bash
.venv/bin/python -m task1.leakcheck 2019-10-22 2019-11-11
```

Для каждого якоря t команда:
1. создаёт во временном каталоге базу только с событиями до t и заново считает по ней `pair_first`, `item_static` и `item_brand_day`;
2. строит день текущим `build.py` дважды: признаки из полной базы и из обрезанной; запросы и метки в обоих случаях — из полной;
3. сортирует обе таблицы по `(user_id, product_id)` и сравнивает. Форма и имена колонок должны совпасть. Дробные значения сравниваются с допуском 1e-9·(1 + |x|), остальные — точно; NULL равен NULL.

Итог по дню — `OK` или `LEAK` с числом расходящихся строк по колонкам; при утечке код выхода 1. Таблицы `days6` проверка не трогает. На сборке с 6 источниками она пройдена на 22.10 и 11.11 (коммит 2703f8d).

Песочница защищена не этой проверкой, а устройством: SQL признака не может прочитать события от якоря и позже. Описание — в начале `task1/extra.py`.

## Прогоны на валидации

Код экспериментов — `task1/exp.py`. Очередь — JSON-список конфигураций. Конфигурация — имя прогона и изменения поверх `exp.DEFAULT`: Logloss, 500 итераций, глубина 6, lr 0.08, l2 10, зерно 2026, 50 случайных негативов на запрос, `neg_seed` 0, 10 потоков.

```bash
.venv/bin/python -m task1.exp task1/runs/night-2026-10-20/q1.json
```

Модель обучается на train и ранжирует всех кандидатов val. Каждый прогон пишет:
- `artifacts/task1/v2/exp/<name>.parquet` — метрики каждого запроса val: `ndcg`, `recall`, `purchase_ndcg`, `purchase_recall` и половину `half` (A или B);
- строку в `artifacts/task1/v2/exp/runs.jsonl` — конфигурацию, число признаков и строк обучения, метрики половины A и время в `seconds` (подготовка, обучение, скоринг).

Печатаются и пишутся в журнал только метрики половины A. Половина B читается только через `exp.compare(..., on='B')` (следующий раздел). Исключение — первые 11 строк журнала (q1 и q2): они записаны до этого правила и содержат метрики всей val. Повтор имени перезаписывает parquet и добавляет строку в журнал. Без ключа `days` прогон читает `model.DAYS`: таблицы на 4 источниках в `artifacts/task1/v2/days`, если не задана переменная `TASK1_DAYS`.

`task1/runs/exp-runs.jsonl` — журнал автора под Git, 83 строки в том же порядке, абсолютный путь к корню репозитория заменён относительным. Строки 1–70 — прогоны до теста. Строки 71–83 добавлены коммитом 2c1e0ad: 13 прогонов сетки после теста (раздел «Сетка F0/F1/H/H+ и край настройки»). Прогоны плацебо `pl19_*` в журнал автора дописаны позже, в копию под Git не входят, `pl20_*` пишутся в `artifacts/task1/v2020/exp/runs.jsonl`. Выдержки из записей обоих — поле `fits` в `task1/runs/placebo-2026-10-21/result.json`. Так же исправлен путь к таблицам дней в `task1/runs/agent_night20/summary.json`; `log.jsonl` агента оставлен как записан. Три строки `smoke_agent_*` — проверка цикла агента на уменьшенных таблицах в `/tmp`. В отчёт они не входят.

Зёрна `(seed, neg_seed)`: s0 — (2026, 0), s1 — (7, 1), s2 — (11, 2).

Очереди лежат в `task1/runs/night-2026-10-20/`:

| Очередь | Что проверяет | Прогонов |
|---|---|---|
| `q1.json` | 6 источников против 4 при глубине 6: `q1_b6_s0`–`s2` на `days6`, `q1_b4_s0` и `q1_b4_s1` на `days` | 5 |
| `q2.json` | одна ось от `q1_b6_s0`: YetiRank, 100 негативов, трудные негативы, вес свежих дней (`half_life` 7 и 14), глубина 8, 1000 итераций с lr 0.05, l2 3 | 8 |
| `q3.json` | второе зерно глубины 8; 1000 итераций на глубине 8 и пакет из брейншторма на глубине 8 — по два зерна | 5 |
| `q4.json` | база + DFS top-20, два зерна | 2 |
| `q5.json` | абляция: база без одной группы признаков (`cf_`, `s_`, `i_`, `up_`, `uc_`, `ub_`, `u_`, `ui_`) | 8 |
| `q6.json` | база на 4 источниках, два зерна: повтор `q1_b4_*` | 2 |
| `q7.json` | база без `cf_` и `s_` вместе | 1 |

- `q1_b4_*` в журнале нет. Тогда они упали: код искал колонку трудных негативов, которой нет в `days`. Сейчас `exp._read` берёт запасную колонку. Те же конфигурации повторены в q6.
- q3 требует таблицы пакета из брейншторма (ниже), q4 — таблицы DFS (раздел «DFS»).
- `base.json` — не очередь, а конфигурация базы отчёта: `days6`, глубина 8. Её передают в `task1.dfs --select` и `task1.agent --config`.

Пакет из брейншторма перед q3. Его SQL написан по идеям брейншторма субагентов, вне цикла агента:

```bash
for n in hand_variant hand_cpshare; do
  mkdir -p artifacts/task1/v2/extra/$n
  cp task1/runs/night-2026-10-20/hand/$n.sql artifacts/task1/v2/extra/$n/feature.sql
done
.venv/bin/python -m task1.extra hand_variant hand_cpshare --splits train val
```

## Числа половины B в отчёте

Отчёт сравнивает ветки на половине B. `exp.compare(ref, new, on='B', metric=...)` принимает имя прогона или список прогонов. Для списка метрики запроса усредняются по прогонам: так в отчёте объединены два зерна. CI — парный бутстрап по запросам, разброс между зёрнами он не учитывает. Метрики покупок считаются только по запросам с целью-покупкой.

Нужны parquet двенадцати прогонов: `q1_b6_s0`, `q1_b6_s1`, `q2_d8`, `q3_d8_s1`, `q4_d8_dfs_s0`, `q4_d8_dfs_s1`, `q6_b4_s0`, `q6_b4_s1` и четырёх прогонов агента (раздел «Агент», путь без LLM). Первые восемь дают очереди q1–q4 и q6. Если нужны только эти числа, хватит короткой очереди с теми же конфигурациями; таблицы DFS для неё всё равно нужны:

```bash
cat > /tmp/b-queue.json <<'EOF'
[
 {"name": "q1_b6_s0", "days": "artifacts/task1/v2/days6"},
 {"name": "q1_b6_s1", "days": "artifacts/task1/v2/days6", "seed": 7, "neg_seed": 1},
 {"name": "q2_d8", "days": "artifacts/task1/v2/days6", "depth": 8},
 {"name": "q3_d8_s1", "days": "artifacts/task1/v2/days6", "depth": 8, "seed": 7, "neg_seed": 1},
 {"name": "q4_d8_dfs_s0", "days": "artifacts/task1/v2/days6", "depth": 8,
  "extra": ["dfs_p_top", "dfs_c_top", "dfs_b_top"]},
 {"name": "q4_d8_dfs_s1", "days": "artifacts/task1/v2/days6", "depth": 8, "seed": 7, "neg_seed": 1,
  "extra": ["dfs_p_top", "dfs_c_top", "dfs_b_top"]},
 {"name": "q6_b4_s0", "days": "artifacts/task1/v2/days"},
 {"name": "q6_b4_s1", "days": "artifacts/task1/v2/days", "seed": 7, "neg_seed": 1}
]
EOF
.venv/bin/python -m task1.exp /tmp/b-queue.json
```

Разности, таблица «Парные разности на B»:

```bash
.venv/bin/python - <<'EOF'
from task1.exp import compare

PAIRS = [
    ('6 источников против 4', ['q6_b4_s0', 'q6_b4_s1'], ['q1_b6_s0', 'q1_b6_s1']),
    ('глубина 8 против 6', ['q1_b6_s0', 'q1_b6_s1'], ['q2_d8', 'q3_d8_s1']),
    ('настроенная база против 4 источников', ['q6_b4_s0', 'q6_b4_s1'], ['q2_d8', 'q3_d8_s1']),
    ('DFS top-20 против базы', ['q2_d8', 'q3_d8_s1'], ['q4_d8_dfs_s0', 'q4_d8_dfs_s1']),
    ('агент (p5) против базы раунда', ['agent_night20_r5_base', 'agent_night20_r5_base2'],
     ['agent_night20_r5p5_cf_considered_seed_coview', 'agent_night20_r5p5_cf_considered_seed_coview_s2']),
]
for title, ref, new in PAIRS:
    out = []
    for metric in ('ndcg', 'purchase_ndcg'):
        c = compare(ref, new, on='B', metric=metric)
        out.append(f"{metric} {c['d']:+.5f} [{c['ci'][0]:+.5f}, {c['ci'][1]:+.5f}]")
    print(f'{title}: ' + '; '.join(out))
EOF
```

Вывод на данных автора:

```
6 источников против 4: ndcg +0.00313 [+0.00219, +0.00411]; purchase_ndcg +0.00244 [+0.00100, +0.00382]
глубина 8 против 6: ndcg +0.00098 [+0.00032, +0.00162]; purchase_ndcg +0.00109 [+0.00013, +0.00204]
настроенная база против 4 источников: ndcg +0.00411 [+0.00310, +0.00513]; purchase_ndcg +0.00353 [+0.00202, +0.00508]
DFS top-20 против базы: ndcg -0.00053 [-0.00122, +0.00016]; purchase_ndcg -0.00074 [-0.00183, +0.00037]
агент (p5) против базы раунда: ndcg +0.00037 [-0.00040, +0.00114]; purchase_ndcg +0.00001 [-0.00111, +0.00119]
```

Уровни метрик — таблица раздела «Результаты на валидации». Строки эвристик даёт `task1.baseline`:

```bash
.venv/bin/python -m task1.baseline
```

Он читает `days`: каталог по умолчанию `model.DAYS`, другой задаётся переменной `TASK1_DAYS`. Три эвристики ранжируют кандидатов этих таблиц, затем обучается прежняя база на 4 источниках (`full`). Метрики запросов пишутся в `artifacts/task1/v2/val/<имя>.parquet` без колонки половины, половина считается по `user_id` из `qid`:

```bash
.venv/bin/python - <<'EOF'
import duckdb
from task1.exp import half, metrics


def heuristic(name):
    m = duckdb.sql(f"SELECT * FROM 'artifacts/task1/v2/val/{name}.parquet'").df().set_index('qid')
    m['half'] = half(m.index.str.rsplit(':', n=1).str[1].astype('int64'))
    return m


ROWS = [
    ('популярность', heuristic('h_pop')),
    ('доля категории у пользователя', heuristic('h_user_category')),
    ('совместный просмотр', heuristic('h_coview')),
    ('база на 4 источниках', metrics(['q6_b4_s0', 'q6_b4_s1'])),
    ('6 источников, глубина 6', metrics(['q1_b6_s0', 'q1_b6_s1'])),
    ('база: 6 источников, глубина 8', metrics(['q2_d8', 'q3_d8_s1'])),
    ('база + DFS top-20', metrics(['q4_d8_dfs_s0', 'q4_d8_dfs_s1'])),
    ('база + признак агента', metrics(['agent_night20_r5p5_cf_considered_seed_coview',
                                       'agent_night20_r5p5_cf_considered_seed_coview_s2'])),
    ('база агента с теми же зёрнами', metrics(['agent_night20_r5_base', 'agent_night20_r5_base2'])),
]
for title, m in ROWS:
    b = m[m.half == 'B']
    print(f'{title}: запросов {len(b)}, NDCG@20 {b.ndcg.mean():.4f}, Recall@20 {b.recall.mean():.3f}, '
          f'NDCG@20 покупки {b.purchase_ndcg.mean():.4f}')
EOF
```

Вывод на данных автора:

```
популярность: запросов 19361, NDCG@20 0.0604, Recall@20 0.124, NDCG@20 покупки 0.0772
доля категории у пользователя: запросов 19361, NDCG@20 0.0739, Recall@20 0.154, NDCG@20 покупки 0.0857
совместный просмотр: запросов 19361, NDCG@20 0.1233, Recall@20 0.241, NDCG@20 покупки 0.1347
база на 4 источниках: запросов 19361, NDCG@20 0.1462, Recall@20 0.281, NDCG@20 покупки 0.1633
6 источников, глубина 6: запросов 19361, NDCG@20 0.1494, Recall@20 0.291, NDCG@20 покупки 0.1657
база: 6 источников, глубина 8: запросов 19361, NDCG@20 0.1503, Recall@20 0.292, NDCG@20 покупки 0.1668
база + DFS top-20: запросов 19361, NDCG@20 0.1498, Recall@20 0.292, NDCG@20 покупки 0.1661
база + признак агента: запросов 19361, NDCG@20 0.1508, Recall@20 0.293, NDCG@20 покупки 0.1667
база агента с теми же зёрнами: запросов 19361, NDCG@20 0.1504, Recall@20 0.292, NDCG@20 покупки 0.1667
```

## DFS

DFS — детерминированная сетка признаков: сущность (товар, его категория, бренд, пользователь) × окно (1, 3, 7, 14 дней) × тип события. Всего 128 колонок, считаются той же песочницей. Описание — в начале `task1/dfs.py`.

```bash
.venv/bin/python -m task1.dfs --compute
.venv/bin/python -m task1.dfs --materialize
.venv/bin/python -m task1.exp task1/runs/night-2026-10-20/q4.json
```

- `--compute` считает таблицы `dfs_p`, `dfs_c`, `dfs_b`, `dfs_u` на днях train и val.
- `--materialize` копирует колонки из закоммиченного `task1/runs/dfs-select.json` в таблицы `dfs_p_top`, `dfs_c_top` и `dfs_b_top`. Их читают q4 и ветка `dfs` теста.

Повтор самого отбора:

```bash
.venv/bin/python -m task1.dfs --select 20 --config "$(cat task1/runs/night-2026-10-20/base.json)"
git diff task1/runs/dfs-select.json
```

Отбор не читает val. Модель с конфигурацией базы, признаками базы и всеми колонками товара, категории и бренда обучается на якорях train до 3.11. Важность LossFunctionChange считается на якорях 4–7.11. Берутся 20 сгенерированных колонок с наибольшей положительной важностью. Колонки пользователя не отбираются: внутри запроса они постоянны и порядок кандидатов не меняют. У автора из 96 колонок отобраны 11 товарных, 8 брендовых и 1 категорийная.

Отбор сразу материализует таблицы `_top` и перезаписывает закоммиченный `dfs-select.json`, поэтому его стоит сравнить с версией в Git. `task1.final` не запустится, если список в `dfs-select.json` не совпадает с `dfs_selected` в `final.json`. Дни теста для DFS досчитывает `task1.final`.

## Агент

LLM-агент (`task1/agent.py`) по раундам предлагает SQL-признаки. Песочница считает каждый признак на днях train и val. `task1.exp` обучает модель с признаком и базу раунда и сравнивает их на половине A. Признак принимается, если на двух зёрнах нижняя граница 95% CI выше нуля, а прирост больше `--min-gain`. Второе зерно — `seed + 1` и `neg_seed + 1`, то есть (2027, 1). Из прошедших за раунд берётся лучший. Половину B и дни теста агент не читает.

### Запуск с LLM

Агент вызывает `claude -p <промпт> --model opus --output-format json --tools '' --strict-mcp-config` в пустом каталоге `/tmp/tlab-agent-llm`: без инструментов и MCP-серверов. Версия CLI и модель, на которую указывал алиас `opus`, в логе не записаны.

Повтор — с новым идентификатором прогона:

```bash
.venv/bin/python -m task1.agent --run agent_repro --config "$(cat task1/runs/night-2026-10-20/base.json)" \
  --rounds 6 --per-round 5 --max-llm-calls 6 --model opus --min-gain 0.0005
```

У автора было два запуска `--run agent_night20` с теми же аргументами. Первый — с `--config` базы, `--rounds 4 --max-llm-calls 5`. Второй продолжил его: `--rounds 2 --max-llm-calls 6`.

- `--config` по умолчанию — `days6` с глубиной 6, а база отчёта — глубина 8. Поэтому при первом запуске `--config` обязателен.
- Продолжение `--run <id>` берёт из `log.jsonl` историю попыток, конфигурацию и прокси (`--proxy`, у автора пустой).
- Остальные аргументы берутся только из командной строки, при продолжении их передают заново. Аргументы первого запуска записаны в первой строке лога, но не читаются. `--min-gain` по умолчанию 0.001, у автора 0.0005. `--max-llm-calls` — общий лимит вместе с уже сделанными вызовами, по умолчанию 15. `--rounds` — число новых раундов. Также `--per-round`, `--model`, `--threads`.
- Не продолжайте `agent_night20`: новые раунды допишутся в закоммиченную историю, а в его логе абсолютный путь к таблицам на машине автора.

Новый запуск пишет `task1/runs/<id>/` (`log.jsonl`, `prompt-r*.txt`, `summary.json`), таблицы признаков `artifacts/task1/v2/extra/<id>_r*p*_*` и прогоны `<id>_r*_base*`, `<id>_r*p*_*` в `artifacts/task1/v2/exp/`. Ответы LLM недетерминированы: повтор даст другие предложения, а не признаки `agent_night20`.

### Без LLM: принятый признак

SQL признака `agent_night20_r5p5_cf_considered_seed_coview` лежит в `task1/runs/agent_night20/p5-feature.sql`: дословно из `log.jsonl`, сверху комментарий.

```bash
n=agent_night20_r5p5_cf_considered_seed_coview
mkdir -p artifacts/task1/v2/extra/$n
cp task1/runs/agent_night20/p5-feature.sql artifacts/task1/v2/extra/$n/feature.sql
.venv/bin/python -m task1.extra $n --splits train val test
```

Дни теста досчитал бы и `task1.final`, а дни train и val ему нужны готовыми.

Четыре прогона раунда 5 с теми же именами, для таблиц B:

```bash
cat > /tmp/p5-queue.json <<'EOF'
[
 {"name": "agent_night20_r5_base", "days": "artifacts/task1/v2/days6", "depth": 8},
 {"name": "agent_night20_r5_base2", "days": "artifacts/task1/v2/days6", "depth": 8, "seed": 2027, "neg_seed": 1},
 {"name": "agent_night20_r5p5_cf_considered_seed_coview", "days": "artifacts/task1/v2/days6", "depth": 8,
  "extra": ["agent_night20_r5p5_cf_considered_seed_coview"]},
 {"name": "agent_night20_r5p5_cf_considered_seed_coview_s2", "days": "artifacts/task1/v2/days6", "depth": 8,
  "seed": 2027, "neg_seed": 1, "extra": ["agent_night20_r5p5_cf_considered_seed_coview"]}
]
EOF
.venv/bin/python -m task1.exp /tmp/p5-queue.json
```

`agent_night20_r5_base` повторяет конфигурацию `q2_d8`.

## Финальная проверка и тест

Спецификация — `task1/runs/final.json`. Три ветки заморожены до теста в коммите 6fe96b3, ветка агента добавлена в 01709dc. Ветки:
- `base` — `days6`, глубина 8; эталон сравнения;
- `base_4src` — `days`, глубина 6;
- `dfs` — база + DFS top-20;
- `agent` — база + принятый признак агента.

Зёрна — (2026, 0) и (7, 1).

Проверка всего пути без теста, сколько угодно раз:

```bash
.venv/bin/python -m task1.final --eval val
```

Каждая ветка обучается на train и ранжирует всю val. Результат — `artifacts/task1/v2/final/val.json` и `val_<ветка>.parquet`.

Тест:

```bash
.venv/bin/python -m task1.final --eval test
```

Для каждой ветки и зерна модель обучается на train + val (якоря 15.10–13.11, метки 13.11 кончаются 14.11 00:00) и ранжирует всех кандидатов 18–28.11. Метрики запроса усредняются по зёрнам. Каждая ветка сравнивается с `base` парным бутстрапом. Перед обучением ветки досчитываются недостающие дни теста её дополнительных признаков: признак агента — из `feature.sql`, DFS — пересчётом `dfs_p`, `dfs_c`, `dfs_b` и материализацией. Нужны готовыми: `days6` и `days`, выгрузка событий, дни train и val признака агента и таблиц DFS.

Защита:
- тест запускается только со спецификацией по умолчанию, без `--spec`;
- до любой работы команда пишет маркер `artifacts/task1/v2/final/test.started` и при его наличии не запускается. После сбоя маркер удаляют вручную, а метрики уже напечатанных веток тогда будут увидены второй раз;
- при ветке DFS список в `task1/runs/dfs-select.json` должен совпасть с `dfs_selected` в `final.json`.

Результат — `artifacts/task1/v2/final/test.json` и `test_<ветка>.parquet`. Поля `d_ndcg_vs_base` и `d_purchase_ndcg_vs_base` — разность «ветка минус база» и 95% CI. Копия под Git — `task1/runs/test.json`.

Тест запущен один раз, 20.10.2026. На новой машине маркера нет, и команда запустится. Для проверки отчёта повторять её не нужно: числа теста — в `task1/runs/test.json`, путь целиком проверяет `--eval val`.

## После теста

Ниже — пути к разделам отчёта после теста 2019. Одноразовые шаги уже выполнены: тест 2020, открытие holdout и final-модели переноса, посылки Kaggle H&M и Tinkoff. Повтор прочитал бы закрытые метки заново, поэтому числа отчёта берутся из названных файлов. LLM-агент платный и недетерминирован, поэтому путь везде идёт от закоммиченного SQL или замороженного набора.

### Сетка F0/F1/H/H+ и край настройки

Разделы отчёта «Заменяет ли автоматика ручные признаки» и «Край настройки», правила — [предрегистрация](../task1/runs/grid-2026-10-20/spec.md). Нужны `days6`, таблицы DFS после `task1.dfs --compute` и все 30 таблиц агента на днях train и val. SQL таблиц агента — в `log.jsonl`:

```bash
.venv/bin/python - > /tmp/agent-tables.txt <<'EOF'
import json
from pathlib import Path

P5 = 'agent_night20_r5p5_cf_considered_seed_coview'  # построен в разделе «Агент»
todo = []
for line in Path('task1/runs/agent_night20/log.jsonl').read_text().splitlines():
    r = json.loads(line)
    if 'sql' not in r or r['name'] == P5:
        continue
    sql, f = r['sql'].strip() + '\n', Path('artifacts/task1/v2/extra') / r['name'] / 'feature.sql'
    if not f.exists():
        todo.append((f, sql))
    elif f.read_text() != sql:
        raise SystemExit(f'{f} differs from log.jsonl')
for f, sql in todo:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(sql)
    print(f.parent.name)
EOF
.venv/bin/python -m task1.extra $(cat /tmp/agent-tables.txt) --splits train val
.venv/bin/python -m task1.exp task1/runs/grid-2026-10-20/check.json
.venv/bin/python -m task1.exp task1/runs/grid-2026-10-20/grid.json
.venv/bin/python -m task1.posthoc
git diff task1/runs/grid-2026-10-20/result.json
```

- Скрипт пишет `feature.sql` только у таблиц, которых ещё нет. Таблица с `feature.sql`, но без parquet дней, им пропускается молча, и `task1.exp` потом остановится на отсутствующих днях: такие таблицы добавьте в список `task1.extra` вручную. Если на месте другой SQL, он останавливается до записи. `task1.extra` перезаписывает parquet дней всех перечисленных таблиц. Пустой список значит, что все таблицы уже есть; тогда `task1.extra` откажет, и строку можно пропустить.
- `check.json` — `grid_check_q2_d8`: проверка, что новый стенд повторяет `q2_d8`. `grid.json` — 12 прогонов: край `grid_d10_s0` и `grid_yeti8_s0`, по два зерна F0, F1, H+, F1-DFS и F1-агент. Ветку H дают готовые `q2_d8` и `q3_d8_s1`.
- `task1.posthoc` перезаписывает закоммиченный `result.json`, отсюда `git diff`. Если diff не пуст, оставьте свой файл до плацебо, а после него верните закоммиченный: `git checkout -- task1/runs/grid-2026-10-20/result.json`. Причина: `read` плацебо сверяет H+ − H своих прогонов 2019 с ним. Край не прошёл порог на A, поэтому очередь второго зерна `edge2.json` не создавалась.
- Совпадение пересчитанных таблиц агента с таблицами автора не проверялось. У p5 побитовое совпадение не гарантируется (раздел «Что воспроизводится точно, а что нет»).

### Повтор на январе–феврале 2020

Правила и замороженные входы — [спецификация](../task1/runs/replication-2020/spec.md) и `spec.json`. `task1.replicate` требует квитанции скачивания со `status: verified` и SHA-256 из `spec.json`:

```bash
mkdir -p data/raw2020
for m in 2020-Jan 2020-Feb; do
  curl --fail --location --continue-at - --output data/raw2020/$m.csv.gz https://data.rees46.com/datasets/marketplace/$m.csv.gz
done
.venv/bin/python - <<'EOF'
import hashlib
import json
from pathlib import Path

for name, f in json.loads(Path('task1/runs/replication-2020/spec.json').read_text())['data'].items():
    path, h = Path('data/raw2020') / name, hashlib.sha256()
    with path.open('rb') as s:
        for block in iter(lambda: s.read(1 << 20), b''):
            h.update(block)
    ok = h.hexdigest() == f['sha256'] and path.stat().st_size == f['compressed_bytes']
    receipt = path.with_name(name.replace('.csv.gz', '.download.json'))
    if ok and not receipt.exists():
        receipt.write_text(json.dumps(f | {'status': 'verified'}, indent=1) + '\n')
    print(name, 'verified' if ok else 'MISMATCH')
EOF
```

Дальше идут по порядку команды раздела [«Как воспроизвести»](../task1/runs/replication-2020/spec.md#как-воспроизвести) кроме последней:
- импорт;
- выгрузка событий;
- дни на 6 и 4 источниках; вывод сборки дней теста уходит в `artifacts/task1/v2020/sealed/` и не читается;
- `leakcheck`;
- `--prepare`, `--rehearse`, `--eval val` с флагами из спецификации.

`--eval test` не запускайте: тест открыт один раз, 20.10. Его журнал и числа отчёта — `task1/runs/replication-2020/test.started` и `test.json`. Защита смотрит на `artifacts/task1/v2020/replication/`, а не на Git: на новой машине команда запустится.

### Плацебо

Раздел «Плацебо и состав прироста H+». Команды — [«Порядок и команды»](../task1/runs/placebo-2026-10-21/spec.md#порядок-и-команды): тесты, очередь 2019, очередь 2020 с `TASK1_PERIOD=2020`. Входы — таблицы сетки 2019 и таблицы 2020 после `--prepare`. `run` и `read` не запускаются, пока код плацебо не закоммичен. `read` сравнивает новый итог с имеющимся `result.json` целиком, вместе с временем, коммитом и памятью прогонов и версиями библиотек. На новых прогонах он остановится. Поэтому `read` — так:

```bash
mv task1/runs/placebo-2026-10-21/result.json /tmp/placebo-result-git.json
.venv/bin/python -m task1.placebo read
.venv/bin/python - <<'EOF'
import json

new = json.load(open('task1/runs/placebo-2026-10-21/result.json'))
old = json.load(open('/tmp/placebo-result-git.json'))
for k in ('2019', '2020', 'claim'):
    print(k, 'совпадает' if new[k] == old[k] else 'расходится')
EOF
git checkout -- task1/runs/placebo-2026-10-21/result.json
```

### Перенос на H&M

Отчёт, [Перенос на другие наборы](task1-v2-report.md#перенос-на-другие-наборы), H&M.
1. M23 и E46 — [hm-kaggle.md](hm-kaggle.md), разделы 0–8, с двумя поправками к командам: в §5–6 `--threads 8`, как у всех fits автора (`thread_count` входит в identity fit, и с 4 потоками `ma contrast` откажет «not paired»); в §5 ещё и `--seed 2027`, потому что port `M2027` нужен шагу 10 hm-agent и плацебо MA. Скачивание требует принятых правил соревнования и токена пользователя в `~/.kaggle/kaggle.json`.
2. Рука MA — [hm-agent.md](hm-agent.md). Без LLM: шаги 0–1, затем 7–15 по закоммиченным `configs/datasets/hm-agent-set.json` и `hm-agent-prereg.json`. Шаги 2–4 дали бы новый набор: завершённый прогон агента не повторяется, `freeze` набор не перезаписывает.
3. Плацебо MA — блок [«Команды»](hm-ma-placebo.md#команды). Его последнюю строку `cp … docs/hm-ma-placebo-result.json` замените на `diff "$A/placebo/result.json" docs/hm-ma-placebo-result.json`: `cp` перезаписал бы закоммиченный итог.

Файлы заново не отправляйте. Gzip детерминирован, поэтому достаточно сравнить SHA-256 собранных файлов с таблицами [hm-kaggle.md](hm-kaggle.md), раздел 9, и [hm-agent.md](hm-agent.md), «Результаты 21.10.2026»; там же счёт Kaggle. Квитанции сборки — `artifacts/hm-kaggle/submissions/{M,E}{2026,2027}.json` и `artifacts/hm-agent/submissions/MA{2026,2027}.json`, вне Git.

### Перенос на Tinkoff и СберМаркет

Отчёт, [Перенос на другие наборы](task1-v2-report.md#перенос-на-другие-наборы), Tinkoff и СберМаркет. Порядок — [контракт, §8](xfer-design.md#8-порядок-и-ресурсы), якоря ролей — §2 документов [Tinkoff](xfer-tinkoff-design.md) и [СберМаркета](xfer-sber-design.md). Запуск — `.venv/bin/python -I scripts/<модуль>.py <команда>`; аргументы — `--help` команды. `xfer_agent.py` и `xfer_model.py` требуют `--dataset tinkoff` или `--dataset sber`. Адаптер набора — `xfer_tinkoff.py` или `xfer_sber.py`.

Порядок на машине автора:
1. Адаптер `load` из `data/raw-tinkoff-kaggle/` или `data/raw-sbermarket-kaggle/`.
2. Адаптер `collect --role train|val --anchor --base --output` по начальной базе.
3. `xfer_model.py fit --base-dev --base --output`: итерации базы, затем заморозка `base.json`.
4. Пересборка train и val из `base.json`.
5. `xfer_agent.py export`, адаптер `collect --role probe`, `xfer_agent.py probe`, `run` (LLM, пишет `artifacts/xfer/<x>/run/run-<id>/`), `freeze`. `freeze` пишет `configs/datasets/xfer-<x>-set.json` с `audit: null`. Поле `audit` после независимого аудита SQL заполняется вручную, команды для этого нет; без него `sidecar` откажет. Затем `xfer_model.py prereg`.
6. Адаптер `collect --role holdout`: метки уходят в `sealed/`, в stdout их нет.
7. `xfer_agent.py leakcheck`, `sidecar --collection` на каждую коллекцию.
8. `xfer_model.py fit --series dev --arm B|BA|BApl --seed 2026|2027`, `contrast`.
9. `fit --series holdout`, `gate --stage 1 --leakcheck`.
10. После «да» пользователя (цитата — в квитанции открытия) `holdout-open --gate --quote`, затем `holdout`.
11. Адаптер `collect --role kaggle`, сайдкар, `fit --series final`, `score`: гейт 2 и сборка файлов прошедших рук.
12. Посылки — только пользователем, его учётными данными, после «да» на конкретные файлы; затем `reading --private`.

Одноразовые шаги — `holdout-open`, `holdout` (обе отказывают, если квитанция уже закоммичена) и `fit --series final`: он учится на закрытых метках holdout.

**Квитанция скачивания.** `load` требует `kaggle-verify.json` рядом с CSV, но ни одна команда репозитория его не пишет. Форматы:
- Tinkoff (`xfer_tinkoff.load`): `{"status": "complete", "files": [{"name", "size", "sha256"}, …]}` с `data_train.csv`, `test_users.csv` и `baseline.csv`.
- СберМаркет (`xfer_sber._verify_entries`, `load`): `{"files": [{"name", "sha256"}, …]}` со всеми CSV под путями архива. Поле `matches`, если есть, должно быть `true`. Список `sbermarket_tab_2_*/tab_2_products_*.csv` должен совпасть с диском.

Самописная квитанция удостоверяет только собственную загрузку читателя. Полных хешей файлов автора под Git нет, у Tinkoff в §0 документа набора — только их начала.

**На клоне** `base.json`, набор и prereg уже в Git. `base.json` и `docs/xfer-<x>-run/` — закоммиченные вручную копии.
- Шаг 3 не нужен: train и val собираются сразу с `--base configs/datasets/xfer-<x>-base.json`.
- Из шага 5 — только `export`. `probe`, `run`, `freeze` и `prereg` не запускайте: `run` — новый платный прогон LLM, `prereg` откажет, потому что файл уже есть.
- Holdout-коллекцию клон не соберёт: закоммиченная квитанция открытия закрывает окно `collect-holdout` (`xfer_common.holdout_window_open`). Поэтому `leakcheck`, holdout-модели, гейты и final на клоне не повторяются.
- Остаются dev-часть: train и val, их сайдкары, dev-модели, `contrast`. Коллекцию kaggle и её сайдкар клон собрать может: их окно открывает закоммиченная квитанция результата.

**Где числа отчёта.** Holdout и вердикты — `configs/datasets/xfer-<x>-holdout.json`, рядом `xfer-<x>-holdout-open.json` и `xfer-<x>-deviations.json`. Пути гейтов и сайдкаров — таблицы «Цепочка» в [xfer-tinkoff.md](xfer-tinkoff.md) и [xfer-sber.md](xfer-sber.md).

Посылки Tinkoff, public и private — `docs/xfer-tinkoff-run/kaggle-submissions.json`. СберМаркет на Kaggle ничего не отправлял, статус — в `docs/xfer-sber-run/kaggle-submissions.json`:
- BA и BApl не прошли гейт 2;
- B2026 и B2027 собраны, но не отправлены: ждут «да»;
- чтение Kaggle не вычислено.

Post-hoc СберМаркета читает dev-модели, коллекции `val-2020-08-19` и `kaggle-2020-09-17` и их сайдкары:

```bash
.venv/bin/python -I docs/xfer-sber-run/posthoc_recency.py > /tmp/posthoc-recency.json
diff /tmp/posthoc-recency.json docs/xfer-sber-run/posthoc-recency.json
```

У post-hoc Tinkoff скрипта в репозитории нет, его числа есть только в `xfer-tinkoff.md`.

## Совет агентов

Разделы отчёта: [«Совет агентов над H+ (REES46 2020): первая проверка»](task1-v2-report.md#совет-агентов-над-h-rees46-2020-первая-проверка) и [«Совет агентов на Tinkoff и СберМаркете: повторный тест»](task1-v2-report.md#совет-агентов-на-tinkoff-и-сбермаркете-повторный-тест). Правила — контракты `council/runs/rees46-2020/contract.md` и `council/runs/xfer/contract.md`. Порядок ночи 22.10 с критериями готовности — `council/runs/night/2026-10-22-plan.md`. Совет идёт после повтора 2020 и переноса и читает уже открытые тесты повторно.

Порядок:
1. prereg-0: проверка пути, шум, гейт мощности;
2. волна карточек, критика, куратор;
3. compute — таблицы совета;
4. план: 48 подгонок, `analyze`, `selection.json`;
5. C_val — только REES46;
6. после «да» владельца: маркер теста, очередь C_test, чтение.

### Что воспроизводится без LLM, а что нет

- **Вызовы Opus не повторяются.** Роли совета — `claude -p <промпт> --model opus --output-format json --tools '' --strict-mcp-config` из пустого каталога: `/tmp/tlab-council-llm` у REES46, `/tmp/tlab-council-llm-a` или `-b` у переноса. Через LLM идут стадии `reference` (с одним вызовом `reference-fix` на упавшие предложения), `wave1`, `cross` и `authors`. Их итоги под Git: `reference-rb<k>.json`, `cards-wave1.json`, `critiques.json`, `cards-final.json`, промпты `prompts/`, ответы `replies/`, журнал `llm.jsonl` с ценой вызовов. Стадии возобновляются по своему файлу: записанное второй запуск у LLM не спрашивает. На клоне они вернут закоммиченное без вызовов. Запуск в чистом каталоге — новый эксперимент.
- **Промпты REES46.** `council.tests.test_golden_rees46` пересобирает все 18 промптов `llm.jsonl` из сохранённых входов и прогоняет их через `council.llm.ask` с подменённым `claude -p`. Байт в байт совпадают 10 — `cross` (6) и `authors` (4). Восемь вызовов `reference`, `reference-fix` и `wave1` шли до правок ревью (отклонение 13 в `prereg-0.md`). В текущих шаблонах есть список слов, которые отвергает песочница; без этого блока совпадают и они. Тест закрепляет и расхождение, и его причину.
- **Курация REES46.** Тот же тест пересобирает `curation.json` из `cards-final.json`, `probes.json` и `critiques.json` байт в байт. `council.tests.test_xfer_curate` проверяет то же для кода переноса с правилами REES46. Своего эталона курации у Tinkoff и СберМаркета нет.
- Обоим тестам нужен кэш проб `artifacts/task1/v2020/council/probes/` (вне Git). Подтест без нужной записи пропускается с названной причиной. `test_golden_rees46` ещё читает схемы parquet `days6` и 34 таблиц H+ (`agents.context()`). Значит, нужны кэш проб и таблицы 2020 после `--prepare`.

```bash
TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_golden_rees46 -v
TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_xfer_curate -v
```

- **Без LLM, кодом:** пробы (`evidence`), `prereg1`, курирование, `compute`, сборка плана, подгонки, `analyze`, выбор, C_val и C_test. Их входы — закоммиченные карточки. Совпадение пересчитанных подгонок с подгонками автора не проверялось.
- **Однократные чтения.** Брокер — единственный читатель меток. Каждое чтение он пишет в закоммиченный `reads.jsonl` и сверяется с ним.
  - REES46: второй `noise_explore` и второй `c_val` отказывают. На клоне откажет только `start_test()`: маркер `test.started` лежит под Git. Подгонкам теста нужен лишь этот маркер. У `c_test` нет ни счётчика (`once` стоит только у `noise_explore` и `c_val`), ни сохранённого чтения. Поэтому подгонки теста и `read-test` на клоне пройдут и перечитают метки. Защищает только правило: не запускать.
  - Перенос: маркер — запись `test.started` в `reads.jsonl`, второй `start-test` отказывает. `read-test` берёт сохранённое чтение `artifacts/council/xfer-<x>/test-read-<sha>.parquet`. Если есть запись `c_test`, а файла нет, он останавливается. Метки C_test — holdout-коллекция, а её клон не соберёт (раздел «Перенос на Tinkoff и СберМаркет»).

Сверка чисел отчёта с файлами совета — без данных и без LLM:

```bash
.venv/bin/python -m council.report rees46 --check
.venv/bin/python -m council.report tinkoff --check
.venv/bin/python -m council.report sber --check
```

- Каждый блок `<!-- report:<набор>:<таблица> -->` отчёта сравнивается с таблицей, построенной сейчас: числа, метки ожидания и закрытый словарь вердиктов. При расхождении — diff и код выхода 1.
- `--dry` перечисляет найденные и недостающие входы.
- Блок `report:rees46:costs` читает журнал подгонок `artifacts/task1/v2020/council/fits/runs.jsonl`, он вне Git. По коду на клоне без этого журнала время и пик в блоке не построятся, и `--check` по `rees46` разойдётся. Сверка `tinkoff` и `sber` читает только файлы под Git.
- Описательное раскрытие без новых чтений меток (H2, H3, H1', H14): `.venv/bin/python -m council.reveal <набор>`. С `--write` оно пишет `reveal.json`.

### Тяжёлая полоса

- Тяжёлый шаг — подгонка совета, `compute`, проба памяти, побочные H6, H8–H11. Одновременно идёт только один. Рядом допустимы вызовы LLM и правка кода, но не пробы, DuckDB и полный набор тестов.
- Пики у автора, машина 36 ГБ:
  - проверка пути REES46 (`full_val`) — 21.0 ГБ (`prereg-0.md`);
  - проба памяти `full_test` — Hrp 24.0 ГБ, ALL_P 25.8 ГБ (`memory.jsonl`);
  - H9–H11 — ≈24–26 ГБ по оценке prereg.
- Очередь и `compute` переноса, H6, H8 и H9–H11 держат `/tmp/tlab-heavy.lock` и ждут процессов REES46. `council.queue` замок не берёт. Поэтому перед каждым тяжёлым шагом REES46 нужна проверка:

```bash
.venv/bin/python -c "from council.xfer.queue import lock_holder; print(lock_holder())" \
 && ! pgrep -fl '[c]ouncil/xfer/run.py.*(queue|compute|fit-one)|[c]ouncil\.(fit|queue|memory)|[c]ouncil[./]side|[c]ouncil\.agents.*compute|scripts[./]xfer_'
```

  Ожидается `None` и пустой `pgrep`. Шаблон шире проверки из плана ночи: в нём ещё `compute` REES46 и скрипты `scripts/xfer_*`, как в `FOREIGN` из `council/xfer/queue.py`.
- Гейт проб есть только у переноса и у H13. Там проба — лёгкий шаг: 4 потока, DuckDB 4 ГБ, гейт перед каждой пробой. Она идёт рядом с тяжёлым шагом, только если его записанный пик не выше 20 ГБ (`PEAK_LIMIT_GB`). Рядом с подгонками REES46 `full_val` и `full_test`, `council.memory` и `compute` она не идёт.
- У проб REES46 гейта нет. Их делают `council.agents reference`, `evidence` и `authors`, по умолчанию с `--threads 8`. Запускайте их только при пустой тяжёлой полосе.
- Очередь переноса вытесняется так: `kill -TERM <PID родителя>`. Дочерний `fit-one` дописывает запись и отпускает замок. Повторный `queue <NAME>` пропускает готовые подгонки. Очередь REES46 тоже пропускает подгонку с файлом и записью той же спецификации.
- Журналы пишутся через `> /tmp/tlab-<имя>.log 2>&1`, без пайпа. На PID тяжёлого шага — `caffeinate -i -w <PID> &`.

### REES46 2020

Нужны `TASK1_PERIOD=2020`, таблицы 2020 после `--prepare`: `days6` и 34 таблицы H+, список — `council/roles.py`. Ещё нужен прогон плацебо `pl20_Hp_s0`: с ним сверяется путь. Файлы совета лежат в `council/runs/rees46-2020/` под Git. Подгонки, кэш проб и сохранённое чтение C_val — в `artifacts/task1/v2020/council/`.

**1. prereg-0.** Отдельной команды нет. `prereg-0.json` и `prereg-0.md` впервые записаны в коммите 3c17c9f, позже их правили 6591a6f и a4bb59c. Записаны они кодом `council.fit`, `council.queue`, `council.broker` и `council.design`:
- подгонка пути `path_Hr_full_val_s0` (`council.fit.path_spec()`) и `broker.path_check` против `pl20_Hp_s0`;
- две подгонки шума из `queue-noise.json` и единственное чтение `broker.noise_explore`;
- `design.rehearse` и гейт мощности. Гейт не пройден (0.52 < 0.8), поэтому SEL = ALL_P по построению.

На клоне повторяются подгонка и сверка пути; `noise_explore` откажет. Подгонка пути нужна и C_val: это рука H+r на зерне 0.

```bash
TASK1_PERIOD=2020 .venv/bin/python -c "import json; from council.fit import path_spec; print(json.dumps([path_spec()]))" > /tmp/council-path.json
TASK1_PERIOD=2020 .venv/bin/python -m council.queue /tmp/council-path.json
TASK1_PERIOD=2020 .venv/bin/python -c "from council import broker; print(broker.path_check('path_Hr_full_val_s0'))"
```

`path_check` печатает только наибольшие разности по метрикам и дописывает строку в `reads.jsonl`.

**2–3. Волна, критика, куратор, compute.**

```bash
TASK1_PERIOD=2020 .venv/bin/python -m council.agents reference --k 1
TASK1_PERIOD=2020 .venv/bin/python -m council.agents reference --k 2
TASK1_PERIOD=2020 .venv/bin/python -m council.agents wave1
TASK1_PERIOD=2020 .venv/bin/python -m council.agents evidence
TASK1_PERIOD=2020 .venv/bin/python -m council.agents cross
TASK1_PERIOD=2020 .venv/bin/python -m council.agents authors
TASK1_PERIOD=2020 .venv/bin/python -m council.agents prereg1
TASK1_PERIOD=2020 .venv/bin/python -m council.agents curate
TASK1_PERIOD=2020 .venv/bin/python -m council.agents compute
```

- `reference`, `wave1`, `cross` и `authors` вызывают Opus. `authors` заново измеряет переписанные карточки.
- `evidence` измеряет карточки без исходов. Уже измеренную версию карточки он не перемеряет.
- `prereg1` записывает хеши SQL, знаки и страты.
- `curate` — код без исходов. Если `curation.json` уже есть, он возвращается как есть; байты проверяет эталонный тест выше.
- `compute` — тяжёлый шаг: таблицы семейств, близнецов и оставленных Rb на всех днях train, val и test.

**4. План и выбор.**

```bash
TASK1_PERIOD=2020 .venv/bin/python -m council.plan build
TASK1_PERIOD=2020 .venv/bin/python -m council.queue council/runs/rees46-2020/queue-plan.json
TASK1_PERIOD=2020 .venv/bin/python -m council.plan analyze
git diff council/runs/rees46-2020/
```

- `build` пишет `prereg-2.json` и `queue-plan.json` из `curation.json`: 48 подгонок плана Плакетта–Бёрмана, T_fit → S0, половина B.
- `analyze` читает S0-select через `broker.y_select`, такое чтение допускается сколько угодно раз. Он пишет `plan-result.json` и `selection.json`.
- Все команды `council.plan` пишут через `_save` (`council/plan.py`) — простую запись без проверки содержимого. Без отказа перезаписываются закоммиченные `prereg-2.json` и `queue-plan.json` (`build`), `plan-result.json` и `selection.json` (`analyze`), `queue-cval.json` (`cval`), `val.json` (`read-val`), `queue-test.json` (`ctest`) и `test.json` (`read-test`). Поэтому после каждой нужен `git diff`.
- У автора `selection.json` закоммичен до первой подгонки C_val. Без закоммиченного выбора `c_val` и `start_test()` откажут.

**5. C_val.**

```bash
TASK1_PERIOD=2020 .venv/bin/python -m council.plan cval
TASK1_PERIOD=2020 .venv/bin/python -m council.queue council/runs/rees46-2020/queue-cval.json
TASK1_PERIOD=2020 .venv/bin/python -m council.plan read-val
TASK1_PERIOD=2020 .venv/bin/python -m council.memory --arm ALLP
```

- `queue-cval.json` — 9 подгонок train → val:
  - H+r на зерне 1;
  - H+r⁺ (`Hrp`), ALL_P и рука-близнец на двух зёрнах;
  - Rb1 и Rb2 на одном.
- `read-val` делает одно чтение `broker.c_val` и пишет `val.json`. Само чтение сохраняется в `artifacts/task1/v2020/council/cval-read.parquet` и переиспользуется. Поэтому при сохранённом чтении повтор `read-val` молча перезаписывает закоммиченный `val.json`. На клоне `c_val` откажет: запись о чтении уже есть в `reads.jsonl`.
- `council.memory` обучает руку в рецепте `full_test` без скоринга. Дни теста он не читает и дописывает пик в `memory.jsonl`. У автора проба памяти Hrp выполнена 21.10, ALL_P — 22.10.

**6. C_test** — только после «да» владельца. В `council/runs/rees46-2020/test-approved.md` записывается строка `approved: <дословная цитата с «да»>`, затем:

```bash
TASK1_PERIOD=2020 .venv/bin/python -m council.plan ctest
TASK1_PERIOD=2020 .venv/bin/python -c "from council import broker; print(broker.start_test())"
TASK1_PERIOD=2020 .venv/bin/python -m council.queue council/runs/rees46-2020/queue-test.json
TASK1_PERIOD=2020 .venv/bin/python -m council.plan read-test
```

- `queue-test.json` — 10 подгонок train + val → 14–29.02: H+r⁺ и ALL_P на четырёх зёрнах, H+r на двух.
- `start_test()` проверяет цитату и то, что `selection.json` закоммичен и побайтно совпадает с выбором, с которым читался C_val. Затем пишет `test.started`. Подгонки теста без маркера отказывают.
- `read-test` пишет `test.json`: H1 (SEL против H+r⁺ по четырём зёрнам) и контрасты. Они считаются на основных днях без 27–28.02 и на всех 16.
- На клоне шаг технически повторим: маркер под Git, откажет только `start_test()`. У `broker.c_test` нет `once`: каждый вызов снова читает метки теста и лишь дописывает строку в `reads.jsonl`. `read-test` вызывает его дважды (основные дни и все 16) и перезаписывает `test.json`. Не запускайте (п. «Однократные чтения» выше).

### Tinkoff и СберМаркет

Нужна dev-часть переноса из раздела «Перенос на Tinkoff и СберМаркет». Подгонка совета сверяет строки обучения с отчётом подгонки `BA2026` той же серии переноса. Проверка пути сравнивает с `dev/BA2026` и `holdout/BA2026`.

Запуск — `.venv/bin/python -I council/xfer/run.py --dataset tinkoff|sber <стадия>`, из корня, один набор на процесс:
- `-I` обязателен: без него `council/xfer/queue.py` заслонит стандартный модуль `queue`.
- `TASK1_PERIOD` ставится в 2020 сам.
- `info` печатает якоря, пути и code identity против prereg. `stages` выводит список стадий.
- Файлы совета лежат в `council/runs/xfer-<x>/`, подгонки, таблицы и пробы — в `artifacts/council/xfer-<x>/`.

Порядок на Tinkoff; для СберМаркета — те же команды с `--dataset sber`:

```bash
.venv/bin/python -I council/xfer/run.py --dataset tinkoff info
.venv/bin/python -I council/xfer/run.py --dataset tinkoff queue-path
.venv/bin/python -I council/xfer/run.py --dataset tinkoff queue path
.venv/bin/python -I council/xfer/run.py --dataset tinkoff prereg0
.venv/bin/python -I council/xfer/run.py --dataset tinkoff reference --k 1
.venv/bin/python -I council/xfer/run.py --dataset tinkoff reference --k 2
.venv/bin/python -I council/xfer/run.py --dataset tinkoff wave1
.venv/bin/python -I council/xfer/run.py --dataset tinkoff evidence
.venv/bin/python -I council/xfer/run.py --dataset tinkoff cross
.venv/bin/python -I council/xfer/run.py --dataset tinkoff authors
.venv/bin/python -I council/xfer/run.py --dataset tinkoff evidence
.venv/bin/python -I council/xfer/run.py --dataset tinkoff prereg1
.venv/bin/python -I council/xfer/run.py --dataset tinkoff curate
.venv/bin/python -I council/xfer/run.py --dataset tinkoff compute
.venv/bin/python -I council/xfer/run.py --dataset tinkoff plan-build
.venv/bin/python -I council/xfer/run.py --dataset tinkoff queue plan
.venv/bin/python -I council/xfer/run.py --dataset tinkoff analyze
.venv/bin/python -I council/xfer/run.py --dataset tinkoff select
```

- `queue-path` собирает 4 подгонки: путь dev, путь test и шум на двух зёрнах. `queue path` их выполняет.
- `prereg0` сверяет пути, делает одно чтение S0-explore и проверяет гейт мощности. У автора prereg-0 обоих наборов записан на одном штампе кода совета: поле `identity.council` в двух `prereg-0.json` совпадает. С этого момента `council/xfer/*` заморожен до `read-test`. Правка возможна только отклонением в `configs/datasets/xfer-<x>-deviations.json`.
- Стадии `reference`, `wave1`, `cross` и `authors` вызывают Opus. Бюджет — 24 вызова и $25 на набор.
- `evidence` измеряет карточки без исходов и проверяет гейт перед каждой пробой. Второй запуск после `authors` измеряет переписанные карточки.
- `compute` — тяжёлый шаг. Он начинает с коллекции C_test, у которой самая длинная история.
- `plan-build` пишет `prereg-2.json` и `queue-plan.json` (48 подгонок). До запуска плана у автора было два независимых ревью: `review-prereg2-r1.md` и `review-prereg2-r2.md`.
- `analyze` пишет `plan-result.json`. Если номинированный список D не пуст, он пишет и `queue-confirm.json`; тогда до `select` выполняется `queue confirm`. У автора D пуст у обоих наборов.
- `select` пишет `selection.json`. Флаги `--cut` и `--cut-plan` (§4 контракта) у автора не применялись: `cut` пуст, `cut_plan` — `false`.
- `prereg-0.json` и `selection.json` пишутся строго один раз: если файл есть, команда откажет даже при том же содержимом. `prereg-2.json` и файлы очередей пишутся через `_save_new`: то же содержимое оставляет файл как есть, другое — отказ.

C_test — только после «да» владельца для этого набора. В `council/runs/xfer-<x>/test-approved.md` записываются строки `approved:` (цитата с «да») и `transcript: <id сессии> / <сообщение>`:
- цитата или сообщение называют набор и `final_labels`;
- строки не совпадают со строками `test-approved.md` другого набора, иначе `start-test` откажет.

Затем:

```bash
.venv/bin/python -I council/xfer/run.py --dataset tinkoff start-test
.venv/bin/python -I council/xfer/run.py --dataset tinkoff test-queue
.venv/bin/python -I council/xfer/run.py --dataset tinkoff queue test
.venv/bin/python -I council/xfer/run.py --dataset tinkoff read-test
```

- `test-queue` собирает 14 подгонок, при непустом D — 16.
- `read-test` пишет `test.json`.

На клоне:
- `prereg0` откажет сразу: `prereg-0.json` уже есть;
- `analyze` и `select` откажут из-за закоммиченного `selection.json`;
- `compute` и тесту нужна holdout-коллекция, а её клон не соберёт.

Без данных проверяются `council.report <x> --check` и `council.reveal`.

### Чтение C_test и post-hoc по JSON плана

Эти шаги не читают меток, подгонок и `data/`, им нужны только закоммиченные файлы совета.

**Правило чтения C_test.** Записано 22.10 до `read-test` всех трёх наборов: `council/runs/note-inference-level-2026-10-22.md`, §1. Рядом с вердиктом H1 отчёт приводит описательную t по средним четырёх зёрен против t₃, 0.95 = 2.35. Если вердикт «уступает» или «обыгрывает H+», а |t| < 2.35, в отчёт идёт оговорка; сам вердикт не переписывается.

```bash
.venv/bin/python -m council.posthoc_ctest_t
.venv/bin/python -m council.posthoc_ctest_t --dataset sber --json
```

- Читает `test.json` из `council/runs/rees46-2020/` и `council/runs/xfer-<x>/`; набор без `test.json` пропускается с сообщением. `--dataset` принимает `rees46`, `tinkoff`, `sber` (по умолчанию все три), `--file` — путь к отдельному `test.json`.
- Ничего не пишет, только печатает.

**Post-hoc по плану.** Два правила, записанные после дедлайна. Они читают только `plan-result.json`, `prereg-2.json` и `selection.json` трёх наборов, на вердикты контракта не влияют.
- `council/posthoc_phantom_fwer.py` — сколько пустых столбцов прошли бы порог номинации, будь каждый кандидатом. Prereg — `council/runs/posthoc/phantom-fwer.md`, итог — `council/runs/posthoc/phantom-fwer-result.json`.
- `council/posthoc_beyond_empties.py` — какие семейства лежат за всеми пустыми столбцами, в сравнении с записанной номинацией. Prereg — `council/runs/posthoc/beyond-empties.md`, итог — `council/runs/posthoc/beyond-empties-result.json`.

```bash
.venv/bin/python -m council.posthoc_phantom_fwer --write council/runs/posthoc/phantom-fwer-result.json
.venv/bin/python -m council.posthoc_beyond_empties --write council/runs/posthoc/beyond-empties-result.json
git diff council/runs/posthoc/
```

Без `--write` результат только печатается. С `--write` закоммиченный итог перезаписывается без проверки, отсюда `git diff`. Неутверждённые черновики следующих post-hoc лежат в `council/runs/posthoc/drafts/`; по ним команд нет.

### Побочные проверки

**H13, покрытие кандидатов** (REES46 2020, хвост T_fit). Модуль — `council/side/coverage.py`, prereg — `council/runs/side/coverage.md`, итог — `council/runs/side/coverage.json`. Это лёгкий шаг: DuckDB в памяти, база 2020 подключена только для чтения. Он ждёт тяжёлых шагов REES46 и переноса. Метки S0, val и test он не читает.

```bash
TASK1_PERIOD=2020 .venv/bin/python -I council/side/coverage.py --dry
TASK1_PERIOD=2020 .venv/bin/python -I council/side/coverage.py > /tmp/tlab-side-coverage.log 2>&1
```

**H9–H11** — REES46 2019. Выбор на половине A val делает модуль `council/side/task1_side.py`. Однократное чтение половины B для H9 и H11 — отдельный модуль `council/side/task1_side_b.py`. Правила, время и пики — prereg `council/runs/side/h9.md`, `h10.md`, `h11.md`. Общий стенд и проверка пути описаны в `h11.md`.
- H9 — настройка H+.
- H10 — ранняя остановка.
- H11 — групповой приём таблиц агента.

В prereg записан порядок дня «проверка пути → H9 → H10 → H11» (`h11.md`, «Порядок дня 23.10»). У автора запланирован порядок: проверка пути (пройдена 22.10, `council/runs/side/t1-path-result.json`) → H9 → B H9 → H11 → B H11 → H10; результаты H9–H11 появятся в `council/runs/side/*-result.json` после прогона. Перед каждым тяжёлым шагом, включая чтение B, — проверка тяжёлой полосы.

Каждый шаг на A окружают снимки листинга `artifacts/task1/v2`, `artifacts/task1/v2020`, `artifacts/xfer` и `task1/runs`; команды снимков — в разделе «Команды» каждого prereg. Под `artifacts/task1/v2` и `task1/runs` diff обязан быть пустым: строка там — инцидент, результат `refused`, выход 3. Строки под `artifacts/task1/v2020` и `artifacts/xfer` сверяются с журналами владельцев (`queue.jsonl`) за время прогона. Если владельца нет, это тоже инцидент.
- В снимках prereg стоит BSD-форма `stat -f '%m %z %N'` (macOS). На Linux: `stat -c '%Y %s %n'`.

```bash
TASK1_PERIOD=2019 .venv/bin/python -X faulthandler -m council.side.task1_side path > /tmp/tlab-side-path.log 2>&1
TASK1_PERIOD=2019 .venv/bin/python -m council.side.task1_side h9 --dry
TASK1_PERIOD=2019 .venv/bin/python -X faulthandler -m council.side.task1_side h9 > /tmp/tlab-side-h9.log 2>&1
TASK1_PERIOD=2019 .venv/bin/python -m council.side.task1_side h11 --dry
TASK1_PERIOD=2019 .venv/bin/python -X faulthandler -m council.side.task1_side h11 > /tmp/tlab-side-h11.log 2>&1
TASK1_PERIOD=2019 .venv/bin/python -m council.side.task1_side h10 --dry
TASK1_PERIOD=2019 .venv/bin/python -X faulthandler -m council.side.task1_side h10 > /tmp/tlab-side-h10.log 2>&1
```

- Результат пишется в `artifacts/side/<h>/` и `council/runs/side/<h>-result.json`; проверка пути — в `t1-path-result.json`.
- `task1_side` половину B не читает.

**Чтение B 2019 для H9 и H11** — `council/side/task1_side_b.py`, коммиты e8d634e и e2dad51. Спецификация шага — `council/runs/night/2026-10-22-bughunt.md`, находка «B-step spec». Шаг идёт после A-прогона своей гипотезы со статусом `ok` и только по дословному «да» владельца:

```bash
TASK1_PERIOD=2019 .venv/bin/python -m council.side.task1_side_b h9 --dry \
  --owner-yes '<дословное «да»>' --owner-date YYYY-MM-DD
TASK1_PERIOD=2019 .venv/bin/python -X faulthandler -m council.side.task1_side_b h9 \
  --owner-yes '<дословное «да»>' --owner-date YYYY-MM-DD --owner-source '<чат, сессия>' \
  > /tmp/tlab-side-h9-B.log 2>&1
```

То же с `h11`, после своего A-прогона.
- `--owner-yes` обязан содержать «да», «B 2019» и имя гипотезы (H9 или H11), иначе отказ до чтения. Цитата, дата и источник пишутся в результат. У автора — «да — чтение B 2019 для H9 и H11», 22.10.2026.
- `--dry` — только проверки: ни дня, ни строки B, ни маркера. `--no-wait` отказывает вместо ожидания тяжёлого замка. Настоящему прогону нужны закоммиченные модуль, его тесты и файлы `task1_side.COMMITTED`.
- Два прохода под замком `heavy_step('<h>-B', 'rees46-2019')`. Проход A по дням val 08–13.11 сверяет предсказания сохранённых `.cbm` с `<name>.A.parquet`, требуется max|Δ| = 0. При расхождении пишется `status refused` и `B_read = false`; маркера нет, B не тронут, повтор разрешён. Иначе атомарно (O_EXCL) создаётся маркер `artifacts/side/<h>/B.started`, и с этого момента B гипотезы потрачен. Затем проход B. Любой сбой после маркера пишет `status failed`.
- Результат — `council/runs/side/<h>-B-result.json`, предсказания по запросам — `artifacts/side/<h>/<name>.B.parquet`. Вердикт A в `<h>-result.json` не меняется, его sha256 до и после пишется в результат. Вердикт B заменяет вердикт A в отчёте.
- H9: W (победитель 2-го этапа) скорится на B при любом вердикте A, в том числе «без выигрыша» (`h9.md`, «Условное правило для B»; трактовка пишется в поле `interpretation`). Если 1-й этап не прошла ни одна рука, W нет и B не читается.
- H11: на B скорится G*, выбранная на A, приём на B заново не проверяется. При правиле 1 на A B не читается.
- Однократность. Повтор отказывает, если есть маркер или `<h>-B-result.json` без `B_read = false`. Маркер лежит в `artifacts/`, а она вне Git. Поэтому на клоне однократность держится только на закоммиченном `council/runs/side/<h>-B-result.json`. Без него код снова прочитает B, если на клоне есть данные и `.cbm`.

**Вариант H11 с крупными группами** (`h11.md`, «Вариант с крупными группами»). `task1_side h11 --groups 10|15` запускается только после основного `h11` со статусом `ok` и только по дословному «да» владельца, называющему вариант (правило `h11.md`; код A-прогона это «да» не проверяет). Результат — `h11-L<g>-result.json`. У автора 22.10 вариант не запускался.
- Его чтение B — `task1_side_b h11 --groups 10|15`. «Да» должно называть вариант (`по 10`, `--groups 10` или `L10`).
- Для любого чтения B H11 (основного или варианта) после другого уже прочитанного B H11 «да» должно содержать слово «повторно» (`prior_b`), в каком бы порядке они ни шли.
- Маркер — `artifacts/side/h11/B-L<g>.started`, результат — `council/runs/side/h11-L<g>-B-result.json`.

**H6 и H8** запускаются так же, скриптом с `--dry` и без него. H6 — прокси Π плана REES46: `council/side/proxy.py`, prereg `council/runs/side/proxy.md`. H8 — якорь 611 Tinkoff: `council/side/tinkoff_anchor.py`, prereg `council/runs/side/tinkoff-611.md`.

## Время шагов

Только измеренное на машине автора. Источники: раздел «Затраты» [отчёта](task1-v2-report.md), поле `seconds` в `task1/runs/exp-runs.jsonl`, `log.jsonl` агента, `dfs-select.json`, `test.json`, [журнал экспериментов](task1-night-2026-10-20.md), §7 [спецификации признаков](task1-baseline-features.md).

| Шаг | Время |
|---|---|
| `uv sync --locked`, скачивание архивов | не замерялось |
| `task1.data` | не замерялось |
| выгрузка событий | не замерялось |
| сборка дня, 6 источников | дни train и val — 8–17 с (≈13 с на ≈6.5 тыс. запросов), дни теста — 43–56 с, а параллельно с q1 (23–28.11) — до 123 с; 41 день у автора — ≈18 мин по времени файлов |
| сборка дня, 4 источника (e875b84) | дни train и val — 5–7 с, дни теста — 11–16 с; 41 день — ≈5 мин по времени файлов |
| `task1.leakcheck`, два дня | не замерялось |
| одно обучение на train, 500 итераций | глубина 6 — 305–493 с, глубина 8 — 373–451 с; верхние значения — при параллельных задачах: `q1_b6_s0` шёл со сборкой дней, `q2_hard`, `q2_hl7` и `q2_d8` — с расчётом пакета из брейншторма |
| скоринг val | 1–8 с |
| очередь q1, 3 записанных прогона | 1320 с ≈ 22 мин |
| очередь q2 | 3890 с ≈ 65 мин |
| очередь q3 | 2911 с ≈ 49 мин |
| очередь q4 | 866 с ≈ 14 мин |
| очередь q5 | 2818 с ≈ 47 мин |
| очередь q6 | 657 с ≈ 11 мин |
| очередь q7 | 409 с ≈ 7 мин |
| пакет из брейншторма | `hand_variant` ≈34 с на день, `hand_cpshare` 0.25 с на день; 30 дней |
| `task1.baseline` | обучение ≈5 мин; весь запуск не замерялся |
| DFS: `--compute`, `--select`, два обучения q4 | ≈6, ≈9 (`select_s` 555 с) и ≈13 мин; последнее — только обучение (397 + 400 с), очередь q4 целиком — 866 с |
| DFS `--materialize` | не замерялось |
| агент: 6 раундов, 30 предложений | ≈4.8 ч и $2.89 за 6 вызовов Claude Opus. LLM 1014 с, песочница 866 с, обучение предложений 12 181 с, базы раундов 2490 с, второе зерно принятого признака 781 с |
| признак агента: дни train и val / дни теста | 56 с / не замерялось |
| четыре прогона раунда 5 без LLM | 1605 с ≈ 27 мин |
| `task1.final --eval val` | не замерялось; это 8 обучений на train |
| `task1.final --eval test` | 74 мин: base 1139 с, base_4src 923 с, dfs 1210 с, agent 1162 с; досчёт признаков дней теста сюда не входит |

Время очередей — сумма `seconds` по прогонам. Часть прогонов делила процессор с другими задачами, их время завышено.
