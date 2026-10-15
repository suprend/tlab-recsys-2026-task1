# Round064 — приоритет memory-bounded proof и sparse replay без расширения backlog

**Critical disposition062–063, 15 октября2026.** Read-only сопоставление research с существующими018/015/016, [fresh-clone audit](../backlog-reviews/tlab-fresh-clone-reproducibility-audit.md), [workflow018](../experiments/verification-workflow.md), [replay050](round-050.md), [score sensitivity051](round-051.md) и [claims061](round-061.md). Actual outputs, WIP, real data/model jobs не читались и не запускались. Research recommendations не являются code acceptance, recovery authorization, budget grant или новым final policy.

## Что источники поддерживают

[DuckDB view semantics](https://duckdb.org/docs/current/sql/statements/create_view) и [blocking/spill guide](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads) объясняют техническую возможность уменьшить upfront materialization и работать с disk-backed intermediates. Они не доказывают, что current verifier превышает RAM, что конкретный replacement plan пройдёт gate или что runtime уменьшится. Ни один такой measurement здесь не выполнен.

[Microsoft Research tie paper](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ecir2008.pdf) обосновывает значимость tie treatment; наши fullY denominator/zero/censor rules следуют из принятого006 contract, а не из универсальной «стандартной NDCG». Поэтому future sparse replay обязан воспроизводить конкретный estimator, не выбирать удобную library implementation.

[Официальная SIGIR artifact policy](https://sigir.org/general-information/acm-sigir-artifact-badging/) различает работоспособный/доступный artifact и independently reproduced result; для timing replay просит machine context и не ожидает совпадения времени на другой машине. Это основание report distinctions, не обязательная процедура сдачи T-Academy. Прямой ACM URL вернул403, другой guessed SIGIR path был недоступен; содержимое этих ответов не использовалось, policy прочитана на приведённой официальной SIGIR странице.

## Disposition matrix

| Potential addition | Решение сейчас | Существующее место |
|---|---|---|
| «Разделить verifier на partitions» как новая research HYP | Не добавлять | Это execution strategy существующего source-proof gate, не feature-quality mechanism |
| Independent partition-domain/ownership/bag certificate062 | Уточнить existing review criteria |018 regeneration/exhaustive scopes и actual source verification; не новый framework |
| View вместо whole table ради memory | Future implementation option при доказанной необходимости | Только reviewed observer/verification path; не менять работающий016 по предположению |
| Sparse fullY metric replay063 | Refinement user-facing executable replay | Уже выявленный050 consumer seam; не дубликат source-bootstrap018 |
| Новый metric/approximate topK/score rounding | Отклонить | Меняет estimand/ties и current frozen numerical policy |
| Переписать все accepted observers на streaming | Deferred/no task | Нет доказанного текущего blocker, churn создаёт новый review/cost |
| Dense user×item matrix ради reference | Не требуется | Existing sparse C/fullY достаточно; матрица не прибавляет доказательности |
| Бесплатный rerun после OOM | Отклонить | Existing failure/recovery/claim/budget policy; research не даёт исключения |

**Итог — zero new HYP и zero new production task.** Сохранить две технические refinements: полнота partition proof и estimator-preserving transport. Номер очередной note не означает дополнительную measured гипотезу или выполненную backlog acceptance.

## Порядок необходимых действий остаётся прежним

Первым остаётся завершение **нынешней принятой execution/evidence chain**: exact source/AST/schema/key/value scope, independent expected formulas, physical rows, cumulative terminal resource receipts, затем matched learner comparison. Code-level acceptance не заменяет source acceptance; все просмотренные partitions не заменяют independently expected Q/C cover. В работающую цепочку не внедряется future plan только потому, что документация допускает spilling.

Если observer действительно не проходит memory/resource gate, сначала локализовать конкретный defect и следовать существующему scoped recovery contract. Исправление observer может сохранить producer/model/input/policy bytes, но не объявляется автоматически harmless: нужны proof equivalence, отдельный reviewed delta и оплаченные failed/replay costs. Незавершённая проверка остаётся incomplete; не превращается в отрицательный quality result. Новые fits, replacement arms либо увеличение allowance из062–063 не следуют.

Второй приоритет — user-facing reproduction: symbolic/tiny example без private state, понятные входы для Q/Y/C/F/control/016, различие historical replay и independent rerun новой identity, кто и по какому semantic scope создаёт fresh external source approval. Это existing018 phase2/README, а не новая cache/streaming platform. Если historical predictions reviewer недоступны, aggregate+hashes дают audit trail, но не numerical replay. Поставляемый literal fixture доказывает consumer mechanics, не historical quality.

Третий — читаемый report с evidence ladder. B preservation относительно старого F не означает exhaustive source proof B; full numeric selected12 не означает numeric proof всех24potential columns; four matched fits не доказывают universal strategy superiority. Закрытие этих claims важнее ещё одной оптимизации SQL. Negative либо W=B outcome допустим как результат bounded automation; resource/integrity failure не выдаётся за четыре проигравшие модели.

## Минимальный полезный остаток без jobs

Для existing review/README достаточно трёх точных additions. Во-первых, назвать global certificate: expected Q/C domain, exact physical file set, total/disjoint ownership, bag/key equality, unchanged context и terminal complete status. Во-вторых, описать replay inputs и outputs: exact S=C keys, scoreDESC/IDASC, fullY Nq, topK hit vectors, four estimands, empty/censored handling и численный reduction order. В-третьих, каждому claim сопоставить статус: implemented/reviewed/tiny-tested/actual-verified/proposed. Это document clarity, не ещё один run.

Если позднее выбран streaming backend, отдельно проверяются batch-boundary query carry, giant-query handling, disk/spill cleanup, exact BIGINT+NULL и conservation всех expected keys.≤32row literal fixture может покрыть эти defect classes без обучения, но здесь его исполнение и allowance не предоставлены. Нельзя принять sampled numeric verification как exhaustive лишь потому, что она читает все file headers или streaming rows.

Current016/019 settings, four-fit cap, selector, reserved-target access и final schedule неизменны. Собранные источники дают конкретные варианты future implementation, а не повод задерживать утверждённую инженерную работу. **Приоритет: accepted result → понятное воспроизведение → честный report; новая инфраструктура только при установленном blocker и отдельном решении.**
