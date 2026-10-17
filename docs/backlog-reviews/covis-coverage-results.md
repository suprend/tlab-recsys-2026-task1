# HYP-061 coverage: критерий не выполнен, C0 сохраняется

Root принял конечный результат **17 октября 2026, 11:59 UTC**: **INCONCLUSIVE / KEEP_C0**, продолжение не допущено. [Безопасный агрегат Root](evidence/covis-coverage/tlab-root-hyp061-coverage-public-aggregate-v1.json), [primary](evidence/covis-coverage/primary/aggregate.json) и [независимый результат](evidence/covis-coverage/independent/result.json) сохранены точно. Исторический `UNVERIFIED` внутри оригиналов не переписывается.

Те же [6000 запросов и кандидаты](covis-q6000-results.md), 5988 пользователей; полный Y содержит 121 цель у 104 положительных запросов. New/repeat — 48/73 цели у 42/69 положительных запросов; семь запросов входят в оба среза. Пустые Y остаются в фиксированной когорте, условный Recall для них не определён.

| Вариант | Попадания full / new / repeat | Full query-macro Recall |
|---|---:|---:|
| C0 | 92 / 21 / 71 | 0.783654 |
| Cosine, primary | 95 / 24 / 71 | 0.807692 |
| Count, secondary | 96 / 24 / 72 | 0.817308 |
| Matched popular | 92 / 21 / 71 | 0.783654 |
| Matched cosine | 95 / 24 / 71 | 0.807692 |
| Matched count | 96 / 24 / 72 | 0.817308 |

Равенство агрегатов native/matched не доказывает равенства наборов. Каждый срез использует собственные положительный знаменатель и массу полного Y; off-C цели сохранены, k=0 не исключён.

Primary cosine−C0: **Δ=+0.02403846153846154**, 95% CI **[0;0.056035489848533675]**. Matched cosine−popular имеет ту же положительную точечную разницу. Условия point≥0.005 и matched>0 выполнены, но обязательное **lower95>0 не выполнено**: граница ровно0. Count96 не заменяет primary. Это покрытие полного C, не достигнутые Recall@20 или ranked NDCG; oracle NDCG — только потолок доступности.

[Независимый oracle](evidence/covis-coverage/VerifierSourceV1/README.md) заново реализовал статистику и чтение исторических labels, сверил все6000 приватных строк и11 gained/lost записей. [ACTUAL semantic-review](evidence/covis-coverage/tlab-hyp061-coverage-independent-semantics-actual-v1.md) отдельно сравнил215 полей: максимальная ошибка0. Он не повторял чтение приватных строк. Bootstrap:2000 общих user-cluster draws, все5988 пользователей, multiplicity всех их дней, seed61061/type7;2000 определены. Сравнены endpoints/counts; **per-draw parity с primary не проверена**, individual primary draws не сохранялись.

| Ресурс | Primary | Verifier |
|---|---:|---:|
| Финальный CPU прямого child, с | 13.994364 | 12.601144 |
| Wrapper wall-prefix, с | 14.063938 | 13.052249 |
| Child RSS high-water, B | 422428672 | 461668352 |
| Финальный job, B | 2349821 | 961950 |

Оба original закрыты exit0/reaped без повторов; [resource-review primary](evidence/covis-coverage/tlab-hyp061-coverage-independent-resources-actual-v1.md) и [verifier](evidence/covis-coverage/tlab-hyp061-coverage-verifier-independent-resources-actual-v1.md) qualified. Полные parent CPU/wall и жёсткий aggregate RSS не установлены; final inventory не измеряет transient peak. Physical I/O UNKNOWN, старый32GiB screen не пройден.

Source-история сохранена: V1 дваP2 исправлены V2; V1 decimal-gold FAIL и V2 allowlist-order FAIL — fixture-ошибки. V3 production побайтно тот же V2,15 PASS; verifier5 literal PASS. Обе metadata-writer ошибки и P3 receipt-diagnostics сохранены; P3 в успешном actual не сработал. Code/tests — evidence прототипов, не production CLI; synthetics не доказывают все fault-сценарии.

Два patch сохранены в [V1→V2 JSON](evidence/covis-coverage/SourceV2/V1-to-V2.diff.json) и [V2→V3 JSON](evidence/covis-coverage/SourceV3/V2-to-V3.diff.json); исходные байты восстанавливаются UTF-8-кодированием поля `text`.

Граф, кандидаты и labels — те же исторические: нет fresh cohort, нового raw/formula-подтверждения, serving/general-leak proof или demonstrated normalization gain. Fits/new predictions0; frozen final/CI, negative2027 и обязательная очередь неизменны.
