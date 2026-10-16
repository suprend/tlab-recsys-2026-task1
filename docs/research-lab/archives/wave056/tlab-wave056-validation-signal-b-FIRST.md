# Wave056 B FIRST — validation signal
Frozen UTC: 2026-10-16 02:23:14 UTC. Blind FIRST; peer056 не читался и не обсуждался.

## Независимый анализ (≤350 слов)

**Базовые предпосылки.** Q/C/fullY, membership, NDCG и tie policy корректны и фиксированы; выбирается префикс конечного полного fit, не глобальный optimum. Reused validation не становится независимой от автоматизации выбора. `informative_candidate_groups` удостоверяет наличие candidate-positive и candidate-negative внутри групп, а не изменение их порядков, статистическую мощность или устойчивость k. Ноль допускает меняющиеся rankings при неизменной метрике. Положительное значение допускает плоскую aggregate-кривую. В native fixture informative=1 и одинаковые feature rows намеренно фиксируют score/rank ties; это исходный UNRUN lifecycle-контракт, не найденное переобучение. Exact-dict уже исправлен.

**Одно условное уточнение существующего019: чувствительность argmax к отдельным запросам.** Механизм: aggregate NDCG усредняет query contributions; редкие меняющиеся запросы либо взаимная компенсация могут определять winner при том же structural count. Helper возвращает aggregate curve/support, но не query-prefix contributions. Минимальный диагностический шаг будущего конкретного consumer — из тех же prefix scores получить v_q(k), число запросов с меняющимся v_q и сколько leave-one-positive-query-out удалений меняют выбранный k. Это описывает влияние имеющейся выборки; не новая политика selection, significance test или оценка generalization.

**Предсказание/ближайший конечный опыт — UNRUN.** Три positive Q, три prefixes; C={1,2},Y={1} каждого; g=1/log2(3). Задать contributions: locked — каждый prefix (1,g,1); cancellation — (1,g,1),(g,1,1),(1,g,1). Aggregate curves совпадают; structural count=3 в обоих. Аналитическое ожидание varying-Q=0/2, deletion-смен-k=0/1 при earliest-tie. Проверять только заданные scores [1,0]/[0,1], без fit, CV, нового holdout или ceiling-extension. Применение к реальному consumer требует отдельного разрешённого scope; текущие данные не открывать.

**Польза исходной цели.** Не выдавать механически выбранный k за убедительное улучшение сильного boosting-контроля или автоматизации признаков; показать, сколько запросов реально поддерживают выбор. Контргипотеза: влиятельный запрос отражает редкий настоящий эффект; deletion stability также возможна при общем смещении. Поэтому diagnostic не доказывает шум/переобучение и не запрещает selection.

**Dedup/решение.** Structural→effective distinction уже053D; prospective проверка уже053B; новое здесь только опциональное query-influence представление внутри019. Для014 это не замена экспериментальному сравнению автоматизации. Ноль новых обязательных задач/ID/gates; нет причины задерживать текущий native lifecycle или требовать новые fits.

## Evidence ledger

- 10 inputs: frozen shared-context JSON + 9 pinned source files; all read as text.
- SHA checks: 3 complete passes / 30 checks; all 10 matched supplied pins before reading, after reading and immediately before freeze (02:23:14 UTC).
- Local source facts: development_training.py returns aggregate curve and copied support; unit source covers changing ranks with off-C targets; native source explicitly forces identical validation rows and earliest tied prefix.
- Accepted historical facts are taken from progress-report.md and wave053/054/fixed300 notes, not newly measured here.
- Runtime/import/tests/native/ML/SQL/raw data/collections/Y/models: 0.
- Git/network mutations/canonical writes/helper launches/coordinator contacts/grants/human questions: 0.
- Papers/web: 0. Proposed experiment: UNRUN, not authorized, no IDs.
- TMP outputs owned: this FIRST, pins.json, freeze.json only.
- Schedule provenance: original 02:15 UTC launch was late; shared context prepared 02:18:30.305196 UTC; next original grid remains 03:00 UTC.

