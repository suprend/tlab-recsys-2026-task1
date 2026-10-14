# Граф аудитории и несколько интересов: ограниченный эксперимент

Дата: 15 октября 2026. Независимое исследование; модели не обучались. Факты данных взяты из общего brief, предыдущие `argus.md`, `sequential-embeddings.md`, `embedding-experiments.md` и canonical backlog использованы как контекст. Новые записки коллег не читались. Target, horizon и окончательный split остаются решениями проекта.

## Смысл и границы

В REES46 42,45 млн событий, 3,02 млн пользователей, 166,8 тыс. товаров; медианная история — четыре события. «Любит» означает наблюдаемую активность, не установленное предпочтение: без impressions просмотр без покупки не отрицательный feedback. Граф связывает seed-товары пользователя с пользователями из их аудитории, затем с другими товарами. Это персонализированная связь, но популярный товар получает много путей независимо от намерения.

[Cooper et al.](https://kclpure.kcl.ac.uk/portal/en/publications/random-walks-in-recommender-systems-exact-computation-and-simulat/) сравнивают короткие random walks и прямое вычисление на bipartite user–item graph. [Pixie](https://cs.stanford.edu/~jure/pubs/pixie-www18.pdf) использует несколько seed-pins и ограниченные walks; там вторые узлы — boards, а не наши users. Это основание метода, не перенос industrial latency. [MIND](https://arxiv.org/abs/1904.08030) и [ComiRec](https://arxiv.org/html/2005.09347) мотивируют несколько interest-векторов вместо одного среднего; их matching/retrieval результаты не доказывают пользу признаков CatBoost на нашем фиксированном C.

## P0: обязательные дешёвые контроли

Сначала хорошо настроенный ручной boosting: direct-history, recency, repeat, user/category/brand, item popularity, support. Его tuning проводится на selection в отдельном заранее ограниченном плане; два smoke-fit не означают tuned baseline. Добавить только отсутствующие контроли: `seen_ui=1[i∈H_u(t)]`, `new_category_ui=1[category(i)∉categories(H_u(t))]`, missing-category и размер distinct истории. Это бинарные user×item признаки; `−log popularity(i)` сам по себе item-only. Нулевая история означает неизвестную новизну относительно предпочтений, даже если `seen=0`. Новизну относительно короткого октября нельзя называть lifetime novelty.

## P1: sparse walk и условные интересы

Предлагаемый первый граф — отдельный view-граф; cart/purchase не складывать с view произвольными весами. Для snapshot s: `A_vi=1[существует view пары (v,i) в [s−7d,s))]`. Повторы и технические дубли не увеличивают ребро; event-count weighting — отдельная абляция. Пусть `d_i=Σ_v A_vi`, `d_v=Σ_i A_vi`, `P_iv=A_vi/d_i`, `P_vi=A_vi/d_v`. Из графа для запроса удалить пользователя u вместе с его рёбрами и пересчитать затронутые степени: собственная активность остаётся в direct-history baseline, но не имитирует внешнюю аудиторию.

`H_u(t)` — последние ≤20 distinct просмотренных товаров из `[t−7d,t)`, каждый выбран по последнему событию; `q_j=1/|H|`. На известных графу seeds перенормировать q, отдельно сохранить долю потерянной массы. Предлагаемые признаки: `walk2_ui=(qP²)_i` и `walk4_ui=(qP⁴)_i`, безразмерные вероятности достижения товара. Первый — нормированный ItemCF через аудиторию, второй проверяет дополнительный перенос. Разность `walk4−walk2` не имеет преимущества заранее. История ограничена distinct товарами; отдельно фиксировать original-event count и retained distinct count, чтобы truncation не скрывался.

Дешёвый multi-interest вариант: разделить seeds на две наиболее представленные исторические `category_id` и «остальные», максимум три группы. Категорию закреплять за историческим событием; NULL не выдумывать. Для каждой непустой группы q_k нормируется отдельно; `interest_max_ui=max_k(q_kP²)_i`, `interest_gap_ui=max_k score_k−Σ_k π_k score_k`, где `π_k=|H_k|/|H|`. Среднее равно обычному walk2 при том же seed-наборе: это полезный algebraic control. Максимум проверяет сохранение небольшого интереса; число групп и их support обязательны. Это гипотеза, а не доказанная семантика интересов.

## Время, нули и стоимость

Snapshot содержит только события `<s`; build завершён и `available_at≤t` до первого downstream anchor. Freeze графа/encoder не запрещает обновление текущей истории `<t`; rolling graph и frozen graph — разные эксперименты. Fitted clusters/IDF/learned item vectors тоже должны предшествовать соответствующему блоку. Все одинаковые секунды прогнозируются до обновления состояния.

Хранить две sparse adjacency, не `3m×166k` scores. При верхней оценке 42,45 млн рёбер два int32 массива соседей занимают около 340 MB, без offsets, mappings, dedup/build state; это арифметика, не benchmark RAM. Построение требует ограниченного по времени чтения/дедупликации исходных событий: cap queries не ограничивает scan. Для pilot: 100 запросов, ≤4096 walks длины ≤4 на запрос суммарно между группами, фиксированные seeds RNG; ≤30 минут/6 GiB, затем остановка с partial ledger при превышении. Это ≤1,64 млн переходов, но не оценка end-to-end времени.

Sampled visit count/N оценивает walk-score; ноль посещений не доказывает отсутствие пути. Хранить sample budget, `d_i` внешней distinct-аудитории, число различных промежуточных пользователей в samples, dangling/unknown seed mass и walk-availability. После self-exclusion seeds с нулевой степенью исключаются до нормировки q. Для cold item/empty history score missing, для известного, но не посещённого кандидата — sampled zero; утверждать достижимость нельзя. Exact score на tiny graph проверяет Monte Carlo bias/variance; повтор RNG проверяет устойчивость. Степенные hubs делают exact expansion дорогим; adjacency pruning меняет estimand и требует собственной coverage-абляции.

## P2 и проверяемые гипотезы

PPR задаётся `r=αq+(1−α)rP`; [Andersen–Chung–Lang](https://snap.stanford.edu/class/cs224w-readings/andersen06localgraph.pdf) обосновывают локальную аппроксимацию, но их lazy-walk convention нельзя смешивать с нашим P. PPR, PinSage и learned multi-interest оставить P2. [Авторский ComiRec](https://github.com/THUDM/ComiRec) требует старые TensorFlow-GPU/Faiss-GPU и сообщает исправление NDCG: готовый evaluation не переносить.

**HYP-067, needs-pilot:** walk4 добавляет сигнал сверх matched walk2/ItemCF; counter — только популярность/шум. Walk2 без добавки зарегистрировать refinement HYP-001, отдельную «новую» гипотезу отклонить как дубль. **HYP-068, needs-pilot:** условный maximum превосходит mean при одинаковой истории/support; category-profile или learned pooling без такого контраста отклонить как дубль прежних направлений.

Обе проверять на одинаковых anchors/C и полном Y, с неизменным evaluator: tuned baseline → +walk2 → единственная выбранная добавка; popularity, last-item и mean — дешёвые контроли. Срезы: пустая/одиночная история, новый товар, self-only аудитория, популярный hub, редкая третья категория. Co-purchase и следующий cart — ассоциации, не доказанные complements: нет orderID, shared session не basket. [McAuley et al.](https://ai.stanford.edu/~jure/pubs/prodgraph-kdd15.pdf) различают substitutes/complements через отдельную supervised задачу, недоступную здесь буквально. Рост novelty не равен росту покупки. Для линии автоматизации task1 нужен измеренный прирост над tuned ручным baseline; поиск групп/длины walk оплачивается общим ledger TLAB-016, отрицательные результаты сохраняются. Retrieval с новым C требует отдельного протокола и full-Y coverage.


## Coordinator review appendix — 15 октября 2026

[Review 05–08](review-05-08.md) требует пересчитать mixture weights π_k после одинакового OOV/self-only seed filtering: retained weight группы / total retained weight. Иначе weighted group mean не равен global walk2. Lost mass и empty groups показываются отдельно. qP²/qP⁴ — endpoint probabilities ровно на соответствующем шаге; накопленные visit counts — иной score, который может превышать1. Проверить обе identities tiny oracle до Monte Carlo; sampled zero не означает отсутствующий путь. Walk2 — refinement001, HYP067/068 требуют отдельного ограниченного выбора, не новый общий budget.
