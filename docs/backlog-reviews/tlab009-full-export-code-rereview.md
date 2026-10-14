# TLAB-009 full export: targeted independent re-review

15 октября2026. **CHANGES_REQUESTED: исходные четыре P1 и P2 закрыты; найден один новый воспроизводимый P1 в failed-receipt consumption.** Real full export/source audit/model/fit/actual approval writes не запускались. Все проверки — tiny temporary fixtures; repo/frozen files не менялись. Source-formula proof по6134207rows всё ещё отдельный будущий gate.

Новая exactfreeze сверена до/после: script `ebac0976b303e9e186adcdf086623b5f058b28688376af1f83e49fca70816528`; tests `ba97d7eb9bd5285c04c645b3ed81511e292e6385798e60382e9feeb2a241b37d`; doc `6fc723ad87d15315cb0ce49fa3e4e8e721e25d973bc590ad4d7d3ac04e21d1dc`. Initial `tlab009-full-export-code-review.md` SHA `4be8b0890fa666c8030ed415fdc43b2ba0fd1f64145669fa714c8cc811e15b64` byte-identical; старые helpers/results не переписывались.

## Remaining P1: known failed final receipt не запрещает consumer acceptance

ExecutionAudit сначала сохраняет report.json соstatuscomplete_produced_unreviewed, затем делает final measurement/receipt rewrite. Если **вторая** запись report.json падает до замены файла, код правильно поднимает OSError и сохраняет отдельный report.failed.json. Но на диске остаётся первый complete report. `verify_accepted_export` не проверяет известный failed receipt и принимает этот run при свежих synthetic external pins.

Собственный tiny repro выполняет неизменённый full runtime; writer позволяет первую complete summary и отказывает последующим report.json writes. Результат: caller OSError `INDEPENDENT final receipt unavailable`; report.json.status=`complete_produced_unreviewed`; report.failed.json.status=`failed`; consumer=`accepted`. Outputs/source/keys/model values не менялись; это stale completion после реально наблюдаемой terminal failure, не source-formula defect. Новый внешний approval здесь намеренно synthetic: actual coordinator ещё ничего плохого не подписывал.

Минимальное исправление — consumer и initial full-source audit должны reject известный failed receipt/finalization marker для данного immutable run, до использования complete report и повторно передsuccess. Также первая оплачиваемая summary может иметь noncomplete/finalizing status, пока final receipt ещё не сохранён. Failure marker нельзя просто игнорировать или автоматически удалять; recovery требует отдельно reviewed scope. Source-oracle577… сейчас читает producer report и не проверяет новый report.failed.json, поэтому этот маленький transport guard нужен и там до actual execution.

Evidence: `tlab009-full-independent-rereview-finalization.py` и `tlab009-full-independent-rereview-finalization-results.json`. Этот finding возник на новом fallback path; прежний root-cause preservation fix остаётся корректным.

## Что закрыто независимо

**Physical consumer gate:** original fresh-resealed wrong feature querykey, droppedbrand column и missingrows теперь rejected соответственно key cover/schema/key cover. Healthy full export consumed. Новый verify_physical_export открывает actual Parquets, сверяет schema/count/size, Q rows/day и accepted pair relation, whole output/provenance/reference boundary и everyuniqueitem representation. Source values он честно не объявляет независимо пересчитанными.

**Primary/secondary errors:** original stageValueError+CPUOSError теперь поднимает ValueError и сохраняет primary в top-level failed report, secondary separately. Primary+terminalRSS counter failure сохраняет failed evidence с RSSnull; primary+reportwriter failure также сохраняет исходный exception. Split timer/close cleanup проверен статически; нормальные close/error/resource faults не даютsuccess.

**CPU accounting:** original manifestwriter+10mockCPU даёт actualmockCPU10/reportCPU10, прежнее0 закрыто. Snapshot теперь послеclose/manifest/первойsummary; минимальный finalreceipt tail явно назван, parent ledger отдельно. Fake close wall+1300/CPU901/RSS8GiB+1, close exception, manifestwrite exception и late reportwrite walloverrun снова failed+exception. Искусственные числа не являются реальными CPU расходами.

**100Q scope:** healthy source-gate record проходит; original fresh-resealed source/candidatecode/specfile omissions rejected. Из уже pinned JSON выбираются actualacceptedtrain иspec, frozen prepare_gate_plan заново выводит полный input identity; self-declared fingerprints больше не задаёт собственный required set. В tiny fixture expected scope21pins, а не actual93: это gate-mechanism proof, не повтор audit реального accepted record. Current actual93record не трогался.

**Phase encoded union:** два дня с brand cardinality1/1 теперь дают diagnostic_phase_encoded_cardinality.brand=2. Это actual encoded set union, сsentinels, отдельноtrain/selection; не veto6000ablation по26000vocabulary. Перенесённый старый boundary recorder обращался к прежнему имени поля и печаталnull; новый finalization harness читает правильное поле и непосредственно подтверждает2.

EXACT14 supplement повторно прошёл actualtiny017-produced healthy lineage; jointQ/C omission после полногоresealing пропускаетсяlegacytransport, отвергаетсяновымcanonical14 gate. EmptyC day сохраняетQ70/F0/provenance0/fullR2; calendar zeroQ day имеет четыре typed empty exports. Day cover/input hashes/immutableattempt policies остаются intact.

## Actual evidence и следующий шаг

21scoped author tests воспроизведены: PASS4,809s; ихCPU отдельно не измерен.26собственных synthetic cases в5invocations: суммарно6,171974s wall/6,543176s processCPU/maxRSS181321728bytes,0fits/0real source reads. Один stale-complete consumer result — failure evidence, не passed check. Full runtime transport prepare mock явно ограничивает proof; strict14 использует настоящий tiny producer.

Raw scripts/results имеют prefix `tlab009-full-independent-rereview-`: faults/fault-results, boundaries/boundary-results,100scope/100scope-results,resource-controls/resource-results,finalization/finalization-results. После узкого failed-receipt fix нужна новая SHA и targeted повтор последнего repro плюс healthy consumer; весь author suite повторять без остальных изменений не требуется. Actual production/source acceptance и один eventual ablationfit остаются blocked отдельными exact approval gates.
