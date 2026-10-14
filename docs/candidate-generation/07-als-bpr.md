# 07. ALS/BPR: факторный retrieval и обновляемая история

15 октября 2026. Независимое исследование; модели не обучались, пакеты не устанавливались. Рекомендация: **P1 ALS после дешёвого MVP**, BPR — следующий контроль. Общая размерность пользовательского и товарного векторов здесь обеспечена совместным обучением.

## Факты и границы

Полный October содержит 3 022 290 пользователей и 166 794 товара; последнее число нельзя превращать в ранний каталог. `U(t)` — товары, наблюдавшиеся строго до `t`, proxy известности, без доказательства наличия на складе. Реализованный [candidate pilot](../experiments/candidate-pilot.md) popular200+recent20 дал 92/121 retrieved targets на 6000 development query-days; ALS/BPR в нём отсутствуют. Текущие зависимости проекта также не содержат `implicit`. Target/split окончательно не приняты.

[Hu–Koren–Volinsky](https://yifanhu.net/PUB/cf.pdf) разделяют бинарное предпочтение `p_ui` и уверенность `c_ui`, минимизируя `Σ_ui c_ui(p_ui−x_uᵀy_i)² + λ(Σ_u‖x_u‖²+Σ_i‖y_i‖²)`. Ненаблюдавшиеся пары имеют малую уверенность, но не являются подтверждёнными отказами. ALS учитывает их аналитически, без materialized user×item таблицы и sampled negatives. Это модельная гипотеза, не калиброванная вероятность покупки.

[BPR](https://arxiv.org/pdf/1205.2618) оптимизирует `−Σ_(u,i,j) log σ(s_ui−s_uj)+λ‖Θ‖²`, где `i` наблюдался, `j` не наблюдался у пользователя в training support. Pairwise цель ближе к порядку товаров, но сама не обещает лучший Recall@K. При обучении на просмотрах обе модели преимущественно учат интерес к просмотрам; покупочный retrieval требует отдельной проверки.

## Предлагаемый ALS-протокол

Один warmup snapshot заканчивается в `s`, до самого раннего downstream training anchor. Матрица строится из `[max(October1,s−7d),s)`, UTC. Grain входа — `(user,item,event_type,UTC_date)` с бинарным присутствием; затем `r_ui=Σ_e w_e n_days(ui,e)`. Начальный контроль `w_view=w_cart=w_purchase=1`; purchase-emphasis `(1,3,5)` — отдельная абляция, числа не оптимальны. Так точные дубли и многократные обновления страницы внутри дня не умножают confidence; повторная активность в разные дни сохраняется. `p=1[r>0]`, `c=1+a log(1+r)`; `a,λ` выбираются только на development validation. В CSR передавать именно положительные `c`, при библиотечном `alpha=1`, поскольку [реализация 0.7.3](https://raw.githubusercontent.com/benfred/implicit/v0.7.3/implicit/cpu/als.py) масштабирует весь переданный confidence.

Все fit-товары принадлежат `U(s)`; пустые столбцы исключаются из retrieval support. Модель ретроспективно рассматривает неизвестные пары в этом snapshot; она не утверждает, что каждый товар существовал в момент каждого старого события. Если нужна именно contemporaneous negative eligibility, обычная snapshot ALS этого не обеспечивает.

ID mapping, веса, параметры и завершённый fit должны быть доступны до anchors: записать `fit_cutoff` и `available_at`. Fit на конце boosting train недопустим для его ранних строк. Для validation/test заморозить `Y`; глобальные группы одинакового timestamp сначала обслуживаются целиком, затем обновляется история. Использовать только события `<t`, включая события других пользователей при любых обновлениях состояния.

Профиль нового или существующего пользователя пересчитывается из `[max(October1,t−7d),t)` по тому же confidence: `x_u(t)=(YᵀC_uY+λI)⁻¹YᵀC_up_u`. Это fold-in, а не среднее item-векторов; [официальный ALS API](https://benfred.github.io/implicit/api/models/cpu/als.html) предоставляет `recalculate_user` без сохранения факторов. У пользователя может не быть training ID. OOV-события не входят в solve; сохраняются `history_OOV_fraction`, число поддержанных товаров, признак пустого профиля.

Retrieval: `TopL_{i∈U(t)∩support(Y)} x_u(t)ᵀy_i`, например `L=100`, tie по product_id. Начать с exact dot search; cosine меняет порядок через item norms и является отдельным экспериментом. Отключить библиотечный `filter_already_liked_items=True`: повторные покупки допустимы. Новые товары после `s` обслуживают recent/popular/category fallback; переобучение либо `partial_fit_items` означают новый versioned snapshot, а не незаметное расширение frozen модели.

## Почему BPR позже

В [CPU BPR 0.7.3](https://raw.githubusercontent.com/benfred/implicit/v0.7.3/implicit/cpu/bpr.pyx) CSR weights игнорируются; после агрегации положительные пары бинарны. Negative item выбирается через случайную позицию interaction-index, то есть частотно по числу user–item пар, затем при `verify_negative_samples=True` уже положительная пара пропускается. Это не uniform catalog sampler. Support ограничить past snapshot, не полным October; будущие positives из evaluation не читать. Такие negatives — неизвестные товары, не dislikes; snapshot sampler также не проверяет доступность на timestamp исходного positive.

Та же реализация добавляет item bias: retrieval score содержит его, нельзя выбросить последнюю координату. [Базовый класс](https://raw.githubusercontent.com/benfred/implicit/v0.7.3/implicit/cpu/matrix_factorization_base.py) не реализует BPR `recalculate_user`. Первый контроль: frozen warm-user BPR с fallback для новых пользователей. Обновление `x` SGD при фиксированных `Y,b` возможно отдельной реализацией с past-only sampler; ALS solve или среднее векторов нельзя выдавать за BPR fold-in.

## Стоимость, проверки и гипотезы

Инженерные оценки при `d=64,float32`: полный item table ≈40,7 MiB, user table ≈738 MiB; CSR, transpose, solver workspace и копии добавляются. Exact scoring требует около 10,7 млн multiply-add на query при полном каталоге; batch256 score-buffer ≈163 MiB. Это не benchmark и не доказательство вместимости обучения. Хранить snapshot manifest, CSR и только top-L `(query,item,score,source_rank,model_version)`; ограничить batch/RSS, измерить fit/fold-in/search отдельно.

[MIT license](https://raw.githubusercontent.com/benfred/implicit/v0.7.3/LICENSE); [PyPI 0.7.3](https://pypi.org/project/implicit/0.7.3/) публикует CPython3.12 Windows-amd64 и macOS-arm64 wheels. CPU — проверяемый первый путь для Windows32GB/3070 и MacM3. [Versioned README](https://raw.githubusercontent.com/benfred/implicit/v0.7.3/README.md) обещает GPU wheels только Linux, CUDA13/RMM; Windows CUDA и Mac MPS не предполагать работающими без отдельной проверки.

- **HYP-073, retrieval:** равный общий budget recent+popular против замены части popular на ALS; сравнить marginal hits, all-target Recall, new-pair/cold/short-history slices, downstream NDCG и стоимость. Расширенная union — отдельный budget experiment.
- **HYP-074, features:** фиксировать прежний C и добавить ALS score/missing/support к тому же ranker. Рост coverage нельзя приписывать этой абляции.
- Проверить пять случаев: пустая/OOV-only история → fallback; новый item → coverage miss; timestamp peers → исключены; повторно купленный item → сохранён; отсутствующая будущая покупка → query сохранён по общей метрической политике.


## Coordinator integration appendix — 15 октября 2026

HYP073 — отдельный retrieval mechanism, needs-pilot с новой reviewed equal-budget config; текущий004 не меняется. HYP074 generic ALS fixed-C score дублирует existing HYP051/056 family, rejected-as-duplicate с сохранением ID. Новый API/source факт implicit0.7.3 не разрешает установку автоматически. Snapshot negative semantics отличаются от contemporaneous eligibility; полную October карту не подставлять в ранние anchors.
