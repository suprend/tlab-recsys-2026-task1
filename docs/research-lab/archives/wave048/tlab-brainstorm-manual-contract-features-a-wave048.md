# Wave048 A FIRST — production-контрпример не найден; NULL-дефект oracle

**Actual coverage, только чтение.**12 core tests уже проверяют18 значений на11 C-строках, отдельный SQL для raw/distinct expiry, latest metadata/null mixture, known-empty0/undefined ratio, observed-prefix recency, permutation/future suffix, multi-anchor и пустые таблицы. Temporal tests отдельно покрывают нижнюю/верхнюю границы, rolling/calendar, source coverage и глобальные peers. Это покрытие конкретных fixtures, не exhaustive proof18 формул на full data.

**Единственный кандидат:** существующий [Python oracle](/Users/mdpospelov/tlab-recsys-2026/tests/test_manual_features.py:67) считает `None` отдельным product; [аналогичная строка](/Users/mdpospelov/tlab-recsys-2026/tests/test_manual_features.py:71) — отдельным user. В RECORDS строки21–45 нет NULL user/product, поэтому текущий all18 тест этого не различает. Production [строка120](/Users/mdpospelov/tlab-recsys-2026/scripts/manual_features.py:120) генерирует COUNT(DISTINCT projection), исключающий NULL; [строка141](/Users/mdpospelov/tlab-recsys-2026/scripts/manual_features.py:141) глобально исключает timestamp anchor. Это дефект/пробел oracle, **не обнаруженная ошибка core SQL**.0 новых ID; refinement005/001/014.

**Буквальный trace, не fixture-файл.** Источник объявлен с Oct01; T=Oct08 00:00 UTC; Q=(u10,T), C={i1}. Все события view/category100:

| Time | user | item |
|---|---:|---:|
| T−2h |10|1|
| T−2h, exact duplicate |10|1|
| T−1h |NULL|1|
| T−30min |10|NULL|
| T, global peer |20|1|

Ручной expected: user_view7d=3, item_view24h=3, **обе distinct=1**, pair_view7d=2, pair_view_recency=7200s, user_category_recency=1800s, item_category_share=3/4. Off-C NULL-product event остаётся raw category denominator; peer не входит. Существующий oracle выведет обе distinct=2.

**Механизм/предсказание/ближайшая проверка — UNRUN.** Литеральный gold разделяет три поведения: raw bag сохраняет дубликат и NULL-проекцию, DISTINCT исключает NULL, peers исключаются глобально. Один будущий unit-case сравнивает production и существующий oracle с этим gold; ожидается production agreement/oracle mismatch. Сильный контроль — вручную заданные значения, а не второй set без NULL-фильтра. Если production расходится, уточнить причину; это пока статическое предсказание, не measured failure.

**Task1 benefit/cost:** исправить значение «independent all18 oracle», не менять features/model. Будущий case:5 invented events,1Q/1C,1 materialization и1 oracle evaluation,0 fits/Y/source scans; setup/checks/failures платные, allowance не выдан. Сейчас только исходники/TMP; Root отдельно решает unit-check/repair. Ни quality claim, ни новый gate, ни reset закрытых caps.
