# TLAB018: конкретный additive bootstrap/replay план

15 октября2026. **План реализации, не execution approval.** Прочитаны README,
`docs/data.md`, round050/051/067, fresh-clone audit, CLI/контракты017/018/008 и
исторические source/control consumers. Никакие actual данные, Y, модели,
ignored approvals или большие hashes не открывались; SQL/tests/fits/download/Git
не исполнялись. Coordinator подтвердил отсутствие занятых bootstrap paths: его
heldout contract/source/prediction/Y-unlock остаётся отдельным владельцем.

## 1. Результат и границы

Нужен воспроизводимый переход **новый source → новый plan → независимое evidence
→ отдельно reviewed decision → новый seal**, плюс самостоятельный zero-fit replay.
Сейчас `verify_development._Inputs` требует уже approved collection, тогда как
017 останавливается до F на `waiting_for_shard_review`. Получается реальный
циклический handoff, который новая CLI должна разомкнуть. Existing018 остаётся
неизменным verifier уже sealed manual18; historical `strong_control`/304 и
`recovered_feature_source`/исторический seal не обобщаются и не переписываются.

Разделить четыре режима в интерфейсе и итоговом evidence:

| Режим | Требуемые внешние inputs | Допустимый результат |
|---|---|---|
| Source-free smoke | clone+locked environment+публичный synthetic fixture | mechanics/typed generation/metric gold;0real labels/ML |
| Supplied artifact replay | отдельно предоставленные private Q/C/Y/scores, optional CBM/F, externally anchored package manifest | пересчёт именно данного пакета, без новых fits |
| Fresh derived regeneration | publisher gzip+новый source/import plan+limited external decisions | новая DB/Q/Y/C/F identity, новые semantic proofs/seals |
| Retraining | вновь accepted collections+отдельный fixed fit plan/разрешение/claims | новая model identity и independently reviewed outputs |

Clone без private пакета не может numerical-replay исторический результат.
Fresh DB/Parquet/model bytes не обязаны совпасть со старыми; критерий fresh run —
зафиксированные schema/protocol/source semantics, а не подгонка к старой метрике.
Повторное обучение не должно автоматически запускаться ради replay.

## 2. Минимальные новые paths, без framework

**Increment A — исполняемый reviewer prefix и score replay, приоритет первый:**

1. `scripts/reproduction_plan.py`: `inspect`, `plan-development`, `plan-fit`.
   `inspect` читает только small public metadata и перечисляет отсутствующие
   ignored prerequisites; ноль implicit download/DB scan. Planning использует
   существующие017/008 planning functions только под явным оплачиваемым context;
   hash-стримы считаются paid preparation, не «бесплатный dry run». Proposal всегда
   `proposed_unreviewed`; отсутствие разрешения даёт readable STOP до paid work.
2. `scripts/replay_ranking_claim.py`: read-only по умолчанию, fixed fullY ranking
   replay, без импорта training runner. Использует reviewed006 evaluator как
   публичную реализацию метрик, собственные file/schema/key/tie checks; tiny gold
   и independent literal test не получают expected values из006.
3. `tests/fixtures/reproduction/manual18-small/`: маленькие текстовые synthetic
   Q/C/Y/scores/schema/claim JSON, максимум32 суммарных input rows, exact integer
   tokens/строки с явно заданным parsing; никакие реальные идентификаторы.
4. `tests/test_reproduction_plan.py`, `tests/test_replay_ranking_claim.py`.
5. `docs/experiments/fresh-clone-reproduction.md`: canonical commands, stages,
   STOP-коды, expected artifacts, cost и приватный handoff.

**Increment B — source import и первичная018 source приёмка:**

6. `scripts/source_import.py`, `tests/test_source_import.py`: strict published
   gzip SHA/size/CRC до создания новой DB, exact nine-field typed parser,
   transaction/checkpoint, schema/time/count/NULL evidence и новый DB hash.
   Default reject existing DB: `ingest_metadata` сам по себе не доказывает
   неизменность events. Claim до hash/CRC, failure/cost/partial DB сохраняются.
   Existing `eda.ingest` не менять и не запускать как будто это bounded018:
   он по умолчанию использует4threads/8GB memory/80GB spill, а ignored download
   manifest у fresh clone отсутствует. Новый import owner задаёт reviewed
   resource context явно; tiny tests не разрешают реальный import.
7. `scripts/development_bootstrap.py`: команды `verify-shard`,
   `verify-collection`, `seal-reviewed`. Принимает **produced-unreviewed** input,
   не требует будущего collection acceptance для проверки его истинности.
8. `tests/oracles/development_bootstrap_source.py`: explicit protocol-v1/manual18
   independent expected Q/Y/C+sampled F kernel. Начальная версия переносит
   независимые `_qyc/_formula/_features`018 с AST/equivalence audit, но не вызывает
   producer sampler/category/compiler. Новый lineage adapter выводит exact
   mandatory maps самостоятельно; нельзя просто вызвать прежний `_lineage`,
   который требует final approval. Accepted018 не редактируется. Не обещать
   универсальную grammar/extensions поддержку.
9. `tests/test_development_bootstrap.py`: tiny real producer→pending shard→oracle
   →external decision→seal→F→collection loop, плюс adversarial fresh resealing.

Новый optional `scripts/replay_saved_model.py`/test — **следующий отдельный
increment**, после score CLI: typed B41(+approved3) schema/CBM/prefix replay.
Не блокировать полезный metrics-only интерфейс отсутствием native model bundle.
Никаких изменений существующих accepted producers/consumers в этих increments.
README update — после independently accepted commands, а не до их реализации.

## 3. Exact handoffs и команды reviewer

Ниже — **предлагаемые будущие commands**, пока новые paths не реализованы.
Все записи — explicit project-relative output, exclusive и без overwrite.

```sh
uv sync --locked
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -m unittest tests.test_feature_programs tests.test_ranking_metrics
uv run --locked python -m scripts.reproduction_plan inspect --project-root .
uv run --locked python -m scripts.replay_ranking_claim --package tests/fixtures/reproduction/manual18-small
```

Smoke/inspect не требуют `data/`/`artifacts/`, не создают approvals/claims, не
импортируют native training. Установка environment — отдельное разрешённое setup;
`.python-version=3.12` не равен обещанию exact historical3.12.14. Record actual
Python/package/OS/arch/lock/code before/after; supported native historical host
DarwinARM64. Нельзя вызывать `platform.platform()` внутри no-subprocess worker.

Для private historical replay reviewer получает **directory package**, не
автоматически распаковываемый архив: manifest version/scope, upstream public
aggregate/code refs, exact Q map/C/fullY/keyed-score map, typed schema, K20/four
estimands/product-ID tie policy, all file hashes и внешний manifest SHA.
Предлагаемый вызов:

```sh
uv run --locked python -m scripts.replay_ranking_claim --package artifacts/reproduction/study --expected-manifest-sha <reviewed-sha> --access-contract artifacts/reproduction/access.json --execution-approval artifacts/reproduction/replay-limit.json --evidence-out artifacts/reproduction/replay-evidence.json
```

`--expected-manifest-sha` приходит через независимый reviewed handoff, а не
вычисляется самим пакетом. Без него разрешён только synthetic fixture либо
explicit unendorsed supplied-package calculation; это не historical acceptance.
Private reviewer должен отдельно получить законный доступ к ID-bearing tables,
моделям и full targets через контролируемый канал. Public repo не распространяет
raw REES46 и реальные Q/Y. Если доступ не предоставлен — reproducible public
mechanics+audit, **не independently replayed historical numbers**. Access contract
разрешает только train/selection; confirmation/final отказывают до чтения Y и
остаются coordinator-heldout scope, без обхода через «reproduction».

Fresh source workflow отдельно требует publisher gzip: published compressed-byte
SHA `8ebca1ad741295297368f2cf0315e3f36853a1a11768fb16babf8c9b83838147`,
size1741928540, gzip CRC/size. Скачивание пользователь выполняет отдельно по
`docs/data.md`; loader не скачивает молча. Source hash/ingestion evidence и DB
physical hash раздельны; другое compressed hash — STOP historical identity,
не автоматическое обновление expected value. Full import/CRC/hashes оплачиваются. Предлагаемый explicit import после
separate source/resource review:

```sh
uv run --locked python -m scripts.source_import --archive data/raw/2019-Oct.csv.gz --db data/processed/october.duckdb --execution-approval artifacts/reproduction/import-limit.json --evidence-out artifacts/reproduction/import-evidence.json
```

Import report связывает compressed source, strict parsing policy/code и новую
DB identity; underlying marketplace logging/ingestion completeness этим не
доказывается. Full EDA необязателен для создания events: не запускать заново весь
месяц diagnostics/user_metrics ради bootstrap. План source import содержит явные
CPU/wall/RSS/threads/memory/spill limits и final lifetime; реальные значения ещё
требуют review/measurement, не наследуют автоматически current016 allowance.
После успешной DB/source проверки:

```sh
uv run --locked python -m scripts.reproduction_plan plan-development --phase configs/development/train.json --db data/processed/october.duckdb --execution-approval artifacts/reproduction/preparation-limit.json --out artifacts/reproduction/train-plan.json
# External code/source/resource reviewer issues exact producer decision.
uv run --locked python -m scripts.development_collection --phase configs/development/train.json --producer-approval artifacts/reproduction/train-producer.json --shard-acceptance-dir artifacts/reproduction/shards --output-root artifacts/reproduction/development
# Expected STOP: waiting_for_shard_review; no F has yet been generated.
uv run --locked python -m scripts.development_bootstrap verify-shard --request artifacts/reproduction/shard-request.json --execution-approval artifacts/reproduction/shard-oracle-limit.json --evidence-out artifacts/reproduction/shard-evidence.json
# External reviewer inspects source evidence and issues a bound decision.
uv run --locked python -m scripts.development_bootstrap seal-reviewed --decision artifacts/reproduction/shard-decision.json --issued-decision-sha <reviewer-sha> --write-acceptance artifacts/reproduction/shards/shard.json
```

017 resume сохраняет failed attempts/seals/state/cumulative cost; downstream F
не считается до exact required shard decisions. Затем аналогично
`verify-collection --request ... --execution-approval ... --evidence-out ...` и
`seal-reviewed --decision ... --issued-decision-sha ... --write-acceptance ...`.
Команды нужно повторить для selection по отдельному plan; confirmation запрещена.

Writer не принимает произвольный fingerprint map как truth: rederive exact
code/source/registry/shard/seal/report/physical closure (включая всех14 обязательных
pins каждого shard и query_coverage), проверить external decision's evidence SHA,
policy/version/proof scope, complete/exit0/full-lifetime receipt/known-failed
markers и повторить pins перед immutable write. Decision strict keys:
`version,scope,decision,subject_id,proposal,evidence,evidence_policy,proof_scope,
required_pins_digest,resource_receipt,reviewer_record`; `decision='accept'` и
CLI-issued SHA не заменяют semantic oracle. Payload writer выдаёт exact existing
017-compatible shard/collection schema, audit sidecar отдельно связывает reviewer
refs; existing accepted017 checks должны принять результат на tiny fixture.
Никакого `approved=true` template как пользовательской инструкции.

## 4. Acceptance tests и порядок приёмки

- Fresh relocated checkout path с пробелами, отсутствующие data/artifacts/private
  approvals: public prefix проходит; inspect даёт точные missing/STOP, не пишет
  acceptance и не запускает training. Pinned public files unchanged.
- Tiny≤32: fullY target вне C, mature zeroY, positive emptyC, exact2^60 и2^60+1,
  NULL, duplicate/orphan C/Y/scores, shuffled positional Q mapping, nonfinite
  scores; own literal Recall/AP/NDCG, все четыре denominators и stable ties.
- Model replay следующий increment: swapped feature order/NULL dtype/prefix
  отказывают **до** native predict; score tolerance не оправдывает changed ranking.
- Tiny gzip import: wrong published digest/size, CRC truncation, malformed type,
  existing DB with plausible metadata but changed events: reject до downstream
  plan; fresh transactional import ties source/parser/newDB evidence. Fixture
  source profile явно synthetic, не подмена production REES46 expected hash.
- Genuine pending017→bootstrap loop: source-derived Q/Y/C relation proof,
  missing/extra shard/query_coverage/source/code/registry pins и jointQ/C omission
  отвергаются после согласованного fresh reseal. Legal wrong sampled F value
  отвергается semantic oracle. Unsampled numeric value **может пройти** нынешний
  sampled policy — явный negative-control limit, а не exhaustive claim.
- Wrong/missing/stale external decision, bool/int confusion, unsupported registry,
  failed/partial output, late failed marker, changed evidence/approval after parse,
  escaped symlink/`..`, second seal attempt: STOP/no overwrite/no source execution.
  Context parse uses verified bytes once; sourceDB READ_ONLY.
- Claim до paid preparation; failure remains paid/consumed. Fake wall/CPU/RSS/
  close/secondary-writer faults проверяют terminal failure, preserved primary,
  no false success. Full lifetime SELF+reaped CHILDREN, no double count, actual
  CPU вместо wall×threads. Unknown usage STOP; никакого автоматического reset.

P0 bounded tiny acceptance проверяет интерфейс без данных/ML и **не расширяет**
existing0167200/once-claims. Реальная source regeneration/replay/retraining требует
отдельного измеримого resource plan и external decision; cap300/512MiB текущего
018 tiny verifier нельзя объявить доказанной производительностью42m source.
Полностью пустой source с известным017daily_outcomes failure остаётся explicit
STOP/сохранённой regression, не скрывается fixture, отдельный future producer fix.

## 5. Что останется честно незакрытым

После A: runnable smoke/score replay при supplied inputs; **не** fresh source seal.
После B: fresh protocol-v1/manual18 development bootstrap, exhaustive Q/Y/C и F
rowset, numeric manual18 sampled со strata/counts. Это не exhaustiveB41, не
автоматическая metadata009/selected12 source approval. Для selected12 нужны
отдельный exhaustive oracle/новая reviewed identity и сохранение B45; historical
recovered-source seal лишь архивный replay, не разрешение новой recovery.

Новый сильный control/016 rerun требует generic fixed-procedure acceptance seam,
новых limited fit/model reviews и сохранённого selection ledger; historical019/
recovered-source SHA потребители этого не дают. Existing public native model
observer — reference mechanics, не бесплатная retraining authority. Fresh clone
не превращает просмотренные development outcomes в нетронутый holdout, не
переоткрывает confirmation/final и не доказывает generalization. Private artifact
availability и независимый reviewer decision остаются внешними prerequisites,
а не скрытыми зависимостями от чата или `/tmp` scripts.
