# F001: независимая проверка первоисточников

Проверено 2026-10-15. Только статьи и авторский репозиторий; без данных проекта, запусков моделей, БД и прикладных API. Другие текущие brainstorm-отчёты не читались. Ниже «подтверждено» означает, что утверждение содержится в первоисточнике, а не что результат воспроизведён.

## TSRec

**Подтверждено.** §3.1.1 задаёт два контекста одного повторяемого item: события между прошлым вхождением и целевым повтором и события перед прошлым вхождением. SRAM сопоставляет их представления; ITRM использует интервалы повторений того же item у других пользователей (§3.3). Это точнее, чем общее «сравнение текущей последовательности с прошлой»; границы контекстов зависят от конкретного кандидата. Задача — следующий item, новый или повторный (§2). Разбиение по времени 70/10/20; HR/NDCG и 100 случайных negatives на test (§4.1). [Статья](https://arxiv.org/html/2506.08531v1).

**Граница переноса.** Ручные сходства контекстов, агрегированные интервальные priors или признаки для F001 являются адаптацией, не реализацией TSRec и не доказанным улучшением её метрики.

**Код не проверен.** Статья указывает [anonymous repository](https://anonymous.4open.science/r/TSRec-2306/), но доступный web-reader вернул пустое содержимое. Это ограничение проверки, не доказательство отсутствия кода.

## Timing-Aware Repurchase Prediction

**Подтверждено.** §2: десятки миллионов customer–item пар из proprietary grocery-платформы; событие наблюдается в окне 30 дней, иначе right-censoring. Обучение на одном snapshot; оценка на той же дате по отложенным клиентам. Общие 84 признака включают order/channel/payment, recency, персональные и population IPI, availability, tenure, basket composition и presence в предыдущем заказе. Оценочные горизонты — 7/14/28 дней. §4 различает AFT и discrete-time hazard; последний расширяет пару в интервалы [0,7), [7,14), [14,30), добавляет interval-relative признаки и преобразует hazards в cumulative probability. [Статья](https://arxiv.org/html/2608.28393v1).

**Граница переноса.** Censoring и conditional hazard подтверждены; перенос на более бедные click-stream признаки, другой outcome или временную валидацию остаётся гипотезой. Одна дата и customer-heldout не проверяют будущий temporal drift. AFT даёт одинаковый порядок на разных горизонтах при фиксированных distribution parameters; DT может менять порядок (§4). Не следует смешивать эти свойства.

## HiFIRec

**Подтверждено.** Метод различает высокочастотные слабые поведенческие сигналы и намерение: user/item/behavior graph, слоистая агрегация, межслойное слияние, behavior weighting. Non-sampling означает использование всех unlabeled пар как negatives, с различными weights по поведению; §3.5.2 объединяет behavior-specific losses через multi-task objective. [Статья, §§2.2–3.5](https://arxiv.org/html/2509.25755v1).

**Граница переноса.** Набор инженерных count/ratio/recency признаков или линейные penalties за views — адаптация мотивации, не HiFIRec и не подтверждённый способ noise correction.

**Качество численных утверждений.** В §4.5 текст называет улучшениями Beibei NDCG 0.0885→0.0643 и HR 0.2947→0.2751, хотя оба значения уменьшаются. Методологическое описание подтверждается; эти количественные аргументы требуют сверки таблицы/кода.

## SCRM

**Подтверждено.** Оба графа прямо названы undirected (§3.2). Substitute edges: соседние click→click или click→purchase. Complement edges: соседние purchase→purchase или purchase→click; затем добавляются второпорядковые complements через substitute-bridge. Это эвристические правила, и авторы прямо признают их шумность; модель содержит denoising layer (§4.1.1). [Статья](https://arxiv.org/html/2312.14957v2).

**Граница переноса.** Правила используют хронологию для построения, но итоговые связи симметричны. Направленные переходные признаки, вероятности конверсии, causal substitutes/complements либо top-K relation priors для F001 — отдельная адаптация; статья не подтверждает их готовую семантику или выигрыш.

## FAM / Feature-aware Temporal Modulation

**Подтверждено.** §5, Eq.2: временной embedding ψ(t) задаёт для каждой feature scale γ, bias β и nonlinear coefficient λ: γ·Yeo–Johnson(x;λ)+β. Модуляция допускается на input, intermediate representations и logits. Это не просто календарный признак или нормализация по temporal bins. [Статья, p.6](https://proceedings.neurips.cc/paper_files/paper/2025/file/ddc20f403d0d296c87940393838d5971-Paper-Conference.pdf#page=6).

**Бюджет подтверждён с уточнением.** Авторский README показывает `--n_trials 100` и `--seed_num 15` для deep/classical commands. Appendix B уточняет: 100 Optuna trials для большинства методов, 25 для FT-Transformer и TabR, затем 15 seeds. [Авторский README](https://github.com/LAMDA-Tabular/Tabular-Temporal-Modulation#deep-method), [статья, Appendix B](https://proceedings.neurips.cc/paper_files/paper/2025/file/ddc20f403d0d296c87940393838d5971-Paper-Conference.pdf#page=13).

**Граница переноса.** Простые time-conditioned transforms являются адаптацией; FAM не доказывает выигрыш именно таких ручных признаков в F001. 100/15 — опубликованный экспериментальный protocol, не обязательный бюджет каждого probe.
