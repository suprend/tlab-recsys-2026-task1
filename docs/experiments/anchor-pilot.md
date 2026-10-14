# Anchor/label feasibility: development pilot

15 октября 2026. TLAB-003. **Измеренный development pilot принят после независимого code/source review и отдельной сверки новых run provenance.** Это диагностика аудитории и labels, без кандидатов, ранжирования и обучения. Протокол остаётся provisional.

В 00:00 UTC 8, 9 и 10 октября создаём запрос для пользователя с любым прошлым событием. A использует eligibility `[t−7d,t)`, B — `[t−48h,t)`. Каждый день выбираем bottom-2000 по SHA-256 от фиксированной ASCII-строки `sample|2026|UTC-anchor|user_id` **до чтения будущих purchases**. Число eligible — точное, не число sampled. Target — distinct product IDs с purchase в `[t,t+24h)`. Все зрелые запросы без покупки сохранены.

Одинаковые seed/алгоритм не делают A/B одинаковыми выборками или одним paired estimand: populations отличаются. История7d для diagnostic bins имеет одинаковую семантику. Дневные выборки не объединяются в оценку «доля пользователей за месяц».

## Измеренный результат

| Показатель | A: активность7d | B: активность48h |
|---|---:|---:|
| Зрелые запросы | 6000 | 6000 |
| Запросы с хотя бы одной покупкой | 43 | 104 |
| Зрелые запросы без покупки | 5957 | 5896 |
| Distinct targets, сумма по запросам | 51 | 121 |
| Строки purchase внутри targets | 59 | 139 |
| Targets, отсутствовавшие в прошлом каталоге | 1 | 0 |
| Targets с прошлым событием этой пары | 28 | 73 |
| Targets с purchase ровно в секунду запроса | 0 | 0 |
| p(nonempty) на sampled queries | 0.717% | 1.733% |
| Полное wall time, включая fingerprint/export | 10.16s | 9.70s |
| Process peak RSS | 712.1MiB | 710.5MiB |

Source coverage — `[2019-10-01,2019-11-01)` UTC; все 12 000 sampled query-days имеют полностью наблюдённый horizon и полную diagnostic history7d. Ни один censored label не интерпретирован как negative. Ноль same-second targets в этих samples не доказывает отсутствия таких purchases в полной population. Cold target остаётся в Y; будущий товар не вставлялся в каталог или candidates. Повтор пары означает любое прошлое событие пользователя с товаром, а не повторную покупку.

| UTC anchor | Eligible A | Positive A / 2000 | Eligible B | Positive B / 2000 |
|---|---:|---:|---:|---:|
| 2019-10-08 | 957543 | 17 | 347614 | 30 |
| 2019-10-09 | 981575 | 13 | 372859 | 37 |
| 2019-10-10 | 1002441 | 13 | 397177 | 37 |

В A — 5986 distinct users, в B — 5988; unit основной диагностики — query-day. Только 43/104 положительных запросов недостаточно для уверенного выбора тонких feature/loss ablations. Разница p(nonempty) описывает разные аудитории. Она не является качеством рекомендателя, causal lift или критерием самостоятельного выбора B.

## Resource gate

Mac M3 Pro; DuckDB1.5.6, две нити, memory_limit2GB, max_temp_directory_size2GB, deadline1800s на вариант. Source открывается read-only; CSV не перечитывается. Для каждого дня временная eligibility-агрегация удаляется после sampling; остаются только sampled Q. Ни user×catalog, ни candidate expansion здесь нет.

EXPLAIN в ignored report содержит **estimates**, отдельно от measured profiler. Для A eligibility stages фактически сканировали 9 216 000 / 9 338 880 / 9 707 520 строк по DuckDB cumulative_rows_scanned; это engine scan counters с возможным округлением до row groups, а не точные counts событий внутри окна. Последующие stages также сканируют source; маленький Q не устраняет их стоимость. Actual eligibility keys — 957543 / 981575 / 1002441 для A и 347614 / 372859 / 397177 для B. Это число групп, не байты distinct state.

Engine system_peak_buffer_memory — отдельный high-water counter (A≈0.94GiB, B≈0.91GiB); не нужно складывать его с process RSS. system_peak_temp_dir_size=0 во всех stages обоих runs: engine spill в этих runs не наблюдался. temp_disk_bytes_at_stage_end дополнительно включает сохранённые profiler JSON и не выдается за peak spill. Полный отчёт сохраняет stages, limits, фактическую schema, ingest metadata и bounded scan plans; при ошибке executor сохраняет partial cost report со status=failed, не объявляя неполные counts результатом.

Измерения относятся к этим двум запуском и объёму anchors; это не benchmark полного обучения. Warm page cache и fingerprint preparation входят в runtime; независимых повторных timing trials не проводилось.

## Проверка и воспроизводимость

13 scoped tests прошли: hand-computed counts, независимый row-iteration oracle, отдельный in-memory DuckDB SQL oracle, lower/upper endpoints, duplicates→binary labels, pre-label SHA sampling, same-timestamp permutation, future suffix для Q, censoring и пустой source. Tests не читают реальные user IDs. После actual execution отдельно проверены parquet counts:6000Q/51Y и6000Q/121Y, Q IDs уникальны. Это проверки корректности, не доказательство metric gain.

Input identity включает фактический SHA-256 immutable read-only DuckDB и SHA-256 uv.lock + трёх production modules. Raw SHA из ingest_metadata `8ebca1ad741295297368f2cf0315e3f36853a1a11768fb16babf8c9b83838147` — ранее проверенный provenance импорта; raw gzip повторно не хешировался. Query/label parquet, detailed profiler и manifest остаются ignored. В Git находятся только код, synthetic tests и эти агрегаты.

- A run_id: `2b764734a8729a86dbb971e970fe1bfaf220ef1e5a7937198053e531336c4435`.
- B run_id: `687afe24b689c0996344892808306685f39afdf56a5dad5aa521c3094ec0305d`.

Повторная команда с той же identity не перезаписывает существующий каталог результатов. Для inspect/reuse читать сохранённые run.json/report.json; новый протокол или код создаёт новую identity.

```sh
python -m scripts.anchor_pilot --config configs/protocols/clock-7d.json
python -m scripts.anchor_pilot --config configs/protocols/clock-48h.json
```

Следующий эксперимент TLAB-004 измерит past-only retrieval coverage на явно выбранном development pilot. До его завершения нет выводов о Recall кандидатов, числе групп с ranking signal или преимуществе моделей. Для обучения/validation потребуется отдельный label-independent план увеличения support и замороженные временные границы; не отбирать покупателей и не открывать final holdout ради этого.

## Review/fix audit

Независимый B2 подтвердил actual aggregates, manifests и parquet предыдущих коротких runs, но нашёл обход wall deadline: SQL interrupt не сохраняет состояние между statements. Исправлен persistent monotonic/Event guard перед/после stages, внутри дневных/label loops, при fingerprint preparation и перед complete; активный SQL дополнительно interrupt. B3 независимо принял fix:13 scoped testsPASS. Четыре новых regressions проверяют Python-stage expiry, persistent flag между SQL, invalid deadline/nonstage checks и сохранение failed partial report/run manifest без query export.

После fix выполнены новые A/B runs с указанными выше identities. Полное двустороннее EXCEPT ALL старых/новых Q и Y дало0 отличающихся строк во всех четырёх сравнениях, daily aggregates идентичны. Старые ignored artifacts сохранены: A`3ef4a51607963d43ffbe3a61e9560c25d248177f71dee13bff7f4e524d4de7cd`, B`5d710990599c31d20b3979303006a471b054412800a9b7beaaaba4e0a261fd88`. Это история исправления; повторных model experiments или подбора sample seed не было. Итоговая приёмка обновлённых run provenance выполнена координатором; [finding/fix и actual evidence](../backlog-reviews/tlab-003-verification.md) сохранены. Это принятие корректности pilot, не преимущества target/model.
