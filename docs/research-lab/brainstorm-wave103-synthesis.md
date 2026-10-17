# Волна 103 — два уточнения, три объединения

SOURCE-синтез принят Root по отдельному handoff: **NEW 0 / REFINE 2 (A,C) / MERGE 3 (A,B,C) / REJECT 0 / scientific ADMIT 0**. REFINE пересекается с MERGE; B — только MERGE. Private coordinator body не включён и не читался. Формальная точка — 17 октября 2026, 12:00 UTC; ранний dispatch 11:57–11:58. Следующая — **12:45 UTC / 15:45 МСК**, шаг 45 минут.

| Автор | Существующая ветка | Решение и предел |
|---|---|---|
| A | [fusion11](../candidate-generation/11-fusion.md), HYP-053; overlap RB1/RB4 | REFINE/MERGE: накопленное насыщение категории при одном pre-fusion D/depth. |
| B | HYP-002 / TLAB-016; rounds016/044/052/071; transfer TLAB-018 | MERGE: semantic alias, различимая функция и полезность модели — разные утверждения, уже записанные ранее. |
| C | TLAB-008 / [L03](../loss-selection/03-listwise.md) / [028](brainstorm-wave028-synthesis.md) / [059](brainstorm-wave059-synthesis.md) | REFINE/MERGE: случайный размер полного Y может менять NDCG-порядок при полном coverage. HYP-035 остаётся отклонённым историческим alias; не возобновляется. |

**A.** Ручной шестипредметный пример residual-product арифметически согласован; это не исполненный тест и не универсальная неэквивалентность любому MMR. До будущего selector-контраста явно требуются `R20⊆D` либо отдельные определения r/q для protected товаров вне D. При `|D\R20|≤200` обе ветви включают весь остаток: candidate-coverage контраста нет. Если остаток больше, короткие категории могут получить искусственное преимущество, а насыщение — вытеснить несколько нужных покупок одной категории. Источник использовал random split; REES46 gain неизвестен. Нового графа или изменения C0 не принято.

**B.** Имя не входит в semantic signature; дополнительный witness не делает функцию полезной. Типы Featuretools не устанавливают истинность action mapping. Повтор прежнего conformance ради номера волны не требуется.

**C.** При Y={a} с вероятностью .45 либо Y={b,c} с .55 коэффициенты ожидаемого full-Y NDCG ставят a первым, BCE/нормированный PairLogit — ниже b,c. Здесь m=h и coverage factor=1; поправка028 не устраняет mismatch. Это population-свидетель при допустимых item-specific scores, без утверждения представимости конкретным learner, распространённости эффекта или quality gain.

Root выбрал **OBJECTIVE-CANARY103, READY, owner Root** в существующем objective contrast TLAB-014/TLAB-008/L03. [SOURCE](archives/wave103/objective-canary-source-v1/README.md) и [независимое статическое ревью](archives/wave103/tlab-wave103-objective-canary-independent-source-v1.md) готовы. Следующее действие Root: внешне ограничить и проверить launch envelope, затем один stdlib literal run ≤5 CPU/8 wall секунд,128 MiB,64 KiB output. Критерий: независимые шесть NDCG-перестановок, ожидаемый порядок относительно BCE/PairLogit, m=h, coverage factor1 и singleton-control. **Actual UNRUN. Запуск — после отдельного допуска Root и проверки внешнего ограничителя; приёмка результата — после original terminal/reap/receipts.** READY обозначает готовность шага, а не разрешение. Это необязательная проверка аналитического примера, без нового gate/ID, данных, fits или quality claim. Scientific ADMIT0 относится к новым эмпирическим ML-опытам.

Main C0, B41/W44 fixed-C attribution, frozen final, negative2027, 14/19 accepted и optional010–013 неизменны. Архив сохраняет самостоятельные FIRST и позднейшие ограничения отдельно; исторические HYP035/UNRUN формулировки внутри оригиналов не переписаны.

Точные оригиналы, SHA256, modes и отсутствие C-helper pins перечислены в [однозначной описи](archives/wave103/publication.json): девять A/B/C FIRST/pins/freezes, три skeptic-файла, семь существующих helper-файлов, три canary SOURCE и два independent SOURCE review. Metadata paths/URLs — provenance; actual data, private Root bodies/controllers и coverage outputs в архив не входят и по ссылкам не открывались.
