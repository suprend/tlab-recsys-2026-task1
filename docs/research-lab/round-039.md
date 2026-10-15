# Research lab, round039: label-blind held-out inference и reporting-only lock

15 октября2026. **Concrete prospective protocol**, не implementation/config/execution approval. Прочитаны [038](round-038.md), actual [model_data](../../scripts/model_data.py), [temporal contract](../../scripts/temporal_contract.py), [clock-v1](../../configs/protocols/clock-48h.json) и [confirmation config](../../configs/development/confirmation.json). Held-out data/targets/models не открывались; SQL/tests/Pool/fit/code/config/Root files не менялись. Исходная confirmation24–25/final26 schema остаётся прежней; reporting-only25/final26+ ниже — amendment для отдельногоreview, не молчаливая переинтерпретация существующего approval.

## Method boundary и текущая несовместимость loader

[Ji et al.](https://arxiv.org/pdf/2010.11060) обосновывают global timeline: interactions/items из будущего относительно query не должны определять его prediction. [Cawley–Talbot](https://jmlr.org/papers/v11/cawley10a.html) показывают selection-criterion overfitting; поэтому внешний prediction seal не исправляет уже использованный для выбора holdout. [ML Metadata](https://www.tensorflow.org/tfx/guide/mlmd) различает artifact, execution и lineage events: это полезная структура доказательства порядка действий, не готовая авторизация или статистическая гарантия.

`prepare_model_data` сейчас **отвергает confirmation/final role**. В разрешённых train/selection режимах после Q selection он всегда загружает `refs['labels']`, строит chosen_labels/full targets, создаётyarray и joinlabels. Это правильный development scope, но не label-blind inference. Простое удаление role guard, `labels=[]`, fakezeroY или стираниеyпосле чтения не удовлетворяют новому contract. Новая функция/режим требует самостоятельного review, сохраняя existing training loader.

## Decision lock и две шкалы времени

Предлагаемый единственный whole-pipeline choice связывает selected B и016winner, AST/programs, schemas/physical masks, source/protocol/QC context, population/weights, parameters, trainediterations/scoringprefix и tie/evaluator/report policy. Никаких refits, adaptive repairs, feature/loss/model changes или promotion после confirmation.

Simulated2019: `Msel=max used label maturity=24Oct00`, `Dready≥Msel+ε`, `ε>0`, `Dready<25Oct00`; dependency fit/availability согласованы. Старое modelavailable22 не делает новое selectiondecision доступным22. Предложенный final26+ использует те же frozen models/rules, поэтому maturityconfirmation26 не требуется для нового выбора — его нет.

Actual2026: immutable model/program/decision hashes фиксируются до held-out inference. **Все scheduled held-out predictions для обеих branches, confirmation25 и полного заранее выбранногоfinal range, sealed до открытия любого query-level held-out Y/evaluation.** Parent receipts доказывают физический порядок, не наличие model files в2019. Schedule/query scope фиксируются заранее; «ALL» не определяется surviving outputs после failures.

## Permitted relations и запрещённые capabilities

Label-blind inference inputs: reviewed Q/C/F descriptors, frozen model/program/schema, source/context digests и execution limits. Q содержит exact keys/user/anchor; C фиксирует past catalog/retrieval без target insertion; F покрывает каждый `(query_id,item)` и следует strictpast `[S,t)`, windows/metadata/globalpeers. Maturity flag допустим только как calendar/coverage metadata, не outcome-derived selector. Past eligibility/hash sampling не читаетfuture positives.

Inference descriptor/API не имеет labelrefs/paths, labeltable, targetsets, yarray, evaluation callback или metric branch. Нельзя передать полный development collection и надеяться, что labels останутся unused. Upstream already-declared mechanical digests могут оставаться в audit lineage, но это не разрешение открыть/hash-read query-level held-out labelfile через inference helper. До unlock нельзя вызывать fullY evaluator или producer helper, который автоматически создаёт/читаетY.

Source-backed feature materialization/independent oracle имеют отдельную whitelist rawevents и точные per-anchor predicates; expected formulas не получают held-outY. Future sourcebytes уже доступны offline и whole-month EDA известна: claim — **запрет query-target/evaluation feedback в решении**, а не абсолютная информационная blindness. Например25purchase event законно входит в26past counts и observed catalog, но не25features; это не refit/selection. Temporal predicates должны применяться глобально, без invented order peers.

## Артефакты и terminal transition

| До Y opening | Обязательное evidence |
|---|---|
| Prospective lock | Calendar/branches/QC quotas/program/model/schema/parameter hashes; full consumed development history; noadaptive policy |
| QCF inputs | Exact schema/types/key cover/coverage, strictpast source proof для заявленногоscope, immutable pins |
| Prediction outputs | Raw score для каждой C-row, branch/query/item keys/order, scoringprefix/model hashes, finite/type/tie policy |
| Query coverage | ВсеQ включая emptyC; offsets/counts отдельно от score rows, no fabricated candidate |
| Terminal seal | Exact outputs/hashes, successful exit, cleanup complete, measured CPU/wall/RSS/spill, resource gate и external decision |

Inference сохраняет integer keys без float transport, feature order/float32/NULL encoding совпадают с frozen model assembly. EmptyC query имеет0score rows, но остаётся вQ/report coverage; ошибка не превращает его вzeroY. Duplicate/missing/extra keys, changed pins, wrongschema/values/modelprefix или unknownusage — STOP. Partial output не seal-complete; поздняя ошибка не разрешает открытьY «для диагностики» или выбрать только удачно scored days.

Source correctness, preservation acceptedB, model-input assembly и saved-score fidelity — различные proof scopes. Original018sampled manual18 numeric checks не переименовываются exhaustiveBsourceproof. New01612columns требуют отдельно принятого independent source oracle035. Наличие hashes само по себе не заменяет этот evidence и не позволяет producer auto-approve.

## После all-prediction seal

Только отдельный reviewed unlock открывает fullY/evaluation. Используются заранее заданные fullY denominators/ties/maturity, включая outC misses/zeroY/emptyC; evaluator не меняет Q/C/models. Confirmation отрицателен или неопределён — честный reporting-only результат, final остаётся тем же. Это quality failure, не permission rescue и не автоматическое integritySTOP. Source/API/lineage/resource fault — STOP prospective claim; после его обнаружения нельзя молча исправить prediction и сохранить прежний «один взгляд».

Если нужны postconfirmation изменения, они становятся новым retrospectivedevelopment/protocol amendment с раскрытием consumed outcomes; нынешний prospectiveclaim прекращается. Нельзя бесплатно сдвинуть final, подобрать другуюветвь/threshold, refit или назвать already-open targets «новым holdout». Negative result не скрывается; reporting-only не означает confirmatory superiority.

Для source `[1Oct,1Nov)` right-open target31Oct00/H24/δ0 mature1Nov00 **только при полном coverage**. Поздние anchors/ненулевой delay/неполный horizon censored; нельзя сделатьzeroY из отсутствующихNovemberevents илиобъявитьlivefuturebytes. Frozen final range/maturity policy должны зафиксировать этуграницу доopening.

Минимальные future fault obligations, без запуска/бюджета сейчас: forbiddenlabelref rejected доI/O; label-reader/evaluator spy не вызывается; emptyC retained; event25меняет26features, но не25; corruptlastprediction/failedcleanup оставляютunlockclosed; changedmodel/program послеseal rejected; negativeconfirmation не меняет finalbranch. Все preparation/oracles/readback/sealing/failures входят в existing authorized ledger, не новую allowance. До отдельногоcode/source/resource/chronology review никакой held-out execution или configchange этимnote не разрешён.

## Уточнение actual003 seam: Q отдельно от Y

Статически [create_queries](../../scripts/anchor_pilot.py#L142) строит past eligibility/hash-sampled Q отдельно от [create_labels](../../scripts/anchor_pilot.py#L202). Future driver может переиспользовать только этот Q primitive, затем label-blind candidate generator/manual compiler при новых reviewed input manifests. Generic `build_pilot`/`run` вызывает labels/history outcome summary и экспортируетpilot_labels: доpredictionseal запрещён.

Есть конкретный interface gap: create_queries записывает `label_is_mature=None`, а [candidate validate_queries](../../scripts/candidate_pilot.py#L24) отвергаетNULL. Нужен отдельно reviewed **calendar-only maturity annotation** по target endpoints/availability delay/source coverage доC/F; нельзя вызыватьcreate_labels радиflag или создаватьfakezeroY. Правильность этой annotation и отсутствиеYaccess требуют отдельной tinyfault проверки; существующий publicQseam не означает готовый held-outdriver. Никаких вызовов primitive или codechanges сейчас не выполнено.
