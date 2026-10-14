# TLAB-009 full export: independent code/fault review

15 октября2026. **CHANGES_REQUESTED — четыре P1 и одно P2 уточнение до real execution.** Проверены frozen code/tests/doc, опубликованный proposal/critic, accepted100Q aggregate evidence и unchanged core/helpers. Actual full source,017 Parquets, модели/targets не читались; реальные prepare/production/source-oracle/fit/approval writes не запускались. Все изменяемые fixtures/harness/results — temporary synthetic inputs. Source-formula exhaustiveness остаётся следующим независимым gate, не результатом этого review.

Exact freeze до/после: script `f60b639f76bef61eeffaace4b6fccbb4beb4b733596c9e9a13a01a7149dab379`; tests `236350162119a07c071b7a6c0d9005b22e15adf9cf53fced59160c3245cae05f`; doc `aba04a198d29ce4c9c415636fd57af946f9bbace10c48996d035fc63f94a8656`. Файлы не редактировались.

## P1. Consumer не проверяет физический schema/key cover

`verify_accepted_export`, строки420–438, проверяет day schedule, output paths, report/manifest agreement и hashes. Actual Parquet schema/rows/keys не читаются. Следовательно, точный derived input plan и свежие output pins не обеспечивают обещанный structural consumption gate.

В собственном synthetic transport repro после здорового full export отдельно заменены: (a) query_id у всех строк одного feature day на другой key; (b) удалена колонка brand; (c) оставлена одна feature row. Каждая Parquet заново записана, SHA/bytes/rows/schema в manifest актуализированы, dependent report/day/counts и external acceptance pins согласованы. **Все три verify_accepted_export принимает.** Expected accepted Q/F inputs остались прежними; это не старый hash mismatch.

Минимально: после pin verification открыть outputs read-only, сравнить fixed physical schemas, actual rows с declared counts, query/day range/key relation с accepted Q, addon/provenance exact keyed cover с accepted F; проверить duplicate/orphan/full phase cover. Это structural validation, не повтор source-price oracle. FullR schema/keys/day и consistency также проверяются; source membership/values остаются задачей внешнего exhaustive oracle. Свежий approved JSON намеренно синтетический: finding не утверждает, что настоящий coordinator уже подписал плохие файлы. Оно показывает, что consumer доверяет approval там, где обещает независимо проверить cover.

## P1. Secondary audit failure теряет primary exception/partial status

`ExecutionAudit.stage`, строки220–226: если operation бросает ValueError, а CPU counter вfinally бросает OSError, именно OSError выходит наружу и становится report.error. Независимо воспроизведено: stage row сохраняет `INDEPENDENT PRIMARY`, но raised exception и top-level failure сообщают secondary CPU error. Это отдельно подтверждает coordinator finding без чтения его harness.

`__exit__`, строки270–280: итоговые peakRSS/temp/wall measurements и report write не защищены тем же first-error collector. В собственном fault primary ValueError + terminal RSS-counter OSError заменяют primary и оставляют disk report **running**, без failed partial evidence. Primary ValueError + failing report writer также поднимают writer OSError вместо primary; в этом варианте writer успел сохранить failed report перед ошибкой.

Исправление: сохранить исходное operation/with-body exception, counters/serialization/write errors записывать secondary, недоступные measurements — null. Собирать каждый terminal measurement независимо; best-effort failed evidence не должно снова заменить первопричину. Если финальный disk write невозможен, сохранить существующий partial и доступный in-memory/error evidence, не обещать невозможную durable запись. Timer cancel и connection close предпочтительно разделить, чтобы первая ошибка не пропустила вторую cleanup operation. Нужны regression cases именно для совместных failures, а не только counter failure на здоровом path.

## P1. Report CPU snapshot предшествует оплачиваемому terminal work

Строка261 снимает totalCPU **до** run.json serialization/write, затем строка270 публикует прежнее значение. Последующие guard читают настоящий counter и хорошо останавливают превышение900, но ledger недосчитывает terminal work нижеcap.

Независимый deterministic repro: run.json writer добавляет10mockCPU seconds, лимит900; операция успешно возвращает complete, report.process_cpu_user_system_seconds=0 при actualmockCPU=10. Это accounting defect, не настоящий10секундный fit/scan. Перенести final accounting boundary после оплаченных manifest/summary операций; явно описать минимальный неизмеряемый tail последнего report persistence и общий parent ledger, вместо объявления всей terminal стоимости нулевой. Корректный hardguard не исправляет неверное reported consumption общего009budget.

## P1. Accepted100Q input scope определяется самим gate identity

`verify_accepted_metadata_gate`, строки133–154, выводит required pins из identity.fingerprints и проверяет наличие семи GATE_CODE paths. Canonical acceptedtrain/spec/pyproject input map заново не выводится. Поэтому self-declared smaller input set получает exact-required agreement, хотя утрачено утверждение о том, что100Q run потребил полный reviewed input scope.

По дополнительному запросу coordinator independently проверен маленький gate transport: healthy synthetic identity содержит фактический tiny sourceDB и candidate producer code. Затем отдельно удалены source pin, candidate-code pin или actual spec-file pin; пересчитаны identity/runID, renamed output directory, output paths/hashes, execution approval, run/report и внешний source acceptance. Все три варианта **accepted**. В tiny record scope18→17pins; actual93record не менялся и не проверялся этим опытом. Это структурный аналог93→92, не заявление о дефекте принятого реального100Q audit.

Full prepare позднее merge-ит train pins, но это не доказывает прежнее input consumption именно gate run. Для обещанного exact100scope нужно вывести canonical gate input map из уже проверенного acceptedtrain + actual metadata spec +pyproject/current GATE_CODE (например reviewed mechanical prepare_gate_plan, без materialization) и потребовать identity equality; затем проверить execution/output/run/report additions. Другой допустимый узкий контракт — bind конкретный ранее reviewed immutable93map как external expectation, без обещания универсального scope rederivation. Одного scope/approvedtrue и вновь собранных hashes недостаточно для заявленного независимого mechanical proof. Source numeric values всё ещё проверяет отдельный oracle.

## P2. Phase cardinality пока не fulltrain diagnostic

`validate_day_arrays` считает encoded cardinality отдельно за день, а phase report не содержит union encoded values/cardinality. Предложение/doc говорят actualfull26000 diagnostic. Maximum/sum дневных distinct counts не заменяет union: две disjoint brand values в двух днях дают1/1daily и2phase. В tiny demonstration дневные diagnostics действительно1/1, phase result отсутствует.

Либо накопить exact encoded phase sets/counts с sentinels внутри budget, либо честно назвать текущий результат daily-only и отложить fulltrain diagnostic до019loader. Ни один вариант не должен veto0096000абляцию по26000vocabulary, обучать encoder наselection или включать CTR fallback. Это не найденный source-value defect и не повод добавлять fit.

## Что проверено и выдержало faults

`prepare_export_plan` повторяет accepted008 mechanics, shared source/registry/schema/roles/availability gap, связывает source-gate record и текущий code bundle; execution approval exactidentity отдельно от hash proposal. Actual93/113pin values этого review не пересчитывались: читались только опубликованные accepted100Q evidence и synthetic inputs. No target table load/parse видно по export path; Y hashes остаются provenance.

EXACT14 supplement проверен независимо на настоящем tiny017-produced lineage, без mock verify_collection: healthy принят; свежо resealed joint Q/C omission проходит legacy transport, затем rejected canonical14 gate. Expected map выведен из проверенных source/code/seals, включая query_coverage; F inputs/report runIDs проверяются отдельно. Frozen100/core/spec не меняются.

Producer идёт по calendar phase days, сохраняет Q сemptyC, использует reviewed daily440k paircap и cap22000unique model rows **до** fetchall/arrayallocation. Product-invariance grouping охватывает все18model fields до representation checks. Собственные transport fixtures подтвердили emptyC day: Q70/F0/provenance0/fullR2; calendar day безQ: четыре typed empty exports, day не исчезает. Эти fixtures не доказывают actual full source values.

Отдельные controls fake close wall+1300/CPU901/RSS8GiB+1, close error, manifest-write error и report-write wall overrun все дают failed+exception. Значит прежний false-success resource seam не повторён; новые P1 относятся к error preservation/accounting/consumer scope. Immutable existing-run refusal, no retry, source read_only и full producer key EXCEPT ALL checks присутствуют; independent direct-peer-list oracle ещё не выполнялся наfull inputs.

## Actual evidence и следующий gate

11scoped author tests независимо воспроизведены: PASS2,125s; ихCPU отдельно не измерен. Собственные24synthetic cases в четырёх invocations: суммарно3,768942s wall/4,207741s processCPU/maxRSS184877056bytes,0fits/0real-source reads. Неверные consumer accepts и audit failures не названы passed checks. Full runtime transport использует явно mocked prepare из tiny fixture; strict14 test использует настоящий tiny producer. Mutations/resealing/assertions собственные, не author test helpers.

Artifacts: `tlab009-full-independent-faults.py` + `...-fault-results.json`; `tlab009-full-independent-boundaries.py` + `...-boundary-results.json`; `tlab009-full-independent-resource-controls.py` + `...-resource-results.json`; `tlab009-full-independent-100scope.py` + `...-100scope-results.json`. После batchfix нужны новая exactfreeze и targeted re-review этих faults/healthy controls. До того real full production и source acceptance blocked; ablation/model_data/ONEfit/019/016 approvals остаются отдельно.
