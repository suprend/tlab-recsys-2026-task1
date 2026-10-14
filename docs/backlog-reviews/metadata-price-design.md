# TLAB-009: один ограниченный блок metadata/price

Предложение после008 smoke. Реальные метаданные не рассчитаны, gain не измерен. Ownership реализации ещё не назначена. Один100Q cost/oracle gate, затем максимум один новый ablation fit внутри существующего бюджета009, после этого решение о составе сильного контроля замораживается. Не открывать дополнительную бесконечную сетку ручных блоков перед016.

## Входы и семантика

Принятые017 Q/Y/C/F, исходный typed DuckDB с fingerprint, исходный005 registry и новый immutable block spec. Точки t/семантика global read-before-update прежние. C/Y не меняются. На каждую пару сохраняются query_id/product_id; output — отдельный keyed addon, base artifacts/pins не переписываются. Признаки не читают labels; evaluation остаётся fullY.

Category ID, brand, price берутся из последнего ГЛОБАЛЬНОГО observed timestamp товара строго<t, рассматривая весь bucket всех пользователей и дублей. Поле clean, если все значения bucket ненулевые и совпадают. AllNULL = missing; known+NULL или несколько известных значений = ambiguous. Нет older-clean backoff. Поля проверяются независимо: цена может быть ambiguous при известной категории. Category ID обязан совпасть с базовым005. Наблюдаемая прошлая цена не объявляется фактическим текущим offer или признаком наличия товара.

Читаемую category code не восстанавливаем будущими месяцами или полным месяцем. Отдельный as-of dictionary category_id→set(named category_code), построенный из [S,t), даёт code только при единственном известном значении. Это отдельный provenance-preserving lookup по известному текущему category ID, а не переписывание raw/latest code. При двух известных кодах — ambiguous, при отсутствии — missing; исходные missing/ambiguity flags сохраняются. Реконструкция не гарантируется для каждого числового ID. Признак recovered отмечает, что dictionary дал код при отсутствии чистого соответствующего code в latest bucket.

## Три nominal поля

- category_id_nominal из чистого as-of ID;
- category_code_by_id из однозначного past dictionary;
- brand из чистого latest bucket.

UTF8 bytes с префиксом value: для значений и state:missing/state:ambiguous для sentinels, чтобы реальные строки не столкнулись с sentinel. IDs не передаются числом. Native one_hot_max_size=4096, фактическая train cardinality каждого поля<=4096; при превышении fail/review, никакого неявного targetCTR fallback. Model encoder fit только по train; unseen selection categories поддерживает native inference. FeaturesData: numeric float32 + object categorical bytes, explicitshape/type/null/finite validation у нашего кода, фиксированные names/order.

## Цена и относительный category reference

Valid price — единственная чистая p>0. log_price=log1p(p). Zero/negative/missing/ambiguous flags отдельные; не заменять неизвестное нулём и не вводить learned clipping без нового решения.

Reference population R_c(t): distinct products с событием [t−7d,t), чистой текущей категорией c и valid as-of price. Каждому продукту одна строка, независимо от количества views/users. Пусть z_j=log1p(p_j), N_c=|R_c|, A_c=Σz_j. Для товара i:

n_peer = N_c − 1[i∈R_c]
peer_mean = (A_c − 1[i∈R_c] z_i) / n_peer, если n_peer>0;
category_log_price_difference = z_i − peer_mean при известной цене/категории/reference.

Это разность log1p price относительно средней log1p цены других наблюдавшихся товаров категории; не арифметический price ratio и не независимая популяция impressions. Проверка membership обязательна, а не безусловный N−1. При неизвестной категории/null conditional key reference=NULL; support и missing flags явные. Mean log price выбран для bounded exact leave-one-out черезsum/count; median потребовал бы другой алгоритм и не добавляется молча. Direct-row oracle считает среднее списка других товаров, не повторяет algebraic subtraction.

Ориентировочный bounded output:3nominal +15numeric новых columns:2brand flags,3code flags,log_price+4price flags,peer_mean/support/difference+2missing flags. Existing category ambiguity/missing flags не дублировать. Точная схема/число колонок фиксируются после synthetic compiler/schema check. Это один block effect; выигрыш нельзя приписать одной цене или одному brand без дополнительных оплаченных ablations.

## Проверки и cost gate

Synthetic: latest global timestamp от другого пользователя; несколько peer rows/NULL mixtures; code dictionary конфликт и будущий suffix; price0/negative/missing; единственный/два reference products; membership включён/не включён; большие повторные event counts не меняют distinct-product reference; same-second/future rows не влияют на snapshot; product with category move; direct versus historical category semantics. Source oracle100Q на заранее label-independent subset с multiple days, все selectedpair metadata + category reference inputs/формулы проверяются независимым способом; exact C/addon key cover и schema/cost ledger.

Materialization partitioned per UTC day/shard, no Q×all-events crossproduct. Derived per-day product snapshots/shared category sum/count/dictionary; join only fixed C. Ограничения сначала100Q/<=22000pairs, CPU2threads,<=10minutes/RSS8GiB, временные файлы<=2GiB; при превышении остановка и reviewed redesign, не автоматическое расширение. Полные phase exports только после acceptance cost/source gate, исходные файлы не меняются.

Один ablation fit: тот же sampled train Q и selected smoke loss/settings (screening decision в selection ledger), те жеC/Y; base versus base+wholeblock, При предложенной схеме 41 числовой признак превращается в 56 числовых +3 категориальных (59); точное число подтверждается фактической схемой. Same fixed checkpoint50, external006 allselectionfullY; не nativeOD. Прирост/Recall tradeoff/CPU/RSS/unknown-category rates сообщаются, безconfirmatory claim. После этой проверки freeze feature set, затем отдельный prospective strong tuning grid и016. Confirmation/final labels не читаются.

## API-only evidence

15Oct2026, CatBoost1.2.10: [portable API proof](../experiments/metadata-price-api-proof.md) и [actual result](metadata-price-api-result.json). Tiny6rows/1numeric+3nominal, CPU2threads,2trees: Logloss и PairLogit работают через FeaturesData+Pool, one_hot_max4096, JSON splits OneHotFeature/noOnlineCtr, unseen-category raw predictions finite. Это synthetic interface check, не REES46 обучение и не доказательство выигрыша.

Primary sources: https://catboost.ai/docs/en/concepts/python-features-data__desc ; https://catboost.ai/docs/en/features/categorical-features . Документация требует own validation для FeaturesData и отделяет обычный PairLogit от CPU pairwise scoring objectives, где one-hot не поддерживается.


## Coordinator accepted semantic amendment — 15 октября 2026

[Independentdesignreview](metadata-price-design-review.md) changesrequested закрыты уточнениемниже; принят DESIGN дляsyntheticimplementation, неrealproduction/fit. Base008smoke сначала выполняется отдельно. Нельзя менять accepted005/008/017 helpers илиихpins радиblock.

Clean field означает все значения latestglobalbucket **NON-NULL** иравны. Price0 — clean observedvalue, ноinvalidpositiveprice; flags не сливаютего сmissing. SourceNaN/Inf в relevantasofsnapshot failclosed на этомanchor; future-onlysuffix не долженменятьpastoutput. ОжидаемыйnumericoutputNULL сериализуетсяNaN+declaredmask, не0; ±Inf послеfloat32cast запрещены.

LOO строгоpiecewise: member=1[i∈R]; removed=z_i еслиmember, иначе0 безвычисления0*NULL. n_peer=N−member; A_peer=A−removed. Unknowncategory→support/mean/differenceNULL; knownemptyR→support0/meanNULL; invalidownprice/nonmember сN>0→supportN иvalidpeermean, differenceNULL. Validmember singleton→support0/meanNULL/differenceNULL; validmember сpeer→N−1/peermean/z_i−peermean. R используетвсеdistinctactiveproducts7d внеC, currentclean category/positivefiniteprice, немероприятияповторно.

Exactly3nominal: category_id_nominal/category_code_by_id/brand, UTF8bytesnamespacevalue:/state:. Exactly15modelnumeric: brand_missing,brand_ambiguous; code_missing,code_ambiguous,code_recovered; log_price,price_missing,price_ambiguous,price_zero,price_negative; category_peer_log_price_mean,category_peer_product_support,category_log_price_difference,category_peer_mean_missing,category_price_difference_missing. ExistingcategoryIDflags остаютсяbase. Pricezero/negativeflags относятсяclean scalar; приambiguousprice они0. Mean/support могутбытьдоступныприinvalidownprice, differenceтребуетобеvalidстороны.

CodebyID — отдельнаяpastdictionaryrecovery, rawlatestcode не переписывается. CleanID+0namedcodes→code_missing;1→known;>1→code_ambiguous. UnusableID→code_missing сreasonвexistingbasecategoryflags. code_recovered=1 толькоеслиdictionaryknown, аrawlatestcode неcleanmatching; rawcode/resolutionstates сохраняютсявsource/provenance/verification, безобещаниядополнительных2modelnumericflags сверх15. Brand/code dictionary/sourcepolicy независимыотprice. Cardinality4096 проверяетсянаactualencodedtrainvalues включаяsentinels, noCTRfallback.

Все100Qselectedpairs иполнаяRreferencepopulation проверяютсяsourceoracle; knownempty/unknown/membership/invalidprice/futurepeer fixtures обязательны. Толькопослеcost/source acceptance полныйaddonexport; oneablationfit≤existing009cap требуетотдельногоapproval после008smoke. Noqualitygain claim.
