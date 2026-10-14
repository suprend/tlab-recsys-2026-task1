# 08. Two-tower / sequence retrieval: извлекать новые покупки, а не повторять feature experiment

Дата: 15 октября 2026. Независимое исследование по первичным источникам; код, данные, окружение и Git не изменялись, модели не обучались. Контекст: общие briefs, существующие `docs/sequential-embeddings.md`, `docs/embedding-experiments.md`, M06 и `configs/protocols/clock-48h.json`. Новые candidate notes коллег не читались.

## Факты и рекомендация

Двухбашенная модель вычисляет профиль пользователя и вектор товара независимо, затем извлекает товары по inner product. Первичный пример — YouTube: история → user/context embedding → dot-scored candidates → отдельный ranker; sampled training не превращает retrieval score в purchase probability. [Covington et al., 2016](https://research.google.com/pubs/archive/45530.pdf).

Для REES46 первым проверять jointly trained pooling retrieval, затем SASRec-small как проверку пользы порядка. Медиана четырёх событий и отсутствие богатого контента делают сложный sequence encoder необязательным. Готовый pretrained ARGUS не предполагается. Это предложение новой **candidate source**, тогда как M06/UI06 исследуют совместимость на фиксированном C; повторять их feature-гипотезы под новым номером нельзя. HYP079/080 здесь остаются reserved, без новой формулировки или разрешения обучения.

## Точное правило источника

Единица запроса q=(u,t), UTC; история — события view/cart/purchase из `[t−7d,t)`. `V_t` — товары, наблюдавшиеся строго до t: proxy known catalog, не stock availability. Совместно обучаем `v_i=gθ(ID,categoryID,brand,missing)` размерности 64 и `z_q=fθ(history)`. P0 исключает price из tower; динамические metadata кандидата берутся из latest global bucket `<t`, с сохранением NULL/conflict, без поиска более старого «чистого» значения. Для history token используются атрибуты, доступные при событии. Векторы materialize по версии checkpoint и metadata state, не только по product_id.

Pooling-контроль: `z=MLP(concat(mean_view(v),mean_cart(v),mean_purchase(v),counts,empty_flags))`. Последние максимум 50 событий выбираются целыми timestamp buckets, двигаясь от новых к старым; crossing bucket и всё старше пропускаются, `truncated/overflow` сохраняются. Внутри bucket pooling симметричен. SASRec/GRU-адаптация получает один агрегированный token на timestamp bucket плюс gap/event summary; causal порядок существует только между разными timestamps. Это адаптация, не воспроизведение оригинальной event-token архитектуры.

`R_nn(q,k)=TopK_{i∈V_t}(z_qᵀv_i)`, exact batched dot search, deterministic tie-break по ID только при равных **scores**. Исторические события по ID не упорядочивать. Не нормализовать векторы после dot-training: cosine меняет retrieval rule. Для GRU брать output item representation, совместимую с hidden state; reset по `(user_id,user_session)` означает session-рекомендации, carry через сессии — отдельную модель. SASRec использует causal attention, dot scoring и sampled binary loss; его готовый sampler/evaluator нельзя переносить без временной проверки. [SASRec paper](https://arxiv.org/html/1808.09781v1), [author code](https://github.com/kang205/SASRec/blob/master/model.py), [официальный GRU4Rec](https://github.com/hidasib/GRU4Rec_PyTorch_Official).

## Предложение обучения и доступность

После утверждения purchase set-target взять `Pq=distinct purchases in [t,t+H)`, `P′=Pq∩V_t`, `m=min(128,|V_t\Pq|)` уникальных uniform negatives без replacement. Минимизировать mean по поддержанным positive и затем по queries: `−log(exp(s_p/τ)/(exp(s_p/τ)+Σ_N exp(s_n/τ)))`. Это sampled per-positive contrast; другие positives не negatives, повторные покупки не исключаются. Пустые P′/N пропускаются с reason counters; zero-purchase queries остаются в evaluation. Нет impressions: sampled unobserved не доказанные отказы.

Next-view pretraining — дополнительная ветка внутри warm-up с тем же input support, затем purchase fine-tuning внутри того же временного бюджета; view loss не purchase objective. Для next-bucket supervision нельзя превращать peers в цепочку next-event. Веса, vocabulary, scaler и sampler должны удовлетворять `fit_cutoff≤available_at≤first downstream query`; labels warm-up зрелые до cutoff. Затем freeze parameters, обновлять только фактически прошедшую историю и as-of metadata. Fit на конце train не разрешает признаки или candidates для ранних train queries.

## Квоты и проверка полезности

Текущий provisional base `004`: popular200 + recent20, dedup, max220, **no-refill** — не менять без review. Отдельное предложение: recent20 + popular100 + neural100, dedup, max220, no-refill; recent priority, затем чередование двух ranked lists в пределах квот. Это пример бюджета, не optimum.

Публиковать actual |C| и Recall итогового union; marginal contribution — `|Pq∩(R_nn\C_base)|/|Pq|`, дополнительно удаления positives из-за уменьшения popular quota. Для честного derived budget comparison оба результата обрезать до `min(|C_base|,|C_new|)` по заранее заданному порядку, без refill; исходные результаты сохраняются. Одинаковые queries/labels, no oracle positive insertion. Показывать all-target Recall, in-support Recall/coverage, OOV, history length и repeats; zero-purchase convention фиксировать заранее. Baselines: recent+popular, pooling, затем SASRec с теми же inputs/objective/budget. Downstream gain и fixed-C similarity-feature ablation сообщать отдельно.

## Инженерная оценка и границы

FP32: 166794×64 item table≈40.7 MiB; веса/градиенты/два Adam moments≈163 MiB только таблица. Logits256×(1+128)≈129 KiB; exact inference256×166794≈162.9 MiB; full training logits256×50×166794≈7.95 GiB. Это арифметика, не peak-memory/throughput benchmark. Histories держать streamed/ragged на CPU; все user embeddings и 42 млн event vectors не материализовать.

Windows32GB/RTX3070: PyTorch поддерживает CPU/CUDA, но driver, VRAM и реальные kernels требуют pilot. Mac36GB: CPU и MPS API доступны, совместимость конкретного sampler/GRU/attention не подтверждена. [PyTorch platforms](https://pytorch.org/get-started/locally/), [MPS](https://docs.pytorch.org/docs/stable/mps.html). У PyTorch [BSD-style license](https://github.com/pytorch/pytorch/blob/main/LICENSE). Author SASRec — Apache-2.0, legacy TF1/Python2; указанный авторами PyTorch-port также Apache-2.0, закреплять commit. GRU4Rec official допускает research/education, commercial требует лицензирования; это не MIT. [SASRec](https://github.com/kang205/SASRec), [port](https://github.com/pmixer/SASRec.pytorch), [GRU license](https://github.com/hidasib/GRU4Rec_PyTorch_Official#readme).

Edge cases: пустая history → past-popular fallback; новый после warm-up ID → обученный ID-dropout OOV+as-of metadata; одинаковые metadata → ties, без индивидуальной cold-различимости; oversized same-second bucket → overflow policy; target вне V_t → явный miss. Сохранить источник/rank/checkpoint/cutoff/OOV/overflow у каждого кандидата. Остановить усложнение, если marginal Recall исчезает против recent+popular при matched actual C или эффект ограничен скрытым warm-only срезом.
