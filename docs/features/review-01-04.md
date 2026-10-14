# Независимое ревью тем 1–4: решения для общего appendix

Дата: 14 октября 2026. Прочитаны обе A/B-записки тем counts, windows, rates, categories и общий research-context. Исходники не изменены; другое ревью не читалось. Это проверка дизайна, без моделей, тестов, установки пакетов или новых запросов к данным. Ниже перечислены только существенные расхождения и необходимые уточнения. Отдельные P0 авторов не образуют общий P0 автоматически.

## 1. Необходимые коррекции и однозначные решения

**[1B](01-counts/research-b.md), «смешанные группы исключать и считать отдельно как ambiguous».** Формулировка допускает неверную реализацию: удалить смешанную группу, затем соединить ближайшие оставшиеся группы. Например, `view | {cart,purchase} | cart` не содержит надёжного соседнего `view→cart`. В appendix явно потребовать сначала построить исходную adjacency timestamp-групп внутри `(user_id,user_session)`, затем проверять обе вершины каждой исходной соседней пары. Если хотя бы одна mixed, переход не считать; через неё не мостить. Ambiguous-group count вести отдельно. Несколько однотипных строк дают один group transition; same-product переход — другая гипотеза. В общий MVP transitions не включать.

**[2B](02-windows/research-b.md), «При L=0 полоса ненаблюдаема: missing плюс coverage=0»** против **[1A](01-counts/research-a.md), «Для существующего ключа без прошлых событий counts равны 0»** и **[2A](02-windows/research-a.md), «Missing после LEFT JOIN для счётчика заменять нулём».** Это разные допустимые encoding, но объединять их без выбора нельзя. Решение appendix: count/unique по доступной части всегда численно 0 при пустом множестве, включая `L=0`; отдельно хранить coverage и `window_unobserved=(L=0)`. При недоступном ключе/metadata, например неизвестной сессии или категории кандидата, весь соответствующий conditional feature остаётся missing: это не пустая история известного ключа. `coverage` измеряет временную протяжённость предоставленного лога, не доказанную непрерывность сбора. Rates при нулевом знаменателе остаются missing; recency при отсутствии прошлого события тоже missing с flag.

**[3A](03-rates/research-a.md), P0 «u_events_per_observed_day_7d», знаменатель `max(t−7d,t0,first_observed_u)` и «Exposure как отдельный множитель».** Главная необходимая коррекция: первый зарегистрированный event не устанавливает начало наблюдения пользователя или exposure. Формула математически определена, но название/обоснование могут придать ей лишнюю измерительную достоверность. Перенести в P1 и назвать `events_per_day_since_first_observed`; сохранить общий first-past timestamp по всем типам, возраст, исходный count, длительность и заранее заданный minimum age, например сутки. Не интерпретировать как исправление left censoring или установленную Poisson exposure. Совпадает с оговоркой **2A**, «это не исправление left censoring». Отдельная величина `count/E_log`, где `E_log=min(W,t−S)`, нормирует покрытие источника, а не время после first-seen; не смешивать эти знаменатели. Оба rates отложить за MVP.

**3A, «Для всех шести отношений … произвольный hard cutoff … не нужен»** требует оговорки: выше в том же списке для since-first-observed уже установлен `E_u≥1`. Это явная engineering policy против секундного знаменателя, а не отсутствие порога. Для raw shares достаточно denominator/support; для time-rate отдельно действует minimum age. Исправление пояснительное, исходную формулу не удалять.

**[4A](04-categories/research-a.md), «uc_view_affinity_7d»** против **[4B](04-categories/research-b.md)**, «uc_view_share_7d = V_uc/V_u»: первая при нулевой истории пользователя и положительном global support возвращает prior, вторая missing. В MVP выбрать raw view-share 4B, denominator=0 → missing плюс no-view-history. Сглаживание 4A — P1. Его динамический `p_c(t)` по строго прошлому потоку сам по себе не утечка: это причинная агрегированная статистика; α — отдельно заданный/выбранный параметр. Месячный prior и fit конца train для ранних строк запрещены.

**3A «N_(u,c)/N_u» по всем eventtypes** против **[3B](03-rates/research-b.md)/4B view-share** — разные признаки. В общем MVP только view-share по точному category_id. Иначе одинаковое название «интерес» скрывает изменение состава действий; доля покупок/просмотров не вложенная вероятность.

**4A «ic_purchase_share_7d»** против **4B «item_view_share_in_category_7d»**: обе формулы корректны при одинаковой категории, окне и поддержке. Выбрать view-share первым из-за более плотного потока; purchase-share — отдельная P1-абляция, без обещания превосходства. При category denominator=0 missing; при положительном denominator и нулевом numerator — настоящий 0. Если category mapping неизвестен на anchor, отношение не рассчитывается.

**4A «relative_price»** и **4B «relative_price_category»** различаются временем и support: точное rolling на t, ≥20 товаров, против закрытого дневного snapshot на d, ≥5. Это не взаимозаменяемые реализации. В общем MVP цену не материализовать; P1 выбрать дневной `[d−7d,d)` snapshot с одной последней положительной наблюдавшейся ценой на product_id, metadata as-of d, support≥20 как предварительный порог. Кандидатная цена — допустимая as-of t. Snapshot/порог явно versioned; support 5 против 20 можно проверить позже. Это ассортимент наблюдений, не доступный каталог; нулевая цена остаётся в raw, нормировка missing плюс zero-price flag.

## 2. Общий небольшой MVP

Зафиксировать rolling 24h и 7d; `obs` использовать только для last timestamps/возраста. Не соединять все окна, types и grains.

* User: view/cart/purchase counts 7d; distinct viewed items 7d.
* User–item: view/cart/purchase counts 7d; recency последнего view и purchase по доступной истории `[S,t)`.
* Item: view/purchase counts 24h; distinct viewers 7d.
* User–category_ID: view count 7d, raw view-share 7d, view-recency `[S,t)`.
* Item внутри category_ID: view-share 7d вместе с числителем item-view7d и знаменателем category-view7d.

Получается 18 числовых колонок, включая два дополнительных support-counts для последнего отношения; повторно уже имеющиеся counts не копировать. Дополнительно общий E1/E7, возраст наблюдения user/item и явные availability/missing flags. Recency без прошлого missing; zero age при секундном strict-past невозможен. Все 372 безымянных ID сохраняют условную историю; `code_missing` не означает `category_id_missing`. Session-блок оставлен P1 и требует доступной текущей сессии anchor. Ratio `N_i/U_i` по всем типам нельзя реализовать через distinct-viewer denominator: это другой grain.

## 3. Время, стоимость и оценка

Согласованная сильная сторона записок: `[t−W,t)`, нижняя граница включена, верхняя исключена. В appendix подчеркнуть **глобальную** timestamp-группу: item/category state не обновляется даже событиями других пользователей этой секунды. Calendar и rolling — разные estimands. Разность cumulative counts корректна для полос; разность/сумма scalar distinct не корректна. Same-second metadata conflicts требуют явного ambiguity, без row-order tie-break.

Новые learned priors, clipping/encoders/словари должны существовать до первой downstream training-строки: warmup-freeze либо forward snapshots. Обновление счётчиков на val/test отделить от замороженных weights. Label-derived rates используют зрелые anchors с `a+H+δ<t`; прошлые purchase-event counts maturation не требуют. Полный30d и зрелый положительный horizon почти несовместимы в одном October — 30d не обязательное условие оценки.

Стоимость: sparse state и expiry очереди по выбранным ключам; exact distinct требует reference counts. 7d user–item state может доминировать в RAM; теоретический линейный проход после сортировки не означает доказанной скорости. Ни user×catalog, ни anchors×вся история, ни сумма daily-uniques не допустимы как экономная подмена. Измерить wall time, peak RSS, spill и размер результатов при реализации.

Абляции на неизменных anchors/candidates: counts → distinct/recency → category count/share → item-within-category share. Затем отдельные P1: action P/V с supports, smoothing, session, trend/decay, price. Raw P/V при V=0 missing, P>V допустимо; Beta–Binomial не применять. Срезы short-history, ранний October, zero denominator, unnamed ID обязательны. Дубли сохранять; sensitivity меняет только history при тех же anchors/labels. Проверка будущего suffix и перестановки same-second строк должна охватывать **все** shared states и snapshot metadata.
