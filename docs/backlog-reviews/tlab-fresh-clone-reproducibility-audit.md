# Fresh-clone reproducibility audit — минимальные gates018 phase2/README

15 октября2026. Read-only audit требований task1; commands не исполнялись, данные/модели/ignored approvals не открывались. Код019/016 в разработке не рецензировался. Ссылка на strong.prepare_plan/sealed008/009 ниже относится к поставленному Root вопросу и опубликованному дизайну, а не новой независимой code acceptance019. Инцидент scope: широкий текстовый поиск исторических metrics случайно вернул две строки strong_baseline.py; дальнейшего чтения этого WIP не было, выводы на этих строках не основаны.

**Вывод:** текущий репозиторий честно описывает принятые локальные artifacts и запускаемые механизмы, но ещё не предоставляет замкнутый пользовательский workflow «clone → новые Q/Y/C/F → независимо принятый control →016» без контекста чата. Это отдельная незавершённая часть воспроизводимости из [проверенных требований](../task1-requirements.md), не опровержение уже проведённых source/model audits. [README](../../README.md) прямо признаёт отсутствие ignored artifacts и отсутствие fresh approvals/regeneration018.

## Развести два режима

**Exact artifact replay** получает отдельно конкретный неизменный bundle, approvals, модели, score arrays и reports. Он проверяет прежние hashes/identity, source/model proofs и пересчёт опубликованных агрегатов. Clone один этих inputs не содержит. Контрольные значения старого опыта здесь уместны.

**Independent rerun** получает исходный архив из опубликованного источника, создаёт новый DB/collection/model identity и новые независимые decisions. Даже одинаковый логический эксперимент может получить другие physical bytes/paths/reports/platform identity. Совпадение старых metrics не должно быть условием его корректности. Старые approvals не переписываются и не копируются с новыми hashes. Rerun требует нового ограниченного execution разрешения; свежий clone не предоставляет бесплатные fits/retries.

## Фактические seams и gaps

| Этап | Уже опубликовано/реализовано | Что нужно для clean workflow |
|---|---|---|
| Source/EDA | README: `uv sync --locked`, `scripts/eda.py`; source location/hash в data.md | Явно отделить hash архива от физического DB hash и зафиксировать ingestion/schema/coverage evidence; differing DB bytes не объявлять автоматически corruption или старой identity |
|017 plan/producer | `prepare_execution_plan` возвращает proposal; CLI принимает phase/db/producer-approval/shard-acceptance-dir | Публичный plan-only export без исполнения и документированный reviewer input/output, без ad-hoc Python snippets из чата |
| Q/Y/C |017 останавливается на `waiting_for_shard_review` | Переносимый pre-acceptance shard source oracle и reviewer decision; он не должен требовать ещё отсутствующий final collection approval |
| F/collection | После shard approval017 производит F;008 механически проверяет full lineage | Независимый source/formula evidence с честным sampled/exhaustive scope и новый collection decision |
|018 | `--project-root`, `--expectations`, optional `--evidence-out`; только existing reviewed collection | Phase2 ещё отсутствует: нет первичной выдачи approvals, regeneration, `--write-acceptance`; нельзя советовать пользователю поставить approved=true самостоятельно |
|008 control | CLI требует train/selection acceptances и fit-approval, atomic fit claims | Документированный plan-only handoff, точный ограниченный fit decision и independent model/output acceptance; failed consumed claim не удалять для retry |
|009→019 | Принятый009 helper закрепляет конкретный008 control;019 дизайн зависит от sealed evidence | Явно выбрать replay current dependency chain либо отдельно принять rerun-compatible incumbent contract; не имитировать missing rejected009 evidence |
|016 | Published generator/tiny acceptance, реальные дополнительные коллекции и quality comparison ещё не завершены | После runtime acceptance опубликовать точный путь generate/freeze → selected-union source proof → preservedB → four authorized attempts → final report |

Прямое подтверждение replay-specific009: [metadata_ablation.verify_control](../../scripts/metadata_ablation.py) заново строит008 plan, требует совпадающий run ID, ровно две50-tree модели, fixed artifact scope и точные исторические conditional NDCG/Recall. Environment validator сверяет loaded/installed версии с lock. Эти guard полезны для неизменного принятого опыта; их нельзя молча ослабить или назвать общим acceptance любого нового корректного rerun. [008 runner](../../scripts/train_baselines.py) и [017 runner](../../scripts/development_collection.py) предоставляют planning functions, однако их CLI ориентированы на execution с уже подготовленными approvals.

## Минимальный decision workflow phase2

Предложение, не реализованный интерфейс: producer-plan proposal → независимый code/source/resource decision → Q/Y/C production → shard oracle evidence → отдельный reviewed shard decision → F production → collection oracle evidence → collection decision → fit-plan/limited fit decision → models/output proof → model acceptance. Каждый переход закрепляет exact policy/version, scope, filenames/hashes, reviewer decision reference, resource outcome и predecessor evidence. Необходимые pin sets выводит проверенный verifier, а не сам утверждаемый JSON.

Verifier и writer не должны быть одним неявным «hash and approve» действием. Возможный writer получает отдельно reviewed decision, проверяет evidence/pins повторно, пишет exclusive immutable file и отказывает на failed/partial/unsupported evidence. Reviewer — явно названный внешний по отношению к producer процесс проверки; это может быть самостоятельный воспроизводимый user review по опубликованному checklist. Пароль, подпись или новая инфраструктура для этой минимальной границы не предполагаются. Human decision без source oracle остаётся недостаточным свидетельством formulas.

Scope018 phase2 нужно определить заранее: текущий018 даёт exhaustive Q/Y/C и F rowset, но numeric manual18 только sampled;009 addon и016 extensions unsupported. Новый workflow не может переименовать этот результат в exhaustive source proof всего B41. Для016 отдельно требуются выбранные12 новых numeric columns exhaustively и every-row preservation старого B, с прежним sampled source boundary B сохранённым.

## Что должен показывать итоговый README

Два явно названных режима и список externally supplied inputs; stage DAG с одной canonical командой на опубликованный этап, expected stop/status и output location; схема того, кто и на основании какого evidence создаёт каждый fresh approval; supported OS/resource backend; immutable identity/claims/resume rules; полный cumulative cost включая failures/oracles; current unsupported gates без фиктивных placeholders, выдаваемых за готовые commands.

Отдельно сохранить temporal lock: train/selection development и известная whole-month EDA, две временные шкалы, prospective heldout calendar, label-blind prediction path и prediction seals до query-level Y opening. Fresh rerun уже посмотренных selection outcomes не создаёт новое untouched holdout. Отсутствие quality gain016 допускает честный отрицательный отчёт, но не автоматически закрывает формулировку о превосходстве сильного контроля. Ни portability, ни полный task1 result этим аудитом не утверждаются; новый framework, fits или execution allowance не предлагаются.
