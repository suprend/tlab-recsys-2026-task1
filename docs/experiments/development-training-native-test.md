# Native opt-in test: normal-path toy body принят

## Текущий статус — 2026-10-16 16:45:06 UTC

**Принят normal-path запуск именно текущего opted-in test body**, [tests/test_development_training_native.py](../../tests/test_development_training_native.py), SHA `eca8d1a071361a93e563b105b0c743f235073527876a49e81dd8080c2dea1887`. [Результат](../backlog-reviews/native-helper-engineering-result.md), [независимый output review](../backlog-reviews/evidence/native-helper-engineering-result/independent-output-review.md) и [Root acceptance](../backlog-reviews/evidence/native-helper-engineering-result/root-acceptance.json) подтверждают один actual CatBoost fit до 8 деревьев, oracle всех восьми плоских префиксов, отдельную выбранную копию с 1 деревом и save/reload parity. Исходная full model осталась восьмидеревной. Это один flat/tie toy case, не проверка неплоского максимума, качества или CV.

Разовый **50 CPU / 65 wall helper-only allowance consumed/CLOSED**; остаток не переиспользуется, повторного запуска нет. **Ordinary adaptive CLI native E2E и native callback-abort остаются UNRUN.** Новый отдельный human question50 CPU/65 wall для CLI ещё без ответа; он не выдан этим документом и не покрывается старым helper allowance.

Default discovery ниже — исторические **1 discovered / 1 skipped / 0 body executions** на прежнем source SHA `342f9ee5…`; это остаётся skip-proof и не превращается в native PASS. Поздняя приёмка относится к текущему opted body с добавленным support assertion. Исходный UNRUN docstring и тестовый код сохраняются как история без правок. Предложение60 CPU/90 wall/1 GiB ниже — прежний **невыданный** allocation, а не текущий runtime budget. [DOC currentness audit и безопасная карта источников](../backlog-reviews/evidence/native-test-guide-currentness/publication.json) различают эти срезы; новых tests, grants или gates нет.

## Исторический guide: pre-native инструкция и невыданное предложение

Прежний body ниже сохранён побайтно. Его UNRUN и будущие budget-формулировки описывают исходный pre-native срез, а не отменяют позднюю приёмку того же текущего opted body.

[Тест](../../tests/test_development_training_native.py) по умолчанию пропускается. Приняты [CODE-review](../backlog-reviews/development-training-native-test-code-review.md) и [Root acceptance](../backlog-reviews/evidence/development-training-native-test-code/acceptance.json).

Фактический default discovery `f3e9e9 CLOSED exit0`: 1 discovered, 1 skipped, 0 body executions, 0 native fits, 0 forbidden import attempts; [точный результат](../backlog-reviews/evidence/development-training-native-test-code/default-discovery-result.json). Это проверка безопасного skip, **не native PASS**. Opted body и его совместимость с CatBoost остаются UNRUN; заголовок исходника UNRUN сохранён.

Будущий opt-in: `TLAB_RUN_NATIVE_TRAINING_TEST=1`, запуск из checkout его locked-venv Python с `PYTHONPATH=.`. Флаг не выдаёт runtime-разрешение. Сценарий использует реальные [helper](development-training.md), callback и selector: один fit до 8, 8 selector checkpoints, 11 direct predict calls (8 независимого oracle + 3 parity/retention), один save и один load. Imports, Pool, copy/shrink и cleanup также оплачиваются.

Идентичные validation rows создают плоскую кривую: проверяются item ties, fullY off-C/empty-C, earliest tie, shrink и serialized-score parity; **не non-flat maximum**, качество или CV. CLI/controller/quality gate не добавлены.

Предложенные 60 CPU s / 90 wall s / 1 GiB — не выданы и не измерены. Body guard 45 CPU / 60 wall кооперативен и не ограничивает whole lifetime; внешнее наблюдение startup/native blocking/tail принадлежит будущей операции. Остаток 6 CPUh неизвестен, закрытые caps сохранены; повторного бюджета или автоматического запуска нет.
