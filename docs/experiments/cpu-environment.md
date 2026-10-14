# CPU-окружение CatBoost

15 октября 2026. Подготовительный этап TLAB-008. **Реальные модели ещё не обучались.** Установлен CatBoost1.2.10, выполнены synthetic CPU API-check и 112 интеграционных проверок проекта. Dependency diff принят независимой coordinator verification.

Версия и совместимый CPython3.12/macOS universal2 wheel проверены по [официальному PyPI](https://pypi.org/project/catboost/1.2.10/) и [документации установки](https://catboost.ai/docs/en/concepts/python-installation). Точный SHA и размер дополнительно сверены с [API PyPI](https://pypi.org/pypi/catboost/1.2.10/json), а не только с локальным lock.

- Wheel: catboost-1.2.10-cp312-cp312-macosx_11_0_universal2.whl.
- Размер:28 884 278 байт.
- SHA-256:b27115d5b443048f710001c8ac666892dfe03498492310b00466203c91cc30a5.
- Python3.12.14, macOS26.3 arm64; task_type=CPU, две нити. Доступность Windows/RTX3070 не предполагается.

В pyproject добавлена одна прямая зависимость catboost==1.2.10. Все 51 ранее зафиксированные версии сохранены. В lock добавлены CatBoost, graphviz0.21, narwhals2.27.1, pandas3.0.6, plotly7.1.0, scipy1.18.1 и условная tzdata2026.5. На Mac установлены шесть новых пакетов; условная tzdata этому окружению не потребовалась. NumPy2.5.4 и DuckDB1.5.6 не обновлялись. Дополнительные widget extras, CUDA toolkit и внешние сервисы не устанавливались.

Synthetic check использовал восемь строк, два числовых признака и четыре группы: две информативные, одну полностью отрицательную и одну полностью положительную. CatBoostRanker/PairLogit получил две явные пары с массой1 на информативную группу; CatBoostClassifier/Logloss — веса строк0,5. Обе модели выполнили по одной итерации на CPU, предсказания имеют правильную форму и конечные значения. allow_writing_files=False; реальные dataset rows, eval_set, early stopping и native best-model selection не использовались. Это API-проверка, не эксперимент качества и не выполнение двух реальных baseline fits.

Первая версия проверочного вызова передала Ranker параметр prediction_type, который поддерживает классификатор. Вызов исправлен: Ranker.predict возвращает raw score без этого параметра. Повторный synthetic check завершился успешно. Фактический fit/predict segment занял0,092с; это не benchmark подготовки или обучения на реальном датасете.

После установки общий suite:112testsPASS за1,754с; git diff --check успешен. pyprojectdiff:+1строка,lockdiff:+212строк,изменений существующихpackageversions0.

Новая SHA uv.lock:4675021f74063889ffb596325b9e608a3a5776a29f967d052b86923e40485eab. Предыдущая:0c54aa349b8d3aef654aaffc5a56cbd88213686256c05c00d6498da0051d0d7e. Старая lineage сохранена коммитом005; принятые fingerprints старых Q/C/Y/features не переписывались. Новая development-коллекция должна получить новую lineage и приёмку. Старые программы со строгими accepted pins правильно отклонят смешивание lock-версий.

```sh
uv sync --locked
uv run python -m unittest discover -s tests -q
```

Локальные synthetic API/evidence JSON остаются вне Git; aggregate values и официальный wheel provenance сохранены здесь. Дальше — ревью окружения, runtime TLAB-017 с закрытой confirmation, новые принятые train/selection artifacts и только затем реальные fits с external full-Y evaluator.


[Independent dependency acceptance](../backlog-reviews/tlab-008-dependency-verification.md) фиксирует actual package diff, отдельный primary-source wheel check и coordinator103-test результат.
