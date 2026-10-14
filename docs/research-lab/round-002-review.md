# Round 002: независимая критика формул, контроля и execution budget

15 октября 2026. Проверены [round 002](round-002.md), [round 001](round-001.md), [его review](round-001-review.md), [canonical backlog](../backlog.md) и переданная проверенная выписка требований Task1. Выполнена только документационная/primary-source проверка; код, tests, данные, Git, dependencies и Root implementation не затрагивались.

**Вердикт:** принять исследовательскую записку вместе с этим appendix. HYP-045 — `needs-pilot`, допустим bounded semantic/cost MVP после upstream gates; quality promotion требует исправления контроля ниже. HYP-046 — `needs-pilot` как execution gate той же ветви, без собственных fits/columns; speedup promotion требует симметричного timing protocol. Доказанного gain или speedup нет. Очередь и общий бюджет не расширять.

## Проверенные первичные основания

1. **OneBM:** авторы/название/2017 совпадают. §III-A3 действительно различает коллекции, §III-A4 явно ограничивает данные prediction cutoff; §IV описывает общий cache и canonical equivalent paths. §IV-C усекать joins разрешает как sampling-оптимизацию, а не теорему сохранения exact values. Round правильно не переносит это усечение в точную семантику нашего оператора. [Авторский текст, §§III–IV](https://arxiv.org/html/1706.00327v1).

2. **RelBench:** официальный NeurIPS-2024 источник и авторский PDF соответствуют названию/авторству. В §4 recommendation baselines включают popularity, past visit, LightGBM; expert feature-engineering study вынесен в §5, temporal sampling описан отдельно. Это не эксперименты нашей grammar/fixed-C NDCG. Round корректно ограничивает вывод. [Авторский PDF](https://cs.stanford.edu/people/jure/pubs/relbench-neurips24.pdf), [официальное издание](https://proceedings.neurips.cc/paper_files/paper/2024/hash/25cd345233c65fac1fec0ce61d0f7836-Abstract-Datasets_and_Benchmarks_Track.html).

3. **F-IVM:** название и четыре автора совпадают; arXiv history подтверждает v1 2023/v2 2024. Factorized maintenance и ring payloads действительно связывают joins/aggregates/statistics. Авторская страница описывает разделяемые view trees; это не лицензия считать max/distinct обратимыми scalar sums. [Версии и первичный текст](https://arxiv.org/abs/2303.08583), [авторский проект](https://fdbresearch.github.io/ivm.html).

4. **Provenance for Aggregate Queries:** авторы/2011 подтверждены. Статья распространяет provenance на computed aggregate values и отдельно рассматривает nested queries; происхождение самого output tuple не заменяет происхождение его содержимого. У round нет обещания готового temporal checker или необходимости symbolic polynomials на всём REES46. [Авторский PDF, §§3–4](https://arxiv.org/pdf/1101.1110).

Существенного source-fidelity дефекта в этих четырёх основаниях не найдено. Их технические идеи поддерживают дизайн, не доказывают качество или стоимость нашего MVP.

## Material finding 1: confirmation-контроль не закрывает заявленное сравнение с B

В общем контракте control — существующий сильно настроенный manual B. Но HYP-045 выбирает treatment относительно `B+S` и разрешает confirmation только против `B+S`. Эти критерии не эквивалентны. Воспроизводимый контрпример: NDCG(B)=0,100; NDCG(B+S)=0,090; NDCG(B+T+S)=0,093. Treatment проходит предложенный Δ≥0,002 против B+S и может иметь узкий положительный paired CI, оставаясь хуже исходного tuned manual B.

**Минимальный fix без новых fits:** заранее назначить основным confirmation-контролем уже frozen B; contrasts с B+S использовать для selection/mechanism diagnostics. Если требуется и дополнительный guard против B+S, объявить его до confirmation вместе с claim hierarchy. Не выбирать control по 24–25 октября. Сравнение с исходным B не требует переобучения: его scores на тех же Q/C/Y уже часть зафиксированного эксперимента. Позитивный treatment-vs-support-only результат иначе называется только этим локальным результатом, без утверждения выполнения основного Task1-сравнения.

Reservation исправлена относительно round001: 24–25 заранее закрыты для baseline/loss/блоков/grammar/thresholds, histories продолжают поступать по policy, weights/refit — нет. Эта защита должна применяться и к будущему bounded tuning B. Условная календарная запись не доказывает reservation фактически; один использованный confirmation нельзя отдавать следующему round.

## Material finding 2: однократная пара timing runs не идентифицирует DAG speedup

HYP-046 задаёт ≥20% CPU improvement, но не фиксирует равенство cache/setup и порядок измерений. Naive cold scan против shared plan после прогрева, либо naive с повторным input loading против shared с готовыми intermediates, способны пройти порог без преимущества общего вычислительного плана. Простое равенство 11 output columns этого не исключает.

**Минимальный fix внутри тех же ≤20 минут:** объявить одинаковый input boundary, что включается в preparation/compile/materialization, cold/warm policy и симметричный порядок. Выполнить несколько коротких пар с заранее чередуемым порядком, если они помещаются в cap; сравнивать declared summary paired CPU и RSS. Если ресурс не позволяет отделить эффект от order/cache, semantic equality можно принять, speedup оставить `inconclusive/needs-pilot`. Не выдавать единственную выгодную пару за подтверждение ≥20%; не добавлять новый benchmark budget или бесконечные repeats.

## Принятые формулы, grain и обязательные границы MVP

HYP-045 — содержательное refinement HYP-002, а не дубликат HYP-011. U — уже известный unconditioned reference; T добавляет связывание candidate category внутри user-history aggregate. Четыре T/четыре U/три S дают 11 новых scalar columns; G переиспользует ту же восьмёрку и не открывает новый search space. HYP-046 задаёт equivalence/cost нескольких программ в одном плане, тогда как round001 лишь дедуплицирует AST. Это инженерный вопрос автоматизации, не отдельная гипотеза ranking gain.

Точный grain reference — `(u,category,t,A,W)`: он одинаков для всех кандидатов одной категории. Поэтому standalone T сохраняет popularity ordering **внутри категории**, меняя межкатегорийный offset; общая отметка candidate-conditioned не доказывает индивидуальную item compatibility. При единственной категории T=U. Такие fixtures обязательны и помогают честно объяснить отрицательный результат.

Перед compiler/oracle зафиксировать: V — global raw view count с данным W; D — distinct products, не view multiset; category истории — последняя user-view секунда в 7d, category кандидата — последняя глобальная strict-past секунда. Это две намеренно разные as-of policies, их нельзя незаметно унифицировать optimizer rewrite. Для ambiguous/NULL history category явно определить exclusion-versus-unavailable-reference policy и S flag; для unavailable candidate category T остаётся missing, без fallback U. Known-category empty reference — missing со support0.

Требуемые semantic fixtures: duplicate views не перевзвешивают mean; latest-second metadata conflict не разрешается row-order; category move сохраняет historical assignment; чужое global view меняет V_j на следующем t без нового user event; expiry, t−W/t boundaries, peers/future suffix; две one-to-many ветви не размножают membership/support. Global popularity не ограничивается candidate products или sampled users. Cache identity содержит полный AST/policy/input/cutoff; equality masks/integers точная, floats — заявленный tolerance. Эти требования уточняют существующий опыт, не добавляют features.

## Budget, fitted state и переносимость

Четыре fits — B+S/U/T/G, максимум; новый fit/tuning B внутри016, failed attempts, oracle, naive/shared evaluation и confirmation scoring расходуют **тот же** остаток12 columns/4 fits/2 CPUh. CPU определён суммарно по процессам; wall cap120min отдельный. Узлы кэша не считаются бесплатными вычислениями. После semantic/cost failure quality fits не запускаются; нужен честный deferred/inconclusive, а не новые окна/seeds.

Операторы здесь не содержат learned priors/encoders, но B/preprocessing обязаны иметь доступные до downstream anchors versions; train-only selection не разрешает backward-injection fitted features. Fixed C, полный Y и external evaluator неизменны. One seed и два confirmation-дня дают локальный case study, не превосходство стратегии вообще.

UCI ограничение корректно: invoice line/invoice/unit различаются; HYP-045 category predicate отсутствует и не заменяется Country. As-of cancellation/description и missing users остаются будущими adapter gates. Schema-only compile HYP-046 подтверждает структуру, не recommendation gain; новое скачивание/обучение этим review не требуется. [Официальная UCI схема/лицензия](https://archive.ics.uci.edu/dataset/352/online%2Bretail).
