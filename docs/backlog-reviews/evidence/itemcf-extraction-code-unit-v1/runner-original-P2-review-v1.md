[P2] Сохранять первичную ошибку и outer receipt при ошибке cleanup — `/tmp/tlab-itemcf-code-unit-outer-proposal-v1.py:35–40`.

После первого timeout/interrupt `killpg` и второй, уже ограниченный оставшимися ≤2 секундами, `communicate` не защищены от вторичного исключения. Например, истечение этого bounded reap выходит из обработчика до записи receipt на строках43–52; первичная причина заменяется вторичным TimeoutExpired, а сведения о неизвестном reap теряются. Требуется сохранить primary/pending evidence до cleanup, отдельно защитить kill/reap и записать вторичные ошибки с неизвестным reap, сохраняя исходный30wall предел. Успех допустим только после известного reap. Это вывод из source, без выполненной fault-пробы.

Других поддержанных blockers в runner/request не найдено. Единая `scripts.itemcf_extraction` identity регистрируется до compile/exec; kernel/тесты связаны pins и пятью method IDs. Inherited hard15 допускает child hard10; soft1/4/10 сохраняют предложенный CPU envelope. Request approved=false; отдельный Root issue/hash обязателен. RSS/агрегация и final-tail оговорки не повышены до доказанных hard bounds.

Все входные pins/snapshots повторно свежие. Только source review: без imports кандидатов/native/SQL/tests/fixtures/ML/realdata/Git/network/helpers/canonical writes. Runner, outer и пять тестов UNRUN; runtime grant не выдан.
