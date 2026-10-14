# M08. Гибридные признаки и ограниченный выбор моделей

15 октября 2026. Независимое исследование; новые записки коллег не читались. Использован workflow research: первичные источники и отдельный Markdown. Ни обучения, ни установки, ни изменения репозитория/данных не выполнялось. Ниже — предложения, а не принятый эксперимент.

## Исходное состояние и рекомендация

Сильный ручной boosting обязателен для task1 по локальному `docs/experiment-plan.md`. Принятые 001–007 и dependency CatBoost 1.2.10 не означают готовность такого baseline: первоначальные два CPU-fit по 50 деревьев в 008 — SMOKE. У 017 идёт первый проход Q/C; actual collections ещё не приняты. Заявлять прирост сейчас невозможно.

P0: один сильный CatBoost, дешёвые контроли и один контролируемый гибрид. P1: максимум второй сильный ranker — LightGBM; максимум одна optional neural-ветвь. Восемь модельных семейств одновременно превращают ограниченный validation в поиск случайного победителя. Риск переобучения критерия выбора показан [Cawley & Talbot, JMLR 2010](https://www.jmlr.org/papers/v11/cawley10a.html); это обоснование ограничить попытки, а не доказательство превосходства CatBoost.

## Матрица, отделяющая представление от модели

Единица — `(query=(user,t), candidate i)`. Для каждой строки фиксируются ручные признаки X, бинарная purchase relevance согласованного полного target-set Y, candidate union C(t), known-catalog proxy и strict-past история. Ни будущие positives, ни будущие товары не вставляются в C. Все arms имеют одинаковые запросы, C, метрики, временные границы, доступные labels и вычислительный учёт.

| Arm | Score / вход | Проверяемый вопрос |
|---|---|---|
| Контроли | popularity, last-view/repeat, ItemKNN score | Есть ли выигрыш сверх простого поведения? |
| B | CatBoostRanker(X) | Сильная ручная база |
| H | Тот же CatBoost(X + S) | Добавляет ли frozen representation информацию? |
| N, optional | Компактный MLP(X + S), один scalar output | Меняется ли результат при замене downstream learner? |

Предлагаемый P0 objective B/H/N — pairwise logistic `log(1+exp(-(f(q,i+)-f(q,i-))))`, с одним manifest пар и одинаковой нормировкой веса query. CatBoost PairLogit поддерживает явные пары; пары внутри одного group обязательны, object weights не заменяют pair weights ([документация](https://catboost.ai/docs/en/concepts/loss-functions-ranking)). Группы без различающей relevance не дают pairwise signal, но остаются в evaluation. Автоматические скрыто разные samplers недопустимы. Если итоговый loss выбран другой, матрицу пересогласовать до fit. LightGBM LambdaRank — отдельное сравнение model×objective; одинаковое название «ranking» не делает loss эквивалентным.

S получается от одного компактного purchase-trained encoder: `e_i∈R^32`, `z_u(t)=mean(e_j: event_time<t)`, `s=dot(z_u,e_i)`. ID-embeddings учатся на W тем же purchase/pairwise протоколом; pretrained ARGUS, тексты и изображения не используются. W-fit завершается до первой downstream train query; затем vocabulary, веса, нормировки заморожены, история обновляется. Для B история и ручные признаки получают тот же доступный W. Encoder нельзя учить на B-labels и затем приписывать его scores ранним B-строкам. Важность глобальной временной оси подтверждает [Ji et al., TOIS](https://arxiv.org/abs/2010.11060).

Минимальный S: score, cosine, missing-history/OOV flags; matched cheap control добавляет ItemKNN/last-item similarity вместо learned score. Retrieval-source flags, source rank и исходный source score входят уже в X всех arms. Missing source имеет отдельный флаг; кандидаты дедуплицируются. H учится взаимодействию neural score с history length, repeat и source; отдельные ручные произведения сначала не нужны. N получает ровно X+S, поэтому сравнение H/N честно по входу. Ранжирование только frozen dot-score допустимо как бесплатная диагностика; оно использует иной downstream fit и не считается равным по обучающим данным конкурентом.

## Остановка должна использовать итоговую метрику

CatBoost выбирает best iteration по `eval_metric`, которая может отличаться от objective ([официальное описание](https://catboost.ai/docs/en/concepts/parameter-tuning)). Но встроенная метрика на C обычно не знает positives из Y вне C. Поэтому заранее реализовать фактическую full-Y primary metric: например, Recall@K с denominator `|Y|` и NDCG@K с ideal ranking полного Y. Непокрытые покупки остаются misses; query без покупок сохраняются в учёте с явно согласованной zero-policy. Нельзя сначала остановиться по native candidate-only NDCG, затем пересчитать full-Y и назвать это корректным selection.

Предложение: заранее заданная сетка checkpoints; общий evaluator full-Y определяет patience, минимальный прирост и сохранённый checkpoint. Native best-model truncation отключён, если не доказана эквивалентность evaluator. В LightGBM custom evaluation доступна, а `first_metric_only` нужен, чтобы дополнительные metrics не управляли остановкой ([API](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRanker.html), [early stopping](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.early_stopping.html)). Реальную передачу full-Y metadata требуется проверить, не считать поддержанной автоматически.

Selection 22–23 октября с labels available 24 октября 00:00 и confirmation с 24 октября 00:00 не оставляют времени на решение. До freeze надо перспективно выбрать положительный gap либо сократить selection; новые даты здесь не утверждаются. Требуется `max(model_available_at, decision_available_at) ≤ frozen_before ≤ first_confirmation`. Holdout остаётся закрыт.

## Бюджет, дрейф и критерии прекращения

Общий cap — 6 CPUh, включая подготовку, failures, scoring и evaluation; 016 вложен: ≤12 новых колонок, ≤4 fits, ≤2 CPUh. Encoder и MLP тоже считаются fits; H/N запускаются только при оставшемся бюджете. Strong-B tuning получает заранее ограниченные осмысленные конфигурации, а не произвольное одинаковое число деревьев. Если baseline ещё растёт на последнем checkpoint, зафиксировать underfit/budget limitation, не приписывать neural преимущество.

Инженерная оценка: item table `166794×32×4` ≈20.4 MiB; миллион строк четырёх float32 scores ≈15.3 MiB до joins/copies. Это не замеры RAM или времени. P0 хранит scalar S, не миллионы user vectors.

Смена forward-checkpoint меняет координаты; общий поворот сохраняет dot-product, но ломает отдельные координатные splits CatBoost. Даже scalar scores могут менять scale/rank. P0 поэтому использует один frozen checkpoint. P2 snapshots требуют отдельной past-only нормировки, OOV/version lineage и проверки score drift; scaler конца B создаёт утечку ранним строкам.

До запуска определить минимально полезную Δ и guardrails; продвигать H только при устойчивом парном выигрыше full-Y над B и matched cheap control, без неприемлемых провалов cold/short-history slices. Неопределённость считать по users, не независимым candidate rows. Нет выигрыша, исчерпан cap, нарушена доступность или память — остановка ветви с отрицательным/неопределённым результатом. Confirmation открывается один раз после lock; повторный поиск по нему запрещён. HYP-083/084 оставить зарезервированными: обычный frozen-score hybrid сам по себе нового механизма не формулирует.


## Coordinator grouped-review appendix — 15 октября 2026

[Review05–08](review-05-08.md) требует common history/window/bucket/cap/weighting для order/encoder claims; M05events/M06events/M07buckets не одинаковые inputs. B/H share downstreampairmanifest, warmupencoder имеет отдельный более раннийmanifest; standalonelearnerнаmaturetrain — допустимая другая chronology. «Бесплатный» dotdiagnostic означает0newfits, но scoring/sorting/evaluation/bootstrap оплачиваются. LightGBM externalstopping требует metric="None" строкой и solecustomcriterion, first_metric_only недостаточно. HYP083/084 reserved; strongB/oneoptionalhybrid не разрешение всехfamilies. Shared6CPUh/016nestedcap безadditivebudget.
