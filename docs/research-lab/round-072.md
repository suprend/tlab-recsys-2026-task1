# Round072 — query-balanced Logloss и пользовательский выигрыш: разные величины

15 октября 2026. Source-only уточнение для итогового отчёта: прочитаны опубликованные [loss review](../loss-selection/review-01-03.md), [training contract008](../experiments/boosting-baselines.md), [model-data](../experiments/model-data.md), [target evaluation](../target-research/05-evaluation.md), rounds [019](round-019.md)/[069](round-069.md) и accepted [evaluator006](../../scripts/ranking_metrics.py). Ни data, ни models/private Y, ни текущие016 outputs не открывались; вычислительные задания, fits, resampling и новые looks не выполнялись. Ниже буквальная аналитическая конструкция, не результат эксперимента. Текущие016 weights, selector, population и candidates остаются закреплёнными.

## Что уравнивают веса

В [accepted008](../../scripts/train_baselines.py) `group_accounting` задаёт строке `w_qi=1/|C_q|`; Logloss Pool получает эти object weights. Для множества зрелых training queries с непустым C соответствующий эмпирический риск:

`R = (1/|Q_train|) Σ_q [(1/|C_q|) Σ_(i∈C_q) BCE(y_qi,p_qi)]`.

Это наш вывод подстановкой в weighted Logloss, опубликованный в [официальных docs CatBoost v1.2.10](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/docs/en/concepts/loss-functions-classification.md). Каждая группа имеет массу1 независимо от числа кандидатов; пользователь с m training query-days имеет массу m. Здесь нет автоматического уравнивания пользователей, положительных строк, дней или purchase events. Например, единственный positive в C размера2 получает вес1/2, а в C размера4 —1/4. Равная масса групп не означает равного положительного градиентного сигнала.

Риск включает all-zero C: как Y=∅, так и непустой full Y целиком вне retrieval. Поэтому query-balanced training не является непосредственной оптимизацией conditional NDCG только по положительным queries. Пустой C остаётся в evaluation Q, но не создаёт training rows; censored query не становится отрицательной группой. Полный Y нужен evaluator, тогда как BCE видит только `Y∩C`. Нормировка весов не восстанавливает missing retrieval targets и не превращает unobserved purchase в зарегистрированный отказ после показа.

## Буквальный контрпример: восемь candidate rows

Все три query зрелые, имеют один target p внутри C; нет ties. A имеет два разных daily anchors, B — один. Буквы p/n здесь лишь роли строк, не реальные IDs. B₀ — baseline, W — альтернативный scorer; scores и обученная модель не предполагаются.

| Query/user | C и full Y | Порядок B₀ | Порядок W | Сумма training weights |
|---|---|---|---|---|
| qA1/A | C={p,n}, Y={p} | n,p | p,n | 1 |
| qA2/A | C={p,n}, Y={p} | n,p | p,n | 1 |
| qB/B | C={p,n1,n2,n3}, Y={p} | p,n1,n2,n3 | n1,n2,n3,p | 1 |

Это ровно8 физических candidate rows. Для одного target NDCG20 при ранге r равен `1/log₂(r+1)`, что следует из [первичного определения discounted gain и query averaging](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html) и принятой binary full-Y нормировки006. Обозначим `a=1−1/log₂3`, `b=1/log₂5−1`.

Тогда `Δquery=(2a+b)/3≈+0.05627`, но `Δuser=(a+b)/2≈−0.10013`. У всех запросов Recall20=1 для обоих scorers, поэтому Recall guard не разрешает расхождение NDCG. Пользователь A имеет суммарную training массу2, B —1. Query-macro выигрыш корректен для объявленного estimand, однако фраза «улучшено качество для среднего пользователя» из него не следует. Это не доказательство реального такого расхождения в016: текущие outputs не читались.

## Разреженность и нулевые queries

В той же конструкции intercept-only BCE имеет аналитический optimum `p*=mean_q(|Y∩C|/|C|)=5/12`; без весов частота positive rows была бы3/8. Это свойство ограниченной constant-predictor задачи, не предсказание поведения конечного CatBoost с деревьями и регуляризацией.

Добавим четвёртый query пользователя Z с двумя кандидатами и пустым Y: всего10 строк, всё ещё меньше16. Он добавляет единичную negative training массу и меняет constant optimum на5/16, но conditional evaluation его не включает. Zero-query estimand его включает, zero-user estimand дополнительно уравнивает пользователей. Отсюда нельзя заключить, что all-zero training вреден: он оптимизирует другую, заранее принятую смесь и может влиять на взаимодействия признаков. Нельзя исправлять наблюдаемую sparsity отбором только будущих покупателей.

## Конкретное уточнение отчёта и будущая проверка

В [006](../../scripts/ranking_metrics.py) user-paired bootstrap переносит вместе повторные query-days пользователя, но query-macro draw пересчитывает `Σk_u s_u/Σk_u n_u`; кластеризация не заменяет это средним `s_u/n_u`. Уже rounds019/069 охватывают bootstrap uncertainty. Новое здесь — соединить training weight, conditional population и формулировку выигрыша в одном читаемом абзаце:

> «Logloss уравнивает суммарный вес непустых training query-days. Primary результат — conditional full-Y macro по queries, поэтому повторные положительные дни пользователя сохраняют отдельные голоса. User-macro — отдельный уже объявленный estimand; user-cluster interval учитывает совместное resampling дней, сохраняя выбранное усреднение. Выигрыш primary не доказывает выигрыш user-macro или вероятность покупки после воздействия».

При последующем отдельно утверждённом протоколе возможен контроль `w_qi=1/(m_u|C_q|)`, где m_u считается по тем же зрелым непустым training queries без label-conditioned фильтра. Он проверял бы изменение риска при user balancing, при фиксированных Q/C/features/learner/evaluation, а не «исправлял» текущие веса. Контргипотеза: изменение массы не улучшает заранее выбранный estimand либо лишь переносит выигрыш между усреднениями. Нужны отдельные оплаченные attempts и закрытая последующая оценка; нынешние heldout, fits и looks для этого не разрешены. Выбор удобного averaging после просмотра результатов тоже является selection: [Cawley–Talbot](https://jmlr.org/papers/v11/cawley10a.html) обосновывают риск переоптимизации конечного selection criterion. Существующих loss/evaluation/report задач достаточно; новой HYP или task не требуется.
