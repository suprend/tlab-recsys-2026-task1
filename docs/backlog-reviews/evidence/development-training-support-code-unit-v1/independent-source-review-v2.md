# Development-training support V2 — независимое source review

Поддержанных P1/P2 замечаний в трёх кандидатах не найдено.

`scripts/development_training.py:89–91` добавляет `informative_candidate_groups` в новый dict из уже вычисленного `validation_accounting['informative_groups']`. Selector support остаётся отдельным объектом; fit, полный диапазон/argmax, copy/shrink, checks и отказы не изменены. Обратная замена return полностью восстанавливает baseline helper.

Новый `tests/test_development_training.py:186–262` извлекает реальные Prepared/accounting/rankings/callback и четыре selector-функции. При exec классов нужный ModuleType зарегистрирован в sys.modules; globals `np`, dataclass, QueryRanking, math предоставлены, selector imports разрешаются в тот же accounting и фактический ranking_metrics. CatBoost/Pool остаются FakeClassifier/FakePool, SQL/data-loader imports исключены.

Ручной разбор: train имеет обе labels; validation fullY={99}, C={1,2}, labels=[0,0], informative=0. Три score-вектора действительно дают порядки (1,2), (2,1), (1,2); literal full-Y NDCG=(0,0,0), global-band argmax выбирает 1. Проверены отдельный support dict, отсутствие нового ключа в оригинале, один fake fit, полный исходный tree_count=3 и shrink только копии до 1. Удаление добавленного метода и нового setup-key полностью восстанавливает baseline test source: десять прежних тел неизменны.

Документация правильно использует последний элемент accounting tuple (`[-1]`), ограничивает order-invariance корректными labels/фиксированным C и не обещает power при положительном числе групп. Исторические 10/22 PASS относятся к прежним байтам.

Все 11 методов на новых байтах и native helper body **UNRUN**. Выполнены только чтение, текстовые сравнения и SHA; test AST не исполнялся. Runtime, реальный fit/shrink и resource/extraction доказательства не выдаются. 19 inputs и copies повторно совпали; точные pins — в ledger.
