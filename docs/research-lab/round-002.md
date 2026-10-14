# Research lab, round 002: candidate-conditioned программы и стоимость реляционной автоматизации

15 октября 2026. Literature/generalization round, отдельный от 58 тематических записок. **Результат — проект эксперимента, не измеренное улучшение.** Прочитаны [backlog](../backlog.md), [round 001](round-001.md), его [review](round-001-review.md), feature synthesis и user–item profiles/audience. Статусы ниже предлагаются координатору; только он изменяет canonical backlog. Repo, Git, код, dependencies и raw не изменялись; модели и архивы не скачивались, обучения/API-вызовов нет.

## Четыре первичных основания

**1. Hoang Thanh Lam, Johann-Michael Thiebaut, Mathieu Sinn, Bei Chen, Tiep Mai, Oznur Alkan, 2017, One button machine for automating feature engineering in relational databases.** OneBM различает типы коллекций после join: multiset, sequence, time series; выбирает преобразования по типу, ограничивает глубину, кэширует общие префиксы и удаляет эквивалентные пути. Раздел III-A4 прямо предусматривает prediction cutoff. Однако усечение большого join до последних строк меняет вычисляемый объект; эту оптимизацию нельзя выдавать за точный оператор. Источник поддерживает typed relational generation, но не доказывает superiority при нашем CPU budget или ranking estimand. [Авторский текст, разделы III–V](https://arxiv.org/html/1706.00327v1).

**2. Joshua Robinson et al., 2024, RelBench: A Benchmark for Deep Learning on Relational Databases, NeurIPS Datasets and Benchmarks.** Временные predictive tasks, связи primary/foreign key и temporal neighbor sampling полезны как ориентир контракта. Рекомендационные таблицы сравнивают GNN с popularity/past-visit/LightGBM; экспертный feature-engineering user study описан отдельно. Это результаты конкретных моделей и задач, а не доказательство качества нашего search DSL. Не следует переносить ни опубликованные MAP, ни выигрыш GNN на NDCG нашего fixed-C ranking. [Первичный PDF, §§3–5](https://cs.stanford.edu/people/jure/pubs/relbench-neurips24.pdf), [официальное издание](https://proceedings.neurips.cc/paper_files/paper/2024/hash/25cd345233c65fac1fec0ce61d0f7836-Abstract-Datasets_and_Benchmarks_Track.html).

**3. Ahmet Kara, Milos Nikolic, Dan Olteanu, Haozhe Zhang, F-IVM: Analytics over Relational Databases under Updates, препринт 2023, версия 2024.** Работа сочетает факторизацию, incremental view maintenance и ring payloads для joins/aggregates и статистик обучения. Из неё следует возможность разделять промежуточные вычисления, а не гарантированный speedup любого generated feature. Особенно нельзя переносить обратимость sum на rolling max/median/distinct: expiration требует собственного состояния. Наш pilot заимствует принцип, не устанавливает F-IVM/DBToaster. [Авторский PDF](https://arxiv.org/pdf/2303.08583), [авторская страница проекта](https://fdbresearch.github.io/ivm.html).

**4. Yael Amsterdamer, Daniel Deutch, Val Tannen, 2011, Provenance for Aggregate Queries.** Авторы показывают, почему tuple-level аннотаций недостаточно для общей агрегации, и описывают provenance вычисленных значений. Это основание фиксировать происхождение scalar и его знаменателя; оно не является готовым temporal checker. Полные symbolic polynomials для всех реальных строк здесь не предлагаются. [Первичный PDF](https://arxiv.org/pdf/1101.1110).

## Общее решение и ledger

**Предложение:** DSL хранит grain, ключи, unit, event family, set/multiset, окно, metadata policy, cutoff и свободные переменные `{u,i,t}`. При компиляции отмечать `query-constant`, `item-only` и `candidate-conditioned`. Это описания зависимости, не фильтр «бесполезных» features: query-constant может помогать boosting через interactions. Для `p_i−r_u` standalone порядок совпадает с `p_i`; HYP-011 уже честно признаёт этот предел.

Контроль B — существующий **сильно настроенный manual boosting**, с документированными bounded tuning и выбранными ручными блоками. Initial TLAB-008 с двумя fits остаётся smoke. До любых 008/009 fits: selection **22–23 октября**, confirmation **24–25** закрыта для baseline/loss/блоков/grammar/порогов. Fit cutoff, label maturity и available_at согласованы. Final test закрыт; уже раскрытая confirmation не переиспользуется следующим round.

Единственный лимит TLAB-016: **≤12 новых scalar columns, ≤4 fits, ≤2 CPU-часов**, 2 threads, RSS≤8 GiB. Здесь CPU — суммарное user+system всех дочерних процессов; wall time записывается отдельно, дополнительно stop через 120 минут. Preparation, failed runs, repair, oracle, selector и confirmation scoring оплачиваются. HYP-045 **заменяет** G/S/A либо residual ветвь round001, не складывается с ними. Если 016 уже потратил бюджет, сначала пересчитать остаток; четыре новых fits автоматически не разрешены. Новое обучение B внутри 016 тоже уменьшает этот остаток.

## HYP-045 — reference по истории, условной на кандидате

**Статус: needs-pilot, refinement HYP-002/TLAB-016.** Пусть `D_u` — distinct товары view-истории `[t−7d,t)`; каждому принадлежит category_id последнего view этого товара в окне. Конфликт последней секунды означает ambiguous. Candidate category берётся по проверенной as-of политике `<t`. Для `A∈{mean,max}`, `W∈{24h,7d}` генерировать:

`F_A,W(u,i,t)=log1p(V_i,W(t))−A{log1p(V_j,W(t)): j∈D_u, cat_j=cat_i(t)}`.

Все вложенные popularity states используют один t, не конец месяца. Набор четыре conditional программы T; четыре аналога U без category predicate уже соответствуют HYP-011. Это автоматическое связывание candidate key внутри вложенной агрегации, а не новая ручная сетка counts.

**Новизна:** user→past items→global item state→candidate-keyed reference отсутствует в HYP-011. Category share/manual-18 и HYP-029 conditional price не агрегируют текущую popularity прошлых товаров; ItemCF/HYP-001 и audience prototypes используют другую связь. Приписывать академическую новизну не требуется. **Counterhypothesis:** узкие category histories нестабильны; выигрыш объясняется support/category mix либо взаимодействиями, уже доступными B. При единственной категории T вырождается в U; type annotation не гарантирует фактическую вариативность внутри query.

**Inputs:** past views, exact category_id, versioned metadata, фиксированные Q/Y/C и B. Пустой reference — missing, без скрытого fallback. Общие S: distinct matched-history count, candidate-category availability и empty/ambiguous-reference flag. Итого восемь программ плюс три supports/masks = **11 columns**; существующие поддержки не дублировать.

**Минимальный опыт:** четыре новых fits с одинаковыми настройками/seed B: `B+S`, `B+U+S`, `B+T+S`, `B+G+S`; G — четыре программы равномерно без возвращения из восьмёрки, seed фиксируется до labels. Кэш совпадений не пополняет attempts. Сначала independent tiny SQL oracle, затем 100 label-independent queries и ≤30 минут materialization; fixed C не расширяется. Published one-seed comparison — case study, не превосходство стратегии поиска вообще.

Primary conditional macro-query NDCG@20 с полным Y; secondary Recall@20, all-query/user-macro, support, repeat/novel, missing metadata, каждый день и cost. Заранее правило selection: выбирается один treatment относительно B+S. Если выбран T, confirmatory claim — только его frozen comparison с B+S; T−U/T−G остаются selection-only диагностикой механизма. Для подтверждения именно conditioning нужен отдельный заранее закрытый контрольный блок, без повторного открытия 24–25.

**Accept:** confirmation ΔNDCG≥0,002, paired user-cluster 95% CI выше нуля, ΔRecall≥−0,002, одинаковые candidates/coverage и стоимость≤2×B внутри absolute caps. **Reject:** достоверно отрицательный эффект либо semantic defect; при малом support/неопределённом CI — needs-pilot, при resource exhaustion — deferred. Переносимая часть — candidate-key binding и nested aggregate; view/category semantics REES46 не переносятся автоматически.

## HYP-046 — общий execution DAG сохраняет значения и экономит search

**Статус: needs-pilot, execution gate HYP-045, без дополнительных fits/columns.** Механизм: идентичные typed subexpressions вычисляются один раз; reference кэшируется по `(u,cat,t,A,W)`, global item state — по `(j,t,W)`. В provenance входят AST hash, input/version, multiplicity, support, window, availability и metadata policy. Cache key обязательно содержит полный policy identity; query-constant и candidate-conditioned узлы не сливаются.

**Новизна:** TLAB-001/005 проверяют primitives, round001 дедуплицирует AST; здесь проверяется cost и equivalence **общего плана нескольких программ**, включая недопустимые optimizer rewrites. Это гипотеза эффективности автоматизации, не claim metric gain. **Counterhypothesis:** стоимость global scan/state доминирует, cache только увеличивает память. Изменяющаяся global popularity также не позволяет обновлять все nested references лишь при новых событиях пользователя.

**Опыт:** naive независимое вычисление тех же 11 columns против shared DAG, сначала synthetic fixture с двумя one-to-many ветвями, повтором/expiry distinct, сменой category и глобальными peers, затем те же 100 queries. Проверить equality missing/integers, floats `atol=1e−10, rtol=1e−9`; перестановка peers/future suffix и переименование schema с обратным mapping сохраняют результат. Naive oracle не использует production helpers. Никакой sampling истории и изменения max на approximate не допускается.

**Accept:** ноль semantic mismatches, ≥20% меньше CPU на одинаковом входе, RSS≤1,2×naive и ≤8 GiB. Пороги — **предложения**, speedup не измерен. ≤20 минут общего ledger на эту пару планов; если gate не пройден, сохранить naive bounded execution или deferred, не ремонтировать бесконечно. Отчёт включает source rows scanned, intermediate rows, cache hits, state keys, spill и полный CPU/wall; 100 queries не доказывают стоимость полного скана 42 млн событий.

## Второй dataset: уточнение UCI вместо расширения списка

Оставить **Online Retail**, Daqing Chen, DOI 10.24432/C5BW33. Следующие факты взяты из [официальной карточки UCI](https://archive.ics.uci.edu/dataset/352/online%2Bretail); архив не открыт.

| Свойство | Совместимость и ограничение |
|---|---|
| Лицензия/размер | CC BY 4.0; XLSX 22,6 MB; 541 909 строк |
| Grain/relations | Invoice line; CustomerID–StockCode–InvoiceNo; invoice≠session, quantity≠event count |
| Time/horizon | 01.12.2010–09.12.2011; InvoiceDate date/time; timezone, реальная resolution и подходящий horizon не установлены |
| User/item types | ID категориальные; пропуски/coverage требуют проверки файла, даже при карточке «No missing» |
| Events/negatives | Transactions/cancellations; views, impressions и exposure negatives в схеме отсутствуют |
| Metadata | Description/UnitPrice/Country; category taxonomy отсутствует; as-of description/price нельзя заменять финальной карточкой |
| Применимые primitives | Strict-past invoice-line/invoice/distinct-item aggregates; unconditioned nested popularity после явного выбора единицы |
| Непереносимые без решения | View/cart grammar и HYP-045 category predicate; Country пользователя не эквивалентна category товара |

Будущий adapter не отменяет старую покупку задним числом по будущей cancellation и не объединяет missing CustomerID в пользователя. Сначала schema-only compile/fixture для HYP-046, затем отдельное решение о download/pilot и бюджете. Компиляция подтверждает лишь структурную совместимость; quality generalization потребует собственного frozen temporal task/control. Не создавать fake category ради положительного portability результата.

**Отклонённые повторы:** ещё один category-price profile дублирует HYP-029/TLAB-013; cohort/audience pooling — существующие notes; «RelBench доказал превосходство нашей автоматизации» не является допустимым выводом. HYP-047…050 остаются свободны. Для Task1 приоритет — измерить автоматизацию против tuned manual, а не накапливать operators без экспериментального результата.


## Coordinator review appendix — 15 октября 2026

[Независимый critic](round-002-review.md) подтвердил первоисточники и нашёл два material design gaps; исходный текст выше сохранён.

1. **Основной confirmation control — frozen tuned B**, а не только B+S. Treatment, который улучшает ухудшенный B+S, может всё ещё проигрывать B. Четыре предложенных fits сохраняются; scoring уже frozen B не требует нового fit и входит в тот же CPU ledger. Selection и единственный primary claim фиксируются до24октября. B+S/T−U/T−G остаются mechanism/selection diagnostics; дополнительный guard против B+S возможен только заранее, без смены control после confirmation. Accept threshold относится к ΔagainstB.
2. **HYP046 timing симметричен.** Оба плана имеют одинаковые input/setup/compile/materialization boundaries; generated outputs очищаются перед каждым run. Source page-cache policy объявляется и одинакова; несколько коротких пар с заранее чередуемым AB/BA порядком сравниваются declared paired summary внутри прежних20минут. Подготовка/warmup/oracles оплачиваются. При недостаточном времени или order/cache ambiguity принять только semantic equality, speedup оставить inconclusive. Не добавлять benchmark budget.
3. Для historical reference latest-view bucket с ambiguous/NULL category исключается из conditional membership, причина отражается S; unavailable candidate category даёт missing T без fallback U. Global V — raw view count по всем пользователям/товарам. Candidate-conditioned reference одинаков внутри категории: standalone порядок popularity внутри неё сохраняется. Это обязательные semantic fixtures, не доказательство персонального rank gain.

HYP045/046 остаются needs-pilot в единственном shared TLAB016 ledger≤12columns/4fits/2CPUh, замещая другую ветвь. Semantic/cost pilot после upstream gates; quality fit только после tunedB/selection reservation. Datasets не скачивались; UCI category predicate не выдумывается.
