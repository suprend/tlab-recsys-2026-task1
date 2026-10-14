# TLAB-006: независимое verification review evaluator

15 октября 2026. **Verdict: accept. Material findings: 0.** Проверены фактические [ranking_metrics.py](../../scripts/ranking_metrics.py) и [test_ranking_metrics.py](../../tests/test_ranking_metrics.py) относительно [TLAB-006](../backlog.md), [evaluation proposal](../target-research/05-evaluation.md) и [review 05–08](../target-research/review-05-08.md). Implementation report использован как контекст, не как доказательство выполнения.

## Scope и фактическая проверка

Оба файла на момент review — новые untracked additions; обычный `git diff -- scripts/ranking_metrics.py tests/test_ranking_metrics.py` пуст именно поэтому. Проверен полный фактический текст additions и статус этих двух путей. Другие WIP-файлы, окружение, данные, Git и implementation не изменялись. Новые dependencies и обучение не запускались.

Независимо выполнена только разрешённая команда из корня репозитория:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_ranking_metrics.py -v
```

Фактический результат: **13 tests, 0.002 s, OK, exit 0**. Набор TLAB-002 и полный test discovery не запускались. Принятие ниже опирается также на чтение формул и hand-golden assertions; passing tests сами по себе не доказывают правильность протокола данных.

## Соответствие контракту

- **Полный Y и короткий shortlist.** `score_query` делит Recall и AP на весь distinct target count; IDCG использует `min(K,|Y|)`, независимо от наличия товаров в candidates/catalog proxy. DCG строится только по фактически возвращённым позициям. Missing positives не вставляются с −∞. Golden query с одним найденным первым из трёх targets при K=20 даёт Recall=1/3, NDCG=0.46927872602275644 и AP=1/3. Пустой C при непустом Y даёт настоящий miss.
- **Empty mature и censored.** Mature query требует full target iterable, включая пустое множество; censored допускает только `targets=None`. `QueryScore` сохраняет mature flag и различает target_count=0/None. Evaluation выводит отдельные counters, censored не попадают в знаменатели. При отсутствии mature denominator результат missing, а не искусственный ноль.
- **Четыре estimands.** Conditional query macro усредняет nonempty mature queries; all-query zero добавляет нули empty mature. Conditional user macro усредняет пользовательские средние по positive queries только для пользователей с такими queries; all-user macro zero включает всех mature users и их empty queries. `_estimate` различает query count и user count. Hand fixture с тремя успешными queries A и одним неуспешным B правильно даёт 3/4 против 1/2. Отдельный fixture с empty-only пользователем различает all-query и all-user denominators. Равенство all-query=p×conditional проверено только для одинакового query weighting.
- **Paired bootstrap.** Проверяются одинаковые query IDs, users, maturity и full labels; порядок right не имеет значения. Одна multiplicity-map каждого draw применяется к обоим моделям. Query macro пересчитывается через взвешенные суммы/counts, user macro — через пользовательские средние. Mature empty-only users остаются в cluster population. Полностью censored users исключены. Identical-model fixture даёт нулевую разность всех draws; opposite-model fixture проверяет pairing при неравном числе queries.
- **Undefined draws и воспроизводимость.** Conditional draw без positives остаётся `None`, не пересэмплируется. Число undefined раскрывается, при отсутствии defined draws интервала нет. Seed и порядок left clusters задают воспроизводимые draws; это явно документировано. Ограничение replicates≤1000 соответствует бюджету задачи.
- **Входы/K/ties.** Ranked items требуют ordered sequence; duplicates отвергаются, включая повторы после K. Duplicate targets схлопываются согласно set-target. K должен быть положительным integer, bool запрещён. Duplicate query IDs и mismatched pair populations/labels отвергаются. Evaluator не принимает scores: caller supplies окончательный deterministic order, поэтому порядок ties принадлежит upstream policy. Тест явно показывает разные результаты двух допустимых порядков без скрытого пересортирования.

Тесты содержат независимые численные goldens, пустые/короткие списки, cutoff, несколько hits, AP=RR для single target, unequal query counts, обе zero conventions, empty/censored populations и pairing. Они проверяют наблюдаемые результаты, а не внутреннее устройство очередей/агрегаторов. Для TLAB-006 это meaningful coverage; обязательного исправления тестов не найдено.

## Пределы принятия

Модуль доверяет caller declarations о полноте Y, зрелости, заранее разрешённом candidate universe и deterministic tie policy. Их истинность должен проверять upstream temporal/retrieval pipeline; здесь нет raw-event replay, model quality, coverage report или resource benchmark.

`interval_95` — percentile interval по defined draws с linear interpolation. Он честно документирован, а effective draw count восстанавливается из replicates−undefined_draws. Однако API разрешает и очень малое replicates, и очень мало пользователей/defined draws. Например, replicates=1 формально выдаст вырожденный percentile interval. Это **не material violation TLAB-006**, поскольку минимальная статистическая мощность не задана, missing policy и counts доступны. Downstream report/promotion gate обязан показывать user_count, requested/defined draws и ограничения, а не трактовать вырожденный интервал как надёжное доказательство улучшения. User clustering также не покрывает общий временной шок и selection bias после validation search.

Приёмка относится к evaluator как независимому вычислительному компоненту. Она не утверждает готовность full ranking baseline или доказанность полезности какой-либо модели.
