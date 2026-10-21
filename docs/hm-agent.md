# H&M: рука MA — M23 плюс все колонки LLM-агента

Runbook ветки MA по [контракту](hm-agent-design.md). MA — это закреплённая M23 плюс все колонки всех валидных предложений агента, без отбора, в замороженном порядке (контракт §0). Шаги идут в порядке контракта §4 и §7. Решения здесь не принимаются: всё, чего нет в контракте, решает координатор письменно.

Общие правила запуска — как в [docs/hm-kaggle.md](hm-kaggle.md), вводная часть и §0. Кратко:
- запуск только `.venv/bin/python -I scripts/<m>.py` из корня checkout, без `-I` команда откажется;
- в stdout одна JSON-строка. Exit 0 — успех, exit 1 — `status: failed`, и тогда зависимые шаги не запускаются. У `control`, `leakcheck` и `gate` exit 1 означает также DIFF, LEAK или FAIL;
- сообщения DuckDB, CatBoost и ошибки агентского SQL маскируются: подробности смотрите в `manifest.json` или `report.json` в output;
- построчные выходы пишутся только в `artifacts/hm-agent/`. Каждый output должен быть новым; исключение — продолжение `score`;
- упавший output не удаляется. Если путь фиксирован (`export`, `sidecars/<A>`), переместите его в `$A/failed/` и повторите запуск.

Тяжёлая задача на машине всегда одна (контракт §7). Fits и скоринг не запускайте параллельно с плацебо REES46 или с чем-то ещё тяжёлым.

## 0. Окружение

```zsh
cd ~/tlab-recsys-2026 && git switch task1-v2
hm()   { .venv/bin/python -I scripts/hm_kaggle.py "$@"; }
sbx()  { .venv/bin/python -I scripts/hm_agent_sandbox.py "$@"; }
llm()  { .venv/bin/python -I scripts/hm_agent_loop.py "$@"; }
ma()   { .venv/bin/python -I scripts/hm_agent_kaggle.py "$@"; }
DB=artifacts/hm-kaggle/eda/audit.duckdb
C=artifacts/hm-kaggle/collections
A=artifacts/hm-agent
E=$A/export
S=configs/datasets/hm-agent-set.json
P=configs/datasets/hm-agent-prereg.json
D=configs/datasets/hm-agent-deviations.json
.venv/bin/python -m unittest tests.test_hm_kaggle tests.test_hm_agent_sandbox tests.test_hm_agent_loop tests.test_hm_agent_kaggle
```

Обозначения совпадают с контрактом §0: `E` — экспорт, `S` — набор. Коллекции: `$C/2020-08-12-c0q120` … `$C/2020-09-16-c0q120`, шесть штук. На Windows аргументы те же, запуск через `.venv\Scripts\python.exe -I scripts\<m>.py`.

## 1. Экспорт (контракт §1.1)

```zsh
sbx export --database "$DB" --output "$E"
```

- **Пишет** `$E/tx/d=YYYY-MM-DD/*.parquet`, `$E/articles/articles.parquet` и `$E/export.json` (файлы read-only). Ни `--before`, ни таблицы customers здесь нет.
- **Проверить в stdout:** `status completed`, `before null`, `rows 31788324`, `articles 105542`. В `export.json`: `tx.first 2018-09-20`, `tx.last 2020-09-22`. Значение `digest` запишите: это identity экспорта во всех дальнейших манифестах.
- **При ошибке:** перенесите `$E` в `$A/failed/`. Если ошибка `Export and database…` или `database_sources`, проверьте `kaggle-source.json` рядом с DB.
- **Оценка (контракт §7, шаг 6):** export и проба вместе ≈ 0,25 ч. Нужно ≥ 10 GiB свободного места (`resource_preflight`).

## 2. Проба 2020-09-09 (контракт §2, «Проба»)

```zsh
sbx probe --database "$DB" --export "$E" --anchor 2020-09-09 --users 5000 \
  --output "$A/probe-2020-09-09" --threads 3
```

- **Пишет** `keys.parquet`, `sources.parquet`, `m23.parquet`, `stats.json` (только агрегаты истории до 09-09) и `probe.json`. Метки не строятся.
- **Проверить:** `status completed`, `users 5000`, `rows 600000` (120 × 5000); `export_digest` равен digest шага 1.
- **При ошибке:** `…customers bought…` — в истории меньше 5000 клиентов, остановитесь. `stats.json would carry an id-shaped string` — ошибка кода, нужна правка до шага 3. Перед повтором перенесите output в `$A/failed/`.

## 3. Один прогон агента (контракт §2, «Раунды», «Один прогон агента»)

Запускайте только при свободной тяжёлой очереди. Таймауты 20/60 с и бюджет пробы 90/180 с отсекают колонки навсегда (контракт §7).

```zsh
uptime; pgrep -fl 'hm_kaggle|hm_agent|hm_experiment|task1|catboost' || echo "очередь свободна"
RUN=$A/run-$(date +%Y%m%d-%H%M)
llm run --export "$E" --probe "$A/probe-2020-09-09" --output "$RUN" \
  --rounds 6 --proposals 5 --model claude-opus-5-5 --max-calls 12 --threads 3
```

- **Вызов LLM:** изолированный `claude -p … --model claude-opus-5-5 --safe-mode --setting-sources project --tools '' --strict-mcp-config --disable-slash-commands --no-session-persistence --no-chrome --output-format stream-json --verbose`. Cwd — пустой `mkdtemp`, timeout 900 с, окружение минимальное (контракт §2). `claude` должен находиться в `PATH`.
- **Пишет** в `$RUN/`: `prompt-rN.txt`, `reply-rN.json`, `log.jsonl` (статус и статистики валидности по каждому предложению, плюс `loadavg`), `values/<id>.parquet` (значения на пробе, это строки данных) и `run.json`.
- **Проверить в stdout:** `status completed`, `stop` равен `rounds` или `max_calls`, `calls` ≤ 12, `valid`, `columns`. В `run.json` каждая строка `call_log[*].init` должна показывать пустые `tools`, `mcp_servers`, `skills` и `slash_commands`, `model claude-opus-5-5` и плагины только `agents-md@builtin`. Сверьте `loadavg` в `log.jsonl`: высокие значения при отказах `timeout` или `budget` запишите как ограничение.
- **При ошибке.** Повтор допустим только после технического сбоя: падение кода, сбой CLI или `stop retries_exhausted`. Решение о повторе не опирается на содержание предложений. Повтор идёт в новую папку:
  ```zsh
  llm run --export "$E" --probe "$A/probe-2020-09-09" --output "$A/run-<новый id>" \
    --retry-of "$RUN" --reason "<техническая причина>"
  ```
  Остановка оператором (`KeyboardInterrupt`) не повторяется. Завершённый прогон не повторяется. Код допускает не больше двух повторов на пробу. Предложения упавшего прогона в набор не входят.
- **Оценка (контракт §2, §7 шаг 6а):** 1–2 ч по часам, ожидается 6–8 вызовов на $2–5.

## 4. Заморозка (контракт §2, «Заморозка»)

```zsh
llm freeze --run "$RUN" --output "$S"
mkdir docs/hm-agent-run
cp "$RUN"/prompt-r*.txt "$RUN"/reply-r*.json "$RUN"/log.jsonl "$RUN"/run.json docs/hm-agent-run/
```

- **Пишет** `$S`: все `valid` в порядке (раунд, индекс, колонка), `digest = canonical_digest([[id, level, sql, columns], …])`. В `docs/hm-agent-run/` попадают промпты, ответы, журнал и `run.json` со строками init. `values/` не копируется: там строки данных.
- **Проверить:** `status completed`, `proposals`, `columns` и `digest` в stdout; `probe.export_digest` в `$S` равен digest экспорта.
- **При ошибке:**
  - `no valid proposal` означает, что MA не строится. Запишите результат «агент не дал валидных колонок» (контракт §2) и остановитесь.
  - `exists with other content` означает, что `$S` уже существует. Файл не перезаписывается, разберитесь вручную.
  - `More than one completed run` нарушает правило одного прогона. Остановитесь.

## 5. Prereg `configs/datasets/hm-agent-prereg.json` (контракт §4, «Prereg»)

Код читает из prereg следующие поля (`read_prereg`, `fit_ma`, `contrast`, `gate`):

| Поле | Требование кода | Как получить |
|---|---|---|
| `agent_set.sha256` | строка; равна `agent_set.sha256` в сайдкарах, fits, плане и leakcheck | SHA-256 байтов `$S` (`shasum -a 256 "$S"`) |
| `export_digest` | строка; равна `export_digest` во всех артефактах | `digest` из `$E/export.json` |
| `code` | непустой dict; должен быть равен текущему `agent_code_identity()`, иначе `fit`, `contrast` и `gate` откажут. Хеши `hm_kaggle.py` и locked-модулей должны совпадать с `code` в отчётах port M | `hm_agent_sandbox.agent_code_identity()`: 5 locked-модулей, `hm_kaggle.py`, 3 модуля `hm_agent_*` и `hm_result_audit.py` |
| `threads` | int; `fit` требует равенства с `--threads` | `8` (контракт §4, D10) |
| SHA-256 файла prereg | `prereg_sha256` записей отклонений; `prereg.sha256` в отчётах | prereg после первого числа MA не меняется ни на байт |

Остальные поля контракт требует, а код не читает: digest набора и число колонок, identity DB, руки, seeds, якоря, fits, правила и ограничения. Prereg собирается из файлов, а не вручную. Перед сборкой `git status --short docs/hm-agent-design.md scripts/hm_agent_*.py` должен быть пуст или показывать только `??` у ещё не добавленного кода: `contract.sha256` и `code` фиксируют байты рабочего дерева.

```zsh
.venv/bin/python -I - <<'EOF'
import json, sys
from pathlib import Path
sys.path.append(str(Path.cwd()))
from scripts import hm_agent_sandbox as sandbox, hm_agent_kaggle as ma, hm_experiment as experiment
S, E, P = Path('configs/datasets/hm-agent-set.json'), Path('artifacts/hm-agent/export'), Path('configs/datasets/hm-agent-prereg.json')
agent, export = sandbox.read_agent_set(S), sandbox.read_export(E)
assert export['before'] is None and agent['probe']['export_digest'] == export['digest'] and not P.exists()
contract = Path('docs/hm-agent-design.md')
ref = lambda part: f'docs/hm-agent-design.md {part}'
record = {
  'format': 'hm-agent-prereg-v1',
  'contract': {'path': contract.as_posix(), 'sha256': experiment.sha256_file(contract)},
  'agent_set': {'path': S.as_posix(), 'sha256': experiment.sha256_file(S), 'digest': agent['digest'],
                'columns': len(agent['columns']), 'run': agent['run']},
  'export_digest': export['digest'], 'database': export['database'], 'sources': export['sources'],
  'code': sandbox.agent_code_identity(),
  'threads': 8, 'score': {'threads': 4, 'chunk_users': 15000, 'anchor': '2020-09-23', 'control': 'M2026'},
  'arms': {'M': 'M23 из lock', 'E': 'E46 из lock', 'MA': 'M23 + все колонки agent_set в замороженном порядке'},
  'seeds': [2026, 2027],
  'anchors': {'sidecars': list(ma.SIDECAR_ANCHORS), 'port_train': list(ma.PORT_TRAIN_ANCHORS),
              'port_validation': ma.PORT_VALIDATION_ANCHOR, 'final_train': list(ma.FINAL_TRAIN_ANCHORS),
              'leakcheck': list(ma.LEAKCHECK_ANCHORS), 'leakcheck_users': ma.LEAKCHECK_USERS},
  'fits': ['port/M2026', 'port/M2027', 'port/E2026', 'port/MA2026', 'port/MA2027',
           'final/M2026', 'final/M2027', 'final/E2026', 'final/E2027', 'final/MA2026', 'final/MA2027'],
  'dev_contrast': ref('§4 «Дев-контраст»'), 'gate': ref('§4 «Гейт отправки MA»'),
  'first_number': ref('§4 «Первое число MA»'), 'refusal': ref('§4 «Правило отказа»'),
  'deviations': ref('§4, configs/datasets/hm-agent-deviations.json'),
  'kaggle_reading': ref('§4 «Чтение Kaggle» и «Сколько seeds»'), 'fallbacks': ref('§4 «Правило отказа», §7 «Запасные варианты»'),
  'limitations': [ref('§2: обратная связь агенту — только валидность и покрытие, в REES46 агент видел dNDCG (D9)'),
                  ref('§5: знание LLM о решениях соревнования H&M принимается и не отделяется (D8)')],
}
P.write_text(json.dumps(record, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
print(json.dumps({'prereg_sha256': experiment.sha256_file(P), 'columns': len(agent['columns'])}))
EOF
```

- **Проверить:** `columns` равно числу колонок из шага 4. Код `hm_agent_*.py` после этого не меняется. Любая правка до первого числа MA требует перевыпуска prereg (шаги 5–6), а после первого числа — записи в отклонения (шаг 17).
- **Оценка (контракт §7, шаг 6а):** freeze и prereg вместе ≈ 0,25 ч.

## 6. Коммит набора и prereg (контракт §0, §4)

```zsh
git add scripts/hm_agent_sandbox.py scripts/hm_agent_loop.py scripts/hm_agent_kaggle.py \
  tests/test_hm_agent_sandbox.py tests/test_hm_agent_loop.py tests/test_hm_agent_kaggle.py   # если код ещё не в Git
git add "$S" "$P" docs/hm-agent-run docs/hm-agent.md
git diff --cached --stat
git commit -m "H&M MA: замороженный набор агента и prereg"
```

- Prereg коммитится до первого MA fit. Хеши `code` в prereg относятся к байтам кода, поэтому код должен быть в Git в этом же коммите или раньше.
- **Проверить:** `git status --short` не показывает `$S`, `$P` и код; `shasum -a 256 "$S"` равен `agent_set.sha256` в prereg.

## 7. Leakcheck (контракт §5)

Запускается до первого сайдкара. Гейт проверяет, что `finished_at_utc` leakcheck раньше `started_at_utc` каждого сайдкара.

```zsh
ma leakcheck --database "$DB" --export "$E" --agent-set "$S" \
  --collections "$C/2020-08-19-c0q120" "$C/2020-09-16-c0q120" --users 2000 --output "$A/leakcheck"
```

- **Пишет** `$A/leakcheck/report.json`: по якорю `rows`, `columns`, расхождения полного экспорта со срезом `--before A`, расхождения инвариантности (1 батч против 4) и OK/LEAK. Значения не пишутся. Срез экспорта создаётся во временном каталоге внутри output и удаляется.
- **Проверить:** exit 0, `result OK`; на каждом якоре `rows 240000` (2000 × 120), `leak_mismatches 0`, `invariance_mismatches 0`. Гейт требует ровно якоря 08-19 и 09-16 и `--users 2000`.
- **При LEAK или падении с `proposal`:** сайдкары не строятся. Колонки не удаляются, SQL не правится (контракт §4, «Правило отказа»). Ошибку кода до первого числа исправьте, перевыпустите prereg (шаги 5–6) и повторите leakcheck в новый output. Если так исправить нельзя, MA не выполнена; это записывается как результат.
- **Оценка (контракт §7, шаг 8):** leakcheck вместе с шестью сайдкарами — 0,5–0,8 ч.

## 8. Сайдкары × 6 (контракт §3.1)

```zsh
for anchor in 2020-08-12 2020-08-19 2020-08-26 2020-09-02 2020-09-09 2020-09-16; do
  ma sidecar --database "$DB" --export "$E" --agent-set "$S" --collection "$C/$anchor-c0q120" \
    --output "$A/sidecars/$anchor" --threads 4 || break
done
```

- **Пишет** `$A/sidecars/<A>/{keys.parquet, agent.parquet, manifest.json}`. Коллекции не меняются.
- **Проверить:** по каждому якорю `status completed`, `rows 2400000`, `columns` = числу колонок набора. В `manifest.json` каждое значение `non_null` > 0: колонка без не-NULL провалит паритет гейта.
- **При ошибке:** stdout с `proposal` означает правило отказа (как в шаге 7). `TimeoutError` (лимит `--wall-seconds 3600`) — техническая причина. `fit` читает сайдкар по пути `$A/sidecars/<A>`, поэтому упавший каталог перенесите в `$A/failed/` и повторите запуск.
- **Оценка (контракт §3.1):** 2–6 мин на якорь, RSS ≤ 6 ГБ.

## 9. Port MA2026 и MA2027 (контракт §3.2, §4)

```zsh
PORT_TRAIN=("$C/2020-08-12-c0q120" "$C/2020-08-19-c0q120" "$C/2020-08-26-c0q120" "$C/2020-09-02-c0q120" "$C/2020-09-09-c0q120")
for seed in 2026 2027; do
  ma fit --seed "$seed" --train "${PORT_TRAIN[@]}" --validation "$C/2020-09-16-c0q120" \
    --sidecars "$A/sidecars" --prereg "$P" --output "$A/port/MA$seed" --threads 8 --wall-seconds 14400 || break
done
```

- **Первое число MA** — MAP первого port fit (контракт §4). После него запрещено удалять колонки, менять SQL, параметры и данные и перезапускать агента.
- **Пишет** `model.cbm`, `params.json`, `query-metrics.parquet`, `predictions-top12.parquet` и `report.json` (`format hm-agent-fit-v1`, `arm MA`).
- **Проверить в stdout:**
  - `trees 500`, `deviation null`;
  - `train_queries 100000`, `train_positive_rows 4233`;
  - `queries 20000`, `positive_queries 1905`, `distinct_query_target_pairs 5962`, `oracle_map_at_12_conditional 0.17352937` — всё как у port M (docs/hm-kaggle.md §5).

  MAP здесь не оценивается: пол по популярности проверяет гейт.
- **При ошибке:** `Preregistration…`, `Code differs…`, `threads differ` означают, что prereg не совпадает с кодом; до первого числа помогают шаги 5–6. `TimeoutError` и нехватка памяти после первого числа исправляются только через шаг 17.
- **Оценка (контракт §3.2, §7 шаг 9):** fit в 2,5–4 раза дольше M (M: 314–321 с), пик ≤ 10 ГБ. Port × 2 вместе с контрастом — 0,5–1,5 ч.

## 10. Дев-контраст против port M (контракт §4, «Дев-контраст»)

```zsh
ma contrast --reference artifacts/hm-kaggle/port/M2026 artifacts/hm-kaggle/port/M2027 \
  --alternative "$A/port/MA2026" "$A/port/MA2027" --prereg "$P" --output "$A/dev-contrast.json"
```

- **Пишет** `$A/dev-contrast.json`: `map_by_fit`, `delta_by_seed`, `mean_map` по рукам и `bootstrap` (paired, 2000 draws, seed 2026), без округления.
- **Проверить:** `status completed`. Роль контраста описательная: при CI ±0,0025 эффект размера H+ не различим. На отправку и на вердикт он не влияет.
- **При ошибке:** `not paired` означает, что `inputs`, `training_populations`, база или рецепт (включая `thread_count`) MA не совпадают с M. Это ошибка цепочки: разберитесь, ничего не переобучая наугад.

## 11. Final MA × 2 (контракт §3.2, §4)

```zsh
FINAL_TRAIN=("$C/2020-08-19-c0q120" "$C/2020-08-26-c0q120" "$C/2020-09-02-c0q120" "$C/2020-09-09-c0q120" "$C/2020-09-16-c0q120")
for seed in 2026 2027; do
  ma fit --seed "$seed" --train "${FINAL_TRAIN[@]}" \
    --sidecars "$A/sidecars" --prereg "$P" --output "$A/final/MA$seed" --threads 8 --wall-seconds 14400 || break
done
```

- **Проверить:** `trees 500`, `train_queries 100000`, `train_positive_rows 4377` (как у final M, docs/hm-kaggle.md §9). Validation нет.
- **При ошибке:** как в шаге 9. Если к пятнице 23.10, 12:00, готов только один final MA, отправляется он один, и чтение идёт по случаю «один файл MA» (контракт §4, §7).
- **Оценка (контракт §7, шаг 10):** 0,5–1,5 ч на оба fit.

## 12. score_ma на 2020-09-23 (контракт §3.3)

`--chunk-users 15000`: пик RSS скоринга M/E при 15k составил 8,94 ГБ, это не меньше 8 ГБ, поэтому 30k не берётся (контракт §3.3).

```zsh
ma score --database "$DB" --export "$E" --agent-set "$S" \
  --fits "$A/final/MA2026" "$A/final/MA2027" --control artifacts/hm-kaggle/final/M2026 \
  --output "$A/score-2020-09-23" --chunk-users 15000 --threads 4 --wall-seconds 28800
```

- **Пишет** `plan.json` (`PLAN_FORMAT` с полем `agent`), `chunk-NNNN.json` с дополнительными полями `agent_seconds`, `nonfinite_scores`, `agent_non_null` и `agent_rows`, `top12-{M2026,MA2026,MA2027}-NNNN.parquet` и `report.json`.
- **Проверить:** `status completed`, `users 518920`, `chunks 35` (как у `artifacts/hm-kaggle/score-2020-09-23`), `computed + skipped = 35`. Пик RSS смотрите в квитанциях.
- **Продолжение:** повторите ту же команду; чанки с квитанцией пропускаются. `plan differs` требует нового `--output`. Тупики и `score.lock` описаны в docs/hm-kaggle.md §7. Ошибка с `proposal` подчиняется правилу отказа: чанк без квитанции, команда падает целиком.
- **Оценка (контракт §3.3, §7 шаг 11):** 1,5–4 ч, пик RSS 6–12 ГБ. Шаги 12–15 вместе — 1,8–4,3 ч.

## 13. Контроль (контракт §3.3, «Контроль»)

```zsh
ma control --agent-scores "$A/score-2020-09-23" --kaggle-scores artifacts/hm-kaggle/score-2020-09-23 --model M2026
```

- **Пишет** только stdout, файла нет. `gate` повторяет контроль сам.
- **Проверить:** `result OK`, exit 0; `only_agent 0`, `only_kaggle 0`, `article_mismatches 0`, `score_mismatches 0`, `max_abs_score_difference` ≤ 1e-9.
- **При DIFF:** MA не отправляется. Ищите техническую причину и исправляйте по шагу 17.

## 14. Гейт (контракт §4, «Гейт отправки MA»)

```zsh
ma gate --prereg "$P" --leakcheck "$A/leakcheck" --sidecars "$A/sidecars" \
  --agent-scores "$A/score-2020-09-23" --kaggle-scores artifacts/hm-kaggle/score-2020-09-23 \
  --port "$A/port/MA2026" "$A/port/MA2027" --model M2026 --output "$A/gate"
```

- **Пишет** `$A/gate/gate.json` с проверками `prereg`, `leakcheck`, `control`, `finite`, `parity` и `popularity`; в каждой OK или FAIL со счётчиками. Пол по популярности печатается только как OK/FAIL, без MAP.
- **Проверить:** exit 0, `result OK`, все шесть проверок OK.
- **При FAIL:** сначала ищется техническая причина, исправление идёт по шагу 17. Если технической причины нет, MA не отправляется; запишите «MA не прошла гейт: <пункт>». Агент не перезапускается, колонки не удаляются (контракт §4).

## 15. Assemble × 2 (неизменённый `hm_kaggle.py assemble`)

Запускается только после `gate OK`.

```zsh
for model in MA2026 MA2027; do
  hm assemble --database "$DB" --scores "$A/score-2020-09-23" --model "$model" \
    --output "$A/submissions/$model.csv.gz" || break
done
```

- **Пишет** `$A/submissions/MA{2026,2027}.csv.gz` и квитанции `MA{2026,2027}.json`.
- **Проверить в квитанции:** `rows 1371980`, `model_customers 518920`, `popular_fallback_customers 853060` (как у M/E). SHA-256 файла запишите.
- **При ошибке:** docs/hm-kaggle.md §8. `.part` остаётся для разбора, повторный запуск возможен только после того, как `.part` убран вручную.

## 16. Отправка (контракт §4, «Отправка»; D1)

Отправка идёт только после явного «да» пользователя именно на эти посылки MA. «Да» на M/E от 20.10 их не покрывает.

```zsh
for model in MA2026 MA2027; do
  ~/.venvs/kaggle-cli/bin/kaggle competitions submit -c h-and-m-personalized-fashion-recommendations \
    -f "$A/submissions/$model.csv.gz" -m "$model: M23 + all agent columns (hm-agent-set.json)" || break
done
~/.venvs/kaggle-cli/bin/kaggle competitions submissions -c h-and-m-personalized-fashion-recommendations
```

- Лимит посылок описан в контракте §4 («Отправка») и D1. По каждому файлу запишите private, public и SHA-256.
- Если отправлен один файл MA, правило чтения не применяется: см. ниже.

## 17. Отклонения (контракт §4, «Первое число MA»)

- **Когда.** Только после первого числа MA (шаг 9) и только для технических исправлений: таймаут, память, размер чанка, падение кода, ошибка кода, найденная гейтом или контролем. Данные, SQL, колонки и параметры модели не меняются. До первого числа вместо отклонения перевыпускается prereg (шаги 5–6).
- **Запись.** В `configs/datasets/hm-agent-deviations.json` записи добавляются в конец, по времени:
  ```json
  {"format": "hm-agent-deviations-v1",
   "deviations": [
    {"id": "d1", "time": "2026-10-22T10:15+03:00", "reason": "<техническая причина>",
     "prereg_sha256": "<shasum -a 256 configs/datasets/hm-agent-prereg.json>",
     "code": {"<все ключи code из prereg>": "<SHA-256 после исправления>"},
     "rebuilds": ["score", "control", "assemble"]}
   ]}
  ```
  - `code` — полный набор хешей после исправления, с теми же ключами, что в prereg:
    ```zsh
    .venv/bin/python -I -c 'import json,sys; sys.path.append("."); from scripts import hm_agent_sandbox as s; print(json.dumps(s.agent_code_identity(), indent=2, sort_keys=True))'
    ```
  - `rebuilds` — различные шаги из `leakcheck, sidecar, port, contrast, final, score, control, assemble`. Пересобираются самый ранний из названных шагов и все шаги после него в этом порядке.
  - `time` указывается в ISO 8601 со смещением. Id уникальны.
- **Коммит.** Файл коммитится до запуска, который им пользуется.
- **Запуск.** Каждая следующая команда (`sidecar`, `leakcheck`, `fit`, `contrast`, `score`, `control`, `gate`) получает `--deviations "$D"`. Пересобираемые шаги запускайте в новые output; для `sidecars/<A>` старый каталог перенесите в `$A/failed/`.
  - Артефакт получает `deviation` = id последней записи, если текущий код равен её `code`; иначе `deviation null`.
  - Шаг, который запись пересобирает, с другим кодом откажет.
  - `score`: plan записывает версию файла отклонений, поэтому продолжение требует той же версии. Запись, которая пересобирает `score` или более ранний шаг, требует нового `--output`.
- **Проверка.** `gate` сверяет `code` и `deviation` всех артефактов с prereg и записями.
- **Если исправить нельзя.** MA не выполнена; это записывается как результат.

## Результаты 21.10.2026

Строка прогона агента — из шага 3 (`run.json`) и аудита. Остальное — из stdout и отчётов шагов 7–15: одна цепочка 01:57–02:35 МСК от коммита 6bd2903. Отклонений нет: во всех манифестах и отчётах с полем `deviation` оно равно null. Время — по меткам лога цепочки, включая загрузку. Вне фолбэка (518 920 строк) MA2026 и MA2027 совпадают точно в 9 строках, с M2026 и M2027 — в 0; M2026 и M2027 между собой — в 24. Независимая проверка файлов: заголовок, 12 различных известных товаров в каждой строке, набор клиентов равен `customers`, популярный список тот же, что у M.

| Шаг | Получено | Ожидание |
|---|---|---|
| Прогон агента | `run-20261021-0145`: 6 вызовов, $1,17, 30 предложений, 29 valid, 34 колонки; аудит SQL — CLEAN ([audit.md](hm-agent-run/audit.md)) | — |
| Leakcheck 08-19 / 09-16 | `rows 240000`, `leak_mismatches 0`, `invariance_mismatches 0`, OK | то же |
| Сайдкары × 6 | `rows 2400000`, 34 колонки; минимальный `non_null` по колонкам 117 539–128 525; 18–19 с на якорь | не-NULL > 0 |
| Port MA2026 / MA2027 MAP@12 | 0.03621653 / 0.03618981; `train_positive_rows 4233`, `positive_queries 1905`, oracle 0.17352937; 319 с на fit | счётчики как у port M |
| Дев-контраст MA − M | по seeds +0.00289 / +0.00303, среднее +0.00296, 95% bootstrap [+0.00011, +0.00587] | описательный |
| Final MA2026 / MA2027 | `trees 500`, `train_positive_rows 4377`; 300 / 313 с | 4 377 |
| Score 2020-09-23 | 518 920 клиентов, 35 чанков, ≈ 21 с на чанк (агентские колонки ≈ 11 с), пиковый RSS 9,82 ГБ | 35 |
| Control M2026 | 6 227 040 строк, 0 расхождений, `max_abs_score_difference 0.0` | OK |
| Gate | OK: prereg, leakcheck, control, finite, parity, popularity | OK |

Port M для сравнения: M2026 0.03332364, M2027 0.03316327, E2026 0.03399804 ([hm-kaggle.md](hm-kaggle.md) §9).

| Файл | Строк | model / fallback | SHA-256 | Public | Private |
|---|---:|---|---|---:|---:|
| MA2026 | 1 371 980 | 518 920 / 853 060 | `668ea427965fb321c925e0f0726ab0f860ecd9c5c2e38b2d1dda7b5d316519d7` | 0.02444 | 0.02360 |
| MA2027 | 1 371 980 | 518 920 / 853 060 | `cbbc5319168d30edafc5223061f4d7abad89a0c32e3a59120a8b56bf39910ed6` | 0.02317 | 0.02317 |

Оба файла отправлены 21.10 в 06:14 и 06:17 UTC (ref 57469040 и 57469161) после отдельного «да» пользователя; SHA-256 перед отправкой совпали с таблицей. Чтение по private (контракт §4): MA2026 0.02360 и MA2027 0.02317 выше M2026 0.02308 и M2027 0.02284, то есть `min(MA) > max(M)`. Но разность средних 0.000425 меньше размаха MA 0.00043, и вердикт по опубликованным числам — «не различено». Разрыв 0.000005 лежит в пределах округления: Kaggle CLI отдаёт счёт с пятью знаками, и на неокруглённых счетах условие могло как выполниться, так и нет. Калибровка E−M по тому же правилу тоже «не различено», на границе: разность средних 0.00024 равна размаху M.

**Плацебо MA (post-hoc, вне контракта).** Port fits MApl — MA с 34 колонками агента, переставленными по строкам внутри каждого якоря ([предрегистрация](hm-ma-placebo.md), [результат](hm-ma-placebo-result.json), коммиты 47a9e72 и f100fa8). Локальный условный MAP@12 на 09-16, 1 905 покупателей:

| Зерно | MA | MApl | M | D = MA − MApl, 95% CI | MApl − M, 95% CI |
|---|---:|---:|---:|---|---|
| 2026 | 0.03622 | 0.03249 | 0.03332 | +0.0037 [+0.0008, +0.0069] | −0.0008 [−0.0033, +0.0016] |
| 2027 | 0.03619 | 0.03181 | 0.03316 | +0.0044 [+0.0005, +0.0083] | −0.0014 [−0.0041, +0.0012] |
| среднее зёрен | | | | +0.0041 [+0.0012, +0.0072] | −0.0011 [−0.0032, +0.0009] |

Чтение по правилу: «прирост MA несёт содержание колонок агента, а не их число». Спецификация до прогона называла правило 1 почти недостижимым: у MA − M на зерне 2027 CI накрывает 0. Оно выполнилось, потому что переставленные колонки слегка вредят (MApl ниже M на обоих зёрнах, CI накрывают 0), и D больше MA − M. Неделя 09-16 — та же, на которой MA сравнивали с M до гейта, поэтому D может быть смещён вверх. Неделя одна, плацебо по ключам не делалось.

## Чтение Kaggle

Правило не пересказывается. Действует контракт [§4 «Чтение Kaggle»](hm-agent-design.md#4-обучение-и-оценка) вместе с «Сколько seeds», в версии, закреплённой `contract.sha256` в prereg. Там же описаны случай одного файла MA и калибровка E−M.

## Расхождения кода и контракта

Везде выполняется код; ниже перечислено, чем он отличается от текста контракта.

1. **Повтор прогона агента.** В контракте сказано только «новая папка `run-<id>`, причина записывается». Код требует `--retry-of <упавший run> --reason "…"` и принимает только `status failed` с типом ошибки, отличным от `KeyboardInterrupt`. Повторов не больше двух на пробу (`MAX_RETRIES = 2`). Любой завершённый прогон на той же пробе где угодно под `artifacts/` запрещает новый прогон. Имя каталога должно соответствовать `run-[A-Za-z0-9][A-Za-z0-9._-]*`.
2. **`LANG` при вызове `claude`.** Контракт пропускает `LANG` из окружения, код ставит `LANG=en_US.UTF-8`.
3. **`docs/hm-agent-run/`.** По контракту init копируется туда; код пишет init только в `$RUN/run.json` и `reply-rN.json`. Копирование ручное (шаг 4).
4. **`--deviations` у всех шагов.** Контракт называет приём отклонений только у `fit_ma`, `contrast` и `gate`. В коде флаг есть также у `sidecar`, `leakcheck`, `score` и `control`. По контракту поле `deviation` — это «id последней записи на момент запуска или null». В коде это id последней записи, только если текущий код равен её `code`; иначе null. Без `--deviations` всегда null.
5. **`threads` в prereg.** Контракт перечисляет threads среди содержимого prereg. В коде `fit` отказывает, если `threads` в prereg не равно `--threads`.
6. **Final fit.** Без `--validation` код требует ровно якоря 2020-08-19…2020-09-16; контракт задаёт их только таблицей §4.
7. **Лимиты времени.** У `sidecar` есть `--wall-seconds` (default 3600), у `leakcheck` — `--wall-seconds` (default 7200); в командах контракта их нет. У `export` и `probe` флага нет, внутренний лимит 3600 с.
8. **`export --threads`.** Флаг есть (default 4), в контракте его нет.
9. **`gate`.** Контракт не даёт CLI. В коде `--output` — новый каталог с `gate.json`, и добавлена шестая проверка `prereg`:
   - привязка всех артефактов к набору, экспорту, коду и записям отклонений;
   - сайдкары — ровно те, что использовали fits;
   - final MA обучены на final-якорях;
   - port fits есть ровно для отправляемых seeds.

   Проверка `leakcheck` дополнительно требует якоря 08-19 и 09-16, `users 2000` и завершения раньше старта каждого сайдкара. В контракте «запуск до первого сайдкара» — порядок, а не пункт гейта.
10. **`control`.** Файла не пишет: результат только в stdout, exit 1 при DIFF. Гейт пересчитывает контроль сам и проверяет его под своим `deviation`.
