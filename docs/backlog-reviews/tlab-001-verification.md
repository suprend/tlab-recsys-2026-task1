# TLAB-001: независимая проверка временного контракта

15 октября 2026. **Verdict: accept для TLAB-001. Материальных дефектов в проверенном scope не найдено.** Это не приёмка полного feature pipeline, ranking protocol или baseline.

Прочитаны фактические [temporal_contract.py](../../scripts/temporal_contract.py) и [test_temporal_contract.py](../../tests/test_temporal_contract.py), сопоставлены с [планом B2](verification.md). Оба файла на момент проверки были untracked: обычный `git diff --` пуст, поэтому проверены полные новые файлы, а не вывод об отсутствии изменений. Статус Root не использовался как доказательство. Репозиторий, Git, данные, зависимости и проверяемый код reviewer не менял; subagents, установки и обучение не запускались.

## Фактическое исполнение

Из корня проекта запущена только разрешённая группа:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_temporal_contract.py -v
```

**Результат: exit code 0; Ran 12 tests in 0.011s; OK.** Общий suite и незавершённая TLAB-002 не запускались. DuckDB oracle использовал отдельную in-memory database с шестью вымышленными событиями; реальные логи не читались. Отключена запись Python bytecode.

## Проверенный смысл API

- **UTC и интервалы.** `_utc` отклоняет naive/не-datetime значения и нормализует aware datetime до UTC. Нормализация выполняется до арифметики duration и календарного midnight. История действительно `[t−W,t)`: левая граница включена, все peers на t исключены. `closed_utc_days` возвращает закрытые по завершению UTC-дни, отдельно от rolling history. Нулевая/отрицательная duration и невалидный days отклоняются. [Код](../../scripts/temporal_contract.py#L17), [содержательные boundary/calendar/timezone tests](../../tests/test_temporal_contract.py#L26).
- **Target и зрелость.** Оба endpoints обязательны и должны быть bool; проекту не навязывается выбранный target. Для cutoff c и неотрицательной задержки δ код сравнивает конец target с `c−δ`: right-open допускает равенство, right-closed требует строгое неравенство. Это соответствует доступности событий строго до cutoff, включая случай покупки ровно на правой границе. Положительная задержка и запрет отрицательной проверены исполнением. [Код](../../scripts/temporal_contract.py#L71), [тесты](../../tests/test_temporal_contract.py#L72).
- **Coverage и возраст.** `source_coverage` вычисляет длительность пересечения окна с `[S,E)`; первый observed event пользователя в формуле не участвует. `observed_history_age` возвращает missing для None, tied и future first observation, положительный возраст только для строгого прошлого. Проверены ранний октябрь, нулевое покрытие до/после источника и полное 30-дневное окно только 31 октября. [Код](../../scripts/temporal_contract.py#L104), [тесты](../../tests/test_temporal_contract.py#L51).
- **Глобальные timestamp batches.** Группировка использует только нормализованное время, не user/item, сохраняет все peers и не сортирует их искусственно. Пустой stream допустим, обратный порядок вызывает ошибку. Возвращаемый tuple позволяет потребителю сначала прочитать весь batch, затем обновить state. Именно такой порядок исполняет тестовый replay; six peer permutations и future suffix не меняют прошлые результаты. [Код](../../scripts/temporal_contract.py#L147), [replay и invariance](../../tests/test_temporal_contract.py#L102).

## Почему проверки не являются зеркалом реализации

Ручной golden результат `a:0,b:0,c:2,d:3,e:0,f:2` независимо фиксирует межпользовательские same-second peers, точное включение левой границы, expiry старых строк и другой item. SQL oracle читает исходную fixture table и сам задаёт `h.time >= a.time − INTERVAL '1 day' AND h.time < a.time`. Он не вызывает `TimeInterval.contains`, batching или общий production predicate. Поэтому ошибочная граница Python не копируется автоматически на SQL-сторону. Равенство сверяется и с oracle, и с ручными числами. [Oracle](../../tests/test_temporal_contract.py#L114).

Это meaningful маленький интеграционный replay для primitives. Он не доказывает правильность будущей материализации distinct, metadata, layers, candidates или metrics: таких production components в TLAB-001 ещё нет. Добавлять их проверки заранее как тысячи microtests не требуется.

## Ограничения при использовании и ближайшие проверки

**Неблокирующие оговорки, не material findings:**

1. `SourceCoverage.complete` означает полную **длительность** пересечения, а не label maturity. Для right-closed target, заканчивающегося ровно на exclusive source_end, длительность может быть полной, хотя конечный исход недоступен. Для допуска labels использовать `label_is_mature` с cutoff не позже доступной границы источника; не заменять его coverage. Текущие history windows right-open, поэтому эта оговорка не нарушает их контракт.
2. `timestamp_batches` документирует read-before-update, но не управляет внешним mutable state. Следующий production consumer обязан сохранить batch-порядок; принимать его только по тестовому `_replay_counts` нельзя. Также функция streaming: ошибка позднего несортированного suffix не откатывает уже обработанные batches.
3. Label maturity проверяет правую доступность, а не полноту начала/внутренних участков источника и не as-of cutoff encoder/priors. Эти отдельные gates должны появиться при сборке protocol manifest и fitted components. TLAB-001 их выполнение не заявляет.

При ближайшем расширении достаточно нескольких точных дополнительных случаев: right-closed label с положительной δ на равенстве и секунду позже; частичное правое пересечение source; peers одного instant в разных UTC offsets. В текущем коде соответствующие ветви прочитаны, ошибки не обнаружены; отсутствие этих дополнительных regression cases не блокирует TLAB-001.

**Необходимых исправлений до принятия TLAB-001 нет.** Следующая независимая проверка должна охватить actual feature consumer, exact distinct expiry и разделение features/candidates от labels, затем tiny end-to-end pipeline по B2.
