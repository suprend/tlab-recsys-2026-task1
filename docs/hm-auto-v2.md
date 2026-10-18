# H&M v2: почему расширение признаков хуже и как улучшить автоматизацию

Старт 2026-10-18T13:27:46.654222+00:00. Пользователь явно поручил диагностировать отрицательный результат v1 и попробовать улучшить автоматизацию для T-Lab. Предыдущее предпочтение «нет пределп» сохраняет отсутствие общей time/round границы. Этот проход имеет конечный протокол: максимум30 development fits и4 новых customer-test fits; неиспользованный бюджет не превращается в дополнительные попытки до положительного результата. Минимальный полезный результат — различить хотя бы один механизм и проверить автоматическую процедуру, которая может отказаться от неподтверждённых дополнений. Улучшение не обещается.

Исторический [итог v1](hm-report.md), его код, config и decision lock сохраняются побайтно. Новые модули, конфигурации и outputs имеют отдельные имена. [Протокол v2](../configs/datasets/hm-auto-v2.json) закреплён до первых новых fits; SHA84f3e2db341358a72ae7938c90af0696f5926b91faba746f61b801a7f7cd8b8b. Единственная исполнимая очередь — [backlog](backlog.md), журнал — [brainstorm log](research-lab/brainstorm-log.md). Исполнитель — текущий активный чат/root, без расписаний, paid APIs, публикаций, push или submission.

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
