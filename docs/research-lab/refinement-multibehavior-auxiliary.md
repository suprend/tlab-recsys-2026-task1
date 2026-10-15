# HYP065: сначала определить «any», затем проверять auxiliary transfer

15 октября2026. **HYP065 оставить deferred до existing encoder/resource gate.** Один будущий узкий refinement — сравнение purchase-only gradient с purchase+binary-horizon-any при одинаковом Q×C/encoder/procedure. Это не предложение немедленно запускать ESMM/MMoE/AITM/graph family. Прочитаны [L05](../loss-selection/05-multitask-pretrain.md), [loss critic](../loss-selection/review-04-06.md), model notes и [backlog065](../backlog.md). Они уже требуют purchase-only/any-only/reweighted controls и различают next-item, set и activity supervision. Новая HYP/task не нужна; frozen015/016, labels и fit allowances неизменны. Ни данные, model/API/test/jobs, installs или Git не использовались.

## Четыре первичных источника и граница переноса

**ESMM, SIGIR2018, arXivv2.** Моделирует impression domain: `P(click∩conversion|x)=P(click|x)P(conversion|click,x)`. Loss — CTR и joint click-conversion BCE по всем impressions; CVR является промежуточным выходом, отдельный CVR loss не используется. Shared embedding переносит более плотный сигнал. Delayed feedback явно вне основного scope. Это не «две любые event-heads устраняют sparsity/bias». [Original paper,§§2.1–2.3](https://arxiv.org/pdf/1804.07931v2).

**MMoE, KDD2018.** Official author abstract описывает shared expert submodels и отдельные task gates; эксперименты меняют relatedness и проверяют synthetic/real tasks. Это основание учитывать negative transfer и различие задач, не гарантия, что cart или view помогают purchase. Полный PDF OpenReview вернул browser challenge; здесь использован именно [Google Research author abstract](https://research.google/pubs/modeling-task-relationships-in-multi-task-learning-with-multi-gate-mixture-of-experts/), не якобы проверенный implementation/training budget. MMoE — дополнительная архитектурная переменная, лишняя для первого auxiliary-loss contrast.

**AITM, KDD2021.** В§4 labels обязаны удовлетворять `y₁≥…≥y_T`; Behavioral Expectation Calibrator штрафует `max(p̂_t−p̂_(t−1),0)`. Industrial domain — impression→click→application→approval→activation; для delayed activation учитывается14-day maturity, datasets делятся хронологически. REES46 view/cart/purchase rows не задают такую verified цепочку одной exposure. Копировать penalty `p̂_purchase≤p̂_cart≤p̂_view` нельзя. [Original paper,Eq.12–13,§5.1,AppendixA.3](https://arxiv.org/pdf/2105.08489).

**MBGCN, SIGIR2020.** Problem formulation прямо не требует temporal/strength ordering behaviors. Multi-behavior graph inputs сочетаются с **одним target-behavior BPR objective**; это не эксперимент auxiliary heads. Paper использует MF pretraining, hyperparameter grid и validation early stop; его cost не равен одному нашему fit. No-order assumption относится к relations между behaviors, не является гарантией нашего query-time strict-past builder. [Original author PDF,§§2,3.6,4.1.4](https://fi.ee.tsinghua.edu.cn/~gaochen/papers/SIGIR2020-MBGCN.pdf).

Их empirical gains относятся к собственным domains/procedures. Ни offline AUC, ни graph Recall не доказывают прирост нашего fixedC/fullY purchase ranking, exposure debiasing или пригодность для текущего CPU budget.

## Новое точное различие: union-any действительно nested, next-any — нет

Для **одной** зрелой строки `(q=(u,t),i∈C_q)` определим `y_P=1{purchase i в[t,t+H)}` и `y_A=1{view OR cart OR purchase i в[t,t+H)}`. Тогда `y_P≤y_A` по конструкции. Здесь факторизация `P(P|q,i)=P(A|q,i)P(P|A,q,i)` математически допустима для этой наблюдаемой популяции. Однако она не превращает C в impressions и не восстанавливает propensity/CTR/CVR. Для минимального опыта независимые BCE проще, чем ESMM product architecture.

Напротив, next-any-item и next-purchase-item из rawL05 имеют разные item targets. Пусть после t сначала cart(j), затем purchase(i). One-hot next-any для i равен0, next-purchase для i —1: inclusion сломано. Для horizon-union labels i имеет(1,1), j —(0,1). При purchase(i) без view/cart внутри H raw labels(view,cart,purchase)=(0,0,1), что законно и противоречит blind AITM funnel. Предыдущий view мог быть до t; missing view также не доказывает отсутствие exposure. Это наши literal counterexamples, не actual log findings.

Именно definition version нужно закрепить до сравнения: одинаковое слово «any» не разрешает незаметно заменить existing next-item proposal на set-BCE и сообщить чистый effect второй головы.

## Минимальная будущая постановка и контроль

Refinement065 — **conditional auxiliary effect при уже принятом компактном encoder**, не новый architecture search. История/features используют events строго<t с глобальными peers; обе головы получают одинаковую зрелую Q×C population, object weight1/|C_q|. Все зрелые empty-purchase/all-zero groups остаются; informative-only selection запрещён. EmptyC сохраняется в evaluation Q, но не создаёт training rows. Purchase вне C не вставляется для auxiliary: обе training головы видят только C, evaluator использует полный независимый purchaseY.

Предлагаемый loss:

`L_α = mean_q mean_(i∈C_q) BCE(y_P,p_P) + α·mean_q mean_(i∈C_q) BCE(y_A,p_A)`.

Одна небольшая α, например0,1, выбирается заранее как инженерная константа, не оптимум. Единственный узкий contrast: α=0 versus этот α, без tuning. Сохраняются architecture/parameter inventory, initialization policy, minibatch order, число optimizer steps, purchase examples, scheduler и остановка. Обе головы/вычислительные paths можно сохранять и приα=0; никаких extra epochs за «бесплатную» auxiliary phase. Это matching **процедуры и resource ceilings**, не обещание byte-equal CPU: forward/backward/optimizer/memory и labels construction оплачиваются, actual work показывается отдельно. При превышении cap arm ineligible/STOP по будущему объявленному policy, без refill.

Сравнение с сильным frozen boosting — отдельный уже необходимый reference, не доказательство, что выигрыш над слабым neural purchase-only превосходит B. Два arms отвечают только «помогает ли этот auxiliary term этому encoder». Они не доказывают необходимость двух голов вместо any-only/reweighted-single-head; existing broader controls сохраняются как граница claim, а не добавляются сейчас пакетом. Если их нельзя оплатить будущим отдельным протоколом, широкое mechanism superiority не заявлять.

Maturity обеих heads требует полного H и declared action availability delay; при разных задержках — общего cutoff по максимуму используемых label-ready times. Censored outcomes — mask/unknown, не0. Fitted encoder/model availability и decision lock должны быть до нового reserved evaluation; старые training anchors не объявляются реально обслуженными post-train encoder. Selection — только purchase fullY primary, не лучший из purchase/any AUC; снижение auxiliary loss не является promotion.

## Tiny falsification прежде fit и решение

Future-only≤16literal rows: past view(i); cart(j) послеt; purchase(i) послеt с duplicate; событие ровноt+H; отдельный mature no-event query и censored query. Gold проверяет union inclusion, независимые cart/view labels, binary duplicate collapse, endpoint, masks и неизменность ранних features при future suffix. Далее source/train-only aggregate support/overlap не заменяет effect test. Сейчас fixture не исполняется, resource allowance не выдана.

Контргипотеза: any обучает activity/popularity/повтору и ухудшает редкий purchase ranking либо improvement исчезает при matched procedure. Перенос из литературы не снимает её. Минимальный backlog action — уточнить label-definition version у existing065; **defer architecture/quality experiment до encoder gate, нового label reservation и отдельно оплаченных attempts**, после завершения нынешнего015/сдачи. Никаких новых нынешних fits/looks или изменений target policy.

## Publication boundary

Archived15October2026 as a refinement of existing hypotheses, not a new independent idea round or an execution allowance. The original research result is retained; subsequent code/review progress does not retroactively change its historical snapshot. No actual source/model/target/fit job was run for this note.
