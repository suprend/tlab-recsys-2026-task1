# HM-W004: объяснимость фиксированного отбора

Принято 2026-10-18T11:40:24.344850+00:00 после независимых FIRST A/B и отдельного скептика. Предыдущий next_due11:43:22.210762UTC; волна выполнена заранее. Следующая — 2026-10-18T12:25:24.344850+00:00 / 2026-10-18T15:25:24.344850+03:00 либо после двух принятых эмпирических раундов; счётчик0. Общий предел времени/раундов не задан.

## Наблюдения

Шесть ручных recipes прошли независимый audit OP020 PASS. Выбран Strong34/500d8, MAP .0345144793. M−pilot150 Δ+.00062076 CI включает0, M−recency+.00540886 описательный CI положительный. Все выводы development. CPU4 amendment фиксирует прежний рецепт независимо от свежего M4 MAP; OP021 выполняется на source8c0bbdb9/commit58440f6 после113root tests и независимого source review. Final не оценён.

## Независимые FIRST и критика

A (`hm_wave003_mechanism`) не предложил новых проверок. Подпись «эффект feature recipe зависит от capacity → различающиеся matched-budget Δ → шесть сохранённых fits» совпадает с W002A/HM005/HM007. Фактические Strong−Pilot Δ:150d6 −.00101979544,500d6 +.00126209398,500d8 +.00141609515. Это описательная смена знака, не статистически установленная interaction/causal mechanism; информационный состав и представление признаков не разделены.

B (`hm_wave003_validity`) предложил optional reporting refinement B1 для HM006/HM007: из уже сохраняемого selector manifest показать selected12 с определениями/окнами/training PVC, exact-zero counts, значения12-го/13-го элементов и точный tie. Механизм: коррелированные признаки могут делить использование, tie частично разрешается nameASC. Минимальный тест — чтение frozen study/selection JSON и сверка names/ranking/digests с importanceDESC,nameASC;0fits/DB/model calls. При любом исходе width12/names/selector неизменны, новый threshold не появляется. Ноль PVC не доказывает отсутствие информации; gap не устанавливает стабильность или gain. B2: последующие contrasts только с новым M4, возможное отличие M2→M4 не позволяет перевыбирать recipe; это дубликат post-manual contract.

Отдельный `hm_wave003_skeptic` проверил фактические aggregate audit/source/config/docs и подтвердил **NEW0 / REFINE1 / MERGE3 / REJECT0 / scientific ADMIT0**. REFINE/MERGE пересекаются на B1; дополнительных fits/gates0. A merge→W002A/HM005/HM007; B1 merge→W003B2/HM006/HM007; B2 merge→действующий контракт.

Скептик уточнил границу B1: manifest хранит численные PVC только для eligible53 в pool_ranking, а importance_model_order содержит87имён без всех87значений. Поэтому число нулей подписывается **среди eligible53 / среди selected12**; model-wide87 zeros не сообщаются и отдельный вызов PVC не требуется. Exact tie определяется до округления по сохранённым числам. Фактическая длительность будущего чтения пока не измерена.

## Решение

Core: завершить/проверить M4 → prepare pool/random до M+all → training-only PVC12 → selected/random controls → diagnostic confirmation → fixed final M/selected×2026/27. B1 выполняется попутно либо откладывается без блокировки core. Отрицательный/inconclusive final завершает исходное исследование, новых обязательных ветвей нет.
