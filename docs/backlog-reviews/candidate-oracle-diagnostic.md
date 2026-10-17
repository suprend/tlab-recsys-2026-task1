# Где теряется NDCG: диагностический потолок фиксированных кандидатов

Root принял карточку 17 октября 2026 в 09:30:38 UTC после независимого пересчёта selection и всех четырёх категорийных ячеек. Это математическая диагностика одного фиксированного списка кандидатов, **не обещание достижимого улучшения**, причинная оценка или новый критерий приёмки. Ноль fit и новых прогнозов. [Исходная карточка](evidence/candidate-oracle/tlab-oracle-ceiling-readout-actual-v1.json), [конечная приёмка Root](evidence/candidate-oracle/tlab-root-oracle-ceiling-final-actual-acceptance-v1.json), [независимая проверка](evidence/candidate-oracle/tlab-oracle-ceiling-independent-actual-v1.md).

Для binary fullY у каждого запроса m=|Y|, h=|Y∩C|. Oracle O — максимально возможный NDCG@20, если все min(h,20) релевантных кандидатов поставить первыми: IDCG(min(h,20))/IDCG(min(m,20)), где IDCG(n)=sum(r=1..n)1/log2(r+1). Полный m не заменяется числом найденных целей. Запрос с m=0 не входит в positive macro; в all-query-zero ему назначается 0. Даже m=100/h=20 даёт oracle=1: неполный Recall не всегда создаёт потерю NDCG@20.

Selection22–23 октября — **те же 4000 Q и 73 положительных запроса**, что у [принятого seed2027](seed-replication-results.md): 96 полных целей, 65 в C, max m=7. Независимый пересчёт Q/C/Y дал positive oracle **0.6942312761**, all-query-zero oracle 0.0126697208; максимальное расхождение с исходной карточкой — 0. Метрики M взяты из точной Root-приёмки seed2027 для этих же Q/C/Y, не из моделей другого seed или календаря. Нового чтения моделей/score streams для карточки не было.

| Seed2027, свой лучший префикс | M: NDCG@20 | Потеря из-за фиксированного C, 1−O | Остаток порядка внутри C, O−M |
|---|---:|---:|---:|
| B41, 98 деревьев | 0.450401 | 0.305769 | 0.243830 |
| W44, 134 дерева | 0.433256 | 0.305769 | 0.260975 |

Для positive-query macro тождество **1−M=(1−O)+(O−M)** разделяет недоступный этому C идеальный DCG и оставшийся разрыв внутри C. Эти слагаемые не измеряют, какую часть устранит конкретный retrieval или ranker: oracle знает будущие Y, а обычный алгоритм их не знает. Размеры слагаемых сами по себе не выбирают следующий метод. Поле selection `positive_ordering_loss=UNKNOWN_without_same_cohort_scorer` в исходном JSON — общий прежний placeholder; его уточняют заполненные per-arm `scorers_seed2027`. Карточка сохранена без исправления исторических байтов.

Для all-query-zero идеальная средняя величина — p=73/4000=0.01825, поэтому правильное тождество **p−M_all=(p−O_all)+(O_all−M_all)**. Здесь structural loss равна 0.0055802792, residual B — 0.0044498975, W — 0.0047628024. Подстановка 1 вместо p ошибочно добавила бы отсутствие положительного Y. All-user macro — другой estimand; совпадение positive user/query значений в этом selection связано с 73 пользователями на 73 положительных Q.

Категорийный пилот8–10 октября — **отдельная популяция**: 6000 Q, 104 положительных, 121 fullY, max m=4 в каждой ячейке. Все четыре ячейки пересчитаны раздельно с одинаковыми fullY/user/anchor для одного Q; точное расхождение — 0.

| Категорийные списки | Найдено / 121 | Positive oracle NDCG@20 | All-query-zero oracle | Остаток порядка |
|---|---:|---:|---:|---|
| Native C0 | 92 | 0.789320 | 0.0136815452 | UNKNOWN |
| Native C1 | 93 | 0.798935 | 0.0138482119 | UNKNOWN |
| Matched C0 | 90 | 0.770089 | 0.0133482119 | UNKNOWN |
| Matched C1 | 93 | 0.798935 | 0.0138482119 | UNKNOWN |

Scorer на этих категорийных Q/C/Y отсутствует, поэтому O−M здесь неизвестен. Selection M, fixed300 final26–31 и категорийные oracle не смешиваются. Более высокий oracle C1 не переопределяет исходный отрицательный результат критерия продвижения: [coverage inconclusive, новые пары20 против21, C0 сохраняется](category-candidate-pilot-results.md). Ни категории, ни selection-карточка не дают свежего final, CI, generalization или causal gain.

Независимый audit сначала допустил две собственные ошибки, обе сохранены. В первом category-счётчике группировка только по arm смешала native и matched; assertion остановил приёмку. Родитель первого reader получил PermissionError на /bin/ps до wait, поэтому его child terminal/reap остаётся UNKNOWN; наличие JSON не доказывает успешное завершение процесса. Второй отдельно разрешённый category-only пересчёт завершился exit1 на CREATE VIEW с prepared parameter ещё до декодирования Parquet. Root проверил узкое исправление создания view и новый output path; окончательный category-only V3 завершился tool exit0, все четыре группы PASS/max error0. Selection повторно не читался. Это ошибки audit harness, не findings исходной Root-карточки. Полные ранние истории сохранены в [отчёте и pins](evidence/candidate-oracle/tlab-oracle-ceiling-independent-actual-v1-pins.json); частные harness/source/raw outputs сюда не копируются.

Все три reader имели CPU hard10с, wall alarm20с, DuckDB256MiB/1thread/0spill. Ресурсные числа review — self-reported prefixes; первый внешний monitor не дал полной accounting/cleanup квитанции, точная сумма lifetime не заявлена. У исходной карточки записаны prefix CPU0.261364с/wall0.356058с/RSS107855872байт при выбранных15CPU/20wall/512MiB наблюдаемого RSS; это не универсальный жёсткий memory bound. Root полностью прочитал конечный отчёт, заново сверил25 типизированных ссылок и linkage к seed2027/loss arithmetic. Реальные raw DB, train/final, model bodies не открывались; fit/new predictions —0. Диагностическая приёмка не создаёт новых обязательных задач.
