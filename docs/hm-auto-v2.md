# H&M v2: почему расширение признаков хуже и как улучшить автоматизацию

**Итог конечного прохода:** прирост не подтверждён. Customer-test M MAP=0.03306033, E=0.03182877, Δ=−0.00123155, 95% CI[−0.00310429; +0.00062035]. Основным остаётся ручной M23; цель получить подтверждённый прирост для T-Lab остаётся открытой. Все 28+4 новых fits и проверки завершены. [Читаемый отчёт](hm-auto-v2-report.md). Датированные checkpoints ниже сохраняют историю и не являются текущими поручениями.

Старт 2026-10-18T13:27:46.654222+00:00. Пользователь явно поручил диагностировать отрицательный результат v1 и попробовать улучшить автоматизацию для T-Lab. Предыдущее предпочтение «нет пределп» сохраняет отсутствие общей time/round границы. Этот проход имеет конечный протокол: максимум30 development fits и4 новых customer-test fits; неиспользованный бюджет не превращается в дополнительные попытки до положительного результата. Минимальный полезный результат — различить хотя бы один механизм и проверить автоматическую процедуру, которая может отказаться от неподтверждённых дополнений. Улучшение не обещается.

Исторический [итог v1](hm-report.md), его код, config и decision lock сохраняются побайтно. Новые модули, конфигурации и outputs имеют отдельные имена. [Протокол v2](../configs/datasets/hm-auto-v2.json) закреплён до первых новых fits; SHA84f3e2db341358a72ae7938c90af0696f5926b91faba746f61b801a7f7cd8b8b. Единственная исполнимая очередь — [backlog](https://github.com/suprend/tlab-recsys-2026-task1/blob/archive-2026-10-25/docs/backlog.md), журнал — [brainstorm log](https://github.com/suprend/tlab-recsys-2026-task1/blob/archive-2026-10-25/docs/research-lab/brainstorm-log.md). Исполнитель — текущий активный чат/root, без расписаний, paid APIs, публикаций, push или submission.

## Исходный симптом и гипотезы

V1: selected−M на final−0.00177647,95% CI[−0.00375881;+0.00007831]. Точечные оценки отрицательны на обоих seeds и двух development-неделях. Это воспроизведённое наблюдение по сохранённым отчётам, не установленный software bug или статистически доказанный вред. Низкий общий retrieval coverage не объясняет разный retrieval между arms, поскольку C/Q/Y одинаковые.

1. PVC измеряет использование признаков в обученной all-модели, а не их marginal MAP на будущей неделе. [Официальное определение CatBoost](https://catboost.ai/docs/en/concepts/fstr) описывает среднее изменение предсказания и неотрицательные importance; все58 ненулевых значений поэтому не доказывают полезность всех58.
2. Фиксированные12 дополнений могут быть избыточны. Prefix1/3/6 при одинаковом рецепте проверяет ширину конкретного ranking. Меньший набор, полезный на обоих development-срезах, поддержит эту стратегию; GPU stochasticity и изменившиеся splits не изолируются этим тестом.
3. Параметры, выбранные для M, могут хуже подходить расширенной модели. Симметричный L2-grid проверяет зависимость результата от рецепта. Он не устанавливает переобучение как единственную причину.

## Последовательность и критерии

Два известных development folds: Aug12/19/26→Sep02 и те же+Sep02→Sep09. C0-Q120, train20k/sample20/cohort2026, GPU500d8/seed2026 совпадают с v1. Сохранённые M и PVC12 используются только после проверки exact identities.

Первый шаг: widths1/3/6 из замороженного v1 training-only PVC ranking на обоих folds,6fits. Ranking обучен до Sep02 и остаётся прошлым для Sep09; это fixed-ranking width diagnostic, не freshly refitted fold-specific selector. Кандидат допускается при strict positive point ΔMAP на обоих folds; winner — максимальный minimum weekly delta, затем mean delta, меньше признаков, имя. CIs development описательны после поиска.

Если ни один prefix не допускается,5 dimension groups ×2folds =10fits. При допущенной первой группе возможен один greedy-шаг по четырём оставшимся группам, максимум8fits. Добавление принимается только при положительном marginal MAP к текущему набору на обоих folds, с тем же winner/tie rule. Размеры групп11/12, двух групп22–24; equal-width сравнение не утверждается. Если нет допущенной первой группы — width0. При width0 повторно используются сами M models/predictions: отдельная стохастическая копия M не может считаться эффектом features.

Для непустого выбранного expansion обязательно одинаково проверяются M/expanded × L2{10,50} на двух folds, четыре дополнительных L2=50 fit, L2=10 reused. Каждая процедура выбирает L2 по mean weekly MAP, ties lowerL2. До B допускается только непустой вариант с positive point delta к equally tuned M на обоих development folds. Иначе B остаётся нетронутым, gain не заявляется. Максимум30dev включает6prefix+10groups+8secondstep+4L2+2freshreferences; доказуемо совпадающие references не переобучаются.

## Новая проверка

Известная final-неделя Sep16–22 не становится новым temporal holdout. Вместо этого резервируется20k новых пользователей по history-only eligibility и hash salt hm-v2-customer-test-20261018. Исключаются все прежние H&M sampled/train Q и любые v2 supervised query IDs; в резервировании реконструируются также20k history-only cohorts Aug05..Sep16, что безопасно сверхисключает ранний pilot5k. Резервные ID/digest фиксируются до чтения их Y. Их прошлые покупки могут входить в общепопуляционные исторические статистики; supervised labels, selector и tuning по ним запрещены.

До конкретного нового decision lock нельзя создавать test labels/feature caches или читать target counts/coverage. После lock: equally tuned manual/auto × seeds2026/2027, primary per-user seed-mean AP и paired positive-user bootstrap2000/seed2026. Gain iff lower95>0. Это customer holdout той же известной недели; общий календарь/каталог/адаптация по v1 ограничивают независимость. Нельзя менять names/params/cohort/seeds по B outcomes.

## Исполнение и состояние

Root — один heavy SQL/model worker. Отдельный GPU job1860s, optional outer1920s, SQL4threads2GB/spill8GB; desiredRSS8GiB без hardcap, GPUram_part0.5 не гарантирует hardreservation. TEMP/TMP/CUDAcache на D. После ошибки зависимые шаги остановлены; неизвестный op сверяется с process/report до retry. Исторические outputs сохраняются.

W007: независимые FIRSTA/B и отдельный скептик. NEW2(width/groups),REFINE1(symmetricalL2 из ранее deferred recipe-dependence),merge двух совпавших предложений A/B; три экспериментальные семьи admitted условно по конфигу. Customer holdout — отдельный validation contract. Следующая волна 2026-10-18T14:12:46.654222+00:00 либо после2accepted rounds, counter0.

Checkpoint13:32UTC:6prefix configurations/names/optionalJobdriver прошли независимый readinessreview. Root batch session61067 исполняет HM2-OP001–006 последовательно. OP001 succeeded153.266s; prefix1 Sep02 MAP.03384318085068868 — пока неаудированный diagnostic point, не вывод о gain. Следующий fit уже принадлежит тому же driver; не запускать повтор.

Новый `hm_auto_fit.py` SHA50b1d1cb48c04b823f3a73d802669c6770a37fc2c16ebf3cd1a77bca4caaa3e5:12focused tests PASS author,140H&Mtests PASS author; независимый guard12tests PASS2.797s, блокирующих дефектов не найдено. Это FakeML/tinyDuckDB, реальный L2fit ещё не запускался. Runner development-only: никакие final anchors/markers до mkdir/SQL/Pool не допускаются. Caller обеспечивает фактический внешний1860s Job.

Label-free `hm_auto_reserve.py` SHAd396817aac00967f644afbae248c64dd862b69c3cacf872ee16f63d48ff872be и10synthetic tests PASS author; независимое read-only code review отдельно. ActualIDreservation/target access не выполнялись. После review реальный history-only SQL запускает только root вне GPU-batch.

Update13:37UTC: reservation independentreview PASS10tests1.847s, rootcombined22tests PASS3.599s; все11v1 sourceSHA совпали. OP001/002/003 succeeded153.266/155.453/143.172s. Sep02 provisionalMAP: prefix1.03384318085068868; prefix3.029767338517930654; prefix6.031447567399553594; M.03367563099291461. Вторая неделя и resultaudits ещё не завершены, scientificround не принят.

Postfit driver `artifacts/hm-auto-v2/run_prefix_audits.py` SHA32133c7656e54de1b716342f856e0f92b89bb44161854fa30b58a5f84e72c880 прошёл независимый static+mockedsubprocess readinessreview. После успешных OP001–006 он выполняет OP007/008 audits в порядке M/PVC12/prefix1/prefix3/prefix6, OP009/010 семь фиксированных paired2000/seed2026 descriptivecontrasts и OP011 history-onlyreservation. ActualпокаUNRUN. Semanticgroupmanifest SHA6feb442f86f2993eaf8cf79155edd12c37648efd64c88a90455e1f80409d255a проверен: exact58 frozenpool, M23 и disjointгруппы11/11/12/12/12. Эти metadataне разрешают conditionalgroupfits до prefixdecision.

Краткий engineeringaudit: metadata-only подготовка groups дважды остановилась до создания output (ошибочно указанный key `pool_programs`, затем objectaccess вместо dict); после сверки фактической схемы исправлена и проверена. DB/fits от этих попыток не запускались, группы не выбирались по outcomes. Старые и новые outputs не перезаписывались.

Update13:43UTC: OP004/005 succeeded171.969/177.875s, prefix1 Sep09.029860530861926946 и prefix3 Sep09.031635621766242614 против M.031220688912491235. Таким образом ни один prefix не будет eligible BOTH, если producer points подтверждаются аудитом: prefix1 отрицателен Sep09, prefix3/6 отрицательны Sep02. OP006 ещё исполняется, все шесть завершаются до conditionalbranch. Group10fitdriver SHA8565c1be4764310c420ae8bf1f8d7985b06c8779e215675263bcc4254466669c прошёл independent mockreadiness; actual groupfits ещёUNRUN.

Metadata-only prefixselector на независимом review выявил P2: exactfloat equality строже допустимых auditor1e-12. OneULPsynthetic воспроизводит отказ; в17старыхactualпар различий нет. Author устраняет compatibilityдефект до actualdecision; научное правило выбора неизменно. Это новый engineeringedgecase, не причина отрицательного v1qualityрезультата.

## Первый диагностический результат: ширина старого PVC-списка

Все шесть GPU fits завершились. Аудиты OP007/008 независимо восстановили development Q/Y из исходной базы и пересчитали метрики сохранённых top12; оба PASS. OP009/010 рассчитали семь заранее заданных paired contrasts на каждой неделе. OP012 запустил новый metadata-only selector и получил `chosen=null`, `next_action=group_fallback`. Отдельная read-only проверка raw exports ещё идёт; приёмка раунда пока pending.

| Дополнение к M23 | MAP@12 Sep02 | MAP@12 Sep09 | Положительная Δ к M на обоих folds |
|---|---:|---:|---|
| Нет: ручной M | 0.0336756310 | 0.0312206889 | Reference |
| Первый PVC-признак | 0.0338431809 | 0.0298605309 | Нет |
| Первые3 | 0.0297673385 | 0.0316356218 | Нет |
| Первые6 | 0.0314475674 | 0.0303527736 | Нет |
| Прежние12, v1 | 0.0309630870 | 0.0291826918 | Нет |

Сокращение списка само по себе не даёт устойчивого преимущества над M. Prefix1 лучше M на Sep02, prefix3 — на Sep09; mean weekly Δ у всех трёх отрицательна. Это ограничивает гипотезу «достаточно взять меньше из того же ranking». Один modelseed на development и stochastic GPU не позволяют установить единственную причинную связь или отдельно измерить вклад случайности. Интервалы после этого поиска описательные.

Следующий заранее предусмотренный шаг — проверять semantic groups по marginal MAP двух folds. Ни новый PVC ranking, ни новые модели вне протокола по этим наблюдениям не добавляются.

OP011 history-only reservation completed25.219s:20,000 новых пользователей,23,979 исключены по union старых когорт, overlap0. Actual manifest и два ID parquet находятся только в ignored artifacts; приватные IDs в Git не включаются. Ни B-Y, ни target counts/coverage, ни labeled B cache не читались. Исторические training/dev query sets остаются прежними и покрыты exclusion.

Prefixselector P2 исправлен узко: `metrics_equal` использует точные typed integer counts и finite fractional tolerance1e-12; выбор берёт audited MAP. SHA87af0a872bc7662ddab9f8fbb988b8224b83992c1abb38c7c0447a5fb596c190, independent15tests PASS1.143s, root15PASS1.089s. Реальное OP012completed0.141s. Scientific rule и frozen config84f неизменны.

HM-R009 accepted13:48UTC. Независимый reviewer пересчитал AP/Recall всех10 arms из savedtop12 и fullY и все14pairedbootstrap means/CI с точностью≤1e-12,7.953s. Reservationfile/orderedIDhashes иsaltorder совпали; все6actualoldQ входят в exclusions и disjointB. Union этих6=23,484, ещё495 exclusions соответствует дополнительно reconstructedAug05. Eligibility/Aug05source SQL повторно не сканировались: они опираются на reviewedreservationcode+manifest. Нативный порядок omitted C-scores не проверялся.

| Артефакт | SHA256 |
|---|---|
| Prefix audit Sep02 | 8269e968032b9d99d2e8780b0b8cc486e72e7444be0faa3e1819a0b4fe58f207 |
| Prefix audit Sep09 | 52d6393952dea83c64173d958e372621c1f4a8255ace91eba285919037e60497 |
| Prefix contrasts Sep02 | 11c991221c32c393097cd6d8c80e9fc42a8aaa50c548396b44ce58eb57acaa10 |
| Prefix contrasts Sep09 | 35ce0cddaeeb7ea02727323ad0cbd7182299f1b0b97b9ed5bd2899f69e4fafaa |
| Automatic prefix decision | cc191bc551693f67c4da8bf53c202e525c41bee1f988ffe70a172202f485c3c8 |
| History-only reservation manifest | 424eace8c378caf7d10d98af364ba1a7f99f7d17177e7b41c19ccb9bc0f53e89 |

Groupselector `hm_auto_groups.py` SHAd4c60ffce9548ef4d1acb0e7f0d5b916511a1376c68c344dfcd282fc3812b9f8 прошёл independentreview14group+15dependencytests PASS5.672s. Реализованы stage1 и stage2, strict marginalboth/maxmin→mean→width→name; отсутствие второго улучшения сохраняет первую группу, отсутствие первой — exactMreuse/noL2/noB. Это syntheticmetadataQA, actualgroupdecision покаUNRUN.

FullH&M suite179tests PASS41.759s. Первая попытка дала1error в старой fixture `outside_artifacts`: TEMP был внутри artifacts, поэтому путь по определению не был outside. После переноса только testTEMP в новый `D:/hm-auto-v2-test-temp-20261018` повторный полный запуск прошёл; sourceне менялся. Логи локальные/необязательные, успешный статус воспроизводится canonical unittestdiscover приTEMP вне checkoutartifacts. Model/SQL jobs сохраняют прежний D:-TEMP.

Current checkpoint13:48UTC: rootsession36231 исполняет ровно10groupfits OP013–022, затем2source/metricaudits и22descriptivecontrasts OP023–026. ReviewedfitdriverSHA8565c1be4764310c420ae8bf1f8d7985b06c8779e215675263bcc4254466669c, auditdriverSHAbf4a7cbf32b85f6cde2876677057c8a4cc3284f770caa6fc7322d8e307c7e131. Root — единственный heavy worker. Следующая волна14:12:46UTC либо после следующегоacceptedround; W007counter1.

## Что именно исправляет новый критерий

PVC оценивает изменение предсказаний внутри уже обученной модели, а не результат переобучения без признака на будущей неделе. Ненулевое значение не свидетельствует о положительном marginal MAP. Документация отдельно предупреждает о расхождении большой prediction-importance и небольшого влияния на ranking metric. Корреляция агрегатов остаётся возможным механизмом; причиной нашего проигрыша она этим не доказана. [Официальное определение](https://catboost.ai/docs/en/concepts/fstr).

Замена PVC на native `select_features` также не гарантирует нужного результата. В SHAP-ветке CatBoost1.2.10 loss criterion берётся из `ObjectiveMetric`, в нашем случае Logloss; отдельный вариант `RecursiveByPredictionValuesChange` продолжает использовать PVC. [Исходник соответствующей версии](https://github.com/catboost/catboost/blob/v1.2.10/catboost/libs/features_selection/recursive_features_elimination.cpp#L723). Native MAP по candidate labels не видит цели вне C, поэтому его знаменатель может отличаться от full-Y. Это вывод из определения нашей метрики, а не результат нового ML-эксперимента.

Inverse-inclusion weights корректируют sampled loss: при предположении равномерного negative sampling её ожидание для фиксированных предсказаний соответствует full-C weighted Logloss. Это не гарантирует ту же обученную модель и не превращает objective в MAP. Простое добавление `eval_metric` задаёт оценку для best-model/overfitting detection, сохраняя обучающий objective. [Logloss](https://catboost.ai/docs/en/concepts/loss-functions-classification#logloss), [роль eval_metric](https://catboost.ai/docs/en/references/training-parameters/common#eval_metric). Различие критериев установлено; его конкретный вклад в отрицательный Δ пока не измерен.

Положительный support ограничен: train3 содержит2,434 retrieved-positive rows из1,202,434 sampled fit rows; train4 —3,381 из1,603,381. На validation хоть одна цель присутствует в C у711/2,111 и612/1,957 future purchasers соответственно. C одинаков у arms, поэтому низкое coverage не создаёт различие retrieval между моделями; оно ограничивает доступный ranking-сигнал. Эти числа берутся из проверенных M fit/audit reports, без нового SQL по данным.

Коэффициент L2 не обязан одинаково подходить разным наборам признаков; его определение — регуляризация cost function, не гарантия оптимума. [Параметр l2_leaf_reg](https://catboost.ai/docs/en/references/training-parameters/common#l2_leaf_reg). Текущий v2 проверяет его симметрично только после непустого admitted expansion. Если все группы отклонены, влияние переноса L2 остаётся открытым: отдельный четырёх-fit тест прежнегоPVC12/M×L2=50 на обоих folds был предложен исследователем, но НЕ включён в frozen84f и сейчас не запускается. До нового prospective решения B остаётся нетронутым.

Update14:00UTC: conditionalgroup firstweek4/5producerpoints завершены: type.0317864424,colour.0337371067,department.0321623234,garment.0315843705; M.0336756310. Пока толькоcolour имеет tinypositivepoint; целыйgroupраунд/вторая неделя/audits ещё не завершены. OP017index firstweekpending, root36231 единственный heavy worker. Все4новыхsourceмодуля/config проверены и сохранены локальным commitd2c9da3, не pushed. Документальные пояснения послеcommit прошли independentreview с двумя узкимиwordingправками иrereviewPASS. W008FIRSTготовится по общему rawpacket, no newadmission/изменений84f; W007counter1 иnextdue14:12:46UTC сохраняются.

## HM-R010: semanticgroup проходит две development-недели

Принято14:19UTC. Все10fits OP013–022 завершены, оба independent source/metric audits023/024 PASS. Контрасты025/026 содержат по11заранее заданных comparisons. OP027 выбрал единственную eligible группу `index_code`,12дополнений к M23. Отдельный reviewer пересчитал AP/Recall14arms из savedtop12/fullY и22pairedbootstrap2000/seed2026 contrasts≤1e-12,11.390s. Source/runtime/recipe/QCY/report/CBM hashes/500trees и все013–027receipts подтверждены; originalDB/nativepredict/B-Y он не открывал.

| Группа дополнений | Width | MAP Sep02 | MAP Sep09 | Δ Sep02 | Δ Sep09 | Eligible BOTH |
|---|---:|---:|---:|---:|---:|---|
| product_type_no | 11 | .0317864424 | .0322598462 | −.0018891886 | +.0010391572 | Нет |
| colour_group_code | 11 | .0337371067 | .0306950764 | +.0000614757 | −.0005256125 | Нет |
| department_no | 12 | .0321623234 | .0336190431 | −.0015133075 | +.0023983542 | Нет |
| garment_group_no | 12 | .0315843705 | .0326463191 | −.0020912605 | +.0014256302 | Нет |
| index_code | 12 | .0340748361 | .0320242645 | +.0003992051 | +.0008035756 | Да |

Index12−M CI Sep02[−.0018487478,+.0026802940], Sep09[−.0010562279,+.0028997448]. Оба включают0; это development selection после поиска, не независимое доказательство gain. Meanweekly pointΔ+.0006013904. Department имеет положительную meanΔ, но не проходит заранее выбранный strict-both gate: не утверждаем, что все отклонённые группы хуже в среднем.

Новый набор содержит столько же дополнений, сколько прежний PVC12. Сокращение старого ranking не прошло обе недели, а другой состав из12 прошёл. Это ограничивает объяснение только числом признаков и поддерживает проверку иной процедуры отбора; данные не устанавливают единственную причину или превосходство стратегии при равном search budget. Старый и новый наборы сравниваются здесь на уже известных development-срезах.

ArtifactSHAs: auditSep02 `05f2de303ac303480e2b7a4bb89a25161ec10aee91d4a3837d6edb79e462aee2`, auditSep09 `64307a6c5322677194623f2dcb04372ef113988034da856bb1be1c44861e0fdb`; contrasts `fcd613322a6f457691d1d37ee807d86133fa1db79afb4075e4e5e8e2e012aa9f` / `e564d8c45bbd69a921da7dd721a733763824b78ac5c82898ad47054a0574556c`; decision `55095814df83d0076bf4eb38fea3b10ad20bd8b65a895a66775aa225271869df`.

W008 принят14:13:02UTC: условный recipeprobe отдельноописан в [волне](https://github.com/suprend/tlab-recsys-2026-task1/blob/archive-2026-10-25/docs/research-lab/hm-wave008.md) иконфигеb6b18a. Его условиеwidth0 НЕвыполнено; HM013superseded, никакого изего4fits не запускается. Первоначальный84f остаётся неизменным.

Текущий checkpoint14:19UTC: root47871 запускает reviewedprivate stage2driver22ea70ab3fa11114351cf0e481c00d0326b9cc06eb83a124c39e1d2823c1cf3d: index_code+каждая из4remaininggroups, по2folds, ровно8fits028–035, затемaudits036/037,18fixeddescriptivecontrasts038/039, automaticgroup2decision040. Если ни одно добавление не даст positive marginalΔобоих folds, сохраняется index12. Ни новых widths, ни третьей группы по outcomes не добавляется.

Originalv2 L2validator `hm_auto_regularization.py` SHA3e1e31791c45bd4404b5a77cab243c2b2c80284bf39da6b67478d7e6e0003754 и13новыхtests прошли независимый review;42relatedtests PASS16.235s reviewer/14.985s root. Он принимает только nonempty acceptedgroup2, explicitprospectiveplanSHA, exactM/E10refs иM/E50outputs; проверяет8auditedcells, choosesL2bymeanweeklyMAPties10. InteractionD descriptive, practicalgate строго equallytunedE−M>0both. Любой customerholdout им НЕавторизуется. ActualL2plan/fits покаUNRUN.

Подготовка finalsource выполняется отдельно от доступа к outcomes: новые lock/collector/customQauditor и inventedfixtures пишут3независимыхвладельца. Только root создаст actualконкретныйlock после eligibleL2decision; доэтого B-Y/counts/features остаются закрытыми. W008counter1,nextdue14:58:02UTC либо следующийaccepted empiricalround.

Engineering checkpoint14:35UTC: симметричный L2 metadata-validator/source сохранён локальным commit`8b18418`; rootdriver `run_l2_stage.py` SHA`624467743ed584cb39c37aa28f990ff70cd0b339cea355a40c8cddbeda677787` прошёл independent static и mock replay с настоящими metadata validators. Реальный prospective plan создаётся только после acceptedOP040, его explicit SHA фиксируется до четырёх fits041–044. Далее exact4arm audits045/046,6descriptivecontrasts/week047/048 и decision049. ActualL2plan/fits всё ещё UNRUN.

Новые customer-test gate/collector/auditor сохранены локальным commit`903f27f`; два независимых code reviewers приняли один общий29file snapshot, затем обновлённую двухфайловую правку. SourceSHAs: gate`f1ca8215c2a65deaca45a2f91dbb7d288d40175627921ff39ad3c7214be32ebf`, collector/fit`5e937c9b3058838fddde4eee25cd1c5df55a5f4249bd672c840e59c3df2faf49`, auditor`33788d7de9c74fb94061b50a764c15dc79c27901f288e794bdf684afe5d89464`. Проверены explicit19code/runtime/lockSHA, replay group/L2 evidence, actual reserved-Q вместо старого cohortselector, до-Y exclusion checks, independent7sourcecohorts/saltQ/C0/fullY, четыре extendedfitidentities и compatibility с тремя frozencontrasts. Это code readiness на inventedfixtures/FakeML, не приёмка B-runtime/качества.

Root suite238tests PASS66.048s до узкой CBM-правки; после неё root20affectedtests PASS4.040s, оба reviewer20PASS5.180/5.226s. Сама правка вызвана отдельным native metadata-only witness на уже известной development CBM: reload округляет `bayesian_matrix_reg` .10000000149011612→.1000000015 и `learning_rate` .05000000074505806→.05000000075. Exact dict equality ошибочно отклоняла валидную модель; теперь только savedparameter finitefloats допускают rel1e-8/abs1e-12, структура/types/core recipe/metric tolerance остаются строгими. Root повторил actualDEVreload/helper PASS и corruption LR.051 reject;0новых fits/Baccess. Это дефект нового audit-path, не причина исходного v1qualityloss.

Prospective customer-lock builder SHA`ea0401342dae096b869ed75819835ce126be9ffb37dafbfaed581fd400a5622d` и executiondriver SHA`63fde8b130c6d4a7785264c5664820b229bba9879e6d2d81ca714229400397a6` прошли два independentreview, отдельный mockedCLI chain050–056. Они actualUNRUN. Новый concreteJSON отсутствует; reservedB-Y/counts/features по-прежнему не открывались. Перед первым targetSQL требуется actualeligibleL2 evidence и отдельно проверенный concrete lock, уже сохранённый Git вместе с точными19sources. Corecode/reports/config/oldlocks сохранены; remote/push/schedule отсутствуют.

## HM-R011: одна marginal-группа принята

Принято14:41UTC. OP028–040 завершены; оба source/metric audits PASS. Independent replay всех12savedtop12/fullY AP/Recall и18pairedcontrasts≤1e-12 занял8.782s. Проверены report/modelbytes/source/runtime/500GPUtrees/QCY и serialreceipts; originalDB/native scoring этим reviewer не повторялись. Root отдельно replay metadata-rule иprovenance до запуска L2, PASS.

| Добавление к index12 | Width всего дополнений | MAP Sep02 | MAP Sep09 | MarginalΔ Sep02 | MarginalΔ Sep09 | Eligible BOTH |
|---|---:|---:|---:|---:|---:|---|
| product_type_no | 23 | .0318727120 | .0321559947 | −.0022021241 | +.0001317302 | Нет |
| colour_group_code | 23 | .0342861231 | .0326467703 | +.0002112870 | +.0006225057 | Да |
| department_no | 24 | .0334491633 | .0317786166 | −.0006256728 | −.0002456479 | Нет |
| garment_group_no | 24 | .0331718355 | .0335298464 | −.0009030006 | +.0015055818 | Нет |

Actualgroup2decision выбрал `index_code + colour_group_code`:23дополнения,46total modelinputs. MarginalCI к index12: Sep02[−.0016407449,+.0019506547],Sep09[−.0014735294,+.0028848518]. Разность к M: +.0006104921/+.0014260814 (≈+1.81%/+4.57%), descriptiveCI[−.0018109415,+.0029463562]/[−.0010916588,+.0041069738]. Все интервалы включают0; это development candidate после поиска, не независимое доказательство gain. Garment имеет положительную mean marginalΔ, но не проходит BOTH; правило не выбирает просто лучшую одну неделю.

SHAs: decision`9f118eba7d34dfb3c0ae0226f86d634dd54b2649b9469978ff2ccbbcba7a9522`; audits`d1d1eb68f087dd5fba4b0936513cca90c494131c335704a101270b0a0dd472f3`/`c93acbe39f267674ecb9d7dcd473e04c6eaaa800575ba5807cf06cbcda63cb77`; contrasts`d625b9e65dd1f5fe30a3e6ef75931f952ebd60a7dde8d1d66d4e768335683879`/`f3c2e32250aec6373e01d3585c124c3183aac6b8841a7c882b62c1b72c8bf8ea`.

## Текущий checkpoint14:42UTC

Root47871 EXIT0/no pending; root74723 исполняет reviewed original L2-stage. Prospective plan`artifacts/hm-auto-v2/l2-plan.json` SHA`f42cd4222e320ff8c658fa9e422385f831999acb37b34f402c5006ed75aff778` создан и проверен ДО firstfit041. Зафиксированы M23/E46, exactL210 references и четыре новых L250 fits041–044, exact4arm audits045/046,6fixedcontrasts/week047/048 и decision049. Третья группа, новые widths/params/seeds не добавляются. До equallytunedpositiveBOTH B остаётся закрытым.

[W009](https://github.com/suprend/tlab-recsys-2026-task1/blob/archive-2026-10-25/docs/research-lab/hm-wave009.md) принята14:42:01UTC: NEW0/REFINE1/MERGE2, новыхadmissions0. Уточнение existingfinalinterpretation:2modelseeds не rerunfeaturesearch, sameL2grid не equalallsearchbudget, mixedseedpoints не новыйvetо, CIcross0 не equivalence, knownweekcustomerholdout не temporal/coldstart. Bootstrap условен на закреплённые модели/неделю, не покрывает всю trainingvariability. Counter0,nextdue15:27:01UTC or2acceptedrounds; finitecompletion отменяет future_due без расписания.

## HM-R012: симметричная регуляризация принята

Принято14:54UTC. OP041–049succeeded, root74723EXIT0. Оба source/metric audits PASS. Independent replay8savedtop12/fullY APRecall и12paired2000/seed2026 means/CI≤1e-12,5.984s. Проверены одинаковые trainingpopulations/inputs, actualGPU500d8/500trees/L2, sourcelegacy2/new5/runtime/model/reportbytepins, serialreceipts иprospectiveplanf42cd4 до041. Root независимо повторил metadata plan/groupchain/provenance иpurechoice, PASS. Нового B-access этим не было.

| Arm | L2 | MAP Sep02 | MAP Sep09 | Mean двух недель |
|---|---:|---:|---:|---:|
| M23 | 10 | .0336756310 | .0312206889 | .0324481600 |
| M23 | 50 | .0252640860 | .0303507510 | .0278074185 |
| E46 | 10 | .0342861231 | .0326467703 | .0334664467 |
| E46 | 50 | .0283350096 | .0311628687 | .0297489392 |

BothchooseL210, tunedE−M +.0006104921/+.0014260814. DescriptiveCI остаются[−.0018109415,+.0029463562]/[−.0010916588,+.0041069738], cross0. Practicaldevelopmentgate пройден; это ещё не независимый gain. InteractionD +.0024604316/−.0006139636 mixed иописателен, не заменяет gate. Этот опыт не проверял counterfactual старогоPVC12 приL250: условныйHM013 былsuperseded, не приписываем ему результат новогоE46.

SHAs: actualL2decision`2a58403d10f7250dcdba65659f91905632a5eb58f8824fbd5984c3d266ca8df2`; audits`530025db871dd1616605b16637e02ff36f7a56f59df9cce53c24365df8d4a931`/`4345b3a8a13943fb1588e425125c60ddfbcea7aa340567f599a11f8e54c51c46`; contrasts`ab46e51900f494fff52767081bd87452bb1cd296c740cf5a1ac639ff36afe482`/`8a5d0718d9ce8c2220544a7063bde5a4ba18523e70374ff1b6d4e1e8e00901d3`.

Checkpoint14:54UTC: после acceptedR012 root metadata-only builder создал `configs/datasets/hm-auto-holdout-lock.json` SHA`a04ef587b05c37f33694175d172ef47dc981242b84edf7cd0f4fd5f5b02ce3a1`. Actual`load_lock`PASS безDB/Parquetdecoding/Y/cache/model; ID-файлы проверены только по bytehash. Отдельный independentreview actualJSON идёт по92metadata/source snapshot, после него requiredlocalcommit до firsttargetSQL. Будут только4GPUfits M2026/M2027/E2026/E2027 и3fixedcontrasts, без tuning. Source19 уже сохранены903f27f/8b18418; source/84f/v1файлы неизменны. Bcollection/labels/targetcounts ещё отсутствуют; новыхheavyjobs нет. W009counter1,nextdue15:27:01UTC ornextacceptedround.

Checkpoint14:56UTC: independentactualJSONreviewPASS; all92metadata/sourcefiles fresh до/после, all19sources byte-equal committedHEAD903f27f. Reviewer actual`load_lock(explicitSHA)` инезависимый meanL2replayPASS; толькоopaqueID bytehash, никакого BParquetdecoding/DB/CBM/Y/cache. Root проверил полный JSON/diff и сохранил его отдельным localcommit`ed6ec35` в14:56UTC, до запуска050. SHAa04ef5 неизменен. Новыйroot2840 выполняет reviewedlockeddriver63fde8:050collect,051–054fourfixedfits,055independentaudit и056threecontrasts. Перед SQL driver сверяет committedJSON+19sources, all001–049success иотсутствие7futureoutputs. Исходы B не меняют решение; noextra fits/contrasts, одинheavyworker.


## HM-R013: итоговая пользовательская проверка принята, конечный проход завершён

Принято 18 октября 2026. OP050–056 succeeded; root2840 EXIT0 в 15:12:13 UTC. Все OP001–056 завершены, неизвестных/pending операций нет. Выполнены 28 новых development fits и четыре итоговых; два точных ручных reference fits переиспользованы. Условный HM013 не запускался. Дополнительный подбор по B не выполняется.

### Фиксация до целей и фактические данные

Lock `a04ef587b05c37f33694175d172ef47dc981242b84edf7cd0f4fd5f5b02ce3a1` и 19 исходных модулей проверены внутри commit `ed6ec35f41fd5fbf258d95f0bde50aeec139572f`, сохранённого в 14:56:07 UTC. OP050 prepared в 14:56:37.142274 UTC, после коммита. Конкретный план закрепил M23/E46, L2=10, пять обучающих недель Aug12/19/26/Sep02/Sep09, sampler26/train20k/20negative, seeds2026/2027 и три сравнения. Frozen source/config/locks после этого не менялись.

В B 20 000 запросов, 1 862 пользователя с покупками, 5 680 разных целевых пар; 849 целей входят в 120 кандидатов на запрос (~14.95%). Candidate digest `ed3ba50edbd78af2c5e699d7f95537d18b43ec0f3bca3c55f8a1b739cd087de9`, QCY `e12e7ce11959d170814fb1c9a3648b023e6f6da7d1c9068d8a3a2ad0e6f03210`. Это новая пользовательская когорта с известной историей той же уже известной Sep16–22 недели 2020, не новый temporal holdout и не cold-start.

### Результат без дополнительного выбора

| Arm | MAP@12 среди купивших | Recall@12 среди купивших |
|---|---:|---:|
| M2026 | 0.03327363305578934 | 0.06289384770856307 |
| M2027 | 0.03284701986792033 | 0.06336416596889206 |
| E2026 | 0.032479829643018224 | 0.05461733831836721 |
| E2027 | 0.031177715100000523 | 0.05691687968880009 |

Primary per-user mean AP по двум seeds: M=0.03306032646185483, E=0.03182877237150937, ΔE−M=−0.0012315540903454624 (−3.72517%). Парный bootstrap на Q+, 2 000 resamples/seed2026: 95% CI[−0.0031042859151498964; +0.0006203520925216481]. Gate `lower95>0` FALSE. Secondary seed26 Δ=−0.0007938034127711129, CI[−0.002514263326995892; +0.0010287955618701167]; seed27 Δ=−0.0016693047679198123, CI[−0.00453954917677358; +0.0011799624311723328]. Все интервалы включают ноль. Доказанного ухудшения или эквивалентности нет; контроль M23 сохраняется.

Выбор по direct MAP/grouping дал положительные development points, но выбранное E46 не подтвердило перенос на другую пользовательскую когорту. Возможный selection optimism не выделен как единственная причина. Два seeds не повторяют весь feature search; интервалы условны на конкретные модели/неделю и не охватывают всю training variability. Симметричный L2-grid не означает одинаковый полный search budget.

### Независимая проверка и контрольные суммы

OP055 source audit PASS за 35.843s независимо восстановил семь прежних history-only Q cohorts/exclusion union, reserved salt-Q, C0-Q120, fullY/labels/weights; проверил пять train manifest identities, четыре saved CBM metadata/500trees/core parameters и byte pins. Все формулы признаков и нативные scores заново не вычислялись.

Отдельный HM-R013 replay PASS за 4.313s: независимый код без metric helpers кампании проверил raw top12/fullY, AP с denominator min(12,fullY), Recall, per-user seedmean до bootstrap, четыре AP/Recall и три CI≤1e-12. Искусственные off-C/empty/precision/seedmean self-tests PASS. Проверены reservation ID triple/order/hash, fullQ/Y всех четырёх arms, 19 source/runtime, five train identities, четыре extended fit identities, byte hashes всех CBM/reports/Parquet, serial receipts и lock commit до OP050. Этот replay не открывал original DB и native CBM. Исходное C/Y подтверждено отдельным PASS source audit; глобальная корректность native top12 по всем 120 scores заново не устанавливалась, поскольку полные scores не пересчитывались.

Ключевые локальные артефакты и SHA256:

- `artifacts/hm-auto-v2/customer-test/collection/manifest.json`: `f85468ef8fe0af33b736c56e1350a9db74f08da9dee1fa3895f8c4d02b376dbb`.
- `artifacts/hm-auto-v2/customer-test/audit/report.json`: `c028cc548bcdc9b27c2e7ac9b30a2451943901829d43e60bdb850adec390edc5`.
- `artifacts/hm-auto-v2/customer-test/contrasts/report.json`: `30160cae47b54cdc69e92696998eb819fdbde731527ff5c00ff4a4d0c847683d`.
- M2026 report: `c2b0d151361075929baec6885164542a64612342497ac381e44c593c03d99841`; M2027: `3f6926462ceffa2f9be83696b7308bc1edcdf255ee54e73cbed8a3c22e95177c`.
- E2026 report: `422ffbd73f0374d7b79e7703f358fb2a5e32faa20e4129b3f85d121262383d66`; E2027: `53f972189957654058b9c5a34a4dcffa5453139155b6a6359d0e965a636526f2`.
- Независимый replay source: `D:/hm-r013-prepared-reviewer-0940x96_/replay_r013.py`, SHA `19b9dca4cceae76e6287d594ca3fb888ff1be9f0bd4ce4e54fc96a7f26c19bc6`; результат `D:/hm-r013-replay-oqvffhgk/result.json`, SHA `c6bac1af46ef3dab493288f3d53900a24ccfe710f5d59266c1008e817c719701`; полный mapping в соседнем `pins.json`.

Raw CSV/DB/ID/CBM/Parquet, reviewer temp и figures — необязательные локальные дополнения, исключённые из Git. Их пути фиксируют доступность на этой машине, не передачу на другую. Основные числа, правила и границы вывода записаны здесь; полный повтор из fresh clone пока не выполнен.

Финальное состояние: приняты R009–R013, W009counter2; конечный тест завершён, future_due отменён, новых запусков/волн/расписаний нет. Подтверждённый прирост для T-Lab не получен. Неиспользованный бюджет не расходуется на подбор по B; следующий исследовательский проход требует нового prospective протокола и независимой от этого отбора проверки.
