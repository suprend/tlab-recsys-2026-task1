# Popularity: устойчивый спрос, короткий тренд и квоты

15 октября 2026. Независимое исследование CANDIDATE02; предложения, без запусков и измеренного прироста. Итоговое место — `docs/candidate-generation/02-popularity.md`.

## Контракт и основание

Текущий pilot: purchase-distinct-users за 7d, top200 плюс recent20, union/dedup без refill; его не меняем. Новый источник означает отдельный protocol/manifest. В [backlog](../backlog.md) HYP-004 уже проверяет recent против popularity при одинаковом бюджете: здесь её не повторяем. Главная цель рассматривается как purchase ranking; окончательные anchors/H/split не утверждены.

Каталог `U(t)` — товары с любым событием строго до t, а не stock. Итоговые 166794 ID нельзя переносить назад. Нет impressions, orderID, release timestamps: popularity не CTR, purchase-строки не число заказов, first-observed не дата выпуска. Происхождение/схема: [данные проекта](../data.md), [авторская карточка REES46](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store).

Первичное исследование [PARE, §4.2–5.1](https://arxiv.org/html/2308.08799v1) сравнивает TopPop за разные прошлые периоды и мотивирует temporal popularity. Там месячные окна и другие домены; это основание проверить recency, не доказательство пользы 1h в REES46. Обучаемый PARE сейчас избыточен.

## Точное правило

Snapshot b≤t; для clock-pilot b=t. История — `[b−W,b)`, UTC, W∈{1h,1d,7d}; все peers секунды b исключены. Для произвольного t допустим последний закрытый час b, с записанным lag; baseline обязан использовать тот же b. Полные окна отдельно от left-censored; `observed_hours` хранится явно. Short-window источник выключается при неполном окне, существующий pilot сохраняет свою утверждённую политику.

Для товара i и event_type e:

- `E(i,e,W)` — число строк событий;
- `D(i,e,W)` — число различных user_id с этим событием и товаром;
- baseline-score `D(i,purchase,7d)`; положительные score сортируем убывающе, ties по product_id возрастающе.

Один покупатель даёт один голос внутри окна, даже при повторах; это не утверждение, что повторы ошибочны. `E` — отдельный count-control. Точные дубли увеличивают E, но не D; политика дублей фиксируется заранее. [DuckDB DISTINCT](https://duckdb.org/docs/current/sql/functions/aggregates#distinct-clause-in-aggregate-functions) удаляет дубли аргумента агрегата; `COUNT(DISTINCT user_id)` считается внутри item/window/type, не по всему магазину.

**Предлагаемый trend**, не результат статьи: короткое A=`[b−1d,b)`, фон B=`[b−7d,b−1d)`. Пусть n_iA/n_iB — distinct buyers товара, N_A/N_B — distinct buyers магазина. Задаём `p0_i=(n_iB+1)/(N_B+2)`, `p_i=(n_iA+50·p0_i)/(N_A+50)`, `T_i=log(p_i/p0_i)`. Допускаем только n_iA≥3, N_A≥50 и T_i>0; иначе нет trend-кандидата. Параметры — заранее выбранные инженерные константы. Для диагностического 1h заменяем A на последний час, B — предыдущую часть 7d; не вычитаем distinct-счётчики. Это доля покупателей, включая multi-item buyers; она не распределение вероятностей по товарам и не conversion.

## Нормировка, новое и fallback

Нормировка `D/N` на общую аудиторию не меняет глобальный порядок. В категории denominator тоже постоянен: пользу могут дать cross-category allocations/квоты, а не арифметика внутри списка. Для category/cohort g считаем `D(i,g,7d)/N(g,7d)`, где N — покупатели категории/когорты; сглаживаем к глобальной доле с фиксированной силой50. Категория — numeric category_id as-of; missing code не удаляет товар.

Когорты пока P2: допустимо past-only определение «имел purchase за предыдущие7d» на b и единое применение assignment ко всем событиям окна. Нет демографии или источника трафика. При N_g<50 возвращаем глобальный список. Не сравниваем несглаженный score когорты из двух человек с массовым спросом.

Recent-new — отдельный от recent-user источник: товары с `first_observed∈[b−1d,b)`, ранжированные по distinct view-users за1d, n≥3; optional cap10 вместо десяти глобальных слотов, protocol P2. Это новые для наблюдения товары, не новые поступления. View/cart/purchase держим раздельными источниками: их частоты и coverage различны; purchase/view не CTR.

Для новых протоколов квоты берутся до union; пересечения дедуплицируются, недобор остаётся недобором. Пустой trend просто теряет квоту; refill глобальными товарами — только отдельный заранее заявленный вариант. Не исключаем ранее купленное. Сохраняем provenance/rank/support и измеряем marginal target coverage каждого источника, overlap и фактический размер C.

## Две ограниченные проверки

**HYP-031, needs-pilot:** краткий сглаженный тренд добавляет будущие покупки сверх стабильного спроса. Counter: шум/меньший overlap. Compare frozen `200global+20recent` с `170global+30trend+20recent`; контроль `170global+30top1d+20recent` отделяет trend от простой recency. Одинаковые Q/U/Y и no-refill; дополнительно size-matched усечение кандидатов по заранее заданному порядку источников. Один retrieval-пилот, без fit; 1h остаётся диагностикой, не дополнительным поиском лучшего окна.

**HYP-032, rejected на уровне дизайна:** деление popularity на размер категории само улучшает retrieval. Counter решающий: при неизменных квотах denominator постоянен внутри категории, поэтому порядок и C совпадают; отдельный pilot этой арифметики не нужен. Содержательный P2-вариант — `160global+40category+20recent`: категории из последних20 distinct history-items, до четырёх, по частоте/tie-ID, round-robin по10. Но это новая квота/персонализация, а не эффект нормировки; её следует проверять в отдельном category-протоколе против global200, с теми же метриками и ресурсным потолком. Empty history оставляет недобор; smoothing исследуется отдельно.

Primary — all-target candidate Recall, cold targets остаются misses; дополнительно in-U Recall, macro по positive queries, дни/head-tail/repeat, zero-purchase доля отдельно. Accept для следующего этапа: ΔRecall≥1п.п., улучшение минимум в двух из трёх development дней, Δtail Recall≥−1п.п. при достаточном support; иначе reject/defer. Малый support [anchor pilot](../experiments/anchor-pilot.md) требует uncertainty, не заявления о победе; при широком user-clustered интервале — defer. Downstream NDCG20 проверяется позднее с одинаковым ranker/protocol; feature ablation сохраняет C.

## Стоимость и крайние случаи

Общий лимит HYP-031 на три варианта:30min, RSS6GB, ≤1.32m emitted rows на вариант, ≤3.96m суммарно; это stop-gates, не прогноз скорости. Материализуем top-lists один раз на b; distinct state может быть значительно больше output. Не суммируем дневные unique-users: один человек пересекает дни. Нужны точная дедупликация окна или user-item refcounts с expiry; сохраняем scan bounds, active keys, spill, elapsed/RSS. Ошибка/timeout даёт partial cost, не Recall.

Обязательные fixtures: события ровно b и b−W; истечение последнего/непоследнего повтора; пустой час и неполные7d; single-buyer burst нового товара; все источники совпадают. Suffix после b не меняет C, но может менять Y. Ни низкий support, ни missing metadata не оправдывают будущий каталог или вставку positives.
