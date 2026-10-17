# LOCAL192 — independent actual review

**PASS: фактический локальный commit точно устанавливает разрешённый frozen payload из 192 путей. Новых замечаний нет.** Проверка выполнена после закрытия всех четырёх phase terminal; runner повторно не запускался.

Независимые read-only Git reads подтвердили:

- HEAD `13ce92d650a59794d1a503063c23e9fc9529bcbc`;
- tree `5fc997f2d9e24fe1a65ee04562ec8aa0adfa71de`;
- единственный parent `c538de4097322715fccac494e2b2becc3279e8e1`;
- прежнюю ветку `codex/research-features-and-targets`, точные commit-message bytes и SHA1 самого commit object.

Полное committed tree содержит 3312 записей против 3140 у parent. Изменены ровно 20 старых путей и добавлены ровно 172; удалений нет. Для остальных 3120 прежних записей совпадают blob ID и Git mode. Их содержимое повторно не читалось: это полная проверка tree metadata, не semantic review 3312 файлов.

Для каждого из 192 путей committed blob, рабочий файл и frozen candidate совпали побайтно, по SHA256, размеру и ожидаемому mode. Набор путей/операций точно соответствует manifest SHA256 `51746b8bb6d69dbdfba1882ccdded2364f1ab77e4a118c665b28f08497a6efa1`. Все 27 code/test/recipe путей совпадают с принятым 643-file SOURCE-срезом. Два coverage test файла получили разрешённый filesystem mode 0644 вместо 0444; bytes и Git mode 100644 сохранены. Все 15 guards — 13 dependencies и два scientific/history документа — плюс `.gitattributes` неизменны. Удаление четырёх новых document inserts точно восстанавливает прежние body hashes.

Index содержит ровно committed tree, без unmerged stages. Его SHA256 до/после независимых reads — `2271b411699f7a26d3bf97ceca6425977198e5bade53acb8deb56a23b97320d9`. Рабочее дерево, index и untracked status CLEAN; повторное чтение HEAD подтвердило тот же commit.

[Final actual receipt](/tmp/tlab-full-pipeline-audit-LOCAL-execution-v1/final-actual-receipt.json), четыре result receipts и terminals связаны точными hashes. Apply `0c55f5`, stage `826668`, commit `12da43`, verify `07197a` — известные CLOSED0, без живой session. Проверены все 67 CLOSED/reaped команд, соответствующие journal events и 120 сохранённых stdout/stderr. Единственный nonzero — ожидаемый пустой `check-ignore` exit1.

Обычный `git diff --cached --check` выполнен один раз с exit0 до обычного commit. Commit argv не содержит hook/signing/filter bypass flags. Семь recorded config hashes и текущие read-only config/attributes совпадают с policy pins; active hooks отсутствуют. Прочитанный runner SHA256 `1095454d…` наследует environment, запрещает alternate index/config controls и требует тот же проверенный index перед commit (`operation.py:139–145,180–203,295–310,334–341`). Исходные receipts и политика не переписывались.

Установленные CODE aggregates сохраняют точные disjoint списки 57 и 32 уже выполненных синтетических методов: **89 уникальных**, не 114+32. Старый FAILED v2 и исторический R3-v1 pending статус сохранены как прежние snapshots; актуальный aggregate указывает qualified89. Эта проверка установки не запускает тесты заново и не расширяет их смысл до native ML, полного raw pipeline, exhaustive F source proof, late-arrival completeness или научного выигрыша. Зафиксированный CI всё ещё пересекает ноль; будущие no-fit/native планы не становятся actual quality evidence.

Выполнены только read-only Git, чтение источников/receipts и stdlib hash/JSON-проверки. Project imports, тесты, SQL, модели, native ML, сеть и canonical/Git mutations отсутствуют. Pins и freeze проверены повторным чтением; STOP.
