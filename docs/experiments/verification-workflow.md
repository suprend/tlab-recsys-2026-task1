# TLAB-018: независимая проверка существующего development bundle

Первая итерация принята после [независимого targeted code/fault review](../backlog-reviews/tlab018-independent-rereview.md), только synthetic verification. Реальные source scans и regeneration ещё не запускались и этим документом не разрешаются. [CLI](../../scripts/verify_development.py) проверяет существующие внешне закреплённые017 outputs; [tests](../../tests/test_verify_development.py) создают исключительно временные искусственные fixtures.005/008/017 code и принятые artifacts не меняются. Новых dependencies, model fits и acceptance writes нет.

## Публичная граница

`verify(project_root, expectations_path, *, seconds=300, rss_bytes=512*2**20)` возвращает агрегированный evidence. Ошибка поднимает `VerificationError` с partial `evidence`, status failed и failure_gate. CLI печатает такой evidence и возвращает1; verified возвращает0. Нет raw rows, user/item/query IDs или sampled tuple IDs в evidence. Collection/expectations/verifier hashes — provenance, не идентификаторы пользователей.

Ожидания первой итерации совместимы с **ранее принятым** external JSON scope `reviewed_development_collection`: version1, approved true, collection_id, named complete_attempt_report и exact fingerprints. Это restriction existing-sealed-bundle workflow, а не режим первичного одобрения свежего producer. Verifier не составляет fresh expectations и не утверждает, что producer сам может выдать review. Pre-acceptance source verification, regeneration и перенос reviewer decision в новый approval — отдельная будущая фаза.

Пример формы команды после независимого code review и отдельного source/resource разрешения:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m scripts.verify_development \
  --project-root '/path/to/fresh project' \
  --expectations artifacts/acceptance/reviewed-collection.json
```

Здесь пути placeholders; команда не скачивает данные и не устанавливает окружение. Interpreter должен быть подготовлен по принятому lock отдельным setup. SourceDB и matching ignored artifacts/expectations предоставляются отдельно. CLI требует project root; project-relative dependencies и symlinks, выходящие за него, отвергаются. Новый root может содержать пробелы; metadata/report диагностические machine paths не используются как input location.

По умолчанию outputs открываются для чтения, sourceDB attached READ_ONLY, tables — in-memory. Spill выключен, engine requested memory128MB; ничего не экспортируется автоматически. Явный `--evidence-out artifacts/verification/new.json` пишет **один новый** файл в существующий project-relative parent; exclusive create отказывает перезаписи. При ошибке явный файл может содержать только failed partial evidence. Source/state/reports/seals/старые evidence не исправляются.

`--write-acceptance` отсутствует и отвергается parser. В следующей фазе такой режим потребовал бы отдельный reviewed decision, связанный с exact evidence/policy/pins, повторную проверку bytes и immutable create. Один CLI flag или complete stdout не авторизация acceptance.

## Что проверяется

Механическая часть читает exact plan/state/named complete attempt, source/config/lock/producer code/registry, child manifests/seals, external shard approvals и full selection definition. Identity source/registry/code/phase связаны с execution fingerprints и actual phase body; exact producer input set и child Q/Y/C→F lineage обязательны. Missing/extra pins и changed bytes отвергаются, в конце все pins и expectations перепроверяются. Runtime DuckDB сверяется с lock; версия и SHA самого verifier входят в evidence.

Для текущей017 policy shard approval имеет **exact14** fingerprints, выведенных verifier независимо из уже проверенных upstream manifests/seals: один source, пять union code/lock inputs, четыре anchor files (run/report/Q/Y) и четыре candidate files (run/report/C/query_coverage). Проверяются exact keys и hashes, включая coverage; approval не определяет собственный допустимый scope. Это намеренно более строгая project policy, чем required-minimum public007 contract: дополнительные pins здесь unsupported, не автоматически accepted. F identity обязан содержать ровно этот derived map плюс approval-file SHA, manual18 registry и одну actual selection definition. Candidate report.anchor_run_id равен actual anchor manifest ID; feature report anchor/candidate IDs равны actual am/cm IDs. Политика не использует global ROOT из producer helpers и не исполняет code из artifact paths.

Поддержка ограничена reviewed protocolv1 clock с24h target `[t,t+24h)`, всеми view/cart/purchase eligibility/recent types и **точной** manual18 registry, включая header policies. Train/selection допустимы, confirmation/final закрыты. Unknown registry/оператор/окно/политика не аппроксимируется.009 metadata addon и автоматические extensions пока unsupported. Public JSON/protocol/manifest validators общие; source formulas не вызывают query sampler, category resolver, counters или feature compiler producer.

Q/Y/C реконструируются прямым source SQL для каждого exact anchor: past eligibility, bottom-SHA **до labels**, diagnostics/coverage/maturity; полный distinct Y с raw multiplicity/first time/catalog/pair diagnostics; distinct-buyer popularity и recent-source ranks/ties/union/no-refill. Bidirectional EXCEPT ALL сравнивает relations. Проверяются exact shard/day cover, физические names/order/types, уникальность и orphan keys. Все mature zero-purchase Q и empty-C Q сохраняются, Y вне C остаётся miss; aggregate population/counts выводятся отдельно. Source ingestion completeness этим не удостоверяется.

F имеет exhaustive exact C rowset, восемь immutable retrieval columns, query user/anchor,45-column schema/types и cheap range/core missing-flag checks. **Числовые значения F проверяются только на explicit deterministic sample**: до4 bottom-hash pairs на anchor плюс до1 в каждой strata pair-view support/category-missing/category-ambiguous/pair-purchase support/observed recency старше7d. Union дедуплицируется; available и sampled counts каждой strata публикуются, пустая strata не pass. Sample не меняет train/evaluation population.

Для каждой sample pair Python source-row oracle вычисляет все18 core formulas, latest global timestamp bucket с known+NULL ambiguity/no older-backoff, historical event-category numerator и полный category denominator вне C, observed-prefix ages/history flags, source-window coverage и missing flags. NULL/bool/integer equality точная, floats absolute/relative tolerance1e-12.18×sample_pairs — число core comparisons; metadata/support checks считаются отдельно. Sampled proof не объявляется exhaustive numeric F acceptance, malformed unsampled values могут остаться незамеченными.

## Resource и failure contract

Tiny scope:≤300s wall и process CPU,2DuckDB threads, process peakRSS≤512MiB,0fits. `--seconds` может только уменьшить cap. Timer interrupt прерывает SQL, guards проверяют время/RSS между этапами, hashing chunks и sampled source reads. Это cooperative process gate, не OS hard memory limit: allocation/fetch или отдельная операция может пересечь предел до следующего guard. PeakRSS — lifetime процесса, не incremental delta. Реальная collection throughput/память не измерены;128MB setting не доказательство peakRSS128MB.

Unsupported input, deadline/RSS, engine-open failure, schema/lineage/semantic mismatch завершают scope как failed. Partial completed stages/resources сохраняются в исключении/CLI stdout; optional evidence file только по явному запросу. Ошибка не создаёт acceptance, не продолжает producer и не запускает repair/retry автоматически.

## Synthetic evidence и upstream boundary

Meaningful fixtures покрывают fresh-resealed wrong F value, category denominator вне C, altered candidate rank, потерянный cold Y вне C/zero-purchase Q, duplicate F, missing flag/type, mixed-NULL latest bucket, category move, lower-bound expiry, full-prefix recency, peers/future suffix, empty C, exclusive evidence, path escape, runtime version и early resource/open failures. Fresh root with spaces проверяет input relocation, не clean-environment reinstall или реальный source regeneration. Mandatory checks используют exceptions, не assert.

Обнаруженная граница immutable017 сохранена regression: при полностью пустом source producer создаёт typed children, затем aggregate_collection падает `Missing or duplicate daily report coverage`; failed state/report не получают verified evidence018. Положительный complete-all-empty producer case не подделывается. Это отдельная future bugtask для empty daily_outcomes; текущие nonempty accepted train/selection не меняются. Zero-Y и empty-C queries при непустом source проверены отдельно и сохраняются.

До реального запуска обязательны independent code/fault review018, согласованный source/resource budget и external expectations. Перенос legacy temporary oracles объясняет provenance дизайна, но CLI не импортирует их и не требует machine-local dependencies. Future acceptance/regeneration mode, exhaustive numeric F и009/extensions требуют отдельного reviewed scope; текущая итерация их не заявляет.

## Audit первоначальной synthetic проверки

15Oct2026: только `test_verify_development.py`,23scoped synthetic tests PASS10,480s, exit0. Полная измеренная invocation10,517s wall/11,557s processCPU/152338432bytes process peakRSS;0fits. Полный repository suite не запускался. Эти числа включают создание tiny017 fixtures и fault injection, не являются benchmark реальных коллекций. Code ещё требует независимого review; реальное исполнение/acceptance не запускались.

## Поправка resource seal перед freeze

Coordinator обнаружил, что первоначальная версия9310433… возвращала verified до connection cleanup/final resource summary.23PASS не закрывали эту границу. Независимые synthetic faults воспроизвели false verified при fake close wall+700/CPU+700/RSS>512MiB и потерю нормального failed evidence при close/counter errors. Реального sleep или превышения RSS не было.

Исправление: success promotion выполняется только после timer cancellation, connection close, post-cleanup budget check, resource summary и заключительного budget check. Cleanup/summary error сохраняет failed partial evidence; недоступные counters обозначаются null/partial_unavailable, не нулём. Пять новых fault subcases проходят вместе с прежними semantic/lineage checks. Fixture connections явно ограничены2threads. Initial23-results выше сохраняются как audit, не acceptance revised code.

Final revised synthetic verification15Oct2026:25scoped tests PASS11,813s, exit0; measured invocation11,851s wall/13,015s processCPU/151306240bytes peakRSS,0fits. Это версия после resource-seal исправления; первоначальные23PASS не используются как доказательство revised code. Independent review и разрешение real source/resource execution всё ещё нужны.

## Поправка lineage после независимого review

Независимый C11 review версии9d0e30c… нашёл отдельный P1: свежо resealed approval и F inputs без actual Q/C pins всё ещё получали verified. P2: три несогласованных upstream report IDs также получали verified. Числовые source relations оставались правильными; это дефекты mechanical provenance, не доказанная порча принятых реальных данных. Первоначальные25PASS и успешный resource-seal audit не закрывали эти проверки. Исходный independent review сохраняется без переписывания.

Исправление ограничено exact14 derivation и report-ID binding выше. Public verify seam сначала получил failing freshly resealed synthetic regressions: четыре targeted tests, девять ожидаемых failures; отдельный source-omission case уже отклонялся прежним child-source guard. После исправления четыре targeted tests проходят. Окончательные scoped результаты и новые SHA публикуются в implementation handoff; acceptance этой версии требует targeted C11 re-review. Реальные source scans, regeneration и acceptance writes по-прежнему не выполнялись и не разрешены.

Revised lineage-fix verification15Oct2026:29scoped synthetic tests PASS14,522s, exit0; measured invocation14,613s wall/16,041s processCPU/149159936bytes peakRSS,0fits. Включены прежние cleanup wall/CPU/RSS overrun, close-error и unavailable-summary regressions. Independent code acceptance этой версии ещё не выдана; source execution остаётся закрытым.


## Принятый статус первой итерации — 15 октября 2026

Targeted independent review принял exact final code60519794…10ee0 и29-test synthetic suite. Собственный независимый harness:18cases, healthy verified и17faults failed;5.001701s wall/5.496802s actual process CPU/141770752bytes peakRSS,0fits. Исходные [P1/P2 findings](../backlog-reviews/tlab018-independent-review.md) и прежние false-pass evidence сохранены. [Окончательная приёмка](../backlog-reviews/tlab018-independent-rereview.md) закрывает missing/extra/wrong mandatory pins, child report IDs и cleanup regressions.

Это **code acceptance существующего sealed workflow**, а не завершённое воспроизведение с чистого clone. Real collection execution под отдельным ресурсным планом, первичная независимая source verification до external seal, regeneration и acceptance-writing ещё не реализованы и не приняты. Числовой F oracle остаётся sampled. Historical review-pending statements выше относятся к указанным прежним версиям.
