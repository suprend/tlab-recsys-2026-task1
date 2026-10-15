# M001: новые модели, loss и перенос — независимый раунд

15 октября 2026. **Исследование и предложения; запусков нет.** Прочитаны первичные работы2024–2026 и существующие canonical model/loss/research notes. Новые отчёты двух других brainstorm-линий не читались и не используются для выводов. Данные, query targets, модели, encoder APIs и зависимости не открывались/не устанавливались; внешние источники прочитаны браузером. Текущий015/016 и их отложенные25–31 не меняются. Кандидатные ID M001-C1…C5 стабильны внутри раунда; новые HYP назначаются после независимой проверки novelty.

Главное предложение — рассматривать две разные возможности: **изменить способ использования purchase labels** и **изменить inductive bias learner при тех же признаках**. Название новой архитектуры не устраняет малый support, зависимость запросов одного пользователя или selection bias. Поэтому ниже каждый кандидат начинается с дешёвого механического опровержения, а не с обучения большого чужого pipeline.

## M001-C1 — distillation с проверкой возраста учителя

**Первичное основание.** Khani et al., RecSys2024, исследуют distillation в меняющихся online ranking distributions. Они отделяют hard/soft supervision, обсуждают перенос ошибок учителя и стоимость своевременного распространения его logits. Их video/multi-objective результаты не доказывают purchase-ranking эффекта здесь. [Авторский paper, §§2–3](https://arxiv.org/html/2408.14678v1).

**Наша гипотеза:** небольшой student может извлечь полезный порядок альтернатив из своевременных teacher scores, но устаревший teacher причинит вред прежде всего на новых/слабо наблюдавшихся парах. Для будущего опыта student получает ровно существующие B41, без metadata/sequence расширения. Teacher использует те же входы и отдельно разрешённый более ранний mature interval. На строках после его availability определить soft target `ỹ=(1−λ)y+λ sigmoid(z_teacher)`, λ=0.5 заранее; query-weighted CrossEntropy сохраняет массу1 на непустой C. Это **наш ограниченный direct-KD adaptation**, не воспроизведение auxiliary-head системы статьи.

**Контроль и counterhypothesis:** тот же student на hard labels; дополнительный stale-teacher arm нужен для вопроса о возрасте, а не для выбора лучшего учителя по test. Контргипотеза — сглаженные teacher labels всего лишь копируют popularity и подавляют редкие покупки. Самый дешёвый первый gate —32 синтетические строки: teacher, обученный после их anchors, должен быть отвергнут; swap suffix labels не меняет ранее выданные logits; soft-target orientation/масса проверяются буквально. Будущий pilot:100 query inference-cost gate, затем максимум два teacher checkpoints из разных заранее заданных past-cutoffs и три student fits, всего5 fits/60 CPU минут, RSS8GiB,2 threads, включая все teacher scoring и persistence. Это запрос на новый budget, не доступный остаток016.

**Novelty:** HYP025 — item-only supervised prior, M08 — upstream encoder score как downstream feature; здесь teacher scores меняют supervision student, а возраст teacher является отдельным treatment. Общие student rows начинаются после availability обоих teacher checkpoints; различие teachers включает изменившийся training prefix и не является чистым эффектом elapsed age при неизменных знаниях. ARGUS/Sona distillation уже упомянута, поэтому «использовать distillation» само по себе не новая идея. Статус: новый узкий objective/lifecycle candidate, deferred до новой reservation. При отсутствии superiority над hard-label student и приемлемой latency ветвь закрывается; невыигрыш ничего не говорит обо всех KD системах.

## M001-C2 — quantile-weighted top‑20 loss на полном фиксированном shortlist

**Основание.** Yang et al., KDD2025, SL@K используют сглаженный top-K threshold и weighted softmax. Paper содержит условие ненулевого DCG в derivation; это не общая гарантия прироста любой модели. [Авторский PDF, Eq3.5/Theorem3.2](https://jiawei-chen.github.io/paper/KDD25-SLK.pdf), [авторский код](https://github.com/Tiny-Snow/IR-Benchmark).

**Гипотеза:** при C≤220 полный score vector уже достаточно мал, чтобы заменить Monte Carlo quantile статьи точным candidate threshold и сосредоточить learning на границе20. Для mature `P=Y∩C`, `|P|>0`, предложенный loss:

`Lq = mean[p∈P] sigmoid((sp−β20)/τw) × logsumexp[j∈C]((sj−sp)/τd)`.

Здесь mean охватывает произведение, β20 берётся только из текущих scores всего C; τw/τd фиксируются до pilot. При |C|≤20 weight=1 задаётся явно; tie policy и stop-gradient/дифференцирование threshold требуют одного выбранного контракта. Это адаптация, а не неизменённый paper objective. Query без найденного positive не создаёт listwise signal, но сохраняется в full-Y evaluation; target внеC не вставляется.

**Counterhypothesis:** sigmoid даёт больший вес уже хорошо ранжированным positives и может закрепить плохую cold/tail coverage. Дешёвое опровержение — literal21-item fixture с positive на19/20/21 позициях, ties, |C|0/1/20 и zeroY; сравнить математические значения/градиенты и отказаться, если normalization или threshold делает loss бессодержательным. Затем ровно два fits одного компактного numeric MLP: обычный full-C softmax против adaptation, без смены backbone/features/query weights; максимум30 CPU минут после100Q cost gate. Published full-catalog speedup сюда не переносится.

**Novelty:** HYP057/058 изучают full/sample denominator и negative law, L03 — существующие pairwise surrogates. Здесь меняется positive weighting по конкретному cutoff20 при **том же полном C**. Статус: новый loss candidate, needs-design-review; strongest first hypothesis, но не право менять current Logloss/B.

## M001-C3 — parameter-sharing ensemble вместо более глубокого одиночного MLP

**Основание.** TabM, ICLR2025, использует совместно обучаемые implicit MLP с общей матрицей и небольшими member adapters; авторы изучают regularization и optimization эффекты. Benchmark training speed в статье включает A100, не наш Mac. [Первичный paper, §§3.2–3.5/4.3](https://proceedings.iclr.cc/paper_files/paper/2025/file/c1ba41c694834aeef91ae161711d4939-Paper-Conference.pdf), [авторская реализация](https://github.com/yandex-research/tabm).

**Гипотеза:** совместное ограничение `li(x)=si⊙W(ri⊙x)+bi` уменьшит нестабильность sparse-label tabular reranking без необходимости добавлять sequence/ID tables. Начать с k=4, двух128-wide layers, фиксированного mean probability для ранжирования и одного frozen checkpoint. Shared B41 preprocessing обучается только на training prefix: median imputation, clipping/scaling и явные missing masks одинаковы у TabM и matched MLP. Это расширение представления для обоих neural arms, поэтому сравнение с CatBoost отдельно называется package comparison.

**Counterhypothesis:** четыре сильно коррелированных submodels почти идентичны, а выигрыш объясняется дополнительными параметрами или compute. Первый gate без quality labels — посчитать actual parameters/activation bounds и проверить четыре несливающихся adapter branches на32 synthetic rows. Далее matched-width одиночный MLP и TabM получают одинаковые Q/C/loss/preprocessing и отдельные **равные CPU ceilings**, плюс полный учёт пройденных updates. Два fits≤30 CPU минут/8GiB/2threads, после100Q train/inference gate. Не pruning heads после validation и не бесплатный selection по отдельным submodels.

**Novelty:** M05 предлагает candidate-conditioned attention, DCN/DLRM; здесь нет attention/history encoder и проверяется конкретная shared-weight ensemble regularization. Generic ensemble был deferred, но такого механизма в canonical ledger не найдено. Disagreement heads — диагностический scalar, **не калиброванная uncertainty** и не основание удалять low-support queries. Статус: новый learner candidate, deferred до dependency/resource review.

## M001-C4 — локальный in-context learner как ограниченный tabular перенос

**Основание.** Localized TabICLv2, arXiv preprint августа2026, выбирает k-nearest **training rows** в learned row space перед ICL stage. Его основные результаты включают fine-tuning stages2/3, stratified classification splits и A100; маленький context не устраняет стоимость построения cached representations. [Авторский текст, §§3–4](https://arxiv.org/html/2608.16429v1). Базовый TabICLv2 и открытый inference/pretraining recipe описаны отдельно. [ICML2026 paper](https://proceedings.mlr.press/v306/qu26a.html), [авторский repository](https://github.com/soda-inria/tabicl).

**Наша гипотеза:** для low-support candidate rows32 локальных зрелых примера могут дать полезный inductive transfer лучше32 случайных примеров при одинаковом frozen foundation checkpoint. Это retrieval **контекста обучения**, не замена item candidate generator. Нельзя автоматически считать похожими две строки лишь потому, что в них одинаковая числовая величина ID; используются B41 и past-fit preprocessing. Repeated user rows ограничить одной на query и заранее задать user cap, иначе соседями становятся копии одной истории.

**Дешёвый falsifier:** metadata/license/checkpoint provenance и shape/memory план без загрузки weights; затем только при отдельном разрешении100Q, pool≤4096 mature rows, k32, локальный против seeded-random context, одинаковый row encoder/cached state. Representation construction, neighbor search, all predictions и weight download входят в будущий cap≤30 CPU минут/8GiB. При недоступном CPU/MPS backend или превышении ресурса — deferred без silent cloud/GPU. Не обещаем повторить headline миллион строк.

**Novelty:** прежние TabPFN mention относятся к AutoFE benchmarks, а ItemCF/HYP001 выбирает соседей items. Новый кандидат фиксирует выбор labelled contexts под временным/зависимым recommendation estimand. Counterhypothesis — nearest contexts имеют плохой positive support, amplifying popularity или same-user dependence; random contexts оказываются не хуже. Все queryY будущего периода запрещены в context, scaler/cache обучены/доступны до prediction. Статус: новый transfer candidate, resource-blocked design; не current mandatory task.

## M001-C5 — bilateral positive denoising: сохранить явный отказ

BSL, ICDE2024, заменяет positive mean на `−τ+ log mean[p∈P] exp(sp/τ+)`, добавляя negative log-mean-exp с отдельной температурой. [Авторский paper, Eq17–18](https://jiawei-chen.github.io/paper/ICDE24-BSL.pdf), [официальный code](https://github.com/junkangwu/BSL). **Мой вывод из формулы:** при единственном positive первая часть точно равна `−sp` для любого τ+; нового positive-side механизма нет. При нескольких positives он сильнее поддерживает уже высокий score и может игнорировать трудную покупку.

Это отличается от generic focal loss, но пока недостаточно для новой исполняемой HYP. Дешёвый будущий gate — support distribution `|Y∩C|` на отдельно разрешённом training prefix и literal1/2-positive algebra. Никаких новых scans здесь не выполнено. Если almost-all mass приходится на singleton groups, branch rejected как малополезная; реальные покупки нельзя объявлять noise из-за низкого model score. Ни будущие покупки для negative cleaning, ни heldout contamination для оценки noise не допускаются. Статус: rejected-for-current-plan / сохраняем candidate ID,0fits.

## Общая проверка, переносимость и очередь

Приоритет: C2 design → C3 resource feasibility → C1 teacher chronology; C4 только после metadata/resource admission; C5 не обучать. Это **альтернативы**, их proposed ceilings не складываются в разрешённый новый портфель. До любого pilot нужно выбрать один вопрос, новый development/confirmation domain и полный attempt ledger. Нынешние25–31 останутся report-only для уже замороженных моделей.

Matched arms используют один заранее созданный Q/C/Y, full-Y NDCG20/Recall20 и четыре прежних estimands. Proposal success: improvement по primary conditional query NDCG, Recall guard−0.002 и отсутствие заранее заданного неприемлемого ухудшения past-history≤4/missing-support slices, с поддержкой и paired user uncertainty. Threshold/slice-count minima фиксируются **до нового run**; недостаточная поддержка означает inconclusive, не quality winner. Не выбирать лучший seed/температуру/head/checkpoint бесплатно.

Для другого dataset сначала schema/action/time/license compatibility. Механизмы могут переноситься на tabular ranking rows, но предполагаемые exposures, stock или одинаковые category labels не возникают из foundation weights. Отказ narrow adaptation не опровергает исходную статью. Ни одна из её accuracy/AUC/speed цифр не становится обещанным uplift нашего purchase pipeline.
