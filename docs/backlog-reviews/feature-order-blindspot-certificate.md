# Certificate: одинаковые inputs при разном порядке событий

17 октября2026. **Root принял конечный synthetic informational certificate** HYP-142/FB-01 и HYP-002/TLAB-005/016. [Финальная acceptance](evidence/feature-order-certificate/tlab-root-wave099-certificate-final-actual-acceptance-v1.json) имеет SHA256 `4af508c7dd98dadad15705375b77e9ba01a584f118c259b6da67b5c573914a66`; [независимый ACTUAL review](evidence/feature-order-certificate/tlab-wave099-certificate-independent-actual-v1.md) — PASS. Это ограничение представления на заданных вымышленных примерах, без вывода о качестве рекомендателя.

Для одного invented user/item/category заданы события вT−6h,…,T−1h. H1=`V,C,V,C,V,C`, H2=`C,V,V,C,V,C`. В обоих мирах одинаковы view/cart counts3/3, purchase count0, distinct counts, последние view/cart и наблюдаемые ages. Все события внутри24h/168h окон. Отдельная area `Σ(t_s<t_r)(V_s C_r−C_s V_r)`, без деления на2, равна3 и1. Поэтому точное совпадение model inputs не позволяет deterministic scorer только этих inputs различить миры; это не утверждение о будущих покупках.

| Encoding case | Area H1 / H2 | Что проверено |
|---|---:|---|
| Original |3 /1| Literal равенство всех восьми44-input bundles между мирами. |
| Обратный физический порядок строк |3 /1| Timestamp-семантика, а не порядок хранения; invariance внутри мира. |
| Excluded peers ровноT и future purchaseT+1h |3 /1| Strict-past граница; эти invented события не меняют inputs. |
| Последний view перенесён за последний cart |1 /−1| Recency7200→1800s во всех16 world/bundle сочетаниях; supplied last_user_event_time тоже обновлён. Межмировое равенство сохранено. |

**Что фактически исполнялось.** Одна исходная попытка, exit0/reaped, retries0. Production `create_manual_features` материализовал2×8×4=64 registry cases. Raw closure содержит42 проверяемых numeric/flag поля,64×42=2688 literal cells. Две дополнительные label-free source projections доводят model input до B41+3=44;64×44=2816 final literal cells. Custom projection использует те же `CAST(... AS FLOAT)` expressions и NULL→NaN/float32 transport, с точным порядком44, shape1×44 и masks. Полные Y-aware prepare/loaders не вызывались; fixed Q/C supplied, retrieval не пересчитывался, Y-таблиц нет.

Cross-world comparisons:4×8×44=1408. Within-world original↔reverse/excluded:2×2×8×44=1408. Эти сравнения относятся к тем же конечным fixtures, а не к независимым статистическим репликациям. Есть16 sensitivity checks и8 area evaluations. Expected literals и row-list oracle запечатаны до producer imports/output; [seal](evidence/feature-order-certificate/expected-before-producer.json) и [complete result](evidence/feature-order-certificate/result.json) сохранены побайтно. Один explicit pool generation и одна allocation с внутренней regeneration validation дают2 generation calls, один pool/одну allocation, без redraw/search.

Независимый reviewer проверил source axis и готовые literal rows, заново пересчитал area и float32 literals стандартной библиотекой; suite/SQL повторно не запускался. Root прочитал весь certificate.py и independent MD, повторно хешировал32 typed references и пересчитал areas3/1→1/−1. Это32 ссылочных проверки, не утверждение о32 непересекающихся независимых исходниках.

**Lifecycle и errata.** [Receipt](evidence/feature-order-certificate/receipt.json) сохраняет исходный exit0/reaped и child CPU1.078544s, parent CPU prefix0.034366s, wrapper wall1.099072792s, child MAXRSS131039232bytes. Chosen envelope10CPU/20wall/512MiB/5MiB; engine1thread/128MiB/no spill. RSS/output наблюдались по stages, это не hard OS aggregate caps; prefix CPU и весь lifetime не смешиваются. [stdout](evidence/feature-order-certificate/stdout.txt) и [stderr](evidence/feature-order-certificate/stderr.txt) исходные.

Исходный [ACTUAL.md](evidence/feature-order-certificate/ACTUAL.md) сохранён с ошибочным prose256197bytes. [ERRATA.md](evidence/feature-order-certificate/ERRATA.md) исправляет сумму original pre-receipt map на **248197bytes**, не меняя receipt/result/lifecycle. Оба freezes сохранены. Эта сумма включает исходные launcher/prepared, которые намеренно не публикуются; она не является размером архивного subset. Исправление не было новым runtime attempt.

[certificate.py](evidence/feature-order-certificate/certificate.py) — **historical inspected source** с Mac/TMP путями, не portable public CLI. Его архивирование не разрешает запуск. [Publication map](evidence/feature-order-certificate/publication.json) содержит точные hashes15 safe originals и отмечает исключённые launch.py/prepared.json/private controllers; исторические pins/receipts сохраняют metadata references к ним. Основной воспроизводимый pipeline остаётся отдельным.

Prevalence blind spot, utility area для24h purchases, отсутствие всех возможных утечек, NDCG gain, arbitrary-schema automation и причина seed2027 failure остаются неизвестными. Real-data support/quality pilot не admitted; нового gate или задачи нет. Все IDs и строки fixture вымышлены; реальные data/model/score payloads в архив не включены. При подготовке этого архива не было imports, SQL, suite reruns, fits, predictions или чтения реальных данных.
