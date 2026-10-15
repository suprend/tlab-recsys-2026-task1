# Round057 — TGN как deferred stateful alternative, не дополнение016

**Primary paper/code audit и prospective serving contract.** Рассмотрен один подход за пределами bounded grammar: Temporal Graph Networks. Никаких installs, graph builds, tensors, models, fits, data/holdout reads или hardware tests. Это refinement существующих sequential/graph research families, не новая HYP и не текущая implementation proposal.

## Что делает исходный метод

[Rossi et al., TGN, arXiv2006.10637v3](https://arxiv.org/pdf/2006.10637v3) представляют события temporal multigraph, node memory, messages, GRU/RNN update и graph embedding. Memory обновляется observed events и после обучения; learned parameters и evolving state — разные объекты. Для gradients raw messages прошлого batch применяются перед predict следующего. Все predictions batch используют общий memory snapshot, поэтому поздние events внутри batch имеют stale state; авторы обсуждают trade-off. Эксперименты относятся к future-edge prediction/node classification на Wikipedia/Reddit/Twitter, с sampled negatives,10runs и AWSp3.16xlarge. Это не daily purchase-set ranking/fullY и не замер RTX3070. Результаты TGN не являются evidence выигрыша у нашего boosting.

Официальный [repository](https://github.com/twitter-research/tgn) — primary implementation; ниже наблюдён public master, immutable SHA не установлен. Его старые dependency pins не устанавливались и не объявляются совместимыми с текущей Windows/GPU средой.

## Точные code seams, которые нельзя перенести молча

В [model/tgn.py](https://github.com/twitter-research/tgn/blob/master/model/tgn.py) `compute_temporal_embeddings` вычисляет embeddings, затем сохраняет/применяет messages для positive source/destination pairs. Следовательно, вызов на candidate C как на interaction edges не является read-only inference: он выдумал бы события просмотра/покупки. Здесь же raw node/edge feature arrays целиком переводятся на device, а raw-message timestamps становятсяfloat32.

[NeighborFinder](https://github.com/twitter-research/tgn/blob/master/utils/utils.py) использует `np.searchsorted` без side override и возвращает prefix до найденной позиции: равныеcutoff timestamps исключены. Но bounded recent-neighbor selection при cut внутри большого tied bucket зависит от сохранённого порядка peers. Это sampled/truncated history, не exact aggregate history005.

[LastMessageAggregator](https://github.com/twitter-research/tgn/blob/master/modules/message_aggregator.py) берёт `messages[node][-1]`; равные timestamp не становятся доказанно упорядоченными. Mean aggregator усредняет bag messages, то есть задаёт иной state transition. [Memory updater](https://github.com/twitter-research/tgn/blob/master/modules/memory_updater.py) допускает timestamp equality и клонирует полную memory. Local nondecreasing check не доказывает exclusion всех global peers.

[Training example](https://github.com/twitter-research/tgn/blob/master/train_self_supervised.py) использует one-negative BCE; time normalization statistics берёт из full_data, а eval negative sampler — из полного ID universe. [Evaluation](https://github.com/twitter-research/tgn/blob/master/evaluation/evaluation.py) обновляет state по test interaction batches и считает AP/AUC. Это собственный benchmark access/task contract. Для нашего lifecycle statistics должны зависеть только от разрешённого fit population, а eval проходит по fixed C/fullY; temporal neighbor mask не удостоверяет остальные зависимости.

## Минимальный будущий serving contract

Предлагаются три раздельных операции, не готовый framework:

1. `rebuild_state(θ,observed_prefix,policy)` фиксирует reviewed weights/version, source prefix, vocabulary/OOV, clock/precision и message aggregation. Replay cost оплачивается; memory, накопленную при меняющихся training weights, нельзя автоматически объявить state окончательнойθ.
2. `score_queries(Qτ,Cτ,state<τ)` читает один snapshot для **всех** query/candidate pairs timestampτ, не обновляет messages, gradients или node state. Repeated scoring/C permutation не меняют state. C не ограничивает universe observed events, которыми разрешено обновлять shared item memory.
3. `consume_observed_bucket(eventsτ)` выполняется после scoringτ; все messages используют pre-bucket state, затем одно объявленное per-node aggregation/update. Нельзя придумать stable event order из CSV rowid. Raw duplicates либо сохраняют multiplicity, либо иной edge weighting отдельно утверждён до fit.

При переходе кτ+1 потребляются только события сevent_time<τ+1 и допустимой availability. Query-level futureY никогда не становится входом updater. Уже наблюдённые purchase events прошлых суток использовать законно; вёрстка target table и optimizer step — другие действия. Frozenθ доступна до первого downstream query, simulated2019 clocks отделены от physical executor seals2026. State cache identity включаетθ, adapter, source prefix, cutoff, aggregation/truncation/OOV policy, а не только node IDs.

Для equal-time neighborhood budget требуется peer-invariant selection по заранее объявленной set/bag policy либо явный rejection overflow; «take last20 rows» недостаточно при неопределённом порядке. OOV/new node может получить declared initial memory, но это не learned historical embedding. Empty history и известный zero score различимы. TGN memory — модельный summary; его координаты нельзя назвать exact counts/recency005.

## Timestamp и CPU/3070 feasibility

**Наш аналитический контрпример.** Для Unix seconds2019 около1.57·10⁹ float32 spacing равен `2^(30−23)=128seconds`. Official neighbor output тоже используетfloat32 times. Поэтому непосредственный перенос абсолютныхUTC seconds способен схлопнутьT−1/T/T+1 и повредить deltas. Будущий adapter обязан сохранять exact time ordering вinteger representation и отдельно объявить origin/units при кодировании durations; простое «модель temporal» не закрывает gate. Это не воспроизведённый баг в нашем коде.

[Memory module](https://github.com/twitter-research/tgn/blob/master/modules/memory.py) хранит denseN×d float memory сrequires_grad=False, last_update и pending messages; backup создаёт clones. Нельзя автоматически приписывать каждому node vector Adam moments, но реальные copies/messages/activations учитывать необходимо. Иллюстрация, не измерение текущей коллекции: N=3million,d=172 требует2.064GB **на одну**float32 memory; триcopies —6.192GB, без node/edge features и model workspace. E=40million и4edge features —ещё640MB;172edge features —27.52GB. Official all-edge-device path поэтому может оказаться главным ограничением.

[Официальная NVIDIA specification](https://www.nvidia.com/en-me/geforce/graphics-cards/30-series/rtx-3070-3070ti/) даёт reference RTX3070 8GBGDDR6. [Наш README](../../README.md) планирует Windows32GB/RTX3070, не подтверждает availableVRAM/runtime. Даже уменьшеннаяmemoryd=32 (~384MB приN=3million) не доказывает fit feasibility: остаются adjacency build, Python objects, per-epoch stream, message storage, cloning и scoring всехC. CPU execution path существует в example, но нет оценки two-core wall/CPU; POSIX lifecycle telemetry не становится Windows-supported автоматически. Никакой speedup или бюджет здесь не обещан.

## Единственный оправданный следующий gate и dedup

После текущего deliverable можно отдельно рассмотреть ≤32literal-event/0-fit state-conformance drill с deterministic dummy updater: before/at/afterT, multiuser shared item, duplicate events, empty/OOV, global-peer permutation, repeated candidate scoring, cutoff overflow и resume после whole bucket. Independent expected state/digest должен ловить fabricated C updates и float timestamp collisions. Это проверит interface mechanics, не trainability, memory capacity или purchase gain; сейчас test не исполняется и allowance не выдан.

Существующие user-item08/model07–08 уже обсуждают graph/sequence/learned representations. Поэтому не добавлять ещё одну «TGN улучшит» quality hypothesis. Новая содержательная деталь — serving/state/time/physical-memory obligations конкретного official API. Full neural experiment остаётся deferred: нужны отдельные task/loss/negative-sampling/fitavailability/resource decisions. Нынешний016 pool, fourfits, source oracle и final selector не расширяются.
