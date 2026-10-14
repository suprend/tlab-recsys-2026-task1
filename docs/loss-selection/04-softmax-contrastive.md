# L04. Softmax и contrastive learning: сначала определить support

Дата: 15 октября 2026. Независимое исследование; обучение и замеры не выполнялись. Контекст: `docs/experiment-plan.md`, `docs/embedding-experiments.md` и общие briefs. Предлагаемый минимум — full softmax компактного history encoder на фиксированных кандидатах; sampled objective оправдан после измерения стоимости полного знаменателя.

## Единица, target и нормировка

Рабочие обозначения: фиксированный набор запросов \(\mathcal Q\), запрос \(q=(u,t)\), история строго до \(t\); \(Y_q\) — множество различных купленных товаров в предварительном горизонте \([t,t+H)\); \(C_q\) — кандидаты, построенные только по доступному прошлому. Target/anchor/H пока не утверждены. Обучение допускает только созревшие labels: конец горизонта не позже cutoff обучения. Покупки в секунду \(t\) входят в предварительный target, но не историю; порядок внутри секунды не восстанавливается по ID.

Пусть \(P_q=Y_q\cap C_q\), \(z_{qi}=\langle h_\theta(history_{<t}),e_\theta(i)\rangle/\tau\). Начальный encoder — pooled history, \(d=64\), последние 50 событий; \(\tau=1\), без изменения архитектуры между losses. Это предложенные параметры. Для \(|P_q|>0\):

\[
L_q=-\frac1{|P_q|}\sum_{p\in P_q}\log\frac{\exp z_{qp}}{\sum_{i\in C_q}\exp z_{qi}},\qquad L=\operatorname{mean}_{q:|P_q|>0}L_q.
\]

Каждый запрос имеет одинаковый вес независимо от числа покупок. Такая cross-entropy с распределением target поддерживается [PyTorch CrossEntropyLoss](https://docs.pytorch.org/docs/main/generated/torch.nn.CrossEntropyLoss.html); вероятности target нужно проверять самостоятельно. Все positives находятся в общем знаменателе с соответствующей положительной массой. Альтернатива \(-\log\sum_{p\in P_q}P_\theta(p\mid q)\) может удовлетвориться одним легким positive: для покрытия всего набора это иной objective.

Это распределение массы между товарами условно на наличии обучающего positive, не вероятность покупки пользователя. Запросы без покупок не дают такому loss сигнала, но сохраняются в оценочной популяции с заранее выбранным правилом zero-target metrics. Next-item loss имеет единственный следующий товар и другой временной смысл; view-dominated next-event pretraining нельзя объявлять оптимизацией purchase-set ranking.

## Full, sampled, InfoNCE

Full означает весь объявленный support: full \(C_q\) не равно всему catalog-at-t. Отдельный retrieval objective может использовать каталог наблюдавшихся до \(t\) товаров; тогда меняется эксперимент, а не только ускоряется loss. Нельзя добавлять будущий товар в \(C_q\), чтобы получить train/eval positive. В оценке сохраняется полный \(Y_q\): отсутствующий кандидат дает miss, отдельно показывается coverage.

Для проверяемого sampled приближения оставить \(P_q\) детерминированно и взять \(K\) независимых negatives с возвращением из \(C_q\setminus P_q\), распределение \(\pi_q(i)>0\):

\[
\widehat Z_q=\sum_{p\in P_q}e^{z_{qp}}+\frac1K\sum_{k=1}^K\frac{e^{z_{qn_k}}}{\pi_q(n_k)},\quad
\widehat L_q=-|P_q|^{-1}\sum_pz_{qp}+\log\widehat Z_q.
\]

Negative logit здесь исправляется на \(-\log K\pi_q(i)\); детерминированный positive так не исправляется. Несмещенный estimator знаменателя не делает log-loss/градиент несмещенными при конечном K: различие sampling bias и labeling bias разобрано у [Rawat et al., ICML 2021](https://proceedings.mlr.press/v139/rawat21a.html). Удаление повторов sampled IDs требует другой inclusion probability; нельзя сохранять формулу для draws без изменения весов.

Обычный InfoNCE \(-\log[e^{z_p}/(e^{z_p}+\sum_ke^{z_{n_k}})]\) — классификация positive среди sampled примеров. Без correction он не становится full-catalog CE; распределение negatives определяет задачу. Первичный источник — [CPC](https://arxiv.org/abs/1807.03748). Contrastive описывает objective; self-supervised описывает происхождение supervision. Покупки как явные labels дают поведенческое обучение по implicit feedback; [SupCon](https://arxiv.org/abs/2004.11362) прямо показывает supervised contrastive постановку.

## In-batch и настоящая logQ

In-batch negatives дешевы благодаря повторному использованию embeddings, но их law — частоты товаров в **реально выбранных обучающих строках**, включая query sampling, выбор одного positive, повторения и батчинг; это не автоматически частота всех октябрьских событий. [Yi et al.](https://research.google/pubs/sampling-bias-corrected-neural-modeling-for-large-corpus-item-recommendations/) используют frequency correction. Смесь draws должна учитывать \(\pi=\alpha\pi_{batch}+(1-\alpha)\pi_{uniform}\), затем ограничения support/positives и перенормировку. Uniform-компонента обеспечивает поддержку tail; один in-batch pool не покрывает никогда не выбранные positives. При фиксированных counts двух источников нужен согласованный estimator их смеси.

Дубликат positive ID у другого пользователя нельзя считать отрицательным; все товары из текущего \(P_q\) исключаются из negative draws. Неизвестные будущие интересы остаются возможными false negatives: impressions отсутствуют. Повторная реальная покупка отличается от полного дубля события; set-target схлопывает повтор товара только внутри своего горизонта. Батчи соседних overlapping anchors одного пользователя создают дополнительные коллизии.

Официальный [TensorFlow sampled_softmax_loss](https://www.tensorflow.org/api_docs/python/tf/nn/sampled_softmax_loss) принимает expected counts sampler и удаляет accidental hits; default log-uniform не соответствует частотам произвольных product IDs. [Текущий TFRS code](https://github.com/tensorflow/recommenders/blob/main/tensorflow_recommenders/layers/loss.py) вычитает переданный log-probability: API не проверяет корректность sampler. [RecSys 2025 logQ paper](https://arxiv.org/html/2507.09331v1) уточняет детерминированный positive, но использует приближение correction для смешанных negatives; промышленный индекс дополнен test positives. Эту оценочную процедуру здесь не переносить.

## Ресурсы, приоритеты и проверка

Инженерные оценки float32: таблица 166794×64 — 40,7 MiB; weights+gradient+два Adam states — около 163 MiB. Logits B=256 по всему месячному максимуму каталога — 163 MiB, по 500 кандидатам — 0,49 MiB; in-batch B² — 0,25 MiB. Но 256×50×166794 позиционных logits требуют 7,95 GiB **только logits**. На 8GB RTX3070 last-anchor full softmax малого encoder потенциально реалистичен; позиционный вариант требует sampled/chunked denominator и замера peak memory. На 32GB RAM истории подавать по anchors, позиционные logits месяца не материализовать. Оценки не гарантируют время или вместимость обучения.

- **P0:** exact candidate-softmax; logsumexp, query normalization, empty-support/zero-positive guards; all-positive запрос не дает различения релевантности, sampler пропустить. Encoder, vocabulary, priors и sampler fit до downstream anchors, freeze либо forward snapshots; одного history<t недостаточно.
- **P1 / HYP057:** full против uniform sampled на тех же Q/Y/C и pooled encoder; K=256, затем 1024 только при оправданной стоимости.
- **P1 / HYP058:** при том же K сравнить uniform с 50/50 in-batch+uniform; correction on/off только при проверенной law. P2 — новая logQ formulation, hard negatives, temperature search.

Предлагаемый бюджет: максимум четыре основных конфигурации, один seed, до трех epochs и двух GPU-часов каждая; два лучших повторить вторым seed. Сравнить качество, peak memory, wall time и конечный прирост над тем же сильным CatBoost. Оценивать полный C и полный Y, без sampled-eval shortcuts; их несопоставимость показана [Krichene & Rendle](https://research.google/pubs/on-sampled-metrics-for-item-recommendation/). Проверить разницу основной метрики bootstrap по пользователям и по дням; заранее задать практически значимый порог. Остановить ветку без устойчивого прироста. Главная развилка — набор покупок зрелого горизонта либо следующий товар; loss ее не решает.
