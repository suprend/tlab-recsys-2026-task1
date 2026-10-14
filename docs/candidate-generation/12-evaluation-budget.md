# 12. Оценка кандидатогенерации и бюджет: отделить потолок retrieval от качества ranker

15 октября 2026. Независимая исследовательская записка; новые записки других агентов не читались. Реальные модели не обучались. Ниже факты проекта, методологические основания и предложения отделены явно.

## Фактическая отправная точка

Принятый TLAB-004 создаёт до 200 популярных по distinct purchase users товаров плюс до 20 последних distinct user-items, с past-only окнами и без refill после дедупликации. В принятом B-пилоте: 6 000 Q, 121 target, 92 найденных target, 1 226 268 фактических candidate rows; positive-query macro Recall=0,78365. Pooled Recall=92/121≈0,76033 — другой estimand. Это измерение конкретного пилота, не оптимальность 200+20 и не качество будущей модели. [Локальное evidence](../backlog-reviews/tlab-004-verification.md).

Последний переданный координатором source-verified статус TLAB-017: train 26 000 Q / 619 targets / 444 retrieved, selection 4 000 Q / 96 targets / 65 retrieved. Полная F-collection ещё не принята, real fits закрыты. Эти более поздние counts не заменяют accepted B evidence автоматически; перед использованием нужны закреплённые artifact hashes и collection acceptance. Сильный ручной boosting и автоматизация TLAB-016 остаются главным сравнением task1; расширение retrieval — отдельная возможная ветвь.

## Предлагаемый контракт измерения

Query q=(user,t) берётся из одного заранее выбранного past-eligible Q. Полный distinct purchase-set Yq задаётся horizon/endpoints принятого протокола независимо от candidates. Uq={items:first_seen<t} — наблюдавшийся каталог, не stock. История всех пользователей, metadata, fitted weights и доступность snapshot должны предшествовать t; peers той же секунды исключаются глобально. Последовательность «fit на конце train, затем признаки ранних train rows» этому условию не соответствует. Влияние нарушения общей временной шкалы показано в [Ji et al.](https://arxiv.org/abs/2010.11060).

Для заданного правила источников строится Cq(B)⊆Uq с заявленными quotas, deterministic ties, dedup и truncation. Основная retrieval-метрика на Q+={q:|Yq|>0}: Rq(B)=|Yq∩Cq(B)|/|Yq|. Рядом публикуются:

- positive-query macro: среднее Rq по Q+;
- pooled/micro: Σhits/Σ|Yq|;
- user-macro: сначала среднее query-метрик внутри пользователя, затем среднее пользователей; conditional и all-query версии маркируются отдельно;
- support coverage Σ|Yq∩Uq|/Σ|Yq| и in-support Recall=Σhits/Σ|Yq∩Uq|. При ненулевых знаменателях их произведение равно pooled all-target Recall, но такого равенства для средних query-ratios обычно нет.

Зрелые zero-purchase queries сохраняются. Их Recall математически неопределён; для отдельной операционной all-query сводки явно назначается ноль и публикуется p(Q+). Тогда all-query macro=p(Q+)×conditional macro. Это конвенция отчётности, не доказательство плохих рекомендаций покупателю без покупки. Незрелые queries исключаются из label-метрик с отдельным count, не превращаются в нули. Missing/OOV item остаётся miss полного Y; in-support query без supported targets не получает искусственную единицу.

Предлагаемые slices: UTC day; history support 1/2–5/>5 distinct items; repeat/new user-item; cold target вне U; head/tail по замороженному past purchase support. Для каждой строки нужны Q/Q+/users/targets/hits: малое число покупок не позволяет считать стабильным каждый slice. Парный user-cluster bootstrap пересчитывает выбранный estimand; дневные результаты показывают временную нестабильность. Ни CI, ни дополнительные folds не исправляют выбор победителя после многократного просмотра holdout.

## Бюджетная кривая и абляции

P0: воспроизвести accepted 200+20 и popularity-only/recent-only без нового fit. P1, после отдельного разрешения изменения протокола: сравнить, например, popularity quotas 100/200/400 при неизменном recent20, затем одну альтернативную source-конфигурацию при том же максимальном общем B=220. Это предложения, не уже одобренная сетка. Публиковать actual |Cq| min/median/p95/max и total, а также новые hits G=|Y∩(Cnew\Cold)| и потерянные L=|Y∩(Cold\Cnew)|; при cap новая source может вытеснить полезные items. Для nested budgets требуется сохранять общий ordering, иначе Recall не обязан монотонно расти.

Ранжировочные Recall/NDCG@20 используют полный Y и полный IDCG, включая отсутствующие candidates. Feature-ablation сравнивает manual baseline и автоматизацию на одном fixed C; retrieval-ablation меняет C и отдельно сообщает coverage и downstream ranking. ANN Recall против exact top-B того же score-space — проверка приближения поиска, отдельная от purchase Recall. [Faiss](https://github.com/facebookresearch/faiss/wiki/Guidelines-to-choose-an-index) определяет Flat как exact reference без обучения индекса.

Обучающие negatives описываются распределением, размером и dedup; unobserved не означает dislike. Смена sampler меняет обучающую задачу, поэтому её нельзя одновременно приписывать новой source/feature. BPR — конкретный pairwise objective со sampling, а не универсальное обоснование отрицательности всех отсутствующих покупок. [Оригинальная работа](https://arxiv.org/abs/1205.2618). Для eval нельзя добавлять будущие positives к случайной подвыборке каталога и называть результат catalog Recall/NDCG: sampled metrics способны менять порядок моделей даже в ожидании. [Krichene–Rendle](https://research.google/pubs/on-sampled-metrics-for-item-recommendation/). Дешевле уменьшить Q до labels независимым sampling, сохранив весь доступный ranking universe.

## Стоимость, остановка и пограничные случаи

Предложенный MVP ledger: source scan/state build, refresh/index, retrieval, union, feature export, fit, scoring, evaluation; wall/CPU time, peak process RSS, engine memory/spill, disk bytes, scanned/output rows, preparation и failed attempts. Ограничение output B не ограничивает построение ItemCF: попарная работа зависит от Σm² внутри user/session-групп до truncation.

Предлагаемый новый retrieval-пилот: сначала 100 неизменных queries, затем максимум accepted 6 000; 2 потока, engine memory 2 GB, RSS ceiling 6 GB, 30 минут, partial report при stop. Это ограничения запуска, не benchmark и не разрешение обучения. BLAS/OpenMP также ограничиваются: [Faiss](https://github.com/facebookresearch/faiss/wiki/Threads-and-asynchronous-calls) отдельно использует OpenMP и BLAS. Для exact d=128 верхняя арифметика на итоговых 166 794 float32-векторах — около 85,4 MB, без служебных структур; ранний U меньше, скорость неизвестна.

Stop: нарушение времени/lineage, cap, RSS или deadline; повторный новый источник без положительного net hits на заранее выбранном screening; невозможность завершить selection decision до confirmation. Например, минимальный practically useful gain 0,5 п.п. можно согласовать заранее, но текущих редких positives недостаточно для обещания его обнаружить. Confirmation остаётся закрытым до положительного decision-compute gap и frozen claim/control. Edge cases для oracle: пустой C; zero Y; холодная покупка; повтор ранее купленного; overlap источников с недобором. Новая оценочная методика здесь не заявлена: HYP-089/090 следует оставить reserved.


## Coordinator current-status appendix — 15 октября 2026

Исходный source-verified handoff выше сохранён исторически. Теперь [017collectionsourceaudit](../backlog-reviews/tlab017-collection-verification.md) принял обе immutable train/selection collections после allQ/Y/C source reconstruction и1620numericfeaturechecks; это не realmodelfit/strongbaselineclaim. Finalreview [09–12](review-09-12.md) подтверждает раздельные fullY/support/ANNdenominators и cap/refillcost boundaries.089/090reserved, validation невыдаётсязановуюresearchnovelty.
