# Round049 — восстановление проверки без нового эксперимента

**Статус: методическое предложение для backlog, не разрешение на повторный запуск.** Изучены первичные источники и опубликованные аудиты009/019. Данные, модели, targets и live019/016 outputs не открывались; вычислений и изменений кода нет. Основной вывод: сбой observer не доказывает ошибочность эксперимента, но название «observer defect» также не сохраняет автоматически его валидность. Нужна доказанная локализация причины и отдельная цепочка восстановленной verification.

## Что поддерживают источники

ACM разделяет доступность артефактов, проверку их функциональности и независимое воспроизведение результатов. SIGIR отдельно требует версионировать проверяемый код и связывает artifact review с конкретными утверждениями статьи. Отсюда полезное для нас различие: успешный импорт исправленного verifier ещё не воспроизводит численный результат и не подтверждает качество метода. Это использование принципа, а не заявление о получении ACM badge. [ACM policy v1.1](https://prod-www.acm.bloomreach.cloud/publications/policies/artifact-review-and-badging-current), [официальная процедура SIGIR](https://sigir.org/general-information/acm-sigir-artifact-badging/).

NoREC показывает способ обнаружения ошибок посредством сравнения семантически эквивалентных вычислений. Расхождение указывает на ошибку хотя бы одной стороны; оно само не назначает виновным production или reference. Авторы также прямо ограничивают силу автоматического тестирования: отсутствие найденной ошибки не гарантирует её отсутствия. Поэтому независимый literal counterexample здесь важнее второго «PASS» от общего helper. [Rigger и Su, NoREC, §1–3](https://www.manuelrigger.at/preprints/NoREC.pdf).

ML Test Score различает проверки данных, feature code и модели, предлагает фиксировать ожидания схемой. Это поддерживает раздельную диагностику слоёв, но не содержит нашего готового recovery protocol. Cawley–Talbot показывают риск переобучения критерия выбора: исправление проверяющего не даёт права дополнительно оптимизировать pipeline по уже увиденной validation. [Breck et al., 2017](https://research.google/pubs/the-ml-test-score-a-rubric-for-ml-production-readiness-and-technical-debt-reduction/), [Cawley–Talbot, 2010](https://jmlr.org/papers/v11/cawley10a.html).

## Фактические локальные примеры

В [initial009 failure](../backlog-reviews/tlab009-model-oracle-initial-failure.md) observer сравнивал параметры сохранённой CBM и in-memory metadata слишком буквально: learning rate различался последними цифрами сериализации. Опубликованный аудит сохраняет первоначальный отказ, узкую float-only regression и точную проверку predictions; модели не переобучались. Начальные3.335586 и последующие4.585806 CPU seconds оплачены вместе, согласно [итоговой verification](../backlog-reviews/tlab009-model-output-verification.md).

Другая ошибка была опаснее: nullable BIGINT округлялся при создании expected DataFrame, приводя одновременно к false reject правильного ID и false accept округлённого. [Targeted rereview](../backlog-reviews/tlab009-full-source-oracle-rereview.md) проверил exact transport до DataFrame, крайние int64 и NULL, но объявил принятие именно transport code; actual source acceptance требовала отдельного выполнения. Значит, исправимый observer может обесценить прежнее доказательство, даже если producer впоследствии окажется правильным.

[019 observer review](../backlog-reviews/tlab019-oracle-independent-review.md) описывает ещё два исправления до реальных019 models: effective float32 learning rate и повторное чтение уже проверенного context. Принятие интерфейса явно отделено от принятия actual outputs. Эти опубликованные примеры не являются утверждением о состоянии текущего019 исполнения.

## Предлагаемая классификация и recovery gate

| Наблюдение | Предварительный статус | Что может закрыть проблему |
|---|---|---|
| Ошибка parser/API/transport при неизменных смысловых входах | Проверка незавершена | Узкое доказательство observer defect и проверка прежних артефактов исправленной версией |
| Неверные source/Q/C/Y/F, dtype, temporal boundary, параметры или scoring prefix | Experiment/output invalid | STOP; отдельно рассматриваемый новый этап, без автоматического refit/reselection |
| Неизвестная причина, потерянный terminal receipt или неизвестный расход | Unresolved, не accepted | Дополнительное доказательство в разрешённом scope; отсутствие доказательства не превращается в PASS |
| Корректный pipeline не улучшил frozen B | Валидный отрицательный результат | Сохранить результат; recovery качества не требуется |

Перед любой коррекцией предлагается сохранять первоначальные observer bytes, ошибку, partial report, stdout/stderr, входные pins, producer receipts и фактическую последовательность открытия outputs. Нельзя затирать отказ успешным отчётом, удалять claim или обнулять ledger. Необходима карта воздействия: какой predicate ошибочен, где он применялся, мог ли пропустить настоящую порчу и какие прежние acceptances поэтому требуют пересмотра.

Допустимый observer-only delta должен удовлетворять одновременно пяти условиям. Во-первых, источник ошибки воспроизводится на tiny literal fixture без нового fit или targets. Во-вторых, specification остаётся прежней: тот же набор ключей, окна, NULL, estimator, tie/Recall rule и precision contract. В-третьих, новая regression принимает конкретный корректный случай и отвергает соседний материальный drift; увеличение tolerance «пока пройдёт» недопустимо. В-четвёртых, independent reviewer проверяет минимальный delta и затронутый scope. В-пятых, producer/model/input/config bytes и исходная попытка остаются прежними; новый observer hash получает отдельную связанную attestation, а старый approval не переписывается под новый код.

Например, BIGINT `2^60+1` нельзя принять через approximate float comparison; исправление transport должно одновременно отвергнуть `2^60`. Для CBM-сериализации допустимость конкретного float roundtrip не распространяется на integer L2, boolean, feature order или semantic configuration. Совпадение hashes не подтверждает формулы: обе реализации способны использовать один неверный predicate.

## Граница selection, стоимости и будущих решений

Повторный расчёт **того же** заранее закреплённого контраста по тем же sealed inputs не создаёт нового кандидата. Однако он остаётся наблюдением с CPU, wall, RSS и audit history; считать его неадаптивным допустимо лишь при отсутствии нового выбора по результату. Если исправление evaluator меняет scores, feasibility или winner, исходный выбор теряет доказательство. Это не автоматическое разрешение выбрать другого arm: необходим отдельный внешний разбор влияния и хронологии, без нового fit, refill или открытия holdout.

Для019/016 strict shared caps сохраняются вместе с failed observer cost; cleanup и terminal receipts входят в завершённую проверку. Неизвестный расход нельзя записывать нулём. Resource failure, integrity failure и отрицательное качество сохраняют разные статусы. После открытия confirmation нельзя задним числом исправить prospective chronology: mechanical correction может восстановить отчёт о прежней замороженной модели, но изменение модели, программы или выбора требует явно признать потерю исходного prospective claim.

Предлагаемый итоговый recovery record: причина и counterexample; старые/новые observer pins; неизменные producer/input/model pins; область отозванного и восстановленного доказательства; independent decision; cumulative cost; отсутствие новых fits/arms/holdout opening. Проверка здесь не выполнена и allowance не создан. Это уточнение существующих verification/STOP gates для018 phase2 и финального README, без новой HYP или framework.
