# NULL-oracle: CODE/unit принят и локально установлен

[Root CODE/unit acceptance](evidence/manual-oracle-null/tlab-root-manual-oracle-null-code-acceptance-v2.json) и [последующая точная установка](evidence/manual-oracle-null/tlab-root-manual-oracle-null-installed-acceptance-v1.json) различаются по времени. Локально установлен тестовый GREEN `f8a77299…`; HEAD/index сохранены. Production, recipe/lock/model code не менялись.

Фактический terminal `a16375 CLOSED exit0`: completed children CPU1.811772s, supervisor wall2.267949958s. Это scoped unit-учёт, не глобальный CPU остаток. [Result](evidence/manual-oracle-null/result.json), [RED](evidence/manual-oracle-null/red-result.json), [GREEN](evidence/manual-oracle-null/green-result.json).

RED выполнял один новый case: production совпал с independently literal all18 gold, старый Python oracle дал две ожидаемые DISTINCT ошибки2→1. GREEN выполнил13 методов PASS, включая тот же case; это не14 уникальных случаев. [RED transcript](evidence/manual-oracle-null/red-tests.txt), [GREEN transcript](evidence/manual-oracle-null/green-tests.txt), [точные pins](evidence/manual-oracle-null/publication.json).

Исправление — два None-фильтра DISTINCT плюс пятисобытийный all18 regression. Source-review не нашёл P1/P2 в patch; timeout-evidence P2 отдельного runner исправлен и повторно проверен до запуска. [Review](evidence/manual-oracle-null/tlab-manual-oracle-null-regression-independent-review-v1.md), [runner rereview](evidence/manual-oracle-null/tlab-manual-oracle-null-check-runner-focused-rereview-v2.md).

Ограничение traceback: исполнялись pinned TMP-байты с canonical `__file__`; linecache snippets RED взяты из прежнего canonical файла и не доказывают candidate source. Actual pin и testcase/subTest IDs, а не показанная строка, связывают исполнение. Реальных данных/ML fits не было; это oracle accuracy, не full-data proof, качество модели или native helper PASS. Старые ошибки/расходы и неизвестный6CPUh сохранены.
