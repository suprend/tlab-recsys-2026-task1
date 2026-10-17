# Independent ACTUAL review — binary oracle ceiling

Срез **2026-10-17T09:29:41.584448+00:00**. Результат: **ACTUAL PASS для selection и всех четырёх category-карточек**. Реальных арифметических или cohort-mixing ошибок исходной карточки в проверенном объёме не найдено. Два ранних сбоя моего audit harness сохранены и закрыты отдельно; они не являются findings Root-карточки. Новых gates/fit/look требований не предлагаю.

Карточка `/tmp/tlab-oracle-ceiling-readout-actual-v1.json` exact SHA256 `f3d53e03037172cfdbbad57a43c440686611c7b44c83222ee3f73d80f1855b7d`, 6305 bytes. Все девять перечисленных входов проверены по bytes/SHA256 до пересчёта; e62 report имеет заявленный `e62b1f47…864a9b`, Root seed2027 acceptance — `048a6a07…86e54`. Я не автор исходного вычислителя.

## Проверенная формула и знаменатели

Для distinct binary full-Y у query положить m=|Y|, h=|Y∩C|. Максимальный DCG при данном C получается, когда его min(h,20) релевантных товаров стоят первыми; остальные позиции имеют gain0. Поэтому Oq=IDCG(min(h,20))/IDCG(min(m,20)), где IDCG(n)=sum(r=1..n)1/log2(r+1). Полный m не заменяется h или количеством positives, найденных в candidate sample.

При m=0 conditional oracle неопределён и query исключён из positive mean; all-query convention назначает ему0. Таким образом O_all=p(Q+)·O_positive. Это не all-user macro. В accepted seed2027 positive-query и positive-user значения совпали из-за73 positive users на73 positive queries; all-query и all-user значения различаются, и карточка использует правильный all-query показатель.

Проверены свидетели m100/h20→1; m2/h1→0.6131471927654584; m0 conditional undefined/all-query0. Первый свидетель показывает: oracle NDCG20 может равняться1, даже если большая часть full-Y targets не вошла в C за пределами первых20 ideal gains.

## Selection: независимое восстановление из точных Q/C/Y exports

Прочитаны только e62 selection22–23 октября Q/C/Y parquet. Query IDs уникальны; 817149 candidate `(query_id,product_id)` и96 full-Y пар уникальны, неизвестных query IDs в C/Y нет. SQL пересечение рассчитало h, независимый Python discount loop с math.fsum рассчитал oracle; project evaluator не импортировался. Итог:4000 Q,73 Q+,96 targets,65 hits,max m7. Oracle positive **0.6942312761177089**, all-query **0.012669720789148187**; positive macro Recall **0.684931506849315**, а pooled65/96 — иной estimand. Отклонение от карточки по всем этим полям —0.

M взят только из exact Root-accepted seed2027 JSON, не из старых seed2026 метрик e62 report. Accepted scope прямо указывает historical frozen exports/full selection rebuilt,4000 mature Q,73 Q+,k20,0 censored; Root в поручении подтвердил тот же cohort. Это проверка linkage к принятой Root-квитанции, без новой независимой загрузки score stream/model или проверки каждого Mq.

| Arm | M_positive | 1−O_positive | O_positive−M_positive | M_all | p−O_all | O_all−M_all |
|---|---:|---:|---:|---:|---:|---:|
| B | 0.45040127767495736 | 0.30576872388229115 | 0.2438299984427515 | 0.008219823317567971 | 0.005580279210851812 | 0.004449897471580215 |
| W | 0.43325580108319933 | 0.30576872388229115 | 0.2609754750345095 | 0.007906918369768388 | 0.005580279210851812 | 0.004762802419379798 |

Все значения совпали с карточкой, max error0. Проверены positive identity `(1−M)=(1−O)+(O−M)`, all-query identity `(p−M_all)=(p−O_all)+(O_all−M_all)`, а также M_all=p·M_positive, p=73/4000=.01825. Для all-query loss исходная идеальная величина —p, а не1.

Строковое поле `positive_ordering_loss=UNKNOWN_without_same_cohort_scorer` в selection-card остаётся общим и может выглядеть устаревшим рядом с заполненными per-arm `scorers_seed2027`. Числа per-arm верны; это необязательная правка ясности, не арифметический blocker.

## Category8–10: независимая проверка четырёх cohorts

Окончательный явно разрешённый category-only пересчёт V3 прочитал exact accepted coverage и сохранил4 группы `cohort+arm`: native/C0, native/C1, matched/C0, matched/C1. В каждой6000 строк и6000 unique query IDs,104 Q+,121 full-Y targets,max m4. Проверено, что query имеет одинаковые full-Y target count,user_id,anchor в четырёх группах; repeats+new_pairs=targets и repeat_hits+new_hits=hits в каждой строке. Это исключает смешение native/matched в принятом итоговом пересчёте.

| Cohort/arm | Hits | Positive oracle NDCG20 | All-query-zero oracle NDCG20 |
|---|---:|---:|---:|
| native/C0 |92|0.7893199154787948|0.013681545201632443|
| native/C1 |93|0.7989353000941795|0.01384821186829911|
| matched/C0 |90|0.7700891462480256|0.01334821186829911|
| matched/C1 |93|0.7989353000941795|0.01384821186829911|

В каждой группе все счётчики, positive macro Recall, positive fraction и оба oracle mean совпали с исходной карточкой: max absolute error0. Отдельно проверена identity O_all=(104/6000)·O_positive. У category нет same-cohort M; ordering residual остаётся UNKNOWN. Selection M к этим queries не применяется, final25–31 не читался. Переноса category oracle в selection/final нет.

В первом ошибочном счётчике category была сгруппирована только поarm:12000 строк/arm,208 Q+,242 targets, hits182/186. Эти pooled результаты сохранены как свидетельство причины ошибки audit harness. Его финальный assertion остановил приёмку; позднейший V3 не переписывает этот raw FAILED.

## Полная история трёх отдельно разрешённых finite episodes

1. Исходная одна попытка: первый monitor получил `PermissionError: Operation not permitted: /bin/ps` и завершился exit1 до wait. Child успел записать полный result: selection/loss checks PASS, затем собственный `AssertionError: category card missing matching source fields` из-за grouping толькоarm. First code/stdout/stderr/result сохранены без перезаписи. Child self prefix CPU0.146091s, wall0.146360500017s,maxRSS186580992 bytes,DuckDB1.5.6/256MiB/1thread/0spill; spill files0. External RSS/reap receipt не получен; child exit/reap UNKNOWN. Это не hard RSS enforcement.
2. Root явно разрешил ещё один targeted category-only episode, без повторного selection. Он завершился original direct tool completion **exit1**, chunk0634aa. До parquet query возникла моя `BinderException: Unexpected prepared parameter`: CREATE TEMP VIEW не принимает read_parquet(?) в prepared DDL. Source bytes/hash повторно проверены, parquet bodies во второй попытке не декодировались. Self prefix CPU0.205839s, wall0.165577832988s,maxRSS91684864 bytes; spill files0. Отдельный result/receipt сохранён. Этот эпизод остановлен без автоматического retry. Затем Root самостоятельно проверил причину и явно выдал отдельное окончательное разрешение, описанное ниже.


3. После фикса причины Root проверил Source V3 exact SHA256 `8d94f679a614b5fa94a418d6be4c9cbd262c2f81a03e12bd9bdba0177e0106e9`,4005 bytes. Изменились только создание view через `con.read_parquet(str(source)).create_view('coverage')` и новый output path; предыдущие harness/result/log файлы остались неизменными. После отдельного разрешения выполнен один окончательный category-only episode, **original tool exit0**, chunk00a2ee. Все четыре группы PASS, max error0, first_error=null. Self prefix CPU0.21953s, wall0.178898874990s,maxRSS111230976 bytes,spill files0. Selection и третьи данные не перечитывались. Новых метрик/условий не добавлено. Предыдущий честный PARTIAL report/pins сохранён отдельно, итоговый статус обновлён после actual результата.

Все три child имели CPU hard10s, wall alarm20s, DuckDB256MiB/1thread/0spill.512MiB описывает проверенный self-RSS prefix, не внешний hard bound; ps во второй/третьей попытках не применялся. Длительности — self-reported prefixes, не полная сумма всех launcher/import CPU; первая monitor accounting незавершена. Нельзя суммировать их как точный total lifetime cost. No process success/reap не выведен из наличия JSON.

## Граница вывода

Oracle — post-label математический потолок для данного fixed C/validation. Structural loss и ordering residual описывают эту фиксированную выборку; они не являются causal attribution, обещанием достижимого улучшения без знания будущего Y, оценкой отдачи от конкретного source/ranker, fresh-final claim или сменой основного критерия Task1. Их размеры сами по себе не выбирают следующий метод.

Только объявленные derived coverage и selection exports; raw/source DB/train/final/model bodies не открывались. e62/seed JSON прочитаны как metadata/accepted metrics; содержащиеся в них train/model references не разыменовывались. Project imports0, model loads0,predictions0,fits0,downloads0,canonical/Git writes0. После отдельного V3 category per-cohort actual PASS; ранние PARTIAL/FAILED артефакты сохранены без перезаписи.
