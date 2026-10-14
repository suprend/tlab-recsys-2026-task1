# TLAB009: независимый review frozen pure core

Вердикт: **ACCEPT pure core на четырёх exact freeze pins ниже**, без замечаний, блокирующих эту ограниченную границу. Это текстовый review, не запись acceptance для данных, runner или модели. Реальные признаки REES46, 100Q cost/source gate, full exports, mixed59-input integration, actual full-train cardinality и единственный009ablation fit остаются отдельными gates. Реальные данные/модели не читались, fits не выполнялись; frozen008/005/017 и production files не изменялись.

## Проверенный freeze

SHA256 совпали до и после независимых запусков:

| Файл | SHA256 |
|---|---|
| scripts/metadata_price_features.py | 7c348c28e21baa183b7243c651e976872a23bdd46c44a31b9581a48a33787e3b |
| tests/test_metadata_price_features.py | 4cc95e3275f7254a6c5413b04274c9f282d1dd323e55f7f76b0971ac88eba021 |
| configs/features/metadata-price.json | 20c11d9bc2e752816c07fe894e975a93a94fd81926ce5de20e250c31283fa2b8 |
| docs/experiments/metadata-price-features.md | f7f6e921afde0f0d0fb3e497810a364aa13db7a2f3d84fac94c8855c4d2c58f0 |

Прочитаны принятый design/semantic appendix, прежний critic и research round006. Исходники pure core/tests/spec/docs проверены полностью. Авторские15tests независимо воспроизведены: PASS, unittest0.490s. Их oracle не использовался для собственного ожидаемого результата.

## Независимый oracle и исполненное доказательство

[List oracle](../../tests/oracles/metadata_price.py) написан по семантике до чтения production freeze. Вход — Python mappings events/Q/C и явный UTC source_start; выход — keyed3nominal+15numeric, отдельная provenance и полный reference rowset. Он не импортирует producer, SQL helpers, CatBoost или real data. Latest bucket строится прямой фильтрацией списка, поля разрешаются независимо, dictionary — множество nonNULL codes из полного прошлого. Для каждого кандидата заново формируется список всех active products подходящей current category; peers — этот список без собственного product_id, mean — `fsum(peer_logs)/len(peers)`. Production A−removed/N−member не повторяется.

[Harness archive](tlab009-pure-core-harness.md) вызывает production только для actual values на собственной in-memory DuckDB. Expected values/005 category inputs получены независимым oracle. Все tables создавались на искусственных строках; никаких production tests fixtures или их oracle для expected не импортировалось. Проверялись exact keyed/model/reference relations, все raw provenance fields, dictionary count/scalar/first-known, latest timestamp и membership. Числовой допуск объявлен `atol=1e−12, rtol=1e−9`; NULL/flags/integers/encoded nominal сравниваются точно.

Финальный [JSON evidence](tlab009-pure-core-evidence.json):14cases,518model rows×18features=**9324comparisons**,323full-reference rows и518provenance rows. Golden cases дополняют8seeded randomized datasets на двух anchors; два users при одном anchor имеют разные C. Максимальная абсолютная разница model numeric —3.552713678800501e−15. Пройдены3metamorphic variants: перестановка строк/C, повторы source rows, future-only malformed suffix. Отдельно6source NaN/±Inf случаев отвергнуты с именно Nonfinite-price reason, включая active product внеC; guard проверен actual producer, не остановлен заранее oracle.

Выполнены8fault rejections: corrupted price/brand/code masks, nullable support, nominal namespace, numericInf, actual encoded cardinality4097 с добавленным sentinel и malformed UTF8. Ровно4096actual bytes values принято. Empty Q/C выдаёт typed(0,15)/(0,3) arrays; повторный вызов после непустого результата заменяет все три output tables нулевыми, stale reference/provenance не остаются.

## Почему семантическая граница принята

- Source `[S,t)` и последний **глобальный** timestamp включают других users и весь tied bucket. NULL не отфильтровывается до resolver; older backoff отсутствует. CategoryID сравнивается с принятым005 ID/ambiguity/missing, а не только по наличию ключа.
- Цена/brand/code/category независимы. Brand/price missing означает отсутствие clean scalar, включая ambiguity; ambiguous subtype имеет обе flags1. Clean0/negative наблюдаемы: missing0, log=NULL, соответствующий flag1. `{0,NULL}` ambiguous и zero0. CategoryID0 и empty string metadata остаются наблюдаемыми значениями, без скрытой чистки.
- Code dictionary использует весь past prefix, не7d/current raw code и не future month. UnusableID/zero codes→code_missing, >1codes→code_ambiguous с code_missing0. Recovery известного dictionary при raw missing/ambiguous сохраняет raw state в provenance, не переписывает исходные события. First-known сверено независимо.
- Full R включает outsideC/current-category products и по одной строке на product; raw repetition не меняет вес. Lower7d endpoint включён; inactive valid candidate не вычитает себя. Category move меняет current R membership, а этот блок не изменяет historical005 numerator.
- Peer list oracle подтверждает unknown category→supportNULL, known empty→0, singleton→0, invalid own price/nonmember→полныйN и известный mean при peers, differenceNULL без valid own log. Собственный вклад вычитается только при фактическом R membership; NULL arithmetic не ломает invalid-price reference.
- Source nonfinite guard применяется к relevant latest bucket всех active7d products плюс fixed candidates, до positive/category filters. Более старое malformed значение и future-only suffix не влияют на выбранный snapshot. Это проверка feature snapshot, не новый source-wide audit.
- Fixed20-column schema/order содержит2keys+3nominal+15numeric. Loader выдаёт float32 expectedNaN+declared masks и object UTF8 bytes, отвергает Inf/flags/mask/conditional-state faults. Namespace `value:` защищает реальные строки `state:missing/state:ambiguous`; ID не превращается в numeric model input.

## Численная граница и стоимость review

Отдельная sensitivity цена1e−20 дала SQL`ln(1+p)=0`, Python`log1p(p)=1e−20`; это ожидаемая потеря малого при сложении с1. Она внутри объявленного absolute tolerance и вне положительной ценовой сетки принятого DECIMAL(12,2). Поэтому здесь нет blocking finding, но нельзя объявлять битовую/относительную точность для произвольно малых p или нового price-unit adapter. Тест с большим own price и маленьким peer дополнительно проверяет subtraction cancellation через direct peer mean. При изменении source units/precision нужна новая numeric gate; silently clipping не предлагается.

Independent harness выполнен дважды: второй запуск расширил проверку **всех** provenance fields/first-known и exact nonfinite failure reason. Оба завершились0; финальные counts выше относятся к одному полному финальному запуску, не искусственно сложены. Сумма двух measured harness wall≈2.1111s, user+system≈2.4393s; max processRSS123338752bytes. Финальный запуск: wall1.05184s/user1.108736s/system0.106379s. Отдельные15author tests имеют wall0.490s; их CPU counters не экспортировались, поэтому2.4393s не заявляется полным CPU всего review. Использовались2threads/128MB requested engine memory/no spill; это tiny evidence, не hard memory proof или прогноз42m scan.

## Что этот review не принимает

Spec gate100Q и helper max_pairs до6m имеют разные scopes: core поддерживает будущий bounded materialization, **runner обязан отдельно enforce**100Q/≤22000pairs/600s/RSS8GiB/spill2GiB, source/pin/code/selection provenance, immutable attempts и accounting. Runner ещё отсутствует. Passing cardinality check на tiny/100Q не доказывает full-train≤4096; проверяются actual encoded values полного будущего train input включая sentinels, отдельно effective one_hot settings и CTR evidence в уже разрешённом fit. Новый fit для проверки не выдаётся.

Нет acceptance source/cost/full exports/model quality/confirmation/final. Следующий полезный шаг — reviewed runner и настоящий заранее выбранный100Q/all-selected-pairs/full-R source gate. Mixed base41+15numeric+3nominal59 interface и один whole-block ablation с frozen smoke settings требуют своих проверок и approvals в существующем бюджете009.
