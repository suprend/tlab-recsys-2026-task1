# Независимый cross-review M001: модели, loss и перенос

15 октября 2026. Review target: `brainstorm-m001.md` и его ledger; опубликованная копия M001 — тот же target. Прочитаны canonical backlog, model/loss notes, data/schema и accepted strong-B report. Другие новые brainstorm reports не использовались. Для primary-source проверки TabM/TabICLv2 привлечён отдельный read-only research subagent; существенные claims также сверены с первичными страницами. Из проекта читались только документы: без actual DB/raw/feature/target/model reads, large hashing, dependency installs, downloads, fits, encoder/API jobs и Git. Выполнены лишь stdlib literal-math probes. B/W и frozen015/016/25–31 неизменны.

**Решение:** C3 сохранить как **accept-needs-pilot после исправления training contract**; C1 и C2 — **refine**, C4 — **defer**, C5 — **reject-current**. Ни один статус не разрешает исполнение. Приоритет C2 как «strongest first» пока снять: у предложенной формулы найден буквальный контрпример направления градиента.

| ID | Verdict | Что решает следующий минимальный gate |
|---|---|---|
| M001-C1 | refine | Определены ли BCE/weights, teacher availability и общий post-teacher student interval; укладывается ли весь контраст в 5 fits |
| M001-C2 | refine; naïve full-gradient adaptation fails | Может ли update поощрять демоцию настоящего positive; выбран ли ограниченный score/weight-gradient contract |
| M001-C3 | accept-needs-pilot, admission conditional | Mean per-head loss и actual shape/cost; 2 fits сравнивают learner mechanism, сильный B оценивается отдельно |
| M001-C4 | defer | Есть ли воспроизводимый localized implementation/checkpoint; mature label-bearing caches, class support и CPU cost |
| M001-C5 | reject-current, preserve ID | Singleton positive-side term тождественен −score; noisy-purchase premise не обоснован |

## Общий контекст, который ограничивает все пять идей

[Canonical backlog](../backlog.md) и [accepted019 verification](../backlog-reviews/tlab019-strong-output-verification.md) уже содержат сильный development B: CatBoost Logloss, base41, 26000 train Q, depth6/L2=30, 300 trained trees и prefix300. Его development NDCG20=.458611, Recall20=.585127; это не untouched quality. Selection имеет только 73 positive full-Y queries из4000 и96 targets. Миллионы candidate rows не создают миллионы независимых purchase observations. Bootstrap должен кластеризовать users, а sparse slices с недостаточным support остаются inconclusive. Нельзя доказывать пользу альтернативы только победой над ослабленным hard-label MLP.

В [baseline input contract](../experiments/boosting-baselines.md) B41 — numeric manual counts/recencies/shares, missing/age/coverage/context и retrieval signals. Raw query/user/product/category IDs не являются ordinal inputs; NULL остаётся NaN. [Schema](../data.md) не содержит titles, images, impressions, stock, order IDs/quantities. Metadata-price009 rejected wholeblock: новый numeric learner не получает brand/price/code незаметно. Train-only imputation/scaling/masks для neural arms допустимы как объявленная preprocessing package; они не дают права говорить, что inputs буквально совпадают с CatBoost NaN treatment.

Один вопрос требует новой prospective development/confirmation reservation. Текущий report-only25–31 не является запасным selection для этих идей. Q/C/full-Y и четыре estimands сохраняются; positives вне C не вставляются. Новые models, hyperparameters, checkpoints, failures и cost gates имеют attempt ledger. Source-paper accuracy/throughput не становится ожидаемым uplift или измеренной стоимостью здесь.

## C1: полезный узкий KD-контраст, но нужен более точный estimand

**Первичный claim подтверждён.** Khani et al. v1 датирован26Aug2024; RecSys2024. Paper рассматривает multi-objective pointwise video ranking, continuous teacher updates и auxiliary logits против bias propagation прямой distillation. Это мотивирует chronology/bias check, но не доказывает прямой convex-target purchase KD. [Даты](https://arxiv.org/abs/2408.14678), [метод, §§2–3](https://arxiv.org/html/2408.14678v1).

**Novelty:** narrow teacher-prefix/freshness contrast отличается от HYP025 item-only prior и M08 frozen encoder feature: scores меняют supervision. Generic distillation уже есть в ARGUS/Sona discussion; новый ID не должен означать «первыми предложили KD». Fresh/stale checkpoints отличаются training prefix и количеством данных, поэтому causal elapsed-age effect не идентифицирован. Название treatment — «две заранее заданные teacher-prefix policies на общем later student interval».

**Необходимое уточнение:** определить objective как query-weighted binary BCE

`Lq = (1/|Cq|) Σi∈Cq [softplus(si) − ((1−λ)yi + λ sigmoid(zi_teacher))si]`, `λ=.5`.

Тогда сумма1 относится к row weights, а не teacher target probabilities. Сумма sigmoid по C не обязана быть1. Если автор намерен использовать categorical CE, нужно заново определить positive normalization и zero-positive groups; это другой objective. Teacher logits не являются калиброванной purchase probability только из-за sigmoid.

**Chronology:** для каждого teacher все upstream labels должны быть mature к fit cutoff, весь preprocessing/selection — на этом прошлом; `teacher_available_at≤student_row_anchor` для logits, выдаваемых как time-aligned supervision. Общие student rows начинаются после availability обоих teachers. Teacher, fitted позже anchor, не исправляется ordinary random OOF: отсутствие собственного label не исключает future-period information. Forward/time cross-fitting с несколькими checkpoints — дополнительные fits. При обычном standalone offline student его hard labels могут становиться mature после anchors; нельзя путать это с teacher-state availability treatment.

**Дешёвый falsifier:** 32 literal rows с намеренно поздним teacher, future-suffix swap, empty C/zero-Y, BCE orientation и row-weight mass. Затем metadata-only schedule должен показать ненулевой общий student interval и ожидаемый support без новых target scans. «Два teachers + hard/stale/fresh students» действительно5 fits, если каждый attempt единственный и λ/seed/checkpoint фиксированы. 100Q реальный training gate не является шестым бесплатным fit: это prefix уже учтённой попытки либо отдельно зарезервированный fit. Все scoring/persistence/failed costs оплачиваются. Strong-B refit на том же допустимом label domain потребует ещё fit slot, если reuse accepted B не оправдан его availability/population; один five-fit mechanism contrast сам по себе не доказывает task1 superiority.

**Verdict refine.** После этого возможен новый ограниченный pilot; сейчас не тратить budget на выбор учителя или калибровки по test.

## C2: формула требует исправления до model pilot

**Первичный claim подтверждён с существенной границей.** SL@K — KDD2025,3–7Aug2025. Eq3.5 использует sigmoid positive weight и exponential score differences. Theorem3.2 предполагает ненулевой Top-K hit; он не гарантирует improvement при градиентном обучении нашей адаптации. [Paper](https://jiawei-chen.github.io/paper/KDD25-SLK.pdf). Авторский executable code использует cosine scores, periodically cached beta, `no_grad` при quantile update; сам positive weight остаётся differentiable. Его docstring о sigmoid denominator расходится с executable logsumexp — ориентироваться на исполненный метод. [Авторский код](https://raw.githubusercontent.com/Tiny-Snow/IR-Benchmark/main/src/itemrec/optimizer/optim_SLatK.py).

**Novelty:** fixed-C top20 weighting — новый узкий objective внутри уже существующей softmax/listwise family L03/HYP057/058. Exact top20 threshold в C≤220 разумен как инженерная адаптация, но full-C denominator, current per-query threshold и unbounded MLP scores отличаются от paper/code. Нельзя наследовать catalog-level theorem или speedup.

**Независимый контрпример, выполнен literal stdlib math.** C содержит21 item:20 negatives со score0 и один true positive со score−1; β20=0, обе температуры1. Positive стоит21-м, и для малой perturbation его score не меняет threshold. Для предложенного `L=σ(sp−β)·logΣj exp(sj−sp)` получено:

| Quantity | Value |
|---|---:|
| L при sp=−1 | 1.0795198718 |
| ∂L/∂sp, analytical | **+0.5251083930** |
| Central finite difference | +0.5251083930 |
| Ordinary full-softmax ∂L/∂sp | −0.9819382552 |
| L при sp=−10 | .0005899787 |
| L при sp=−100 | 3.8315e−42 |

Gradient descent уменьшает true-positive score и loss. Для unbounded score функция может почти обнулиться, выбросив трудный positive. Это контрпример naïve adaptation, не опровержение всей статьи: исходные cosine scores ограничены, и training dynamics иные. Дифференцирование только threshold не исправляет пример — здесь threshold уже локально constant.

**Минимальный repair gate:** заранее выбрать один update contract: например, stop-gradient **всего** positive weight, либо другой обоснованный bounded-score/weight policy. При detached weight в этом же fixture derivative=−.2640838700; это reweighted CE update и не градиент исходного полного scalar expression. Threshold stop-gradient отдельно недостаточен. Не добавлять все repairs как бесплатный temperature/algorithm search.

После выбора повторить ranks19/20/21, ties, C0/1/20, P0/all-positive, finite/infinite score guard, translation invariance и positive normalization. При all-positive CE может иметь ненулевой balancing gradient; «нет ranking distinction» не означает нулевую производную. Только затем2 заранее заданных matched-MLP fits с полным C и одной preprocessing/loss-normalization policy. Strong B остаётся отдельным same-domain benchmark. **Verdict refine; готового pilot нет.**

## C3: наиболее конкретный допустимый learner-кандидат после contract correction

**Primary chronology:** TabM v1=31Oct2024, ICLR2025; paper не2026 foundation release. Shared matrices/member adapters — реальный механизм. [Paper chronology](https://arxiv.org/abs/2410.24210), [официальный implementation](https://github.com/yandex-research/tabm). В [training contract](https://github.com/yandex-research/tabm#training) явно требуется mean отдельных head losses, **не loss(mean prediction)**; classification inference обычно усредняет probabilities. Вариант k4/2×128 — наша small adaptation; paper heuristic k32 не переносится автоматически. Source Apache2.0 и CPU/macOS setup есть; 30CPU-min/8GiB на этом pipeline не проверены. [License](https://github.com/yandex-research/tabm/blob/main/LICENSE), [CPU reproduction setup](https://github.com/yandex-research/tabm/blob/main/paper/README.md).

**Novelty:** отдельный shared-weight regularization mechanism, не HYP063 conditional history pooling, HYP064 cross layers или generic independent ensemble. Для fidelity зафиксировать `arch_type='tabm'`, numeric embedding choice, first random input scaling, remaining adapter initialization и независимые output heads; простая BatchEnsemble formula не задаёт весь TabM. Fresh weights обучаются только на mature train prefix, внешнего pretrained state здесь нет.

**Cheapest falsifier:** literal parameter/activation ledger и32 synthetic rows с независимостью branches, mean-per-head loss и фиксированным inference aggregation. Нет необходимости обучать foundation model. Затем100Q gate должен считать до22000 candidate rows и входить в attempts/cost. Один jointly trained TabM — один optimizer-fit attempt, но k4 member computations/activations и four predictions платятся физически; это не четыре бесплатных MLP.

Matched same-width MLP и TabM с одинаковыми B41/preprocessing/query weights/objective изолируют ensemble package. Одинаковая width не равна одинаковому parameter count или compute; выбрать равный actual CPU ceiling и раскрыть parameters/updates. Если total2-fit cap30CPU-min, per-arm ceilings не могут быть30min каждый: плану нужны явные15+15 либо иной равный split. Не выбирать head/seed/checkpoint post-hoc. Strong-B сравнение на том же новом domain — обязательное условие полезности для task1, а не гарантия from-paper. **Verdict accept-needs-pilot условно на эти contracts, dependency review и новую reservation;0execution authority.**

## C4: перенос интересен, но frozen base не воспроизводит localized result

**Даты и provenance подтверждены.** Localized TabICLv2 v1=17Aug2026, workshop paper; base TabICLv2 — ICML2026. Localized method извлекает cosine neighbors из cached Stage2 representations и включает synthetic fine-tuning stages2/3; A100/stratified classification не является нашим temporal purchase experiment. [Localized source](https://arxiv.org/html/2608.16429v1), [base venue](https://proceedings.mlr.press/v306/qu26a.html). Inspected paper не даёт released localized code/FT-checkpoint link: это **не доказательство отсутствия**, но base repository не доказывает его доступность. Base author-linked v2 checkpoint metadata показывает110MB/BSD3; weight bytes не читались. [Metadata](https://huggingface.co/jingang/TabICL/blob/main/tabicl-classifier-v2-20260212.ckpt).

**Correction:** CPU/MPS backend поддержан официальным [classifier source](https://github.com/soda-inria/tabicl/blob/main/src/tabicl/_sklearn/classifier.py); нельзя объявлять его отсутствующим. Но наличие backend не подтверждает local110MB weights + representations + inference fitting в30CPU-min/8GiB. Gate должен включать setup/download отдельно по wall/network и actualCPU, cached embeddings, neighbor search и22000 candidate-row predictions на100Q. Размер weights не равен peak memory.

[Base paper](https://arxiv.org/html/2602.11139v1) описывает entirely synthetic pretraining и target-aware labels до Stage1/2. Поэтому foundation release2026 — явно объявленная retrospective-benchmark availability, не автоматическое доказательство future REES label leakage. Однако собственный cache/index label-bearing: все контекстные labels должны быть mature/available к prediction anchor уже при его построении. Удаление futureY только в final32 contexts слишком поздно. Fit scaler/vocabulary и retrieval preprocessing также входят в snapshot. Нельзя заранее кодировать будущие test rows совместно и выдавать трансдукцию за pure past-only protocol.

**Population/design gate:** official frozen `fit(X,y)` не принимает training sample_weight. [API](https://tabicl.readthedocs.io/en/latest/api.html). Local-versus-random32 contexts проверяет retrieval policy при том же checkpoint, не matched query-weighted Logloss training. Для sparse binary candidate labels случайные32 rows могут иметь один класс; one-row-per-query/user caps дополнительно меняют class support. Нужны заранее одинаковые local/random mature pools, exclusion own query/target, explicit same-user policy, class-support/fallback rule и fixed row-feature distance. Нельзя отбирать contexts по heldout purchase outcome или трактовать raw ID magnitude как similarity. Strong B — separate package comparison; любая новая B fit оплачивается.

**Novelty:** labelled-row context retrieval отличается от item retrieval/HYP001 и прежнего TabPFN benchmark mention. **Verdict defer** до metadata-only admission и честного source/base-adaptation naming. Cheapest falsifier — документированный localized implementation/checkpoint либо явная наша frozen-base kNN adaptation, shape/backend/class-support план; без загрузки weights. Даже успешная feasibility не означает quality.

## C5: отказ для текущего плана корректен, но основание нужно формулировать узко

BSL впервые опубликован как arXiv v1 20Dec2023 и представлен на ICDE2024. Eq17–18 даёт negative log-mean-exp и positive term `−τ+ log mean exp(sp/τ+)`. [Chronology](https://arxiv.org/abs/2312.12882), [Eq17–18](https://jiawei-chen.github.io/paper/ICDE24-BSL.pdf). Авторский multi-mode собирает positive aggregation по повторяющемуся user в batch, а не автоматически по нашему query-day P; copying batch semantics поменяет задачу. [Author code](https://raw.githubusercontent.com/junkangwu/BSL/master/utils/losses.py).

Literal singleton algebra подтверждено: positive term=−sp для любого positive τ. Для scores[2,−2],τ=1 positive gradients=[−.982014,−.017986]: трудная покупка получает мало positive-side signal. Это не даёт права объявлять её noise. Actual `|Y∩C|` distribution здесь не читалась; claim «почти все singleton» пока гипотеза. Также singleton identity касается только positive-side mechanism: negative temperatures/denominator могут отличаться от выбранного baseline, так что **весь BSL не доказан тождественным BCE/full-C CE**.

**Verdict reject-current/preserve-ID,0fits.** Нет нового justifyable purchase-denoising experiment. Возврат только при separately admitted mature-train support summary и содержательном noise/provenance основании; будущие покупки за H не используются для negative cleaning. Отказ не опровергает BSL на его исходных datasets.

## Передача координатору

Сохранить M001-C IDs без новых HYP до этих refinements. Candidate ceilings альтернативны и не складываются. C3 admission и repairs C1/C2 можно делать document/synthetic-only; C4 остаётся design-only, C5 не обучать. Любой будущий pilot требует нового bounded attempt/CPU/RSS/wall/selection-look ledger, fixed primary full-Y NDCG20/Recall guard−.002 и заранее заданных support minima; paired-user uncertainty не исправляет reused development. Никаких текущих B/W,015/016 или frozen25–31 изменений этот review не предлагает.
