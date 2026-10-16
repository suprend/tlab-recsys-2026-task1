# Tiny CLI fixture: источник и два плана подготовлены

Один реальный no-fit builder run завершился EXIT0; Root принял источник и два плана, затем принял их независимый review. **Q/Y/C/F collections, read-only verifier, модели и ordinary native CLI на этом этапе не выполнялись.** Это инженерная подготовка synthetic fixture, а не проверка качества или завершённый end-to-end путь.

Созданы 28 файлов: прямой typed9 источник с десятью придуманными событиями, 19 точных исходных копий, конфиги и два preparation plans. Оба плана связаны с одной sealed DB — 798720 байт, SHA `49d5db82fcdf10a94097f612450419e2b573570c50db57d03a0efb8d71b12b49`. DB и 19 копий в этот архив не входят. Builder проверил schema/row roundtrip; независимый reviewer проверил hashes, modes, inventory и plan identities без открытия DB или SQL-сканирования. Source calendar заявлен для fixture и не доказывает production completeness.

Train занимает 8–9 октября, model availability — 10 октября, selection — 18–19 октября. Проверены соответствие actual configs и обоих идентификаторов; producer-only approvals после review отдельно выдал Root. Их тела и control plans здесь не публикуются; они не означают принятие shard, feature/collection outputs или native fit.

| Факт | Наблюдение |
|---|---|
| Завершение builder | outer205344 EXIT0, wrapper/child reaped, повторов нет |
| CPU дочернего процесса | 0.701103 s |
| От запуска child до reap | 0.964268250 s |
| Наблюдённый Darwin peak RSS child | 117080064 B |

Parent SELF 0.062782 s исключает JSON/fsync/exit tail; эти значения не являются полным wrapper lifetime. Tool wait не заменяет wrapper wall, а engine memory64MB не является RSS containment. Ошибка metadata-reader bd4e0a сохранена: relative path был затёрт absolute path при объединении словаря. Исправлялся только reader; runtime не повторялся.

[Publication map](evidence/native-cli-tiny-builder/publication.json) связывает exact результаты, captures, reviews и source evidence. [Fixture generator](evidence/native-cli-tiny-builder/build-fixture.py.txt) сохранён побайтно как инертный `.py.txt`. Это исторический one-shot рецепт для изначально отсутствующего once-project: существующий consumed namespace нельзя запускать заново; архивная копия здесь не исполнялась. Будущий новый namespace требует отдельного точного review/issue, а не изменения этого оригинала.

[Девятисобытийный независимый FIRST](evidence/native-cli-tiny-builder/oracles/nine-event-FIRST/tlab-native-cli-tiny-manual-oracle-FIRST.md) — исторический другой вариант. Выбранный [десятисобытийный manual Q/Y/C](evidence/native-cli-tiny-builder/oracles/ten-event-QYC/manual-QYC.md) явно раскрывает полученное до design freeze peer-summary; blind-design claim отсутствует. [Pre-F oracle](evidence/native-cli-tiny-builder/oracles/ten-event-F/manual-F.md) предсказывает trainQ2/Y1/C=F3 и selectionQ3/Y3/C=F3, 18 registry features/41 numeric fields, off-C targets99/77 и denominators2/3. Это ручные предсказания до производства F; actual Q/Y/C/F ещё не подтверждены, native score/rank/tree не предзаданы.

Следующий допустимый шаг — отдельно выданная ограниченная no-fit production до существующей остановки shard review. После реальных outputs нужны существующие независимые physical/semantic acceptance и verifier; one-fit native grant сейчас недоступен. Callback-abort также UNRUN. Принято14 из19, TLAB-014 продолжается, TLAB-010–013 необязательные/отложены; прежние научные результаты не меняются. Закрытые science/native allowances не пополняются, остаток science UNKNOWN; deadline25Oct23:59/timezone unknown сохранён.
