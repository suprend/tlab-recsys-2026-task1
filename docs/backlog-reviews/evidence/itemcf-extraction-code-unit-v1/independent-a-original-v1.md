# Независимое correctness review A — ItemCF extraction V1

Поддержанных P1/P2 замечаний не найдено. Полностью прочитаны три новых файла и восемь зафиксированных контекстов; проверка исходников и ручной разбор, без исполнения.

В `scripts/itemcf_extraction.py:181–210` история использует только `view` в полуоткрытом `[b−7d,b)`, исключает NULL user/product до группировки и cap21, сортирует latest-time DESC / SHA256 canonical signed-decimal ID / exact ID. `:220–243` независимо извлекает полные глобальные аудитории, включая пользователей вне Q и собственное старое взаимодействие; GROUP BY убирает повторные голоса. Python принимает только точные signed BIGINT, SQL/Python перенос не проходит через float.

`:211–255` сохраняет Q/C order и пустые C, создаёт точные отдельные `C∪H21` maps с известными пустыми tuples. `max_members+1` выявляет переполнение до возврата результата, signed-limit+1 защищён; `2*N` проверяется до opener/check. Успешный close предшествует финальному check/return; SQL/limit/interrupt путь закрывает соединение.

Ручная проверка `tests/test_itemcf_extraction.py:50–100`: 36 событий + 2 Q + 3 C = 41; H21=(1…21), P9000=P2=(1,2,3,4), P8888=(), суммарно 28 memberships. После исключения собственного голоса support=3, max=3/13, mean=3/260, defined_fraction=1/20. Нижний endpoint включён, верхний и outsider за одну секунду исключены; NULL/action/duplicate случаи согласованы. Остальные три теста соответствуют заявленным descriptor refusal, hash-tie и overflow/close случаям.

Все четыре новых теста **UNRUN**. Это не доказательство исполнения DuckDB SQL, extraction на реальном источнике, его полноты/неизменности или CPU/RSS/IO выполнимости. Source authentication, корректный свежий read-only opener и внешнее native supervision остаются доверенными обязанностями caller; код и документация это различают. Установки, runtime grant или нового обязательного gate этот вывод не выдаёт.

Scope SHA: `0ecdf01899b60a06958b7e4f08c61c6c4262de3eecb7c9641f35b5b81dbc124c`. Production SHA: `aeb0a2e83597630b1cf57443bb581a22a239ed56f74dd4108813ec8b87737aa5`. Все исходные и snapshot pins повторно совпали; точный перечень — в ledger.
