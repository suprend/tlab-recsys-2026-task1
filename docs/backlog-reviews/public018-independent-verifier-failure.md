# Независимая проверка018 остановилась до проверки моделей

Исходный verifier5316 CLOSED/reaped1fc4ff EXIT1. Root принял факты ошибки и её жизненного цикла; [девять точных оригиналов](evidence/public018-independent-verifier-failure/publication.json) сохраняют consumed marker, traceback, process,109-file inventory и исходные unknown flags. Публикатор прочитал только эти маленькие metadata-файлы; файлы, перечисленные в inventory, не открывал и не копировал.

DuckDB1.5.6 не разрешил relation.create_view на source connection, открытом read_only. Ошибка произошла в adapter audit_sources302; тот же native API используется ещё в трёх местах trusted read_matrix. До ошибки случились native imports, аутентификация/inventory и проверка source count42,448,764. Model loads/predicts/fits=0, heldout targets не открывались; Q/C/fullY/матрицы/численные метрики не приняты.

Внешние21,96wall/21,54CPU секунд имеют conservative upper21,98/21,56. Отдельные V6 upper26,950679wall/23,537504CPU не прибавляются кinclusiveexternal; sampledRSS163774464B. Rawunknowntrue после nonzero exit сохраняется, даже при известной причине. Первая отдельно выделенная600CPU/900wall попытка закрыта; свободный переносимый остаток для повтора не объявляется.

Предложенный ремонт использует ephemeral memory connection, ATTACH исходной базы READ_ONLY и temp events alias; научные AST и байты источника должны остаться прежними. SourceV3, focused review и один invented API canary3CPU/5wall/256MiB пока только готовятся. Публикатор не выполнял canary, не устанавливал adapter и не выдавал новую проверку. Любая намеренная следующая операция требует отдельного Root решения, автоматического retry нет.

Успешный producer79330, две новые fixedfit модели и clean environment остаются приняты в [своём процессном scope](public018-fresh-environment-and-producer.md). TLAB018 partial,13 из19; отложенное качество015 и отчёт неизменны. Следующий максимум18:00UTC от исходного17:15, цель активна. [Машиночитаемый статус](public018-independent-verifier-failure.json).
