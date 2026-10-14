# M07. Последовательная модель: сначала доказать ценность порядка

Дата: 15 октября 2026. Независимое исследование; обучение, установки и изменения репозитория не выполнялись. Target, anchor, H и split остаются предложениями. Числа REES46 взяты из общего source brief и существующих `docs/embedding-experiments.md`, а не из нового вычисления.

## Рекомендация и приоритет

**P0 — сильный настроенный ручной boosting B**, popularity/last-item и обучаемый mean-pooling контроль. **P1 — один SASRec-small-подобный encoder**, если pooled-профиль уже полезен или есть отдельная проверяемая гипотеза о порядке. **P2 — GRU4Rec для session-based постановки; MIND отложить.** Последовательная ветка необязательна, ARGUS или готовые pretrained-веса не являются условием проекта.

Медиана October — четыре события и один активный день; это полная наблюдаемая история, а история раннего anchor может быть ещё короче. Поэтому длинные зависимости — гипотеза. В исходном [SASRec](https://arxiv.org/pdf/1808.09781) attention концентрируется на недавних действиях в sparse данных; удаление positional embeddings даже улучшило результат на наиболее разреженном наборе Beauty. Переносить этот результат на REES46 нельзя, но он обосновывает обязательность простых контролей.

## Точная предлагаемая модель

Единица — `(user, anchor t, candidate i)`; вход — события строго `event_time < t`. Предлагаемый старт: `d=64`, один attention block, одна голова, causal mask, FFN, residual/normalization/dropout, максимум 50 временных bucket-токенов; это бюджетная конфигурация, не установленный оптимум. Товарная таблица общая для входа и score: `s(u,i,t)=dot(z_u(t), e_i)`. Обучаемой таблицы трёх миллионов пользователей нет.

Для одной секунды одного пользователя создаём один токен: permutation-invariant mean векторов `(item + event_type)` всех событий bucket плюс проекция счётчиков типов; добавляем позицию bucket и фиксированную log-bucket давность до t. Финальный query-токен читает только прошлые bucket. Это **наша адаптация**, а не оригинальные SASRec event/time признаки. Она исключает порядок по row ID внутри секунды. Простая треугольная маска над сырыми строками этого не гарантирует.

Оставляем последние 50 полных bucket, старые удаляем целиком; сохраняем overflow flag и число отброшенных событий. Большой bucket агрегируем потоково без отсечения отдельных строк. Точный дубль обрабатываем по единой согласованной политике; повторы в разные секунды сохраняем. Пустая история получает fallback и отдельный индикатор; OOV item — отдельный embedding, padding — отдельная маска. Metadata/price, если добавятся, должны быть as-of.

## Loss и обучающая популяция

В [авторском model.py](https://raw.githubusercontent.com/kang205/SASRec/master/model.py) исходный SASRec использует сумму positive/negative logistic terms по непустым позициям. [Sampler](https://raw.githubusercontent.com/kang205/SASRec/master/sampler.py) выбирает пользователей с минимум двумя событиями и исключает из negatives весь их train-item set. Это не готовый рецепт наших anchor/population: молчаливое копирование меняет поддержку негативов и использует будущие относительно раннего prefix взаимодействия.

Предложение для purchase-ranking — одинаковый sampled-softmax для pooling и sequence: `−log(exp(s+)/[exp(s+)+Σ exp(s−)])`, 256 uniform negatives из зафиксированного доступного до соответствующего anchor support; sampler и распределение документируем. Для предлагаемого set-target берём уникальные purchases с `t < τ ≤ t+H`, усредняем loss по ним, исключая весь зрелый target set из negatives; покупки той же секунды отдельно считаем неоднозначными. Дубликаты negatives маскируем; in-batch negatives сначала не нужны. Это sampled objective, не exact full-catalog likelihood или calibrated purchase probability.

Обучение на query с покупкой оценивает условное предпочтение товара; query без покупок не даёт положительного сигнала этому loss и остаётся в отчёте о покрытии и согласованной оценке. Нельзя скрыто выбирать anchors непосредственно перед purchase. Next-any-event pretraining — отдельная optional ветка, преимущественно view-задача; улучшение её loss не доказывает покупочный выигрыш. Нет impressions: unobserved не означает dislike.

Все encoder/item weights, vocabulary, sampler priors и настройки должны быть доступны **до первого downstream train anchor**, например после отдельного warmup с созревшими labels. Затем frozen encoder при обновляемой истории. Обучить encoder до конца boost-train и вычислить им ранние train-features недостаточно. Forward snapshots требуют согласования представлений; сырые координаты разных checkpoint нельзя склеивать как одинаковые признаки.

## Память и программная реализуемость

Оценки арифметические, не замеры. Таблица `166794×64` FP32 — 40.72 MiB; weights+gradient+два Adam-state — примерно 162.88 MiB, без прочих тензоров. Для `B=128,L=50` полные logits `B×L×166794×4` — **4,269,926,400 bytes, 3.98 GiB**. Только финальная позиция — 81.44 MiB. Sampled logits `B×L×257×4` — 6.27 MiB; один anchor — 0.126 MiB. Однако материализация отдельных sampled embeddings всех позиций добавит 401.56 MiB; shared negatives/chunking меняют эту стоимость. Attention, backward, optimizer и allocator добавляют память.

Windows 32 GB RAM/RTX3070 предположительно 8 GB выглядит правдоподобной платформой малого sampled-пилота, но VRAM/драйвер/throughput не проверены. [PyTorch официально поддерживает Windows/CUDA](https://pytorch.org/get-started/locally/); [Apple подтверждает MPS для Apple silicon](https://developer.apple.com/metal/pytorch/), однако Mac 36 GB unified memory не равен 36 GB свободной VRAM. Конкретные операции и backward требуют smoke-check. Истории читаем компактно/потоково, не загружаем весь October в Python objects.

[Оригинальный SASRec](https://github.com/kang205/SASRec) — Apache-2.0, протестирован на Linux/Python 2/TensorFlow 1.12; современная PyTorch-адаптация предпочтительнее восстановления этого окружения. TensorFlow [после 2.10 не поддерживает GPU на native Windows](https://www.tensorflow.org/install/pip#windows-native). [Официальный GRU4Rec PyTorch](https://github.com/hidasib/GRU4Rec_PyTorch_Official) предлагает cross-entropy/BPR-max, session-reset и не реализует полноценный user-history перенос/BPTT; это отдельная адаптация. Его [лицензия](https://github.com/hidasib/GRU4Rec/blob/master/license.txt) разрешает research/education, коммерческое применение требует разрешения.

## Решающий эксперимент

Одинаковые anchors/candidates/target/loss/budget: B; B+last-bucket score; B+mean-pool score; B+sequence score. Последний bucket с несколькими товарами тоже агрегируем симметрично. Будущие positives в candidates принудительно не вставляем; cold targets вне universe считаем misses и показываем coverage. Проверяем длины 0/1/2–4/5+ и повторы. Удаление positional embeddings не делает многослойный causal encoder полностью orderless: нужен настоящий pooling-контроль. Если прирост есть только на длинном хвосте или исчезает против pooling, ветку остановить. [MIND](https://arxiv.org/pdf/1904.08030) выделяет несколько интересов через dynamic routing и label-aware attention для matching; это другая гипотеза, не доказательство ценности порядка. Frozen-feature протокол обеспечивает честность, сам по себе новизной не является.


## Coordinator protocol appendix — 15 октября 2026

Авторский right-closed (t,t+H] не используется в текущем clock: [t,t+H) включает anchor purchase после pre-update prediction, исключая его из history. Same-second label — наблюдаемый outcome этого clock, не внутрисекундный порядок. Right-open maturity t+H+delay≤cutoff; closed-right требует строгого <cutoff при sourceevents<cutoff. Для matched pooling/sequence одна history/types/weights/truncation policy. «256 negatives и dedup» требует явного sampling law: uniform без возвращения m=min(256,support) либо иной declared multiplicity; не переносить draw correction после dedup. Fifty bucket tokens не cap50raw events, большой bucket streaming aggregation учитывается в стоимости. HYP077/078 не сформулированы как новые hypotheses и остаются reserved. Proposed comparison fits не расширяют budget.
