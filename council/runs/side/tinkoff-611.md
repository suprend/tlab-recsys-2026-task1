# H8: якорь 611 Tinkoff как оценочный — prereg

Записано 22.10.2026, до любого запуска `council/side/tinkoff_anchor.py`. План — гипотеза 9 и E4 в
`council/runs/night/2026-10-22-plan.md`; открытый вопрос раздела «Перенос» отчёта; post-hoc раздел
`docs/xfer-tinkoff.md` («Post-hoc: на ком прирост»).

## Гипотеза

На dev (val-641) прирост колонок агента D = BA − B около нуля у пользователей теста Kaggle и точечно выше у остальных;
разность групп не проверялась. На Kaggle BA ниже B на обоих зёрнах. Гипотеза: **прирост BA над B сосредоточен вне
пользователей теста Kaggle, и это воспроизводится на другом, не использованном для оценки якоре**:
D_rest − D_kaggle > 0.

Предусловие плана: запуск только если проверка C0(d) подтвердила T_fit (план, строка 05:00–07:00). Модуль его не
проверяет; это решает координатор.

## Вход

- Якоря Tinkoff (`scripts/xfer_tinkoff.anchors()`): обучение — train-якоря серии dev до 611: 461, 491, 521, 551, 581;
  оценка — train-611 (роль `train`, метки открыты и раньше использовались только для обучения dev).
- Руки B и BA (те же, что в xfer: `scripts.xfer_model.training_block`, `matrices`, `make_pool`, `recipe_for`,
  `score_rows`, `open_labels`, `evaluate` — только импорт), зёрна 2026 и 2027, рецепт `xfer_common.RECIPE`
  (500 деревьев, глубина 8, lr 0.05). `xm.Context('tinkoff')` проверяет prereg, базу, набор агента и code identity.
- Группы: пользователи запросов 611, входящие в `test_users` из `artifacts/xfer/tinkoff/load/static.duckdb`
  (только id, открывается `read_only=True`), против остальных.
- Не читается: val-641, holdout-671, kaggle-701, их метки и сайдкары, `prereg`/`plan` совета, брокер.

## Выход

Только `artifacts/side/tinkoff-611/<рука><зерно>/{scores,metrics}.parquet, report.json` и
`council/runs/side/tinkoff-611.json`; журнал шага — `council/runs/side/queue.jsonl`. `xm.fit`/`fit_dir` не вызываются,
в `artifacts/xfer` ничего не пишется. Снимок листинга и mtime `artifacts/xfer` и `artifacts/task1` (каталоги `sealed`
— записью со своим mtime, без захода внутрь) снимается после взятия замка и сверяется до его снятия: шаг REES46, за
которым ждали, не даёт ложного отказа. Любое изменение — `status: refused`, код выхода 3. Готовый `<рука><зерно>`
переиспользуется только при том же дайджесте спецификации, коде `council/side` и code identity xfer.

## Правило решения

Для каждого зерна: D = BA − B по запросам 611 (NDCG@20 запроса, `xm.evaluate`); D_kaggle, D_rest — парный бутстрап
`xfer_common.bootstrap` (2000, `default_rng(2026)`); D_rest − D_kaggle — независимый ресэмплинг запросов в каждой
группе, 2000 выборок, линейные квантили 2.5/97.5.

- **воспроизводится**: CI(D_rest − D_kaggle) выше 0 на обоих зёрнах;
- **обратная**: CI ниже 0 на обоих зёрнах;
- **не различено**: иначе.

## Что считается результатом

Вердикт и таблица: по зерну и группе — число запросов, B, D с CI, D_rest − D_kaggle с CI; общий D. Результатом
считается любой из трёх вердиктов; «не различено» не заменяется описанием точечных оценок. Вывод о Kaggle
(почему BA < B) делается только при «воспроизводится» и только как согласие с post-hoc dev, не как доказательство.

## Тяжёлый шаг

`council.xfer.queue.heavy('side tinkoff-611', 'tinkoff')`: flock `/tmp/tlab-heavy.lock` и проверка чужих тяжёлых
процессов (REES46 fit/queue/memory/compute, `scripts/xfer_*`); `check()` перед каждой из 4 подгонок. Запись держателя
делает `lock_holder()` ненулевым, ПРОВЕРКА-HEAVY REES46 ждёт; её pgrep
`! pgrep -fl '[c]ouncil/xfer/run.py.*(queue|compute|fit-one)|[c]ouncil\.(fit|queue|memory)|[c]ouncil[./]side'` ловит путь скрипта, поэтому запуск — только скриптом `-I council/side/tinkoff_anchor.py`, не `-m`. Пробы xfer рядом не идут: у вида `side` нет пика в их
журналах, `light_gate` отказывает (безопасная сторона).

## Команды

```
cd ~/tlab-recsys-2026 && TASK1_PERIOD=2020 .venv/bin/python -I council/side/tinkoff_anchor.py --dry
cd ~/tlab-recsys-2026 && TASK1_PERIOD=2020 .venv/bin/python -I council/side/tinkoff_anchor.py > /tmp/tlab-side-tinkoff-611.log 2>&1
```

Оценка: 4 подгонки по 3–4 мин плюс скоринг 611 — 20–25 мин; пик ≈ 8.5–9 ГБ (подгонки пути xfer — 8.55 ГБ).
