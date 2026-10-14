# Full009: final narrow failure-marker re-review

15 октября2026. **ACCEPT CODE ONLY** для daily full-export producer/consumer на exact freeze ниже. Remaining failed-receipt P1 закрыт; предыдущие четыре P1 и phase-cardinality P2 уже закрыты отдельным targeted review. Real full production/source acceptance, model_data/ablation/fit approval этим verdict не разрешаются.

До/после проверки SHA256 совпали:

- script `3a255515514d06d7e7e13970477cf67461033067aaf4b3a29d91ff49a9510d8d`;
- tests `09da5d00941f76f1900a106a698ca553512ccd7f2844be03adb934cb4e8802d6`;
- doc `a8952963af36ca245364d7a4632c9b2748eabff994503b38fc38789be63311fe`.

Producer сохраняет первую оплачиваемую summary соstatusfinalizing; complete публикуется только при окончательном receipt. `verify_accepted_export` отвергает известныйreport.failed.json до manifest/current-input preparation. Изменения локальны к finalization/consumer boundary, source math/metadata core/retention policy не расширялись.

Собственный `tlab009-full-independent-final-marker.py` независимо выполнил три tiny runtime cases:

1. Healthy finalization проходит running→finalizing→complete, marker отсутствует, consumer принимает physical bundle.
2. Original final writer fault, адаптированный к новому status sequence, отказывает записи **финального complete receipt** до замены файла. Caller получает исходныйOSError; disk report остаётсяfinalizing, fallbackreceiptfailed; consumer отклоняет доprepare.
3. Legacy stalecomplete report плюс knownfailed marker также отклоняется доprepare. Это отдельно закрывает старый опасный bundle shape, а не только отказ на новомfinalizing status.

Для cases2/3 prepare callback заменён forbidden assertion и не вызван. Fake external approvals существуют только в temporary fixture; actual approvals не создавались. Full runtime preparation остаётся явно mocked transport, source values не объявляются независимо проверенными этим тестом. Known-marker gate не является атомарнымfilesystem snapshot или доказательством безопасной работы с живым одновременно изменяемым run directory; будущий pipeline потребляет завершённые immutable artifacts последовательно.

Четвёртый case проверяет coordinator source observer `fe1c5142e71b344af59dd2ec81bec7143ff08533147a80f04e1cf5b2f5d5586b` AST-only, без Root imports/sourceSQL: knownfailed marker отвергается ещё при отсутствииrun.json; transport/engine callbacks вызваны0раз, initialattempt сохраняет failed evidence. Подробнее в `tlab009-full-source-oracle-marker-rereview.md`.

Raw evidence `tlab009-full-independent-final-marker-results.json`:4cases, все expected accepts/rejects совпали, measured1,537086s wall/1,592612s processCPU/180813824bytes peakRSS,0fits/0real source reads.23author tests по handoff не повторялись: scope ограничен этим маленьким изменением; ранее самостоятельно воспроизведён21-test revised suite.12typed source-transport cases также не повторялись без изменений.

История сохранена: initial code review SHA `4be8b0890fa666c8030ed415fdc43b2ba0fd1f64145669fa714c8cc811e15b64`; prior rereview SHA `bc6018935f1ad326c0db9092cb2d35fbf037db16503b01f63db506c8907655aa`. Старые helpers/results/reports byte-identical. Следующие gate — exact external execution decision, bounded900CPU producer, отдельный900CPU exhaustive independent source audit и external acceptance, затем отдельно reviewed mixed loader/ONEfit. Никаких actual6134207row/source/cost/model результатов этот code acceptance не утверждает.
