# Публичное воспроизведение018: ресурсный план и независимая проверка

Root принял два source-only design документа с явными уточнениями. CODE/runtime, установка нового CLI, setup, реальные fits и проверка будущих выходов ещё не разрешены. [План verifier: четыре точных оригинала](evidence/public018-verifier-design-v1/publication.json); [ресурсный план: пять оригиналов](evidence/public018-resource-design-v1/publication.json), включая preparation failure. Старые source/private artifact payloads по references не копировались. [Машиночитаемый overlay](public018-resource-and-verification-plans.json) отделяет принятые условия от исходных формулировок.

Предлагается одна новая инженерная попытка raw→fresh typed9 DB→15daily collections→две NEW fixed300tree B41/W44 модели→train/selection comparison. Train8–20/selection22–23; final25–31 не входит. V2 candidate заморожен для адресного CODE rereview, а не принят к исполнению; scientific recipe не меняется.

| Этап | Предложенные конечные пределы | Текущий статус |
|---|---|---|
| Offline fresh-clone/venv setup |300CPU/600wall/2GiB RSS, cache miss останавливает без download fallback|UNGRANTED, cache availability не проверена|
| Producer whole operation |4200CPU/3600wall/12GiB aggregate job RSS;2threads,2GBengine, aggregate16GiBspill;80GiB free scratch floor|DESIGN only, не measured peak/гарантия успеха|
| Отдельный independent output verifier |600CPU/900wall/8GiB RSS;2loads,2fullselection predicts,0fits|DESIGN only, adapter после V2schema, точный расход неизвестен|

Внутренний public-work envelope4050CPU/3400wall плюс150/200tail находятся внутри producer4200/3600 и не являются resettable grants.40GiB recipe floor не доказывает worst-case;331GiB observed free snapshot не резервирует диск. Нужно учесть одновременные gzip/raw/canonical CSV,DB/WAL,spill,Parquet,matrix/key/label/weight/chunk buffers,nativePool/quantization/model и сохранённые B rankings при W. Cooperative callbacks и2GBengine не дают hard RSS или полный external lifetime. Старые закрытые source7200/10800 и600/900 не переносятся; общего численного баланса018 не заявляется.

Root уточнил исходный resource prose: governing historical path — model_data/program_model_data через strong_baseline, не strong_model_data; relevance dtype int8, не uint8. Предложенный300CPU/300wall/1GiB zero-predict review покрывал бы лишь metadata; полный numerical/native output acceptance требует отдельного verifier дизайна600/900/8GiB с2predict. Предложенные namespace paths ещё не созданы и не выданы.

Verifier не импортирует producer prepare_matrix/rankings/evaluate/bootstrap. Он должен связать одно наблюдаемое concrete execution, две consumed native fit попытки и их возврат, новые CBMs, full exit/reap и external costs. JSON consumed сам по себе training не доказывает; разные CBM hashes не обязательны и тоже не доказательство. Проверяются все Q/C/fullY/types/order,полная B41-prefix W44,все матрицы и rowweights1/C,два native model metadata,все selection rawscores/ranks,4metric estimands и200фиксированных paired-user bootstrapdraws. Public CLI не зависит от старых private approvals/CBMs/TMP.

Опциональный internal canonical matrix_proof comparison с принятым историческим R2 report503c434 не требует старых binaries. Полная materialized-matrix parity не превращает sampled manual18 formula evidence в новое exhaustive source-formula proof. Source transport/adaptation и exact all-keyed output comparison остаются разными доказательствами.

Сохранены ошибки metadata preparation и Root first cap120000 assertion: известный bounded report160834B прошёл после исправления bound на256KiB. Это ошибка metadata checker, не приложение. Исправленная metadata writer success не считается runtime. TLAB018 partial/13из19, actual015/reportDONE; новые планы не добавляют canonical задач или условий качества.
