# Heldout25/26–31: строгая граница prediction-before-Y

15 октября2026. Независимый source/design audit; никакие heldout data/targets/models/SQL/tests не открывались и не выполнялись. Coordinator проектирует новый контракт; данная note не утверждает календарь, config, бюджет или execution. Прочитаны accepted temporal/anchor/metrics helpers и предыдущие [038](../research-lab/round-038.md)/[039](../research-lab/round-039.md). Наблюдавшиеся SHA: `anchor_pilot.py` — `d9344599ae1d64780374ede5006644e1f9983ed84085d0c8a64ec76fd99c835d`; `temporal_contract.py` — `c85adccbd861463051c479b96f9dffdc8dfd920326e08c55ddefe6b5bbd41d66`; `ranking_metrics.py` — `90c3a02d69bb7850eda24a61526978e53e70ffc3856f44c5204e6409b833c9a9`.

**Вывод:** reporting-only25 и unchanged26–31 совместимы с динамической strict-past историей, если freeze относится к decision/model/program/policy, а не к прекращению поступления raw events. Новый тонкий риск — назвать этот режим «все target-составляющие байты ещё неизвестны» или «та же фиксированная популяция пользователей». Оба утверждения неверны для разрешённого протокола.

## Temporal/access obligations

Пусть T25=25Oct00 UTC, t — query anchor, H=24h, δ — объявленная задержка доступности. History использует только `S≤event_time<t`; глобальные peers в t исключены. Target — distinct purchased products на `[t,t+H)`. Full maturity требует coverage до `t+H` и `available_before−δ≥t+H`; это right-open endpoint правило, не правило для `(t,t+H]`.

Simulated decision availability `A` должна удовлетворять `A≥max(used selection label maturity + positive decision compute allowance, fitted artifact availability)` и `A<T25`. Actual2026 audit должен доказать seal model/program/decision до открытия reserved query-target/evaluation feedback, затем seal **всех заранее разрешённых branches/dates predictions** до отдельного unlock. Здесь нет утверждения, что physical model file существовал в2019. Не добавляются branches, checkpoints, looks или fits.

Raw purchase25 может попасть в strict-past features, observed catalog и active48h eligibility на26. Это применение frozen transform к новой разрешённой истории; не refit и не новое decision. Но тот же raw event может составлять Y25. Значит prediction-before-Y — граница query-target relations/evaluator/feedback, а не запрет любого доступа к пересекающимся raw source bytes. Whitelist источника и per-anchor predicates обязательны; target table/yarray/automatic label-producing helper до unlock запрещены. Whole-month EDA/source hashing уже раскрыты отдельно.

[Ji et al., TOIS2023](https://arxiv.org/abs/2010.11060v4) показывают проблему нарушения общей timeline и future-item leakage. Это поддерживает global history boundary, но сама дата split не доказывает availability каждого metadata/fitted component. [Meng et al.2020](https://arxiv.org/abs/2007.13237v1) показывают зависимость model rankings от split; поэтому изменение25/26 dates после результата не является нейтральным repair. [Cawley–Talbot2010](https://www.jmlr.org/papers/v11/cawley10a.html) обосновывает отделение model choice от оценки выбранного решения. Reporting-only confirmation без нового выбора не требует выдуманного positive decision gap26; postconfirmation adaptation уже нарушает эту предпосылку.

## Population, coverage и censoring

Active48h — eligibility по view/cart/purchase в `[t−48h,t)`, затем deterministic bottom SHA over eligible users, до labels. Это выборка **user-days**, максимум2000 ежедневно; eligible IDs и hash order меняются с anchor. Нельзя фильтровать только будущих покупателей, только users из train, только непустые C, только успешно scored days или users с полными персональными48h. Одинакова policy, а не множество user IDs. User появился вчера — это короткий observed age, не отсутствие calendar source coverage.

Bottomhash воспроизводимая cap-выборка, не доказанная probability sample всех marketplace users. Conditional query-macro относится к mature sampled queries с непустым Y; zero variants отдельно сохраняют mature zeroY. Repeated-user dependence и малая positive support не исчезают от большей общей численности Q. [Cañamares–Castells–Moffat2020](https://doi.org/10.1007/s10791-020-09371-3) разделяет решения выбора users/targets/candidate domain; это основание явно назвать population, а не переносить метрику на всех пользователей.

EmptyC сохраняет Q, ноль prediction rows и полный future target после unlock. OutC/cold Y остаются misses; observed catalog не равен stock. Censored query не превращается в mature emptyY. Для31Oct00/H24/δ0 нужен source coverage до1Nov00: nominal config endpoint и timestamp последнего наблюдавшегося события сами по себе не доказывают completeness логгирования. При δ>0 доступность maturity сдвигается; нельзя получить negative label из отсутствующего будущего периода. Coverage assumption/provenance фиксируются до outcome opening.

Старый017 phase table содержит confirmation24–25, а предполагаемый reporting-only контракт —25. Нужен отдельный prospective version/lock с явным supersession; старый config нельзя молча прочитать как уже утверждённый новый календарь. Public `create_queries` отделён от `create_labels`, но возвращает maturity=None: перед C нужна calendar-only annotation. Generic003 build/run и current always-Y model-data loader не являются label-blind inference path; fake zeroY shim недопустим.

## Малый source-free adversarial test specification

**Только будущая спецификация**,0fits, без разрешения исполнения. T=25Oct00; p уже наблюдаем, z/r впервые появляются в указанных строках. Ниже10 physical event rows; две одинаковые строки сохраняются.

| User | Item/action | Time |
|---|---|---|
| A | p/view | T−48h |
| B | p/view | T−1h |
| C | p/view | T |
| A | z/purchase | T |
| A | z/purchase | T+1h |
| A | z/purchase | T+1h, exact duplicate |
| B | p/purchase | T+24h |
| C | r/cart | T+23h |
| D | p/view | T−48h−1µs |
| E | p/view | T−1h |

При untruncated tiny cap4: eligible25={A,B,E}, eligible26={A,B,C,E}; всего7Q. D не допущен lower boundary, C peer не допускает C25. Eligibility25 не изменяется от future suffix. Для отдельного sampling test cap2 определяется literal independent SHA-256 reference над точной accepted serialization `sample|2026|UTCanchor|integerID`, без label input. Здесь hashes/выбранные ID не вычислялись. Перестановка/дублирование raw rows не меняет sampled IDs; замена purchase outcomes вне eligibility prefix не меняет Q25.

Задать5 C rows:25 A→p,B→p,E→empty;26 A→z,B→p,C→r,E→empty. Итого10events+7Q+5C=22rows, expected tiny predictions по каждой C-row без native model. До unlock label-reader/evaluator spies должны иметь0calls. После unlock: Y25(A)={z}, Y25(B/E)=empty; Y26(B)={p}, остальные26Y empty. z outC25 остаётся miss; anchor26 purchase исключён из F26 и Y25, но включён в Y26. Pair purchase count A,z на26=3raw rows, distinct target25 size1. z ещё не catalog25, но законно catalog26. Дополнительная mutation удаляет A25→p: positive Q с теперь emptyC сохраняется, fullY={z} и ranking score остаётся0; условная population не сокращается по candidate availability.

Отдельные calendar-only records сохраняют bound≤32rows:31Oct00 mature при E=1Nov00/δ0; тот же запрос censored при E на1µs раньше либо δ=1s без поздней availability. Unknown coverage не принимается как complete. Fault mutations: corrupt последняя prediction/изменённый model prefix/cleanup failure/пропущенный emptyC Q/target-reader доseal оставляют unlock закрытым. Negative quality25 после lawful unlock не меняет26–31 model/program/prefix; integrity failure не переименовывается в no-improvement. Все эти expected values выводятся из literal spec, без production materializer.

## Отчётная формулировка

«В2026 выполнен ретроспективный offline replay с simulated2019 availability и заранее замороженной процедурой. На каждом daily anchor past-active48h user-days отбирались по фиксированному bottomhash правилу; Q/C и strict-past features формировались без открытия query-level targets/evaluation feedback. Все предусмотренные predictions были sealed до target unlock.25 использовался только для reporting;26–31 оценивали те же frozen models/prefixes с разрешённой обновляемой историей. Метрики относятся к указанным sampled mature queries/fullY и coverage assumptions, не ко всем marketplace users или causal recommendation lift».

No new policy/metric/budget/task: эти уточнения и tiny acceptance obligations входят в существующий heldout/reproduction/evaluation scope. Actual schedule/config/source/model/resource approval остаются отдельными gates.
