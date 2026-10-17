# Повтор seed2027 на сохранённых экспортах исследования

Команда проверяет один фиксированный вопрос: сохраняется ли development-разница B41/W44 при общем новом seed2027, если выбранный блок L05, данные, веса и процедура выбора числа деревьев не меняются. Это **повтор на сохранённых исторических экспортах d35cfb6**, а не новый raw→исправленные producers запуск, поиск новых признаков или независимая финальная оценка.

## Необходимые входы

Нужны Python3.12 и зависимости из `uv.lock`, этот checkout и сохранённый пакет исходного `public-frozen-bw-once`: неизменённый `report.json`,75 parquet exports и15 manifests за train8–20/selection22–23 октября2019. Пакет не входит в Git. Его можно переместить целиком, сохранив внутренние относительные пути и bytes. Произвольная новая выгрузка не заменяет этот пакет. Выполненная историческая проверка относится к Mac/M3. Переносимость на Linux оценена только по исходникам; выполнение этого повтора на Linux не подтверждено.

Поддержан ровно исторический report SHA256 `e62b1f47d6db808f6f5235f63a1b207970ac2f8487c09d9273902c4fbc864a9b`,52 763bytes. Доступность всех входов на новом компьютере не гарантируется. Если пакет утрачен, эта команда не умеет восстанавливать его из raw; используйте документированный самостоятельный raw-повтор для другой задачи и не переписывайте ожидаемый digest, чтобы выдать новые данные за старые.

Семь поздних исправлений ужесточили recipe/lineage, empty-Q, cleanup, namespace, exact-ranking и cache checks. Известной ошибки численных значений канонических B41/L05 в этих экспортах не установлено; формулы, SQL и порядок B41 сохранены. Это не доказывает выполнение нынешних raw producers. Историческая provenance входов и свежая source closure потребителя хранятся отдельно; старые receipts не редактируются и не переутверждаются текущими.

## Построение локального request

Из корня checkout задайте `HISTORICAL_EXPORT_ROOT` — существующий путь к сохранённому пакету, `NEW_REQUEST` — новый файл в существующем принадлежащем вам каталоге. Ни путь к чужому TMP, ни private approvals/controllers не нужны.

```bash
uv run --locked python -B scripts/build_seed_replication_request.py \
  --producer-root "$HISTORICAL_EXPORT_ROOT" --output "$NEW_REQUEST"
```

Builder читает только source/config и metadata исторического report. Он печатает request SHA256; сохраните его как `REQUEST_SHA256`. Это ещё не проверка содержимого входов. Source paths определяются текущим checkout, а producer root — вашим аргументом. JSON не публикуют как переносимый фиксированный файл: абсолютные пути и source pins относятся к данной установке. После перемещения/изменения кода стройте новый request; исторические report/manifests не меняйте.

## Два фиксированных обучения

Задайте `NEW_OUTPUT_DIRECTORY` — отсутствующий каталог с существующим родителем. Он не должен находиться внутри исторического producer root. Сначала выделите ресурсы для **всей** операции; выполнение не перезапускается автоматически.

```bash
uv run --locked python -I -B scripts/replicate_frozen_seed.py \
  --request "$NEW_REQUEST" --expected-request-sha "$REQUEST_SHA256" \
  --output "$NEW_OUTPUT_DIRECTORY"
```

Caller сверяет свежую source closure и полные оригинальные report/manifest/export pins, затем точные matrix identities. Два рецепта сохраняются до fit/feedback. Поддержаны только B41 и B41+три L05-поля, seed2027,depth6,L2=30,rate0.05,CPU/two threads, одинаковый потолок1200. Сохраняются26 000 train Q,4000 selection Q, полный Y, off-C и empty-C. Выбор собственного prefix каждой модели — по conditional fullY macro-query NDCG@20; глобальная полоса1e−12, при равенстве меньше деревьев. Это полный fit с последующим выбором, а не early stopping.

Пределы caller кооперативные:3500CPU/2700wall секунд,12GiB RSS,8GiB spill,2GiB новых outputs. Заявленный whole-operation envelope —4200CPU/3600wall секунд с учётом startup, hashing, подготовки, scoring, проверки, failures и exit. Native blocking, startup/exit и жёсткая остановка всего процесса требуют внешнего наблюдения; команда сама такого hard bound не обещает. Лимиты процесса/машины не меняются глобально. Достаточность памяти и времени для другой среды неизвестна; при превышении сохранить failure и не уменьшать Q/ceiling скрыто.

Всего не более2 fits и2400 обученных деревьев. Две positive-only staged streams дают2400 зависимых curve points. Full-prefix, selected-copy и selected-reload проверяются на полном selection:6 predictions/4 902 894scores; выбранных scores сохраняется1 634 298. Допуск1e−12 дополняется точным равенством ranking order.

## Что читать в результате

`produced-unreviewed.json` — заявление producer, не независимая приёмка. Два full/selected model pairs, полные curves, support, effective parameters, pins и scores сохраняются в вашем output. Положительный ΔNDCG при неотрицательном ΔRecall означает лишь выполнение заранее выбранного seed2027-критерия на повторно использованном development. Matched-k300/600/1200 — только диагностические значения NDCG@20 тех же curves; matched-k Recall не рассчитывается. Периоды25–31 не открываются. Ни надёжный выигрыш на новой популяции, ни превосходство стратегии поиска, ни экономия обучения не следуют из этого повтора. Исторический fixed300 final и его интервал, включающий0, остаются прежними.

## Проверка оркестрации без native ML

```bash
uv run --locked python -B -m unittest discover -s tests -p 'test_replicate_frozen_seed.py' -v
```

Тесты используют NumPy и Fake model/helper, вымышленные малые матрицы и системный TMP. Они не запускают caller.run, CatBoost, DuckDB, SQL или реальные данные. Проверяются16 сценариев, включая seed/effective parameters, оба рецепта до feedback, exact Prepared, полный Y, изменение входов, отсутствие скрытого subsampling/retry и exact-ranking parity. Проверка backend imports сравнивает набор модулей до и после Fake-операции, включая новые подмодули. Отдельный regression использует заранее загруженный вымышленный duckdb sentinel и доказывает, что новый backend-подмодуль всё равно отклоняется; реальный backend не импортируется. Такой pass не подтверждает реальные входы, native поведение, качество или достаточность ресурсов.
