# Журнал новых исследовательских идей

Обновлён 15 октября 2026, 05:59 UTC / 08:59 МСК. Этот журнал отделяет новые механизмы от уточнений прежнего backlog. Статус «исследуется» означает текущую работу, а не готовый результат или разрешение эксперимента. Отложенные результаты25–31 остаются закрыты.

## Три независимые линии

| Линия и раунд | Начало в журнале | Вопрос | Результат и статус |
|---|---|---|---|
| Feature/automation, F001 | 15.10.2026 05:22 UTC | Новые группы признаков и методы автоматического поиска, первичные работы2024–2026 | [Draft:4 кандидата](brainstorm-f001.md); [независимый cross-review](brainstorm-f001-review.md) и [решения](brainstorm-f001-review-ledger.json) сданы |
| Retrieval/session, R001 | 15.10.2026 05:22 UTC | Retrieval, сессии, повторные покупки и replenishment | Процесс прерван до сданного draft; завершение не подтверждено |
| Models/loss/transfer, M001 | 15.10.2026 05:22 UTC | Новые learner/objective/transfer механизмы сверх уже записанных ALS, generic boosting и auxiliary heads | [Draft:5 кандидатов](brainstorm-m001.md); [независимый cross-review](brainstorm-m001-review.md) сдан, [решения](brainstorm-m001-review-ledger.json) ниже |

Время в таблице — момент регистрации линий, а не утверждение точного начала каждого агентского процесса. Сданные раунды связаны ниже; независимые cross-reviews будут добавлены после их завершения. В каждом раунде ожидаются3–5 конкретных кандидатов с первичными источниками, доступными входами, контргипотезой, проверкой дублей и самым дешёвым опровергающим опытом. Количество статей и заметок не равно количеству новых гипотез.

## Реестр кандидатов новых раундов

| Кандидат | Связь с existing/new HYP | Решение | Основание |
|---|---|---|---|
| NB-F01 | Candidate-specific pre-purchase context recurrence | Accept-needs-pilot условно | Distinct historical-reference operator; common-window/non-degenerate support gate, редкость прошлого purchase context существенна |
| NB-F02 | Censoring-aware residual waiting-time prior | Defer | До probe нужны exact spell/category/tie/risk/warmup/availability definitions; fitted estimation оплачивается |
| NB-F03 | Action-role-directed category association | Refine | Seed/channel, global adjacent buckets, prefix overflow, self-excluded N и composite contrast ещё надо зафиксировать |
| NB-F04 | Source-only temporal reliability allocation | Refine | Literal unit-scaling counterexample для IQR+1; exact hist/weighting, coverage comparator и100vs400Q cap ещё не согласованы |
| M001-C1 | Time-aligned teacher supervision | Refine после независимого review | Явный query-weighted binary BCE, teacher-prefix availability и общий later student interval; новый fit ledger |
| M001-C2 | Candidate-domain quantile-weighted top20 loss | Refine: naïve full-gradient formula fails | Literal21-item counterexample даёт положительный gradient true-positive score; один repair/update contract нужен до pilot |
| M001-C3 | Shared-weight TabM regularization | Accept-needs-pilot, условно | Mean per-head training losses, fixed variant/shape, fair CPU split, dependency admission и новая reservation обязательны |
| M001-C4 | Local labelled in-context rows | Defer после source review | CPU/MPS есть; localized provenance, label-bearing cache chronology, class support и actual cost ещё не приняты |
| M001-C5 | Bilateral positive denoising | Reject-current, ID сохранён | Singleton identity касается positive side, а не всего loss; noisy-purchase premise не обоснован, support не измерен |
| R001 | Reconstruction pending | Незавершённая линия после прерывания | Незавершённый draft не считается сданным результатом |

Кандидат получает стабильный ID своего раунда. После дедупликации он либо связывается с существующим HYP как refinement/duplicate, либо становится новым HYP с явной дельтой механизма. `needs-pilot`, `deferred`, `rejected` отделяются от права исполнения. Отказы сохраняются: недостаточные входы, дублирование, несоответствие ресурсу или слабая идентификация эффекта не стираются из истории.

## Уточнения, которые не считаются новыми идеями

| Записка | Связь | Статус и причина |
|---|---|---|
| [Query sampling и estimand](refinement-query-sampling-estimand.md) | Текущий протокол оценки и веса | Refinement: уточняет популяцию и знаменатели, не предлагает новую модель |
| [Приоритет будущего retrieval](refinement-post-heldout-retrieval-priority.md) | TLAB012 / HYP001 и candidate research | Refinement: существующий ItemCF cost gate, без нового бюджета |
| [Multi-behavior auxiliary](refinement-multibehavior-auxiliary.md) | HYP065 / прежняя multi-task ветвь | Refinement: отделяет next-any от next-purchase; запуск отложен |
| [Category text controls](refinement-category-text-controls.md) | TLAB010 / HYP003/085/086 | Refinement: lexical identity, hierarchy и semantics — разные проверки |

[Старые74 раунда](index.md) сохраняют research/audit историю; они не переименовываются в новые brainstorm-раунды. [Canonical backlog](../backlog.md) отдельно хранит принятое исполнение и отложенные ветви.

## Архивирование первых результатов — 05:33 UTC

Сохранены два реально сданных независимых отчёта и их исходные ledgers:9 candidate IDs, включая один явный отказ. [Freeze](brainstorm-f001-m001-freeze.json) связывает точные первые bytes; выводы пока не прошли cross-review. Имена будущих HYP не назначены, ни один pilot не запускался. Файлы отчётов сохранены без изменения авторского текста; их приоритеты и proposed caps не являются разрешениями на выполнение.

Предыдущая строка R001 описывала запуск до прерывания. Его завершение не подтверждено; новая независимая retrieval-линия восстанавливает этот пробел. Текущая расширенная команда после рестарта регистрируется отдельно по фактическому запуску, чтобы не выдавать исторические процессы за активные.

## Расширенная независимая команда: проверенный снимок 05:35 UTC

После рестарта authoritative agent inventory подтвердил17 работающих процессов, включая Root. Это **четыре независимые линии нового brainstorm**, два независимых cross-review, исполнители pipeline и их узкие вспомогательные исследования. Вспомогательный поиск статьи не считается отдельным независимым авторским раундом. Время ниже — момент наблюдения списка, а не выдуманное время начала работы.

| Процесс | Наблюдавшийся scope | Статус на05:35UTC |
|---|---|---|
| `/root/brainstorm_features_a` | Новые feature/automation механизмы, независимый draft A | Работает; результата ещё нет |
| `/root/brainstorm_features_b` | Новые feature/automation механизмы, независимый draft B | Работает; результата ещё нет |
| `/root/brainstorm_retrieval_a` | Новые retrieval/session механизмы, независимый draft A | Работает; primary-session helper отдельно |
| `/root/brainstorm_retrieval_b` | Новые retrieval/session механизмы, независимый draft B | Работает; результата ещё нет |
| `/root/review_feature_ideas` | Независимая критика уже сданного F001 | Работает; primary-source helper отдельно |
| `/root/review_model_ideas` | Независимая критика уже сданного M001 | Работает; tabular/TabM source helpers отдельно |

Остальные наблюдавшиеся процессы: Root, sole backlog coordinator/publisher, six-role harness с supervisor reviewer, source-import owner и независимый source-import reviewer с typed9 helper. Их code/review работа не выдаётся за brainstorm новых моделей. Новые исследования сначала сдают независимый первый draft; знакомство с соседними новыми результатами и cross-review фиксируются после него. Исследовательские предложения не меняют нынешнюю015/016 reservation.

## Новая пара model/loss авторов: снимок05:40UTC

Authoritative inventory подтвердил **шесть работающих независимых brainstorm roots**: прежние featureA/B, retrievalA/B и новые `/root/brainstorm_models_a`, `/root/brainstorm_models_b`. Root назначил model/loss авторам blind first drafts, без чтения свежего M001 до их сдачи. Обе F001/M001 cross-review линии тоже работают. В списке17 известных процессов, из них14 running и3 completed; completed helpers/reviewer не выдаются за текущую активность. Освободившиеся reviewer slots использованы для новых самостоятельных вопросов.

| Новый процесс | Scope | Статус на05:40UTC |
|---|---|---|
| `/root/brainstorm_models_a` | Новый независимый model/loss draft A | Работает; первого результата ещё нет |
| `/root/brainstorm_models_b` | Новый независимый model/loss draft B | Работает; первого результата ещё нет |

Следующий свободный канонический диапазон после исторических reserved/refinement IDs —139+. Номера не присваиваются заранее ради объёма: сначала independent novelty review, затем явный `needs-pilot`/`deferred`/`rejected` и минимальный опровергающий опыт. Сохранённые draft IDs NB-F/M001 остаются стабильными.

## Первый новый blind draft и законченный cross-review —05:43UTC

[Features-A FA001](brainstorm-fa001.md) сдал четыре candidate-механизма: FA01 pair-synergy-first expansion; FA02 adaptive directed migration между typed families; FA03 shared symbolic search с bounded local adaptation; FA04 archive-induced grammar macros. [Ledger](brainstorm-fa001-ledger.json) сохраняет counterhypotheses, matched controls и самые дешёвые literal falsifiers. First draft заморожен до чтения соседних новых reports; cross-review пока ожидается. Это добавляет4 предложения, а не4 выполненных улучшения.

[Независимый M001 review](brainstorm-m001-review.md) завершён: C1/C2 refine, C3 accept-needs-pilot условно, C4 defer, C5 reject-current. Главная найденная проблема: unbounded top20-weighted loss из draft может уменьшать loss, понижая score настоящей покупки. [Literal corroboration](brainstorm-m001-math-corroboration.json) отдельно воспроизвёл derivative +.525108393 и узкую singleton-positive identity; реальных данных и native jobs не было. Proposed repair ещё не выбран, поэтому C2 не готов к model pilot. [Freeze](brainstorm-fa001-m001-review-freeze.json) связывает original и portable-publication hashes; author drafts и исходное negative evidence сохранены.

Всего сейчас реально сданы13 draft candidates в F001/M001/FA001;5 из них прошли первый независимый cross-review. Эти counts не означают13 новых канонических HYP: часть остаётся refine/defer/rejected, новые номера пока не назначены. Следующий cross-review использует замороженные drafts; авторам незавершённых blind линий соседние выводы до их first freeze не передаются.

## FeaturesB и обе retrieval-линии сдали drafts —05:45UTC

| Сданный раунд | Candidate IDs | Механизмы | Проверка |
|---|---|---|---|
| [FB001](brainstorm-fb001.md), [ledger](brainstorm-fb001-ledger.json) | FB-01…04 | Second-order action-path areas; item audience contribution shape; purchase-reset observed episodes; support-context feature-arm router | Root назначил FA↔FB независимую crossed critique после freeze |
| [RA001](brainstorm-ra001.md), [ledger](brainstorm-ra001-ledger.json) | RA-01…03 | Mature other-user situation→purchase memory; exact two-seed triple completion; horizon-integrated delayed category recurrence | Новизна, source semantics и caps ждут crossed review |
| [RB001](brainstorm-rb001.md), [ledger](brainstorm-rb001-ledger.json) | RB1…4 | Probability-derived source quotas; conjunctive prefix completion; item repeatability admission; seed/channel call allocation | Взаимная критика RA/RB после first freeze, не готовый retrieval result |

Всего в шести сданных drafts F001/M001/FA001/FB001/RA001/RB001 —24 local candidate IDs. Явная возможная коллизия RA-02/RB2 о conjunctive completion ещё не дедуплицирована: не выдаём её за две канонические гипотезы. [Freeze](brainstorm-fb001-ra001-rb001-freeze.json) фиксирует exact originals и portable publication copies. FB прямо сообщает чтение journal summaries, RA — ранее опубликованных NB-F notes; поэтому независимость означает отдельное авторство первого draft без чтения параллельных полных reports, а не полное незнание всех зарегистрированных новых идей. Для будущих строго blind waves нужен фиксированный prior-context snapshot.

Root дополнительно назначил `/root/brainstorm_transfer_a` и `/root/brainstorm_transfer_b`: в этой волне распределены8 самостоятельных feature/retrieval/model/transfer roots. Это число назначенных независимых авторов; часть уже сдала draft и перешла к crossed review. Оно не означает8 одновременно незавершённых brainstorm jobs. Primary-paper helpers по-прежнему отдельно. Новые канонические HYP ещё не присвоены, real data/models/target jobs не запускались.

## F001 cross-review закончен: accept/defer/refine, а не четыре готовых pilots

[Независимый review F001](brainstorm-f001-review.md) и [primary-source проверка](brainstorm-f001-primary-verification.md) сохраняют NB-F01 accept-needs-pilot, NB-F02 defer, NB-F03/NB-F04 refine. Старый публичный manual005 summary показывает редкость prior-purchase context; новый100Q gate не считается заведомо выполнимым. NB-F04 получил отдельный literal counterexample: IQR+1 reliability ranking может меняться при эквивалентной смене единиц. Конкретный scale-aware repair ещё не выбран.

[Stdlib script](brainstorm-f001-literal-review.py) и [результат](brainstorm-f001-literal-results.json) опубликованы; coordinator один раз воспроизвёл его stdout точно. Это четыре раздела арифметики на вымышленных событиях/curves/histograms, а не REES46 source-тесты или измерение бюджета. [Freeze](brainstorm-f001-review-freeze.json) сохраняет original/public hashes и честно раскрывает первоначальный SyntaxError служебного reviewer checker до его исправления. Всего9 из24 сданных candidate IDs получили первый independent cross-review; новую canonical очередь надо дедуплицировать по всем раундам до присвоения139+.

## ModelA/B drafts сданы; повторное открытие механизма не раздувает HYP count

[MA001](brainstorm-ma001.md), [ledger](brainstorm-ma001-ledger.json), и [MB001](brainstorm-mb001.md), [ledger](brainstorm-mb001-ledger.json), зафиксировали ещё8 local candidates. MA: TabM diversity, ModernNCA labelled-row metric neighborhood, exact-C SL@20 с full-Y coverage weight, full-C против teacher-top20 KD. MB: bounded PSL-tanh gradients, TabM shared ensemble, separate-head teacher-bias isolation, joint hierarchical item tokenization. [Freeze](brainstorm-ma001-mb001-freeze.json) сохраняет первые bytes и portable path-only copies.

Независимо rediscovered TabM в M001-C3/MA-01/MB02 — одна mechanism family, а не три новых HYP. MA-03 пересекается с M001-C2; negative-gradient counterexample уже передан на crossed review после first freeze. Три distillation направления могут иметь разные contrasts, но общий teacher/chronology contract ещё требует совместной дедупликации. ModernNCA labelled-memory prediction не автоматически тождественен frozen foundation ICL: это отдельный вопрос review.

Теперь в восьми реально сданных drafts32 local IDs;9 прошли первые F001/M001 reviews. Количество canonical new hypotheses пока0. Это прозрачный счёт предложений, не выполненных экспериментов. Root назначает modelA↔B cross-review после их freeze; transferA/B ещё исследуются. Следующая строго blind wave использует фиксированный prior-context commit `ec3dabc`, до новых summaries, а не live journal.

## Crossed feature/retrieval/model reviews завершены

| Проверенный draft | Независимый reviewer | Решения и найденные ограничения |
|---|---|---|
| [FA001 review](brainstorm-fa001-review-by-b.md) | FeaturesB | FA01 accept-needs-pilot; FA02 defer; FA03 refine; FA04 defer. MI не различает invertible sign reversal, поэтому первоначальный negative-transfer fixture FA03 не годится |
| [FB001 review](brainstorm-fb001-review-by-a.md) | FeaturesA | FB01 accept-needs-pilot; FB02/03 refine; FB04 defer. Denominator/missing closure, reset peer/window boundary и router chronology требуют exact contracts |
| [RA001 review](brainstorm-ra001-review-by-b.md) | RetrievalB | RA01 accept-needs-pilot research; RA02 merged withRB2; RA03 defer. При12-item session до220triples/660rules, outputquota не ограничивает build |
| [RB001 review](brainstorm-rb001-review-by-a.md) | RetrievalA | RB1 existingHYP053 refinement; RB2 merged needs-pilot family; RB3/4 refine. Greedy exact overlap нельзя выбирать по скрытым retrieval outputs и одновременно заявлять equal calls без prepaid cache |
| [MA001 review](brainstorm-ma001-review-by-b.md) | ModelsB | MA01 TabM duplicate; MA02 refine/defer; MA03 blocking update contract; MA04 distinct KD closure contrast, defer without compression need |
| [MB001 review](brainstorm-mb001-review-by-a.md) | ModelsA | MB01 refine→needs-pilot; MB02 TabM duplicate; MB03 narrow KD-head contrast deferred; MB04 distinct joint-code mechanism deferred. Теорема bias isolation и paper/code token-loss sign не переносятся автоматически |

[Freeze](brainstorm-wave001-crossreview-freeze.json) связывает14 original/public review/evidence files; первые авторские drafts неизменны.32 local candidates восьми drafts теперь покрыты first independent reviews; это не32 новых HYP и не32 реализованных улучшения. TransferA/B first drafts и их crossed critique ещё должны завершить общую novelty map перед окончательным присвоением139+.

## Следующие решения

Сначала сдача текущих независимых drafts, параллельно критика уже сданных F001/M001; затем ротация cross-review и сравнение novelty/стоимости. Следующие темы выбираются по найденным пробелам, а не ради счётчика HYP. Любой будущий pilot требует отдельной development/label reservation, matched baseline, заранее заданных метрик и предела стоимости. Нынешние015/016, выбранные модели и heldout policy новыми идеями не изменяются.
