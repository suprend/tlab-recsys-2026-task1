# Round059 — accepted019 как контроль: справедливость016 и точные границы claims

**Source-only audit, 15 октября2026.** Прочитаны опубликованные [019 review](../backlog-reviews/tlab019-strong-output-verification.md), [aggregate](../backlog-reviews/tlab019-strong-output-aggregate.json), [prospective016 selector](../experiments/feature-program-selection.md) и [проверенный парафраз task1](../task1-requirements.md). Модели, scores на уровне строк, raw source, reserved targets и WIP016 не открывались. Это интерпретация уже принятого evidence и будущего сравнения, не независимый повтор019. Новых HYP, правил, задач или бюджета не предлагается.

## Что действительно принято

019 завершил четыре заранее объявленных Logloss fits на26000 training queries; каждый обучен300 iterations. Двенадцать scoring prefixes — зависимые проверки тех же четырёх моделей, а не двенадцать независимых обучений. Учитывается и ранее просмотренный008 incumbent. Принятый B использует исходную41-колоночную схему, depth6/L2=30, trained300/scoring300. Опубликованные conditional query-macro NDCG@20=0.4586107284411232 и Recall@20=0.5851272015655578 относятся к selection4000queries; положительных fullY queries всего73, distinct query-item targets96. All-query-zero NDCG=0.0083696457940505 — другой estimand, не ухудшенная версия той же условной величины.

Поэтому точное название — **«ручной CatBoost-контроль, выбранный ограниченной заранее заданной настройкой»**. Допустимое короткое «настроенный контроль» требует соседнего описания4fits/12prefixes/seen incumbent. «Оптимальный», «исчерпывающе настроенный», «лучший boosting» не следуют из этих данных. Слово «manual18» описывает ядро расчётных определений, а не число физических model columns: контроль B41 включает объявленное расширение схемы.

Независимый observer перепроверил сохранённые predictions, четыре fullY estimands, модельную схему/параметры и правило выбора без refit. Это сильное evidence воспроизводимости конкретного результата. Но фактические training weights из CBM не извлекаются: их основание — reviewed fit code, принятая популяция и receipts. Переиспользована старая sampled source verification manual18; новый exhaustive baseline-formula proof019 не возник. Нельзя распространять будущий exhaustive selected12 oracle016 на весь B задним числом.

## Первичные AFE основания и их пределы

[OpenFE, §5.1–5.3](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf) использует общий split, tuning на base features и одинаковую ширину добавления для методов. Это поддерживает логику контролируемого feature contrast, но не переносит tabular результаты на наш strict-past/fullY ranking. [ExploreKit, §IV–V](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf) выбирает features через wrapper/CV, используя Weka default learners; следовательно, опубликованная AFE-польза не всегда предполагает отдельный joint retuning каждого набора.

[Cawley–Talbot](https://jmlr.org/papers/v11/cawley10a.html) объясняют переобучение конечного selection criterion. Фиксация seed и проверка arithmetic не превращают selected maximum в независимую оценку. Поэтому повторные development looks надо раскрывать; bootstrap уже выбранного B не устраняет историю выбора. Это методологическое ограничение, а не заявление о недействительности принятого019.

## Fairness016: что сравнивается и что оплачивается

| Компонент | Уже заданная граница | Что нельзя вывести |
|---|---|---|
| Обучение | Все arms наследуют accepted019 population, weights, параметры, trained iterations и scoring prefix | Одинаковые learned trees, effective capacity или optimality для нового набора |
| Возможности | Два static-I slots и два seeded-R draws из общего legal pool; каждый arm3 physical columns включая mask | Два независимых исследования intelligent strategy или равный observed CPU |
| Выбор | B плюс все четыре I/R arms; Recall guard, global NDCG band, physical-width/lexical tie | Что random winner доказывает преимущество guided proposals |
| Стоимость | Общие расчёты, hashes, oracle, failures/recovery/retries входят в общий ledger | Что shared scan делает новые columns бесплатными |
| Неуспех | Collision/recognized resource failure оплачены и consumed; integrity/API/unknown STOP | Что неполное сравнение равно четырём проигравшим моделям |

R sampling с возвращением допускает collision с I либо другим R. Это часть объявленной opportunity law; replacement ради четырёх уникальных программ был бы новым поиском. Номинальные slots, unique bundles, actual physical union и completed fits надо показывать раздельно. При reuse одного verified result одинаковыми slots это не две независимые реализации. Сопоставимость двух возможностей каждой семьи сохраняется на уровне allocation, но не создаёт оценку превосходства стратегий по двум наблюдениям.

Selected-union calculation может оплачивать source scan один раз. Для честного отчёта нужны total paid cost и прозрачное описание shared/per-arm attribution; приписывать полный scan каждому arm и затем суммировать — двойной счёт, исключать scan из study cost — недосчёт. Наблюдённый меньший CPU у arm может отражать более дешёвое primitive/state или cache reuse, а не более эффективный proposer. Эти положения уже входят в compute/repro gates; отдельный benchmark сейчас не нужен.

## Качество, часы и отрицательный итог

Primary016 contrast — sealed W−B, причём W может быть B или random arm. Best-two-I−best-two-R остаётся descriptive development screening. Отрицательный либо неопределённый итог не отменяет доказанную schema→AST generation и correct calculation; он запрещает обещание quality gain. W=B даёт нулевой selected contrast вследствие правила, а не equivalence theorem для всех будущих learners/datasets. Resource-incomplete experiment и semantic-invalid experiment требуют отдельных статусов, не красивого отрицательного среднего.

User-bootstrap описывает variation sampled users при фиксированных датах/моделях и собственном query weighting;73 positives и200draws не дают seed/date robustness или postselection confirmatory guarantee. Heldout prospective evidence допустимо описывать лишь после существующих prediction-before-Y seals и terminal verification. Сейчас это gate, не результат.

Нужны два времени: simulated2019 определяет past features, maturity и positive decision compute allowance; actual2026 — порядок audit/seals/opening targets. Нельзя утверждать физическое существование модели в2019 либо отсутствие любых future bytes: whole-month EDA уже было. Честное более узкое утверждение — неиспользование reserved query-level targets для адаптации после фактического lock.

## Минимальный report-spine amendment

Предлагаемый абзац, не изменение протокола: «Контроль выбран из четырёх заранее заданных обучений и двенадцати зависимых scoring prefixes с учётом ранее известного incumbent. Приведённые019 показатели получены на development selection; они не являются untouched holdout оценкой. Автоматизация016 проверяет фиксированную процедуру генерации/расчёта и ограниченный выбор добавлений при тех же настройках контроля. Качество, source correctness и затраты сообщаются отдельно; отсутствие улучшения сохраняется как результат».

Task1 допускает automation generation/calculation как исследовательский путь либо альтернативу, превосходящую хорошо настроенный boosting. Это разрешает честный no-improvement experiment на первом пути, но не гарантирует оценку задания и не освобождает от экспериментальной проверки/воспроизводимого pipeline. Текущий backlog уже покрывает необходимые gates; **new-task outcome: none**.
