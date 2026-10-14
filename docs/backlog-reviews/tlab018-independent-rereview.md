# TLAB-018: targeted independent re-review

15 октября2026. **ACCEPT CODE ONLY: existing-sealed protocolv1/manual18 readonly verifier.** Исходные P1/P2 закрыты на новой exact freeze; новых material blockers в targeted scope не найдено. Это не разрешение real collection scans, regeneration, первичного approval или acceptance-writing. Actual017 Q/Y/C/F и sourceDB не читались; source operations были только над tiny synthetic fixtures в temporary roots.

## Exact version и сохранение истории

Проверены до и после всех запусков:

- `scripts/verify_development.py`: `60519794c8c5b8bc7ac04f960e554f13ab3e125043c2a0e46d53f67ea0810ee0`;
- `tests/test_verify_development.py`: `dec1291cc9db51546532bcc2d851d38abf2e273d027d9b847781449f049edd73`;
- `docs/experiments/verification-workflow.md`: `a18a15d4665ce6cf89e5f4de7e162c4a81cd5700f9327ef47c652888b29f27f1`.

Первоначальный `tlab018-independent-review.md` byte-identical: SHA256 `cf8a1c1d1fce6ebd65a774f1319e2ca0cb69902bd2121e18c1379e37b13e23da`. Его CHANGES_REQUESTED/failure evidence не переписаны. Новые helper/results/report имеют отдельные имена; прошлые false-verified результаты остаются audit history, не выдаются за результат исправленной версии.

## P1: mandatory approval map теперь независим от approval

Новый код выводит upstream map из actual проверенных source, am/cm code/input maps и всех физических anchor/candidate seals. Получается ровно14paths: source1, union code/lock5, anchor manifest/report/Q/Y4, candidate manifest/report/C/query_coverage4. Сравниваются одновременно keys и values approval с этим derived map. F inputs должны равняться derived map плюс approval-file SHA, registry и единственная actual selection definition.

Таким образом произвольный approval больше не задаёт себе обязательный scope. Проверка строгих14pins — явно документированная policy этой итерации; она не приписывается более широкому старому required-minimum API007. Derived maps ещё проходят прежние child source/code/input checks, поэтому их union не разрешает обойти source binding или candidate consumption anchor outputs.

Независимо повторён **original joint Q/C omission**: удалить actual queries/candidates hashes одновременно из approval и F manifest, заново reseal identity/run_id, reports, seals, state и верхние external pins. Теперь `failed`, gate `lineage.shard_approval_scope`, до source semantic stages. Отдельные удаления query, query_coverage и producer code pin дают тот же gate. Extra approved/input path с действительным файлом и свежим верхним pin также rejected. Wrong approval digest при правильных physical bytes rejected именно map equality. Удаление C только из F inputs rejected `lineage.feature_inputs`; source omission из approval/F rejected прежним `lineage.child_source`.

## P2 и cleanup regression

Все три исходных report-ID mutants сохранены намеренно при resealing: candidate report неверный anchor ID→`lineage.candidate_report_ids`; feature report неверный anchor либо candidate ID→`lineage.feature_report_ids`. Healthy bundle проходит все lineage/QYC/F stages. Helper обновляет закономерно изменившиеся downstream IDs, но не исправляет явно внесённый mutant; author rewrite_output/reseal helper не использовался.

Шесть cleanup regressions выполнялись после здорового lineage/source пути: fake close wall+700 и processCPU+700→`budget.deadline`; RSS536870913→`budget.rss`; close exception→`cleanup.close`; недоступный counter→failed partial resources с RSS null. Primary semantic exception вместе с close exception сохраняет `independent.primary`, а cleanup.close отражает secondary failure. Ни один fault не вернул verified. Реального sleep или расхода700CPU seconds/памяти сверхcap не было: значения подменены только в synthetic fault instrumentation.

## Actual evidence и границы

Собственный `tlab018-independent-rereview.py` выполнил18cases: один healthy,11lineage faults,6cleanup faults. Все17faults failed, healthy verified; результаты `tlab018-independent-rereview-results.json`. Измеренная invocation: wall5,001701s, processCPU5,496802s, peakRSS141770752bytes,0fits/0real-source reads. CPU — process counter, fake increments вне итогового measurement. Авторские29scoped tests независимо воспроизведены: PASS14,755s; их CPU отдельно не измерялся и не добавлен к числам собственного harness. Full repo suite не запускался.

Expected source logic/resource finalization не расширялись; прежний code review и semantic/readonly faults относятся к неизменённым участкам, новый suite также сохраняет эти regressions. Q/Y/C и F rowset/schema checks exhaustive в рамках данного API; numeric F и metadata/support values остаются deterministic sample. Этот re-review не превращает sample в полный numeric proof и не подтверждает actual шестишардовую совместимость без отдельного coordinator evidence.

Durable public readonly CLI может быть принят в указанном существующем sealed workflow. Clean-environment installation, перенос реального source, complete regeneration, all-empty upstream017 producer fix,009/new grammar и explicit acceptance-writing остаются отдельными reviewed scopes. Repo/Git/dependencies/frozen artifacts/реальные approvals в ходе проверки не изменялись.
