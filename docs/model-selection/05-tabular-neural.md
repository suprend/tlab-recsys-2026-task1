# M05: компактный табличный neural ranker с историей кандидата

15 октября 2026. Независимое исследование; обучения, установки зависимостей и изменений репозитория не было. Рекомендация: после сильного ручного бустинга рассмотреть **один MLP с candidate-conditioned pooling**, без таблицы user ID. DCNv2 и DLRM оставить сравнением конструкций, а не тремя обязательными запусками.

## Контракт и основание

Единица входа — пара `(q,i)`, где `q=(u,t)` — разрешённый anchor, `i∈C_q`, `Y_q` — выбранные зрелые purchase labels. Anchor, H и relevance пока не утверждены. Архитектура **не меняет Q/Y/C**, sampler, доступность атрибутов и определение нулевых запросов. Нет impressions, изображений, текстов товаров или stock: category ID/code, brand и as-of price — достаточные доступные metadata, но не полный каталог.

В октябре 3 022 290 пользователей и медиана четыре события: преимущество отдельного обучаемого user ID сомнительно из-за слабого support и отсутствия способа индивидуально представить нового пользователя. Это инженерная гипотеза, не измеренный результат. Существующий `docs/embedding-experiments.md` уже предлагает pooled history/two-tower; здесь проверяется конкретно раннее взаимодействие кандидата с историей. По проверенному `docs/task1-requirements.md` нейросеть не отменяет хорошо настроенный ручной boosting; исследовательскую часть закрывает измеренный эффект автоматизации/альтернативы, а не название архитектуры.

## Один предлагаемый кандидат

Предлагаемые размеры, не defaults: общий item embedding `d=32`; отдельные embeddings category ID, code-prefix и brand, проецируемые вместе с item ID в 32 координаты. Numeric-входы: прошлые user/item/pair counts, recency в секундах, наблюдаемая длина истории, log1p(price). Масштабы и clipping обучаются только на разрешённом прошлом; числовые ID не становятся ordinal features. Для цены ноль сохраняется с отдельным флагом; missing получает mask, а не приравнивается нулю.

История `H_q` содержит view/cart/purchase строго до t, с event-type embedding и `log1p(t−t_j)` в секундах. Ограничение — около 32 последних событий, сохраняя timestamp buckets целиком; при переполнении пограничного bucket политика задаётся заранее и не изобретает порядок по ID. Фиксированное окно W остаётся частью общего протокола. Предлагаемый attention:

`a_ij = MLP_a([e_i,h_j,e_i⊙h_j,log1p(Δt_j)])`,

`α_ij = exp(a_ij)/Σ_{k∈Hq}exp(a_ik)`, `z_qi=Σ_j α_ij h_j`,

`s(q,i)=MLP_[128,64,1]([e_i,z_qi,e_i⊙z_qi,x_numeric,x_sparse])`.

Пустая история даёт нулевой z и explicit empty flag; softmax по пустому набору не вычисляется. Это компактная адаптация идеи local activation из [DIN](https://arxiv.org/abs/1706.06978), а не точное воспроизведение: нормировка здесь выбрана явно. Candidate-conditioned z нельзя закешировать один раз на пользователя. Новый user с историей обрабатывается общими весами; без истории остаются metadata/popularity/context. OOV item получает общий unknown ID плюс доступные metadata; missing category code отличается от OOV category ID, padding — от обоих.

## MLP, DCNv2, DLRM и two-tower

MLP учит взаимодействия после concatenation. [DCNv2](https://arxiv.org/html/2008.13535v2) добавляет `x_(l+1)=x_0⊙(W_lx_l+b_l)+x_l`: две cross layers могут заменить разрастание MLP; low-rank `W=UVᵀ` снижает параметризацию. Это optional абляция, не обещание выигрыша на REES46. [DLRM](https://arxiv.org/abs/1906.00091) сочетает dense bottom-MLP, sparse embeddings одинаковой размерности и их попарные dot interactions перед top-MLP. При F полях возникает `F(F−1)/2` скаляров; сам DLRM не задаёт candidate-conditioned history. Его [авторская реализация](https://github.com/facebookresearch/dlrm) и [MIT-лицензия](https://github.com/facebookresearch/dlrm/blob/main/LICENSE) доступны; перенос benchmark-пайплайна здесь избыточен.

Two-tower `s=g(H_q)ᵀf(i)` позволяет кешировать item vectors и применять retrieval; [Yi et al.](https://research.google/pubs/sampling-bias-corrected-neural-modeling-for-large-corpus-item-recommendations/) исследуют такую схему. Наш MLP допускает произвольные pair-features и внимание к кандидату, зато требует вычислений примерно `O(|Q|·|C|·L·d)`. Поэтому это reranker фиксированного C, а не дешёвый full-catalog retrieval. Общая loss не превращает произвольные MLP hidden states в совместимое user/item пространство.

## Память и доступность

Расчёт для float32: таблица пользователей `3 022 290×32` — 96,7 млн параметров, 369 MiB только весов. С dense gradient и двумя Adam moments получается около 1,44 GiB; d=64 удваивает это до 2,88 GiB, ещё без activations/intermediates. [PyTorch memory guide](https://docs.pytorch.org/tutorials/intermediate/optimizer_step_in_backward_tutorial.html) подтверждает состав памяти и дополнительный peak у foreach. Sparse gradients не делают moments разреженными: [SparseAdam source](https://github.com/pytorch/pytorch/blob/main/torch/optim/sparse_adam.py) создаёт два `zeros_like(parameter)`.

Item-table `166 794×32` — 5,34 млн параметров, 20,4 MiB; с небольшими metadata/MLP разумная проектная граница — 6 млн параметров, около 92 MiB для FP32 weights+gradient+moments. Это оценка, не замер полной RAM/VRAM. Начальный microbatch 512–2048 пар, история 32, потоковая загрузка; нельзя материализовать историю заново для всех query×candidate строк. [Windows CUDA поддерживается PyTorch](https://pytorch.org/get-started/locally/); [Mac MPS](https://docs.pytorch.org/docs/2.14/notes/mps.html) существует, но совместимость конкретных операций и доступные 8 GB RTX3070 ещё проверяются. Первый пилот без custom CUDA/extensions и без предположения, что AMP уменьшит optimizer state.

## Loss, проверки и остановка

Старт — тот же sampled BCE, если он принят общим протоколом: `Σ_q w_q Σ_i v_qi[softplus(s_qi)−y_qi s_qi]`. Query/item weights, negative support и correction фиксируются отдельно; sampled-unobserved не становится отказом или калиброванной покупкой. Pairwise замена потребует общей согласованной абляции. Происхождение target определяет supervised/self-supervised режим, не архитектура или BCE.

**P0:** сильный tuned boosting и cheap controls. **P1/HYP-063:** условный pooling против mean pooling при одинаковых inputs, loss, C и сопоставимом числе параметров. **P2/HYP-064:** две cross layers против MLP только после полезного P1; при дублировании существующей гипотезы объединить, не создавать новую «новизну».

Бюджет предложения: три заранее заданные конфигурации, до пяти эпох с validation stopping, подтверждение победителя тремя seeds; общий потолок 12 GPU-часов с учётом оценки кандидатов. Он не гарантирует завершения: исчерпание означает недостаточный эксперимент. Сравнивать с boosting на одинаковых downstream anchors; fitted encoder/vocabulary/scaler заморожены до первого downstream периода, labels зрелые, history обновляется строго раньше t. Проверить empty/zero-purchase queries, OOV/cold targets вне C, повторные покупки и same-second группы. Отдельно убрать attention и pair-features: прирост может объясняться последним просмотром. Остановить ветку при отсутствии устойчивого validation-прироста над сильным boosting либо неприемлемой стоимости; test остаётся финальным однократным решением.
