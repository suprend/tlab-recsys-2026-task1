# Товар ↔ профиль интересов пользователя

Дата: 2026-10-15. Независимое исследование; обучение и измерение прироста не выполнялись. Предпочтительная цель — purchase-ranking; горизонт, split и приведённые параметры provisional. Факты схемы — [данные](../../data.md): описаний, impressions и orderID нет; доступны category_code, category_id, brand, event-price. Поэтому «любит» означает наблюдаемое взаимодействие, не предпочтение среди показанных альтернатив.

## Контракт и единица наблюдения

Признак имеет grain `(u,i,t)`, история UTC `Hᵏ=[t−7d,t)` отдельно для `k=view,purchase`; cart — последующая абляция. Начало файла ограничивает полноту окна: сохранить observed_window_seconds и first_past_age. В P0 один distinct product даёт один голос в канале: выбрать его последнее событие данного типа строго до t; конфликт атрибутов при одинаковом последнем timestamp делает соответствующее поле ambiguous/missing. Метаданные истории принадлежат этому событию, кандидата — последнему доступному состоянию `<t`; цена текущего anchor допустима только при явно наблюдаемой карточке. Все peers секунды прогнозируются до обновления state. Полные дубли не добавляют голос; повторные покупки остаются видимыми в отдельном event-count baseline.

Для каждого канала хранить `n_items`, `n_events`, `n_valid(field)` и coverage=`n_valid/n_items`; пустой знаменатель — missing. Нулевое совпадение при ненулевой поддержке отличается от отсутствующей истории. Персональный профиль включает собственную историю намеренно; «аудитория других пользователей» здесь не оценивается.

## P0: категории и бренды

Пусть `a_d(c)` — полный префикс пути на глубине d; underscore сохраняется. Для известного кандидата:

`Aᵏ_d(u,i)= Σ[j∈Hᵏ]1[a_d(c_j)=a_d(c_i)] / nᵏ_d`,

где `nᵏ_d=Σ1[depth(c_j)≥d]`; если глубина кандидата меньше d, feature missing. Для ID `Aᵏ_id=Σ1[id_j=id_i]/n_items`. Начать с первого и полного текстового узла: `Aᵏ_root`, `Aᵏ_leaf`; для leaf знаменатель — все известные category_code, совпадение полных строк. Брендовый профиль `Bᵏ=Σ1[b_j=b_i]/nᵏ_brand`. Это lookup массы распределения в узле кандидата, а не user-only энтропия. Нельзя складывать доли разных уровней как вероятности независимых исходов. Missing code не мешает exact category_id; одинаковый missing-brand не создаёт сходство. Непроверенные восстановленные имена исключены.

Контроль weighting заменяет каждый distinct-голос всеми событиями с их event-time атрибутами; менять только это, сохраняя окна и labels. Иначе refresh карточки незаметно становится «силой интереса».

## P1: цены и lexical similarity

Цены сравнивать внутри exact category_id кандидата. `Jᵏ={j∈Hᵏ:category_id_j=category_id_i,p_j>0}`; `nᵏ=|Jᵏ|`. При `nᵏ≥3` определить `mᵏ=Q_.5({ln p_j})`, где Q — нижний эмпирический квантиль `x_(ceil(qn))`. Выдать signed gap `Dᵏ=ln p_i−mᵏ` и midrank `Fᵏ(p_i)=(Σ1[p_j<p_i]+0.5Σ1[p_j=p_i])/nᵏ`. Gap безразмерен; `exp(D)` — отношение к медиане. При `p_i≤0` или неизвестной цене оба score missing; невалидная историческая цена исключается с отдельным флагом и support; fallback на общую пользовательскую цену не выполнять скрытно. При двух поддержанных каналах `G=mᵛ−mᵖ` различает просмотренный и покупаемый диапазоны. Это не willingness-to-pay, elasticity или вероятность конверсии: покупки не вложены в просмотры, quantity неизвестно.

Lexical: атомарные path-prefix токены, без бренда, как в [исходной токенизации](../../nlp-tokenization.md). На уникальных известных category_code до первого downstream anchor: `idf(z)=ln((N+1)/(df_z+1))+1`; `x_c=normalize₂(1[z∈c]idf(z))`. Заморозить vocabulary/IDF либо forward snapshots. Профиль `vᵏ_u=Σx_c/n_valid`, score=`cos(x_i,vᵏ_u)`; дополнительно `max_j cos(x_i,x_j)` показывает узкий интерес, скрытый средним. Нулевой вектор/OOV — score 0 плюс missing/coverage. Косинус нормированных TF-IDF соответствует dot product ([официальная документация](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html)); это иерархическое сходство, не доказательство языкового понимания.

## P2: dense и направление отношений

Один frozen E5 checkpoint: category string, `query:` с обеих сторон, нормированные векторы `e_c`; заменить x на e в тех же mean/max формулах, бренд оставить одинаковым baseline. Правила префикса и размерность 768 даны [авторами E5](https://huggingface.co/intfloat/multilingual-e5-base). Category-conditioned pooling мотивирован [DIN](https://arxiv.org/html/1706.06978v4), но его CTR-результаты не доказывают purchase-ranking здесь.

Сходство симметрично, покупательский контекст направлен. Без объявленного графа отношений не называть соседнюю категорию complement. Минимальный проверяемый contextual cross: `R=Aᵛ_leaf×1[∃purchase той же leaf в [t−24h,t))`, рядом собственный индикатор и recency последней покупки. Знак эффекта обучается: насыщение потребности конкурирует с повторным спросом. Телефон→чехол и чехол→телефон различаются; даже substitutes могут быть направлены ценой. [Sceptre](https://ai.stanford.edu/~jure/pubs/prodgraph-kdd15.pdf) моделирует направление отдельно; его reviews/related-product labels здесь отсутствуют. R не восстанавливает такие labels.

## Стоимость, проверки, гипотеза

Sparse профили строить только для anchor-users; P0 lookup O(1), lexical/dense mean O(d) на кандидата, max O(20d) при отдельном cap20 последних distinct-items, с флагом truncation. Не создавать user×catalog. Pilot: 1000 queries, ≤220 кандидатов, ≤30 минут подготовки/6GB RSS; это ceilings, не benchmark. Два fit максимум, ≤60 минут каждый; scan42m оплачивается отдельно, timeout сохраняет partial report.

Проверки: первый event; известный ID без code; purchased-item без view; нулевая/сменившаяся цена; одинаковая секунда с конфликтом metadata. Абляции: strong direct/recency/category baseline → conditional price → lexical; distinct против event, mean против max, view против purchase при одинаковых candidates/anchors. Dense только после identity/prefix контроля, HYP-003 уже покрывает lexical-transfer.

**HYP-029, needs-pilot:** условные Dᵛ/Dᵖ/G улучшают ranking сверх item-price/category-price и supports; механизм — расхождение рассмотренного и оплаченного диапазона, counter — category mix/редкие покупки. Новизна к TLAB-013 — именно персональное двухканальное условное распределение. Inputs/as-of определены выше. Принять при paired user-bootstrap 95% CI ΔNDCG@20>0, ΔRecall@20≥−0.002 и ресурсных ceilings; неопределённость — needs-pilot, отрицательный эффект — rejected, превышение бюджета — deferred. Срезы history/support обязательны. HYP-030 не расходуется: dense-transfer дублирует HYP-003; отдельный новый механизм не обоснован.
