# Round054 — одно frozen сравнение и сила automation claim

**Углублённое чтение одной recommendation-evaluation работы с применением к final report.** Исследованы primary paper и companion source; реальные данные, metrics/models019/016, WIP и holdout не открывались, запусков нет. Последний сообщённый coordinator status — producer019 завершил четыре fits/12looks, independent observer требует scoped recovery. Это не прочитанное здесь execution evidence: accepted019 winner неизвестен и ниже не предполагается. Новых HYP или policy changes нет.

## Primary study: что именно повторяется

Rodriguez, Lesota, Tommasel, **Training seeds and model-selection stability in recommender-system evaluation**, RecSys2026 Research&Practice Notes, [arXiv2609.02499v1](https://arxiv.org/html/2609.02499v1), фиксируют partition и меняют training seed. Три datasets — MovieLens1M, Steam, AmazonAllBeauty2023; per-user chronological split80/10/10. BPR/NeuMF/BERT4Rec/SASRec имеют соответственно3/9/12/12 configurations. Для каждой используются seeds1…10, max300epochs, patience10 и best-validation checkpoint; primary metricNDCG10. Анализ разделяет user-level sensitivity, selection stability, validation→test consistency и list agreement. Обнаруженная чувствительность не обязательно меняет winner; стабильный validation winner не обязательно сохраняет преимущество на test. Авторы не разделяют внутренние причины training randomness и не варьируют split.

Это особенно релевантное ограничение: авторский предмет — **повторное обучение**, не повторный расчёт метрик одной сохранённой модели. Его нельзя воспроизвести увеличением числа bootstrap draws или сравнениями разных checkpoints одного fit.

[Companion run_seeds.py](https://github.com/knife982000/RecSeed/blob/main/run_seeds.py) подтверждает последовательность: dataset seed→create_dataset/data_preparation один раз, затем model seed→новый model/trainer→fit→evaluate best checkpoint. Validation и test predictions собираются из одного выбранного состояния. [analyze.py](https://github.com/knife982000/RecSeed/blob/main/analyze.py) выбирает config по validation mean и сравнивает его test mean с максимальным **наблюдённым** test mean среди рассматриваемых configs. Это диагностический oracle regret, не разрешение выбирать deployment winner по test и не истинный мировой optimum. Прочитан public main, immutable code SHA не установлен; paper version закреплена явно.

Номинальная сетка из описанного дизайна даёт `3datasets×(3+9+12+12)configs×10seeds=1080` training slots. Это наш арифметический вывод, не проверенный completed-attempt ledger авторов. Ни elapsedCPU, ни наш resource feasibility из этого произведения не следуют.

## Какие вопросы требуют нового evidence

Обозначим frozen-model contrast `Δ(s₀,D)=M(A(s₀),D)−M(B(s₀),D)`, где D содержит fixed dates/Q/C/fullY, а s₀ — фактически использованный training seed. Он отличается от среднего эффекта по seeds, новым датам или заново выполненному model-selection procedure.

| Предмет inference | Что пришлось бы повторять | Чего не достаточно |
|---|---|---|
| Correct replay сохранённых моделей | Те же keyed inputs/predictions и независимый estimator | Новый fit не нужен; это не distributional robustness |
| Training-seed sensitivity fixed programs/settings | Полное обучение каждого pipeline на заранее объявленных seeds | Повторить predict или resample users одной модели |
| Stability выбранного config/checkpoint | В каждом repetition повторить весь заданный training+selection procedure | Пересчитать max по прежним12scores |
| Frozen-model performance на новых датах | Новые законные date windows с теми же frozen models | Две старые даты не создают новые shocks; новые fits необязательны |
| Learning-procedure robustness при rolling origins | Source/labels/selection chronology и обучение для каждого origin | Перенести ту же fitted модель на новые dates и назвать refit stability |
| Перенос метода между datasets | Отдельные source/adapter/target contracts и соответствующий study design | Несколько random splits одного источника |

Per-user chronological split статьи не тождествен global strict-asof dailyqueries нашего протокола. Multiple seeds не доказывают ingestion availability или отсутствие будущих событий в исторических aggregates. Multiple datasets не являются iid repetitions одного магазина. Эти выводы — наше разграничение estimands, а не дополнительные авторские теоремы.

Для selection с73positive queries точное вычисление conditional macroquery metric остаётся полезным, но73 — не доказательство достаточной мощности и не1080 независимых training trials. Один user-cluster CI условен на имеющихся dates/fitted models; повторное tuning019 и выбор016 не входят в него автоматически. Четыре configurations и12checkpoints показывают bounded search history, а не12независимых подтверждений. Это короткое применение019/034, без повторения bootstrap recipe.

## Как объединить positive/negative engineering evidence

[Проверенный парафраз task1](../task1-requirements.md) требует manual boosting pipeline и предложение автоматизации generation/calculation **либо** альтернативного метода, превосходящего хорошо настроенный boosting, с экспериментальной проверкой. Для automation route отрицательный quality result логически совместим с подтверждённой автоматизацией и содержательным экспериментом. Но слово «либо» не заменяет исполнение/verification центрального сравнения и не гарантирует внешнюю оценку задания.

| Доказанное свойство | Допустимый claim | Отдельное недоказанное свойство |
|---|---|---|
| Accepted symbolic schema→AST/type/dedup/closure | Ограниченная генерация по human annotations/templates | Learned discovery или автономное понимание схем |
| Independent source proof выбранных additions | Correct calculation в объявленном checked scope | Exhaustive numerical source proof всех старых B; тот остаётся sampled |
| Actual shared resource ledger | Измеренный расход этого эксперимента | Speedup против batched005 или human-hours saving |
| Complete matched arms с acceptedB и fullY | Наблюдаемые development contrasts и frozen selection | Устойчивость across seeds/dates/datasets |
| Prospective reserved evaluation frozenW−B | Результат уже закреплённого решения на reserved population | Результат после reselection/refit по holdout или causal lift |

009 whole metadata block уже является опубликованным valid negative quality result; он не отменяет source correctness и не доказывает бесполезность всех category/price features. Аналогично, если016 complete/source-valid arms не улучшаютB, generation/calculation evidence сохраняется. ЕслиW=B, primary contrast по определению0 вследствие frozen selection rule, а не доказанной эквивалентности всех arms. Resource failure означает paid/ineligible/budget-limited; observer/integrity uncertainty означает unverified/STOP. Их нельзя представить как отрицательные измерения качества.

## Конкретный текст итогового отчёта

> Реализована ограниченная генерация typed feature programs из явно аннотированной схемы и человеческих templates. Correct calculation подтверждён отдельно в указанном scope. Четыре заранее allocated opportunities сравнивались с общим manual control по единому full-Y protocol; completed/ineligible attempts и расход раскрыты. Приводимые quality contrasts относятся к конкретным fitted models, training seed и date window. Они не устанавливают превосходство стратегии поиска по двум random draws, устойчивость к переобучению на иных seeds или переносимость качества.

После фактической verification сюда подставляется один из честных вариантов: «наблюдаемое улучшение не получено»; «point estimate положительна, uncertainty не устанавливает знак»; либо «frozen contrast положителен в данном evaluation scope». Development screening нельзя переименовать в prospective подтверждение. CI через0 не доказывает equivalence; precision самого replay не исправляет малый support. Holdout outcome здесь неизвестен. Значения и окончательный winner заполняются только после independent output/chronology acceptance.

## Один worthwhile future experiment, отдельно бюджетируемый

Proposal: **seed sensitivity двух уже frozen pipelines**, без поиска новых features/configs. После текущего исследования заранее закрепить B и W, один fixed development partition, полный Q/C/Y/context, одинаковые weights/settings/trained iterations/prefix и три новых seeds. Это шесть заранее оплачиваемых fit attempts, не добавление к нынешним budgets. W=B делает такой contrast бессодержательным: тогда не заменятьW постфактум «интересным» проигравшим arm и не активировать proposal автоматически.

Primary diagnostic — три paired seed contrasts одного ранее закреплённого estimator, все sign/values и failures без best-seed selection; никаких новых checkpoint looks/refill. Нужны separately approved CPU/wall/RSS/source-oracle budgets до запуска. Три seeds дают небольшой sensitivity drill, не уверенное распределение uncertainty, не selection-procedure replication и не confirmation. Применение к уже известному development окну честно exploratory; current reserved labels не открываются ради этого предложения. Дальнейшие dates/datasets потребовали бы другого study, который здесь не предлагается и не финансируется.
