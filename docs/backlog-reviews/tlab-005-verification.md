# TLAB-005: независимая проверка manual18 и production runner

15 октября 2026. **Окончательный verdict после исправления: accept для code/synthetic scope TLAB-005 и перехода к100-query cost gate.** Revised scoped suite фактически прошёл18 tests; оба material findings закрыты. Подробности — в audit amendment в конце. Full6000 остаётся за отдельным measured resource gate; real data reviewer не запускал.

**Первоначальный verdict: changes requested перед100-query cost gate.** Ниже сохранён исходный review: core materializer соответствует принятому MVP; два material findings относятся к provenance/failure gates runner. Принимать только18-фичевое ядро как доказательство готовности production нельзя.

Полностью прочитаны actual [manual_features.py](../../scripts/manual_features.py), [tests](../../tests/test_manual_features.py), [registry](../../configs/features/manual-18.json), [документация](../experiments/manual-features.md), design/prereview и [canonical TLAB-005](../backlog.md). Reviewer не менял repo/Git/code/deps/реальные данные, не запускал real100/full и не затрагивал TLAB-007. Дополнительные repro использовали только TemporaryDirectory, крошечный синтетический DuckDB и process-local module patch; fixtures удалены после исполнения.

## Фактические проверки

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_manual_features.py -v
```

**Exit 0; Ran 12 tests in 0.440s; OK.** Suite проверяет `create_manual_features` и registry; **ни один из12 tests не вызывает `run()`**. Поэтому handoff о materializer correctness подтверждён, а provenance/error claims runner этим suite не доказаны.

Full18 direct-row oracle независим от compiler/production SQL. Есть отдельный DuckDB oracle count/distinct, raw duplicates и expiry с живым повтором, exact boundaries, recency старше7d, latest-second NULL/known conflicts, category move, чистая новая metadata-секунда без backfill, future/peer invariance и typed empty outputs. SQL injection/неподдержанные registry states и unsupported anchors отклоняются.

## Принятый core MVP и границы доказательства

[Реестр](../../configs/features/manual-18.json) содержит ровно18 числовых definitions: user4, pair5, item3, user-category3, item-category3. Дополнительные ages/coverage/flags и фиксированные retrieval columns отделены документально; downstream training обязан выбирать список features явно. Compiler принимает только whitelist grains/types/operators/windows/columns и безопасные identifiers, ratio references должны быть matching count supports одного type/window с согласованными вложенными grains. Произвольный SQL не компилируется.

[Metadata resolver](../../scripts/manual_features.py#L172) берёт последнюю **глобальную** секунду `<t`, учитывая все event types. `{c,c}` известно, `{NULL}` missing без ambiguity, `{c,NULL}` и `{c,d}` ambiguous; нет выбора удобной строки или отката назад. Source prefix начинается с S. Event category ID сохраняется у каждой исторической строки; category_code не участвует, поэтому unnamed numeric IDs остаются полноценными ключами.

[_grain_sql](../../scripts/manual_features.py#L123) правильно разделяет ограничение source: item/item-category используют selected products; category denominator использует relevant category IDs, **без candidate-product filter**. Некандидат той же категории входит в denominator. Для category move A→B numerator — только historical `(item,B)` views, denominator — все historical B views; старые A views не переклассифицируются. Этот prereview seam закрыт.

Counts известного пустого ключа coalesce→0; unavailable category превращает conditional values в NULL. Положительный denominator и нулевой numerator дают0, denominator0 — NULL с flag. Full-prefix recency и user/item first-seen age используют `[S,t)`, не7d; source coverage рассчитывается отдельно из source bounds. Exact distinct реализован повторным точным SQL по окну, а не суммой daily uniques или неверной scalar subtraction. Output identity/row count совпадают с fixed C; anchors validated как единые midnight UTC timestamps. Golden oracle покрывает18 core values; ages/masks дополнительно проверены чтением actual SQL, но возрастам полезен отдельный hand assertion в существующей fixture.

Pair aggregates ограничены selected users, но могут сохранять их исторические пары вне C. Это не user×catalog, однако output cap не ограничивает такой state или prefix scans. Resource gate должен измерить эти states, а не вывести их размер из числа feature rows. Это предел измерений, не найденное нарушение значения feature.

## Material finding P1: upstream code/output C не проверяются как accepted contents

Место: [run preflight](../../scripts/manual_features.py#L277), [input/code fingerprint collection](../../scripts/manual_features.py#L316).

Runner сверяет `candidate_manifest.identity.input_hashes`, но **не сверяет upstream `code_hashes`**. Затем текущие production modules хешируются как code новой005 identity. Изменённый upstream script относительно sealed004 manifest, следовательно, не отклоняется. Аналогично candidate output parquet не входит в004 input hashes: его текущий hash просто добавляется в новую005 identity. Это фиксирует потреблённые bytes, но не доказывает, что они являются независимо принятым C. `status=complete` и matching run_id не заменяют accepted output-content pin.

**Фактически исполненный isolated repro:** создать временный root с одной Q на 8 октября, двумя past view товарами и C из первого товара; source DB, original003 Q/Y, reports/manifests запечатать `build_run_manifest`/SHA-256. Все code/lock файлы fixture имеют известные синтетические hashes. Подменить только C parquet на второй товар, оставив004 run/report и inputs неизменными. Process-local `patch.object(manual_features, '__file__', synthetic_root/'scripts/manual_features.py')` направляет runner в fixture; `run(..., max_queries=100, seconds=10)` завершился **complete**. Затем восстановить C и изменить только synthetic `scripts/candidate_pilot.py` относительно004 code hash: второй run тоже **complete**.

Полученные aggregate assertions:

```text
modified_candidate_output_accepted=True; candidate_hash_changed=True
upstream_code_no_longer_matches_manifest=True; modified_upstream_code_accepted=True
```

Никакого real-data replay для этого не требовалось. Первый fixture setup встретил DuckDB COPY multiple-parameter internal error; это не выдавалось за PASS. После замены параметра synthetic product на фиксированный literal итоговые repro завершились exit0.

**Минимальный fix:** принимать coordinator acceptance pins для accepted004/003 либо эквивалентные обязательные expected hashes; сравнить actual candidate output hash с принятым hash **до** материализации. Проверять обе группы code/input hashes обоих upstream manifests, complete anchor report, matching source/lineage и exact original003 Q/Y paths/hashes. Не ограничиваться хешированием текущего C для новой identity. Acceptance snapshot/hash должен входить в005 identity. Эквивалентная схема уже реализована в accepted007, но менять007 или навязывать зависимость005 от scorer этим review не требуется.

Regression: sealed synthetic C изменён → rejection; upstream code изменён → rejection; missing pin/wrong lineage/incomplete anchor → rejection; допустимые exact inputs → tiny runner E2E complete.

## Material finding P1: ранние provenance/timeout ошибки теряют partial cost report

Место: [run initialization, строки268–338](../../scripts/manual_features.py#L268). `report`, `StageLedger` и try/finally создаются **после** expensive provenance fingerprinting, selection writes, manifest creation и DB open. Timeout/tamper/missing-file/connection error на этих этапах оставляет ни measured failure report, ни stage ledger. В частности, identity ещё может быть неизвестна, поэтому ждать её вычисления для audit нельзя.

**Фактический repro** на том же временном root:

```python
with patch.object(anchor_pilot.RunDeadline, 'check',
                  side_effect=TimeoutError('synthetic expiry')):
    manual_features.run(candidate, registry, output,
                        max_queries=100, seconds=10)
```

`TimeoutError` поднят на первом provenance fingerprint; `len(list(output.rglob('report.json')))==0`. Это точная потеря обещанного partial evidence, а не неверная статистика completed pilot.

**Минимальный fix:** создать attempt directory/report/ledger и внешний try/finally до provenance/hashing/connection; сохранять accepted/requested declarations, elapsed time, RSS и пройденные stages даже до run ID. После получения identity можно атомарно переименовать attempt. Connection/timer могут быть None. Никакой early failure не должен получать complete feature result. Guard RSS/deadline применять также к loads/fingerprints и перед complete; recording failed stage должно включать resource exceptions.

Persistent RunDeadline сам по себе корректно импортирован, output-stage checks присутствуют, selection bottom-hash query_id не использует labels, source открывается read-only. Эти правильные части не закрывают ранний error path. Bounds из spec —≤3600s/RSS8GiB/threads2/engine2GB/spill2GB — должны сохраняться как cooperative limits и проверяться synthetic runner failure tests, а реальные costs пока неизвестны.

## Приёмка после исправления

Нужны actual revised files, targeted synthetic runner E2E/provenance/failure regressions и scoped suite PASS, затем независимая повторная проверка. После code acceptance — только100 label-independent queries с прежним C; full6000 допускается после measured resource review. Сохранить state keys/scan bounds/profile rows/spill/RSS/output fingerprint, не считать маленький output доказательством дешёвых full-prefix scans. Real100/full, model gain и обучение данным review не подтверждены.

**Core18 принят по смыслу; TLAB-005 как готовый runner пока changes requested.** Других материальных дефектов feature values в просмотренном scope не найдено.

## Audit amendment: повторная проверка исправленного runner

15 октября 2026, после freeze revised files. Фактически прочитаны revised runner и новые synthetic tests, registry и обновлённая документация; исходные finding/repro выше сохранены. Это re-review кода, без real100/full, raw-data scans, изменений repo/Git/deps/code или TLAB-007.

### Finding1 закрыт: explicit accepted contents

[run теперь требует acceptance_path](../../scripts/manual_features.py#L261), CLI — обязательный `--acceptance`. Accepted007 public `verify_accepted_inputs` проверяет accepted004/003 complete lineage/protocols, exact original Q/Y, output C, source DB и upstream code/input pins по фактическим bytes. Remaining declared pins также проверяются отдельным циклом, а не игнорируются. Это reuse уже принятого public validator, без редактирования007.

Acceptance file SHA включён в input identity, как registry и actual selection specification. Новые code fingerprints явно включают используемые `heuristic_baselines.py`/`ranking_metrics.py` вместе с прежними модулями/lock. Следовательно, новый provenance helper не стал скрытой неидентифицируемой зависимостью. Current upstream code не подменяет проверку declared accepted upstream code.

Новые runner regressions фактически подтвердили: валидный, но заменённый C отклоняется с fingerprint error; изменённый upstream candidate code отклоняется; feature export отсутствует; failed preparation report сохраняется. Tiny sealed runner с точными accepted contents выдаёт complete,3Q/6feature rows/18core, а output SHA совпадает с parquet. Full/subset selection дают разные run IDs и сохраняют label-independent query selection. Missing pins/lineage/status также остаются gates reused accepted007 validator; отдельный007 suite при этом review не запускался.

### Finding2 закрыт: failure audit начинается до prep

Attempt directory, report и StageLedger создаются [до registry/provenance/source work](../../scripts/manual_features.py#L272). Общий try/finally включает preparations/fingerprints/open connection, а con/timer могут оставаться None. До identity сохраняется preparation report; после identity attempt переименовывается в идентифицированный run. Existing identified outputs не перезаписываются.

Stage wrapper проверяет persistent deadline и cooperative RSS до/после операции; fingerprint loop также guarded. Source open — самостоятельная записываемая stage. Synthetic early-expiry test поднял TimeoutError на первом check, но теперь проверил **существующий failed partial report** и отсутствие features. Connection-open failure сохраняет identified report с failed `open_source_read_only` stage. Эти фактические tests закрывают исходный zero-report repro; complete feature result при таких failures отсутствует.

### Фактический scoped результат и окончательные границы

Повторно исполнена **только** та же команда `unittest discover -s tests -p test_manual_features.py -v`, с `PYTHONDONTWRITEBYTECODE=1`: **exit0; Ran18 tests in0.722s; OK.** Шесть runner regressions добавлены к12 прежним core tests. Original claimed timings и failed historical repro не заменены этими данными и не выданы за результаты revised code.

**Final verdict: accept code/synthetic MVP.** Разрешён следующий технический этап —100 queries по label-independent bottom-hash при accepted004 pins, с прежним C. Полный6000 run требует отдельной проверки measured wall/RSS/spill/state/scan/output evidence; passing synthetic tests не прогнозирует его стоимость. Registry18, metadata/category/recency semantics не расширяются этим acceptance; feature gain/model quality не измерялись. Новых материальных findings в revised scope не найдено.


## Coordinator final execution/source acceptance — 15 октября 2026

После code/synthetic acceptance выполнены100/full pilots. Coordinator actual validator проверил оба run manifests, matching complete reports, все stages, actual source/code/registry/acceptance/selection/input hashes и output Parquet SHA.100Q точно совпали с bottom SHA(query_id), без labels; full6000Q и1 226268 unique pairs сохранились. Полное двустороннее EXCEPT ALL всех retrieval input columns против прежнего C дало0 различий, а не только совпадающее число строк.

Независимый Python/source oracle на18 validation pairs (random и поддержанные pairs, выбранные для проверки после artifacts) заново вычислил18 core features:324 scalar comparisons совпали. Oracle отдельно читает past user/item rows, latest global metadata bucket и global category denominator; production aggregate/compiler helpers не используются. User/item first-past ages также совпали. Проверены defined ranges и45-column/18-core schema; NULL recency/ratios не заменяются нулями.

100identity8144771408379aa127ce891f627084ae271f0c62ccbe307fbb37c4f4f2d96a3e:3.682s/RSS393330688bytes/20477rows. Fullidentitya52ec38733d2455b902498753388bcb9014054e92edab373519fddbe68ac85a6:5.128s/RSS2154364928bytes/1 226268rows. Engine spill0. Full engine buffer high-water3170382952bytes превысил requested2GB setting; точная причина не установлена. Принят отдельный cooperative RSS≤8GiB gate, **не** утверждение о hard2GB cap. Partitioned collection/resource gates обязательны при расширении.

**TLAB005 accepted**, включая actual execution. Findings/repro и исправления выше сохранены; [aggregate definitions/cost report](../experiments/manual-features.md) не заявляет quality gain.008 может переходить к отдельной reviewed phase/dependency/model реализации; strong tuned baseline и automation experiment ещё не выполнены.
