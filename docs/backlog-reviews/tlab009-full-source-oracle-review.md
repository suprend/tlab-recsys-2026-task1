# Full009 independent source-oracle transport review

15 октября2026. **CHANGES_REQUESTED: один доказанный P1 в expected-value transport.** Проверена неизменённая `tlab009-verify-full-source.py`, SHA256 `d76ccb8925d433c64da01e4fc980a79efd83fe22d5ce297c2252ff320fe3ae35`, и accepted metadata_source.py/metadata_price.py. Root WIP/full tests не импортировались, E2E не повторялся, source/fulloutputs/models/targets не читались. Код oracle не менялся, acceptance не создавалась.

## P1: nullable BIGINT превращается в float до SQLCAST

`install_expected` сначала создаёт обычный pandas DataFrame из Python rows, затем CAST-ит зарегистрированные columns в declared SQL types. Если category_id содержит integer иNone, pandas может вывести float64. Для больших ID это уже необратимая потеря точности: последующий CAST AS BIGINT не восстанавливает исходный integer.

Независимый AST-only repro извлёк **дословные** need/install_expected/compare_broadcast definitions, импортируя только pandas/DuckDB и standard library. В expected rows `[[1,1152921504606846977],[2,None]]` SQL expected table получила `1152921504606846976`. Physical row с правильнымID…6977 отвергается; строка с неверным округлённымID…6976 **принимается**. Поэтому это не просто ложный отказ: transport допускает false acceptance повреждённого exact nominal/category provenance. Core resolver/direct-peer-list math к этому не относится и не изменялся.

Actual REES outcome этим опытом не диагностируется. Даже если конкретный день не содержитnullable category, declared mixed-NULL/global-bucket contract и большие BIGINT IDs должны совместно работать. Маленькие IDs и здоровый tiny E2E не закрывают этот defect.

Исправление: построить **явно typed Series из исходных Python values до DataFrame inference**: nullable Int64 дляBIGINT, boolean дляBOOLEAN, string дляVARCHAR, Float64 дляDOUBLE, declared datetime дляTIMESTAMP. Нельзя сначала создать float-backed DataFrame и лишь затем astype(Int64). Проверять exact SQL roundtrip больших nullable IDs, NULL и boundary int64; правильныйID должен пройти, соседнийroundedID — отказать. Numeric tolerance не применяется к BIGINT. Root producer files и accepted core исправлять для этого не требуется.

Helper `tlab009-full-oracle-independent-transport.py`; evidence `tlab009-full-oracle-independent-transport-results.json`.6isolated cases, measured0,011804s wall/0,012583s processCPU/99844096bytes peakRSS,0fits/0real source reads. Healthy broadcast проходит; одна плохая duplicate copy и неверныйNULL независимо отвергаются. Три BIGINT observations выше — failure evidence, не passed checks.

## Что принято по static review

Expected domain строится из accepted base_q/base_f, filtered по настоящему phase anchor. Producer queries сравниваются со всем expected Q; addon/provenance — с accepted pair multiset и unique keys. Products для source oracle берутся из accepted pairs, а не из producer representatives. Каждый distinct(anchor,item) имеет один independently resolved expected tuple, затем SQL join/product comparison проверяет **каждую физическую строку**. Ошибка одной копии у другого query не теряется вDISTINCT.

NULL masks/nominal/BOOLEAN/BIGINT сравниваются через IS DISTINCT FROM, finite DOUBLE — absolute1e−12/relative1e−9. До broadcast проверка key multiset устраняет unmatched rows, которые standalone inner join мог бы пропустить. FullR сравнивается целиком поanchor/product/domain/category/logprice, отдельно отC. Independent helper собирает все global ties, dictionarypast отдельно, и считает peermean прямым excluded-self list/math.fsum. Production resolver/sum-minus-self не являются expected values.

Calendar day cover берётся из accepted phase. При Q>0/emptyC всё равно строится full activeR; при Q=0 expectedR объявляется пустым, typed empty expected model/provenance допустимы. Это согласуется с текущим producer calendar-empty policy. Из статического кода не следует actual full source acceptance; опубликованные280rows/5040values tiny evidence прочитаны как прошлый coordinator result, не повторены и не засчитаны собственным запуском.

## Ограниченные transport/resource уточнения

P2: до hashing outputs стоит явно потребовать ровноtrain/selection и four artifact keys queries/features/provenance/reference. Сейчас лишний manifest phase попадает вall_output_pins, но loop collections не проверяет его values; missing keys обычно падают позже. Это static observation, не новый выполненный fault. Внешняя full-code mechanics должна также быть исправлена по отдельному Root review; source formulas не заменяют exact accepted100/input/approval lineage.

P2: `timer.cancel()` вfinally не защищён first-error collector и может пропустить connection.close/failed evidence, если сама cancellation бросит exception. Close/guard/write failures уже собираются с сохранением primary; cancellation следует провести тем же путём. Для portability RSS units должны быть explicit: native ru_maxrss на текущем macOS измеряется вbytes, Linux возвращаетKiB. Не считать этот script уже проверенным наLinux.

900actualCPU/1200wall guards используют process_time иmonotonic, охватывают independent source reads, direct peer loops, before/after pin rehash, cleanup и финальную auditwrite проверку. Source attachedREAD_ONLY, DuckDBthreads2;2GB buffer/spill неhardRSS. Report CPU измеряет run-body delta после imports; общий009ledger должен дополнительно учитывать process setup/import и минимальный final persistence/stdout tail через whole-invocation measurement. Failed run не создаёт approval и не запускаетretry.

После typed-Series fix нужна новая SHA и targeted повтор exact BIGINT mutants/NULL/one-bad-copy/empty cases. Разрешение actual full oracle отдельно зависит от принятого Root producer fix, exact plan/execution approval и общего900+900CPU budget. До этого источник истины — правильные независимые Python integers, а текущий pandas transport ещё не обеспечивает их сохранение.
