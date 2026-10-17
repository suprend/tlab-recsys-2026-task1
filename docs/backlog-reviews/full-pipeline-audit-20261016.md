# Полный аудит pipeline: исправления и проверенные границы

SOURCE-срез 2026-10-17 00:13:55 UTC; состав проверенного пакета, до отдельной actual LOCAL-приёмки.

Исторически приняты рабочий конвейер автоматического построения событийных признаков и полный повтор зафиксированного исследования на Mac. Базовый B41 включает 18 ручных определений и coverage/missing/retrieval context; выбранное расширение добавляет три item distinct-audience признака. Финальный NDCG: B — 0.459825, W — 0.464947. 95% интервал разницы пересекает ноль: надёжный выигрыш не установлен. Выбор 1189 и 403 деревьев остаётся отдельным exploratory результатом на повторно использованной validation.

Полный аудит нашёл семь проблем на границах pipeline. Исправления и регрессии подготовлены в 27 путях; отдельно приняты 57 и 32 синтетических CODE-метода — 89 уникальных, без failures, errors, skips и реального ML. Независимый итоговый R3 принят с явными ограничениями. Это не новый полный raw/native повтор и не доказательство качества модели.

## Семь исправляемых проблем

AUDIT IDs обозначают findings, а не новые задачи. Исторические результаты не объявлены неверными из-за этих инженерных дефектов.

| Finding | Приоритет | Исправление | Существующая область |
|---|---|---|---|
| AUDIT-20261016-01 | P1 | Согласованы live recipe, dependency pins, константа команды и live guide. | TLAB-018 |
| AUDIT-20261016-02 | P2 | Обычный CLI использует строгую canonical Q/C lineage-проверку. | TLAB-019 |
| AUDIT-20261016-03 | P2 | Корректный день без Q отделён от отсутствующего или неуспешного shard. | TLAB-017 |
| AUDIT-20261016-04 | P2 | Cleanup сохраняет failure receipt и исходную ошибку при проверенных close faults. | TLAB-003/004/005/007 |
| AUDIT-20261016-05 | P3 | Проверяется замкнутость имён registry/retrieval и derived missing masks. | TLAB-005/016 |
| AUDIT-20261016-06 | P2 | Допуск scores больше не подменяет проверку точного порядка ранжирования. | TLAB-019 |
| AUDIT-20261016-07 | P2 | Legacy EDA cache сверяет фактическое содержимое через witness. | TLAB-001/018 |

В recipe изменены только шесть разрешённых SHA, остальные 13 dependencies и научные поля сохранены; все 19 pins, paired constant и guide согласованы. Это не новый полный Mac/native запуск. Два старых coverage test sources сохраняют bytes, получая явно разрешённый canonical mode0644 вместо SOURCE0444.

## Что фактически проверено

[Первые 57 методов](pipeline-audit-20261016/CODE-result.json) покрывают семь исправлений, rich all-eight программы, typed9 импорт и существующие FakeCLI lifecycle controls. [Дополнительные 32](pipeline-audit-20261016/CODE-core32-result.json) включают 27 core контролей, batching(2), selected-F57 composition(1) и empty verifier(2). Списки не пересекаются. Оба принятых запуска имеют owner/child exit0, reaped child и нулевые failures/errors/skips/реальные ML imports.

В small fixtures проверены temporal/maturity endpoints, Q/fullY, retrieval duplicate/tie/boundary и label independence, manual18 NULL/history/denominator, seeded program allocation, fullY ranking и paired bootstrap. Batching меняет реальную same-anchor candidate domain и повторно использует TEMP state; literal/mutant controls различают denominator4/share0.25 от1/1 и stale category. Selected-F57 проверяет пятистрочную single-chunk композицию, column order/types/NaNs/large IDs, label perturbation и training/inference parity; B41 не целиком hardcoded. Это не независимый gold каждой формулы на всех реальных строках.

[Global R3-v2](pipeline-audit-20261016/global-R3-v2/report.md) сохраняет пределы: semantic review не покрывает все 643 hash-checked файла, full raw/source completeness/late arrivals, saturation/throughput, concurrent hostile cache writer, произвольный native cleanup и реальную native CLI не проверяли. В просмотренных статических путях подтверждённой temporal leakage не найдено; это не общий сертификат отсутствия утечек.

История не переписана: controller v1 с P1 не выдавался; runtime v2 после 57 assertion statements завершился child120/owner1 и остаётся FAILED. Успешный v3 не превращает57 в114. Batching SOURCE v1/v2 были UNRUN, gap закрыт в v3 до фактической проверки. Ошибка metadata parser e954c0 касалась multiline unittest description и не вызвала повторного CODE.

## Что остаётся

LOCAL41 принят в c538de4; exact476 опубликован и draft PR обновлён. Исправленная обычная native CLI end-to-end и callback-abort ещё не проверены. Прежняя native попытка завершилась FAILED до fit, её разрешение закрыто. Следующий необязательный native шаг пока SOURCE-only: свежая no-fit регенерация, независимые проверки и новые genuine approvals; 122 логических слота не являются свежим inventory. Нового native или publication разрешения нет.

[Будущий native SOURCE-план](pipeline-audit-20261016/native-future-plan/readiness-plan.ru.md) принят только для планирования: пять producer hashes в старых approvals устарели. Нужны genuine no-fit regeneration, независимое чтение outputs, новые approvals, actual fresh inventory и новый concrete worker/controller до возможного вопроса о бюджете. Предложенные50CPU/65wall имеют adequacy UNKNOWN. Это дополнительный инженерный lifecycle, не обязательный недостающий scientific deliverable Task1.

Приняты 14 из 19 исходных задач. TLAB-014 continuous, TLAB-010–013 — четыре отложенных optional эксперимента. docs/backlog.md остаётся единственной очередью; новые IDs, обязательные научные gates и бюджеты не создаются. Научный отчёт, final reservation, исходный deadline и45-минутная сетка не меняются. Волна084 сохранена как qualified research/refinement,085 SOURCE complete без admissions, её raw archive отложен до следующего небольшого среза и не задерживает этот пакет.

[Карта архива](pipeline-audit-20261016/publication.json) различает raw originals и один safe-derived pins: удалены ровно три PersonalOS body fields, другие JSON значения/типы сохранены. Raw anchor pins остаётся TMP; исходный freeze не связывает derivative. Private worker/controller/issuer/consumed/human/policy bodies, raw data и модели исключены. Прежние absolute TMP references внутри immutable reports сохранены как история; карта даёт durable archive aliases.
