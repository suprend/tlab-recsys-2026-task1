# Волна101 — независимый скептик

**NEW0 / REFINE2 / MERGE2 / REJECT_PROPOSALS0 / scientific ADMIT0.** REFINE и MERGE — те же два предложения, не четыре результата. A сохранить как узкое SOURCE-уточнение fusion11; B объединить с уже отложенным influence consumer099, максимум добавив фиксированный срез300. Ни нового HYP, ни runtime admission, ни обязательной задачи/gate не следует. Root — единственный coordinator/canonical writer/publisher.

Первое clock-наблюдение скептика **2026-10-17 10:36:03 UTC**, не process start. Root dispatch был наблюдён10:30:00UTC; авторские FIRST заморожены после due10:30: A10:33:48, B clock непосредственно перед freeze10:34:54. Индивидуальные starts UNKNOWN; это обычная работа после dispatch, не основание считать wave просроченной с начала или сдвигать сетку. **Следующий исходный due11:15UTC /14:15МСК**,45 минут. Deadline25October23:59, timezoneUNKNOWN.

## Проверенные входы и степень независимости

Оба FIRST прочитаны полностью после проверки всех шести переданных SHA256 FIRST/pins/freeze. Все совпали. Все **46 уникальных локальных source/instruction pins** из объединения A/B пересчитаны; все совпали при HEAD `28078c092a862b076f304c27bbd90df7d61bdb26`, Git status clean. Хеш не равен полному прочтению: actual extracts указаны в pins. Проектные AGENTS.md/CLAUDE.md отсутствуют; применены suppliedAGENTS, research-campaign/research и coordination.

Отдельный read-only helper, не автор101, проверил079/099 dedup. Его выводы перепроверены моим чтением actual079 embeddedFIRST/skeptic,099FIRST/skeptic/inventory/synthesis и принятых seed aggregate docs. Helper ничего не писал; текущие101FIRST он не читал. Авторам не предлагалось менять FIRST. Независимость FIRST — их attestation плюс фактическая последовательность freeze/read, не внешнее доказательство отсутствия всех контактов.

| Предложение | Disposition и canonical seam | Минимальная полезная граница |
|---|---|---|
| A101-F1 exact-copy RRF placebo | REFINE/MERGE [fusion11](/Users/mdpospelov/tlab-recsys-2026/docs/candidate-generation/11-fusion.md:21), [review09–12](/Users/mdpospelov/tlab-recsys-2026/docs/candidate-generation/review-09-12.md:27), TLAB-004/014; HYP-061 только контекст | Документировать разницу нового output information и изменения веса. Только если fusion вообще выбран; quality и новые источники не установлены. |
| B101-1 fixed300 joint influence | REFINE/MERGE HYP-002/TLAB-013/014/016/019, прежде всего [099A](/Users/mdpospelov/tlab-recsys-2026/docs/research-lab/archives/wave099/originals/tlab-wave099-A-FIRST.md:17); оставить deferred | Уточнить описание finite reversal, если оно меняет конкретный текст/решение. Новый score consumer здесь не нужен для принятого отрицательного результата. |

## A: корректный аналитический контроль, малая новизна

В actual fusion11 уже задан weighted source-sum `sum w_s/(60+rank_s)`, предупреждение о repeated popularity votes и edge case полностью совпавших источников (L25–29,45). Review09–12 L29–33 уже требует один pre-fusionpool/depth и прямо допускает удвоенный голос без новой информации. RB001 L51–53 уже отделяет duplicate routing от discovery и допускает полезную концентрацию duplicates. Поэтому общий механизм **не новый**. Узкая добавка — signed exact-copy witness и сохранение массы известной provenance-группы, а не очередной retriever или правило схлопывать коррелированные каналы.

[Первичная RRF-статья Cormack–Clarke–Büttcher2009](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf), Eq.1/Discussion, подтверждает rank-sum и исходный k60. Прочитан полный извлечённый текст2pp; raw PDF не скачивался. Следующие тождества — собственная алгебра по объявленному локальному sum по именованным каналам, а не эмпирическое утверждение paper:

- Для A=(a,b,c), B=(b,c,a), F=RRF(A,B): `F(b)-F(a)=1/(62·63)>0`; b — top1.
- Для F'=RRF(A,A,B): `F'(a)-F'(b)=2/(61·62·63)>0`; a — top1. Сравнение с c тоже положительно; все3 исходных ID и finalsize1 неизменны.
- Разделение исходного веса A на две половины восстанавливает исходный score каждого item в точной арифметике. Это не признак независимости и не доказательство бесполезности исходного A.

Контргипотеза автора верна: больший вес хорошего сигнала может быть полезен; count/cosine не exact aliases, совпадение выходов разных retrievers не даёт права автоматически их схлопнуть. Низкий overlap, tail-share или одинаковый finalsize сами по себе не доказывают нового полезного сигнала. Группу ограничить объявленной derivation/config/cutoff/depth identity и точным ordered output. Exact score identity — математический oracle; будущую floating implementation нельзя оценивать как новый информационный механизм по одной ошибке округления/порядку суммирования.

**Попытка независимого tiny literal check — FAILED до арифметики.** Одна stdlib-only команда намеревалась проверить только4 literal fusion calls с пределом2CPU/5wall/64MiB. После установки CPU limit macOS отверг `RLIMIT_AS` с `ValueError: current limit exceeds maximum limit`; вызовы fuse, assert и чтение данных не начались. `/usr/bin/time` напечатал real0.03/user0.02/sys0.00, затем `sysctl kern.clockrate: Operation not permitted`; это неполный профиль, RSSUNKNOWN. Retry0. Отсутствует выполненный PASS: математическая проверка выше ручная, весь author gate остаётся UNRUN. Инфраструктурная ошибка не опровергает тождества и не принимается как test success. Файлов попытки не создано.

Предложенные автором5CPU/10wall/128MiB — только будущие потолки, не текущий grant/measurement. Моё разрешение на меньший tiny check не переносится на этот gate. Польза Task1 ограничена честной атрибуцией возможного fusion; никакого нового обязательного контроля перед существующим фиксированным B/W сравнением.

## B: существенный dedup099; fixed300 не делает consumer бесплатным

В099A L19–29 уже есть совместные d(seed,q), разность e(q), explicit-zero sign table, все complete-user deletions, четыре aggregate parity checks, descriptive concentration и запрет искать спасительные deletion subsets. [Skeptic099 L15–21](/Users/mdpospelov/tlab-recsys-2026/docs/research-lab/archives/wave099/originals/tlab-wave099-skeptic-v1.md:15) уже принимает это как разложение вклада, не causal attribution. Wave056B L8–14 ещё раньше задаёт query-influence;061B — fixed-score descriptive perturbations. [079 embeddedFIRST L138–146](/Users/mdpospelov/tlab-recsys-2026/docs/research-lab/round079-engineering-checkpoint.md:138) сохраняет reused73Q/2400dependent checks и отсутствие нового обязательного comparison. Это более прямой dedup, чем указанная автором101 только098/056/061 цепочка.

Реальный delta101B — **фиксированный prefix300 тех же1200-tree fits**, точная3×3 sign table и сохранение всех73 результатов вместо прежних extrema. Здесь73positiveQ принадлежат73positiveusers по принятому [seed-result L5,14](/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/seed-replication-results.md:5), поэтому одно positive-query deletion равно complete-positive-user deletion в этой популяции; будущий consumer должен сохранить/проверить relation. Это output/slice refinement, не новый метод и не независимая проверка качества.

Аналитический four-query witness автора внутренне корректен: seed2027 B mean=.625, W mean=.525 в обоих мирах; D=-.1. Seed2026 D=.2. Совместно положительных d —3 против0; single-deletion flip —1 против0. Counts32cells/16effects/4aggregateD/16deletionD/two3×3tables согласованы. Ни один fictional row не является фактическим score/NDCG наблюдением либо доказанно достижимой CatBoost реализацией; здесь pilot не выполнялся.

Новый falsifier намеренно очень узок. Из принятого D300,2027=-.012554918159806916 и N=73 следует `sum d≈-.916509025665905`. Чтобы удалить один query и получить положительный mean, его d должен быть ниже примерно **−.916509026** (с поправкой1e−12 band). Это почти полный провал W относительно B по одному query. Неуспех отвергает только такую single-query версию; ни broad harm, ни отсутствие нескольких influential queries не следует. Автор это ограничивает корректно; не расширять поиск subsets после неудачи.

[099 inventory L3–9](/Users/mdpospelov/tlab-recsys-2026/docs/research-lab/archives/wave099/originals/tlab-wave099-A-score-metadata-inventory-v1.md:3) установил metadata существования **selected-prefix** B1189/W403 и B98/W134 векторов, не300. Свежие body hashes/schema/key/fullY alignmentUNKNOWN. [Seed results L16–25](/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/seed-replication-results.md:16) берёт common-k aggregates из кривых; агрегаты не восстанавливают query contributions. Этот bounded docs-pass не доказывает глобальное отсутствие300-векторов. Если их нет в authenticated closure,101B честно требует **4loads/4new full prefix predictions/3,268,596 score values**, не0prediction consumer099. No-fit не равно no-score; новый native путь не разрешается заменой названия.

Для любого будущего consumer до интерпретации сверять **четыре абсолютных** исходных300метрики с accepted fullprecision reference, не только rounded contrast: B2026=.4586107284411232; W2026=.46470287738416133; B2027=.44058213152131637; W2027=.42802721336150945. Это actual public aggregate JSON L55–79, не прочитанные model/score bodies. Один лишь rounded +.006092/−.012555 parity может скрыть одинаковое смещение обоих arms. Затем fullY/off-C/empty-C/ties/query-macro и292 contribution cells/146 deletionD. Сохранённые contributions позволяют независимо проверить **арифметику диагностики**; они не дают самостоятельной проверки корректности новых score→rank→fullY contribution вычислений. Автор честно ограничивает обещание independent replay именно арифметикой; не повышать его до native parity claim.

300CPU/600wall/12GiB/128MiB — prospective all-in limits, adequacyUNKNOWN. Исторический verifier с4loads/predictions показывает осуществимость прежнего другого closure, не гарантирует этот cap, доступность300векторов или независимость результата. При отсутствии конкретного потребителя текста оставить B deferred. Existing099 selected-score вариант потенциально дешевле, но тожеUNRUN и ещё не body-authenticated; здесь не предлагается запускать ни один.

## Решение для исходной Task1 и границы состояния

[Проверенные требования Task1 L5–12](/Users/mdpospelov/tlab-recsys-2026/docs/task1-requirements.md:5) требуют рабочую автоматизацию/альтернативу и измеренное сравнение с сильным boosting. A/B101 не устанавливают её превосходство и не отменяют имеющийся работающий ограниченный конструктор8bundles B41/W44. Умеренная польза A — не назвать смену веса новым сигналом; польза B — при действительном потребителе точнее описать уже отрицательный finite результат. Это не основание для третьего seed, CV, нового final, ещё одной retriever-серии или задержки исходного отчёта.

Прочитанные accepted docs сохраняют14/19,014continuous,010–013optional; frozen final B.459825/W.464947 и CIcross0. Seed2027 отрицателен на тех же73positive developmentQ; matched300 тех же1200fit не равен историческому frozen300final. CURRENT15 byte equality относится к той же processedDB, не к свежему raw/formula oracle.

На последнем canonical checkpoint Q1009904 завершён, runtime ещё не принят. Более свежий Root handoff сообщает resourceauditPASS/correctnessINCOMPLETE после двух harness failures и pending correctedV3; эти actual runtime receipts я не инспектировал. Приоритет — закончить уже идущую correctness-проверку, учитывая обе неудачи. **Q100 не даёт quality gain;6000 остаётся SOURCE-preparation/0admission.** A/B не создают новых prerequisites к этой проверке.

REJECT_PROPOSALS0 не означает принять дополнительные claims: нельзя объявить copied channel независимым сигналом, exact-copy invariant — доказательством purchase utility, single-deletion отрицание — broad harm, либо два seeds — seed distribution/свежей confirmation. Ни один из этих claims сами FIRST не требуют. Scientific ADMIT0 остаётся независимо от SOURCE-пригодности уточнений.

## Scope и остановка

Прочитаны plain-text docs/instructions, public scalar JSON, хеши и read-only Git status; внешний доступ — только2pp primary RRF PDF через извлечённый webтекст. Cawley/TimeSeriesSplit у B здесь заново не проверялись, новых выводов по ним не делается. Broad search и часть batched output были truncated; decisive excerpts перечитаны отдельно. Нет exhaustive novelty proof по всем100волнам; ни хеш46источников, ни helper report не подменяют полное чтение.

DB/Q/C/Y/Parquet/NPZ/model bodies/downloads/projectimports/SQL/projecttests/fit/score/native calls0; canonical/Git/network mutations0. Единственная tiny arithmetic attempt не дошла до fusion; failure/cost limitations сохранены выше. Только три назначенных /tmp артефакта; после проверки readback/hash — **FROZEN_STOP**. Root единолично решает интеграцию; авторам FIRST менять не надо.
