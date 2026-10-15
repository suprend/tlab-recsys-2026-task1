# Research lab, round037: feature reuse не равен approval или fit authorization

15 октября2026. **Prospective identity/reuse contract**, не cache implementation. Контекст: [016pool026](round-026.md), [selected-union oracle035](round-035.md), [019freeze](../backlog-reviews/strong-worker-design-freeze.md). Source/data/SQL/Pool/models/fits не читались/не запускались; Root/coordinator code, dependencies, approvals и бюджеты не менялись. Нового framework или novelty quota не предлагается.

## Первичные основания и граница переноса

[DVC internal files](https://doc.dvc.org/user-guide/project-structure/internal-files) различают content-addressed data cache и run cache. Первый хранит содержимое по hash, независимо от имени файла; второй связывает exact dependency contents/parameter values с literal command и предполагает deterministic commands. [Run-cache docs](https://doc.dvc.org/user-guide/pipelines/run-cache) описывают восстановление результатов stage при прежних conditions. Это полезное разделение хранения и execution signature, а не доказательство, что неявные зависимости автоматически обнаружены.

[TFX ML Metadata](https://www.tensorflow.org/tfx/guide/mlmd) различает Artifacts, Executions, Events и Contexts; связи позволяют проследить upstream inputs и найти прошлую работу с теми же inputs. [Kubeflow caching](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/caching/) описывает reuse доступных outputs при тех же inputs/parameters. Эти системы не удостоверяют наш strict-past predicate, exhaustive source oracle, внешний reviewer decision или project-wide fit claim. Заимствуется contract vocabulary; DVC/TFX/KFP здесь не устанавливаются и не объявляются частью pipeline.

## Три независимых identity obligations

| Уровень | Что идентифицируется | Чего равенство не даёт |
|---|---|---|
| Feature value/representation | Typed function, source/context/domain и exact output representation | Accepted lineage, legal proposer chronology, разрешение fit |
| Accepted artifact lineage | Реальные bytes/paths/manifests/report, verified proofs и external decision | Новая fit attempt или unlimited recomputation |
| Execution authorization | Frozen experiment policy/slots/deadline/global claim/consumed history | Корректные значения лишь по совпадению имени/cache entry |

**Предлагаемый semantic signature** включает typedAST/operator/grain/projectedkey/event/window/endpoints, sourceSHA+adapter/code/runtime versions, source intervals/availability assumptions, exact anchors/Q/C domain, rawbag/NULL/category/conflict policy и coverage. Sourcehash+feature name недостаточны: одинаковый DB поддерживает24h/168h, rawcount/distinct и `<t`/`≤t` как разные функции. Молчаливое изменение duplicates/missingness меняет результат без смены файла.

Representation identity дополнительно закрепляет names/order/physical dtypes, timestamp precision, nullable transport, canonical sorting/encoding, float32 conversion и sentinel policy. Одни keyed mathematical values не гарантируют одинаковые Parquet bytes; different compression/metadata может дать иной artifactSHA. И наоборот, один hash по неправильному output доказывает только те же неправильные bytes. Нельзя подменить semantic evidence byte-addressing.

При нынешних strict exact pins безопасный выбор — conservative miss при source/code/runtime/context change. Даже future suffix, математически не влияющий на старые anchors, меняет full-sourceSHA: reuse потребовал бы отдельного доказательства prefix equivalence и lineage, не автоматического ослабления pins. False miss стоит вычислений; incorrect hit скрывает неправильный experiment. Recompute допустим только в оставшемся авторизованном scope/budget, не как free retry.

## Какие model/label поля куда относятся

Depth/L2/learningrate/trainediterations/scoringprefix не меняют current strict-past count/recency F при неизменном registry/domain/representation. Они принадлежат model/execution identity. Смена019winner меняет feature identity **если** меняет selected columns, population/Q/C, encoding или fitted preprocessing dependencies; один лишь modelID не является математическим determinant raw counts. У fitted scaler/embedding state его fit cutoff/available_at/version тоже стали бы value dependencies, но таких operators current016не добавляет.

Выбор6000/26000 обязан изменить exact dataset/domain identity. Возможная subset projection из принятого largerF требует exact subset-key/type/value/pin proof и собственной допустимой lineage; одинаковое количество строк не разрешает reuse. Full prefix-derived fields и model float32 assembly также должны соответствовать объявленному context. Trained300/scored50 нельзя заменить cachedtrained50model только потому, что F то же.

Y не участвует в label-free formulas selected12. Но current collection approvals/child manifests/F inputs механически закрепляют Q/Y/C и их source proofs: changedY при unchangedFvalues не сохраняет прежнее approval. Нельзя удалятьYpins ради cache hit. Это integrity/context obligation, не утверждение, что численные labels прочитаны при feature materialization.

Label-free AST evaluation не означает label-blind definition selection: staticI design знает008/009history,019/016используют retrospective selection. Proposer/pool/draw/decision availability и consumed looks сохраняются отдельными artifacts. Cache не backdates decision до used-label maturity и не даёт открыть reserved targets раньше sealed lock.

## Concrete counterexamples и failure policy

1. `pair_cart_24h` с тем же name/source, но DISTINCT вместо rawcount: два одинаковых события дают1 вместо2. Name/hash input совпадают, signature обязан различаться.
2. Item-only cache для user/pair feature: два users одногоitem имеют counts1/2. Нужно key(t,u,i), не representativeitem row.
3. Recency cache с7d cutoff: cart−8d ошибочноNULL вместо691200seconds/falsemask. Coverage и observed prefix не взаимозаменяемы.
4. Nullable BIGINT2^60+1 проходит через inferredfloat64 и округляется; rawsemantic source тот же, representation недопустима.
5. Freshly resealed partialF имеет правильные surviving rows, но пропущенный C-key/failedmarker/unknownCPU. Это **не hit**, независимо от новых hashes/statuscomplete.
6. ChangedY или mismatchedchildreport при identicalFbytes: value reuse теоретически возможно, accepted lineage invalid. Existing authorization не переносится молча.

Known corruption, missing mandatory pins, failed/incomplete terminal state или недостаточное proof scope должны давать failed/STOP, а не тихую регенерацию с уничтожением failure evidence. Просто absent optional cache entry — miss; это другая ситуация. Verified hit требует exact physical keyset/multiplicity/schema, complete immutable outputs, external accepted evidence с достаточнымscope, terminal cleanup/resource receipt и актуальную проверку всех mandatory bytes. Producer не одобряет собственный новый seal.

## Узкий016reuse и prospective cache laws

Для frozen L02/L06/L01/L05 возможно однократно получить selected-union11cores+1mask, принять exhaustive new12source proof и every-row preservation B относительноoldF, затем проектировать B+3 каждому arm. Это proposal допустимого reuse evidence, не заявление о наличии cache. Shared materialization/source hashing/oracle оплачиваются **actual once**, per-arm reads/projection/model preparation/diagnostics — actual each. Не начислять одну работу четырежды и не считать последующие операции бесплатными. Equal opportunity budgets не означают equal observedCPU/cores, cache warmth или speed benefit.

Minimum future laws на≤32literal rows/0fits, без запуска сейчас: identical contract+bytes+acceptedterminal evidence→eligible reuse; changedoperator/window/grain/domain/NULL/type→miss/reject; peer reorder сохраняет keyed count/max values при неизменном contract, но не обязательно physicalbytes; rawduplicate меняетcount, неdistinct; alteredY меняетlineage eligibility; corrupt/partial/freshresealedwrongvalue→STOP; consumedfitclaim не становитсяavailable послеfeaturehit; changedmodeldepth-only оставляет Fidentity, но меняетfitidentity.

Native fit slots/global atomic claims остаются независимы: collision consumed/no redraw, incumbent reuse только заранее разрешённое, failedattempt не повторяется из-за cachedF. Validation/hashing/readback/failedattempts/cleanup входят в existing016shared2CPUh и019policy, без новой allowance. Главный automation claim — genuine generation и correct calculation; reuse само по себе не доказывает ranking gain, DAGspeedup или экономию human-hours.
