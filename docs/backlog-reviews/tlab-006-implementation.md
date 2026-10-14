# TLAB-006 — implementation handoff

15 октября 2026. Реализован независимый stdlib evaluator; raw data, обучение, зависимости и чужие implementation-файлы не изменялись. Это проверка вычислительной семантики на synthetic fixtures, не измеренное качество модели.

## Actual files

- `scripts/ranking_metrics.py` — 253 строки. Публичные функции: `score_query`, `evaluate`, `paired_user_bootstrap`; вход `QueryRanking`, результаты — frozen dataclasses.
- `tests/test_ranking_metrics.py` — 191 строка, 13 meaningful unittest cases.

Проверено фактическое содержимое обоих файлов и diff новых файлов против пустого исходника. Whitespace проверен также для untracked files. Оба файла остаются untracked/unstaged; staged diff пуст. Stage/commit/push не выполнялись.

## Контракт

Вход — упорядоченная последовательность уникальных item IDs, уже детерминированная вызывающим кодом. Scores/tie sorting evaluator не придумывает. Дубли ranks отвергаются по всему списку, включая позиции за K. K — положительный integer; bool не принимается. Targets приводятся к distinct set.

Recall, AP и IDCG используют полный Y, включая cold/missing/outside-pool targets. Короткий список остаётся коротким, недостающие positives не вставляются. Помимо Recall/NDCG доступны AP со знаменателем полного Y и reciprocal rank.

Mature query обязан передать полный target set: `None` отвергается и не превращается в negative. Для censored query требуется `mature=False, targets=None`; partial labels отвергаются. Empty mature Y имеет неопределённые per-query metrics. Summary отдельно считает mature/censored/nonempty queries, positive/mature users и p(nonempty). Conditional macro-query/user-macro исключают пустые Y; all-query/all-user zero-convention включает их с нулём. Censored исключены из всех metric denominators.

Парный user-cluster bootstrap сравнивает left−right и требует одинаковых query IDs/users/maturity/full Y. Один multiplicity применяется к обеим моделям. Все зрелые пользователи входят в cluster population; conditional query-macro пересчитывает отношение weighted score sums к weighted query counts. User-macro сохраняет собственный estimand. Replicates ограничены 1…1000, seed — явный integer. Zero-positive draw остаётся `None`, не пересэмплируется; `undefined_draws` сообщает число таких случаев. 95% percentile CI с линейной интерполяцией использует defined draws; без них interval отсутствует. Порядок right queries не влияет на pairing, воспроизводимость требует одинакового порядка left clusters и seed.

## Actual verification

Команда: `.venv/bin/python -m unittest discover -s tests -p test_ranking_metrics.py -v`.

Последний запуск: **13 tests passed**, 0.002 s. Другие WIP test files не запускались. Golden values проверяют Recall=1/3 и NDCG=0.46927872602275644 при одном найденном первом товаре из трёх targets и K≥3; shortlist<K/C=empty, cold targets, empty Y/censoring, AP/RR, cutoff и caller order. Unequal user query counts дают query-macro 3/4 против user-macro 1/2; bootstrap поддерживает эти разные estimands, pairing, обе zero conventions, zero-positive draws и отсутствие знаменателя. Проверены mismatched labels/population, duplicates и budgets.

## Пределы

Независимое review остаётся gate координатора. Evaluator доверяет объявленной зрелости и полноте Y: проверка provenance/as-of/candidate availability принадлежит upstream protocol/retrieval. Catalog/candidate coverage slices не вычисляются без соответствующих входов. Bootstrap не покрывает общий временной шок; interval с пропущенными undefined draws требует чтения их счётчика. Реальных model scores/pilot results нет.
