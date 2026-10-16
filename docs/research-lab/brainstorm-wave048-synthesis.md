# Волна048: NULL-дефект тестового oracle

Два blind FIRST и отдельный skeptic уточнили existing TLAB-001/005/014 без новых ID или обязательных проверок. [Девять исходных отчётов/ledger/FIRST и Root readback](archives/wave048/publication.json) сохранены точно; их UNRUN-предсказания относятся к моменту написания.

FeaturesA обнаружил различие Python-set oracle и SQL DISTINCT: `None` считался отдельным user/product. Production SQL исключал NULL из DISTINCT, сохраняя допустимые строки и дубликаты в raw counts. Пятисобытийный literal gold различает raw bag, non-NULL DISTINCT и глобальное исключение anchor peers; это не установленная ошибка production-фичей. ModelsA дал optional compound category0 witness без обнаруженного mismatch; он не превращён в обязательный новый test.

Позднее Root выполнил ограниченную проверку: RED — один case с двумя ожидаемыми oracle subTest failures; GREEN —13 методов PASS, включая тот же case, а не14 уникальных случаев. Две NULL-фильтрации и all18 gold regression локально установлены точно. [CODE/unit/installation и исходные transcripts](../backlog-reviews/manual-oracle-null-code-acceptance.md).

Реальных ML fits и чтения датасета не было. Исправлен тестовый oracle; frozen recipe, production и прежний scope manual/full-data proof не меняются. Native helper по-прежнему имеет только принятый default skip; этот DuckDB-unit не является native training PASS.
