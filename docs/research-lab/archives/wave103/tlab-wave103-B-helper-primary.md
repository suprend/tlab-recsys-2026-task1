# T-Lab wave103 B — независимая primary-source проверка

Режим: только официальная веб-документация Featuretools; без чтения репозитория, peer-файлов и данных, без тестов, SQL, моделей и сетевой записи. Проверено 2026-10-17. Это проверка документации, не эксперимент.

## Прочитанный объём

1. [Woodwork Typing in Featuretools](https://docs.featuretools.com/en/stable/getting_started/woodwork_types.html), Featuretools 1.31.0: получены и прочитаны строки 0–407 веб-представления (408 строк; вместе с навигацией и примерами). Опорные места: Semantic Tags 94–129; Woodwork in DFS 211–399, особенно 229–231, 285–398.
2. [Feature primitives](https://docs.featuretools.com/en/latest/getting_started/primitives.html), Featuretools 1.31.0: прочитано всё веб-представление 0–441 (442 строки) двумя выдачами 0–375 и 62–441. Опорные места: 37–42, 78–83, 220–274, 306–329, 378–401. Запрос stable-варианта этой страницы вернул HTTP 429; содержимое из него не использовано. Поисковая выдача служила навигацией; другие страницы из выдачи не открывались и не служат источниками выводов.

## Установлено по источникам

`input_types` и `return_type` описывают входное пространство типов и тип результата через Woodwork `ColumnSchema`; схема сочетает logical type и semantic tags и сама не привязана к данным. DFS выбирает допустимые столбцы по `input_types`, а схема результата позволяет последующее stacking. [Typing, 211–231 и 397–399](https://docs.featuretools.com/en/stable/getting_started/woodwork_types.html#woodwork-in-dfs).

В примерах: пустая `ColumnSchema()` допускает любой столбец; tag `numeric` включает Double/Integer/Age с этим тегом, но исключает integer index без него; `logical_type=Integer` допускает integer index; совместное требование Integer + numeric требует обоих условий. Для Age нужен вручную добавленный `date_of_birth`. Это примеры условий конкретных primitive, а не универсальное разрешение для всех вычислений. [Typing, 121–123 и 285–398](https://docs.featuretools.com/en/stable/getting_started/woodwork_types.html#by-semantic-tag).

Многовходовый primitive задаёт несколько входных схем: MeanSunday требует numeric и Datetime; результат — numeric. Документация отдельно показывает функцию вычисления и дополнительные атрибуты ограничения применения. [Primitives, 220–274 и 378–401](https://docs.featuretools.com/en/latest/getting_started/primitives.html#multiple-input-types).

## Краткие цитаты

Typing, суммарно 23 слова:
- «Only columns with the `numeric` tag apply.» (306)
- «The column must have logical type `Integer` and have the `numeric` semantic tag, excluding index columns.» (368)

Primitives, суммарно 25 слов:
- «A primitive only constrains the input and output data types.» (41)
- «This means they can be used to transfer calculations known in one domain to another.» (41)

## Предел вывода

Интерпретация прочитанного: декларации поддерживают отбор по типам и перенос/сочетание вычислений при подходящей схеме. Они сами не устанавливают эмпирическую полезность признака, улучшение качества модели, успешность transfer на конкретных данных или корректность доменного смысла присвоенного тега. В прочитанном объёме нет сравнительного эксперимента для T-Lab.

Равенство схем не устанавливает равенство формул или exact aliases. Единственная непосредственно описанная эквивалентность имён — варианты snake_case/camelCase/TitleCase для включённых primitive (пример time_since_previous/timeSincePrevious/TimeSincePrevious; Primitives, 80). На aliases функций или формул в другом проекте это свидетельство не распространяется.

Допустимый итог: документация подтверждает механизм типовой применимости и композиции; содержательные и эмпирические утверждения требуют собственного основания. Никакие новые gates или очереди не предлагаются.
