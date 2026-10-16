# Native helper: один normal-path toy запуск принят

Root принял один opt-in native тест: **1 CatBoost fit, 8 обученных деревьев, 1 дерево в выбранной копии**. [Независимый review](evidence/native-helper-engineering-result/independent-output-review.md), [Root acceptance](evidence/native-helper-engineering-result/root-acceptance.json) и [карта оригиналов](evidence/native-helper-engineering-result/publication.json) сохранены. Это existing TLAB-019 engineering evidence; в исходной очереди по-прежнему 14 из 19 принято.

На 6 придуманных train rows и 7 validation rows с двумя features helper выполнил fit → staged selection → copy/shrink → save/reload. Все 8 префиксов проверены отдельным literal fullY NDCG@20 oracle; одинаковые validation feature rows дают плоскую кривую и earliest global-band выбор k=1. Исходный full model оставался 8-tree; shrink применён к копии, reload сохранил score parity. Это один flat/tie case, не проверка неплоского максимума. [Child stderr](evidence/native-helper-engineering-result/child-stderr.txt) сообщает один метод, OK без skip; [child stdout](evidence/native-helper-engineering-result/child-stdout.txt) пуст.

[Raw child terminal](evidence/native-helper-engineering-result/child-terminal.json) сохраняет историческое `CHILD_EXIT0_PENDING_ROOT_FULL_EXIT`; его не переписали. [Поздний Root actual terminal](evidence/native-helper-engineering-result/root-actual-terminal.json) подтверждает outer session85582/chunk9d36c3 CLOSED exit0, wrapper и native child reaped. Toy CBM удалён, scratch пуст по Root/read-only metadata review; модели/данные в пакет не включены.

| Наблюдение | Значение и scope |
|---|---|
| Wrapper известный полный выход | 1.308355 s wall от pre-Popen до known wrapper exit |
| Wrapper [profile](evidence/native-helper-engineering-result/profile.json) | 1.291047 s wall от первой строки; SELF CPU 0.024205 s, без final JSON/exit |
| Reaped native child | 0.946233 CPU s; observed peak RSS 136,347,648 B |
| [Conservative known-process CPU sum](evidence/native-helper-engineering-result/external-result.json) | 1.969726 s; возможно перекрытие учтённых descendants, не exact total |

Отдельно разрешённый **50 CPU / 65 wall** allowance один раз завершён **CLOSED**; остаток не reusable, automatic retry нет. Это наблюдаемые scope, не hard whole-tree CPU/RSS containment. Старые scientific allocations/неизвестный остаток не меняются.

**Ordinary development CLI E2E и native callback-abort остаются UNRUN.** Не проверены реальный датасет, CV, quality, неплоская оптимальность, early stopping или экономия обучения. 12 FakeML/CODE CLI tests и installed `--help` exit0 сохраняют свой отдельный scope. Historical UNRUN FIRST/proposal/docstring/V2 snapshots не переписываются: actual receipt меняет только статус normal-path toy body. Native согласие не разрешает exact b760 push — вопрос публикации без ответа; исторический private draft PR №1, UNSENT обновление описания и fresh remote UNKNOWN сохранены. Git episodes FAILED/0 новых commits и ref updates; owned index/первичные HEAD/index неизменны, attributes UNPROBED, Git V4 SOURCE/UNRUN под отдельным Root review.
