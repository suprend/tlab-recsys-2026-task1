# TLAB-008 CPU dependency: independent verification

15 октября 2026. Coordinator проверил actual pyproject/lock diff, официальный wheel provenance, установленную среду и новый запуск accepted-core tests. **Dependency preparation accepted; реальный boosting baseline ещё не обучен.**

В pyproject добавлен только catboost==1.2.10. Независимое сравнение tomllib snapshots HEAD/current подтвердило: все51 существующие package versions сохранены, ровно7 новых entries — CatBoost, graphviz, narwhals, pandas, plotly, scipy и условная tzdata. Direct dependency одна; registry CatBoost — официальный PyPI. Staged scope не включает текущий runtime017.

Независимый публичный GET [официального PyPI JSON](https://pypi.org/pypi/catboost/1.2.10/json) подтвердил cp312/macOS universal2 wheel:28 884278bytes, SHA256 b27115d5b443048f710001c8ac666892dfe03498492310b00466203c91cc30a5. Тот же hash/size содержится в actual uv.lock. Actual imports:CatBoost1.2.10,DuckDB1.5.6,NumPy2.5.4. Новая lockSHA4675021f74063889ffb596325b9e608a3a5776a29f967d052b86923e40485eab.

Root synthetic API script фактически прочитан вместе с результатом JSON:8syntheticrows/2features,explicitpairs/pointwiseweights,1iterationCPU/2threads,allow_writing_files=False, noevalset/nativeearlystop. Исправление unsupported Ranker.predict(prediction_type) сохранено в report. Это API evidence, не качество на dataset; coordinator не повторял тот же tinyfit без новой неопределённости.

После dependency change coordinator независимо выполнил103 accepted-core tests001–007: **103PASS,1.726s,exit0**. WIP runtime017 исключён. Его accepted plan-only9tests независимо выполнил B2 ранее; Root полный112suitePASS1.754s сохраняется как отдельная атрибутированная проверка, не подменяет наши результаты. Synthetic failure-path status=failed в stdout ожидаем, общий suiteOK.

Old accepted artifacts/pins не переписаны. Current lock mismatch со старымproducer identity должен fail closed; новая phase collection создаёт новую честную lineage с independently reviewed producer/source/config/output gates. Наличие пакета не разрешает реальные fits до accepted train/selection collection, model protocol и full-Y checkpoint selection. GPU/Windows readiness не проверена, дополнительных framework/API/cloud installs нет.
