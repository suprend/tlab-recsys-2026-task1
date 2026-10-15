# 019 producer targeted independent rereview

**ACCEPT CODE ONLY** для указанного нового freeze. Исходные три P1 и strict-integer P2 закрыты. Это не execution approval и не принятие actual моделей/данных/метрик: внешний controller, observer entry, exact plan и execution approval остаются отдельными gates до первых реальных fits.

SHA256 до/после своих проверок:

| Файл | SHA256 |
|---|---|
| scripts/strong_baseline.py | 53808ef3b98e0175d628b93ffe3cd0c6997940a132732d03490be78964daff14 |
| tests/test_strong_baseline.py | 1921dcbff87fb2f43e2f3e2662630c77bd4785e86f7e8d95e2ff9d2baf1a3eb7 |
| configs/models/strong-grid.json | d32daac420f447444d987969cdd49ac1cad427bbd7357114d148c02085aed66e |
| docs/experiments/strong-baseline.md | aae39f6fcb6a705bb575e9033b7caf179b9dab3ac06f7f0038632ac7ce073560 |

Issuer binding теперь начинается с digest, сохранённого parent в памяти при allocate_slot. Worker CLI требует его явно; entry сверяет context до чтения slot, а parent проверяет исходную in-memory выдачу до spawn и digest после worker. Исходные свежеперезапечатанные population6000→26000 и CPU100→3240 отвергаются до spawn. Дополнительные probes отвергают валидный новый digest с изменённым slot против старого in-memory parent и изменение context во время mocked worker. Digest фактически присутствует в launch argv. `[50.0,150,300]` отвергается и при новом digest.

Normal leader exit теперь проверяет residual owned group. Исходный tiny leader+sleeping descendant воспроизведён: вместо success получен исходный RuntimeError forbidden descendants; direct leader reaped, группа после cleanup исчезла. Дополнительная настоящая Popen-ветка parent guard failure сохраняет тот же объект первичной ошибки, direct child reaped и не жив. Остаток неизвестного group usage должен оставаться STOP; механизм process groups не является OS sandbox для произвольного намеренного escape из сессии. Никакой такой hard-containment guarantee здесь не принимается.

Parent вызывает complete-worker validator перед включением checkpoints. Собственный healthy receipt с41 numeric names, тремя seen checkpoints и восемью nonempty placeholder files проходит mechanical gate; это намеренно не проверка CBM/NPZ содержимого или качества. Freshly resealed пустые/лишние output maps, missing/empty prefix, forged population/depth/L2/trained_iterations/incumbent/configID, float checkpoint/look, missing/unseen reservations, неверные names/params, invalid metric и OnlineCtr JSON отвергаются. Actual saved-score/parameter replay останется обязанностью независимого observer; producer hashes/metadata его не заменяют.

Own targeted harness v2: **21/21 PASS**, `-W error::ResourceWarning`, wall0.186644916s/SELF0.093208CPU/reaped CHILDREN0.018888CPU/RSS64,225,280 bytes (counters после imports). Initial harness дал20 проверок, из которых одна false failure была ошибкой fixture: expected parent и report делили names list. Mutation меняла обе стороны. Initial helper/results сохранены, v2 независимо копирует names; неверный schema действительно отвергнут. Это не producer исправление или экспериментальный retry. Общая стоимость двух tiny probes видна в отдельных receipts; успешная v2 не стирает первую попытку. Авторские38 tests здесь повторно целиком не запускались; авторский PASS не служит самостоятельным доказательством.

Оригинальные review/helper/results побайтно сохранены; observer279256…64d4 также не менялся во время этого rereview. Registry/grid/resource caps/retrospective selection policy и fit/look quotas не расширены. 203-lineage, once claims, recognized-resource fallback, whole failed-arm exclusion, canonical ties и trained300/prefix наследование остаются ранее проверенными границами; новых реальных доказательств для них этот узкий replay не создаёт.

Evidence: `tlab019-independent-rereview-faults.py` + `tlab019-independent-rereview-results.json` (initial fixture failure); `tlab019-independent-rereview-faults-v2.py` + `tlab019-independent-rereview-results-v2.json` (21 PASS). Actual source/parquet/matrix/Pool/model load/predict/native fits/acceptance writes:0.
