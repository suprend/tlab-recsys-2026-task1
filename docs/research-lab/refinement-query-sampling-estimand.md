# Bottom-hash daily Q: sample contrast и population contrast

15 октября2026. **Точный вывод: current macro-query описывает фиксированные sampled query-days; одинаковый cap2000 не даёт автоматически оценку всех eligible user-days или среднего unique active user.** Это refinement существующих report/evaluation obligations, без новой HYP. Сверены [round019](../research-lab/round-019.md), [round072](../research-lab/round-072.md), bootstrap-claims note, [query builder](../../scripts/anchor_pilot.py), [reserved source](../../scripts/heldout_source.py) и [evaluator006](../../scripts/ranking_metrics.py). Actual DB/Y/scores/models, bootstrap/fit/jobs не открывались/не исполнялись; frozen015/016 не менялись.

## Что действительно отбирается

`create_queries` сначала строит distinct eligible user population по past-only action history, затем сортирует SHA256 ASCII `sample|seed|anchor|user_id`, с user_id tie-break, и берёт не более2000. В015 eligibility — зарегистрированная view/cart/purchase activity за48h до UTC daily anchor; query-time peers исключены. Это не sample всех visitors, всех accounts, всех purchase sessions или всех impression opportunities. Sampling предшествует query-level labels. Global positive fullY вне C остаётся evaluator denominator; emptyC не удаляет Q.

Код уже возвращает daily eligible count и sampled count; `heldout_source.build_day` сохраняет `eligible_user_count`. Здесь реальные значения не прочитаны. Само наличие counter в source code не означает, что внешний итоговый report уже аутентифицировал/показал его.

[Cohen–Kaplan, PODC2007, author PDF](https://www.math.tau.ac.il/~haimk/papers/p225-cohen.pdf) определяет bottom-k через smallest independent random ranks; uniform-weight ranks задают случайную перестановку. Наша SHA256 с фиксированным seed — воспроизводимый deterministic ordering. Его можно интерпретировать как random-rank approximation, но это **модельное предположение**, не доказательство независимости rank/outcome и не реально повторённый randomization experiment. Не следует подменять этой литературой обещание exact design-based coverage для одного фиксированного hash realization.

## Почему daily cap меняет объединённый estimand

Обозначим N_d число eligible users дня, n_d=min(2000,N_d). **Под идеализированной uniform-rank моделью** inclusion probability отдельного user-day равна π_d=n_d/N_d. Она одинакова внутри дня, но различна между днями. Без такой модели fixed sample имеет выбранные/невыбранные rows, а не эмпирически проверенные probability weights.

[Statistics Canada, официальный Survey Methods and Practices, §§7.1.1–7.1.2](https://www150.statcan.gc.ca/n1/en/pub/12-587-x/12-587-x2003001-eng.pdf) различает self-weighting designs и inverse inclusion weights: proportional stratum allocation сохраняет одинаковую sampling fraction, равные absolute sample sizes при разных population sizes — нет. Это основание отличать weighted population estimate от unweighted sample mean, не требование переделать наш benchmark.

Для δ_q=metric_W−metric_B и z_q=1{mature positive fullY} current conditional contrast:

`Δsample = Σ_(q∈sample) z_q δ_q / Σ_(q∈sample) z_q`.

Следовательно, день получает вес по **sampled positive queries**, а не обязательно1/D. Даже если каждый день имеет2000Q, conditional pooled mean не equal-day average дневных conditional means. Для all-query-zero pooled mean при одинаковых n_d равен equal-day average, если все соответствующие Q mature; при n_d<2000 это уже не так.

Для future population-conditional question естественный inverse-probability ratio:

`Δpop_hat = [Σ z_q δ_q / π_d] / [Σ z_q / π_d]`.

Это ratio estimated totals, **не автоматически unbiased finite-sample ratio**. Вес только N_d при разном n_d неверен; population-positive denominator нельзя заменить общим eligible count. Редкие positives делают denominator/variance особенно чувствительными. Нынешний frozen006 этот weighted estimand не вычисляет.

## Два аналитических предостережения

Сконструированные day-level числа, не измерение REES46: N_A=2000, N_B=20000, n_A=n_B=2000; все toy queries positive, средний δ_A=+0,10, δ_B=−0,02. Тогда sample/equal-day contrast +0,04, population-user-day contrast `(2000×0,10−20000×0,02)/22000≈−0,00909`. Знак меняется без ошибки ranking code. Это иллюстрирует разные вопросы, не предсказывает настоящий weighted result.

User-macro тоже требует осторожности. При идеализированных независимых дневных draws пользователь, eligible в днях D_u, попадает хотя бы раз с вероятностью `1−Π_(d∈D_u)(1−π_d)`. Она выше при большем числе eligible дней. Поэтому unweighted user-macro по union sampled users не является автоматически равновероятным user-macro всех уникальных eligible пользователей. Более того, observed sampled days пользователя — не все его eligible days. Формула — наша аналитическая иллюстрация при объявленных assumptions, не установленное свойство независимости SHA между днями.

## Что user bootstrap исправляет и чего не исправляет

Current paired bootstrap переносит все **наблюдённые** query-days выбранного пользователя вместе и использует одну multiplicity для B/W. Он сохраняет query/user estimand; не добавляет несэмплированных пользователей, missing days или inverse-probability weights. [Cameron–Miller, author cluster-inference review](https://faculty.econ.ucdavis.edu/faculty/cameron/research/Cameron_Miller_JHR_2014_July_09.pdf) требует assumptions о dependence внутри и independence между clusters, отдельно рассматривает multiway dependence. Это не survey-design theorem для нашего sparse ranking ratio.

Таким resampling нельзя автоматически исправить unequal day fractions, eligibility/observability selection, общие date shocks или postselection feedback. При полном census одного дня sampling variance для фиксированной finite population отсутствует, а superpopulation user-bootstrap всё ещё может показывать вариацию: это разные uncertainty questions. Прежние019/072 уже покрывают repeated-user dependence и selection-only CI; новый материал здесь — связать их с daily sampling frame/weights, не переписать CI после результата.

## Конкретный report/backlog action

В существующем TLAB-015/итоговом отчёте достаточно одного уточнения:

> «Метрики относятся к фиксированным daily bottom-SHA samples до2000 eligible48h users/day на указанных датах. Primary conditional full-Y mean усредняет положительные sampled query-days. Он не взвешен на размеры всех дневных eligible populations; user-cluster interval не является автоматической поправкой на sampling design или новые дни».

При наличии уже принятой aggregate evidence показать N_d/n_d и positive/mature support, без дополнительного source scan сейчас. Future equal-day versus population-user-day sensitivity имеет смысл только как заранее отдельно разрешённый estimand/weighting study: одна зафиксированная пара B/W, одинаковые Q/C/fullY, published weights/undefined rules, без выбора удобного headline/CI по знаку. Новый bootstrap не обязателен для честной сдачи и здесь не авторизован; он не создаёт новых дат. Новых fits, looks, mandatory task или HYP не предлагается.

## Publication boundary

Archived15October2026 as a refinement of existing hypotheses, not a new independent idea round or an execution allowance. The original research result is retained; subsequent code/review progress does not retroactively change its historical snapshot. No actual source/model/target/fit job was run for this note.
