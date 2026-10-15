# 019 worker seam v2 — narrow independent rereview

2026-10-15. **ACCEPT IMPLEMENTATION DIRECTION, с одним обязательным уточнением shared deadline перед exact freeze.** Проверены v2, исходный critic и canonical backlog019.0code/data changes, tests, matrices, Pool или fits. Новые actual009 outputs/models не открывались. Это design review; execution/code acceptance ещё отдельные.

## Исходные blockers закрыты

Canonical globalmax−1e−12 tie set→fewer selected trees→smaller depth→incumbent→configID восстановлен точно; новых leaf/L2 preferences нет. Eligible incumbent остаётся неизменённым6000 model на final accepted schema, без refit. Population наследуется всеми016arms, не приписывается intelligent strategy.

Fresh one-gate child и sequential fit workers устраняют same-process historical peakRSS fallback. GatePASS фиксирует26000 для всех новых fits; validated resource/cardinalityFAIL допускает6000 один раз, semantic/API/unknown→STOP. Typed DuckDB OOM можно классифицировать как resource; произвольный signal/native RuntimeError — нельзя. GatePASS не обещает fit/Newton feasibility.

TERM5→KILL→reap5, dedicated group, file-backed logs, finally cleanup, запрет OS subprocesses и failed/unknown STOP заданы. Unknown descendant не считается нулёмCPU и не позволяет следующий launch. Это cooperative protocol с честно записанным overrun, не hard OS guarantee; escaped descendants не выдаются за полностью контролируемые.

Все arm/look slots резервируются до spawn/preparation. Full300 fit+parameter/tree gates предшествуют scores. Entirely completed/independently verified arm — единственная eligible единица; late failed arm теряет все checkpoints, но сохраняет consumed reservations/seen metrics. Такая консервативная prospective политика допустима и закрывает исходную неопределённость partial outputs. Не выкидывать failed arm/looks из итогового ledger; partial grid отличается от всех4successful fits. None feasible→STOP/no refill.

## CPU partition согласован

Для каждого launch пусть `P` — фактический productionCPU после предыдущего reap. Из production ceiling3300 остаётся `3300−P`; child allowance выдаётся не больше этого остатка минус60parent/cleanup reserve.300verification/publication reserve остаётся вне production allocation. Если остатка не хватает, следующий slot unattempted/consumed по заранее объявленному ledger, не launch с заново полным лимитом. После reap unused allocation освобождается по **actual**, а не считается spent. Это уменьшает доступный fit budget, не увеличивает3600total.

Одновременно child контролирует свой cumulativeCPU от process entry/imports, parent — собственную launch delta/reserve. Поэтому livechild не нужно ошибочно включать в ещё пустой CHILDREN. Final authoritative `ΔSELF+ΔreapedCHILDREN` содержит parent+все waited workers один раз; child receipts только reconciliation. Failed/killed children оплачиваются; недоступный usage/overrun означает failed/STOP до новой работы. Guard threshold для parent должен оставлять настоящую cleanup margin внутри60, а не расходовать все60 доTERM. Exact numeric margin — implementation-freeze field, не повод увеличить cap.

Independent verifier после producer exits должен измеряться отдельным fresh invocation, добавляться **один раз**, вместе с publication/outer-controller tail в оставшиеся300. Нельзя поверх producer SELF+CHILDREN снова добавить его полный outer CHILDREN aggregate. Unknown historical008 CPU остаётся отдельно неизвестным. Весь cost ниже caps — будущий measured gate, не доказанная сейчас feasibility300trees×4.

## Единственное обязательное уточнение: outer wall deadline

V2 называет3600s **parent** deadline, но verifier запускается после выхода этого parent. Для сохранения ранее предложенного shared3600wall необходимо передать **один outer absolute deadline/started_at** verifier и publisher. Проверять remainingwall перед verifier launch и ограничить его временем до этого же deadline с cleanup. Не выдавать verifier свежие3600wall только потому, что ему зарезервированы300CPU: IO-bound production может завершиться близко к3600 приCPU<3300, а последующая verification уже выйдет за sharedwall.

Зафиксировать numeric wall cleanup reserve отдельно от60**CPU**: минимум TERM5+reap5 плюс оговорённый receipt/final-controller allowance; reserveCPU нельзя превратить в wall×threads оценку. Тот же surviving outer owner должен закрыть totalCPU/publication tail и не принимать артефакт по status-file до успешного reap/final guards. Это короткий design appendix, не новый fit, experiment, dependency или budget. Без него complete execution claim под3600wall не определён; implementation может строиться вокруг этого explicit handoff.

## RSS и016 fidelity

Parent≤1GiB+worker≤7GiB и сумма нормализованных peaks≤8GiB — консервативный simultaneous-job bound, сильнее прежнихper-process8GiB. Это честно может вызвать6000 fallback раньше; tighter partition требует coordinator agreement **до019gate outcomes**, как явно указаноv2. Parent не держит arrays/model/Pool. Последующий verifier имеет отдельный8GiB job scope, включая его controller, а не незаявленную параллельную helper memory. Нормализация Macbytes/LinuxKiB и checks остаются code-review gates.

Сохранение both trained_iterations=300 и scoring_prefix=50/150/300 в выбранном spec — корректный способ не предполагать prefix↔fresh-shortfit equivalence. Каждый016arm наследует300training procedure и **один** fixed scoring prefix; incumbent winner наследует50/50. Это не три новых016looks и не extra refit, но потенциально дороже: существующие4fits/2CPUh остаются, с failure/unattempted без refill. Model copies/shrink не должны мутировать исходный300model; saved-prefix predictions/tree counts требуют отдельной substantive zero-refit verification.

Перечисленныеv2 tiny lifecycle faults достаточны как старт meaningful implementation gate, но пока не выполнены. Exact approved parent/worker context, global tokens, input pins и source/model proof остаются обязательными до data/fit. Retrospective22–23, availability после used maturity24, actual sealing до reserved25targets и positive simulated compute gap сохранены. Direction accepted; final design должен включить outer deadline appendix, затем exact code/fault review и отдельное execution approval.
