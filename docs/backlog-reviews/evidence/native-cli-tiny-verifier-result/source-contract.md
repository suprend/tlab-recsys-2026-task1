# Граница source-verifier для tiny fixture

Этот note описывает исходный контракт `scripts/verify_development.py`, SHA256 `60519794c8c5b8bc7ac04f960e554f13ab3e125043c2a0e46d53f67ea0810ee0`, и принятые результаты двух вызовов. Source прочитан как текст; повторного выполнения нет.

`verify` читает уже существующие externally pinned collections и genuine expectations, реконструирует точный набор required pins и rehash consumed inputs перед завершением. Он не создаёт collection acceptance: исходные evidence сохраняют `acceptance_written=false`. Private expectation/control bodies не включаются в пакет.

Q/Y/C проверяются как полные source relations; F↔C tuples и user/anchor keys проверяются для всего rowset. Значения manual18 и metadata/support проверяются детерминированным sampler: bottom-hash limit4 на anchor плюс support strata. Generic policy остаётся `F_values=deterministic_sample_only`. На данном tiny fixture у каждой роли всего3 пары на один anchor, поэтому bottom-hash покрывает все3:54 formula и51 metadata/support checks на роль,108/102 суммарно. Нулевые missing/ambiguous/old-recency strata не считаются покрытием этих случаев.

Это совпадает с предыдущим независимым literal F review270 physical cells, но не доказывает формулы на произвольных источниках. Diagnostic query_coverage semantics наследуются от отдельного QYC review; verifier pin их сохраняет, но их rows не запрашивает. Source DB literal content наследуется от принятого builder и предыдущих physical reviews.

Контракт не выполняет `prepare_dataset`, float32 X/weights или native Pool/fit/predict/curve/selection/reload. Обычный native CLI и callback-abort этим результатом не проверены. Старые produced-unreviewed/pending records и source approvals не переименовываются задним числом.

SOURCE-worker review pins содержат private source/control snapshots и намеренно исключены; их точный путь/hash записан в [карте публикации](publication.json). В пакет входят только малые actual-results, aggregate role evidence и безопасные actual-output review originals.
