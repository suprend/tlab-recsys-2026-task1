# ItemCF V2 — focused DST rereview A

Root P2 закрыт **на уровне исходников**. `scripts/itemcf_extraction.py:109` переводит уже допустимый offset-zero anchor в `timezone.utc` до семидневного вычитания (`:112`) и проверки покрытия (`:113`). Для London 2020-10-26 нижняя граница теперь Oct19 00Z; фиксированные семь UTC суток согласованы с последующим naive-UTC SQL. Принимаемая область входов не сужена до одного конкретного tzinfo.

`tests/test_itemcf_extraction.py:103–118` содержит точный триггер: London anchor, покрытие Oct19–26 UTC, нулевые descriptors/limits, пустой Q и запрещённый opener. По исходнику V1 отвергает покрытие до empty-Q return; V2 доходит до `()` без открытия источника. Тест проверяет именно preflight-дефект, а не выполнение SQL.

Текстовые обратные преобразования подтверждены: удаление нормализации и дополнительного import восстанавливает production V1 byte-for-byte; удаление единственного нового test method и ZoneInfo import восстанавливает весь прежний test source, включая четыре тела. Документация описывает нормализацию и пять **UNRUN** случаев; runtime/source/resource полномочия не расширены.

Новых поддержанных замечаний в изменённой области нет. Все 33 входных pins и собственные copies повторно совпали. Production SHA `1981cd54e3a7c3737c3dde4da02b1ba0fdf6ee96f0b3514fdaeaba68adcb32bf`.

V1 no-findings и Root P2 сохранены: первый отчёт этот дефект пропустил. Все пять тестов остаются **UNRUN**. Импорты кандидатов, datetime/ZoneInfo вычисления, тесты, SQL/native/data/jobs не выполнялись. Это focused CODE-closure, не runtime/extraction proof или grant.
