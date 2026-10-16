# Независимое review native-support assertion

Поддержанных P1/P2 нет. Единственная правка `tests/test_development_training_native.py:96–97` добавляет ожидаемый `informative_candidate_groups: 1` в exact-dict assertion.

Base SHA: `342f9ee58231af303dec09b1ee16220b9ab563ab10a334ee3da607dc5496222b`.
Candidate SHA: `eca8d1a071361a93e563b105b0c743f235073527876a49e81dd8080c2dea1887`.

Ручной разбор validation fixture (`:45–53`) и фактического `group_accounting`: counts=(3,2,0,2), positive=(1,0,0,0), negative=(2,2,0,2). Predicate `(positive>0)&(negative>0)` истинен только для первой группы, поэтому сумма равна 1. Три full-Y-positive запроса сохраняются, их candidate rows=3+2+0=5; empty-Y группа исключается selector. Current helper возвращает это значение в копии support, SHA `9f7d9ab7c1f69fd0726d657791059b4a0c5270bf7a32da898602eaf84ccffcc9`.

Удаление единственного добавленного поля восстанавливает весь base byte-for-byte: fixture, fit, selector, copy/shrink, prefix oracle и serialization assertions неизменны. `aef629d3…` в pins относится только к 1631 байтам function section, не полному train_baselines.py.

Native body **UNRUN**; PASS не заявляется. Только чтение/текст/SHA, без imports, tests, native/SQL/ML/data/models, Git/network/canonical writes/helpers/coordinator. Review не выдаёт runtime grant; решение об adoption остаётся Root. Все восемь input pins и copies свежие.
