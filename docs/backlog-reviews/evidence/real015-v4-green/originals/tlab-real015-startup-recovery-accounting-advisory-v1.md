**Да, можно подготовить явно разрешаемое versioned startup recovery для первого ещё не начатого project owner, сохранив33914/43200 и1000/300. Но исходную операцию восстановленной считать нельзя.**

[Исходное разрешение](/tmp/tlab-root-real015-original-operation-issued-v1.json) прямо устанавливает: `Any failure consumes operation` и запрещает автоматический retry. Поэтому exit1 окончательно расходует **исходную внешнюю операцию запуска**, даже при отсутствии `controller.consumed` и owner Popen. Старые consumed/failed receipts, namespace и unknown-флаги сохраняются.

[Failed receipt](/tmp/tlab-root-real015-original-failed-external-receipt-v1.json) подтверждает:

- owner claim не израсходован, owner/source/models/Y/fit/predict не запускались, четыре допуска не выданы;
- внешний процесс имеет верхние оценки0.17wall/0.16CPU; это не восстановленный full-tree CPU;
- `original_V6_unknown_active_work=true` и неизвестный full-tree CPU остаются исходными фактами.

Таким образом, owner4200CPU/7200wall/8GiB **не был начат**. Это позволяет просить об одном восстановительном старте того же FIRST project-wide claim, но не даёт автоматического разрешения. Новый внешний запуск требует отдельного явного решения Root после независимого V4 CODE review. Новый внешний namespace допустим как версия recovery; canonical project claim остаётся тем же, прежние маркеры не удаляются.

Расходы failed startup, принятой диагностики и нового старта должны оставаться в едином учёте внешней инженерии. Исходный Root shared reserve10CPU/10wall не возобновляется; нельзя выдавать повторно полный внешний лимит, забыв предыдущие расходы. Неизвестный full-tree CPU нельзя заменить округлённым CPU процесса.

Это инженерия запуска будущего исполнения, поэтому **само исправление env guard не требует добавки к33914**, если модели, признаки, native-параметры и основания выбора неизменны. Резервы1000 metadata и300 authentication не увеличиваются. Если recovery изменит actual decision basis, потребуется узкий additive accounting перед новым заявлением о выполнении12h условия. [Контракт:7](/Users/mdpospelov/tlab-recsys-2026/docs/experiments/heldout-contract.md:7)

**300 с — заявленная граница конкретной подготовки/authentication, а не отдельный установленный runtime guard.** Общий guard4200 не обеспечивает containment этой стадии в300. На уже существующем initial Root gate можно требовать подтверждённый полный preparation bound≤300; превышение останавливает зависимое продвижение и требует обновления учёта. Нельзя объявлять отдельный hard300 установленным. [Контракт:11](/Users/mdpospelov/tlab-recsys-2026/docs/experiments/heldout-contract.md:11)

Следующее конечное решение Root: принять либо отклонить **один versioned recovery request** с точными исправленными pins, сохранённым FIRST claim и оплачиваемым ограниченным startup envelope. Этот advisory такого разрешения не выдаёт и не задерживает независимое V4 CODE review.
