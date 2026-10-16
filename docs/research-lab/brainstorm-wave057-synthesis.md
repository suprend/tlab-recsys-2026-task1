# Волна 057: альтернативные learners на B41

Root принял три уточнения существующего TLAB-014 после трёх новых независимых слепых FIRST и отдельного неавторского скептика. [Оригиналы, восемь замороженных source-context snapshots и решения](archives/wave057/publication.json) сохранены побайтно. Новых ID, задач, gates или grants нет; все предложенные эксперименты **UNRUN**.

**Общая коррекция.** Текущий prefix helper выбирает по NDCG; Recall отчётный и не входит в это правило. Исторический guard TLAB-016 не наследуется. Любой будущий Recall guard требует заранее объявить порог и этап решения; политика здесь не меняется.

**A — TabPFN.** Условное learner-family уточнение, не drop-in для полного B. Предлагаемый case-control контекст меняет complete-Q support и query-weighted меру обучения; полные C/fullY при оценке этого не исправляют. CPU guard 5000 допускает override, но не является измерением доступной локальной стоимости.

**B — TabICL.** Полные C внутри выбранных Q сохраняются, но label-conditioned набор Q и uniform row weights отличаются от полного query-weighted B. Matched CatBoost может отвечать только на этот ограниченный контраст. H100/offloading примеры не доказывают локальную CPU-доступность.

**C — TabM.** Support-preserving recipe концептуально чище, но неудача одного recipe не отвергает семейство. Стоимость preprocessing, полных fits, scoring, повторов и failures должна быть оплачена; ресурс сейчас не предоставлен.

Все три направления — альтернативные learners над B41, а не доказанная автоматизация event features. Reused validation с 73 positive Q остаётся exploratory; untouched outer и отдельного ресурса здесь нет. Независимое превосходство, CV, significance и экономия не заявляются; принятые TLAB-015/018 и их ограничения неизменны.

**История screen.** Первичный Root-record ошибочно назвал остановку pins mismatch: substring-проверка совпала с metadata key о нулевом числе сохранённых snapshots. SHA всегда совпадали, авторские файлы не менялись. [Первичный record](archives/wave057/tlab-root-wave057-critic-pins-mismatch-v1.json) и [исправление](archives/wave057/tlab-root-wave057-critic-screen-correction-v1.json) сохранены раздельно; corrected exact-key screen не обнаружил full external tool snapshots.

Native CatBoost helper/CLI end-to-end остаётся **UNRUN**. Прошли 12 FakeML/CODE CLI-тестов; они не подтверждают native integration. Отдельная Root-приёмка указана reference-only по path/SHA в [publication map](archives/wave057/publication.json). Helper-only вопрос 50 CPU / 65 wall и exact b760 push без ответа; новых разрешений нет. Текущие документы здесь не редактируются. Плановая 057 — 03:00 UTC 16 октября; ранний dispatch 02:53–02:54 после двух исполненных раундов сохранён. Следующая исходная сетка — **03:45 UTC / 06:45 МСК**, без reset deadline или бюджетов.
