# M04. Дешёвые поведенческие модели: контроль и перенос

15 октября 2026. Независимое исследование; обучение и новые измерения не выполнялись. Рекомендация: сохранить popularity/recent/last-view как P0, проверить ItemKNN на фиксированном C как P1, затем один компактный ALS. BPR — P2: его реализация добавляет ограничения, особенно для новых пользователей. Эти модели не заменяют сильный настроенный ручной boosting и отдельное доказательство автоматизации task1.

## Измеренный контекст и единица сравнения

Существующий [heuristic smoke](../experiments/heuristic-baselines.md), а не эта записка, сообщает: на provisional B48h, 6000 зрелых queries, 104 positive queries, conditional NDCG20 popularity=0.073133, recent/last-view=0.489135. Из 121 full-Y targets C покрывает 92; recent попадает в 70/73 repeat pairs, но лишь 6/48 new pairs. Равные метрики recent/last-view не означают равных rankings. Это аргумент проверять перенос на новые пары, а не объявлять решённой рекомендацию.

Query=(u,t), время UTC. Для ranking все методы возвращают прежний C(u,t), без вставки positives, удаления прошлых покупок и незаметного refill. Оцениваются полное Y и зрелые пустые queries; conditional и all-query estimands публикуются раздельно. Для retrieval нужен другой опыт: одинаковый лимит, явно заданные dedup/refill, candidate Recall относительно full-Y, затем отдельное ранжирование. Улучшение shortlist не приписывается ranker.

## P0: точные простые scorer

Предложенные формулы, не литературные оптимумы:

- **Popularity:** P(i,t)=число distinct пользователей с purchase товара в [t−7d,t). Сортировка P↓, ID↑; ранее наблюдавшийся товар без покупок имеет P=0. Это частота органического поведения, не вероятность конверсии.
- **Last-view:** L(u,i,t)=max timestamp view пары в [t−7d,t). Известный L выше missing, затем L↓, P↓, ID↑. Recent-source-first остаётся отдельным контролем, поскольку recent20 построен по всем типам событий.
- **Direct-pair recency:** D=Σe w_type(e)·2^{−(t−time(e))/1d} для событий пары в [t−7d,t); предлагаемые фиксированные веса view/cart/purchase=1/3/5. Это дополнительный screening scorer, не обязательный новый fit. Exact duplicates обрабатываются общей versioned policy; настоящие повторы сохраняются. Пустая пара даёт D=0; отдельно хранится history availability. Далее P↓, ID↑.

Pair counts по типам, last-view/purchase age, item popularity и support переиспользуются из manual materializer. Не создавать дубликаты колонок ради другого названия scorer. Ресурс преимущественно rolling state и joins по C; опубликованные 29.551s/878.7MiB относятся к прежнему smoke целиком, не прогнозируют стоимость ALS.

## P1: ItemKNN и ALS

**ItemKNN:** при snapshot b≤t построить A_vi=1, если пользователь v смотрел i в [b−7d,b). Для проверяемого u использовать A без его строки: n_i=Σv≠u A_vi, n_ij=Σv≠u A_vi A_vj, sim(i,j)=n_ij/√(n_i n_j). Предложение: sim=0 при n_ij<3; нулевой denominator — unavailable. Score — среднее sim(i,j) по последним ≤20 distinct просмотренным товарам пользователя до t, исключая j=i; отдельно max и support. Пустой профиль — missing, затем popularity fallback. Порог 3 — инженерная гипотеза. Cosine item-neighbor models поддерживает [implicit](https://github.com/benfred/implicit/blob/v0.7.2/README.md). Не строить dense I²; отсутствие top-K ребра — truncated/unknown, не доказанный ноль. Нынешний TLAB-012 уже задаёт соответствующий compatibility pilot.

**Implicit ALS:** обучающая единица — агрегированная user×item пара до cutoff b. Предложить r_ui=log(1+count_view_ui), p_ui=1[r_ui>0], c_ui=1+αr_ui, c=1 для отсутствующих пар. Минимизировать Σui c_ui(p_ui−x_uᵀy_i)²+λ(Σu||x_u||²+Σi||y_i||²); score=x_uᵀy_i. Это confidence-weighted reconstruction, не purchase probability и не прямой NDCG objective. Формула и fold-in x_u=(YᵀC_uY+λI)⁻¹YᵀC_up_u следуют [Hu–Koren–Volinsky](https://yifanhu.net/PUB/cf.pdf). α,λ выбирать только на selection; никаких заявлений об оптимальных defaults. Для implicit передавать observed c_ui в CSR при library alpha=1: не применять α повторно.

Freeze Y до первого downstream training anchor, обновлять только strict-past user history. Для новых пользователей с известными товарами ALS позволяет [recalculate_user](https://benfred.github.io/implicit/api/models/cpu/als.html); пустой профиль — fallback. Товар, появившийся после fit, может входить в U(t), но не иметь фактор: отдельный model-OOV, не catalog-cold. Targets вне U(t) остаются misses. Snapshot доступен лишь после фактического available_at; одного history<t недостаточно.

## P2: BPR и поддержка

BPR: s_ui=x_uᵀy_i+b_i; loss=−Σ(u,i,j) log σ(s_ui−s_uj)+λ||θ||², i наблюдался до b, j отсутствует в past-positive set. Unobserved не означает dislike. [Оригинальная работа](https://proceedings.mlr.press/r7/rendle09a.html) обосновывает pairwise criterion. В [implicit CPU v0.7.2](https://github.com/benfred/implicit/blob/v0.7.2/implicit/cpu/bpr.pyx) веса CSR игнорируются, negatives выбираются через случайную запись взаимодействий, следовательно распределение зависит от популярности; verify_negative_samples проверяет принадлежность positive set. [Базовый класс](https://github.com/benfred/implicit/blob/v0.7.2/implicit/cpu/matrix_factorization_base.py) не реализует BPR fold-in. Самодельную оптимизацию нового x считать отдельной моделью. recommend требует filter_already_liked_items=False для наших повторов.

MIT implicit имеет CPU/OpenMP и CUDA ALS/BPR; README v0.7.2 обещает wheels x86_64, GPU wheels Linux. Windows CUDA и Apple ARM/MPS не считать подтверждёнными: сначала отдельная проверка совместимости выбранной версии, CPU путь предпочтителен. Оценка, не benchmark: float32 factors при 3.02m users, 166794 items и d=32 занимают ≈408MB; CSR, transpose, solver buffers добавляются. Dense item² — ≈111GB; scoring fixed-C стоит O(|C|d), full catalog существенно дороже.

## Абляция и stop gate

HYP-055: новая ItemKNN гипотеза rejected-as-duplicate HYP-001/TLAB-012; сохранить уточнения формул. HYP-056: needs-pilot — frozen ALS scalar score/support улучшает tuned B сверх direct-history/popularity на том же C; counter: переупаковка этих сигналов. Максимум два encoder fits d=32/64 и один downstream B+ALS fit, одинаковый seed B; все оплачиваются отдельным заранее согласованным ledger, не бюджетом автоматизации.

Сначала 100-query gate: ≤30min/6GB RSS; превышение останавливает ветвь. На selection сравнить B, ALS standalone, B+ALS; диагностировать repeat/new, short-history, model-OOV. Promotion только после заранее замороженного claim на untouched confirmation: paired user-bootstrap ΔNDCG20 CI выше нуля, Recall20 не хуже, стоимость допустима. Малый support — inconclusive. Same-second события прогнозируются до обновления; пустые/нулевые профили, top-K truncation, OOV и точные дубли проверяются явно. Без incremental эффекта оставить дешёвые sanity scorer и остановить MF, сохранив отрицательный результат.


## Coordinator review appendix — 15 октября 2026

[Review 01–04](review-01-04.md) объединяет HYP056 с HYP051 в одну frozen-ALS family. Fold-in и pooling сравниваются на тех же V; library alpha=1 для уже подготовленных confidence. HYP055 rejected-as-duplicate001. Proposed encoder fits/downstream fit не добавляются автоматически к budget. Исходная note описывает environment на момент исследования; теперь [CPU CatBoost dependency принята отдельно](../experiments/cpu-environment.md), без real model fits.
