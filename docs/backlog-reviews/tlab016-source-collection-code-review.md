# 016 source producer — independent frozen-code review

**CHANGES REQUESTED: два P1 consumer gaps, три воспроизведения.** Producer execution остаётся HOLD. Это review exact frozen implementation и tiny faults, не actual source/model acceptance.

SHA256 до/после совпадают:

| Файл | SHA256 |
|---|---|
| scripts/feature_program_collection.py | fc9de612c7ed69948d4b3bd2d66416f1b44600d7698b1f319ad3ad3e9439fc5a |
| tests/test_feature_program_collection.py | 7f03ae6af205a8ef5f7e81eb71fdfcb59cc3a4879c7801baafb4abc720f17d80 |
| docs/experiments/feature-program-collection.md | a3ab3e17aeb4d4295e3160ddaa697e0c18f3a5a5bcb769a38e822583d0374833 |

Own oraclefde04a6303392c74b7a7f8164ce194a3d021653bb6766f4e664078edf4491e7b сохранён без изменений.

## P1 — report.run_id не связывается с принятым producer

`verify_source_acceptance`, строки286–297. Manifest/plan/approval runID сравниваются, но producer report.run_id пропущен. Независимый tiny fault заменил только report.run_id другим64hex; затем свежо обновил report pin, producer-parent report ref и parent/approval pins. Формулы/output/evidence source map не менялись. Consumer вернул physical_consistency_passed.

Нужно до использования report явно проверить report.run_id == manifest.run_id == planned.run_id == accepted runID. Пин доказывает байты report, но не смысл его собственных identity fields. Добавить regression с fresh reseal затронутых pins, а не простой hash mismatch. Неправильный report нельзя принять как полный receipt текущего source run.

## P1 — full-lifetime parent wall/RSS допускают невозможное занижение

Строки330–344. CPU receipt уже обязан быть не меньше measured producer CPU. Аналогичных нижних границ для wall/RSS нет. Два собственных свежеперезапечатанных receipts приняты:

- producer parent.wall_seconds=0 при report.seconds=0.586364958;
- producer parent.peak_rss_bytes=1 при report.process_peak_rss_bytes=156,319,744.

Все SHA/parent producer path refs актуальны; прочие поля source proof сохранены. Оба вызывают successful consumer return. Это противоречит смыслу полной measured lifetime, включающей body и tail. Помимо верхних1200wall/8GiB нужны parent wall+предобъявленная численная tolerance≥report.seconds и parent peakRSS≥report peakRSS; CPU lower bound сохранить. Для совпадающих целых bytes tolerance не нужна. Нельзя публиковать успешный full-lifetime proof из явно меньших счётчиков. Final oracle-parent receipt должен аналогично связывать его собственный measured body с full-lifetime owner; окончательный oracle evidence schema согласуется отдельно, не придумывается здесь задним числом.

## Подтверждённые границы

Own fresh faults показывают intended separation: count2→3 проходит physical inspection, но повторное использование старого fixed source proof после reseal output/manifest отвергается по exact output map. Старые45 fields сохраняются по всем rows; freshly resealed from_popular change отвергнут. Перенос существующего emptyC query за day partition не добавлял rows и отвергнут whole-Q comparison. Known failed marker остановил consumer до prepare_plan. Source claim существует уже внутри paid planner; planning failure сохраняет claim, повторная попытка не доходит до planner. Неверное execution approval останавливает до source SQL.

Статически prepare_plan действительно начинает с strict accepted collection closures/canonical14, exact actual registry SHA/B41 order, shared source/protocol clocks и explicit raw/global-peer/retrieval policy; строит один18+11 union и57physical fields, не все8 numeric bundles. Dynamic required pins выводятся из фактически проверенных closures+contract/registry/CODE. Actual206-pin plan здесь не запускался и не объявляется доказанным из mocked fixture. Source connect read_only, producer state TEMP; Y refs в fixture отравлены отсутствующим путём, source calculation их не открыла. Реальные Y могут хешироваться механической lineage, но SQL relation/Y parsing не добавлены.

SourceAudit включает imports/planning/approval wait в ENTRY_MONOTONIC и absoluteSELF origin0. Own CPU900.01, expired1200wall, RSS8GiB+1 и child usage guards отвергаются. Физический final inspector actual source path получает тот же persistent deadline. Общая terminal lifecycle наследует ранее принятый ExecutionAudit: close/manifest/initial summary оплачены до final counters, postreceipt guard/knownfailed semantics сохранены; minimal tail остаётся обязанностью успешного parent. Это cooperative ceilings, не OS enforcement. Source900+oracle900 остаются частями7200; fits0, отдельный будущий four-fit claim не заменяется source claim.

## Проверки и пределы

Собственный harness v2: **13/13 наблюдений PASS**, из них три подтверждают дефектное принятие и не являются утверждением корректности. Десять остальных проверяют rejection/guards. Source/query/candidate inputs≤31 включая derivedoldF, только selected12 новых physical columns. Tiny plumbing использует author setup/producer и mocked mechanical planner; expected mutations и assertions независимы. External proof в fixture намеренно opaque synthetic object, не настоящий formula approval. Полный author9 suite заново не запускался как подмена независимых faults.

V2 wall1.822066625s, SELF2.236914CPU/RSS158,318,592 bytes после imports. Initial own harness результатов не стёрт: no-retry FileExistsError был правильным production rejection, но helper ошибочно не включал этот тип в ожидаемые exceptions. V2 исправляет только exception taxonomy и добавляет четыре resource probes; initial report сохраняет failure. Repo/oracle bytes не менялись, Root019live outputs не читались. Actual source/Pool/model/predict/native fits/actual acceptance writes:0.

Evidence: `tlab016-source-producer-independent-faults.py`, `tlab016-source-producer-independent-results.json` (initial helper failure); `tlab016-source-producer-independent-faults-v2.py`, `tlab016-source-producer-independent-results-v2.json` (13 observations). После batch fix нужен targeted replay трёх original resealed contradictions и healthy scope; approval/execution остаются отдельными gates.
