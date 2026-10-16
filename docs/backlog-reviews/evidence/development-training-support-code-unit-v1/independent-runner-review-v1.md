В focused runner-delta scope поддержанных P1/P2 нет.

Три исполняемых модуля связаны точными pins. Их регистрация до compile/exec обеспечивает dataclass identity; tests получают настоящий metrics-модуль. Два RAW source-файла только копируются в `tree/scripts`: вычисленный tests.REPO_ROOT указывает туда. Callback/accounting/ranking/selector извлекаются указанными AST-узлами; необходимые np/dataclass/QueryRanking/math globals заданы. Полные RAW-модули не импортируются.

`patch.dict` заранее помещает подставной ModuleType catboost и RAW-модули в sys.modules, поэтому helper использует FakeClassifier/FakePool. Audit блокирует реальные CatBoost/_catboost, DuckDB/_duckdb и whole-RAW imports; попытки сохраняются и запрещают успешную closure. После patch подставной catboost удалён. Это source-проверка маршрута, не native/version proof.

Outer побайтно совпадает с принятой CF V2 после обратной замены пяти bindings. Primary/PENDING evidence, bounded cleanup/known-reap, inheritedCPU1+4+10/hard15 и whole30wall сохранены; supervisor guard согласован с4CPU. Once namespace, отсутствие retries,11 method IDs и approved=false не изменены после подготовки.

Все14 входов/snapshots свежие. Проверка только source; без imports кандидатов/tests/fixtures/native/SQL/data/ML/Git/network/helpers/canonical writes. Actual version record и один0MLunit ещё не выполнены; отдельный Root issue/внешний lifetime остаются необходимыми.
