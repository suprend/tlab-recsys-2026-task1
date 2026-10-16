В проверенном CODE scope B поддержанных P1/P2 нет. Полностью прочитаны три кандидата; релевантный контекст сверён с замороженными требованиями. Source `aeb0a2e8…` остаётся кандидатом, все четыре теста UNRUN.

`scripts/itemcf_extraction.py:96–144` отказывает по descriptor, coverage и typed Q/C до callback/opener; 2*N и полный payload учтены до открытия. Для пустого batch descriptor не уменьшается. Владение переданным соединением определено явно: opener отвечает за собственный неуспешный open, `_owned` закрывает возвращённое соединение при SQL/limit/callback/BaseException; вторичная close-ошибка не заменяет первичную. Успешный close также предшествует конечному check/return.

SQL сохраняет view-only `[b−7d,b)`, глобальное исключение anchor peers, NULL-before-cap21, declared hash/ID ties и аудитории не-Q пользователей. Постинги не ограничиваются H21; каждый output-map содержит ровно C∪H21, включая известные пустые tuples. LIMIT members+1 обнаруживает overflow без выдачи частичного результата. Literal36events/2Q/3C согласованы с28 memberships и kernel-ожиданиями3/260,3/13 по ручному разбору.

Документация корректно отделяет shape/schema от caller-authenticated completeness и логический work/scan descriptor от физических CPU/RSS/IO. Callback не объявлен прерывателем blocked native SQL. Дополнительный framework, pilot, CLI или gate не требуется.

Граница тестовой осуществимости: тест импортирует `scripts.itemcf_extraction`; будущая fresh-TMP компоновка должна предоставить именно эту единственную module identity и неизменный `scripts.itemcf_projection`, чтобы классы dataclass/LimitExceeded совпадали. Один raw compile под произвольным именем этого не обеспечивает. Готового execution harness в scope нет; это условие загрузки, не обнаруженный дефект и не доказательство native PASS. DuckDB-совместимость/реальное cleanup-поведение ещё не проверены исполнением.

Все scope/candidate/context/original pins и snapshots повторно свежие. Рецензия только статическая: без candidate imports, SQL/native/tests/fixtures/данных/моделей/Y/Git/network/helpers/contact/canonical writes. Runtime/install acceptance не выдан.
