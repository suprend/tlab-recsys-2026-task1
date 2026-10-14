# TLAB-017 runtime: повторная независимая проверка retry fix

15 октября 2026. **Вердикт: accept runtime code scope для проверенной frozen версии.** Материальный resume finding из [первоначального review](tlab017-runtime-review.md) закрыт actual code и независимым воспроизведением. Первоначальный repro/failure audit сохраняется, не переобозначается как успешный запуск. Это не017done, не collection acceptance, не trained baseline и не открытие confirmation.

Проверены [actual runtime](../../scripts/development_collection.py), [scoped tests](../../tests/test_development_collection.py) и [документация](../experiments/development-collection.md). Repo/Git/code/deps/data не изменялись, Root008 не проверялся, production/October source не запускались и не читались. Дополнительные сценарии использовали только изолированные tiny synthetic fixtures с настоящими accepted producers.

## Frozen version и actual tests

SHA-256 runtime: `d3d811e7987812366d36163537bdd8784ccb55ef3e1596ba7bf6d02338f80f3c`.

SHA-256 tests: `adf2688898f8d6ec597b5f7ed5263fd48c1e3877695f9724b05a2134291a940a`.

SHA-256 documentation: `07ecce21e2f603f605612ed5b94942b3aba95c8f06a693b98d8b9d0e6197e65c`.

Все три совпали с handoff и повторной проверкой после scoped tests/fault injections. Repo venv, `PYTHONDONTWRITEBYTECODE=1`, `unittest discover -s tests -p test_development_collection.py -v`: **20 PASS, 2,116 секунды, exit0**. Другие suite/WIP не запускались.

## Что исправлено и проверено

[produce](../../scripts/development_collection.py#L469) сохраняет прежнюю ветвь `_check_cached` для sealed entry. Для отсутствующего seal создаётся отдельный `invocation-<uuid>` output namespace; путь нового producer attempt записывается в state до вызова. Anchor/candidate/feature callbacks получают этот child root, а parent seal проверяет именно его. Старые failed или complete-but-unsealed identified runs не удаляются, не переписываются и не превращаются в принятую cache entry по одному свежему hash. Source producers001–007 для retry не изменены.

Три новые regression tests вызывают ошибку внутри actual Q/Y, C и F producer после identified directory creation. Q/Y и C после снятия fault обычным resume доходят до внешнего shard review; F — до complete_produced_unreviewed. Старые failed reports сохраняются побайтно. Вместе с прежними tests проверяются approval scopes/pins, tampered cache, cumulative budget/crash lock, incomplete cover и закрытая confirmation.

Независимый re-review отдельно повторил исходный F repro: patch `manual_features.create_manual_features` вызывает TimeoutError после создания identified run; затем patch снят, вызван тот же обычный run_phase с теми же inputs/approvals. Actual outcome теперь **complete_produced_unreviewed**, старое partial tree побайтно сохранено, cumulative compute увеличился. FileExistsError из первоначального audit больше не возникает.

Дополнительно проверена другая failure boundary, не покрытая тремя исходными регрессиями: actual producer полностью закончил работу, но `_verify_run` одноразово бросает RuntimeError до parent seal. Сценарий выполнен отдельно для anchor, candidate и features. Для Q/Y и C после нормального resume выдавались synthetic external shard approvals; затем обычный вызов завершал F и aggregation. Во всех трёх случаях:

- actual totals: Q4, Y2, C8, F8; exact C↔F и lineage checks прошли;
- два разных child invocation roots у затронутого stage, только новый успешный seal входит в collection;
- все файлы старого complete-but-unsealed child сохранили исходные SHA-256;
- cumulative cost больше стоимости failed state, runtime lock снят;
- дополнительный cache-run вернул ту же collection и не создал новых child attempts.

Это закрывает generic unsealed-child retry, а не только один искусственный TimeoutError в F. При process death оставшийся runtime lock всё ещё требует отдельного cost/output review; фикс не разрешает его автоматический сброс.

## Сохранённые acceptance boundaries

Runtime по-прежнему требует независимый producer approval конкретного code/phase/source/dependency bundle, а затем строгие внешние Q/Y/C approvals. Наличие свежих fingerprints не является approval. Sealed cache сравнивается с предыдущим seal; diagnostic F subset и изменённая acceptance отвергаются. Final aggregation сохраняет статус `mechanical_integrity_only_pending_independent_semantic_acceptance`, outer report — `complete_produced_unreviewed`.

Поэтому координатор теперь может подготовить producer approval **конкретного текущего train/selection plan и фактических pins** после их сверки. Этот документ не подставляет real source hash, не создаёт approval JSON и не принимает неизвестные artifacts автоматически. Runtime code acceptance не переносится на другую code/uv.lock/config/source версию. Первый real pass должен остановиться для independent Q/Y/C source reconciliation; после F нужны numeric spotchecks, actual counts/resource ledger и отдельная collection acceptance до008 realfit.

Реальные five-shard counts, время, CPU/RSS/spill и пригодность масштаба не измерены. Cumulative invocation wall accounting включает preparation/cache checks и retries, review wait исключён; RSS guard остаётся cooperative, не OS hard cap. Native buffer limit не выдаётся за полный RSS. Новые failed attempts входят в тот же phase budget, не расширяют его.

Confirmation runtime остаётся безусловно закрытым до source read. Selection labels доступны24Oct00, нынешний первый confirmation anchor тоже24Oct00: фактический decision/metrics gap ещё не решён. До открытия нужен отдельный prospectively reviewed schedule/lock с доказанным completion/availability selected decision, а не только checkpoint22Oct. Final holdout не затрагивается. Strong tuned manual B и честное сравнение automation остаются будущими gates; два smoke fits их не заменяют.
