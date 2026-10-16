# Category text: что именно проверять после замороженного исследования

Источник этого brainstorm — публичные документы проекта и три первичных источника ниже. События, модели, heldout, encoder APIs и retrieval implementations не запускались. Числа о тексте взяты из опубликованного EDA, а не перепроверены новым сканированием. Предлагается уточнение existing HYP-003/086; новых HYP, разрешений или расходов нет.

## Доступный сигнал и дедупликация

В [category recovery](../category-recovery.md) описаны 624 numeric category IDs: 252 имеют подтверждённый code, но различных строк только 126; 372 ID никогда не названы в октябрьском источнике. Это месячная характеристика, не каталог, доступный каждому раннему anchor. Нет title, description или image. Brand — отдельный категориальный атрибут; его строка не становится описанием товара. Восстановленные позднее имена из другого месяца нельзя незаметно переносить назад.

[TLAB-010/HYP-003](../backlog.md) уже предусматривают identity → prefix TF-IDF при одинаковых C и history weighting; dense отложен. [HYP-085/086 и retrieval study](../candidate-generation/10-text-retrieval.md) относятся также к отдельному изменению источника кандидатов. Fixed-C similarity feature и retrieval quota experiment отвечают разным вопросам, их бюджеты нельзя смешивать. [Embedding note](../text-embeddings.md) уже требует one-hot и random-vector controls на единице category **string**, а не на 252 ID. Здесь уточняется сила этих контролей, а не предлагается новая модельная линейка.

Metadata доступна только по утверждённой as-of политике: последний глобальный product timestamp bucket строго до t, со всеми peers; known+NULL/conflict даёт ambiguity, без поиска более старого чистого значения. Unknown numeric ID остаётся отдельным identity-сигналом; 372 ID нельзя объединить в содержательную «unknown category». Для исторического события способ привязки категории также фиксируется явно; current candidate category и историческая категория — разные величины.

## BM25 требует определения query

[Robertson–Zaragoza, §§3.4–3.5](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf) различают document-tf saturation и query term frequency: исходный вариант имел отдельный k3, распространённый вариант линеен по qtf. Значит, BM25 сам не решает, считать ли сто повторных просмотров стократным интересом. Это решение о пользовательском профиле.

Для будущего bounded контроля разумно сохранить уже предложенную политику: distinct просмотренные products за 7 дней; вес каждого — decay от последнего просмотра с half-life 3 дня. Это proposal, не текущая исполняемая binding. Для атомарного токена z определить

`a_z = Σ_j w_j · 1[z∈tokens(j)] / Σ_j w_j`.

В знаменатель входят все выбранные history products; потерянный текст отдельно отражается weighted coverage. Токены — полные префиксы, например `cat:electronics` и `cat:electronics.smartphone`, без случайного word splitting; brand исключить из первого taxonomy contrast либо одинаково вынести отдельным каналом. Один product — один corpus document. Компрессия одинаковых codes допустима только с сохранением product multiplicity при df/N; IDF по уникальным codes отвечает другому вопросу.

[Lucene 10.3.1 BM25Similarity](https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/BM25Similarity.html) задаёт положительный IDF `log(1+(N−df+.5)/(df+.5))`, параметры k1/b и field-specific docCount. Это не контракт пользовательского query builder. Требуется явно выбрать N: например, число past-fit products с доступным category field, и заморозить vocabulary/IDF до downstream anchors. При binary document tf и b=0 множитель `tf·(k1+1)/(tf+k1)` равен единице: получается weighted IDF overlap, а перебор k1 ничего не меняет. Это вывод из формулы, не измеренный результат.

## Минимальное различение структуры и pretrained geometry

Точный контрпример: переименуем все атомарные prefix tokens согласованной биекцией в непрозрачные символы, сохраняя membership, df, document lengths и query weights. BM25/TF-IDF scores останутся прежними. Поэтому lexical gain может свидетельствовать о переносе по taxonomy structure, но не о понимании английских слов. Полный code identity, prefix membership и pretrained geometry — три разных механизма.

Минимальное будущее уточнение HYP-086: общий frozen control уже включает numeric-ID/code identity и один заранее выбранный prefix similarity. На новой разрешённой development reservation сравнить **один** дополнительный dense cosine с корректным назначением vectors категориям против такого же cosine после заранее фиксированной биекции vectors между теми же доступными category strings. Одинаковы encoder revision, vector multiset, dimension, normalization, history weights, C, одна дополнительная scalar feature и необходимые masks. Набор strings для перестановки фиксируется по доступному past-fit snapshot; новый code после freeze обрабатывается объявленным OOV/missing правилом, а не добавляется из полного октябрьского списка. Это один механизм-контроль, не разрешение на fits; число fits/расходы ещё должны пройти отдельную фиксацию.

Переставлять нужно готовые vectors, а не кодировать выдуманные opaque названия: второе одновременно меняет subword tokenization и OOV. Random Gaussian vectors из старого плана остаются допустимым identity control, но меняют geometry distribution. Даже выигрыш правильного назначения над перестановкой не докажет чистый эффект «значения слов»: geometry может повторять сложные taxonomy relations сверх одного prefix scalar. Допустим узкий вывод: правильное соответствие pretrained geometry категориям добавляет сигнал к явно заданным identity/hierarchy controls. Counterhypothesis — существующая hierarchy/affinity полностью объясняет результат; отрицательный либо неопределённый contrast оставляет dense deferred.

## Missing/OOV, маленькая проверка и переносимость

До любого fit нужны literal fixtures, без Y: два ID с одним code дают одинаковый text vector, сохраняя различные ID; две sibling категории имеют общий prefix; известные непересекающиеся codes дают определённый zero overlap; NULL/conflict дают missing; пустая history и нулевая vector norm дают mask; новый code может иметь известный prefix и OOV leaf; future suffix не меняет прошлый mapping/IDF. Coverage считается на исходной history, не после удаления unknown. Все fixtures вместе могут укладываться в ≤16 событий; исполнение здесь не предлагается как уже разрешённое.

[Recformer, KDD 2023, §§2.1,3.1](https://arxiv.org/pdf/2305.13731) действительно кодирует историю key-value item texts. Но Amazon experiments используют title/categories/brand, отбрасывают items без title, включают pretraining/finetuning и leave-one-out next-item evaluation. Это источник механизма, не свидетельство выигрыша dense на наших 126 codes, fixed-C/full-Y purchase ranking или strict global peers.

Для другого датасета переносимы только схема профиля, availability/missing contracts и проверяемая формула. Появление настоящих descriptions меняет информационную задачу и требует новой binding. Для текущей сдачи NLP branch остаётся необязательной: полезный результат этой записки — исправление интерпретации lexical/dense controls, а не расширение frozen015/016.

## Publication boundary

Archived15October2026 as a refinement of existing hypotheses, not a new independent idea round or an execution allowance. The original research result is retained; subsequent code/review progress does not retroactively change its historical snapshot. No actual source/model/target/fit job was run for this note.
