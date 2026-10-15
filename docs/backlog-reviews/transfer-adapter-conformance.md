# Transfer adapter conformance: одинаковые columns не сохраняют задачу

15 октября2026. Primary-source/documentation research, без raw data/downloads, native APIs, models, fits, SQL/tests, heldout Y или code/backlog/Git changes. Дедуп rounds040/052/068/070/073/074 и future-label reservation: прежние notes уже задают EventFact/PropertyState/Query roles, cache/vocabulary identity и November caveats. Здесь конкретное дополнение — **feature-value compatibility, protocol compatibility и access compatibility проверяются отдельно**. Passing одного уровня не удостоверяет остальные. Никакой текущий016 contract не расширяется.

## Проверенные первичные основания

[Woodwork0.31.0](https://woodwork.alteryx.com/en/stable/guides/logical_types_and_semantic_tags.html) различает logical type и tags; primary index уникален, стандартные tags убираются. Существенная API деталь: selector `ColumnSchema(Integer)` без требования numeric tag всё равно может выбрать integer index. Следовательно, nominal-ID запрет должен задаваться role/operator contract, а не надеждой на numeric-tag removal.

[Featuretools1.31 Handling Time](https://docs.featuretools.com/en/stable/getting_started/handling_time.html) определяет time index как момент знания строки, secondary index — позднее знание fields. `include_cutoff_time=False` в documented window включает lower boundary и исключает cutoff; default temporal API нельзя приравнять нашему strict<T без явной настройки. [Feast PIT](https://docs.feast.dev/getting-started/concepts/point-in-time-joins) по умолчанию ограничивает event timestamp, допускает поздний backfill; opt-in created filter добавляет created≤entity timestamp. NULL created исключается, неподдерживающий store должен raise error. Это другой explicit API contract, не установленная у нас feature-store implementation и не автоматическая strict-global-peer гарантия.

[Retailrocket publisher card](https://www.kaggle.com/retailrocket/ecommerce-dataset/home), прочитанная через индексированный publisher text, описывает behavior events view/addtocart/transaction и отдельные timestamped item properties из weekly snapshots; actual files не обследованы. [Official MIND format](https://raw.githubusercontent.com/msnews/msnews.github.io/master/assets/doc/introduction.md) содержит impression-time, ordered history IDs и displayed candidate IDs вместе с click1/nonclick0; impression order shuffled, individual history-click times не предоставлены в этой relation. MIND — намеренно контрастный news task, не предлагаемый здесь новый e-commerce benchmark. Эти primary facts показывают, почему похожая tuple(user,item,time) не устанавливает одинаковый target или observation process.

## Минимальный contract: обязательства, а не новый framework

Existing source/adapter identity должна объявлять пять вещей: роль каждой relation и countable bag; exact entity namespaces/keys и multiplicity; отдельные history/query-context/label clocks; predicate domains Q/C/F/Y с source coverage/maturity; разрешённые consumers и момент target opening. Дополнительно фиксируются metadata grain/tie/NULL, fitted dependencies, physical schema и lineage. Ни имя колонки, ни inferred FK, ни sample uniqueness не являются бизнес-доказательством.

**Новый важный clock distinction:** logged C, известный при самом запросеT, может быть законным query context в impression task, пока behavioral features используют события<T. Принудительно фильтровать такой C по нашему prior-observed U(T) — изменение задачи. Обратно, разрешение query context наT не позволяет потреблять глобальные behavioral peersT в counts. Нынешний REES C целиком past-only; это различие требует нового protocol, не ослабления accepted001/004.

| Несовместимость | Что adapter обязан reject/fail closed | Какой более узкий claim возможен |
|---|---|---|
| View, impression и property revision смешаны | Выдавать property update за view или view за logged exposure | Count только explicitly declared business-event bag |
| Click-only source предлагается purchase target | Fabricated purchase0/full-horizon Y из click labels | Новый click/impression protocol, не REES purchase replication |
| Logged slate против past-generated C | Скрытый past-catalog filtering/positive insertion | Explicit source-local C и его own target support |
| Available time неизвестно либо late correction | Strict-knowledge claim без annotation; silent event-time fallback | Заранее declared offline event-time assumption с новой identity |
| Unknown action token | Игнорирование только в F при неявном изменении Q/U/recent/metadata | Полный declared token domain каждой relation, включая excluded tokens |
| Integer key/ID reuse/session namespace | Arithmetic по nominal keys, float-rounded IDs, необоснованный cross-month join | Exact keys и explicit identity/reset assumption |
| Embedded category против property changelog | Whole-file/latest-known backfill или join fanout | Separate historical/current resolver semantics; noncategory subset transfer |
| Нет channel/coverage против пустого окна | Unsupported view→known0; incomplete horizon→negative | Rejection либо observed-part count+coverage; censored Y отдельно |
| Packed candidate+label field | Passing label-bearing raw context в blind inference; fake-zeroY shim | Trusted de-label extraction/escrow с явно ограниченной blindness claim |
| Learned/cache lifecycle | Shape/name equality вместо approved versions/complete evidence | Exact version-bound reuse;073/074 detailed gates без новых fits |

Fail-closed не означает запрет всякого исследования при неизвестном ingestion clock. Это запрет **автоматического** перехода от strict knowledge claim к более слабому assumed-event-time режиму. Человек может заранее выбрать второй как отдельный policy; row-by-row fallback или выбор policy после качества недопустимы. Unsupported capability отличается от known empty, conditional unknown и partial coverage.

## Один source-free literal suite:23 input rows, пока только спецификация

Положим source S=T−10d, complete_end≥T+24h, H24/delay0; у всех обычных events availability=event_time. EventFact9rows:

1–2. Exact duplicate A/cart/X вT−24h, attached categoryA.
3. A/view/X ровноT.
4. B/view/X вT−1h, available толькоT+1h.
5. A/purchase/Y вT+1h.
6. C/view/Z вT−2h, category unknown.
7. D/remove_from_cart/W вT−1h.
8. B/cart/Y вT−8d.
9. A/view/X вT−26h, category unknown.

PropertyState5rows: X/categoryA вT−25h; X/categoryB иNULL в одном bucketT−30min; Y/categoryA вT+30min; Y/brandB с valid timeT−1h, availableT+1h. Query4rows дляA/B/C/D вT; C4rows — соответственноX/Y/Z/W. Последняя input row — **отдельный impression-task variant** U5/T с packed slate `N1-1 N2-0`, не event/action для REES. Всего9+5+4+4+1=23. Это общий literal bag для раздельных positive/negative cases, не обещание одного безусловно допустимого end-to-end input. Q здесь задан внешним synthetic schedule; он не объявлен автоматически прошедшим REES active48h eligibility. Numeric cases заранее объявляют remove token как raw-only/excluded из feature-event domain; вариант без такой annotation обязан reject целиком. Если отдельный case требует knowledge-based active48h Q, B без доступного recent event и D с excluded-only event должны быть отвергнуты на domain gate, а не сохранены ради recency demonstration. Schema variants/ID renaming не добавляют source rows; все IDs synthetic.

Literal expected obligations:

- A/X cart-count24=2 на inclusive lower boundary; distinct cart users=1. Source view ровноT исключён для всех query histories; late B/view исключён при knowledge clock, даже при event_time<T.
- B/Y cart-count168=0, observed recency691200s, missing=false. C/Z noncategory view-count24=1, category-conditioned valueNULL; отсутствие view capability в manifest должно reject тот же requested view AST, а не менять1 на0.
- Property rows не увеличивают business counts. При property policy X current category unknown из B+NULL, без olderA backoff; historical category двух cart eventsA. При canonical embedded005 latest past cart bucket categoryA остаётсяA: это правильное различие источников информации, не adapter failure от несовпавших categories.
- Y/category иbrand ещё недоступны. Полученная после old view PropertyA не backfills его неизвестную historical category. FullY дляA содержитY внеC; target не вставляется кX. Q сохраняются при отдельной empty-C mutation; horizon_end без coverage доказательства не превращает query в mature.
- remove token без relation-wide policy останавливает conformance до eligibility/C/F: ignored-count predicate недостаточен. Exact ID rename X→2^60+1 сохраняет значения/key distinction; nullable integer transport не допускает округления. Requested arithmetic над ID отвергается по role, не только по dtype.
- Impression variant допускает N1/N2 как declared logged query context даже без past EventFact. Click label не является purchase; requested daily-purchase/fullY contract отвергается. Trusted extractor может выдать unlabeled C и закрытый label payload, но inference consumer не получает raw `-1/-0` strings. Это не claim «во всей системе никто не прочитал label bytes».

Expected tables/negative outcomes составляются независимо от compiler/resolvers. Metamorphics — peer permutation, future suffix при фиксированном context, добавление property revision без business event, label-bit mutation после trusted extraction — дополняют gold, не доказывают абсолютную правильность. Duplicate mutation меняет raw counts, не distinct; нельзя обещать invariance всей модели. Никакой test сейчас не исполнен и новый бюджет не предоставлен.

## Как подписать portability result и где остановиться

Успешный будущий suite подтвердит заявленные adapter mechanics/negative-capability handling на23rows. Он не докажет реальные PK/FK, timestamp units/availability/completeness, ID permanence, source scale, quality, stock/exposure, causal lift или совместимость всегоB41. Для real source нужны отдельные bounded source/lineage/resource gates; для quality — source-local model/target/C/calendar contract, reservation и оплаченные fits/looks. MIND slate и REES full future purchases нельзя сравнивать как один estimator даже при одинаковом NDCG названием.

Честная текущая формулировка: «Поддержан ограниченный canonical schema/template contract; primary-source compatibility analysis выявляет необходимые adapters и отказные случаи. Cross-dataset implementation и predictive transfer не выполнены». После literal suite можно добавить «conformance подтверждён на synthetic witnesses», не «метод обобщается на любые ecommerce данные».

Это refinement существующих HYP002/005/016/018 и014; не новая task/HYP. Cache/vocab детали остаются073/074, month carryover — отдельной future-label note. Приоритет прежний: закончить accepted нынешний experiment/reproduction/report; не расширять operators, текущий legal pool, selector, fits, heldout policy или бюджет ради portability текста.


## Publication scope appendix — 15 October 2026

Original SHA256 4998d2f610740f6d227f78a279bd1c2f9d221658700259e487c606d81e4b5e2d. The historical README wording discrepancy is corrected in this local publication. Source/metric/prediction code acceptance remains distinct from actual reserved-period execution, which has not occurred. Local accepted development evidence is versioned; external upload remains pending direct human destination consent. No new task, fit, data download, resource allowance or target-opening grant follows from this research note.
