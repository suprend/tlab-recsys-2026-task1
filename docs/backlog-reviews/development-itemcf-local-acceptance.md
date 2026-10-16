# Локально установленные development helper и ItemCF

Шесть новых файлов установлены побайтно и приняты Root. На установленных путях прошли **22 теста и 1280 сравнений вымышленных аудиторий**, без failures/errors, реального CatBoost fit и чтения датасета. Prototype, portable и installed прогоны повторяют те же случаи: это не 66 уникальных тестов и не 3840 независимых сравнений.

## Что готово

- [`fit_development`](../../scripts/development_training.py) требует train и validation, полностью обучает одну поддержанную CPU Logloss модель до заданного потолка, вызывает существующий полный prefix selector и сокращает отдельную копию. [Контракт](../experiments/development-training.md) явно ограничивает параметры и ответственность caller.
- [`project_itemcf`](../../scripts/itemcf_projection.py) вычисляет all-C mean/max/support/masks из переданных полных postings и latest21; исключает собственный голос по полным аудиториям, исключает candidate до cap20 и обеспечивает refill. [Контракт](../experiments/itemcf-projection.md) отделяет known-empty от неполного входа и локальные work limits от полной стоимости.
- Два независимых portable V1 code review и один узкий V2 recheck не нашли поддержанных замечаний в своём scope. V2 менял только ItemCF docstring и два документа; helper/tests сохранили bytes.

## Что ещё не доказано

Новый helper не проходил реального native fit, shrink/serialization или whole-pipeline integration. Старые команды не переведены на него автоматически: future non-frozen callers должны подключать его явно. Аудит entrypoints обнаружил, что historical strong019 действительно выбирал среди 50/150/300; называть его полностью лишённым выбора было бы неверно. Frozen 300-tree воспроизведение сохраняет исторический контракт.

ItemCF-ядро не извлекает исходные аудитории, не подтверждает strict-past полноту данных и не запускает cost/support pilot. Пилот существующего TLAB-012 остаётся optional deferred: нужны точные входы и отдельное принятое ограничение всех затрат. Фактической CV, нового качества, ускорения или доступного остатка общего CPU-бюджета эти проверки не устанавливают.

## Проверенные свидетельства

- [Root installed-path acceptance](evidence/development-itemcf-local/originals/tlab-root-installed-development-itemcf-acceptance-v1.json), [result](evidence/development-itemcf-local/originals/installed-result.json), [test log](evidence/development-itemcf-local/originals/installed-tests.txt).
- [Локальная квитанция шести файлов](evidence/development-itemcf-local/originals/tlab-local-development-itemcf-install-receipt-v1.json), [предыдущий portable прогон](evidence/development-itemcf-local/originals/tlab-root-portable-module-unit-acceptance-v1.json).
- [Коррекция приоритетов](evidence/development-itemcf-local/originals/tlab-root-training-fundamentals-process-correction-v1.md), [entrypoint audit](evidence/development-itemcf-local/originals/tlab-new-training-tree-selection-entrypoints-audit-v1.md) и [его scoped принятие](evidence/development-itemcf-local/originals/tlab-root-new-training-entrypoints-audit-acceptance-v1.json).
- [Manifest архива](evidence/development-itemcf-local/publication.json) связывает оригиналы и шесть установленных SHA без дублирования кода.

В проекте принято 14 из 19 задач. TLAB-014 остаётся active research; TLAB-010–013 — optional deferred. Принятые adaptive B1189/W403, final TLAB-015 и Mac/new-environment TLAB-018 сохраняют свой исходный scope. Новые helper/ItemCF файлы остаются UNTRACKED; точный коммит b7607b4 и Git-индекс не менялись. Вопрос разрешения отправки этого коммита ещё ожидает ответа после двух автоматических отказов; сетевых повторов нет. Подготовленный PR body остаётся в TMP и не является текущим описанием удалённого PR.
