# H&M: CPU-модели M23 и E46 для Kaggle late submission

`scripts/hm_kaggle.py` превращает закреплённые модели ручного M23 и автоматического E46 из [auto-holdout lock](../configs/datasets/hm-auto-holdout-lock.json) в файлы Kaggle late submission. Для этого достаточно CPU: Windows-GPU окружение не требуется. Закреплённые модули `hm_experiment`, `hm_retrieval`, `hm_feature_engine`, `hm_baseline` и `hm_eda` используются через import. Перед работой их SHA-256 сверяются с pins в lock, а сами файлы не меняются. Основной моделью остаётся M23. На customer-test E46 прироста не показала ([hm-auto-v2.md](hm-auto-v2.md)). Тестовая неделя Kaggle 23–29 сентября новая для обеих моделей.

Команды ниже выполнены на настоящих данных 20.10.2026; результаты и отклонения от команд — в разделе 9. Код также проверен синтетическими тестами `tests/test_hm_kaggle.py` на крошечной DuckDB.

Каждая команда, которая читает скачанные файлы, запускается так: `.venv/bin/python -I scripts/hm_kaggle.py` из корня checkout. Isolated mode не добавляет в `sys.path` рабочий каталог, каталог данных и `PYTHONPATH`, а скрипт добавляет только корень checkout, после стандартной библиотеки. `verify`, `eda` и `collect` без `-I` откажутся работать. Этот отказ лишь напоминание: модуль, подложенный в `PYTHONPATH`, выполнится ещё при import, и остановить его может только сам `-I`. Не вызывайте на этих данных `-m scripts.hm_eda` и другие модули напрямую. Ничего не запускайте и не импортируйте из каталогов с данными (`data/raw/`, `data/raw-hm-kaggle/`). Построчные выходы (DB, collections, модели, scores, submissions) разрешены только в ignored `artifacts/`. Каждый output должен быть новым; исключение — продолжение `score`. Инструмент не удаляет входные файлы и принятые результаты. После ошибки прочитайте JSON-сообщение и `manifest.json`/`report.json`, затем повторите запуск в новый output.

## 0. Окружение

Команды записаны для zsh/bash на macOS. На Windows используются те же аргументы с `.venv\Scripts\python.exe -I scripts\hm_kaggle.py`.

```zsh
cd ~/tlab-recsys-2026
hm() { .venv/bin/python -I scripts/hm_kaggle.py "$@"; }
.venv/bin/python -m unittest tests.test_hm_kaggle
```

Каждая подкоманда печатает в stdout одну JSON-строку, а прогресс и RSS пишет в stderr. Exit code 0 означает успех. Exit code 1 означает ошибку: печатается JSON со `status: failed`, зависимые шаги не запускайте. Ошибка в аргументах командной строки даёт такой же JSON (`error_type: UsageError`) и тоже exit code 1, а не usage argparse. Сообщения DuckDB и CatBoost в stdout не попадают, потому что могут цитировать строки данных. Подробности остаются в `manifest.json`/`report.json` внутри output, если он успел появиться. Превышение `--wall-seconds` печатается как `TimeoutError` с сообщением `Declared wall limit exceeded`, в том числе когда таймер прервал запрос DuckDB. Exit code 2 возвращают только `verify` и `eda`: байты отличаются от pins или не прошла проверка EDA.

У collect и score DuckDB работает в 4 потока (у score — `--threads`) с SQL cap 2GB, spill не больше 8GB, на диске output нужно минимум 10GiB свободного места. Тот же минимум проверяет assemble. EDA работает в 2 потока с SQL cap 4GB и spill до 32GB, поэтому `eda` требует 36GiB свободного места. CatBoost и pandas могут занять память сверх SQL cap. Закреплённый `hm_experiment` строит CatBoost Pool с `thread_count` по умолчанию (−1): пока Pool строится, ненадолго заняты все ядра, независимо от `--threads`. Закреплённый модуль не меняется, это нужно просто учитывать. Если на машине идёт другая тяжёлая задача, например CatBoost grid, запускайте fit и score после неё или уменьшайте `--threads` и `--chunk-users`. На диске нужно около 3,7 GB под CSV, место под архивы Kaggle, около 1,2 GB под DuckDB, до 32 GB под временный spill EDA и место под collections.

## 1. Загрузка с Kaggle

Token кладёт сам пользователь: `~/.kaggle/kaggle.json` с правами `chmod 600`. Агент этот файл не создаёт и не читает. На странице [соревнования](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations) нужно принять правила: без этого не работают ни загрузка, ни Late Submission. Kaggle CLI ставится в отдельный venv вне репозитория, чтобы project-окружение и `uv.lock` не менялись.

```zsh
python3 -m venv ~/.venvs/kaggle-cli
~/.venvs/kaggle-cli/bin/pip install kaggle
(
  mkdir data/raw-hm-kaggle || exit 1
  for f in articles.csv customers.csv transactions_train.csv; do
    ~/.venvs/kaggle-cli/bin/kaggle competitions download -c h-and-m-personalized-fashion-recommendations \
      -f "$f" -p data/raw-hm-kaggle || exit 1
  done
) || echo "DOWNLOAD FAILED"
ls -l data/raw-hm-kaggle
```

Загрузка идёт в subshell: первая ошибка `mkdir` или загрузки завершает его, и печатается `DOWNLOAD FAILED`. `set -e` здесь не годится: слева от `||` bash и zsh его игнорируют, поэтому у каждой команды стоит `|| exit 1`. Если каталог уже существует, `mkdir` без `-p` завершится ошибкой и загрузка не начнётся: файлы ложатся только в новый пустой каталог. Он лежит вне `data/raw/`, где хранятся исходные файлы REES46. Нужны три CSV. Изображения, `sample_submission.csv` и полный архив соревнования не нужны. CLI сохраняет файл либо как `<name>.zip` с одним CSV внутри, либо как сам CSV. `verify` принимает оба варианта, поэтому вручную архивы не распаковывайте.

Повреждённый архив (`verify` сообщает `damaged or unreadable`, например `BadZipFile`) или файл меньше pinned-размера означает неполную загрузку: скачайте заново в другой новый каталог. `--allow-unpinned` (раздел 2) допустим только для файлов полного размера, у которых отличается хеш.

## 2. Проверка байтов

```zsh
hm verify --raw-dir data/raw-hm-kaggle
```

Найденный CSV хешируется целиком. Если CSV нет, `verify` распаковывает рядом `<name>.zip`. Архив должен содержать ровно один член с этим именем, без путей и шифрования. Заявленный размер не может превышать двойной pinned-размер, а на диске нужен запас размер+2GiB. Распаковка идёт в `<name>.part`, после неё файл переименовывается. Результат сравнивается с размерами и SHA-256 из [hm-source.json](../configs/datasets/hm-source.json). Там записаны байты Microsoft mirror, на которых сделаны все GPU-прогоны. Квитанция — `data/raw-hm-kaggle/kaggle-verify.json`, архивы остаются на месте.

- Exit code 0, `complete`: файлы Kaggle побайтно равны зеркалу. Заодно это первая независимая проверка равенства зеркала оригиналу; в [отчёте](hm-report.md) она числится как неустановленная.
- Exit code 2, `mismatch`: остановитесь. Квитанция показывает, какой файл отличается; сравните его `size` с `pinned_size`. Файл меньше pin недокачан: повторите раздел 1 в новый каталог. Для файла полного размера с другим хешем дальше только по отдельному решению. Можно загрузить pinned mirror через `scripts.hm_download` в другой новый каталог ([hm-reproduce.md](hm-reproduce.md), раздел 1). Можно запустить EDA с `--allow-unpinned` и пометить все дальнейшие числа как полученные на незакреплённых данных.
- Exit code 1: например, лишний член архива, отсутствующий файл или `<name>.part` после прерванной распаковки. Повреждённый архив описывается фиксированным текстом с одним лишь типом ошибки (`<name>.zip is damaged or unreadable (BadZipFile)`). Текст из самого архива не попадает ни в stdout, ни в квитанцию. Такой архив скачайте заново в новый каталог. Чужой partial инструмент не принимает и не удаляет. Проверьте и уберите его вручную, затем повторите `verify`.

## 3. EDA и DuckDB

```zsh
hm eda --raw-dir data/raw-hm-kaggle --output artifacts/hm-kaggle/eda
DB=artifacts/hm-kaggle/eda/audit.duckdb
```

`eda` запускает закреплённый `hm_eda.run` (2 потока, SQL cap 4GB, spill до 32GB). Если на диске output меньше 36GiB свободного места, EDA откажется, ничего не записав. Без завершённой квитанции verify EDA не запускается. Перед загрузкой в DuckDB EDA заново хеширует все три CSV и сверяет их с квитанцией: файл, изменённый после проверки, остановит EDA, даже если размер и mtime прежние. Exit code 0 означает, что прошли все проверки `hm_eda` и в таблицах ровно 31 788 324 покупки, 1 371 980 клиентов и 105 542 товара. `summary.json` и `report.md` — агрегированный отчёт.

`kaggle-source.json` рядом с DB записывает `valid`, `pinned_sources`, `allow_unpinned`, SHA-256 и размер `audit.duckdb`, а также SHA-256 квитанции verify. `collect`, `score` и `assemble` читают этот файл рядом с DB, сверяют SHA-256 DB и отказываются работать, если `valid: false`; такую DB `eda` отмечает exit code 2. `pinned_sources` и `allow_unpinned` они переносят в `manifest.json`, `plan.json` и квитанцию submission. Переносите DB только вместе с этим файлом.

## 4. Недельные collections

```zsh
C=artifacts/hm-kaggle/collections
for anchor in 2020-08-12 2020-08-19 2020-08-26 2020-09-02 2020-09-09 2020-09-16; do
  hm collect --database "$DB" --output "$C/$anchor-c0q120" --anchor "$anchor" --users 20000 || break
done
```

SQL и файлы те же, что у `hm_experiment collect --policy C0-Q120`. На fixture тест сверяет байты parquet и identities. Отличаются только ограничения: нет development-потолка 09-09 и Windows decision lock. Вместо них разрешён любой anchor, для которого anchor+7 дней ≤ 2020-09-23, то есть до 09-16 включительно, а неделя без положительных примеров отклоняется.

Collection строится так:
- 20 000 клиентов с покупкой в [anchor−90d, anchor), порядок по sha256(id||':2026');
- кандидаты C0-Q120 из закреплённого `hm_retrieval`;
- закреплённые признаки;
- labels — различные покупки в [anchor, anchor+7d).

Для 08-12…09-09 `collect` печатает `lock_users_match`: совпадают ли SHA-256 и размер `users.parquet` с pins `train_collections[*].users` из lock. `true` — сильное подтверждение, что данные и код те же, что у GPU-прогонов. `false` — повод разобраться (например, могут отличаться метаданные parquet), а не автоматическая остановка. Для 09-16 pin нет, печатается `null`. Сами pins повторены в `manifest.json` как `lock_users`.

Прежде чем продолжать, проверьте вывод для 09-16: `selected_queries 20000`, `buyers 1905`, `target_pairs 5962`, `positive_candidate_rows 894`. Это значения v1 final-недели из [отчёта](hm-report.md). Если числа другие, данные или код отличаются от GPU-прогонов: остановитесь.

## 5. Проверка переноса на CPU

```zsh
PORT_TRAIN=("$C/2020-08-12-c0q120" "$C/2020-08-19-c0q120" "$C/2020-08-26-c0q120" "$C/2020-09-02-c0q120" "$C/2020-09-09-c0q120")
for arm in M E; do
  hm fit --arm "$arm" --seed 2026 --train "${PORT_TRAIN[@]}" --validation "$C/2020-09-16-c0q120" \
    --output "artifacts/hm-kaggle/port/${arm}2026" --threads 4 || break
done
```

Рецепт — GPU-рецепт lock, перенесённый на CPU: 500 деревьев, depth 8, learning rate 0.05, L2 10, Logloss. Явно заданы Bayesian bootstrap, bagging_temperature 1, border_count 128 и Plain boosting; CPU defaults MVS и 254 borders не используются. Убраны только GPU-ключи `devices`, `gpu_ram_part` и `pinned_memory_size`.

Обучающие строки дают `hm_experiment.load_part`: 20 000 клиентов на неделю, все positives и 20 hashed negatives с весами обратной вероятности включения. Списки признаков берутся из lock в его порядке и сверяются с [hm-final-lock.json](../configs/datasets/hm-final-lock.json) и feature engine. `params.json` — это `get_all_params()` CatBoost, ключевые параметры повторены в `report.json` как `resolved_checks`. Каждый fit по умолчанию ограничен 7200 с (`--wall-seconds`). Недообученная модель не сохраняется.

Обучающий набор и неделя те же, что у v1 GPU final, поэтому ожидается следующее:
- `train_queries 100000` и `train_positive_rows 4233`; число positives взято из записи о GPU final в [hm-pilot.md](hm-pilot.md).
- `queries 20000`, `positive_queries 1905`, `distinct_query_target_pairs 5962`, `oracle_map_at_12_conditional` 0.17352937.

Правило для M2026 зафиксировано до первого прогона:
- Остановитесь и ничего не отправляйте, только если CPU `map_at_12_conditional` ниже 0.0300. Это порог грубой ошибки около уровня recency-эвристики: на неделе 2–8 сентября (anchor 09-02) она получила 0,02910562 ([отчёт](hm-report.md), «Результаты selection»).
- Иначе продолжайте. Значение запишите рядом с GPU M2026 и M2027, 0.03340 и 0.03546 ([hm-pilot.md](hm-pilot.md)), как описание, а не вердикт.
- При остановке сравните `params.json` с `resolved_model_parameters` GPU-отчёта на Windows-машине (`artifacts/hm-campaign/final/M2026/report.json`).

E2026: на этой когорте GPU-ориентира нет. E46 измерялась на development-неделях и отдельной customer-test когорте. Запишите значение; один seed на одной неделе даёт только описательную оценку.

До планирования четырёх финальных fit запишите `elapsed_seconds` из `report.json` обоих port-fit.

## 6. Финальные модели

```zsh
FINAL_TRAIN=("$C/2020-08-19-c0q120" "$C/2020-08-26-c0q120" "$C/2020-09-02-c0q120" "$C/2020-09-09-c0q120" "$C/2020-09-16-c0q120")
for arm in M E; do
  for seed in 2026 2027; do
    hm fit --arm "$arm" --seed "$seed" --train "${FINAL_TRAIN[@]}" \
      --output "artifacts/hm-kaggle/final/$arm$seed" --threads 4 || break 2
  done
done
```

Окно сдвинуто на неделю: последняя размеченная неделя 16–22 сентября входит в обучение, поэтому validation нет. Labels для 23–29 сентября в данных отсутствуют. Качество подтверждают раздел 5 и оценка Kaggle.

## 7. Скоринг тестовой недели

```zsh
hm score --database "$DB" --fits artifacts/hm-kaggle/final/{M2026,M2027,E2026,E2027} \
  --output artifacts/hm-kaggle/score-2020-09-23 --chunk-users 15000 --threads 4
```

Anchor фиксирован: 2020-09-23. DB должна заканчиваться ровно 22 сентября. Оцениваются все клиенты с покупкой в [anchor−90d, anchor) в порядке sha256(id||':2026'), id, порциями по `--chunk-users`. Для каждого chunk:
1. Строятся кандидаты C0-Q120 короткой SQL из `hm_auto_holdout` с параметром anchor; ранги товаров считаются один раз на весь прогон.
2. Строятся закреплённые признаки.
3. Все четыре модели оценивают один и тот же frame.
4. Top 12 по (score DESC, article_id) записывается в `top12-<model>-<chunk>.parquet`.
5. Квитанция `chunk-<chunk>.json` фиксирует время и RSS, в stderr уходит JSON-строка.

`plan.json` закрепляет входы: DB и её provenance из `kaggle-source.json`, хеши моделей, код, пакеты, разбиение, `--threads` и digests клиентов и товаров. Fits должны быть построены на collections той же DB.

Один запуск по умолчанию ограничен 6 часами (`--wall-seconds 21600`). Чтобы продолжить после остановки, по времени или по ошибке, повторите ту же команду. Chunks с действительной квитанцией пропускаются, chunk без квитанции считается заново. При изменении любого входа score откажется работать с сообщением «plan differs». Другие `--chunk-users`, `--threads` или fits требуют нового `--output`. `--chunk-users` не больше 50 000: большее значение отклоняется до записи. Меньший `--chunk-users` снижает пиковую память: chunk из 15 000 клиентов — это 1,8 млн строк-кандидатов.

Пока score работает, он держит блокировку `score.lock` в output. Второй запуск в тот же output откажется: «Another process holds score.lock». Блокировку снимает ОС, когда процесс завершается, поэтому сам файл `score.lock` не мешает и трогать его не нужно. У каждого процесса свой spill `duckdb-temp-<pid>` и свои `.part`. Пустой spill удаляется в конце. После аварийного завершения его можно убрать вручную, когда процесс точно завершён.

Тупики продолжения:
- Ошибка до появления `plan.json`: нужен новый `--output`.
- Квитанция chunk не проходит проверку (`receipt belongs to another plan` или `file bytes changed`): переместите `chunk-NNNN.json` и `top12-*-NNNN.parquet` этого chunk из output в другой каталог или начните новый `--output`.
- Новый терминал: сначала снова `cd`, `hm()` и `DB=` из разделов 0 и 3.
- Перед повтором команды убедитесь, что предыдущий запуск завершился.
- `TimeoutError` (`Declared wall limit exceeded`): повторите ту же команду.

## 8. Файлы для Kaggle

```zsh
for model in M2026 M2027 E2026 E2027; do
  hm assemble --database "$DB" --scores artifacts/hm-kaggle/score-2020-09-23 --model "$model" \
    --output "artifacts/hm-kaggle/submissions/$model.csv.gz" || break
done
```

Формат файла: заголовок `customer_id,prediction`, по строке на каждого из 1 371 980 клиентов. В строке 12 различных десятизначных article_id с ведущими нулями через пробел. Клиенты без покупок за 90 дней получают 12 товаров с наибольшим числом различных покупателей за 16–22 сентября, ties по article_id. Если у оценённого клиента не ровно 12 различных товаров с рангами ровно 1…12, assemble останавливается, а не дополняет список. На диске output assemble требует 10GiB свободного места.

Сначала файл пишется как `.part` и проверяется заново:
- заголовок;
- полный набор клиентов без дублей;
- 12 различных известных ID в каждой строке;
- LF в конце каждой строки.

Только после этого `.part` переименовывается. После ошибки `.part` остаётся для разбора; повторный `assemble` с тем же именем откажется работать, пока файл не убран вручную. В квитанции `<model>.json` — счётчики, популярный список, provenance DB и SHA-256 файла. Gzip детерминирован: одинаковые входы дают одинаковые байты.

Файлы отправляются через Late Submission: из залогиненного Kaggle CLI (`kaggle competitions submit -c h-and-m-personalized-fashion-recommendations -f <файл> -m <описание>`) или на странице соревнования. Каждую посылку подтверждает владелец аккаунта. Для late submission CLI показал лимит 100 посылок в сутки Kaggle (UTC), а не 5 активной фазы. Kaggle принимает `.csv.gz` (около 59 MB) напрямую.

## 9. Результаты

Таблицы заполняются только из фактических квитанций и отчётов; оценок вместо них не ставить.

| Проверка | Получено | Ожидание |
|---|---|---|
| verify | `complete`: три CSV по SHA-256 и размеру равны pins | `complete` |
| EDA: покупки / клиенты / товары | 31 788 324 / 1 371 980 / 105 542 | 31 788 324 / 1 371 980 / 105 542 |
| 08-12…09-09: `lock_users_match` | `false` на всех пяти (см. ниже) | `true`; `false` — разобраться |
| 09-16: buyers / targets / C-positive | 1 905 / 5 962 / 894 | 1 905 / 5 962 / 894 |
| Port: train positive rows | 4 233 | 4 233 |
| Port M2026 MAP@12 | 0.03332364 (M2027: 0.03316327) | стоп только ниже 0.0300; GPU M2026 / M2027: 0.03340 / 0.03546 |
| Port E2026 MAP@12 | 0.03399804 | GPU-ориентира нет |
| Port: `elapsed_seconds` M2026 / E2026 | 314 / 334 (M2027: 321) | — |
| Final: train positive rows / `elapsed_seconds` | 4 377 / 282–332 | — |
| Score: клиенты / chunks / пиковый RSS | 518 920 / 35 (34 по 15 000 и 8 920) / 8,94 ГБ; 415 с счёта | — |

Все fits шли с `--threads 8`, а не с 4, как в командах разделов 5 и 6; score шёл с `--threads 4`. `thread_count` входит в гиперпараметры fit и в его identity (`scripts/hm_kaggle.py:276-277, 643-646`); со сверкой lock его не сравнивают (`CHECKED_PARAMETERS`). Сравнения между fits требуют равного `thread_count`, поэтому все fits одной цепочки идут с одним `--threads`.

`lock_users_match = false`: `users.parquet` всех пяти недель на 17–19 КБ меньше pins из lock, причина не установлена. Содержимое косвенно подтверждают два совпадения с GPU-прогонами: 4 233 positives в port-обучении на этих неделях и точные числа 09-16. Остановкой по правилу раздела 4 это не считается.

Четыре файла собраны 20.10 в 23:35–23:36 МСК. Независимая проверка подтвердила:
- SHA-256 совпадает с квитанциями;
- 1 371 980 строк, набор клиентов равен таблице `customers`;
- в каждой строке 12 различных известных товаров;
- ровно 853 060 строк совпадают с популярным списком.

Вне фолбэка файлы попарно совпадают не больше чем в 54 строках из 518 920.

| Модель | Public | Private | SHA-256 файла |
|---|---:|---:|---|
| M2026 | 0.02361 | 0.02308 | `5e5c08fb3f9a12bdd829d6a65c3d74a76cc4fd108b7271beadf728dcded3844b` |
| M2027 | 0.02315 | 0.02284 | `9826af542a2a83c1a55e632fa32530a40bf4c565752f100cbdcd54c7780e2d8a` |
| E2026 | 0.02357 | 0.02327 | `da427b9c77eb772483ed8b3e531ced2f167c2b5d35dd96066e8714a696899a95` |
| E2027 | 0.02345 | 0.02313 | `736c2c5aa8e1c704acfe72b6f6e7165dfd94552d933aea5312b6bab88e20280b` |

## Ограничения и открытые вопросы

- CPU повторяет все явные параметры GPU-рецепта, но backend другой, а GPU-обучение недетерминировано. CPU defaults для незаданных параметров могут отличаться от GPU: `sampling_frequency`, CTR (`simple_ctr`, `combinations_ctr`, `max_ctr_complexity`), `one_hot_max_size`, `model_size_reg`. Отличие проверяется только разделом 5 и сравнением `params.json` с GPU-отчётами на Windows.
- Байты Kaggle совпали с зеркалом: `verify` дал `complete` по всем трём файлам.
- Local MAP@12 условный: он усредняется по покупателям недели среди 20 000 клиентов с историей (1 905 на 09-16), а не по всем 20 000. Kaggle считает и покупателей без истории, которые получают популярный список, поэтому оценка Kaggle, скорее всего, будет ниже локальной. Числа разделов 5 и 9 напрямую не сравниваются.
- kaggle CLI сохранил файлы как `<name>.zip` (`kaggle-verify.json`). `.csv.gz` Kaggle принял.
- Блокировка `score.lock` на Windows (`msvcrt.locking`) тестами не проверена; тесты идут на macOS с `fcntl.flock`.
