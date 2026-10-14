# B3. Скептический разбор и первая очередь исполнения

15 октября 2026. Независимая planning-проверка: прочитаны готовые feature/target reports, B1-draft и B2-plan. Данные, окружение и репозиторий не изменялись; вычислительные оценки ниже — предлагаемые ограничения, не benchmark. Основания: [план проекта](../experiment-plan.md), [feature synthesis](../features/index.md), [target review 01–04](../target-research/review-01-04.md), [target review 05–08](../target-research/review-05-08.md), [архитектура backlog](architecture.md), [верификация](verification.md).

## Вердикт по первым пяти задачам

TLAB-001–005 можно публиковать как provisional execution slice: 001 `in_progress` у Root, 002 `ready`, 003 `blocked` до 002, 004 до 003, 005 до 001/004. В 003 явно различить самостоятельный bounded SQL pilot и production-интеграцию: второй путь зависит также от 001. Иначе исполнитель либо продублирует temporal-core, либо будет ждать несуществующий prerequisite. Исходные отчёты не подтверждают достаточность positive queries, качество retrieval или скорость материализации. Статус «документ готов» не равен `done` соответствующего эксперимента.

## Сильные возражения

**Ресурсный предел задан не на самый дорогой объект.** 6 000 queries×220 candidates ограничивают выход, но не чтение 42,45 млн событий, сортировку, global/category aggregates и exact-distinct state. Выбор 100 пользователей не разрешает считать глобальную популярность только по их историям. Для полного global feature нужен полный необходимый временной срез либо явно изменённая семантика. В manifest разделить scan rows, state keys, output rows, spill/disk и wall time; сначала измерить один день/100 queries. Оценка float-матрицы не покрывает Python-object overhead. [Feature synthesis](../features/index.md), [ItemCF cost](../features/09-user-item/02-item-neighbors.md).

**Предлагаемые A/B проверяют population, а не модель.** Eligibility 7d и 48h меняет аудиторию и prevalence; более высокая условная NDCG во втором варианте не доказывает лучший алгоритм. `[t,t+24h)` fixed-clock до секунды t корректен как явный вариант, но расходится с частью raw notes. Не склеивать его с action anchors или `(t,t+H]`. Next-purchase и purchase-set — отдельные задачи. Выбрать development-протокол по пригодности/стоимости, затем заморозить; не искать clock×eligibility×H×endpoints×loss полной сеткой. [Target review](../target-research/review-01-04.md), [feasibility](../target-research/08-feasibility.md).

**Редкие positives нельзя исправить будущим отбором.** 742 849 purchase-строк не задают число информативных queries. Сохранять все зрелые eligible queries; sample выбирать до labels. Если PairLogit получает мало групп с одновременно positive/negative, это наблюдаемое ограничение. Увеличить label-independent sample по заранее заданной ступени или проверить BCE; не оставить только будущих покупателей и не вставить positive в C. C⊆prior-observed U также не доказывает наличия товара в продаже. [Training review](../target-research/review-01-04.md).

**18 колонок — разумный старт, но пока не доказанный strong baseline.** Сложное дополнение может выиграть у недонастроенной модели. Требуются popularity, last-view/recent-distinct и возврат прямых pair/item признаков перед заявлением пользы learned scores. Counts purchase/view не являются вероятностью конверсии; отсутствие purchase не является отрицательным показом. [Alignment](../target-research/07-tlab-alignment.md), [rates review](../features/review-01-04.md).

**95% интервал после поиска не отменяет selection bias.** Постоянный research-поток способен превратить validation в бесконечный конкурс. Интервал положительной Δ после множества попыток не гарантирует воспроизводимого улучшения. В ledger входят неудачные fits, изменение sampler, preprocessing и tuning baseline. Первые automation-сравнения ограничить четырьмя validation fits, не выдавать локальный CI за доказательство общего превосходства; final test использовать после lock. User bootstrap не покрывает общий дневной шок. [Evaluation review](../target-research/review-05-08.md).

## Первая очередь: outputs, приёмка и остановка конкретного run

1. **TLAB-001, temporal-core.** Root сохраняет единоличное владение двумя согласованными файлами. Acceptance: `[t−W,t)`, global peers read-before-update, maturity для обоих endpoints, future-suffix/peer-permutation invariance на tiny fixture. Stop: необъяснённое расхождение с hand values; сначала исправление, затем дальнейшая интеграция. CPU/Mac достаточен для этой проверки.

2. **TLAB-002, configs/manifests.** Версия, hashes, source interval, sampling, endpoints, duplicates, fit cutoffs, budgets. Acceptance: несовместимые bounds/unknown fields отклоняются, round-trip сохраняет смысл. До 30 минут на первый ограниченный scope; недостающее необязательное поле не повод строить новый orchestration framework. На Mac без raw scan.

3. **TLAB-006, evaluator параллельно 003.** Full Y определяет Recall/IDCG; пустой зрелый Y отделён от censored, tie-break фиксирован. Acceptance: один найденный из трёх даёт Recall=1/3, NDCG≈0,469; короткий C не дополняется positives. Stop при расхождении golden examples. Этот ready-путь не должен ждать обучения.

4. **TLAB-003, labels/anchors.** 8–10 октября, ≤2 000 past-eligible users/day/вариант, hash selection до labels. Output: reconciliation всех query-состояний, prevalence, informative groups, cold targets, same-second purchases. Acceptance: независимый SQL oracle и manifest. ≤30 минут/вариант, DuckDB 2 threads/2GB. При cap сохранить partial cost; уменьшать sample до labels, не менять target. Если precision недостаточна, одна заранее объявленная ступень расширения, затем `inconclusive`.

5. **TLAB-004, retrieval.** Top200 past-popular+20 recent-distinct, заданные event/window/quotas/ties. Acceptance: C⊆U, Y независимо C, no future-positive insertion, отдельные U→C losses. ≤30 минут/6GB RSS на выбранном pilot; сначала 100 queries. Если исчерпан cap, batches/меньший sample, не скрытое сокращение истории. Низкое coverage открывает retrieval-задачу, а не новый feature experiment.

6. **TLAB-007, эвристики и ledger.** Те же Q/C/Y для popularity, last-view, recent-distinct; отчёт repeat/new-item/history/day и измеренная стоимость. Acceptance: tiny E2E сходится с oracle и нет пропавших zero-query. ≤30 минут. Сначала публикуется отрицательный/неопределённый результат; дополнительные heuristics не обязательны.

7. **TLAB-005, materializer18.** Registry фиксирует grain/window/missing/support. Acceptance: exact distinct multiplicity/expiry, category ID≠code, denominators и global peers проходят независимую проверку. Tiny→100 queries→pilot, ≤60 минут/8GB RSS. При превышении остановить масштабирование; менять batch/state, не подменять rolling calendar или exact approximate без новой версии.

8. **TLAB-008, CPU boosting.** Только после measured gates и проверки доступности зависимости. Один PairLogit и один query-weighted BCE, одинаковые кандидаты/колонки/бюджет; выбранный loss фиксируется до feature search. Acceptance: weights/pair mass, contiguous groups, temporal fit и validation report. ≤2 fits, ≤60 минут каждый, 2 threads. Недоступная RTX3070 ничего не блокирует: Mac CPU, меньший label-independent development sample. Установка — отдельное явно назначенное действие; незапущенный fit не описывать как результат.

9. **TLAB-009, первые ablations.** Counts → distinct/recency → category share, максимум четыре fits/2 CPU-часа. Acceptance: те же manifest hashes, paired Δ, supports/cost; диапазон неопределённости опубликован. Stop после лимита либо воспроизводимого отрицательного эффекта; не запускать новые окна до появления механистического основания.

10. **TLAB-016, automation pilot после baseline.** ≤12 feature candidates/4 validation fits/2 CPU-часа, включая failures/preparation. Grammar/random и proposed search получают равный бюджет. Acceptance: operator provenance и воспроизводимый ledger; улучшение только после увеличения бюджета не подтверждает преимущество алгоритма.

## Развилки, гипотезы и защита от deadlock

Не блокировать 001/002/006 ожиданием всех 58 notes, model/loss обзоров, GPU или окончательного пользовательского target. Они проверяют общие интерфейсы. Однако final-test lock действительно зависит от принятого протокола; его нельзя обойти pilot-обозначением. Слабый ranking pilot разрешает отдельный view→purchase experiment с новой единицей/метрикой, не переименование старой NDCG. Category ranking локализует item-level трудность, но не заменяет результат по товарам.

Новые HYP получают ID у координатора. Первый допустимый кандидат: **past-recent history добавляет coverage сверх popularity**. Mechanism: персональные повторы; counterhypothesis: union лишь увеличивает shortlist. Baseline: popularity220 против popularity200+recent20 на тех же Q/U/Y; budget: один TLAB-004 pilot, без fit; metric: all-target candidate Recall и cost по repeat/new-item; reproducibility: frozen hashes/ties/seed. Это отдельная retrieval-ветвь, не автоматическое изменение C для ablations.

Второй кандидат: **grammar search на проверенных primitives улучшает manual18**. Mechanism: комбинации grain/window; counterhypothesis: больше попыток или ослабленный manual. Baseline: strong manual плюс budget-matched random grammar; budget/metric: TLAB-016, paired validation NDCG@20 и подготовка/fit cost; reproducibility: frozen grammar, seeds, manifests, полный журнал попыток. До baseline это `needs-pilot`, не обещанный прирост. Новые идеи без mechanism/counter/baseline/budget/metric/reproducibility остаются research notes. Исчерпание бюджета завершает конкретный эксперимент; освободившийся слот переходит к следующей полезной задаче.
