# Narrow source/traceability audit:047 и evidence map

15 октября2026. Read-only literature/document audit после selector wording re-review. Исходные047/evidence map сохранены. Live019 scores,016 outcomes, source/model artifacts и WIP не читались; jobs/tests/fits/LLM calls нет. Это самостоятельная проверка источников собственного synthesis, не независимая приёмка результатов pipeline.

## Проверенные empirical claims047

[CAAFE](https://papers.neurips.cc/paper_files/paper/2023/file/8c2df4c35cdbee764ebb9e9d0acd5197-Paper-Conference.pdf): abstract подтверждает11/14 иmean AUC.798→.822;§4 — пять random50/50train/test repetitions; appendixF — average4:43min, dominated generation. Эти показатели не названы actualCPU или нашим ranking contrast.

[FeatLLMv2](https://arxiv.org/html/2404.09491v2):§4.1 подтверждает13classification datasets и перечисленныеbaselines, Table1/3/appendix — разныеshot/high-dimensional scopes. Table5 действительно сообщает860.094s/0.006ms и30APIqueries дляAdult16shots, сA100/API-state qualification. Это reported comparison, не доказанный общий call ledger всехensemble configurations. Универсальнаяsplitfraction ичислоreplications не были выдуманы. K-fold epoch selection/gridsearch присутствуют§4.1; эти скрытые относительноheadline costs не получают0-fit трактовку.

[LLM-FEv2](https://arxiv.org/html/2503.14434v2):§4/5 подтверждают19classification/10regression,80/20split иfive-split reports; regression comparison excludes unavailableLLM baselines.20samples/3programs/local30s2GB не преобразованы в whole-search bound. Publication version ограничена именноv2.

[ExploreKit](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf):§V подтверждает25datasets, stratified66%train/threefold, defaultsC4.5/SVM/RF,20cores64GB иthree-day cap. Formula reduction использует1−AUC;20%headline не являетсяaccuracy gain. [OpenFE](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf):§5/Table3 — one shared split иten repetitions, неten independent split draws; AppendixB Microsoft=Regression/RMSE;§6 прямо сообщаетtime-series limitation. Hardware иruntime table sources соответствуют047. Kaggle rank fractions не представлены как effect sizes.

**Итог facts:** новой содержательной source correction047 не требуется. Ограничение «никакой complete temporal Q/C/fullY benchmark здесь не воспроизведён» является сопоставлением требований, а не дополнительным empirical claim авторов.

## Traceability evidence map

Ссылки на rounds024/025/042 и остальные ранее опубликованные документы существуют. На момент этого чтения `round-046.md`, `round-047.md` и `rounds043-046-source-audit.md` ещё отсутствуют в published research directory. Map явно называет их подготовленными, поэтому это publication dependency, не ложное сообщение об уже опубликованной приёмке. Coordinator должен разместить notes с совпадающими именами либо изменить links при публикации карты. Данных/approvals для этого не требуется.

Три пояснения для финального отчёта:

1. NoREC — methodological inspiration независимого сравнения путей; map не означает, что SQLancer/NoREC реализованы в017/018. Actual proof scope задают repository audits: QYC exhaustive, старый B numeric sampled, selected12 source gate отдельно.
2. «019 и016 одинаковые settings» означает **frozen winning019 control и каждый016arm**, а не четыре разные конфигурации019grid. Source-local models будущихdatasets также не являются тем же trained control.
3. Pending selector design ambiguity в старой карте теперь закрыта отдельно принятой config/doc policy; executable selector и actual fit/output acceptance остаются будущими. Doc correctedSHA `1f7ac673560f4191152b1647210fd09e40997e00099a97e1624dec69418ab843`, JSON unchanged `3bb1e4f63f32160135daaee95d257f571f394af25f4b74378ba2785be12b5ac0`. Globalmaximum>B+ε исключаетB; выбранныйWможет иметьpositivegain≤ε.

Future046preflight проверяет declared typed mechanics, а не actual real-source approval илиquality. Existing018/sample boundary, отрицательный009 и отсутствиеtask-completeclaim сохранены. Никакой новый look/fit/operator илиbudget из уточнений не следует.
