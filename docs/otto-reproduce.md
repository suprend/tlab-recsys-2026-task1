# Как воспроизвести OTTO

Инструкция ведёт от файлов соревнования Kaggle OTTO до чисел OTTO-1 ([otto.md](otto.md)), OTTO-2 ([otto2.md](otto2.md)) и OTTO-3 ([otto3.md](otto3.md)). Контракт эксперимента — [otto-design.md](otto-design.md), журнал базы B — [otto-base-log.md](otto-base-log.md).

Все команды выполняются из корня репозитория на ветке `main`. Скрипты запускаются только как `.venv/bin/python -I scripts/<скрипт>.py`: без `-I` они отказываются работать. Каждая команда печатает одну строку JSON. Каталоги `data/` и `artifacts/` исключены из Git, их содержимое создают команды ниже.

Под Git лежит:
- `configs/datasets/otto-*.json` — база B, набор агента OTTO-1, prereg, отклонения d1–d5, квитанции holdout;
- `configs/datasets/otto3-i1-set.json`, `otto3-i2-set.json`, `otto3-i3-set.json` — замороженные наборы агента OTTO-3;
- `docs/otto-run/` — журнал OTTO-1: прогон агента `run-a1/`, аудит, калибровка, leakcheck, гейты, файлы и оценки Kaggle;
- `docs/otto3-run/` — журналы итераций `i1`, `i2`, `i3`, посылки OTTO-3, бутстрап шагов `ladder-ci-F3.json`.

Порядок шагов:
1. окружение и данные;
2. загрузка и коллекции;
3. база B;
4. OTTO-1: агент, аудит, leakcheck, сайдкары, dev, holdout, final;
5. OTTO-2: финальная модель `f4all-lr10-it2000`;
6. OTTO-3: итерации `i1`, `i2`, `i3`;
7. сборка файла и посылка в Kaggle;
8. проверка без переобучения.

Термины.
- Складки: F2 — обучение (`train-F2`), F3 — dev (`val-F3`, популяция 300 000 сессий; проба агента `probe-F3`, 20 000 сессий), F4 — holdout (`holdout-F4`, метки запечатаны), F5 — тест Kaggle (`kaggle-F5`, 1 671 803 сессии).
- Руки: Pop, B (база), BA (база и колонки агента), BApl (плацебо: колонки агента переставлены).
- Зёрна: 2026 и 2027.
- Серии: dev (F2 → F3), holdout (F3 → F4), final (F4 → F5).
- Метрика: Score = 0.1·R_clicks + 0.3·R_carts + 0.6·R_orders, где R — Recall@20.
- Набор агента — SQL-предложения: таблицы, источники кандидатов, признаки. Сайдкар — колонки набора, посчитанные на коллекции. Leakcheck — проверка, что колонки набора не видят будущего.

## Что воспроизводится точно, а что нет

- **Ответы LLM.** Новый прогон агента (`run`) — новый эксперимент с другими предложениями. В `i2` и `i3` действует `replay`: действительные предложения предыдущей закоммиченной итерации проверяются заново в своих раундах без вызова модели. Новые раунды всё равно вызывают `claude -p`. Поэтому источник истины — закоммиченные наборы, а не повтор прогона. Все последующие шаги читают набор из `configs/datasets/`.
- **Данные и модели.** Порядки сессий заданы sha256 с солями. Бутстрап использует 2000 повторов и зерно 2026, CatBoost — зёрна 2026 и 2027. Побайтное совпадение коллекций, сайдкаров и моделей на другой машине не проверялось.
- **Квитанция загрузки.** `otto-verify.json` содержит замеры времени и `created_utc`, поэтому её SHA-256 на новой машине будет другим. Поле `verify_sha256` в prereg — хеш квитанции автора, и код его не сверяет.
- **Kaggle.** Посылка создаёт новую запись в Kaggle и ещё одно чтение F5. Оценки — данные Kaggle; повтор оценки того же файла не проверялся. SHA-256 файла `.csv.gz` зависит от версии и флагов gzip, а без `-n` ещё и от имени и времени изменения файла. Сверять нужно `.csv`.

## Окружение

```bash
uv sync --locked
```

- Python 3.12 (`.python-version`). Версии catboost и duckdb закреплены в `pyproject.toml` и `uv.lock`.
- Машина автора: Apple M3 Pro, 12 CPU, 36 ГБ памяти, macOS 26.3, 174 ГБ свободного диска на старте ([otto-design.md](otto-design.md), §12). На других машинах путь не проверялся.
- DuckDB по умолчанию: 8 потоков, лимит памяти 20GB, временные файлы до 40GB в `artifacts/otto/.spill`. Флаги `--threads` и `--memory` есть у `load`, `collect`, `collect-holdout`, `fold-stats`, `rehearse-frame` и у команд агента `calibrate`, `probe`, `sidecar`, `leakcheck`. У `otto_model.py`, `otto2_dev.py` и `otto2_pool.py` их нет. Таблицы агента считаются в один поток.
- CLI `claude` (Claude Code) с выполненным входом. Он нужен только для шага `run`, модель — `claude-opus-5-5`.
- CLI `kaggle` с настроенным токеном. У автора версия 2.2.4 (`docs/otto-run/kaggle-competition-snapshot.txt`); как она была установлена, не записано. Правила соревнования нужно принять на сайте Kaggle.

Память и диск по журналам:
- `load` — пик 9.5 ГБ. Обучение B и оценка — 4.7 ГБ.
- Leakcheck итерации `i2` на всей популяции F3 потребовал около 150 ГБ, и система его сняла. Поэтому в `i2` и `i3` leakcheck идёт по частям.
- Пик памяти финального обучения на всей F4 не записан. У автора на 36 ГБ оно прошло для `i1`, `i2` и `i3`.
- Диск у автора (`du`, без `sealed/`):
  - сырые файлы ≈14 ГБ (архив 2.08 ГБ и распакованные 11.89 ГБ);
  - `artifacts/otto` — 25 ГБ: сайдкары 9.9, kaggle 5.6, fits 2.6, таблицы 2.4, загрузка 1.4;
  - `artifacts/otto3` — 68 ГБ: `i1` 7.3 ГБ после удаления сайдкаров F4 и F5, `i2` 50 ГБ (из них сайдкары 45 ГБ), `i3` 11 ГБ к 25.10. После финальной модели `i3` (25.10, 08:20) — 119 ГБ, из них `i3` 62 ГБ с сайдкарами F4 и F5. 25.10 после сдачи `i3` parquet-файлы всех сайдкаров `i2` и `i3` удалены по просьбе владельца (101 ГБ), квитанции `sidecar.json` оставлены; осталось 18 ГБ. Сайдкары пересобираются `agent sidecar`.
- Сайдкары законченной итерации можно удалить: они пересобираются командой `agent sidecar`.

## Данные

Ожидаемые файлы в `data/raw-otto-kaggle/`, размеры в байтах ([otto-design.md](otto-design.md), §1):

| Файл | Байт |
|---|---|
| `otto-recommender-system.zip` | 2 080 714 974 |
| `train.jsonl` | 11 307 535 945 |
| `test.jsonl` | 402 090 304 |
| `sample_submission.csv` | 183 898 350 |

SHA-256 архива: `fb88d6b02968abef8a62d2f895c9beb3fc14c4a378066aed63914c0b1242fed1`.

Команда, которой автор скачал архив, не записана. Ниже — стандартная форма Kaggle CLI. Архив нужно оставить на месте: `load` сверяет его размер и SHA-256. Файл `otto.zip.sha256` исключён из Git; `load` читает из него первое слово, 64 hex-символа. Значение ниже взято из контракта.

```bash
mkdir -p data/raw-otto-kaggle
kaggle competitions download -c otto-recommender-system -p data/raw-otto-kaggle
unzip -n data/raw-otto-kaggle/otto-recommender-system.zip -d data/raw-otto-kaggle
echo "fb88d6b02968abef8a62d2f895c9beb3fc14c4a378066aed63914c0b1242fed1  otto-recommender-system.zip" > data/raw-otto-kaggle/otto.zip.sha256
```

## Что откажет на клоне

Часть шагов выполняется один раз, и их квитанции уже закоммичены. На чистом клоне эти команды откажут:
- `otto_data.py collect-holdout`. Окно F4 закрыто закоммиченной квитанцией `otto-holdout-open.json` (`holdout_window_open` в `scripts/otto_common.py`). У автора окно было открыто между коммитами `90cf414` (prereg) и `c361185` (квитанция holdout-open). Как пересобрать F4 на клоне, не установлено. Сборка с той ревизии и перенос на текущий код не проверялись.
- Без коллекции `artifacts/otto/collections/holdout-F4` нельзя выполнить всё, что учится или оценивается на F4:
  - holdout-fits OTTO-1 и final OTTO-1;
  - `f4all-*` OTTO-2;
  - финальные модели OTTO-3;
  - следовательно, и файлы Kaggle.

  Эти шаги повторяются только с артефактами автора.
- `gate`, `holdout-open` и `holdout` пишут квитанции в `configs/datasets/` один раз.
- Нельзя использовать имена, которые уже заняты журналом:
  - `calibrate --name cal1` откажет сразу, потому что `docs/otto-run/calibration-cal1.json` есть;
  - `leakcheck` с именем, отчёт которого уже лежит в журнале, тоже откажет сразу. У OTTO-1 заняты `lc-F3`, `lc-F3b`, `lc-F3c` и `lc-F4`, у `i1` — `lc-F3`, у `i2` и `i3` — части `lc-F3-p*`;
  - `run --name run-a1` и `o3 run --name run-<ID>` откажут только в конце. Журналы `docs/otto-run/run-a1/` и `docs/otto3-run/<ID>/run-<ID>/` закоммичены. `run_loop` копирует журнал (`_copy_journal` в `scripts/otto_agent.py`) после последнего раунда и отказывает, если файл журнала уже есть с другим содержимым. Прогон пройдёт целиком, со всеми вызовами `claude -p`, и получит статус `failed`.

  Для повтора нужны новые имена, например `cal2`, `lc-F3r`, `run-a1r` и `run-<ID>-r`. Новые отчёты и журналы появятся в `docs/` как неотслеживаемые файлы.
- `freeze` нового прогона агента откажет: закоммиченный набор отличается от нового.
- `audit` откажет и на закоммиченном наборе. Вердикт вписывается только в набор, который не совпадает со своей версией в `HEAD` (`require(not oc.committed_clean(output), ...)` в `audit`, `scripts/otto_agent.py`). У закоммиченного набора аудит к тому же уже записан.

На клоне без артефактов автора по коду должны повторяться следующие шаги; на чистом клоне это не проверялось:
- загрузка;
- коллекции F2, F3, проба и F5;
- база B;
- leakcheck F3 под новым именем;
- сайдкары F2, F3 и F5;
- dev-серия OTTO-1;
- dev-замеры OTTO-2;
- быстрые замеры OTTO-3 (обучение на F2, оценка на F3).

## Загрузка и коллекции

```bash
.venv/bin/python -I scripts/otto_data.py load
.venv/bin/python -I scripts/otto_data.py collect --role train
.venv/bin/python -I scripts/otto_data.py collect --role val
.venv/bin/python -I scripts/otto_data.py collect --role probe
```

- `load` выполняется один раз:
  - сверяет размеры файлов и SHA-256 архива;
  - пишет дневные партиции;
  - проверяет гейт 0: числа README соревнования в пределах 1 %;
  - пишет квитанцию `data/raw-otto-kaggle/otto-verify.json`.

  Если квитанция или партиции уже есть, `load` отказывает.
- `collect` берёт закоммиченную базу `configs/datasets/otto-base.json` и пишет коллекции `artifacts/otto/collections/train-F2`, `val-F3` и `probe-F3`. Существующий каталог не перезаписывается.
- Коллекция F5 (`collect --role kaggle`) открывается только после закоммиченного результата holdout. На клоне он уже закоммичен.
- Необязательные замеры: `fold-stats --fold 2|3` и `rehearse-frame --fold 3` (репетиция полного кадра).

## База B

```bash
.venv/bin/python -I scripts/otto_model.py smoke
.venv/bin/python -I scripts/otto_model.py fit --base-dev it0 --base configs/datasets/otto-base.json
```

`smoke` — один fit для orders на признаках B и шумовых колонках. Затем `fit --base-dev` обучает B и оценивает её на dev F3; результат пишется в `artifacts/otto/base-dev/it0/`. Ожидается Score: B 0.4778, Pop 0.4667, потолок кандидатов 0.4824. B заморожена на итерации 0, поэтому база в Git совпадает с начальной (`otto_data.py init-base` строит её из констант). Проверка — в разделе «Проверка без переобучения».

## OTTO-1

### Агент и аудит

```bash
.venv/bin/python -I scripts/otto_agent.py calibrate --name cal2
.venv/bin/python -I scripts/otto_agent.py probe --name probe1
.venv/bin/python -I scripts/otto_agent.py run --probe artifacts/otto/probe/probe1 --name run-a1r
.venv/bin/python -I scripts/otto_agent.py freeze --run artifacts/otto/run/run-a1r
.venv/bin/python -I scripts/otto_agent.py audit --report docs/otto-run/audit-run-a1r.json
```

- `calibrate` пишет `docs/otto-run/calibration-<имя>.json`. У автора имя `cal1`, на клоне нужно новое. `probe` берёт единственную калибровку или ту, что указана в `--calibration`.
- `run` вызывает `claude -p`. У автора было 6 вызовов на $1.80 по оценке клиента. Журнал автора — `docs/otto-run/run-a1/`; имя `run-a1` на клоне занято, отсюда `run-a1r`.
- `freeze` пишет `configs/datasets/otto-set.json` и копирует журнал. На клоне `freeze` и `audit` откажут: см. «Что откажет на клоне».
- Аудит SQL делает независимый ревьюер, скрипта для этого нет. Его вывод — JSON формата `otto-audit-v1` с пунктами `hidden_encoding`, `addressed_oracle` и `recognizability`. `audit --report` вписывает вердикт в набор до коммита набора.
- `export` (необязательно) записывает представления и файлы партиций F2 и F3 с SHA-256, ничего не копируя. Следующие шаги его не читают.
- Prereg (`configs/datasets/otto-prereg.json`) собран генератором вне репозитория, поэтому используется закоммиченный файл. Отклонения d1–d5 (`otto-deviations.json`) уже внесены в код.

### Leakcheck F3, сайдкары и dev-серия

```bash
.venv/bin/python -I scripts/otto_agent.py leakcheck --fold 3 --name lc-F3r
.venv/bin/python -I scripts/otto_agent.py sidecar --collection artifacts/otto/collections/val-F3 --name sc-val-F3
.venv/bin/python -I scripts/otto_agent.py sidecar --collection artifacts/otto/collections/train-F2 --name sc-train-F2
for a in B BA BApl; do .venv/bin/python -I scripts/otto_model.py fit --series dev --arm $a --seed 2026; done
for a in B BA BApl; do .venv/bin/python -I scripts/otto_model.py evaluate --series dev --arm $a --seed 2026; done
.venv/bin/python -I scripts/otto_model.py contrast
```

- Отчёт leakcheck автора, на который ссылается prereg, — `docs/otto-run/lc-F3c.json` (ok).
- Сайдкары требуют закоммиченный prereg и чистый аудит набора.
- `contrast` пишет `artifacts/otto/contrast/<метка>/contrast.json`. Сравнение — с `docs/otto-run/contrast-dev-2026.json`: Score B 0.4778, BA 0.5633, BApl 0.5095; BA − B = +0.0855 [0.0838; 0.0873].

### Holdout (только с артефактами автора)

Цепочка автора, по журналу [otto.md](otto.md), §8. На клоне первая команда откажет:

```bash
.venv/bin/python -I scripts/otto_data.py collect-holdout
.venv/bin/python -I scripts/otto_agent.py sidecar --collection artifacts/otto/collections/holdout-F4 --name sc-holdout-F4
.venv/bin/python -I scripts/otto_model.py gate --kind power --contrast artifacts/otto/contrast/<метка>/contrast.json
.venv/bin/python -I scripts/otto_agent.py leakcheck --fold 4 --name lc-F4
for a in B BA BApl; do
  .venv/bin/python -I scripts/otto_model.py fit --series holdout --arm $a --seed 2026
  .venv/bin/python -I scripts/otto_model.py evaluate --series holdout --arm $a --seed 2026
done
.venv/bin/python -I scripts/otto_model.py gate --kind 1 --leakcheck artifacts/otto/leakcheck/lc-F3c/report.json artifacts/otto/leakcheck/lc-F4/report.json
.venv/bin/python -I scripts/otto_model.py holdout-open --gate artifacts/otto/gate/<gate1-s1-метка>/gate.json --quote "<фраза владельца>" --quote-time <время>
.venv/bin/python -I scripts/otto_model.py holdout
```

- Этап 2 устроен так же. Сначала holdout-fits и оценки с зерном 2027. Затем `gate --kind 1 --stage 2` (leakcheck наследуется), `holdout-open --stage 2` и `holdout --stage 2`.
- Фраза владельца, время, путь и SHA-256 гейта записаны в `configs/datasets/otto-holdout-open.json` и `otto-holdout-open-2.json`.

### Final и файлы Kaggle (только с артефактами автора)

```bash
.venv/bin/python -I scripts/otto_model.py final-sessions
.venv/bin/python -I scripts/otto_data.py collect --role kaggle
.venv/bin/python -I scripts/otto_agent.py sidecar --collection artifacts/otto/collections/kaggle-F5 --name sc-kaggle-F5
for s in 2026 2027; do for a in B BA; do
  .venv/bin/python -I scripts/otto_model.py fit --series final --arm $a --seed $s
  .venv/bin/python -I scripts/otto_model.py score --arm $a --seed $s
done; done
for x in B2026 BA2026 B2027 BA2027; do
  .venv/bin/python -I scripts/otto_data.py assemble --ranked artifacts/otto/fits/final-$x/eval/ranked.parquet --output artifacts/otto/kaggle/$x/$x.csv
done
.venv/bin/python -I scripts/otto_model.py gate --kind 2 --stage 1
.venv/bin/python -I scripts/otto_model.py gate --kind 2 --stage 2
```

- Обучающие сессии final уже покрыты сайдкаром holdout-F4. Поэтому `sidecar --final-training` у автора отказал («Every requested session already has a sidecar»), и отдельного сайдкара нет.
- Оценки Kaggle читаются командой `otto_model.py reading --private <JSON>`. Ключи JSON: B2026, BA2026, B2027 и BA2027. Нужен пройденный гейт 2. Результат у автора — `docs/otto-run/kaggle-reading.json`.

## OTTO-2

Dev-замеры (F2 → F3, BA, зерно 2026). По коду они должны повторяться на клоне; на чистом клоне это не проверялось:

```bash
.venv/bin/python -I scripts/otto2_dev.py --name n12k --n-t 12500
.venv/bin/python -I scripts/otto2_dev.py --name n25k --n-t 25000
.venv/bin/python -I scripts/otto2_dev.py --name neg60 --negatives 60
.venv/bin/python -I scripts/otto2_dev.py --name it1000 --iterations 1000
.venv/bin/python -I scripts/otto2_dev.py --name d10-it1000 --iterations 1000 --depth 10
.venv/bin/python -I scripts/otto2_dev.py --name lr10-it1000 --iterations 1000 --learning-rate 0.1
.venv/bin/python -I scripts/otto2_dev.py --name lr10-it2000 --iterations 2000 --learning-rate 0.1
```

Итоги пишутся в `artifacts/otto/otto2-dev/<имя>/summary.json`. Ожидаемые Score F3 — в таблице [otto2.md](otto2.md), например `lr10-it1000` 0.5644.

Финальная модель на всех размеченных сессиях F4, покрытых сайдкаром. Нужны артефакты автора:

```bash
.venv/bin/python -I scripts/otto2_pool.py fit --name f4all-lr10-it2000 --source 4:all --iterations 2000 --learning-rate 0.1
.venv/bin/python -I scripts/otto2_pool.py evaluate --name f4all-lr10-it2000 --fold 3
.venv/bin/python -I scripts/otto2_pool.py evaluate --name f4all-lr10-it2000 --fold 5
.venv/bin/python -I scripts/otto_data.py assemble --ranked artifacts/otto/otto2-pool/f4all-lr10-it2000/eval-F5/ranked.parquet --output artifacts/otto/kaggle/otto2-f4all-lr10-it2000/f4all-lr10-it2000.csv
```

- Ожидается Score F3 0.5653. SHA-256 `.csv` — `401fdb1250635e72e43b60eaf546243cfbc297ff4458aec6320b41c97de6a5de`. Private 0.58049.
- Вторая посылка, `f4all-it1000`, собирается так же: `fit --name f4all-it1000 --source 4:all --iterations 1000`. Её Score F3 0.5644, private 0.58015.
- Сравнения с моделями OTTO-1: `evaluate --name f4n50-it500 --fold 3 --models artifacts/otto/fits/final-BA2026` и `f4n50-ens2` с двумя `--models` (final-BA2026 и final-BA2027).

## OTTO-3

Итерации различаются числом раундов и повтором (`ITERATIONS` в `scripts/otto3.py`):
- `i1` — 8 раундов, из них 4 на таблицы и источники, до 10 источников, до 300 кандидатов, без повтора;
- `i2` — 12 раундов (6 на таблицы и источники), до 14 источников, повтор `i1`;
- `i3` — 16 раундов (6 на таблицы и источники), до 14 источников, повтор `i2`.

Выходы пишутся в `artifacts/otto3/<ID>/`. Коллекции, калибровка, проба, smoke и гейты — символические ссылки на каталоги OTTO-1, только для чтения. Набор итерации — `configs/datasets/otto3-<ID>-set.json`, журнал — `docs/otto3-run/<ID>/`. Без `setup` остальные команды отказывают.

Функция для краткости (работает в bash и zsh):

```bash
IT=i1
o3() { .venv/bin/python -I scripts/otto3.py --iteration "$IT" "$@"; }
o3 setup
```

### Прогон агента, заморозка и аудит

```bash
o3 run --probe artifacts/otto/probe/probe1 --name run-$IT-r
o3 agent freeze --run artifacts/otto3/$IT/run/run-$IT-r
o3 agent audit --report docs/otto3-run/$IT/audit-run-$IT-r.json
```

- `run` для `i2` и `i3` сначала повторяет закоммиченный набор предыдущей итерации без LLM, потом вызывает `claude -p` в новых раундах. Расход по оценке клиента: `i1` 8 вызовов, $2.34; `i2` 12 вызовов, из них 8 повторов, $1.75; `i3` $2.78.
- Автор называл прогоны `run-<ID>`; на клоне эти имена заняты журналами, отсюда `run-<ID>-r`.
- Повтор прогона на клоне не проверялся. На клоне `freeze` откажет, потому что набор итерации уже закоммичен с другим содержимым, и `audit` тоже откажет (см. «Что откажет на клоне»). Аудит, как и в OTTO-1, делает независимый ревьюер.
- После аудита автор коммитил набор. Следующие шаги требуют закоммиченный набор с чистым аудитом.

### Leakcheck F3

```bash
o3 agent leakcheck --fold 3 --name lc-F3r                                       # так шёл i1
o3 leakcheck-parts --parts 4 --name lc-F3r && o3 leakcheck-summary --parts 4 --name lc-F3r   # i2; у i3 --parts 6
```

- Автор использовал имя `lc-F3`; на клоне оно занято, отсюда `lc-F3r`.
- `leakcheck-parts` вызывает leakcheck OTTO-1 на последовательных частях популяции F3 в sha256-порядке. Флаг `--only I` запускает одну часть. `leakcheck-summary` сверяет, что части вместе — ровно популяция F3 на одном наборе, коллекции и коде, и пишет `docs/otto3-run/<ID>/<имя>-parts.json`.

### Сайдкары и быстрый замер

```bash
o3 agent sidecar --collection artifacts/otto3/$IT/collections/val-F3 --name sc-val
o3 agent sidecar --collection artifacts/otto3/$IT/collections/train-F2 --name sc-train
o3 pool fit --name f2n50-lr10-it1000 --source 2:50000 --iterations 1000 --learning-rate 0.1
o3 pool evaluate --name f2n50-lr10-it1000 --fold 3
```

- Быстрый замер: обучение на F2, 50 000 сессий на тип, оценка на популяции F3. Ожидается Score F3 0.5759 у `i1`, 0.5783 у `i2` и 0.5795 у `i3`.
- Проба негативов у `i1` — тот же `pool fit` с `--negatives 100` и именем `f2n50-lr10-it1000-neg100`; ожидается 0.5748.

### Финальная модель (только с артефактами автора)

```bash
o3 agent sidecar --collection artifacts/otto3/$IT/collections/holdout-F4 --name sc-holdout
o3 agent sidecar --collection artifacts/otto3/$IT/collections/kaggle-F5 --name sc-kaggle
o3 pool fit --name f4all-lr10-it2000 --source 4:all --iterations 2000 --learning-rate 0.1
o3 pool evaluate --name f4all-lr10-it2000 --fold 3
o3 pool evaluate --name f4all-lr10-it2000 --fold 5
o3 data assemble --ranked artifacts/otto3/$IT/otto2-pool/f4all-lr10-it2000/eval-F5/ranked.parquet --output artifacts/otto3/$IT/kaggle/$IT-f4all-lr10-it2000/$IT-f4all-lr10-it2000.csv
o3 check-shared
```

- Ожидается Score F3 0.5777 у `i1`, 0.5802 у `i2` и 0.5810 у `i3`.
- У `i3` обучение на `4:all` прошло за 2 ч 45 мин; запасной `--source 4:700000` из [otto3.md](otto3.md) не понадобился.
- `check-shared` проверяет, что общие файлы OTTO-1 не менялись с момента `setup`.
- `i3` завершён 25.10: F3 0.5810, посылка ref 57617218, private 0.59628 ([otto3.md](otto3.md)). Это последняя итерация.

## Сборка файла и посылка

`assemble` пишет `.csv` и квитанцию со SHA-256 и числом сессий, дополненных из Pop (у всех посланных файлов 0). Как автор сжимал файлы, не записано. Заголовки `.gz` на диске автора:
- у четырёх файлов OTTO-1, у `i2` и `i3` в заголовке есть имя файла и время изменения, то есть сжатие шло без `-n`;
- у двух файлов OTTO-2 и у `i1` имени нет, время нулевое.

Исходных `.csv` у `i1` и `i2` на диске автора нет (у `i3` есть), остались `.gz` и квитанции `assemble`. Поэтому SHA-256 `.csv` сверяется по распакованному потоку. Одна из возможных форм сжатия и сверки:

```bash
gzip -k artifacts/otto3/i2/kaggle/i2-f4all-lr10-it2000/i2-f4all-lr10-it2000.csv
gzip -dc artifacts/otto3/i2/kaggle/i2-f4all-lr10-it2000/i2-f4all-lr10-it2000.csv.gz | shasum -a 256
```

`docs/otto-run/kaggle-files.csv` содержит размер и SHA-256 и `.csv`, и `.csv.gz` четырёх файлов OTTO-1. SHA-256 посланных `.gz` OTTO-2, `i1`, `i2` и `i3` записаны в [otto2.md](otto2.md) и [otto3.md](otto3.md). Они опознают посланный файл, но повторное сжатие может дать другой хеш.

Посылка и выгрузка оценок:

```bash
kaggle competitions submit -c otto-recommender-system -f artifacts/otto3/i2/kaggle/i2-f4all-lr10-it2000/i2-f4all-lr10-it2000.csv.gz -m "<описание>"
kaggle competitions submissions -c otto-recommender-system --csv
```

- Описания посылок автора лежат в CSV оценок и содержат начало SHA-256 файла. Пример: `OTTO task1-v2 B2026 (sha256 csv 2c9da2717ae1); post-hoc d3`.
- Первая строка CSV оценок у автора — время выгрузки в UTC; как именно она дописывалась, не записано. В `docs/otto3-run/otto3-kaggle-scores.csv` это `# 2026-10-24T02:44:59Z` — время первой выгрузки, после посылки `i1`. Строку `i2` дописали позже (коммит `0cf0221`), а первую строку не обновили.
- Журналы посылок: `docs/otto-run/kaggle-submit-log.txt` и `docs/otto3-run/kaggle-submit-log.txt`. Оценки: `docs/otto-run/kaggle-scores.csv`, `otto2-kaggle-scores.csv` и `docs/otto3-run/otto3-kaggle-scores.csv`.

## Проверка без переобучения

**Код, prereg и наборы.** Нужен только клон без данных. Команды проверяют:
- что prereg закоммичен и код совпадает с prereg или с последним отклонением;
- что набор закоммичен, аудит чистый, а digest пересчитывается из предложений;
- для OTTO-3 — ещё и что digest промпта совпадает.

```bash
.venv/bin/python -I -c "
import sys; sys.path.append('.')
from scripts import otto_common as oc, otto_agent as oa, otto_data as od
oc.require_prereg(check_code=True)
r = oa.read_set(base=oc.read_base()); oc.require_clean_audit(r)
print('otto-1', r['digest'][:12], len(r['proposals']), r['digest'] == oa.set_digest(r['proposals']))
print('base', oc.read_base()['digest'][:12], od.initial_base()['digest'] == oc.read_base()['digest'])"
for it in i1 i2 i3; do .venv/bin/python -I -c "
import sys; sys.path.append('.')
from scripts import otto3, otto_agent as oa, otto_common as oc
otto3.configure(sys.argv[1]); otto3.require_prereg3(check_code=True)
r = oa.read_set(base=oc.read_base()); oc.require_clean_audit(r)
print(sys.argv[1], r['digest'][:12], len(r['proposals']), r['digest'] == oa.set_digest(r['proposals']), r['prompt_digest'] == oa.prompt_identity()['digest'])" $it; done
```

Ожидаемый вывод (проверен на ветке `task1-v2` 25.10):

```text
otto-1 cda530622f63 24 True
base 4b50037532aa True
i1 4cf115547219 33 True True
i2 885d50c0384e 51 True True
i3 4534c94a4df5 71 True True
```

Колонок в наборах: OTTO-1 — 39, `i1` — 66, `i2` — 96, `i3` — 141.

**Популяция dev.** После `collect --role val` это секунды, обучения не требуется. Ожидается `populations.dev.sessions_digest` из prereg: `05a49effa11215282d71a99de802e80d347ca0ec25d5171596629b9beb1b74f7`.

```bash
.venv/bin/python -I -c "
import sys; sys.path.append('.')
from pathlib import Path; from scripts import otto_common as oc
print(oc.sessions_digest(oc.read_population(Path(oc.collection_dir('val')).resolve())))"
```

**Журналы прогонов.** Что лежит в журналах:
- `docs/otto-run/run-a1/` и `docs/otto3-run/<ID>/run-<ID>/` — промпты, ответы модели, `log.jsonl` и `run.json` (вызовы, время, оценка стоимости);
- `audit-run-*.json` — вердикты аудита;
- `lc-*.json` — отчёты leakcheck;
- `gate*.json` — гейты OTTO-1.

Предложения в наборах `configs/datasets/` выводятся из этих ответов. Повтор в `i2` и `i3` виден в журнале как раунды без вызова модели.

**Score F3 и бутстрап шагов.** Нужны артефакты автора:
- для каждой руки — `eval-F3/ranked.parquet`, `eval-F3/report.json` и `eval-F5/report.json` финальной модели `f4all-lr10-it2000` (OTTO-2 — в `artifacts/otto/otto2-pool/`, OTTO-3 — в `artifacts/otto3/<ID>/otto2-pool/`);
- метки коллекции `val-F3`.

Руки OTTO-2, `i1` и `i2` обязательны: без оценки F3 любой из них скрипт откажет. Рука `i3` входит, когда есть её `eval-F3/report.json`, и тогда ей тоже нужен `eval-F5/report.json`. Без оценки F3 скрипт печатает, что `i3` пропущена.

Скрипт сверяет SHA-256 каждого `ranked.parquet` с его `report.json`, а модели оценки F3 — с моделями `eval-F5/report.json`: списки F3 должны идти от модели, файл которой послан в Kaggle. Score пересчитывается с допуском 1e-12. Потом скрипт считает парный бутстрап: 2000 повторов, зерно 2026.

Без `--output` результат пишется в закоммиченную квитанцию `docs/otto3-run/ladder-ci-F3.json`. Если содержимое без `created_utc` отличается, скрипт отказывает; `--force` перезаписывает квитанцию. Для проверки результат пишется в отдельный файл и сравнивается с закоммиченным без `created_utc`. Старый `/tmp/ladder-ci-F3.json` с другим содержимым скрипт тоже не перезапишет, поэтому перед повтором его нужно удалить.

```bash
.venv/bin/python -I scripts/otto3_ladder_ci.py --threads 2 --output /tmp/ladder-ci-F3.json
.venv/bin/python -I -c "
import json, sys
a, b = (json.load(open(p, encoding='utf-8')) for p in sys.argv[1:])
for d in (a, b): d.pop('created_utc', None)
print(sorted(b['arms']), a == b)" docs/otto3-run/ladder-ci-F3.json /tmp/ladder-ci-F3.json
```

- Ожидаемые Score: OTTO-2 0.565256, `i1` 0.577732, `i2` 0.580152, `i3` 0.581049.
- Ожидаемые шаги: `i1` − OTTO-2 +0.0125 [+0.0115, +0.0134]; `i2` − `i1` +0.0024 [+0.0018, +0.0030]; `i2` − OTTO-2 +0.0149 [+0.0139, +0.0159]; `i3` − `i2` +0.0009 [+0.0004, +0.0014]; `i3` − OTTO-2 +0.0158 [+0.0148, +0.0168].
- Закоммиченный файл уже содержит руку `i3`. Если повторить скрипт без артефактов `i3`, руки `i3` не будет, и сравнение даст `False`.
- Повторный прогон скрипта в рамках этой инструкции не делался.

**Файлы Kaggle.** SHA-256 `.csv` сверяется с записанными значениями. Если остался только `.csv.gz`, хеш считается по распакованному потоку: `gzip -dc FILE.csv.gz | shasum -a 256`. Хеш самого `.gz` для сверки не годится: см. «Сборка файла и посылка».
- OTTO-1 — `docs/otto-run/kaggle-files.csv` (B2026 `2c9da271…`, BA2026 `3177b1d9…`, B2027 `31677f7b…`, BA2027 `c3f5bf25…`);
- OTTO-2 `f4all-lr10-it2000` — `401fdb12…`;
- `i1` — `b3bdde81d6f1f563d0d3d8c8e411f7498545e3f13ee225f31b0aabfddcfa3c1d`;
- `i2` — `7506449eac83fab86ff3c146bdb44a001df65ab9660fdb542288df970e298e52`;
- `i3` — `eabc0634ed408c7e9d35930711081edc1495ff9b9886fa5fe42de7eb5704b98d` (у `i3` есть и сам `.csv`).

25.10 на файлах автора `gzip -dc` у `i1` и `i2` дал ровно эти хеши.

Оценки private: OTTO-1 BA — 0.57878 в среднем по двум зёрнам, OTTO-2 — 0.58049, `i1` — 0.59299, `i2` — 0.59548, `i3` — 0.59628.

**Тесты.** Тесты синтетические, данные OTTO им не нужны. В рамках этой инструкции они не запускались.

```bash
.venv/bin/python -m unittest tests.test_otto_common tests.test_otto_data tests.test_otto_agent tests.test_otto_model tests.test_otto2_pool tests.test_otto3
```

## Время шагов

Время по часам на машине автора. Источники: квитанции шагов и журналы [otto.md](otto.md), [otto2.md](otto2.md), [otto3.md](otto3.md).

| Шаг | Время |
|---|---|
| `load` | 57 с |
| коллекции train-F2, val-F3, probe-F3 | 4–7 с каждая; holdout-F4 — 19 с |
| smoke; B, итерация 0 (fit и оценка) | 85 с; 180 с |
| калибровка | ≈28 с |
| прогон агента | `run-a1` 10.6 мин; `i1` 17 мин; `i2` 18.5 мин; `i3` 21 мин |
| leakcheck F3 | OTTO-1 7–10 мин; `i1` 24 мин; одна часть у `i2` и `i3` ≈15 мин |
| сайдкары OTTO-1 | train-F2 2.5 мин, val-F3 3 мин, holdout-F4 11 мин, kaggle-F5 18 мин |
| dev OTTO-1: fit / оценка одной руки | 2.5–4 мин / 0.5–2 мин |
| final OTTO-1: fit / score F5 / assemble одного файла | 2.5–4.5 мин / 3–12 мин / 1.5–2 мин |
| dev-замер OTTO-2: обучение / оценка на F3 | 68–924 с (1–15 мин) / 107–141 с; всего 3–18 мин на замер |
| OTTO-2 `f4all-it1000` / `f4all-lr10-it2000`, обучение | 54 мин / 1 ч 45 мин |
| оценка на F3 / на F5 | 2–8 мин / 14–57 мин (верх — `i3`) |
| быстрый замер OTTO-3, обучение | 9–10 мин |
| сайдкары OTTO-3 F4 и F5 | `i1`: F5 40 мин; `i2`: F4 и F5 вместе ≈2.5 ч |
| финальная модель OTTO-3, обучение | `i1` 2 ч 3 мин; `i2` 3 ч 7 мин; `i3` 2 ч 45 мин |

Итого:
- тяжёлые шаги OTTO-1 после prereg — около 3 ч;
- финальная модель OTTO-2 — около 2 ч;
- итерация `i1` целиком — около 5 ч;
- итерация `i2` — около 8 ч.

## Документы

- [otto-design.md](otto-design.md) — контракт: данные, складки, рецепт, гейты, ресурсы.
- [otto-base-log.md](otto-base-log.md) — база B и её заморозка.
- [otto.md](otto.md) — журнал OTTO-1: агент, leakcheck, prereg, затраты, holdout, final, Kaggle.
- [otto2.md](otto2.md) — замеры ранкера и посылки OTTO-2.
- [otto3.md](otto3.md) — итерации `i1`–`i3`, правило продолжения и бутстрап шагов.
- `docs/otto-run/`, `docs/otto3-run/` — журналы прогонов, аудиты, leakcheck, гейты, посылки.
- [task1-reproduce.md](task1-reproduce.md) — то же для задачи 1 на REES46.
