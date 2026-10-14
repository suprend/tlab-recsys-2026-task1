# TLAB-008: независимый review frozen CPU smoke runner

15 октября 2026. **Вердикт: material changes requested.** Два воспроизводимых P1 нарушают заявленную связь approval↔исполненный эксперимент и предел двух fit attempts. Real-fit approval до исправления не выдавать. Проверены [runner](../../scripts/train_baselines.py), [scoped tests](../../tests/test_train_baselines.py), [config](../../configs/models/cpu-smoke.json) и [документация](../experiments/boosting-baselines.md). Repo/Git/code/deps/data не менялись; production/real collections/реальные модели не запускались. Все дополнительные fits — только tiny synthetic, один-два дерева, во временных isolated fixtures. Root017 artifacts не менялись.

## Actual version/tests

SHA-256:

- runner `13ff2ee4b2ee77e1618b7175516b77306185b8377c4611c0344e8ba7af6819dc`;
- tests `2714fbef1798d5e6d4206d47aeb58e6e56a63f19a7fb26db80b5380420e52887`;
- config `d8140e4581e6aa769af75f3638a697bb7224943ce1f6dcd1c5cd4588ed27c14a`;
- documentation `6a8117f8d6af720fb8aee764ae84c9ae774776a01fb361dcaaa003afe0a9ca55`.

Все совпали с handoff. Repo venv/PYTHONDONTWRITEBYTECODE=1, `unittest discover -s tests -p test_train_baselines.py -v`: **14 PASS, 1,104 секунды, exit0**. Заявленные137fullPASS reviewer не повторял: остальные WIP вне scope. Passing suite не закрывает два дополнительных repro.

## P1 — тот же approval разрешает бесплатные повторные fits через другой output root

[Identity guard](../../scripts/train_baselines.py#L435) ищет existing experiment только под переданным `output_root/run_id`; output root не связан с approval и нет общего atomic consumption ledger. CLI позволяет выбрать другой каталог под artifacts. Поэтому заявленное «одна approved identity — ровно две попытки» действует лишь внутри одного output root.

Независимый repro использует SmokeRunnerTests synthetic fixture: accepted-plan/data preparation подменены фиксированными fixture values, остальные run/approval/export/native CatBoost fits настоящие. С одним config, неизменным approval и одним manifest:

```python
run(config, train, selection, artifacts / "first", fit_approval_path=approval)
run(config, train, selection, artifacts / "second", fit_approval_path=approval)
```

Actual: оба `complete_produced_unreviewed`, одинаковый run_id, **четыре actual native tiny fit calls**, по2 attempts в каждом report. Никакого нового budget approval не было. Это штатный параметр CLI/API, не удаление или подделка существующих artifacts. После partial fit смена root также обошла бы refusal/recovery и повторно потратила слоты.

**Минимальное исправление:** независимо от output root атомарно claim/consume approved experiment identity в одном canonical artifacts-level ledger до первого fit; concurrent/relocated calls должны видеть прежний claim. Либо approval явно связывает единственный canonical destination и такой destination строго проверяется вместе с exclusive identity guard. Сохранить failed evidence и reviewed-budget recovery, не разрешать новые fits по свежему hash прежнего approval.

Необходимые regressions: second output root с тем же approval отказывает до native fit; failed-first experiment также нельзя повторить в другом root без отдельного recovery; concurrent claim эксклюзивен. Разные output paths не должны сами предоставлять дополнительные попытки.

## P1 — исполняется первый parse config, approval проверяет второй

В [run](../../scripts/train_baselines.py#L423) config читается и задаёт deadline. Затем [prepare_fit_plan](../../scripts/train_baselines.py#L364) заново читает config и включает новый config/hash в identity. После проверки approval runner продолжает использовать **первый local config**, не сравнивая его с verified identity config. Final hash-check проверяет уже второй pinned файл.

Независимый atomic-replacement fault: первая parse читает iterations1; на boundary подготовки verified plan файл заменяется заранее approved config iterations2. Synthetic prepare-plan stage возвращает корректную identity/fingerprints нового содержимого, data fixture неизменна, реальные native fits выполняются. Actual report:

- current pinned file iterations2;
- approved/run identity config iterations2;
- обе модели имеют tree_count1, report.config iterations1;
- status `complete_produced_unreviewed`; final fingerprints проходят.

Таким образом, параметр эксперимента может отличаться от проверенного approval без итогового отказа. Аналогично расход времени может определяться старым wall_seconds. Repro проверяет конфигурационный seam; он не изображает real-data production или independent collection acceptance.

**Минимальное исправление:** после verified plan и до fit approval/claim обязателен exact equality первого config с `manifest.identity.config`, либо единственный effective validated config берётся из verified plan и deadline пересчитывается от original started_at. Нельзя продолжать с непроверенной копией. Regression заменяет файл между parse иplan и требует отказа с0fit либо согласованного исполнения approved config; report/model parameters/identity/deadline должны совпасть.

## Что выдержало substantive проверку

BCE row mass1/|Cq| корректна для всех mature непустых C, включая empty-Y/missed-positive/all-positive groups. PairLogit удерживает informative groups, explicit p×n pairs с mass1/(pn), indices remapped на compact Pool. Это loss+population-policy comparison, не чистый loss-only effect. Pair cap проверяется до allocation; беспарный train не получает invented negative. Groups contiguous, raw IDs/time keys исключены из числовой матрицы; retrieval timestamp становится strict-past age/mask. Label-independent query subset выбран до чтения Y.

Full Y хранится отдельно от C, empty-C queries остаются в ranking/evaluator; raw-score ties разрешены product_id ASC. Native eval_set/OD/best-model selection отсутствуют, smoke использует заранее фиксированную final iteration, tree_count сверяется. Поэтому external006 metrics оценивают заявленный smoke checkpoint; новый tuned/full-Y selection runner этим ещё не реализован. Selection bootstrap явно screening-only, winner/promotion не объявляется.

Collection verifier требует внешний `reviewed_development_collection` approval, exact required pins без missing/extra, plan/state/complete report, source/config/code/lock, Q/Y/C/F seals и upstream acceptance/spec paths. Existing tests проходят actual synthetic017 lifecycle; current fresh hashes сами approval не создают. Train/selection temporal policies, source/registry/model timing совпадают; fit gap положительный и wall budget в него помещается. Confirmation/final input отвергается. Это проверка конкретных accepted artifacts, не semantic oracle их значений: real017 independent reconciliation/collection acceptance остаются prerequisite.

Дополнительные independent faults/values:

- actual Parquet count и last_user_event_time=NULL превращаются в float32 NaN, retrieval missing flag1; не заменяются настоящим0;
- RSS9GiB до preparation даёт failed audit, collection reads0, fits0;
- actual native callback TimeoutError внутри iteration даёт failed report, attempts1, no CBM export и no second fit;
- same-root immutable retry и неправильный approval scope уже проверены scoped tests; cross-root обход выявлен отдельно.

Guard cooperative: проверяет deadline/RSS до/после этапов и между native iterations; долгий единичный SQL/Pool/predict/export не становится OS hard limit. Row cap и float32 matrix bytes не доказывают peak process memory. Actual full train/selection throughput, CPU/RSS/spill не измерены; preparation/evaluation/failures должны войти в общий compute ledger, не только fit-time.

## Acceptance boundary после фиксов

После revised frozen code scoped tests и повторных обоих repro возможен code-only accept. Затем нужен approval конкретного fit plan с independently accepted017 train/selection, текущими pins и оставшимся budget; сейчас real коллекции ещё не приняты. Повторный fit после ошибки требует reviewed recovery, не смены директории. Ни исправление, ни два50-tree smoke fits не устанавливают strong tuned B или исследовательский выигрыш task1.

Отдельный future gate: selection labels24Oct00 совпадают с first confirmation24Oct00. Нужны prospective decision gap, фактические metric/selected-model availability и timely lock; checkpoint ready22Oct этого не решает. Confirmation/final holdout остаются закрытыми. Никаких real fits этим review не разрешено.

## Audit: owner начал исправление после передачи findings

Повторная SHA-проверка в конце review обнаружила уже изменённые owner files: runner `660cc62268093e0aa81e23ec4c46761a1487ef0997d8db32eb1ec679cd97543e`, tests `684ed81a8ba2521e67a59fabc3ed30d1014231971c2c905ca22b1820de88bf34`; config/docs прежние. Это не reviewer mutation. Findings,14PASS и номера строк выше относятся к первоначальной frozen версии13ff2ee4…/2714fbef…. Новую версию этот initial report не принимает: необходимы отдельный completion handoff, actual revised-code review и scoped/repro verification. Исходный audit сохраняется.
