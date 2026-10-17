# Волна 101 — два уточнения существующих направлений

Root принял SOURCE-синтез **17 октября 2026, 10:41:37 UTC**: **NEW 0 / REFINE 2 / MERGE 2 / scientific ADMIT 0**. REFINE и MERGE относятся к тем же двум предложениям. Новых ID, обязательных задач, quality-gates и разрешённых запусков нет. [Оригинал решения](archives/wave101/tlab-root-wave101-adoption-v1.json).

Два независимых FIRST были заморожены до отдельного чтения скептиком. Root наблюдал dispatch в 10:30 UTC; индивидуальные начала UNKNOWN. Фиксация FIRST после dispatch — обычная работа, не причина сдвигать сетку. Следующий срок **11:15 UTC / 14:15 МСК**, интервал **45 минут**.

| Автор | Решение | Что добавлено и что это позволяет сказать |
|---|---|---|
| A | REFINE / MERGE в [fusion11](../candidate-generation/11-fusion.md), TLAB-004/014 | Placebo точной копии списка различает дополнительную item-информацию и дополнительный вес канала. Разделение исходного веса между точными копиями сохраняет математический score. Count/cosine не объявлены aliases; качество и полезность нормировок не установлены. |
| B | REFINE / MERGE в [существующий influence099](brainstorm-wave099-synthesis.md), HYP-002 / TLAB-013/014/016/019; optional, deferred | Фиксированный prefix300 уточняет совместную таблицу query-эффектов двух существующих seeds и все одно-query удаления. Это описательная проверка концентрации уже наблюдённой смены знака на reused73positive, не seed distribution, fresh confirmation или причинное объяснение. |

У A малая новизна: weighted RRF и repeated votes уже записаны в fusion11/review09–12. Узкая добавка — signed exact-copy witness. У B основные sign/influence/deletion механизмы уже есть в 099A; fixed300 меняет срез. При отсутствии authenticated300-векторов будущему consumer могут понадобиться четыре загрузки моделей и **четыре новых prediction calls**, 3268596 score values. Нулевые fits не означают нулевой scoring. Ни consumer, ни эти calls не допущены; существующий отрицательный результат их не требует.

Root вручную сверил рациональную арифметику A и вымышленные агрегаты/удаления B. Tiny RRF-попытка скептика остановилась **до арифметики**: macOS отверг RLIMIT_AS. Это FAILED, без PASS и без повторной попытки. Авторские gates остаются UNRUN. Проспективные потолки ресурсов — предложения, фактическая достаточность UNKNOWN; они не являются разрешением.

FIRST и скептик сохраняют прежние сообщения Q100 pending/INCOMPLETE как исторический срез. Более поздняя [приёмка Q100](../backlog-reviews/covis-candidate-discovery-results.md) установила конечное совпадение трёх графов и 100 артефактов без Y/ML. Она не устанавливает качество, не превращает старый 32 GiB physical-I/O screen в PASS и не допускает 6000. План 6000 находится на SOURCE-ревью, runtime UNRUN. Исходные final/CI, negative seed2027, 14/19 accepted, TLAB-014 ongoing и 010–013 optional неизменны.

## Точные оригиналы

| Источник | Текст | Pins | Freeze |
|---|---|---|---|
| A FIRST | [FIRST](archives/wave101/tlab-wave101-A-FIRST.md) | [pins](archives/wave101/tlab-wave101-A-pins.json) | [freeze](archives/wave101/tlab-wave101-A-freeze.json) |
| B FIRST | [FIRST](archives/wave101/tlab-wave101-B-FIRST.md) | [pins](archives/wave101/tlab-wave101-B-pins.json) | [freeze](archives/wave101/tlab-wave101-B-freeze.json) |
| Отдельный скептик | [review](archives/wave101/tlab-wave101-skeptic-v1.md) | [pins](archives/wave101/tlab-wave101-skeptic-pins.json) | [freeze](archives/wave101/tlab-wave101-skeptic-freeze.json) |

Все десять архивных оригиналов побайтны. Их metadata references сохранены как provenance; внешние и приватные тела по этим ссылкам в пакет не входят. Новая очередь не создаётся.
