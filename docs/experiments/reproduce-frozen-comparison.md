# Повтор фиксированного development-сравнения из исходного архива

Этот маршрут заново импортирует исходный REES46 October 2019, строит train/selection данные и обучает **две новые модели**: ручной B41 и автоматически сгенерированный R2/L05 W44. Он не использует старые CBM, approvals, claims, абсолютные пути автора или файлы из `/tmp`.

Это повтор ранее выбранного рецепта после model selection. Он не повторяет исторический поиск и не является новой независимой оценкой выбранного победителя. Даты25–31 октября не входят в этот CLI; их отдельный исторический отчёт не влияет на параметры нового обучения. Даже при том же seed совпадение новых model bytes/оценок со старым запуском нельзя заявлять без фактической независимой проверки.

## Принятый полный повтор на M3/macOS

Из clone опубликованного `d35cfb6` и нового locked-окружения заново построены15 дневных коллекций: train8–20 —26000Q/5317058C, selection22–23 —4000Q/817149C. Обучены две новые fixed300-tree модели, без старых CBM/approvals и повторного model selection. Producer и отдельно оплаченный verifier завершились EXIT0 и reaped. Проверены Q/C/fullY/chosen3/metadata, все B41/W44 матрицы и веса,1634298 native selection scores с полными rankings, четыре estimands и200 conditional paired bootstrap draws. Historical W44 materialmatrix witnesses совпали точно; это не исчерпывающий независимый пересчёт core18 формул.

Development NDCG@20 воспроизведён: B0.4586107284411233,W0.46470287738416133. Это frozen post-selection reproduction, не новый independent quality test и не доказательство search/speed/generalization benefit. Даты25–31 не открывались этим маршрутом. Успешный producer стоил966.83s wall/1356.54CPU-s, verifier81.87s wall/130.21CPU-s; sampled peaks соответственно7121993728B и4027482112B. Body measurements и отдельные V6 upper не прибавляются кinclusiveexternal; старые offline/verifier failures, canary и setup оплачены отдельно. Глобальный исторический CPU и универсальный peakdisk/RSS bound не заявляются.

[Полная scoped приёмка и ограничения](../backlog-reviews/public018-complete-output-acceptance.md), [точные агрегаты](../backlog-reviews/public018-complete-output-acceptance.json). Старые принятые DOC/report bytes сохранены immutable в evidence; original producer pending flags не переписаны отдельной приёмкой.

## Запуск обычным пользователем

Из свежего checkout подготовьте locked Python3.12 окружение:

```bash
uv sync --frozen --python 3.12
```

Нужен локальный архив `2019-Oct.csv.gz`: SHA256 `8ebca1ad741295297368f2cf0315e3f36853a1a11768fb16babf8c9b83838147`,1741928540 compressed bytes,5668612855 raw CSV bytes,42448764 событий. Это измеренная в проекте identity архива, а не подписанная publisher checksum. Источник и условия использования описаны в `docs/data.md`; команда ничего не скачивает. Код рассчитан на Linux/macOS; фактический полный повтор принят на M3/macOS в новом locked-окружении. Windows/WSL и другое железо отдельно не проверялись: наличие wheels или одинаковый seed не доказывают работоспособность и ресурсную достаточность другой среды.

Задайте собственные явные ограничения `CPU_SECONDS`, `WALL_SECONDS`, `RSS_BYTES`, `SPILL_BYTES`, затем выполните:

```bash
uv run --frozen python -m scripts.reproduce_frozen_comparison \
  --raw data/raw/2019-Oct.csv.gz \
  --output artifacts/public-frozen-comparison-01 \
  --recipe configs/reproduction/frozen-bw-oct2019.json \
  --cpu-seconds "$CPU_SECONDS" \
  --wall-seconds "$WALL_SECONDS" \
  --rss-bytes "$RSS_BYTES" \
  --spill-bytes "$SPILL_BYTES"
```

Все четыре значения — положительные целые числа. Wall ceiling не превышает43200секунд. `SPILL_BYTES` должен быть не меньше8589934592: существующий import kernel задаёт8GiB spill и2CPU threads/2GB engine memory. Это не8GiB process RSS limit. Перед запуском требуется минимум40GiB свободного scratch disk; это floor, а не доказанная верхняя граница использования диска. Нужен дополнительный запас для исходного snapshot, raw/canonical CSV, DB/WAL, spill, дневных Parquet, матриц и native Pool/quantization. Один полный M3/macOS запуск измерен:966.83s wall,1356.54CPU-s и sampled job peak7121993728B при внешнем envelope4200CPU/3600wall/12GiB. Это конкретный профиль, а не универсальный ресурсный предел или прогноз для другого компьютера; никакое значение переменных здесь не обещает успешного завершения.

Output должен отсутствовать, его parent — существовать. `consumed.json` появляется до чтения архива; при ошибке сохраняются `failed.json`, partial outputs и списанные fit attempts. Failure persistence и telemetry выполняются best-effort: вторичная ошибка записи, измерения или close отмечается у исходного исключения и не заменяет его, включая KeyboardInterrupt/SystemExit. Повтор с тем же output отвергается. Для новой осознанной попытки пользователь выбирает новый output; автоматического retry или замены гиперпараметров нет.

V2 сохраняет выбранный рецепт без изменения параметров. Recipe byte SHA256: `3a26fed3bee450cb7ce4b658816386c14cbd2c4133a18bdaa39ae058e5b560ec`. CLI один раз читает ограниченный byte snapshot рецепта, затем хеширует, разбирает и сохраняет именно эти байты. Он также связывает начальные байты команды, публичные core/dependency snapshots и locked CatBoost/DuckDB/numpy/pandas версии. Fixed source closure компилируется непосредственно из проверенных snapshot bytes, без чтения pyc; нужен свежий процесс без уже импортированных core modules. Изменения исходников отвергаются перед употреблением и на завершении; report хранит начальные фактические witnesses, а не поздние hashes по имени файла. Изменение рецепта требует отдельной версии кода; переменной конфигурации поиска здесь нет. Обычному пользователю не нужен Root gate. Реальный запуск агентом в текущей исследовательской кампании требует отдельного общего runtime budget и внешнего supervision; этот документ такого разрешения не выдаёт.

## Что сохраняется

- `source/`: новый owned source snapshot, проверенный CSV и typed9 `events.duckdb`; `source.json` — измеренные import evidence. Таблица legacy `ingest_metadata` не требуется и не создаётся.
- `train/2019-10-08`…`2019-10-20`, `selection/2019-10-22`…`2019-10-23`: по2000 query/day, полные Q/C, именованные B45, отдельные3 extra fields, full distinct Y и manifest. Исходные ссылки и byte witnesses сохраняются в каждом consumer record; actual exports/manifest проверяются до и после чтения и на terminal close. Отсутствие нужной ежедневной population вызывает STOP.
- `B.fit-consumed.json`, `W.fit-consumed.json`: constructor parameters, матричные identity, реальные веса, bounded B41 values/NaN-mask witnesses и accounting до каждого native fit. Общий B41 train prefix W обязан совпасть с B до создания W Pool; selection prefix проверяется до предсказания W, без полной копии матрицы.
- `B.cbm`, `W.cbm`: только две новые300-tree Logloss модели; обучение последовательно B→W с освобождением train matrix/Pool/model между ветвями. Нет eval_set, early stopping, scoring-prefix search или дополнительного fit. Pool получает явный thread_count=2 и только исторические label/weight/feature_names, без лишнего Logloss group_id.
- `B.selection-scores.npz`, `W.selection-scores.npz`: float64 raw scores с точными int32 groups/int64 product IDs. Глобальная group→query связь задаётся Q ORDERBYquery_id; порядок пар —group/product_id.
- `B.json`, `W.json`, `report.json`, `report.md`: source/code/recipe/environment provenance, full matrix/weight identities, tree/parameter/feature-order checks, fullY metrics всех четырёх estimands, фиксированный paired user bootstrap W−B. Human report содержит агрегаты.

Q выбираются по48h прошлой активности до чтения Y. C —200popular по distinct purchase users за7дней +20recent за7дней, dedup без refill. Глобальные события ровно в момент запроса исключены из всей истории. Полный Y —покупки `[t,t+24h)`, включая товары вне C/catalog; он не вставляет положительные товары в C. Empty-C/empty-Y/all-negative/all-positive queries сохраняются. Каждая nonempty train query имеет суммарный вес1; row weight=1/|Cq|. X=float32 с прежними NULL/NaN и missing flags; IDs остаются nominal join keys.

Возвращаемый статус —`complete_produced_pending_independent_review`. Он подтверждает локальное завершение и проверки самой команды, но не выдаёт независимую приёмку, clean-environment proof или полный внешний process-tail verdict. CPU/wall delta начинается при создании Budget после interpreter/CLI startup и заканчивается точкой измерения, до final repins/полного exit; startup и tail отдельно учитывает внешний supervisor. CPU/wall/RSS/spill проверки в CLI кооперативные; долгую native операцию до callback/возврата может жёстко ограничить только внешний supervisor. RSS —process-lifetime high-water текущего процесса, включая interpreter/CLI startup; начальное RSS не вычитается. Только CPU/wall являются delta от Budgetstart до точки измерения перед полным exit. Внешний lifecycle profile включает startup и tail отдельно.

## Проверка кода без исходных данных и ML

```bash
uv run --frozen python -m unittest discover -s tests -p 'test_reproduce_frozen_comparison.py'
```

Тестовый файл содержит две независимые группы:7 методов с14 полностью выдуманными событиями на fixture, максимум6Q/64C, реальными нижними DuckDB cores и FakeCatBoost; и7 stdlib-only binding/failure регрессий. Native imports находятся только в setUp первой группы. Они проверяют global timestamp peers, off-C fullY, календарную maturity, совпадение глобального training order с фактическим historical loader, named B45→B41/W44 projection, query-mass/empty-C transport, label-blind sampling, два фиксированных fit attempts и сохранение consumed failure. Никакие реальные данные, старые модели, native CatBoost fit/predict или historical approvals не нужны.

Для V2 автор выполнил только stdlib/Fake группу: six unchanged PASS плюс targeted PASS после исправления пропущенного environment field в терминальном fake recipe. Это не новый полный14-method или native integration PASS. Сохранённый V1 tiny-engine evidence не повышается до V2 actual-runtime proof. Новая группа воспроизводит recipe path replacement, изменение manual values/NULL mask, экспортов/manifest/source/module/command, позднюю mutation после report persistence и вторичные ошибки при KeyboardInterrupt/SystemExit. Shared-prefix fake fixture4097строк заставляет пройти две bounded chunks; это stdlib float32 representation, не новые реальные события или NumPy/native arrays. Позднее полный public raw→две новые fixedfits→comparison повтор в новом clone/locked Mac-окружении выполнен и независимо принят; сохранённый synthetic evidence этим не переписан. Новые исполнения агентом по-прежнему требуют отдельного конечного runtime решения.
