# Автоматизация признаков для ранжирования покупок

По состоянию на 15 октября 2026, 14:36:14 UTC, TLAB-015 и финальный экспериментальный отчёт приняты. Механический Oct22 slice из новой DB воспроизвёл все признаки и816684 fixed-model scores без расхождений,0fit/Y; complete018 остаётся partial. Для завершения018 нужен публичный raw→freshcollections→frozenB/W training→comparison путь без privateCBMs/TMP/историческихclaims; финальный приростΔNDCG+0,005122 с95%CI[−0,010433;+0,018561] по-прежнему не доказывает превосходство.

Рабочий отчёт по первой задаче T-Lab. Ручной контроль настроен в пределах заранее заданного бюджета и независимо проверен. Четыре ветви автоматизации и неизменённое отложенное сравнение выполнены и независимо приняты; финальная разность положительна, её интервал включает ноль.

Подробные периоды, точные агрегаты и границы вывода — [принятое отложенное сравнение](backlog-reviews/real015-heldout-results.md). TLAB-015 done, 13 из19 задач приняты; задачи010–013 optional/deferred,014 active,018 partial.

## Что уже подтверждено

Реализован пайплайн, который формирует запросы, кандидатов и признаки из доступного прошлого и оценивает ранжирование по полному набору будущих покупок. После двух пробных моделей и ограниченного подбора настроек принят ручной CatBoost-контроль: conditional query-macro NDCG@20=0,458611, Recall@20=0,585127 на selection 22–23 октября. Его сохранённые модели, оценки и метрики независимо воспроизведены. Это результат выбора на development, поэтому он ещё не доказывает качество на новом периоде. [Приёмка контроля](backlog-reviews/tlab019-strong-output-verification.md)

Основной исследовательский вопрос остаётся открытым: может ли ограниченный автоматический конструктор признаков улучшить выбранный ручной baseline при прозрачном бюджете поиска? На development выбран автоматический блок с NDCG@20=0,464703 против 0,458611 у ручного контроля. Разность мала и её описательный интервал включает ноль; принятое отложенное сравнение также даёт небольшой положительный point estimate с интервалом, включающим ноль. [Условия задания](task1-requirements.md)

## Данные позволяют изучать действия и покупки

Используется REES46 Multi-category за октябрь 2019 года: 42,45 млн событий, 3,02 млн пользователей и 166,8 тыс. товаров. События представлены просмотрами, добавлениями в корзину и покупками. В данных есть время, идентификаторы пользователя и товара, категория, иногда читаемый код категории и бренд, наблюдаемая цена и идентификатор сессии. Названий, описаний и изображений товаров нет. [Схема и проверка данных](data.md)

Отсутствие покупки не является подтверждённым отказом: показы рекомендаций не наблюдаются. Для обучения непокупки среди кандидатов используются как условные отрицательные метки выбранного горизонта; выводов об онлайн-конверсии или истинной вероятности предпочтения из такого эксперимента не делаем. Отсутствие событий до начала месяца также не означает, что пользователь или товар новый.

## Запросы выбираются до чтения будущих покупок

В начале каждого дня по UTC выбираются пользователи с событиями за последние 48 часов. Детерминированная выборка ограничена 2000 пользователями в день и не зависит от будущих покупок. Для каждого запроса целевой набор состоит из всех различных товаров, купленных в следующие 24 часа; неполностью наблюдаемый горизонт не оценивается.

Кандидаты объединяют 200 товаров с наибольшим числом различных покупателей за предыдущие 7 дней и 20 последних различных товаров пользователя за тот же период. Повторы удаляются по идентификатору товара, будущие покупки не вставляются, список не дополняется после удаления дублей. Уже купленные товары могут появляться снова. Это приближение доступного каталога по прошлым действиям: фактическое наличие товара неизвестно. [Протокол](experiments/candidate-pilot.md)

Обучающие запросы охватывают 8–20 октября, их метки доступны к 21 октября. Проверочная выборка для текущих решений —22–23 октября; её метки доступны к 24 октября. Исходная доступность fit-компонента с 22 октября не означает, что весь последующий выбор настроек и признаков был готов тогда. Для итогового B/W-решения принят проект отдельного положительного интервала: 24 октября 12:00 после максимальной зрелости development-меток, до первого отложенного запроса 25 октября. Физические вычисления выполняются в 2026 году, календарь эксперимента — ретроспективный 2019 год. Reporting-only25 и финальные26–31 query-level targets открыты оценочными ролями только после принятых decision/prediction locks, all7 prediction seals/independent fullscore oracle и отдельного target gate; итоговые метрики/полный lifetime приняты отдельной Root receipt14:05:26UTC. Время поступления событий не наблюдается: считаем их доступными в event_time; задержки загрузки этим экспериментом не проверены. Общий EDA и хеширование источника использовали полный месяц — это не скрывается. [Разбиение и проверка данных](backlog-reviews/tlab017-collection-verification.md)

## Метрика сохраняет покупки вне кандидатов

Recall@20 измеряет долю будущих купленных товаров, попавших в первые 20 рекомендаций. NDCG@20 учитывает их позиции: покупки выше в списке дают больший вклад. Идеальное ранжирование определяется по полному целевому набору, включая товары, не найденные генератором кандидатов. Иначе метрика искусственно завышала бы результат retrieval.

Основное текущее сравнение — среднее NDCG по запросам с хотя бы одной будущей покупкой. Все 4000 проверочных запросов сохраняются: 73 имеют покупки; 96 целевых пар запрос–товар образуют полные наборы,65 из них присутствуют среди кандидатов. Отдельно считаются средние по всем запросам с нулём для пустого целевого набора, средние по пользователям и доля запросов с покупкой. Условная метрика не превращает будущее наличие покупки в признак или правило выбора запросов. [Определения и независимая проверка](backlog-reviews/tlab-006-verification.md)

## Пробные модели помогли выбрать рабочую процедуру

В пробном запуске использованы 6000 обучающих запросов и 1,23 млн пар с кандидатами. Только 114 запросов имеют покупки в полном будущем наборе;92 имеют одновременно найденные положительные и условно отрицательные кандидаты. Небольшое число полезных целевых наблюдений ограничивает точность сравнения.

Обе модели используют одинаковые 41 числовой признак, одинаковые кандидаты и фиксированные 50 деревьев глубины 6. Признаки включают контекст retrieval, счётчики пользователя/товара/пары, давности и категориальные доли. Числовые user_id/item_id в модель не поступают. Для Logloss сумма весов кандидатов одного запроса равна 1. Это уравнивает запросы-дни, не пользователей или положительные строки; обучение включает зрелые полностью отрицательные группы и не является прямой оптимизацией conditional-positive NDCG. PairLogit обучается только на информативных группах, с равной суммой весов пар на группу; полностью отрицательные запросы остаются в оценке. Нативная метрика CatBoost и ранняя остановка не выбирают контрольные точки. [Модель и веса](experiments/boosting-baselines.md)

| Метод | NDCG@20 | Recall@20 |
|---|---:|---:|
| Популярность | 0,1059 | 0,2339 |
| Недавние взаимодействия первыми | 0,3884 | 0,5714 |
| CatBoost Logloss, 50 деревьев | 0,4144 | 0,5812 |
| CatBoost PairLogit, 50 деревьев | 0,3752 | 0,5714 |

Значения относятся к одной и той же выборке 22–23 октября и 73 запросам с покупками. Logloss выглядит полезным рабочим ориентиром для следующего ограниченного эксперимента; этот результат не доказывает, что Logloss в целом лучше PairLogit. В этом пробном запуске настройки ещё не подбирались; последующий подбор описан ниже. Период уже просмотрен, а повторные попытки увеличивают риск случайного выигрыша. [Эвристики](backlog-reviews/tlab-007-verification.md), [бустинги](backlog-reviews/tlab008-smoke-output-verification.md)

## Новые признаки сначала проверяются по исходным строкам

Один рассматриваемый блок добавляет бренд, числовой ID категории как номинальное значение, читаемый код категории и относительную цену. Все свойства берутся из последнего глобального момента строго до запроса, с учётом всех строк и пользователей в этот момент. Пропуски и конфликты сохраняются; более старое удобное значение не подставляется.

Читаемый код восстанавливается по числовому ID только при единственном известном коде в прошлом. Для цены строится ориентир по другим активным товарам текущей категории, включая товары вне кандидатов. Неизвестная цена, нулевая цена и конфликт цен различаются. Это последняя наблюдаемая прошлая цена, а не гарантированное текущее предложение магазина. [Определения](experiments/metadata-price-features.md)

После принятого пилота на 100 запросах выполнен полный расчёт: 30000 запросов и 6,13 млн пар на 15 днях. Расчёт занял 66,95 с реального времени и 89,56 процессорных секунд, пик памяти — 2,24 ГиБ. Независимая проверка за 54,46 с реального времени и 69,93 процессорных секунд сверила все 110415726 добавочных значений, каждую строку происхождения и 1,86 млн строк ценовых ориентиров. Совпадение подтверждено; числовые ID/NULL сохраняются без pandas-округления. [Полная source/cost приёмка](backlog-reviews/tlab009-full-source-verification.md).

Единственное заранее разрешённое сравнение выполнено на тех же 6000 обучающих и 4000 проверочных запросах. С метаданными NDCG@20 снизился с 0,4144 до 0,4004, Recall@20 — с 0,5812 до 0,5450. Независимый расчёт воспроизвёл все 817149 сохранённых scores, полные целевые метрики, параметры модели и парный bootstrap.

Блок не прошёл заранее закреплённое правило сохранения и отклонён целиком; следующие эксперименты используют исходные 41 вход. Повторного обучения или подбора блока после результата не было. Это отрицательный результат конкретного ограниченного эксперимента, а не доказательство бесполезности бренда или цены вообще. [Проверка, стоимость и правило решения](backlog-reviews/tlab009-model-output-verification.md).

## Ручной контроль выбран из ограниченного набора настроек

После отклонения блока метаданных выполнены четыре заранее заданных обучения Logloss: глубина 4 или 6, L2 3 или 30, по 300 деревьев. Оценивались фиксированные префиксы 50, 150 и 300 деревьев: это 12 зависимых проверок, а не 12 независимых обучений. Совместимый пробный контроль также оставался явно указанным участником выбора. Проверка памяти разрешила все 26000 обучающих запросов; кандидаты, веса и исходные 41 числовой вход сохранились.

Выбран контроль с глубиной 6, L2=30, 300 обученными деревьями и префиксом 300. На 4000 selection-запросах его conditional query-macro NDCG@20 равен 0,458611, Recall@20 —0,585127. По всем запросам с нулём для пустого Y NDCG равен 0,008370; условное среднее опирается лишь на 73 запроса с покупками. Улучшение относительно пробной модели отражает одновременно популяцию обучения, число деревьев и настройки: отдельный вклад этих изменений не установлен. Это ограниченный настроенный контроль для данного эксперимента, а не доказательство оптимальности CatBoost.

Первоначальный запуск независимой проверки остановился из-за неожиданного системного дочернего процесса при определении платформы. Ошибка и её стоимость сохранены. Отдельный разрешённый проверяющий без новых обучений воспроизвёл все 12 префиксов, оценки, четыре варианта усреднения и парный bootstrap; контроль принят с отдельным учётом полного времени исполнения. Консервативная стоимость всего исследования контроля — 1666,94 CPU-секунды. [Результат и границы проверки](backlog-reviews/tlab019-strong-output-verification.md)

## Автоматизация создаёт ограниченное пространство программ признаков

Конструктор получает объявленные сущности, типы, события и временные окна, генерирует программы и проверяет их зависимости. Привязки схемы и семейства операторов заданы человеком; обученной политики поиска здесь нет. Из восьми допустимых блоков заранее выделены две осмысленные и две случайные ветви. Каждая добавляет к B41 ровно три физических столбца, включая необходимые маски. Общий источник содержит 12 новых столбцов, но модели B+12 в эксперименте нет.

Осмысленные ветви проверяют суточные счётчики пары пользователь–товар и давность корзины вместе с суточным счётчиком корзины товара. Случайные ветви проверяют суточные счётчики пользователя и числа различных пользователей товара в заданных окнах. Все четыре наследуют выбранную обучающую популяцию, веса, параметры и префикс ручного контроля. Разрешены четыре обучения и четыре просмотра selection-результатов, без замены неудачной или дублирующейся попытки. Общий лимит —7200 CPU-секунд с учётом расчёта источника, неудач и проверки.

Источник уже рассчитан для 30000 запросов и 6134207 пар на 15 днях. Первоначальное объединение в широкую таблицу остановилось по памяти после сохранения дневных файлов. Исходная ошибка сохранена; повторной генерации признаков не было. Разрешённый независимый проверяющий сверил все 73610484 дополнительных значения, ключи Q/C и сохранение исходных 45 полей. Несовпадений нет. Консервативная стоимость исходного расчёта и восстановления проверки —177,72 CPU-секунды. Это приёмка источника, качество модели из неё не следует. Исчерпывающая raw-проверка 12 новых столбцов не повышает прежнюю выборочную проверку 18 ручных формул до исчерпывающей; физическое сохранение B45 проверено для всех строк. [Полная проверка источника](backlog-reviews/tlab016-recovered-source-verification.md)

Победитель W выбирается среди B и четырёх исходных ветвей по заранее опубликованному правилу: Recall@20 не ниже B минус 0,002, затем максимальный conditional query-macro NDCG@20 с фиксированной полосой численного равенства и предпочтением меньшего числа добавленных физических столбцов. W может оказаться исходным B. Победа случайной ветви поддержала бы полезность конкретного автоматического пространства, но сама по себе не доказала бы превосходство осмысленной стратегии поиска. [Программы](experiments/feature-programs.md), [правило выбора](experiments/feature-program-selection.md)

Четыре исходных обучения и единственный независимый проверяющий завершились. Все модели использовали 26000 одинаковых обучающих запросов, 300 деревьев, одинаковые веса и настройки B. Проверяющий независимо восстановил входные матрицы и массу запросов, воспроизвёл все 817149 selection-оценок каждой ветви, порядок товаров, параметры, четыре варианта метрик и парный bootstrap; новых обучений не было.

| Вариант | Дополнительный блок | NDCG@20 | Recall@20 |
|---|---|---:|---:|
| B | ручные41 | 0,458611 | 0,585127 |
| I1 | суточные счётчики пары | 0,460022 | 0,590020 |
| I2 | давность/счётчик корзины | 0,425043 | 0,555773 |
| R1 | суточные счётчики пользователя | 0,449530 | 0,605675 |
| R2 | различные пользователи товара | **0,464703** | **0,591977** |

Правило выбрало R2/L05: число различных зрителей товара за 24 часа, пользователей с корзиной за 7 дней и покупателей за 24 часа. Разность NDCG относительно B равна 0,006092. Описательный парный bootstrap по пользователям, 200 повторов, даёт интервал [−0,003207; 0,021294]. Он выполнен после выбора на том же development и не доказывает улучшение обобщения. Победила случайная ветвь внутри заданной человеком grammar; превосходство осмысленного поиска не установлено.

Правила конструктора, приоритеты осмысленных ветвей и общая процедура разрабатывались с уже известными результатами 007/008/009; ручной B выбран в 019 на тех же 73 положительных selection-запросах. Заморозка правила выбора до результатов 016 ограничивает текущий выбор, но не делает весь дизайн label-blind. Четыре новых просмотра 016 не описывают всю историю решений с учётом development-результатов.

Консервативная стоимость расчёта источника, четырёх обучений и независимого проверяющего — 1694,75 CPU-секунды; отдельная внешняя проверка доказательств и её хвост покрыты верхней границей 10 секунд, общая верхняя граница — 1704,75 при лимите 7200. Консервативная сумма пиков памяти основного и дочернего процессов — 5,92 ГиБ. Исходная ошибка расчёта источника сохранена; повторной генерации признаков, нового запуска модельного проверяющего или повторного обучения не было. [Приёмка моделей и все ограничения](backlog-reviews/tlab016-feature-program-model-verification.md)

Зафиксирован будущий контраст ровно B против W=R2. [Принятый контракт](experiments/heldout-contract.md) задаёт reporting-only25 и финальные26–31, положительный simulated compute gap и все семь дней предсказаний до любого queryY. Cores, oracle-адаптеры, lifecycle/context helpers и outer owner приняты на уровне CODE; [фактическая шестиролевая B=W toy integration](backlog-reviews/six-role-toy-v2-output-verification.md) также независимо принята в своём узком scope. Дополнительный [chosen3 W44 V3 запуск целиком завершился exit1](backlog-reviews/chosen3-v3-failure-checkpoint.md): отдельный setup fit и шесть успешных worker exits не заменяют whole-output acceptance. [V4r1 исправление кода и существующие synthetic worker-выходы независимо приняты](backlog-reviews/chosen3-narrow-acceptance.md) отдельно от неудачного outer запуска; новые success artifacts или retry не создавались. Дополнительное toy-обучение для этого узкого вопроса не требуется. Позднее отдельно приняты conditional33914/43200 basis, exactV4/de1e request и четыре actualRootgates; FIRST-owner sixroles завершилисьexit0, targets открыты лишь после all7 prediction seals. Итоговая whole015/metric/lifetime приёмка принята отдельной Root receipt; finalNDCG B=0.459825/W=0.464947, CI разности включает0.

## Воспроизводимость и пределы вывода

Код, зависимости, протоколы и агрегированные результаты сохранены в репозитории. Исходные события, модели, таблицы Q/C/Y и локальные approvals не входят в clone. CLI независимой source-проверки принята для уже запечатанных ручных коллекций. Typed9 source-import kernel и outer owner v8 CODE accepted; [фактический tiny fresh-process импорт четырёх искусственных строк](backlog-reviews/source-import-tiny-v5-output-verification.md) независимо принят. Полное восстановление новых коллекций/подтверждений из raw источника ещё не выполнено; [Полный source-only импорт завершён и typed9 source-prefix отдельно принят](backlog-reviews/full-source018-source-prefix-acceptance.md) после независимой проверки existing outputs. Оригинальнаяsession65471 REAPED exit0, no poll/retry. Исходные pending-флаги сохранены; отдельная Root receipt не завершает018/source-to-model и не разрешает heldout. Publisher большие файлы не читает/хеширует. Отдельная source-free CLI уже воспроизвела публичный пример из 12 синтетических строк в перенесённой папке без данных, artifacts и локальных approvals; это проверка арифметики и интерфейса, а не восстановление реального источника или retraining. [Команда и границы](experiments/fresh-clone-reproduction.md). Имеющийся аудит исполнения не заменяет полный запуск реального пайплайна из чистого clone. [Проверка воспроизводимости](backlog-reviews/tlab-fresh-clone-reproducibility-audit.md)

Остаётся измерить неизменённый B/W-контраст на отложенном периоде и практически воспроизвести доступные шаги реального пайплайна. Исследование не измеряет сэкономленные часы ручной работы, онлайн-конверсию, причинный эффект рекомендации или перенос качества на другой магазин. Совместимость операторов с синтетической схемой проверяет переносимость кода; качество на другом реальном датасете требует отдельного эксперимента.


## Исторический checkpoint — 15 октября 2026, 06:52 UTC / 09:52 МСК

Следующие датированные разделы сохраняют состояние на момент записи; текущий статус приведён в начале отчёта.

Первый фактически проверенный срез задачи уже существует: временной Q/C/fullY-пайплайн, ручной B41, generated pool из8 допустимых блоков и четыре обучения B+3 выполнены на development и независимо приняты. B даёт NDCG@20=0,458611; выбранный R2 —0,464703. Описательный интервал разности включает ноль. Это проверенная работающая процедура и development-результат; reporting25–31 остаётся pending, качество на новом периоде не установлено. [Приёмка016](backlog-reviews/tlab016-feature-program-model-verification.md), [подробный report draft](experimental-report.md).

Reproduction018 пока не завершён. Kernel принят на50 unique tiny cases; owner v8 установлен по exact reviewed bytes и прошёл53 installed-location author checks отдельно от9 safety+2source-snapshot probes. Эти проверки используют искусственные/metadata seams; они не подменяют tiny fresh-process harness или фактический raw import. Два более широких native OS preflight завершились EPERM при инвентаризации посторонних процессов; это сохранённые compatibility failures. Следующий безопасный runtime-шаг выбирает Root после независимого review узкого owned-family observer/harness и точного request, до любых application/model/source jobs. [Owner acceptance](backlog-reviews/evidence/source-import-owner-v8-code-acceptance.json), [native failure](backlog-reviews/evidence/root-observer-native-compatibility-failure.json).

Исследование продолжается независимо от этих execution gates. Шесть canonical research HYP139–144 имеют needs-pilot статус; новые002/003 proposals и negative findings ещё не означают разрешения fit. Две текущие blind004 авторские линии изучают AmazonReviews2023 и RetailRocket; отдельный скептик проверит перенос по исходным источникам после freezes. Canonical очередь исполнения остаётся [backlog](backlog.md), журнал и results/reviews — [research log](research-lab/brainstorm-log.md). Новые идеи не откладывают существующие015/018/report задачи и не сбрасывают их пределы.


## Исторический source-free checkpoint — 07:19 UTC / 10:19 МСК

Root принял ограниченное доказательство переноса: восемь original symbolic/literal cases, без повторного запуска, реальных внешних данных, ML или качества. Amazon reviews не идентифицируют полный24h purchase target; условный RetailRocket adapter и provenance различия RelBench остаются отдельными contracts. [Scope acceptance](research-lab/brainstorm-wave004-root-literal-review.json).

Исправленный supervisor V6 принят Root на уровне кода. При подготовке запуска найдено отдельное сопоставление путей `/tmp` и `/private/tmp`; оно остановило подготовку до application jobs. Новый source-harness freeze проходит focused review. Фактический tiny setup/шесть ролей и raw import ещё не приняты; очередной source-free repair не выдаётся за успешно выполненное воспроизведение. Две независимые author006 линии уже исследуют следующий typed-AST operator search, а отдельный skeptic проверяет005;07:30UTC checkpoint и priority015/018/report сохранены.


## Историческая приёмка обеих tiny integration — 07:54:55 UTC

Root и независимые проверяющие приняли фактический source-import smoke на четырёх искусственных строках и шестиролевой toy pipeline: одно setup-обучение на восьми строках и шесть завершившихся ролей на13 запросах/25 кандидатах. [Source proof](backlog-reviews/source-import-tiny-v5-output-verification.md) и [six-role proof](backlog-reviews/six-role-toy-v2-output-verification.md) сохраняют исходные receipts, ограниченные проверки и exact tested code; DB, модели и raw artifacts в Git не входят.

Эти проверки закрывают ранее ожидавшиеся tiny lifecycle/output gates в их узком scope. В toy B=W, historical consumer заменён stub; native chosen3, full-source bootstrap, fresh environment, production capacity и качество на реальном отложенном периоде не доказаны. Reserved25–31 остаются закрыты. Для исторического бюджета теперь найден исходный completed ingest21.557s и download582.334s из tool metadata; вложенные20.8s не добавляются. Новый cost ledger и независимая приёмка actual request ещё нужны — автоматического разрешения реального запуска нет.

## Полный source-prefix — фактическая приёмка 15.10.2026 10:34:34 UTC

Принят строгий typed9 source-prefix полного месяца: 42,448,764 строк, исходная операция exit0 и отдельный независимый byte/metadata review exit0. Консервативная charge 629.91 CPU с review входит в исходный 7200 CPU/10800 wall; sampled aggregate RSS 1,944,485,888 B отдельно от MAXRSS 1,915,109,376 B. Независимый reviewer прочитал пять больших физических файлов один раз; DB не открывал, SQL/model/queryY не выполнял. Приёмка опирается на принятый kernel, native schema/aggregate conformance и byte binding, не на независимое сравнение каждой ячейки DB. [Область и доказательства](backlog-reviews/full-source018-source-prefix-acceptance.md).

CostV2 37697 отклонён до конечного independently reviewed QA/agent census; старые 4096/128 количественно не обоснованы. Новые census-числа не публикуются до review. Complete018, чистый source-to-model bootstrap и отложенная проверка ещё впереди; original pending flags и chosen3 FAILED не переписываются.

## Текущий код и условная оценка времени —15.10.2026 11:53:27UTC

[Scoped acceptance](backlog-reviews/development-v2-and-conditional-wall-acceptance.md) сохраняет ownerV2/parityV2/portable CODE review, исправленные реальные code-review defects и исходные failures. Принятый код установлен exact-byte; проверены только байты и compilation, без нового suite/native/data/model запуска. Это подготовка механического source-to-fixed-model повтора, не его фактический успех.

Пять стадий условного бюджета33914/43200 active-WALL представлены целиком declared upper, measured=0. Root явно принял конечный cohort/managed-terminal/workload/reserve assumptions; aggregate historicalCPU остаётся неизвестным. Условная retrospective feasibility не становится измеренным завершением, runtime grant, свободным остатком для новых работ или качеством модели. Actual600CPU/900wall, real015/25–31 остаются CLOSED; complete018 pending. Исходные29412/37697 rejections и chosen3FAILED сохранены. [018/019 research refinements](research-lab/brainstorm-waves018019-synthesis.md) не добавляют обязательных gates.

## Actual018 submission —15.10.2026 12:01:55UTC

[Original operation](backlog-reviews/development-whole018-launch.md) submitted once as98791/chunk1b7294 under600CPU/900wall/8GiB, atmost2nativepredictions,0fit/0Y. Root-onlypoll/reap; output/parity/lifetime acceptance pending, no success inferred. Earlier ungranted entries are immutable prelaunch snapshots. Conditional33914/43200 wallbasis and real015 CLOSED are unchanged; requestpayload/data/models are not published.

## Actual018 terminal failure —12:05:15UTC

Original98791/e2f5ba EXIT1,1Bmodel load/0predict/0fit/0Y; Native effective parameter differs in heldout_predictions.verify_model. Partial Q/C/B45/extras are unaccepted, no parity/ownerreturn. Rootexternal5.49wall/8.52CPU, MAXRSS1,952,514,048B distinct from sampledaggregate1,977,745,408B; V6unknowntrue retained. Separate15CPU/30wall Bload diagnosis is not a retry or quality experiment. Source-prefix accepted, real015 execution held on this verifier dependency; pureprep cancontinue/no015grant.

[Original failure receipt and resource limits](backlog-reviews/development-whole018-failure.md) distinguish the measured reaped command from UNKNOWN full-tree actual-totalCPU. Separately accepted inert015 metadata packing is not a runtime grant; its shared verifier dependency remains held.

## Узкая диагностика и pending repairs —12:29:20UTC

[Observed diagnosis/cost scope](backlog-reviews/native-param-diagnosis-and-cost.md) retains exactly one B-load expectedRED, two captured float differences and Root later literal checks; W not loaded. Diagnosis is not a fix/runtime/source acceptance. VerifierV1 list-origin P2 and wrapperV1 two exception-audit P2s remain pending versioned repair, no protected code installed. Engineering costs are separate under unchanged-model/decision conditions;33914/43200/1000/300 are not refilled. Original018FAILED/unknownflags and real015closed unchanged.

## Cadence checkpoint14:15 — фактическая запись 2026-10-15T14:16:14.976108+00:00

Root фактически прочитал clean HEAD85660b1 и опубликованные accepted015 результаты. Wave026 реально назначена двум независимым FIRST авторам features_a/models_b по Root14:14observations; A FIRST уже получен/триSHA проверены, B ещё работает, peerтексты доFIRST не смешиваются. Отдельный существующий retrieval_a skeptic может быть вызван только после обоих exactFIRST;025skepticcomplete/Rootfullreadbackpending. Reportproposal7be5123 frozen у независимого source_harness_review,018 только TMPconstanttransport уexecution_scope_audit без runtimegrant. Текущие science/limits/11fits19looks не меняются; никаких повторных оценок открытого final.

Actual cadence write опоздал на 74.976108s к исходному14:15UTC; своевременная публикация результата14:11:04 сохранена отдельно. Следующий максимум15:00UTC/18:00МСК строго от исходного14:15, либо раньше после двух completed research rounds. Следующаяwave027 planned по тому же контракту после текущих FIRST+отдельногоreview; назначение/active status не выдумываются, Root остаётся владельцемdispatch. Единственный backlog/координатор/goal/17slots и разрешения прежние.

## Принятый final-report и018 CODE-only transport — 2026-10-15T14:29:47.608152+00:00

[Финальный отчёт и отдельная текстовая приёмка](backlog-reviews/experimental-report-heldout-v2.md) установлены byte-exact; MAINreportreviewDONE,13/19 unchanged. Historical numerical-source ledger остаётся snapshot прежней редакции, новые heldout aggregate/Root источники вынесены отдельно. [018 literal transport](backlog-reviews/018-recovery-literal-code.md) меняет только один code pin, не алгоритм или модель; source-only compile/pin checks,0runtime/tests/стейджинг. Complete018partial, separatelyissuedRoot37979 RUNNING/outputpending, Rootonlypoll; closedsource7200/10800 не общий баланс018.

Wave026обаFIRST actualSHAverified, existingretrieval_a separatecritic activated afterboth/idlecheck; no peerread beforefreeze.026research ещё неRootaccepted, noIDs/grants;027 assignment невыдумывается. next_due15:00UTC anchored14:15, priorlate74.976108s retained.

## Actual018 recovery submission overlay — 2026-10-15T14:31:37.795697+00:00

[Root отдельно issued/submitted37979](backlog-reviews/018-recovery-launch.md), RUNNING по Root14:28metadata; fulloutput/parity/lifetime не приняты. Новый600CPU900wall8GiB отдельнооплачен; old600900declareddebit/source720010800nonfungible/oldunknownimmutable, noaggregate018balance.2predmax/0fitY439/no015reexecution/noautomaticretry. Rootalonepolls, publisher0poll/largehash/data/model/jobs; complete018partial и freshtraining не заявлены. MAINreportreviewDONE/015done13of19/next15:00UTC anchored14:15 unchanged.

## Accepted018mechanical slice / early two-round checkpoint — 2026-10-15T14:36:14.657414+00:00

[RootacceptedOct22slice](backlog-reviews/018-accepted-oct22-slice.md): original37979 REAPED/CLOSED894474exit0,2000Q/408342C/allB45+chosen3/2nativepred/816684keyedscores/maxerror0/fullranks.0fit/Y/newmetricselection;Originalproducerpendingflags/oldfailedunknownimmutable. Full018partial/publicraw→freshcollections→frozenB/Wtraining→comparisonroute pending; source-to-fixedscores в существующемruntime неfreshtraining/cleanenvironment. MAINreportreviewDONE/015done13of19.026distinctskepticcomplete14:32:34/Rootreadbackpending;025+026critiquescomplete triggers this earlycheckpoint, nextmax15:00UTC anchored14:15 unchanged/no newdeadline. Newpublicrouteimplementation owner назначаетRoot, активныйпуть невыдумывается; noextraY/refits/currentretune.

## Existing018 public route implementation /026 reviewed — 2026-10-15T14:41:57.745344+00:00

[Completion audit/Root acceptance](backlog-reviews/task1-completion-gap-audit.md) clarifies the existing public raw→freshcollections→NEWfrozenB/Wtraining→comparison gap. execution_scope_audit TMPimplementation nowactive, independentseamreview source_harness_review; noactualfreshfits/integration/runtimegrant. ReportV2/fixedscoreslice accepted separately;29auditcodepins historicalnotrehashcurrent.026research-only refinements accepted,027independentpair actualstarted/Afrozen/Bwriting; no mainprerequisites/newIDs/admissions.15:00UTC anchored14:15 unchanged.

Wave027update 2026-10-15T14:44:16.119811+00:00: bothFIRST/currentbytesSHAverified, distinctexistingFeaturesAskepticactive. B originalFIRSTprefixecb6c139 vs append-correctedcurrent8877a138 explicitly preserved; no falseunchangedclaim. Existingpublicroute synthetic<=32eventFakeCatBoost integration only withinRoot60CPU120wall512MiBscope; realfreshfits/Y ungranted.
