# Сдача task1: пять проверяемых deliverables, без нового research scope

15 октября2026. Read-only сверка [task1](../task1-requirements.md), README, progress report, accepted019/016/P0A evidence и текущих public heldout boundaries. Новых tests/данных/models/scores/heldout jobs/fits/Git/code changes нет; actual execution подтверждается опубликованными независимыми приёмками, здесь не повторялось. Observed README SHA `920f50a02810fb9cb122e513fa1bb0b0e4e0a936d9cfbd83229aa37bc5809755`, report `131c9c2a07ac6575455d9b475134c6bf15a6519c4eaf96d41131c9a383f4907f`.

**Главный вывод:** manual control и bounded automation comparison уже имеют реальный development результат. Их не надо заново доказывать новыми fits, datasets или search. Остались согласованная подача, наглядный generation example, явная граница воспроизводимости и честный heldout status. Само слово «не завершено» сейчас слишком широко.

## 1. Один согласованный читаемый итог

**Уже доказано:** accepted019 — bounded tuned B,26k train Q,depth6/L2=30,300trained/scored, NDCG20≈0.458611/Recall20≈0.585127. Accepted016 — четыре original B+3 fits, один zero-fit observer; W=R2/L05,0.464703/0.591977. ΔNDCG≈0.006092, descriptive postselection user-bootstrap interval[-0.003207,0.021294] включает0. Это observed development gain, не significant/generalization или rule-guided superiority.

**Необходимый остаток:** README и [progress report](../progress-report.md) должны одинаково разделять completed development, CLOSED heldout и отсутствующий full fresh bootstrap. Сейчас README top корректен, но последние абзацы всё ещё утверждают «четыре сравнения и quality result016 ещё не выполнены» и незавершённость всего automation comparison. Исправление только wording; historical audit notes можно сохранить с датой и ссылкой на новый итог. Новый pipeline run для этого не нужен.

## 2. Пользовательский пример именно автоматизации

**Уже доказано:** accepted `feature_programs.py` реально создаёт definitions из human-bounded schema/templates, проверяет type/aliases/closure; selected additions имеют tiny literal/list proof. Текущий публичный P0A пример проверяет ranking arithmetic, **а не generation**.

**Минимальный пример:** короткий existing API walkthrough `generate_pool(contract,base)`→L02/L06 programs/physical_delta→`allocate_slots`→`registry_for_slot(...,'I2')`. Показать два outputs: L02 —3count24h cores; L06 —2cores+automatic BOOLEAN missing=3physical columns; model width44=B41+3, nativefits0/execution_approved=false. Human bindings/windows показать рядом; восемь ready feature JSON lists не хранятся. Связать generated names с tiny expected counts и numeric selected12 source proof. Existing `tests.test_feature_programs` — доступный source-free calculation check, без нового demo module, SQL DSL или web interface. Definition-only snippet уже подготовлен в red-team note; здесь не запускался.

## 3. Короткая таблица эксперимента и достаточная traceability

**Уже доказано:** report содержит B/I1/I2/R1/R2, actual common learner/population/weights/prefix, fullY и73positive queries; I2 не проходит Recall guard. Source016 independently checked73,610,484 new values и old45 preservation; это не новый exhaustive source proof прежних ручных18формул. Models/score order/metrics/selector independently replayed. Shared source+fits+observer/admission upper1704.75CPU seconds раскрыт, original source failure сохранён.

**Остаток для сдачи:** одна compact result/evidence table со ссылками на [019](tlab019-strong-output-verification.md), [016 source](tlab016-recovered-source-verification.md), [016 models](tlab016-feature-program-model-verification.md). Четыре016 looks не стирают предыдущие007/008/009 и019 feedback; это уже верно объяснено report. Negative009 сохраняется краткой строкой. Не заставлять преподавателя читать58studies/все recovery logs; не включать их в основной narrative. Никаких дополнительных bootstrap/seeds/importance plots для этой таблицы не требуется.

## 4. Исполнимый reproduction prefix и честный handoff

**Уже исполнено:** [P0A](tlab018-p0a-independent-rereview-v3.md) принят; relocated CLI на12synthetic rows работал без data/artifacts/private approvals, exit0,0fits/native predictions. [Документация](../experiments/fresh-clone-reproduction.md) даёт actual command, exact integer ties, fullY/emptyC/zeroY, strict package/access limits.

**Не доказано:** чистая environment reinstall, replay реального private package этим CLI, fresh Q/Y/C/F bootstrap и retraining новой identity. Synthetic package не заменяет их. Existing workflow требует внешних issuer decisions, которых в clone нет.

**Минимальный deliverable:** README даёт locked setup, две реально существующие source-free демонстрации generation/metrics и явно подписанный маршрут real-study reproduction: какие source/package inputs нужны, что доступно из Git, где возникает external-review handoff и кто/по какому evidence создаёт свежие decisions. Если полного runnable source→train маршрута нет, прямо назвать это remaining reproducibility limitation. Для более сильного claim нужен один практически проверенный real-study reproduction path, но не универсальный bootstrap framework для всех datasets/OS. Existing018 phase2 — место этого пробела; не плодить новые задачи. Авторизованный supplied train/selection package может сузить numerical-replay gap без refit, но сейчас его фактическая delivery/replay не заявляется и доступа/бюджета записка не выдаёт.

## 5. Однозначный heldout outcome/status

**Пока code/design:** reporting-only25/frozen26–31 contract, source-only и prediction cores прошли scoped review; это не actual new-date source/prediction/target acceptance. Heldout CLOSED, результатов нет.

**Deliverable — одно из двух честных состояний:** после отдельно accepted execution добавить единственную frozen B против R2 таблицу с support/uncertainty/clocks; либо оставить явно «development-only study, reserved evaluation not performed». Во втором случае нельзя заявлять prospective confirmation/generalization. Task1 paraphrase требует experimental automation, но не буквально этот календарь; completed development сравнение уже является экспериментом. Это не гарантия оценки задания и не отмена принятого015 protocol: если heldout исполняется, все семь prediction seals до Y, no adaptation/refit и positive simulated compute gap обязательны. Процесс нельзя сокращать обходом seal или переименованием development.

**Что можно убрать из critical path:** новый dataset/November reservation, learned search/embeddings, speed/human-hours study, дополнительные learner configs и повторение accepted fits. PDF не обязателен, если выбран допустимый readable repository report; отдельная большая платформа для публикации не нужна. Сильный честный результат здесь — ограниченная автоматизация, independently correct calculation, завершённое matched development сравнение с uncertain gain и прозрачная граница replay/heldout. Следующие работы должны улучшать именно эти пять deliverables, а не число исследований или процедур.


## Publication scope appendix — 15 October 2026

Original SHA256 36e5686539a826bd593e1782da6b0617538ea5e3b65c429975d69481d8e1f5a7. The historical README wording discrepancy is corrected in this local publication. Source/metric/prediction code acceptance remains distinct from actual reserved-period execution, which has not occurred. Local accepted development evidence is versioned; external upload remains pending direct human destination consent. No new task, fit, data download, resource allowance or target-opening grant follows from this research note.
