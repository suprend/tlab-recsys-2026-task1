# TLAB-009 full export: independent proposal review

15 октября2026. **ACCEPT направление для реализации; P0 уточнения ниже обязательны до freeze/execution decision.** Daily partitioning и exhaustive per-item oracle подходят. Это review проекта, не code acceptance или разрешение source execution/fit. Прочитаны proposal, accepted100Q audit/aggregate/archive, frozen009 core/spec и существующий008 collection gate. WIP metadata_price_collection.py/tests/doc не читались. Repo/Git/dependencies, actual artifacts/approvals не изменялись; real scans/fits отсутствуют.

## Основание и точная граница100Q

[Принятый audit](tlab009-100q-source-verification.md) относится к run `2f144cb2bcb7b5cf967edef95e51c55ac8803c90eebbb46c5f56dd2d76cdfd54`:100train Q,20586pairs×18=370548comparisons,20586provenance rows,1603114reference rows/13anchors. External record scope `reviewed_metadata_price_100q`, version1/approvedtrue,93pins:86identity inputs +executionapproval +4outputs +run/report. Producercomplete сам по себе не source acceptance.

Measured producer33,129459CPU seconds/oracle26,523796CPU seconds подтверждают небольшой diagnostic, но не full throughput.100Q brand/code/category cardinalities200/49/124 не удостоверяют full training vocabulary. Часть corner cases отсутствовала в actual sample, например price ambiguity/zero; synthetic contracts остаются необходимыми.

## P0: lineage и независимый scope

Full plan должен явно связывать два existing017 acceptance records, roles/ranges/sharedsource/base005, exact100Q accepted record и все его consumed93pins, immutable596f core/spec, новый module/helper bundle/runtime и выбранную output policy. Не принимать один run_id или producer-generated fingerprint map за review decision. Before/after rehash охватывает весь exact input/output scope, не только sourceDB. Новый external full-source decision появляется лишь после независимой проверки конкретных outputs.

008 `verify_collection` полезен как accepted mechanical gate: он проверяет hashes/manifests, не парсит label Parquet. Дополнение EXACT14 shard approval должно выводить обязательный map из actual verified am/cm source/code/input maps и physical seals, включая query_coverage, и проверять keys/values; F inputs — derived map +approval SHA+registry+selection. Нельзя снова определять required inputs из самого approval. Проверять CR/FR upstream IDs. Hashing уже accepted Y допустим для lineage; запрещены SQL views/fetch/query label values, model sampling через prepare_dataset и скрытая label-dependent selection.

Project-root/path confinement, symlink escape и loaded-helper digest binding нужны также при relocation. Читать pinned artifact JSON как данные, не загружать supplied modules. Runtime DuckDB/NumPy и schema semantics должны соответствовать зафиксированному окружению; input pin не удостоверяет фактически импортированный другой helper.

## P0: точный daily cover и exhaustive broadcast

Anchor schedule выводить из accepted phase/Q, а не только DISTINCT anchor экспортированного F. Для каждого дня фиксировать Q identities/count, expected C multiplicity, addon/provenance/reference refs и status;2000Q/440000pairs/22000unique(anchor,item) — самостоятельные caps.13train+2selection days и5317058+817149=6134207addon rows — expected counts, не достаточное доказательство cover. Unique/orphan/bidirectional keyed equality необходимы. Mature zeroY и emptyC Q сохраняются в population; для calendar day безQ нужен явный declared empty-day outcome, не исчезновение из отчёта.

Independent unique item domain строить **из accepted C JOIN accepted Q**, не из producer export. На каждом(anchor,item) oracle заново разрешает latest global all-user/all-tie bucket и отдельный past dictionary, строит полный active R вне C, затем explicit excluded-self peer list с math.fsum. Кэшировать scalar expected tuple, не все peer lists. Стоимость порядка Σanchor,category |unique_candidates|×|R_category| остаётся реальной;100Q успех не гарантирует30CPUmin.

Expected tuple далее broadcast к **каждому** accepted(query_id,product_id), с anchor из Q. Сравнить каждую физическую addon/provenance строку, а не representative и не DISTINCT producer values. Так один повреждённый duplicate-product ряд у другого пользователя будет найден. Exact row counts/keys/schema/order/types/nominal/flags/NULL masks; finite numeric comparison с absolute1e−12/relative1e−9. Полный provenance проверяется отдельно, включая dictionary first-known/latest states; fullR — exact membership/category/logprice, не лишь candidate categories. Этот chain действительно делает addon proof exhaustive без6m Python rows.

Whole20column addon означает2keys+18model fields, а не20новых inputs. Numeric NULL→NaN разрешён только при правильном mask, ±Inf/float32 overflow запрещены. Source NaN/Inf в relevant latest bucket активных продуктов/кандидатов failclosed доpositive filter; future и невыбранные старые bad buckets не создают ложный отказ. Known0/negative, ambiguous, unknown category, knownempty R и invalid own price остаются различными states.

## P0: cardinality и общий CPU cap

Exact per-item invariance **всех18model values** доказывает возможность валидировать float32/UTF8/masks на unique projection; наличие одного случайного representative этого не доказывает. Validate state/value namespace и sentinels, затем полную train union cardinality по encoded значениям, не maximum отдельных дней. Selection unseen bytes допустимы; test vocabulary не превращать в training encoder.

Фраза proposal «fulltrain4096decision» требует уточнения: full26000 cardinality — diagnostic/будущий019population gate. Она не должна автоматически отвергать whole009block, если eventual6000ablation encoded train≤4096. Canonical retention зависит именно от6000mixedfit gates; при excess26000 будущий019может использовать заранее объявленный6000fallback. Ни CTR fallback, ни бесплатный новый fit не разрешены. Full export с корректными значениями и oversize vocabulary должен иметь честный diagnostic status, не ложную model acceptance.

Producer≤1200wall и2threads **не обеспечивают** combined≤1800actualCPU seconds. Нужен единый budget identity/ledger до подготовки, runtime user+system guards у producer/oracle и явный oracle deadline/остаток. Все pin preparation, schema/encoding checks, output/readback, source audit, failed attempts и cleanup оплачиваются; nested inclusive stages не суммировать. Если oracle не помещается, output остаётся unreviewed и scope failed/deferred, без overtime/refill. RSS8GiB/spill2GiB проверяются суммарно в процессе; отдельные2GB engine connections не дают hardRSS guarantee. Final guards после close/counters/manifest-report serialization/auditwrite и доsuccessreturn обязательны; late error сохраняет failed partials.

## Следующий отдельный gate

Full codefreeze/tiny corruption/resource review→exact executionapproval→daily export→independent exhaustive source/cost acceptance. Только затем новый model_data/ablation code review и exact ONE atomic fit decision.6000base arrays/groups/items/y должны совпасть с008;4000selection/fullY/C и006 evaluator неизменны,15numeric+3nominal добавляются целым блоком.50trees/settings/weights/noOD/noCTR проверяются на actual model, failure consumes fit. Retention уже prospectively frozen: Recall≥.5792133072407045 иNDCG>.41444755081727774+1e−12 плюс все integrity/gates; tie→base. Этот point-estimate screening не является promotion или superiority proof.019/016executionbudget не открывается автоматически данным review.
