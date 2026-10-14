# 05. ItemCF как источник кандидатов

15 октября 2026. Независимое исследование; предложения без реализации, обучения и замеров. Финальные anchors, horizon и split не утверждены.

## Назначение и границы

ItemCF переносит интерес с прошлых товаров пользователя на товары с общей аудиторией. Классические работы отделяют построение similarity от агрегации рекомендаций: [Sarwar et al.](https://files.grouplens.org/papers/www10_sarwar.pdf), [Linden et al.](https://www.cs.umd.edu/~samir/498/Amazon-Recommendations.pdf). Здесь исследуется **retrieval**: изменение C(u,t). TLAB-012/HYP-001 уже исследуют cosine mean/max/support на фиксированном C; повторять их как новую гипотезу нельзя.

Факт проекта: [принятый candidate pilot](../experiments/candidate-pilot.md) использует popular200 по distinct purchase-users и recent20 по view/cart/purchase за семь дней, без добора после dedup. На 6000 development queries покрыты 92/121 targets, new-pair — 21/48. Это маленький диагностический sample, не прогноз прироста ItemCF. Действующий baseline остаётся неизменным; новый источник требует отдельного versioned протокола. U(t) — только товары, наблюдённые до t; итоговые 166794 товара октября не ранний каталог. C⊆U(t), наличие на складе неизвестно; отсутствие события не dislike.

## P0: конкретное правило

Для query (u,t) взять последний дневной snapshot b, **доступный** до t: fit-cutoff≤available-at≤t. Его окно — [b−7d,b), UTC; если расчёт после b ещё не закончился, использовать предыдущий доступный snapshot. История H — последние 20 distinct просмотренных товаров из [t−7d,t), ties по product_id. Same-second события t исключены; ранний октябрь имеет сокращённую наблюдаемую историю. Hyperparameters выбирать на прошлом development, затем freeze либо явно задать forward refit.

Grain графа — distinct view-user: B_vi=1 при хотя бы одном view. d_i=Σ_v B_vi, c_ij=Σ_v B_viB_vj, N — число view-users. Предлагается

`s(i,j)=1[i≠j]·1[c_ij≥3]·c_ij/(c_ij+10)·c_ij/√(d_i d_j)`.

Порог 3 и shrinkage 10 — стартовые предложения. При нулевой норме score undefined. Для каждого j сохранить K=100 положительных соседей по s, ties по ID. Получить `S(u,i)=Σ_{j∈H} s(j,i)` по сохранённым рёбрам; вернуть первые 50 distinct i из объединения соседей. Диагональ исключена, но товар из другой позиции истории и ранее купленный товар не исключаются: повторная покупка допустима. Пустая H или отсутствие поддержанных рёбер дают пустой источник. Сохранять source rank, score, поддержку и snapshot age.

P0 включает собственные **прошлые** взаимодействия u: это допустимый персональный сигнал, не future leakage, но не доказательство аудитории других людей. Для такой интерпретации нужны `c−B_uiB_uj`, `d_i−B_ui`, `d_j−B_uj` **до** нормировки и выбора соседей. Вычитание только после global top-K не восстанавливает исключённые соседства. P1: отдельный fold-excluded граф либо exact пересчёт shortlist с явной оставшейся truncation; сравнивать стоимость и семантику отдельно.

## Нормировки и альтернативные grains

P1 последовательно заменяет cosine на Jaccard `c/(d_i+d_j−c)` или lift `cN/(d_i d_j)`, сохраняя поддержку/shrinkage. Lift=1 соответствует независимости; редкие пары могут получить большой lift. Формулы и определения: [официальная документация mlxtend](https://rasbt.github.io/mlxtend/user_guide/frequent_patterns/association_rules/). Это ассоциации пользователей, не транзакций.

Cosine уже учитывает популярность через нормы. Дополнительный штраф `S/d_i^β` — отдельная абляция, способная вытеснять полезные head-items. Activity weighting: `w_v=1/max(1,m_v−1)`, m_v — число distinct товаров; заменить c,d на взвешенные суммы, проверяя minimum support по исходным пользователям. Это инженерное предложение, не BM25. Авторский [implicit](https://raw.githubusercontent.com/benfred/implicit/main/implicit/nearest_neighbours.py) задаёт собственные TF-IDF/BM25-преобразования и ориентацию матрицы; название нельзя переносить на произвольный штраф.

P1 purchase-user граф использует binary purchase-presence, отдельные нормы/coverage и сначала ту же view-историю для изоляции graph effect. P2 session-presence использует ключ (user_id,user_session), только уже наблюдённый prefix, без знания будущего завершения; missing session не объединять. Требовать поддержку нескольких distinct users, поскольку повторные сессии одного человека не независимы. Нет orderID: совместные покупки/просмотры не доказывают комплементарность, взаимозаменяемость или новизну. Content similarity и behavioural association различаются.

## Стоимость и семантика усечения

Полная pair-generation стоит `Σ_v m_v(m_v−1)/2`; медиана четыре события не ограничивает тяжёлый хвост. Activity weights не уменьшают число пар. Ограничение m_v или sampling меняют оценку, требуют отдельного имени/абляции. K ограничивает результат, а не стоимость построения. Запрошенные exact пары fixed-C требуют ≤20·220·100=440000 пересечений на 100 queries, но этот gate TLAB-012 **не доказывает** выполнимость поиска соседей во всём каталоге: merge postings стоит O(d_i+d_j), поиск требует гораздо большего пространства пар.

Инженерная оценка: 166794·100≈16,7 млн направленных рёбер; uint32 ID+float32 score≈133 MB без support, offsets, postings и рабочих буферов. Query обрабатывает ≤2000 рёбер, затем dedup/top50. Полной dense item² матрицы не строить. Отсутствующее top-K ребро означает «не сохранено», не c=0; граф после усечения направленный. Различать truncation, below-support, zero-overlap, snapshot-cold и unknown ID.

## Эксперимент и остановка

**HYP-061:** ItemCF увеличивает all-target retrieval Recall при том же бюджете сверх recent/popular. Новый протокол: control recent20+popular200; treatment recent20+popular150+до50 ItemCF вне исходного union. В обеих ветках одинаковый past-popular refill до220, если U позволяет; это новые конфигурации, включая расширение validator, а старый no-refill baseline показывается отдельно. Labels читать после C; oracle insertion запрещён. Сохранять полное Y, cold-outside-U misses, queries без покупок; дополнительно in-support Recall, new/repeat, head/tail, фактический размер C и downstream NDCG20.

**HYP-062:** activity weighting повышает marginal new-pair coverage при одинаковых K/квотах; counterhypothesis — лишь удаляет head-support. Не дублирует fixed-C feature task. Абляции выполнять по одной: graph grain, нормировка, weighting, K, self-policy. Feature ablations используют один frozen C.

P0 gate: один snapshot и 100 past-selected queries, ≤30 минут/6 GiB RSS, ledger scan/state/pairs/spill; частичный результат не объявлять полной метрикой. Проверить пять случаев: единственный общий пользователь — u; редкая lift-пара; timestamp boundary; cold item после snapshot; overlap всех источников/пустая история. Stop при нарушении past-availability/ресурсов; без устойчивого marginal Recall и downstream выигрыша на нескольких временных срезах при сопоставимой стоимости оставить recent+popular. Test не использовать для подбора вариантов.


## Coordinator grouped-review appendix — 15 октября 2026

[Review05–08](review-05-08.md) требует определить исключение из original200+20 union либо treatment150+20 union: это разные retrieval pools. Refill220 сравнивается с новым refill-control; старый no-refill004 показывается отдельно. TopK adjacency после truncation направленная, missing edge unknown. Other-user contribution вычитается до норм/topK; capped output не ограничивает Σm² graphbuild. Gained hits считаются относительно полного baseline, lost baseline hits после replacement/cap — отдельно.
