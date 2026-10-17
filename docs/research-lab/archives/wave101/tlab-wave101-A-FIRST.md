# Волна 101 A — placebo копии канала перед новым fusion

**FIRST / SOURCE-only / независимый автор A. NEW 0 / REFINE 1 / scientific ADMIT 0.** Уточнение существующего `docs/candidate-generation/11-fusion.md` и его review09–12, связанное с HYP-061 и TLAB-004/014. Это не формулировка зарезервированной HYP-087/088, не новый retriever и не новая обязательная задача. Root остаётся единственным координатором, canonical writer и Git publisher.

Исходный due **2026-10-17 10:30 UTC**, next_due **11:15 UTC / 14:15 МСК**, фиксированная сетка45min; deadline25Oct23:59, timezoneUNKNOWN. Clock observation10:32:30UTC — наблюдение текущего времени, не восстановленный индивидуальный start. Все предлагаемые ниже проверки **UNRUN**, фактические cost/adequacyUNKNOWN.

## Текущая граница решения

Состояние передано Root: работает rule-based конструктор8bundles B41/W44;14/19accepted,014ongoing,010–013optional. Frozen final B0.459825/W0.464947 с CIcross0; seed2027 отрицателен на тех же73positive developmentQ, не свежий final. Категории93/121 против92/121 inconclusive, C0сохраняется. CURRENT15 дал75byteequal файлов той жеDB. HYP-061Q100 original9904 закончен exit0,63nonempty и54differentsets — переданные metadata; correctnessINCOMPLETE из-за harnessps/WAL, resourceauditPASS,0Y/ML. Эти сведения не проверялись мной по actual outputs, не означают ни quality gain, ни production failure и не создают повод для freshfinal/CV/нового seed. Frozen6000 — план,0admission.

**Приоритет Root — завершить исходную correctness-проверку Q100.** Предложение ниже полезно только если после этого вообще выбирается многоканальный fusion. Оно не добавляет prerequisite к исходной Task1 и не требует нового вычисления графа.

## Дедупликация и узкая добавка

В11-fusion и review09–12 уже явно есть: correlated popularity sources могут удвоить голос; один pre-fusionpool/depth; actualsize и gained/lost; fixedC для featureautomation. RB001/RB4 уже рассматривает seed/channel calls и overlap, а волна052 — degree-preserving null для fixedC compatibility. Волна098 уже задаёт общий discoverypool для count/cosine и matched-size replacement. Пересказывать эти механизмы как новые нельзя.

Добавка — **точный placebo одной копии источника с сохранением его суммарного веса**, до любых labels. Он превращает уже известное предупреждение о repeated votes в маленький различающий falsifier. Целевой поиск по старым synthesis и research notes не нашёл явного такого signed oracle; это ограниченный поиск, не доказательство отсутствия эквивалентного теста во всех100волнах. Поэтому только REFINE существующей fusion-заметки, без нового HYP.

## Первичное основание и собственный вывод

[Cormack, Clarke, Büttcher, SIGIR2009, Eq.1 и Discussion, полный извлечённый текст2pp](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) задают сумму reciprocal ranks по input rankings, с k60; arbitrary score scales не входят. Paper evidence относится к TREC/LETOR, не к нашему purchase target. В статье не заявлена инвариантность к копированию источника и нет данного placebo.

Следующий вывод — **моя алгебра из формулы**, не эмпирический вывод paper: если один и тот же ranking добавить второй раз, его вклад удваивается. Нормировка raw cosine/co-count в ранги этого не устраняет. Это допустимая смена channel weight, но она сама по себе не добавляет item information или discovery. RRF не требует независимости каналов; чувствительность к весу не является багом алгоритма.

## Единственное предложение A101-F1: copy placebo для атрибуции нового сигнала

**Механизм.** Два источника могут иметь один и тот же provenance и одинаковый упорядоченный output, но разные имена/обёртки. При equal-weight RRF копия получает ещё голос. На границе квоты меняется admitted set, хотя pre-fusion eligiblepool, каждый item, его past popularity и объём distinct информации остаются прежними. Если это объявить «ещё одним источником нового сигнала», channel-count смешивается с распределением весов. Это особенно актуально перед возможным объединением нескольких graph normalizations; сами count/cosine списки не являются точными копиями и данным placebo не объявляются бесполезными.

**Контргипотеза.** Усиление одного сигнала может быть полезным prior: высокая повторная поддержка способна повышать relevance. Копирование тогда лишь явная настройка веса. Разные retrievers с одинаковым output по случайности могут нести разные основания; их автоматически не схлопывать. Низкий overlap, меньшая head-share или отличающиеся наборы тоже не доказывают полезную новую информацию.

**Аналитический witness, не выполненный эксперимент.** Три eligible items, списки A=(a,b,c), B=(b,c,a), все ranks1-based,k60. Для F=RRF(A,B) top1=b, так как F(b)−F(a)=1/(62·63)>0. Для F'=RRF(A,A,B) top1=a, так как F'(a)−F'(b)=2/(61·62·63)>0. Никаких новых IDs в pool, outputsize в обоих случаях1. Это можно встроить в последний из максимум220слотов после219общих защищённых IDs; это toy boundary, не предложение защищать219позиций в реальном протоколе.

**Ближайший минимальный эксперимент.** Один source-free literal gate:4fusion calls — (1)A,B с весами1,1; (2)A,A,B с1,1,1; (3)A,B с1,1; (4)A,A,B с1/2,1/2,1. Проверить exact rational ожидаемый top1 b/a/b/b и полное совпадение scores(3)=(4). Группа копий определяется общей derivation/config/cutoff/depth identity и побайтно одинаковым ordered output; переименование alias не должно давать отдельную массу. Ничего не кластеризовать по измеренной корреляции и не считать косинус/raw-count aliases. Gate использует3IDs,3serialized input lists×3ranks,4calls,0Q/данных проекта/labels/ML. Предлагаемый предел всего эпизода:5CPU/10wall seconds,128MiBRSS,1thread,0retries. Это выбранные потолки, не замер достаточности; exhaustion даёт incomplete.

**Фальсифицируемое предсказание.** Обычный equal-vote RRF изменит верхнюю позицию только от дополнительной копии. Сохранение total source-weight восстановит исходные scores для любой точной копии. Если последний результат отличается, предложенная vote-conserving реализация неверна. Положительный gate устанавливает только формальное различие channel weighting и новой item information; predictive utility не установлена.

**Как не спутать это с tail/cardinality.** В gate одинаковые исходные IDs и finalsize, поэтому перемена не объясняется расширением C или изменением item popularity; это только веса. Для будущего настоящего quality-вопроса остаются уже существующие контракты: тот же pre-fusionpool/depth,≤220без скрытого refill, nativeactualsize рядом с label-blind matched-size, полныеY и net gained−lost, past-only popularity slices. Copy placebo не заменяет degree/support-controls волны052 и не доказывает, что popularity объясняет весь граф. Уже виденные development labels не становятся свежими от placebo.

## Решение и польза Task1

- **ACCEPT как SOURCE refinement**, если oracle и условия exact-copy/provenance поддерживаются; это максимум маленькое уточнение к11-fusion,0новыхHYP/очередей/обязательныхgates/grants.
- **REJECT claim «новый независимый сигнал»**, если единственная установленная разница — дополнительная копия/вес без нового outputinformation. Можно честно описать это как weight-policy contrast; качество при этом остаётся UNKNOWN.
- **REJECT автоматическое исправление всех коррелированных каналов.** Полезное подтверждение разных источников возможно; никакой universal superiority для collapsed/normalized voting не следует. Если фактический futurefusion не используется, действий по предложению нет.

Task1 получает более честный контроль для любого последующего автоматического source-fusion: число сгенерированных normalizations/aliases нельзя само по себе выдавать за новые полезные признаки или coverage. Отрицательный/нулевой результат не требует ещё seed, модели, свежего heldout или нового source run. Центральное сравнение автоматизации признаков с tuned manual boosting на fixedC остаётся прежним.

## Независимость и фактический scope

Применены skills research-campaign и research; прочитаны suppliedAGENTS и coordination. Peer101B/draft/идеи и текущий критик не читались и не обсуждались. Helpers/другие авторы не запускались. Исторические RB001/RA003 и wave098A прочитаны только для dedup прежних волн; это не peer текущей101.

Локальное чтение: существующая единственная очередь docs/backlog.md (текущие/исполнительные/HYP sections и целевой поиск, не весь исторический body); brainstorm-log/index (верхние статусы, целевой поиск и выбранные исторические sections, выводы больших чтений частично truncated); candidate05/11/12/index/review09–12; RA003/RB001; wave052null, wave086/087/088/098 и целевой поиск synthesis прошлых волн. Полнота чтения указана вpins; SHA доказывает версию файла, не полноту его интеллектуального чтения. Sarwar2001 landing/abstract тоже открыт, но на неполном тексте здесь не основаны новые technicalclaims.

Git status перед записью clean, HEAD28078c092a862b076f304c27bbd90df7d61bdb26. Canonical/Git/networkwrites0; DB/Parquet/raw/NPZ/modelbodies/SQL/projectimports/tests/fit/score/download0. Metadata hashing только разрешённых текстовых инструкций и researchdocs. Записаны только три назначенных /tmp файла. ПослеFIRSTfreeze — STOP до Root.
