# Round017: information boundary автоматического proposer

15 октября 2026. **Research/design-only: без raw scans, новых metrics, fits, feature tests, LLM API calls и изменений репозитория.** Прочитаны актуальный [backlog](../backlog.md), rounds [003](round-003.md)/[005](round-005.md)/[009](round-009.md)/[014](round-014.md)/[016](round-016.md). Root full009 и frozen018 не затронуты. HYP119/120 остаются reserved: refinements002/proposer/lock, без новой квоты гипотез. Описанные шаги не получают execution permission.

## Четыре первичных основания

ExploreKit разделяет generation, candidate ranking и classifier evaluation; learned ranker использует опыт предыдущих datasets. Enumeration и learned usefulness prediction имеют разные dependencies/cost. Его evaluation loop нельзя спрятать под названием «одна intelligent proposal». [ExploreKit, IV](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf).

OpenFE FeatureBoost обучает дополнительную модель относительно baseline predictions, затем выполняет pruning/attribution. Отсутствие полного retraining на каждом candidate не означает отсутствия обучения. Этот поиск не является бесплатной заменой наших четырёх downstream fits. [OpenFE, Algorithms2–4](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf).

Cawley–Talbot показывают overfitting selection criterion; Dwork et al. требуют controlled feedback mechanism для соответствующих holdout-reuse guarantees. Наш ledger/lock делает адаптацию видимой и ограниченной, но не реализует Thresholdout и не устраняет bias повторного просмотра точных selection metrics. [JMLR](https://jmlr.org/papers/volume11/cawley10a/cawley10a.pdf), [adaptive holdout paper](https://arxiv.org/pdf/1506.02629).

## Четыре уровня информации

**Target-free enumeration:** schema/semantic annotations, whitelist operators, grain/windows, exact aliases относительно полного frozen B и physical closure.198 schema templates009 — definitions, а не198 materialized columns. Target-free cost proxies допустимы как заранее объявленные правила; actual calculations оплачиваются. Минимальный текущий I — static schema heuristic003, R — uniform seeded draw. Название intelligent не означает learned predictor.

**Train-only screening:** train labels, residuals и associations могут выбирать AST при соблюдении cutoff и регистрации. Корреляция без model fit всё равно использует targets и cost; materializing198 columns ради выбора трёх нарушит12-column cap, даже если потом обучить только4 models. Learned selector, surrogate, probe, OOF model и его tuning являются fit/trial dependencies. Один learned-proposer fit плюс4 arm fits дают5, а не разрешённые4. Такой вариант требует нового распределения внутри existing cap и отдельного review; дополнительные fits не разрешаются автоматически.

**Selection-feedback adaptation:** изменение weights/operators/AST после просмотра нового selection score — следующий adaptive attempt. Для текущего one-attempt-per-arm дизайна новые bundles не выдаются. Если будущий протокол специально разрешит feedback, consumed looks, порядок и стоимость фиксируются заранее. Confirmation остаётся закрытой; CI на reused selection остаётся screening-only.

**Prior human knowledge:** опубликованные007 heuristic и008 smoke metrics уже известны;009 retention/019 tuning добавят историю решений. Исключение чисел из JSON не делает автора эвристики blind. Нужен общий known-results register и freeze относительно новых результатов: prospective означает prospective к следующим неизвестным outcomes. Внешний LLM/API не авторизован. Pretrained proposer также потребовал бы weight provenance/availability и inference cost, а не автоматическое исключение из ledger.

## Common inputs и draw до новых metrics

Все arms получают один pinned protocol/Q/C/fullY/evaluator, frozen winning B population/settings, полный typed legal pool и semantic-dedup/closure rules. Доступные inputs включают одинаковые schema/registry/context, cost policy и known-results register. I использует объявленный semantic prior, R игнорирует его при uniform draw; это различие стратегии, а не разрешение I получать скрытые targets или более широкий pool.

Canonical pool сортируется по AST/bundle identity; сохраняются pool SHA, PRNG algorithm/version/state/seed, точный draw law и I weights. Предлагаются independent draws с replacement из одного полного pool: collision потребляет attempt, без redraw. Иной without-replacement law фиксируется заранее; нельзя после выбора удалить неудобный bundle только из R pool. Seed без pool order/PRNG version недостаточен для воспроизведения.

Каждый arm замораживает один whole bundle: ровно3 новые physical columns после supports/masks/coverage closure, затем максимум один разрешённый fit. Invalid/duplicate/collision сохраняет status и cost, без replacement. Frozen B не перенастраивается. Общие≤12 columns/≤4 fits/≤2 CPUh включают proposer, preparation, failures и scoring; неучтённый proxy fit не компенсируется одинаковым downstream fit count.

## AST availability и исторические numeric values

Target-aware выбор структуры AST по train labels допустим для downstream prediction после proposer availability. Например, labels зрелы к train cutoff21Oct; selector завершается после cutoff, затем выбранный label-free count AST пересчитывается для training anchors8–20 строго из `[a−W,a)`. Это offline feature selection: AST не объявляется существовавшим8Oct, а numerical counts не читают будущее относительно a.

Learned numeric prior/encoder внутри значений — отдельный fitted component со своим as-of availability; его нельзя спрятать в AST choice. Q/C сохраняют past eligibility/hash sampling до labels: screening только покупателей или вставка future positives в C запрещены.

Если proposer использует019 winner, выбранный по selection labels24Oct, его decision availability не становится задним числом22Oct. Последующие scores на22–23 трактуются как retrospective development, а не независимый online replay той же selection. Для неиспользованной confirmation нужен полный pipeline lock с положительным compute allowance;25-only schedule по-прежнему не утверждён.

## Portable proposer/consumed-look lock

Предложение: versioned artifact хранит role(static/train-learned/selection-adaptive), code/weights/config/dependency hashes, trainQ/C/Y/weights/cutoff, разрешённые inputs, все probe/fit/column counts, PRNG/pool/selected AST/closure, использованные report IDs и ledger stages. Failed/unattempted choices сохраняются; новый output root не отменяет consumption.

Simulation clock2019: used labels зрелы к declared fit cutoff, dependencies доступны до использования; `proposer_available_at≤AST_freeze≤downstream_fit_start`. Model/decision ready строго раньше first reserved query с positive allowance после max used label maturity. Actual clock2026: proposer/model/decision sealed+hashed до открытия reserved query targets сейчас. Physical file в2019 не требуется; audit mtime не доказывает simulated availability. Исполнение разрешают внешний review/pins, а не producer fresh hashes.

## Что сравнивают четыре pipelines

2I+2R дают четыре реализации ограниченной зарегистрированной процедуры. Winner может принадлежать R; единственный frozen winner против B на confirmation проверяет выбранный pipeline. Best-of-two I против best-of-two R — descriptive/screening: две seeds не доказывают general strategy superiority. Оценка стратегии потребовала бы отдельного плана repetitions/uncertainty/cost, без автоматического расширения нынешнего бюджета.

Один prospective **zero-fit** tiny check: три legal3-column bundles, fixed weights и literal entropy draws. Два draws попадают в один bundle — второй attempt consumed без replacement. Перестановка неиспользованных toy labels не меняет static proposer output; injecting undeclared target access/new metric look или ledger1 selector fit+4 arm fits обязано отвергаться до trainer. Выполнение, budget и code не объявляются принятыми. Такой check проверяет boundary/ledger, а не качество эвристики или случайного поиска.
