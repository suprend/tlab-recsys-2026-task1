# Следующий backlog: три полезных проверки, а не ещё три обязательных эксперимента

15 октября 2026. Read-only consolidation существующих HYP, canonical backlog, шести indexes завершённого58-study portfolio и rounds068–074. Прочитаны также018 fresh-clone plan, candidate reviews, ItemCF refinement и accepted reserved-period design. Private inputs, actual models, текущие016 outcomes, hash streams и heldout не открывались; jobs/tests/SQL/fits/Git/code changes отсутствуют. Это предложения после завершения frozen016/heldout claim, без автоматического назначения владельцев, budgets или новых HYP IDs.

**Вывод:** сначала закончить текущие016 evidence,015 reporting-only evaluation и018/README reproduction boundary. Затем наиболее оправданы: (1) source-free adapter conformance; (2) zero-fit recent-retrieval fairness pilot; (3) support-controlled ItemCF. Это ранжированное меню, не последовательность трёх разрешённых запусков. Ни embeddings, ни смена learner weights, ни новый search сейчас не нужны.

## Что изменилось после последних исследований

[068](../research-lab/round-068.md)/[070](../research-lab/round-070.md) показывают, что одинаковые action labels не сохраняют category state или objective: Retailrocket property updates и MIND logged impressions требуют разных контрактов. [071](../research-lab/round-071.md) отделяет AST equivalence от observed equality; zero/NULL mask нельзя выкинуть как single-value nuisance. [072](../research-lab/round-072.md) запрещает подписывать query-balanced training как user-balanced gain. [073](../research-lab/round-073.md) требует оплачивать cache construction/validation, [074](../research-lab/round-074.md) — связать vocabulary с обеими башнями/cache/weights. Это refinements, не шесть новых quality mechanisms.

Важный общий gate: **zero fits не означает zero evaluation looks**. После текущего25/26–31 reporting открытые October targets нельзя объявить новым untouched confirmation следующей гипотезы. На том же REES46 October будущие comparisons возможны как явно retrospective exploratory; independent quality claim требует заранее действительно закрытого нового evaluation domain и отдельного решения о его получении. Новый source/data download здесь не предлагается и не разрешён. [Cawley–Talbot](https://jmlr.org/papers/v11/cawley10a.html) обосновывают selection bias конечного criterion; они не устанавливают специальный TLAB календарь.

| Порядок | Existing seam | Минимальный вопрос | Fits/target access до первых gates |
|---|---|---|---|
| 1 | HYP002,016/005/018 | Какие typed values переносит explicit adapter, а что обязан reject? | 0/нет |
| 2 | HYP004,004 | Даёт ли recent admission дополнительный full-Y retrieval coverage при сопоставимом actual C? | 0/только отдельный будущий look |
| 3 | HYP001,012 | Даёт ли external-audience compatibility что-либо сверх support? | 0 сначала; максимум2 отдельно разрешённых fit attempts позже |

## 1. Schema adapter conformance: самый дешёвый сильный отрицательный тест

**REES46 feasibility.** Existing raw bag/action/time/nominal-key semantics достаточны для эталонных literal events; реальные данные не нужны. Взять paired synthetic encodings REES-like EventFact и Retailrocket-like EventFact+PropertyState, без скачивания источников. Это уточнение уже предложенных043/052/068, не новый adapter framework. Current005/016 не объявляется drop-in generic backend: другое schema binding и capability rejection требуют будущей реализации/review.

**Контргипотеза:** перенос работает лишь потому, что unavailable channel заполнен0, property revisions посчитаны как business events либо current metadata backfilled в historical counters. Совпавший count после неправильного join не спасает неверный category grain. [Featuretools Handling Time](https://docs.featuretools.com/en/stable/getting_started/handling_time.html) различает cutoff/secondary availability; эти annotations должны задаваться явно, не угадываться из column names.

**Минимальный test перед любым fit:**≤32 literal input rows с independent list expected tables. Два одинаковых cart events дают rawcount2/distinct-users1; cart ровноT−24h входит, ровноT исключён глобально; cart8days назад даёт weekly0 и full-prefix recency691200s; metadata update не добавляет event. CategoryA→event→PropertyB между event/query требует historicalA/currentB. Known+NULL latest bucket остаётся unknown, позднее available_at не backfills прошлое; absent views отвергают view AST, declared observed-empty views дают0. Exact BIGINT и empty-C Q сохраняются.

**Accept/reject:** все объявленные category-free программы дают exact keyed/type/NULL expectations; category rules проверяются по отдельным gold, а не требуют ложного равенства двух sources. Любое false support, fanout, boundary или value mismatch опровергает этот conformance claim. Pass подтверждает только mechanics, не real-file completeness/quality и не весьB41. Source-free budget proposal:0fits/0Y,2threads,512MiB,≤5min total включая failure/evidence; отдельное approval необходимо. Любой real-source scan или внешний quality run — следующий самостоятельный gate, не продолжение smoke автоматически.

**Приоритет:** после минимального018 public reviewer prefix полезнее ещё одного encoder; может показать переносимость расчётной идеи без расхода labels. Не должен задерживать нынешний T-Academy report. Fresh-clone source bootstrap остаётся existing018 phase2: conformance не заменяет external decisions и не решает его циклический handoff автоматически. [Официальная SIGIR artifact policy](https://sigir.org/general-information/acm-sigir-artifact-badging/) отделяет исполнимость artifact от reproduced results; это ориентир отчётности, не дополнительное условие конкурса.

## 2. HYP004: recent source против «просто больше кандидатов»

**REES46 feasibility.** Есть past purchases для distinct-user popularity и past actions для recent items; titles/stock/order IDs не требуются. Accepted004 — P200+R20, no-refill, actual C≤220. Он не исполняет P220 comparator: protocol-v1 popular_limit≤200. Следовательно, future HYP004 сначала требует отдельный versioned config/validator review; нельзя тихо заменить comparator P200 и объявить equal-budget ответ.

**Контргипотеза:** gain вызван cardinality/underfill, а recent targets вытесняют не меньше полезных popular targets. Перед Y закрепить source ordering/ties, dedup/ownership/no-refill, P220 versus P200+R20 и actual-size control: `m_q=min(|C_pop|,|C_mix|)`, prefix каждого списка ровноm_q по заранее объявленному порядку. Native policies показываются отдельно. Если order/fill не определены или списки нельзя собрать в cap — pilot ещё не ready.

**Tiny test:** scaled2+1 literal lists. P3={a,b,c}, recent={a} дают mix={a,b}, поэтому equal max3 не означает equal actual size; matched P2 и mix совпадают. При recent={d} mix={a,b,d}: будущий target d даёт gained1, target c — lost1. Эти разные заранее заданные synthetic cases не отбираются по observed Y. Raw duplication не увеличивает popularity distinct-user degree, globalT peers не меняют C, purchased items не удаляются автоматически.

**Первый real-source gate, лишь будущий:**≤100 past-hash-selected Q, максимум двух заранее выбранных dates,0fits, C≤220. Proposal ceiling≤30CPUmin/≤30wall min,2threads,RSS≤6GiB; source/hash/scan/oracle/export/failures входят целиком. Малое output Q не ограничивает global popularity scan. До target opening нужны independently checked candidate/source seals; затем ровно один заранее разрешённый retrieval comparison, без ranker retuning.

Primary future estimand зафиксировать как conditional query-macro full-Y Recall: `Δ=mean_(q∈Q+) [(g_q−l_q)/|Y_q|]`; pooled `(Σg−Σl)/Σ|Y|` отдельно, не подменяет primary. Empty/zeroY/maturity и cold-outside-U сохраняются. Если matchedΔ≤0, recipe не проходит заранее объявленный point screening; это не статистическое опровержение положительного population effect. При малом support/неопределённости — inconclusive, без новых slices/quota/refill. Положительный retrievalΔ ещё не доказывает рост итогового NDCG.

**Приоритет:** первый возможный quality look после deliverable, если вопрос coverage действительно выбран заранее; он дешевле новых neural fits. Но расход labels остаётся существенным, и current016 C/selector не меняются.

## 3. HYP001: exact requested-pair ItemCF сверх support

**REES46 feasibility.** View-user/product IDs достаточны для binary7d memberships; no titles/images или guessed category names. [Sarwar cosine](https://www.ra.ethz.ch/CDstore/www10/papers/519/node12.html) задаёт item vectors в user space, но не наш shrinkage, temporal recipe или purchase gain. Здесь источник — аудитории других пользователей, не complementarity/causal preference.

Контргипотеза: normalized mean лишь переупаковывает popularity/degree/history support. Использовать уже [проверенный refinement001](itemcf-hyp001-refinement.md), без нового max/Jaccard/lift grid. Для snapshotb=t собственный вклад вычитается из intersections **и обеих степеней до нормировки**; диагональ исключена, requested pairs вычислены exact. Missing top-K edge не получает fabricated0.

**До fits:** существующий16-row gold даёт mean3/13 после own subtraction; raw duplicate не меняет membership; global peers исключены; threshold/expiry, zero norm и post-topK subtraction faults обязаны ловиться. Затем existing012≤100Q/≤440000 requested pairs/≤30min/RSS6GB proposal: оплачиваются full source postings/intersections/oracle, не толькоlookup. `Σm_u²` build может нарушить cap даже при небольшом C. При незавершённом pair coverage, unknown cost или нулевом доступном support — stop/defer, а не скрытый cap/window shrink.

Только новый approved fit/label protocol допускает≤2 attempts: F0=B+reviewed support controls, F1=F0+один itemcf_mean. F0 тоже fit, не бесплатный oldB; closures/support aliases проверяются против whole B. Early train rows используют собственные past snapshots, не graph конца train. Финитные CPU/wall/RSS/pairs/matrix limits двух fits должны быть отдельно приняты после cost gate; их нет в нынешнем016 allowance. Exact learner/population/weights/prefix общие; отдельный closed evaluation либо honest retrospective status обязательны.

Operational reject — ΔNDCG(F1−F0)≤0 либо нарушенный future frozen Recall guard; mechanical fault — integritySTOP, resource failure — paid incomplete, широкий interval — uncertain. Положительный screening не доказывает universal CF mechanism. Из трёх пунктов это наиболее дорогой и последний, не prerequisite T-Academy.

## Что не входит в тройку

HYP003 taxonomy/lexical остаётся возможной альтернативой, но negative009 wholeblock не доказывает вред каждого metadata family и не финансирует rescue grid. TLAB013 duplicate sensitivity полезна только как явно другая history policy: без eventID качество не устанавливает «истинную очистку». Query/user weighting072 меняет риск, не исправляет ошибку006; сейчас достаточно report wording. Empirical pruning071 добавляет source screening и новый allocation contract; DAG/cache073 не имеет measured speed advantage над batched005. ALS051/056 — одна family, sequence/graph/ARGUS — deferred:074 vocabulary/state0-fit obligations и warmup/control-population accounting предшествуют fits, не создавая дополнительных испытаний сейчас.

**Backlog disposition:** добавить максимум cross-references/уточнения существующих001/002/004 и018; новых IDs, mandatory runs или суммирования budgets не требуется. Ready после отдельного review можно назвать только конкретный tiny test. Ни весь research portfolio, ни paper count не заменяют accepted current execution, reproducibility и честный отрицательный/неопределённый итог.


## Publication scope appendix — 15 October 2026

Original note SHA256 cf0a47278ad95c5444248e76a7369e7799cdc1cc10dee5a6fd640a6352ffbc74. This retained research snapshot predates the locally accepted actual016 model evidence in the current [progress report](../progress-report.md). Its future tense is historical scope, not the current canonical execution status. No new hypothesis execution, resource grant, fit, source download or reserved-target access is authorized by publication. Current accepted development winner is R2; this does not establish guided-strategy superiority or heldout improvement.
