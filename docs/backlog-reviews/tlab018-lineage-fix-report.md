# TLAB018: scoped lineage fix handoff

15Oct2026. **FROZEN, ready for targeted independent C11 re-review; not code acceptance or real-execution approval.** Изменены только [verifier](../../scripts/verify_development.py), [synthetic tests](../../tests/test_verify_development.py), [workflow](../experiments/verification-workflow.md). Accepted005/007/008/017, данные, dependencies, Git state и actual approvals не менялись. Создавались только временные tiny fixtures/evidence; real source scans, fits, regeneration и acceptance writes отсутствуют. Исходный independent review и его repro/evidence сохранены без изменений.

## Закрываемые findings

В версии9d0e30c61def76206f150054566399433357e401c22a0a7a9f870e5ba7282bb6 P1 позволял approval определить собственный scope: удаление actual Q/C из approval и F inputs с resealing всей цепочки давало verified. P2: candidate report.anchor_run_id и feature report anchor/candidate IDs могли противоречить manifests, тоже с verified. Source-formula значения оставались корректными; findings относятся к mechanical provenance.

Теперь upstream map выводится из independently pinned source, exact am/cm code/input maps и всех am/cm physical seals. Для текущей017 policy ровно14 paths: source1; union code/lock5 (`uv.lock`, anchor/candidate/protocol/temporal scripts); anchor run/report/Q/Y4; candidate run/report/C/query_coverage4. Approval keys **и values** должны равняться этому derived map. F input map равен именно derived map плюс approval-file SHA, manual18 registry и единственная actual selection definition. Missing/extra approved paths не легализуются fresh hashes. Это explicit stricter project policy, а не изменение required-minimum007 contract.

Candidate report anchor ID связан с actual am.run_id; feature report anchor/candidate IDs — с actual am/cm.run_id. Связь selection.source_candidate_run с actual CM сохранена. Production verifier не импортирует global-ROOT helpers005/007, не мутирует их globals и не исполняет artifact-supplied code. Semantic source oracle и final cleanup/resource sealing не менялись.

## TDD и meaningful faults

Новые public verify-seam tests добавлены до code fix. Четыре targeted tests дали девять failures: свежо resealed omission Q, C, coverage, code, extra input, joint Q/C и три report-ID faults получали verified. Source omission уже отклонялся старым обязательным child-source guard; этот boundary сохранён regression. Затем минимальный fix дал4targeted PASS3.116s.

Resealing helper выделен из прежнего synthetic rewrite_output: пересчитывает byte lineage, сохраняя намеренно неверные upstream report IDs. Это важно: helper не должен исправить fault до вызова verify. В одном scope regression семь subcases; ещё три отдельных report-ID tests. Переименование roots, synthetic source semantics, full-Y misses, empty queries, category/null grains, physical types, registry/pin faults и resource-finalization tests сохранены.

Полный **только018** synthetic suite:29tests PASS14.522s, exit0. Измеренная invocation: wall14.613055s, child processCPU16.041083s, process peakRSS149159936bytes,0fits/0real-source reads. Invoked `.venv/bin/python -m unittest discover -s tests -p test_verify_development.py -v` с `PYTHONDONTWRITEBYTECODE=1`. Full repository suite не запускался. Scoped `git diff --check` для трёх owned files — exit0.

Отдельно replay исходного независимого Tiny/reseal implementation, без авторского test helper: healthy verified; original joint Q/C omission failed `lineage.shard_approval_scope`; candidate wrong anchor failed `lineage.candidate_report_ids`; оба feature report faults failed `lineage.feature_report_ids`.5cases, wall1.698520s/CPU1.856857s/peakRSS135806976bytes,0fits/0real-source reads. Это авторский повтор независимого repro, **не новая independent acceptance**. Старые independent JSON evidence не перезаписывались.

## Exact freeze

- scripts/verify_development.py SHA256 `60519794c8c5b8bc7ac04f960e554f13ab3e125043c2a0e46d53f67ea0810ee0`
- tests/test_verify_development.py SHA256 `dec1291cc9db51546532bcc2d851d38abf2e273d027d9b847781449f049edd73`
- docs/experiments/verification-workflow.md SHA256 `a18a15d4665ce6cf89e5f4de7e162c4a81cd5700f9327ef47c652888b29f27f1`

Следующий gate: C11 independently проверяет actual freeze, P1 omissions/extra/value-map scope, P2 links и healthy/resource regression. Совместимость14-map с шестью actual approved shards сообщена coordinator, здесь real artifacts не читались. Existing-sealed manual18/protocolv1 restriction остаётся; QYC exhaustive, F rowset/schema exhaustive, numeric F sampled. All-empty raw-source017 limitation остаётся failclosed. Real scans, regeneration, acceptance-writing, metadata009/extensions и exhaustive numeric F не включены и требуют отдельного scope/решения.
