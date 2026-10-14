# TLAB-003: независимая проверка anchor/label code и actual pilots

15 октября 2026. **Verdict: changes requested.** Сохранённые pilot counts и временная семантика подтверждены; material finding относится к ненадёжному wall-deadline gate executor. До исправления и scoped повторной проверки accept TLAB-003 не выдан. Это не объявляет уже измеренные outcomes ошибочными.

Прочитаны полные actual [anchor_pilot.py](../../scripts/anchor_pilot.py), [synthetic tests](../../tests/test_anchor_pilot.py), [агрегированный отчёт](../experiments/anchor-pilot.md), оба saved run manifests/reports и parquet artifacts. Три owned файла были untracked: пустой обычный diff не заменял проверки полного содержимого. Reviewer не менял repo/Git/code/data/env, не устанавливал зависимости и не обучал модели. WIP TLAB-004 не запускался. В выводах и этой записке нет пользовательских идентификаторов или историй.

## Выполненные проверки и факты

Исполнена только разрешённая test group:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_anchor_pilot.py -v
```

**Exit 0; Ran 9 tests in 0.479s; OK.** Проверки используют отдельный row-iteration oracle, отдельный in-memory SQL oracle и hand-computed counts; production windows/SQL не копируются в row oracle. Протестированы endpoints, 48h lower boundary, binary collapse duplicates, global same-second permutation, future purchase без изменения раннего Q, bottom-hash sample, censoring и пустые таблицы.

Оба saved `run.json` прошли validator; пересчитаны SHA-256 фактической read-only DuckDB, `uv.lock` и трёх production modules. Все hashes совпали с соответствующими identity. Реальные config contents совпадают с manifest protocol. `components=[]` соответствует этому пилоту без fitted layers. Сохранённые status обоих reports — complete; все stage entries — complete. Raw gzip не перечитывался и не пере-хешировался.

Независимая bounded сверка открывала source только read-only, threads=2, memory_limit=2GB. Повторный полный pilot не запускался. Direct SQL сверял **все saved labels** с purchases sampled queries в `[2019-10-08,2019-10-11)`; отдельно проверены first purchase, raw multiplicity, same-second, catalog/pair existence до каждого anchor по source `[2019-10-01,2019-10-10)`. Для history diagnostics выбраны по два query на каждый день, всего шесть на вариант; сверены exact eligibility count, history7d count/distinct/days/max timestamp. Heavy full-month groupby не выполнялся.

| Проверенный показатель | A: eligibility7d | B: eligibility48h |
|---|---:|---:|
| Q / unique query / unique user-day | 6000 / 6000 / 6000 | 6000 / 6000 / 6000 |
| Distinct users | 5986 | 5988 |
| Positive / mature empty queries | 43 / 5957 | 104 / 5896 |
| Unique query-item Y / raw purchase rows | 51 / 59 | 121 / 139 |
| Cold / past pair / same-second targets | 1 / 28 / 0 | 0 / 73 / 0 |
| Censored / invalid Q / bad stable Q hash | 0 / 0 / 0 | 0 / 0 / 0 |
| Orphan/invalid/duplicate labels | 0 | 0 |
| Source target / coverage flag mismatches | 0 / 0 | 0 / 0 |
| History diagnostic mismatches, six Q | 0 | 0 |

Parquet schemas проверены фактически: query/user/product identifiers имеют VARCHAR/BIGINT согласно назначению, anchor/last history/first purchase — TIMESTAMP; counts — BIGINT, coverage — DOUBLE, maturity/catalog/pair/same-second — BOOLEAN. Пустые queries сохраняются на Q независимо от отсутствия строки Y. Report totals согласуются с parquet, а не только с сообщением исполнителя.

Первые ad hoc попытки reviewer SQL остановились на DDL prepared-parameter, попытке persistent relation-view в read-only DB и зарезервированном alias. Эти ошибки не выдавались за PASS; исправлен только способ чтения/alias reviewer query. Успешная итоговая сверка использовала connection-local TEMP VIEW; source и artifacts не изменялись.

## Подтверждённая семантика

В [create_queries](../../scripts/anchor_pilot.py#L109) source ограничен `<anchor`; eligibility фильтрует допустимые прошлые event types и включает левую границу окна. Bottom-2000 строится до вызова label extraction, по фиксированной ASCII serialization `sample|seed|UTC-anchor|user_id`, SHA-256 и deterministic tie-break. SQL не видит future purchase labels при выборе Q. Real query hashes пересчитаны для всех 12 000 Q; bottom-hash selection проверен synthetic oracle и чтением actual SQL, без повторной полной eligibility-агрегации миллионов пользователей.

Диагностическая history7d одинакова для обеих populations; coverage не подменена возрастом пользователя. All-user shared observations в секунде t не влияют на history из-за `<t`; record permutation не меняет агрегаты. Это SQL batch semantics, а не построчное обновление state.

[create_labels](../../scripts/anchor_pilot.py#L164) не принимает C и не обращается к candidates. Distinct `(query,product)` relevance отделена от raw purchase multiplicity. Target endpoints исполняются SQL-условиями и maturity из TLAB-001; censored Q остаются на Q, но не становятся empty negatives. Cold catalog диагностика использует любое событие товара строго до query, от начала source, а не только eligibility lookback. Pair repeat означает любое прошлое взаимодействие, не повтор purchase. Один cold target A сохранён в Y. Full-history diagnostics выполняются после sampling и не меняют Y.

## Material finding: P1 — one-shot interrupt не обеспечивает wall deadline

Место: [run, строки 288–308](../../scripts/anchor_pilot.py#L288). Executor создаёт один `threading.Timer(..., con.interrupt)`. Нет persistent expired flag или monotonic check после expiry, перед последующими stages/loops/exports и перед объявлением complete. DuckDB interrupt, вызванный между SQL statements, не запрещает следующий statement. Поэтому timer может сработать во время Python-работы и быть потерян для последующих запросов; run продолжит работу и сможет записать complete после declared deadline.

Фактически исполненный минимальный driver repro, без dataset и файлов:

```python
import duckdb, threading, time
con = duckdb.connect(':memory:')
fired = threading.Event()
def expire():
    con.interrupt()
    fired.set()
timer = threading.Timer(0.01, expire)
timer.start()
time.sleep(0.04)  # expiry happens between SQL statements
assert fired.is_set()
assert con.execute('SELECT 1').fetchone()[0] == 1
timer.cancel()
con.close()
```

Фактический результат: `deadline_fired_before_next_query=True`, `subsequent_query_succeeds=True`. Отсутствие budget checks в production call chain установлено по actual code. Repro не требует повторять полный pilot.

**Минимальный fix:** сохранить absolute monotonic deadline и persistent cancellation/expired state. Timer должен установить state и прервать текущую SQL; executor обязан проверять state/deadline до и после stages, между Python-driven query loops, перед exports и перед status=complete. Истёкший deadline должен давать failed/timeout report и сохранённые partial ledger/manifests, не complete. Учитывать preparation/fingerprinting в общем времени; если они уже исчерпали бюджет, не начинать pilot. Это кооперативный wall-budget gate: произвольную Python I/O невозможно немедленно остановить одним SQL interrupt, поэтому формулировки документации должны оставаться точными.

Нужен один deterministic regression: expiry в non-SQL gap перед следующей stage, дальнейшая работа не стартует и status не complete; плюс проверка failure path/partial artifact report. Mock clock/event предпочтительнее timing-flaky sleep в production test. Reviewer код не исправлял.

## Resource evidence и пределы приёмки

Из saved actual reports, без повторного timing run: A **9.833271s / 745570304 bytes process peak RSS**, B **9.551122s / 745979904 bytes**. Все stage profiler `system_peak_temp_dir_size=0`: engine spill в этих двух runs не наблюдался. Profiler peak buffer memory — отдельный engine counter (максимумы 1005817856/972791808 bytes), не дополнительная RSS. Stage-end directory bytes включают profiler JSON и не являются peak spill. EXPLAIN estimates отдельно от measured cumulative scan counters; миллионы eligibility keys не выдаются за размер state в байтах. Runtime включает fingerprint/export; это два конкретных запуска с cache effects, не replicated benchmark или оценка полного обучения.

Оба actual runs укладываются в заявленные 1800s/2GB DuckDB limits по сохранённому ledger. Это не закрывает обнаруженный общий deadline defect. Error path внутри try сохраняет failed report в finally; connection создаётся до try, поэтому полная гарантия partial reports для connection-open errors отдельно не доказана. Текущая source DB корректна, и это не объявлено вторым material finding.

**Повторная приёмка:** actual deadline fix и targeted regression проходят scoped suite; reviewer проверяет amended code/failure behavior. Изменение production code изменит run identity: не переписывать старые manifests/fingerprints. Новые запуски, если нужны для final evidence нового executor, сохраняются отдельными artifacts; существующие проверенные counts можно оставить как первоначальные измерения. До этого production TLAB-004 не получает prerequisite acceptance. Других material defects labels/population в просмотренном scope не найдено.

## Независимый повторный audit B3: исправленный deadline executor

15 октября 2026, после заморозки deadline fix. **Amended verdict: CODE ACCEPT; исходный material finding закрыт для проверенной версии кода. Новые A/B runs отдельно pending.** Исходный B2 finding, repro, исторические числа и пределы проверки выше сохранены без изменений. Первоначальный `changes requested` относится к прежнему executor и остаётся частью audit trail.

Повторно прочитаны фактические [anchor_pilot.py](../../scripts/anchor_pilot.py) и [test_anchor_pilot.py](../../tests/test_anchor_pilot.py), исходный finding и failure-path expectations. Файлы всё ещё untracked additions; поэтому полный actual text, а не пустой обычный diff, служил предметом review. Hashes проверенной frozen версии:

```text
scripts/anchor_pilot.py  d9344599ae1d64780374ede5006644e1f9983ed84085d0c8a64ec76fd99c835d
tests/test_anchor_pilot.py  f4638dc017a11c5e110c7a98d001a786dea65110542105711add014c100da804
```

Независимо выполнена только scoped synthetic suite:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_anchor_pilot.py -v
Ran 13 tests in 0.495s
OK; exit 0
```

Это девять прежних semantic/oracle tests плюс четыре deadline regressions. Строка `status=failed`, напечатанная одним тестом, — ожидаемый synthetic failure-path результат; сам тест прошёл. Он создаёт отдельную tiny synthetic DB и artifacts во временном каталоге, не открывает реальный source. Другие test groups, raw scans, real pilots, установки или training reviewer не запускал.

**Проверенное исправление:** `RunDeadline` хранит absolute monotonic deadline и persistent `threading.Event`. Timer устанавливает Event до SQL interrupt; состояние не теряется между statements. `check()` учитывает оба источника expiry. `StageLedger` проверяет deadline до работы и после операции; expiry во время Python-operation не позволяет пометить её complete. Daily/query-driven loops и build orchestration получают тот же budget checker. Preparation/fingerprinting проверяются до/после чтения, поэтому уже исчерпанный preparation budget не разрешает начать pilot. Export проходит ledger, а перед `report.status='complete'` стоит финальный check. Failure внутри execution try сохраняет failed report, ledger и manifest.

**Чувствительность новых regressions:** fake clock достигает границы внутри Python-stage и вызывает failed; persistent expired flag запрещает следующую work-stage, хотя сам DuckDB по-прежнему принимает `SELECT 1`; истёкший orchestration checker не начинает pilot; injected failure executor сохраняет failed stage/report/run manifest без query export. Проверены также невалидные zero/negative/nonfinite/bool budgets. Это предметные проверки поведения, а не только присутствия нового класса.

**Границы code acceptance:** gate кооперативный. Один длительный Python/file read не прерывается мгновенно, но после его завершения expiry обнаруживается до последующей работы. Cleanup/report serialization могут занять время после deadline; полная гарантия отчёта при сбое connection-open до try по-прежнему не заявляется. Эти ограничения не воспроизводят закрытый дефект «потерянный interrupt → продолжение pipeline → complete» и не требуют блокировать исправленный bounded executor.

**Run evidence отдельно:** прежние A/B identities и измерения выше остаются историческими проверенными outputs старого code hash; их нельзя переписывать под новый executor. В этом audit новые A/B artifacts и их DB/code/config/output fingerprints **не проверялись**. Root выполняет новые bounded runs после code acceptance; итоговое принятие нового execution evidence требует отдельной сверки новых run IDs, actual code/input hashes, complete status/stages, Q/Y accounting и output refs. Production TLAB-004 остаётся под prerequisite gate координатора до закрытия этой части TLAB-003 acceptance.


## Final execution provenance acceptance — coordinator, 15 октября 2026

Независимый code review B3 принят выше; coordinator отдельно проверил новые A/B manifests через actual validator, matching report/protocol/run identity, complete каждого stage и wall time ниже 1800s. Фактические SHA-256 DuckDB/code/uv.lock совпали с declared hashes. Новые Q уникальны по query и(user,anchor), 6000 на variant, все mature; Y unique по(query,item), 51/121 targets и43/104 positive queries. Daily report totals сходятся.

Coordinator самостоятельно повторил полный двусторонний EXCEPT ALL новых/старых Q иY: четыре пары сравнений, 0 различий в каждом направлении. Это повторно связывает новые artifacts с ранее независимо сверенными source outcomes; новый full raw scan не понадобился. Aidentity2b764734a8729a86dbb971e970fe1bfaf220ef1e5a7937198053e531336c4435:10.1598s,RSS746717184bytes; Bidentity687afe24b689c0996344892808306685f39afdf56a5dad5aa521c3094ec0305d:9.7046s,RSS744980480bytes. Actual output content hashes проверены и сохранены в локальном provenance evidence; user/product rows в Git не включены.

**TLAB-003 accepted.** Два запуска — диагностика разных audiences, не paired model comparison.Prerequisite 001/002/003 для bounded 004 снят; candidates/provenance/coverage004 проходят отдельную приёмку. Original timer finding истарые измерения сохранены.
