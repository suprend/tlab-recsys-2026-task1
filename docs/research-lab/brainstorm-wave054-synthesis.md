# Волна 054: будущий paired caller и validation

Два новых независимых FIRST и отдельный critic приняты как условные уточнения TLAB-019. [Точные оригиналы](archives/wave054/publication.json). Новых ID, обязательных проверок, refactor или runtime-разрешений нет; конкретный будущий paired consumer пока не установлен.

**A — буквальный порядок.** Если реальному caller нужны оба полных fit до первого selector, понадобятся fit-only и select/shrink фазы. Два нынешних helper-вызова дают B-fit→B-select→W-fit. Ближайший UNRUN spy: оба fit-end перед selector; ошибка W означает ноль selectors. Без реального consumer разделение отложено; исторические маршруты сохраняются.

**B — более узкий информационный контракт.** Неизменные планы и изоляция B-feedback могут исключить адаптацию W, но не воспроизводят буквальный порядок или глобальную независимость. Предсказание: B-wins/B-loses не меняет W recipe/continuation/reporting. Hypothetical trace — source-only рассуждение, не исполненный тест. Даже заранее объявленные metric-driven W cancellation/retry или complete-cases-only reporting не доказывают полный paired comparison.

**Уточнение critic:** pre-fit validation accounting уже читает labels/fullY support для admission, без model-dependent feedback. «Никакого Y до fit» неверно. До fits фиксируются recipes/source identities, features, Q/C/fullY, chronology/maturity, weights/seeds/objective, ceilings, selector/ties и независимое от метрики продолжение. Сохраняются full/selected модели, curves/support, scores/ranks, reload/prefix parity, события и ошибки.

**Польза Task1:** различать выбранные процедуры и fixed-k контраст. Для второго нужны заранее общий k и согласованные recipes; одного k недостаточно для причинного вывода. Оба full fit, K_B+K_W зависимых checks, preparation/verification/persistence, неудачи и tails оплачиваются; shrink не возвращает стоимость обучения. Final не переиспользуется, CPU остаток неизвестен. Интеграция отложена до реального потребителя.
