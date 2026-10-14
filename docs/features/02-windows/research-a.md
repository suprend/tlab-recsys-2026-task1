# Тема 2A. Окна 1/7/30 дней: точные границы и наблюдаемое время

Дата: 14 октября 2026. Независимый угол: измерительная семантика и точная инкрементальная материализация. Исследование B не использовалось; данные, окружение и репозиторий не изменялись. Предложения ниже — эксперименты, не выбор финального target/split.

## 1. Что означает окно

Факт из предоставленного контекста с уточнением: файл покрывает **1 октября 00:00:00 — 31 октября 23:59:59 UTC**, то есть 31 день. Обозначим начало покрытия S, исключённый конец F = 1 ноября 00:00:00. Для anchor t внутри файла:

- Rolling: `C[e,k,W](t) = Σ 1(entity=e, type=k, max(S,t−W) ≤ event_time < t)`, W ∈ {1,7,30} × 86 400 секунд.
- Закрытые календарные дни: `K[e,k,W](t) = Σ 1(max(S,D−W) ≤ event_time < D)`, D — UTC-полночь дня t.

Например, 10 октября в 15:00 rolling-1d начинается 9 октября в 15:00; calendar-1d — весь день 9 октября. Это разные признаки. Calendar + текущий неполный день также не равен rolling: нужно убрать раннюю часть левого дня. 30-дневное rolling-окно полно только с 31 октября 00:00. Раннее `C30` фактически содержит всю доступную историю, а не полный месяц.

Исходный `TIMESTAMP` интерпретировать как UTC по контракту датасета; при переходе на `TIMESTAMPTZ` явно задать UTC, поскольку DuckDB выполняет binning в настроенном часовом поясе. [DuckDB: Timestamp Types](https://duckdb.org/docs/current/sql/data_types/timestamp). Для дробных суток использовать разность секунд / 86 400, не `date_diff('day',...)`: последняя считает календарные границы. [Timestamp Functions](https://duckdb.org/docs/current/sql/functions/timestamp).

## 2. Минимум признаков и denominator policy

**P0 MVP**, сначала grain `user_id`, типы `view/cart/purchase` раздельно:

| Признак | Формула / политика |
|---|---|
| `u_{type}_count_1d/7d` | C выше; 6 точных целочисленных счётчиков |
| `coverage_days_W` | `E_W = max(0, t−max(S,t−W))/86400`; общая доступная длительность лога |
| `window_complete_W` | `E_W = W`; можно вывести из E, не обязательно отдельная колонка |
| `has_user_history`, `history_age_days` | Есть ли события `<t`; `h=min{event_time<t}`, возраст `(t−h)/86400`; без истории возраст NULL |
| `u_view_per_observed_log_day_7d` | `C_view,7/E7`, только при `E7≥1`; иначе NULL и сохранять C/E |

Ноль счётчика означает «нет событий в доступной части», а не доказанное отсутствие активности до S. При `E=0` rate NULL. При `E>0` и C=0 — rate 0. Missing после LEFT JOIN для счётчика заменять нулём, но не заменять нулём недоступную длительность/возраст. У DuckDB `sum` пустой группы возвращает NULL, `count` — 0. [Aggregate Functions](https://duckdb.org/docs/current/sql/functions/aggregates).

**Важное ограничение:** E — длительность покрытия файла, не известное пользовательское или товарное время «под риском». First-seen не регистрация, первое появление товара не дата начала продаж. Аналогия с person-time требует действительно установленного периода наблюдения; здесь такой roster отсутствует. [CDC: Incidence rate](https://archive.cdc.gov/www_cdc_gov/csels/dsepd/ss1978/lesson3/section2.html). Поэтому `C/min(W,t−h)` можно исследовать только как `events_per_day_since_first_observed`, с тем же h по всем eventtypes, порогом длительности и отдельным возрастом; это не исправление left censoring. Не делить на число активных дней вместо времени: это интенсивность активного дня с другим смыслом. Медиана 1 active day и 4 events делает такую подмену особенно рискованной.

**P1:** добавить `u_purchase_count_30d`, `u_view_count_30d` и E30; переносить 1/7d на product/category только при пользе для выбранного target. Не создавать полный Cartesian product entities × operations × windows. **P2:** сглаженные индивидуальные rates, выбор длительностей и decay — после P0; любые fitted priors только warmup/forward, не fit на всём train для ранних anchors.

## 3. Тренд без вложенных знаменателей

P1-кандидат для views: непересекающиеся `R=[t−1d,t)` и `B=[t−7d,t−1d)`, пересечённые с `[S,t)`:

`nR=C1; nB=C7−C1; eR=E1; eB=E7−E1`.

`trend_view_1v6 = log1p(nR/eR)−log1p(nB/eB)`, если обе длительности ≥1 день; иначе NULL, рядом n/e. Никакого epsilon, превращающего неизвестную baseline в ноль. Это описательное изменение частоты, не статистическая значимость. `C1/(C7/7)` смешивает recent с содержащей его baseline; оно допустимо как концентрация, но не независимое сравнение периодов. Для редких purchase сначала counts: rates/ratios часто нестабильны.

## 4. DuckDB: точное окно из buckets

Предлагаемая схема: sparse `(entity,type,day_start,n)`; закрывать bucket только после окончания UTC-дня. Поддерживать префикс `P(d)=Σ events_time<d`; `P(d+1)=P(d)+bucket(d)`. Не строить плотную сетку users × дни; для отсутствующих дат использовать последний доступный префикс или суммировать ≤30 sparse buckets.

Для `L=max(S,t−W)`, `A=UTC-ceil-to-midnight(L)`, `D=UTC-floor-to-midnight(t)`:

`C_W = count[L,A) + (P(D)−P(A)) + count[D,t)`.

W здесь целое число суток ≥1; при L на полуночи A=L. Два raw-остатка и полные внутренние дни не пересекаются. Для раннего окна L=S. Текущий остаток вести prefix-state по секундам; левый — range query или разность префиксов внутри закрытого дня. Это точная арифметика для additive counts/sums; не суммировать дневные unique-users/products, averages или medians. Среднюю цену собирать через sum/count на одинаковом наборе валидных цен.

Эталон проверки — явный SQL predicate `event_time >= L AND event_time < t`. Для событийных anchors альтернативный exact-count:

```sql
count(*) OVER (
  PARTITION BY user_id, event_type ORDER BY event_time
  RANGE BETWEEN INTERVAL '7 days' PRECEDING AND CURRENT ROW
  EXCLUDE GROUP
)
```

Это пример для anchor на событиях соответствующего type; для общих anchors нужны marker rows с нулевым вкладом либо отдельная таблица запросов. `EXCLUDE GROUP` убирает всю одинаковую секунду, `EXCLUDE CURRENT ROW` — только одну строку. Сначала прогнозировать группу t, затем обновлять state. Оконные операторы буферизуют вход и могут потреблять много памяти; выбирать план по измерению, не обещать скорость. [DuckDB: Window Functions](https://duckdb.org/docs/current/sql/functions/window_functions).

Calendar-only вариант дешевле и strict-past, но является иной семантикой/задержкой, а не точной реализацией rolling. Пропорциональное распределение bucket по доле суток предполагает равномерность событий и не имеет гарантии ошибки. Приближённые distinct — отдельный P2: DuckDB предоставляет HyperLogLog, но готовые дневные scalar estimates нельзя складывать или вычитать для rolling cardinality. [Approximate Aggregates](https://duckdb.org/docs/current/sql/functions/aggregates#approximate-aggregates).

## 5. Проверки и ablations

Пять обязательных fixtures: событие ровно t исключается, ровно t−W включается; несколько событий одной секунды получают одинаковую историю; anchor в полночь не удваивает bucket; 1 октября E=0 и 31 октября E30=30; новый user с одним прошлым событием не получает «30 дней user exposure» или огромный безусловный daily rate. Для каждого fixture сверить raw predicate и bucket reconstruction; монотонность `C1≤C7≤C30` полезна дополнительно.

На одинаковых anchors/candidates и временном split сравнить: P0 counts → +coverage/age → +rates → +disjoint trend → +30d; отдельно exact rolling vs закрытые дни, с разрезами early-month и short-history. Не ограничивать весь эксперимент «полными 30 днями»: это почти один день и другой состав anchors. Если label требует horizon H, нужен зрелый outcome `t+H≤F`; strict-past feature не исправляет правое цензурирование target. Target-dependent остаются grain anchors, horizon, delayed outcomes и допустимое обновление историй на validation/test.
