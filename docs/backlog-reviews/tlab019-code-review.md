# 019 — независимая проверка frozen producer

Вердикт: **CHANGES REQUESTED, три P1; actual execution не разрешена**. Проверен producer и его потребление worker receipts. Независимый финальный oracle/controller пока отсутствует; этот отчёт не подтверждает реальные коллекции, модели, метрики или качество настройки.

Зафиксированные SHA до и после собственных faults и scoped author replay совпадают:

| Файл | SHA256 |
|---|---|
| scripts/strong_baseline.py | c44189641210bb26a22c038cdfcdf61522e5baa74981251f776e971d5f9b423e |
| tests/test_strong_baseline.py | 3daf102bf61836623bb9b2092f5ab508b1ca036f47b977b96ee6f8fea4b8276e |
| configs/models/strong-grid.json | d32daac420f447444d987969cdd49ac1cad427bbd7357114d148c02085aed66e |
| docs/experiments/strong-baseline.md | fe3317bbdcd89e52ff70491c8f852e2d3a880e81c18eb3e7293eb245acb1be7f |

## P1 — worker читает заново запечатанный allowance без исходной привязки к issuer

`allocate_slot`/`verify_worker_context`, строки225–280; запуск строки398. Global claim фиксирует пять путей, но не исходные байты выданного slot/context. Worker получает только путь context; его `slot_sha256` можно заменить вместе со slot. Независимые mutations сохраняли execution approval и global claim побайтно: population6000→26000, либо CPU100→3240 и deadline→now+3500. После reseal `verify_worker_context` принимал обе версии до подготовки данных. Это изменения внутри допустимого общего диапазона, поэтому авторские проверки недопустимых2000/3241 их не ловят.

При штатном запуске parent хранит исходный slot и позже может отклонить чужой worker identity; это полезный последующий барьер, но он срабатывает после потенциальной подготовки/fit с неверной популяцией или ресурсами. Нужна доверенная привязка launch к исходному context/slot digest, проверяемая worker до данных, и проверка parent непосредственно перед spawn. Динамическая выдача должна сохранять выбор gate population и исходный outer deadline/remaining allowance, а не только диапазоны. Криптографическая инфраструктура не требуется: достаточно неизменяемого issuer-bound launch аргумента/receipt и строгой проверки его фактических байтов. Hash, взятый из изменяемого самого context, такой привязкой не является.

Дополнительный P2 в строке270: `[50.0,150,300]` проходит равенство с `[50,150,300]`; для reservations нужны настоящие целые типы, как для остальных фиксированных чисел.

## P1 — успешный direct child оставляет живой process group

`run_process`, строки166–187. Cleanup сразу возвращает, если direct process уже завершён; исчезновение лидера не означает исчезновение группы. Собственный tiny child запускал спящий subprocess и выходил0. `run_process` возвращал0 при ещё живых descendant и owned group. Reviewer затем явно послал SIGKILL обоим; реального ML/данных в примере нет.

Проверка worker `child_cpu()!=0` не доказывает отсутствие живого/неожиданного потомка: RUSAGE_CHILDREN учитывает завершённых и waited детей. Следует проверять/убирать оставшуюся собственную группу также после normal exit и на ветках ошибки после exit, сохранять первоначальную ошибку и STOP при неизвестном usage/неподтверждённой очистке. Сам факт forbidden descendants делает такой worker неуспешным; нельзя засчитать orphan CPU нулём или продолжать следующие arms. Проверка только direct `wait()` недостаточна. Изменения не должны расширять общий deadline или TERM/KILL reserves.

## P1 — parent принимает неполный или подменённый arm receipt

`invoke_worker`, строки393–418, и `run`, строки466–480. Успех проверяет число fit и список trees, затем хеширует произвольный `manifest.outputs`; пустая map проходит вакуумно. Собственный fixture с корректным expected identity/consumed receipt, status complete и checkpoints50/150/300, но `outputs={}`, отсутствующими CBM/NPZ и пустыми look reservations был принят. Отдельный вариант дополнительно заменял checkpoint `trained_iterations=50`, depth1/L2=99/population26000/incumbentTrue/config_id=forged; он также принят для исходного arm0/population6000. Native fit не вызывался.

Нужно вывести точный набор восьми outputs из arm/output directory: full300 CBM+JSON и три prefix CBM+NPZ; сверить report artifacts/checkpoint artifacts, пути, digest и отсутствие лишних/пропущенных файлов. До включения кандидата parent обязан проверить checkpoint scope против issued grid: configID, incumbentFalse, population, trained300, trees, depth/L2, конечные метрики, все три consumed/seen reservation statuses и необходимые model/schema/effective-parameter сведения. Producer не заменяет независимый score/formula oracle, однако его mechanical consumer не должен признавать complete arm без артефактов и без правильного scope. Текущее динамическое `seal_outputs` фиксирует имеющееся содержимое и не исправляет отсутствие обязательных outputs.

## Что подтверждено и что остаётся

Scoped author suite: **28/28 PASS**, unittest0.915s, инструментальный wall0.940424125s. Own harness: **8/8 наблюдений PASS**, включая шесть воспроизведений проблем/подтипов и два положительных контроля. PASS в raw evidence обозначает подтверждение сформулированного наблюдения, а не корректность дефектного поведения. Own clocks после imports: wall0.096888667s, SELF0.036018CPU, reaped CHILDREN0.018051CPU, RSS62,865,408 bytes; это стоимость harness, не полного research процесса. Все synthetic files только `/tmp`; repo SHA неизменны. Native Pool/native fit/actual source/matrix/model reads:0.

Статическая проверка положительно оценивает rederivation203→114+коллекции82/30 через принятые planners; canonical spec; once global claim/consumption перед matrix; recognized-resource-only fallback; whole late arm exclusion; full300 перед12 prefix looks; глобальный tie set и наследование trained300/prefix в016. Собственный arithmetic контроль подтверждает SELF40+reaped CHILDREN200=240, child allowance3000 + parent reserve60 + verifier300, без двойного сложения worker receipts.

Финальные measurements явно заканчиваются перед minimal persistence, поэтому внешний controller должен измерить весь tail и передать oracle тот же абсолютный deadline и фактический остаток, максимум300CPU. Это отдельный незавершённый execution gate, а не доказанный текущим producer полный ledger. До настоящих fits нужны исправления трёх P1, targeted rereview, уже существующий и проверенный zero-fit independent oracle entry, внешний lifecycle/controller и exact execution approval. Новых fit, look или CPU allowances этот review не предоставляет.

Evidence: `tlab019-independent-faults.py`, `tlab019-independent-results.json`, `tlab019-author-replay.json`.
