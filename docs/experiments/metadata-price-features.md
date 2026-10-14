# TLAB-009: metadata и относительная цена

Статус: SQL-ядро принято независимым review; ограниченный100Q executor реализован и ожидает отдельного review. Реальные REES46 признаки пока не рассчитаны; новых обучений и результатов качества для этого блока нет. [Принятый дизайн](../backlog-reviews/metadata-price-design.md) задаёт один блок, отдельный100Q cost/source gate и максимум один последующий ablation fit. Accepted005/008/017 и их артефакты остаются неизменными.

## Определения

На каждый UTC anchor t берём последний глобальный timestamp товара в[S,t), затем все строки этого bucket, включая других пользователей и дубли. Category ID, raw code, brand и price разрешаются независимо. Clean означает единственное значение при отсутствии NULL; allNULL даёт missing; known+NULL или несколько известных значений дают ambiguous. Назад к более старому clean значению не возвращаемся. Новый category snapshot обязан совпасть с accepted005 по ID и обеим flags.

`brand_missing` и `price_missing` означают **нет clean scalar**, включая ambiguous; `*_ambiguous` уточняет причину. Clean price0/negative остаются наблюдаемыми: missing0, log_price=NULL и отдельный zero/negative flag1. `{0,NULL}` ambiguous: missing1, ambiguous1, zero0. Source NaN/±Inf в relevant latest buckets отклоняются до фильтра positive-price; future-only строки и более старые invalid prices не меняют snapshot. Relevant population — все active7d товары плюс fixed candidates.

Dictionary по clean current ID использует все nonNULL named codes в[S,t). Единственный код даёт значение; ноль кодов или unusable ID — code_missing; несколько кодов — code_ambiguous. Эти две flags различны. Empty string считается наблюдаемой строкой: код не чистится эвристиками. `code_recovered` включён, если dictionary известен, а clean latest raw code отсутствует/отличается. Отдельная provenance сохраняет raw resolution, latest timestamp, dictionary support/first-known и reference membership; это не дополнительные model inputs.

`R_c(t)` содержит distinct active products с любым событием в[t−7d,t), clean **current** category и clean finite positive latest price. Товары внеC и другие пользователи участвуют. Повторы не меняют вес. `log_price=ln(1+p)` в неизменённой единице исходного price; валюта источника не предполагается. Для каждого кандидата среднее берётся по другим product IDs вR, затем `difference=own_log_price−peer_mean`. Production использует sum/count с кусочным вычитанием только при фактическом membership; oracle строит список остальных товаров напрямую.

| Состояние | Peer support | Peer mean | Difference |
|---|---:|---|---|
| Category unknown/ambiguous | NULL | NULL | NULL |
| Category known, R empty | 0 | NULL | NULL |
| Self-only valid member | 0 | NULL | NULL |
| Nonmember, R nonempty | N | Known | Known iff own price valid |
| Valid member with peers | N−1 | Known | Known |

## Фиксированная схема

Отдельная keyed table имеет ровно20 columns: `query_id`, `product_id`, затем3nominal и15numeric. Nominal order: `category_id_nominal`, `category_code_by_id`, `brand`; все значения имеют namespace `value:` или sentinel `state:missing/state:ambiguous`. Parquet хранит UTF8 strings; loader выдаёт object array UTF8 bytes. IDs никогда не передаются числом модели.

Numeric order: `brand_missing`, `brand_ambiguous`, `code_missing`, `code_ambiguous`, `code_recovered`, `log_price`, `price_missing`, `price_ambiguous`, `price_zero`, `price_negative`, `category_peer_log_price_mean`, `category_peer_product_support`, `category_log_price_difference`, `category_peer_mean_missing`, `category_price_difference_missing`.

SQL считает known numbers вDOUBLE/BIGINT, flags BOOLEAN. Loader преобразует numeric вfloat32, ожидаемые NULL — NaN, проверяет flags/masks/conditional support и отсутствие±Inf после cast. Native train cardinality проверяется по actual encoded values **включая sentinels**, максимум4096 для каждого nominal; превышение требует пересмотра, не CTR fallback. Model feature order будет base41numeric +15numeric +3nominal =59, после отдельного integration review.

## Текущая проверка

15 synthetic tests проверяют все18 model features каждой toy пары, randomized direct-row oracle на двух anchors, UTC seven-day boundary, latest global other-user bucket, category move, duplicate/reference invariance, same-second/future suffix, dictionary conflict/recovery/provenance, unknown/empty/nonmember reference, NULL mixtures, clean0/negative, malformed nonfinite source, float32/bytes/4096 cardinality и fault injection в masks/base category/keys. Чистое ядро не открывает labels, не создаёт model или acceptance.

Следующий шаг после независимого review —100 заранее label-independent Q, распределённых по train days, ≤22000pairs, CPU2threads, wall≤600s, RSS≤8GiB, spill≤2GiB. Проверяется full reference population всех выбранных категорий и каждая selected pair отдельным source oracle. Только после этого разрешается full export и отдельный один ablation fit на заранее выбранном smoke objective Logloss с теми жеC/Y/settings/checkpoint50. Confirmation/final labels для этого не используются.

## Ограниченный исполнитель

Pure-core independent oracle проверил518toy rows×18features=9324comparisons,323full-reference и518provenance rows; максимальная numeric absolute error3.55e−15. Синтетический genericDOUBLE tinyprice1e−20 выявляет известную разницу `ln(1+p)` и stable `log1p(p)` около машинного epsilon. Actual source price — DECIMAL(12,2), где такой положительной величины нет; точность вне этого inputdomain не заявляется.

`prepare_gate_plan` только предлагает identity, проверяя external acceptedtrain collection и точные current helper/spec/input fingerprints. `run_gate` требует отдельный coordinator approval со scope `metadata_price_100q_source_cost_gate`, идентичными runID/fingerprints; сам себя не принимает. Единственный CLI scope —train100Q; нет fullphase/selection/fit flags.

Sampling сортирует queryIDs поSHA256 внутри каждого UTCday, затем берёт100 поwithin-dayrank,anchor,queryID. На13равных trainingdays это8Q на первых9days и7Q на последних4; unequal-day fixture проверяет фактические IDs независимым Python sorting. Ни labels, ни candidates не участвуют в выборе Q. Acceptedtrain label bytes могут хешироваться lineage gate, но target table не создаётся и значенияY не разбираются.

Attempt audit создаётся до подготовки; fixed artifact root и immutable identity сохраняют failed/partial попытки. База открывается read-only, acceptedQ загружаются во временную таблицу, fixedbaseF читаются только дляselectedQ. Исполнитель проверяет точные names/types/order, C/addon/provenance key cover, strict-past provenance и fullR uniqueness/membership. Выдаёт отдельные Parquet Q/addon/provenance/reference, actualQ keySHA/exportSHA/schema/counts вmanifest/report. Source/provenance rows остаются ignored.

Persistentwall deadline и SQLinterrupt работают вместе с cooperativeRSS/tempdisk guards. DuckDB использует2threads, requestedmemory2GB иrequestedspill2GB; это не hardRSS limit. Actual processuser+system CPU seconds записываются отдельно отwall; nestedstageCPU/wall inclusive, их нельзя суммировать поверхprocess total. Неудача CPUmeasurement предотвращает complete. Output100Q cardinalities diagnostic, не доказательство fulltrain4096gate; Pool/model/predict здесь не создаются.

28tests включают прежние15purecore и runnerfaults: approval missing/extra/digest/type; spec snapshot drift; selection-role refusal; unchangedhelper pins; deterministicbalanced/unequal-day sampling;22000cap доallocation; timeout/openfailure; CPUcounterfailure; terminalinputmutation; immutableoutputretry; missingprovenancecolumn/fullRmembership. Первый draft поймал несовместимость relation.create_view с read-only DB: заменено на TEMPtable + fixedF Parquet semijoin. Независимое runnerreview нашло возможность превышения лимита при закрытии connection после последней SQLпроверки: финальные guards теперь проверяют close/finalCPU/manifest/audit write. Три регрессии воспроизводят700sclose, RSS8GiB+1 приclose иcloseexception; все сохраняют failed audit и выбрасывают ошибку. До исправлений реальный executor не запускался.

После отдельного code/approval review один diagnostic вызывается из project root:

```text
.venv/bin/python -m scripts.metadata_price_features \
  --collection-acceptance artifacts/acceptance/tlab017-train-collection.json \
  --spec configs/features/metadata-price.json \
  --gate-approval artifacts/acceptance/tlab009-100q-gate.json
```

`complete_produced_unreviewed` означает только завершение executor. Source/cost acceptance выдаётся после отдельного direct-list oracle по всем selectedpairs и полномуR, а full exports и один ablation fit получают последующие отдельные разрешения.


## Принятый реальный100Q diagnostic

[Independent source/cost acceptance](../backlog-reviews/tlab009-100q-source-verification.md) принимаетrun2f144cb…fd54:100queries/20586pairs/20modelcolumns,all370548values/provenance/full1603114reference rows reconciled. Producer22.1533wall/33.1295actualCPU seconds/RSS1490386944; independentaudit18.4017wall/26.5238CPU/RSS955006976. Nominal100Qcardinalities200/49/124diagnosticonly; no fits/labels/qualityclaims. Metadata100module596f137e…52b4 иspecнеизменны; fullproducer выполняетсятольковновыхmodulesпослеотдельногоревью.
