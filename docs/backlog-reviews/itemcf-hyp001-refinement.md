# HYP-001/TLAB-012: проверить именно compatibility сверх support

15 октября2026. Постоянная research линия, один refinement существующей [HYP-001](../backlog.md)/[ItemCF study](../features/09-user-item/02-item-neighbors.md). Никаких source data, models, SQL/tests/jobs, новых targets или fits не читалось/не выполнялось. Frozen016 и reporting-only heldout не меняются. Ниже будущая спецификация, не execution allowance; нового HYP/task нет.

**Гипотеза:** похожесть кандидата на просмотренные товары через аудитории *других* пользователей может дать перенос на пары, которых query-user раньше не просматривал, сверх direct history/popularity. **Более узкая контргипотеза:** весь возможный gain объясняется support/degree, а normalized compatibility не добавляет полезного сигнала. Это важнее очередной cosine/Jaccard/lift сетки и уже помещается в существующий012 scope.

## Что подтверждают источники и допускает REES46

[Sarwar et al.2001, cosine section](https://www.ra.ethz.ch/CDstore/www10/papers/519/node12.html) определяет item vectors в user-space и cosine между ними. Это основание механизма; original ratings setting не задаёт наш бинарный view-user grain,7d window, own exclusion или purchase-target evaluation. [Amazon2003](https://www.cs.umd.edu/~samir/498/Amazon-Recommendations.pdf), «How It Works», отделяет дорогую offline similar-items table от быстрого online aggregation. Его масштабируемость lookup нельзя перенести на ежедневную постройку/expiry REES46 без измерения. [Hu–Koren–Volinsky2008](https://yifanhu.net/PUB/cf.pdf) различает implicit preference/confidence: повторные действия могут менять confidence, но это не обоснование автоматически заменить distinct-user cooccurrence произведением raw event counts.

В [проверенной schema note](../data.md) есть event_time/action/user_id/product_id/user_session и event-embedded metadata, но нет ratings, order ID, impressions или отдельного stock catalog. Поэтому ItemCF здесь — affinity наблюдаемых view-аудиторий, не вероятность покупки/комплементарность/корзина. user_session не нужен MVP и не исправляет отсутствие order ID. Item/category/name backfill не нужен: core cosine работает по nominal product IDs. Изменение category metadata само по себе не должно менять этот scalar. Raw exact duplicates сохраняются в общем source; **бинаризация является локальным правилом данного оператора**, а не очисткой базового event bag.

Publisher Kaggle card при текущем чтении не вернула содержимое; field facts здесь приписываются опубликованному verified repo schema audit, а не повторной инспекции файла или карточки. Никаких dataset archives не запрашивалось.

## Exact минимальный механизм

Для daily snapshot b≤t определить `B_vi=1` при хотя бы одном view в `[b−7d,b)`. Это distinct `(user,item)` membership. Для query-user u/candidate i/history item j:

`c=C_ij−B_ui B_uj`, `a=d_i−B_ui`, `q=d_j−B_uj`;

`s=1[c≥3]·c/(c+10)·c/√(a q)` при `a q>0`, иначе undefined.

Порог3/shrinkage10 — унаследованное начальное предложение012, не optimum и не формула из Sarwar. Не подбирать их на текущем selection. History — последние≤20 distinct view items на `[t−7d,t)`, candidate diagonal исключён; равенства last_time разрешаются объявленным ID/hash tie, не rowid. Main scalar — mean по всей retained history с техническим0 у undefined pairs **только вместе** с defined_fraction/history_n. Знакомое непересечение/ниже support threshold и uncomputed/missing edge — разные состояния.

Own subtraction требуется в обеих степенях, даже когда u не смотрел candidate и `B_ui B_uj=0`. Если обещана внешняя аудитория, удаление u после top-K не восстанавливает shortlist; MVP должен вычислять exact requested pairs, без global top-K approximation. Self-included — иной допустимый контроль, не temporal leakage сам по себе. Для нынешних daily anchors b=t и snapshot lag=0: это audit field, а не новая постоянная model column.

## Один буквальный witness,16rows

Synthetic IDs: u=1,v1=2,v2=3,v3=4,v4=5; i=101,j=102,k=100. b=t, source покрывает полную неделю.

- u просматривает i в b−2h и j в b−1h:2events.
- Каждый v1/v2/v3 просматривает i,j,k в b−6h,b−5h,b−4h соответственно:9events.
- Ещё одна exact duplicate строки v1→k в b−4h:1event.
- v4→j и v4→k ровно в b:2events, глобально исключены.
- Один Q(u,t), один C-row candidate k:2rows.

Итого14raw events+Q+C=16. Retained H={i,j}. После удаления u: степени i=j=k=3; обе пары k/i,k/j имеют c=3, cosine1, s=3/13. Expected mean=max=3/13, supported_pairs=2, history_n=2, defined_fraction=1.

До удаления u связь j/i имеет s=2/7, а j/k — `3√3/26`; global top1 оставляет i. После удаления обе связи равны3/13 и lexical product100 выигрывает у101. Поэтому сохранённый top1 не может считать отсутствующий k нулём; exact requested pair nonzero. Если вычитать собственный вклад только при совместном просмотре candidate, ошибочная denominator оставит `3√3/26` вместо3/13.

Targeted mutations: удалить v3→k → external c=2 и thresholded score0; передвинуть этот view ровно в b−7d → включён, на1µs раньше → исключён; добавить past u→k → после полного own subtraction scores неизменны, а diagonal k всё равно удалён из H. Перестановка global peers не меняет значения; future suffix не меняет прошлый snapshot. Duplicate v1→k не меняет ItemCF membership, **но может менять базовые raw item-count features**: нельзя обещать инвариантность всего B или trained predictions.

## Самый маленький meaningful future test и отказ

Сначала prospective0fit gate на≤100 заранее hash-selected queries, до target access:≤220 C/query,≤20 history ⇒≤440000 requested pairs до cache. Это bound запросов, не bound source scan/postings memory. Source build, exact intersections, expiry, cache, oracle/readback, failed work измеряются вместе; existing012 proposal≤30min/6GB не выдаёт разрешения автоматически. При превышении gate — stop/defer; не спасать результат posthoc уменьшением пользователей, window, support или hidden top-K.

Механический reject: любое несовпадение literal expected values/keys/missing states, unknown cost или incomplete requested-pair coverage. Cost reject: превышение заранее принятого012 ceiling. При zero support/неизменном scalar нет оснований платить quality fits; это failure данного доступного signal scope, не доказательство бесполезности всех CF.

Только после current decision lock и **отдельного нового protocol/authority** допустимы existing012≤2 future fits: F0=B+history_n+supported_pairs+defined_fraction; F1=F0+itemcf_mean. Это isolates compatibility сверх одинакового support, без cosine/max/lift tuning grid. Одна fixed learning procedure/population/C/fullY/prefix/seed и заранее frozen selection rule; источник/построение графа для ранних train rows тоже строго прошлого дня, не full-train graph задним числом.

Будущий operational falsification criterion должен быть записан до доступа: если Δconditional-query NDCG20(F1−F0)≤0 либо Recall20 нарушает заранее согласованный guard, данная compatibility recipe не проходит pilot. Положительный point estimate без достаточной uncertainty — screening, не universal mechanism proof; undefined positive support/incomplete run — inconclusive, неzero/новый бесплатный seed. Точный guard/acceptance определяется будущим protocol, здесь не изменяется текущий.

Нельзя добавить эту ветвь в нынешние25/26–31 heldout или воспользоваться уже увиденными targets как независимым подтверждением. Если независимого нового evaluation block нет, поздний анализ честно называется retrospective exploratory. Практический приоритет остаётся завершение текущих016/reproduction/report gates; refinement012 сохраняется как одна проверяемая альтернатива, а не обязательная новая работа или расход нынешнего бюджета.
