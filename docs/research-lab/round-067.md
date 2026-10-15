# Round067 — минимальный reviewer protocol: runnable prefix и три честных STOP

**Concrete fresh-clone checklist/test proposal, 15 октября2026.** Прочитаны публичные README/data/018/reproduction docs, .python-version, frozen CLI signatures017/008/018 и synthetic tests006/016. Реальные данные, модели, approvals и WIP не открывались; downloads, installs, tests, SQL и fits не исполнялись. Это уточнение existing018/015/016 deliverable, не новый task/HYP/framework. Ниже команды — **будущая инструкция reviewer**, не выполненная проверка.

## Четыре результата, которые нельзя смешивать

| Режим | Independently regenerate | Что лишь связывается с historical claim |
|---|---|---|
| Source-free contract smoke | Typed definitions/closure/allocation и tiny expected values, метрики literal fixtures | Не реальные source values/качество |
| Source-derived rerun | DB/Q/C/Y/F при новом accepted source/context и независимых decisions | Старые physical DB/Parquet hashes могут не совпасть |
| Saved-model replay | Scores/ordered topK/fullY metrics из предоставленных CBM+exact input sidecars | Model bytes/tree count связываются с historical receipt; actual training weights не восстанавливаются |
| Retraining | Новая модель/outputs в отдельно ограниченной попытке | Это новая execution identity, не повторное использование старого approval |

CatBoost [save_model](https://catboost.ai/docs/en/concepts/python-reference_catboost_save_model) и [load_model](https://catboost.ai/docs/en/concepts/python-reference_catboost_load_model) сохраняют/загружают trained model, включая native CBM path. Это не обещание восстановить все inputs, весь fit ledger или labels. [Predict docs](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_predict) требуют соответствия feature columns; named matching возможно при names с обеих сторон, raw formula и tree range задаются явно. Numeric float32/NaN preprocessing, exact integer keys, B-first column order и scoring prefix поэтому должны идти отдельным manifest, а не угадываться из размера matrix.

## Runnable prefix без ignored state

Reviewer берёт конкретный published commit/release, записывает его identity и supported environment. Текущая validated platform — Mac CPU; Windows/Linux execution backend не объявляется проверенным. `.python-version` задаёт3.12, а historical accepted interpreter3.12.14: minor pin не является обещанием одинакового patch/runtime. Нужны actual interpreter/OS/architecture, lock hash и loaded package versions.

Из корня clone после отдельно разрешённого setup достаточно:

```sh
uv sync --locked
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -m unittest discover -s tests -p test_feature_programs.py -v
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -m unittest discover -s tests -p test_ranking_metrics.py -v
```

Эти существующие scopes используют tiny/source-free inputs, без real datasets/native fits. Первый показывает genuine template→definitions и selected additions на synthetic compiler; второй — fullY/empty/censored/aggregation semantics. Они не удостоверяют качество016 и не дают real execution approval. Full suite не нужен как минимальный пример: в нём другие resource/API scopes.

[uv docs](https://docs.astral.sh/uv/concepts/projects/sync/) уточняют: `uv run` автоматически lock/sync, `--locked` запрещает обновление устаревшего lock, `--frozen` пропускает проверку актуальности. Поэтому reviewer recipe использует locked и проверяет code/config/lock bytes до/после. Это не утверждение, что нынешний README обязательно меняет lock при неизменном checkout.

## Source provenance: download — отдельный необязательный здесь этап

[REES46 publisher catalogue](https://rees46.com/en/datasets) различает Multi-category behavior events и отдельные transactions datasets. Reviewer нужен именно указанный в [data.md](../data.md) октябрьский gzip и его опубликованный **compressed-byte** SHA256/size; текущие URL/ETag не заменяют этот check. Ни archive endpoint, ни содержимое файла в этом pass не запрашивались.

По [RFC9110 §8.8.3](https://www.rfc-editor.org/rfc/rfc9110.html#name-etag) ETag — opaque representation validator, не обязательно cryptographic content hash. Timestamp HTTP ответа не event coverage. Resume download может остаться partial или получить иную representation; только complete-file digest/size и gzip integrity задают принятый historical input. Mismatch означает STOP historical replay, а не автоматическую замену ожидаемого SHA. Новый корректный publisher file потребует нового source decision.

Public checksum связывает полученные bytes с прошлым публичным record; он не доказывает полноту marketplace logging/ingestion truth. После EDA/DB regeneration нужны typed schema, row/duplicate/time/category/coverage evidence. Physical DB SHA фиксирует конкретный artifact, но не является универсальным ожидаемым hash для любого independently generated DB. Source-file identity и DB-artifact identity сохраняются раздельно.

## Три точных handoff-пробела existing018

**STOP1: proposal до producer.** `development_collection` CLI требует `--producer-approval` и `--shard-acceptance-dir`; public `prepare_execution_plan` существует, CLI plan-only export отсутствует. Для fresh workflow нужен документированный proposal/evidence handoff до paid producer call, а не шаблон `approved=true`. Это существующий018 phase2 gap.

**STOP2: source proof до fresh seal.** `verify_development --project-root ... --expectations ...` принимает уже reviewed collection; она не создаёт pre-acceptance source decision. Новый Q/C/Y shard и F требуют независимого semantic evidence с exact supported registry/context, затем отдельного decision, связывающего pins/evidence/policy. Current manual18 numeric scope sampled; selected12 требует своего exhaustive oracle. Producer hashes сами не источник такого решения.

**STOP3: replay без fit.** `train_baselines` CLI требует train/selection acceptances и `--fit-approval`; это training runner, не публичная команда «загрузить CBM и повторить metrics». Для minimal reviewer numerical replay нужен существующий050 seam: documented CBM/schema/prefix или keyed-score/fullY inputs и read-only output. Если artifacts не предоставлены, остановиться после mechanics+audit, не запускать новый fit ради проверки чужого aggregate. New retraining требует fresh limited approval/claim и собственного source/model audit.

## Один future acceptance drill, без запуска сейчас

Existing018/README scope может проверить clone в новом path с пробелами и отсутствующими ignored approvals. PhaseA выполняет ровно два synthetic scopes выше и сохраняет versions/exit/unchanged bytes. PhaseB подаёт tiny project-relative package≤32inputrows: missing approval, freshly resealed wrong value, BIGINT2^60+1+NULL, emptyC, outside-C target, reordered feature schema и неправильный prefix. Каждый negative case обязан остановиться на declared gate **до native fit**, не записать acceptance и сохранить failure evidence. Healthy case доказывает только заявленный synthetic/replay scope; real rerun остаётся отдельным разрешённым этапом.

[CatBoost FAQ](https://catboost.ai/docs/en/concepts/faq) прямо отмечает GPU nondeterminism от summation order. Это запрещает обещать identical retraining лишь из seed, но не доказывает произвольность CPU replay; criteria exact keys/topK/metrics и bounded score difference различаются по051 и фиксируются заранее. Нет новых tolerances, fits или budget. **No-add:** закрыть три существующих handoffs018/050 и честно назвать runnable prefix; task1 reproduction нельзя заменять ни private approval из чата, ни повторным поиском удачного результата.
