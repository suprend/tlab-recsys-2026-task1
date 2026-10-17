# FIX-SOURCE — ordinary CLI strict lineage

**SOURCE ACCEPT для exact3-path candidate; actionable defects в предложенной правке не найдено.** Это не runtime/test PASS и не приёмка canonical integration. Reviewed freeze SHA256 `5c9c88265ab79ec90b7f1277163331cedb0ad20f92c2ca06e1d7c49af55f284b`; manifest `6d78f9f5f7b4a9939e9350f6b68622fe8b0a5065b199c0c555e148575e2da7b6`. Все 43 sealed file hashes/bytes совпали. Только 3 candidate paths меняются; original mapping — `/Users/mdpospelov/tlab-recsys-2026/`.

## Исправление guard и dependencies

`candidate/scripts/train_development.py:83–85` связывает `runtime.verify_collection` с существующим `metadata_price_collection.verify_collection_strict`, импортируя его только внутри lazy loader. Оба actual `run` входа вызывают этот seam (`:166–167`) до phase/schema/input pins/environment и подготовки (`:168–174`). Нет weak fallback и нет перезаписи `b.verify_collection`, поэтому dynamic legacy import внутри strict supplement (`context/scripts/metadata_price_collection.py:68–69`) не рекурсирует. Existing strict выводит canonical14 из upstream code/source/seals (`:82–87`) и проверяет exact feature consumption/selection (`:92–101`). Пробел предыдущего P2 закрывается на уровне source path.

CLI `CODE:17–19` добавляет обе newly imported source files: `metadata_price_collection.py`, `metadata_price_features.py`. AST literal comparison подтвердило exact13 union с `b.CODE`, совпадающий с manifest. Existing input-pin merge/recheck покрывает эти файлы; остальные dependencies strict import уже в существующем closure/accepted producer pins. Не введён manual18-only source oracle; supplement связывает фактический registry, не фиксируя 18 features.

## Различающая сила новых тестов

Новый `tests/test_development_cli_lineage.py` не подменяет loader, legacy verifier, strict verifier или lineage helpers. Actual tiny producer fixture создаёт train и separate selection, approvals и seals; `:41–42` привязывает b/strict ROOT к тому же TMP, остальные producer ROOT патчит inherited fixture (`context/tests/test_development_collection.py:124–127`). Дополнительное copying `:43–46` сохраняет уже pinned producer bytes; новые CLI/metadata files не входят в существующий producer plan.

Actual loader проверяется identity assertion (`new test:160–163`) и затем снова вызывается самим `cli.run`. Инертный `catboost` установлен заранее (`:69–72`); constructor/fit запрещены. Только environment и preparation подменены (`:73–82`). Intact test требует конкретный `PreparationReached`, один train preparation call, kernel environment и failed/fit_attempt0 report (`:164–172`), поэтому преждевременный unrelated отказ не выдаётся за успех.

Omission test объявляет шесть случаев: Q, C, Q+C независимо в train/selection (`:174–176`). Reseal `:122–158` обновляет все затронутые approval/manifest/report/state/outer hashes и feature run IDs. Перед CLI каждый вариант обязан пройти actual legacy transport (`:181`), затем CLI обязан дать именно `ValueError` с `canonical14` (`:183–184`), без environment/preparation/model/fit и с failed report (`:185–188`). Originals восстанавливаются в finally; положительный case — отдельный test с новым fixture. Это не mock guard и не «любой отказ PASS».

Pin test `:193–211` проверяет добавленные CODE entries, hashes и реальное отклонение source mutation через recheck, не исполняя изменённый source. Изменённый старый lifecycle test явно остаётся FakeML/accepted-data double; legacy trap и order assertion полезны только для seam routing, strict coverage принадлежит новому файлу.

## Границы интеграции

Источник тестов включает actual DuckDB/NumPy tiny producers; они **UNRUN**, их setup/хронометраж/прохождение не установлены SOURCE review. Все model/native operations в новых cases запрещены, но это не означает отсутствие synthetic SQL. Предстоящий bounded CODE run должен подтвердить setup, intact boundary и все шесть специфических отказов.

Ожидаемые отдельные изменения helper/collection следует объединять только с проверкой base/context hashes и повторным focused run на итоговых bytes: candidate copying fixture и consumer pins будут брать интегрированные sources. Этот review не одобряет незнакомые overlapping patches и не подтверждает их совместимость заранее. Native CLI E2E/callback, scientific quality, текущие artifacts и historical acceptance не расширены.

Выполнены только чтение/поиск, stdlib AST parse/literal inspection и hashing/readback. Tests, project imports/functions, SQL, native/ML/data/model/getter операции и canonical/Git записи не выполнялись. SOURCE freeze/readback PASS; STOP.
