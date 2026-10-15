# Публичное воспроизведение018: V1 требует исправлений

Root подтвердил пять P2 после двух независимых wholeCODE reviews. V1 заморожен и не принят; entry, recipe, tests и инструкция этого кандидата не установлены и не опубликованы. Исправления выполняет исходный автор; отдельные адресные rereviews и Root решение ещё нужны. Реальных новых fits не разрешено;018 остаётся partial,13 из19 задач приняты.

| Область | Подтверждённое замечание | Требуемое поведение |
|---|---|---|
| A001 | Manifest экспортов не удостоверяется при чтении; W B41 prefix не сравнивается с B | Связать consumed bytes с manifest и exact B41 prefix для train/selection до соответствующего native operation |
| B001 | Вторичная ошибка записи failure report/telemetry маскирует первичную | Best-effort evidence сохраняет вторичную причину отдельно; наружу возвращается первичная ошибка |
| B002 | Recipe hash, parsing и saved copy читают разные bytes | Один bounded authenticated snapshot для hash/parse/copy |
| B003 | Поздние core imports и final provenance не связаны с исходно проверенным code | Связать executed closure с initial witnesses и проверить dependency/recipe pins до использования/завершения |
| B004 | Pool constructor не задаёт2threads | Явно thread_count=2; classifier setting не ограничивает отдельный constructor |

Дополнительно Root попросил убрать ненужный Logloss group_id для совпадения с историческим caller; численный эффект добавленного metadata не доказан и шестым P2 не объявляется.

[Пятнадцать byte-exact оригиналов](evidence/public018-code-v1-changes-requested/publication.json) содержат A/B reports/ledgers/finalfreezes, один A и два B in-memory AST probes с code/results/stdout/timing и Root disposition. Snapshot/source refs в них исторические;170 inputs не копировались. Probe exit0 воспроизводит дефект и не означает product acceptance. Probe scripts хранятся под docs и не являются collectable tests; публикатор их не запускал.

Авторский final proof — шесть неизменённых методовPASS изV2 плюс один исправленный emptyC targetedPASS изV3. Ранний7BODY/outerBSDwrapperEXIT1 и V2fixture-errorEXIT1 сохранены; whole7 rerun success не заявляется. Первоначальный synthetic allowance60CPU/120wall/512MiB не пополняется. Отдельный ресурсный план обязан учитывать все одновременные CSV/DB/spill/Parquet/matrices/nativePool/model/ranking состояния и полный process lifetime.40GiB — минимум, не worst-case; disk331GiB snapshot сам по себе достаточность не доказывает.2GBengine/8GiBspill не являются RSS guarantee; cooperative checks не заменяют будущий отдельный Root finite operation.

Принятые015, финальный отчёт и Oct22 fixed-model parityslice остаются в прежнем scope; они не удостоверяют новый публичный raw→fresh collections→две NEW frozen300tree модели→comparison маршрут.
