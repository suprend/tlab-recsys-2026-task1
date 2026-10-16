# Opt-in native lifecycle: CODE принят, native body UNRUN

[Тест](../../tests/test_development_training_native.py) по умолчанию пропускается. Приняты [CODE-review](../backlog-reviews/development-training-native-test-code-review.md) и [Root acceptance](../backlog-reviews/evidence/development-training-native-test-code/acceptance.json).

Фактический default discovery `f3e9e9 CLOSED exit0`: 1 discovered, 1 skipped, 0 body executions, 0 native fits, 0 forbidden import attempts; [точный результат](../backlog-reviews/evidence/development-training-native-test-code/default-discovery-result.json). Это проверка безопасного skip, **не native PASS**. Opted body и его совместимость с CatBoost остаются UNRUN; заголовок исходника UNRUN сохранён.

Будущий opt-in: `TLAB_RUN_NATIVE_TRAINING_TEST=1`, запуск из checkout его locked-venv Python с `PYTHONPATH=.`. Флаг не выдаёт runtime-разрешение. Сценарий использует реальные [helper](development-training.md), callback и selector: один fit до 8, 8 selector checkpoints, 11 direct predict calls (8 независимого oracle + 3 parity/retention), один save и один load. Imports, Pool, copy/shrink и cleanup также оплачиваются.

Идентичные validation rows создают плоскую кривую: проверяются item ties, fullY off-C/empty-C, earliest tie, shrink и serialized-score parity; **не non-flat maximum**, качество или CV. CLI/controller/quality gate не добавлены.

Предложенные 60 CPU s / 90 wall s / 1 GiB — не выданы и не измерены. Body guard 45 CPU / 60 wall кооперативен и не ограничивает whole lifetime; внешнее наблюдение startup/native blocking/tail принадлежит будущей операции. Остаток 6 CPUh неизвестен, закрытые caps сохранены; повторного бюджета или автоматического запуска нет.
