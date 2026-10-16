# Wave048 FIRST B — negative category-core audit

**Итог:0 strong defect candidates,0 новых IDs; existing005/001/014.** Сначала прочитаны actual tests. `test_manual_features.py:107–179` уже проверяет все18 значений на11 придуманных парах, отдельный SQL count/DISTINCT oracle, raw duplicates/expiry, metadata NULL-mixture/all-NULL, known-empty0, denominator0→NULL, смену категории без переклассификации старых событий. `:187–206` покрывает peers/future и позднее очищение metadata; temporal tests отдельно проверяют half-open endpoints/30-day coverage. Это synthetic coverage, не exhaustive full-data formula proof.

**Mechanism / ambiguity resolved.** Registry явно задаёт historical_event_category_id (`manual-18.json:6`). `_grain_sql` группирует исходный `e.category_id`, исключая NULL (`manual_features.py:139–142`); join использует query-current `m.category_id` (`:198`). Metadata берётся из последнего полного past timestamp bucket (`:175–185`). Known category определяется `IS NOT NULL`, не числовой truthiness (`:204–205`); ratio использует `nullif(denominator,0)` (`:223–227`). Исторический NULL не перекрашивается поздней категорией.

**Один непокрытый compound witness, не заявленный bug.** SourceStart=Oct1; query `(u10,i1,Oct8 00:00UTC)`. Литеральные `(time,action,user,item,category)`:

| time | action | user | item | category |
|---|---|---|---|---|
| Oct7 20:00 | view | 10 | 1 | NULL |
| Oct7 21:00 | view | 10 | 2 | 0 |
| Oct7 21:00 | view | 10 | 2 | 0 |
| Oct7 22:00 | cart | 99 | 1 | 0 |
| Oct8 00:00 | view | 10 | 1 | 999 |

**Prediction / ручной expected.** Последний peer исключён. Candidate category=0, missing=false, ambiguous=false; user_view_7d=3, user_category_view_7d=2, share=2/3; category_view_7d=2, item_category_view_7d=0, item share=0. User-category recency=10800sec; pair-view recency=14400sec; user distinct viewed items=2. Оба share_missing=false. Статические branches согласуются с этими значениями; mismatch не установлен.

**Nearest finite UNRUN regression / Task1 benefit.** При отдельном решении Root добавить одну direct-value conformance regression этой комбинации с actual manual18 registry; expected выписаны независимо от compiler. Share1 выявит historical-NULL reclassification, NULL вместо известных0/2/3 — category-zero handling. В просмотренных tests нет category_id=0, но отсутствие случая само по себе не дефект. Польза — защитить точный смысл существующих признаков, не менять формулы/модель. Никакого бюджета, нового gate/repair requirement или перезапуска closed caps; fixtures/tests/code не создавались и не выполнялись, peer048 unread.
