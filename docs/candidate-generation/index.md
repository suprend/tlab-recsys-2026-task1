# Candidate generation — промежуточный исследовательский пакет

15 октября 2026. Готовы3 из12 независимых исследований; три cross-review и полный синтез ещё ожидаются. Source proposals не изменяют исполняемый baseline автоматически.

| Тема | Записка |
|---|---|
| Exhaustive reference / prior-observed catalog | [01 exact reference](01-exact-reference.md) |
| Popularity, trend, quotas | [02 popularity](02-popularity.md) |
| Direct recent/repeat interest | [03 recent/repeat](03-recent-repeat.md) |

Текущий P0 — versioned top200 purchase-distinct-users7d +recent20 distinct all-event items7d, union/dedup без refill; targets присоединяются после C. U(t) — observed proxy, не stock. Полный Y остаётся знаменателем metrics. Exact dot/ANN и full CatBoost audit — отдельные вопросы; missing search edge не превращается в measured zero. HYP023 exact audit и HYP031 trend требуют собственных budgets/configs/review. HYP032 normalization-only отклонена: при fixed quotas постоянный denominator не меняет порядок. HYP004 popularity220 пока blocked protocolv1≤200, validator не обходится.

Recent20 уже покрывает прямой повторный интерес; type/session/cooldown варианты должны показывать marginal coverage. Repeat clicks не являются доказательством repeat purchases. Fixed-clock query не знает текущую будущую сессию; bought items сохраняются.

[Backlog](../backlog.md) · [Target research](../target-research/index.md). Другие9 тем и3 cross-reviews остаются обязательной очередью.
