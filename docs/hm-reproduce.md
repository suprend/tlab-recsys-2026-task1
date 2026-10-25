# Воспроизведение H&M: данные, признаки и замороженное сравнение

Инструкция описывает повтор прежнего исследования H&M с ручной базой M23. В историческом [отчёте](writeup/REPORT.pdf) агент добавляет признаки к этой базе. Выполняйте команды из корня репозитория в PowerShell на Windows. Локальный запускатель и средства диагностики из исключённого из Git каталога `artifacts/` не нужны.

**Полный повтор этих команд в свежем клоне ещё не проверен**. Исходные данные, DB, CBM и построчные результаты не входят в Git. На другой системе метрики и файлы моделей могут отличаться. Проверенные результаты и ограничения находятся в [журнале H&M](hm-pilot.md), действующий протокол записан в [campaign config](../configs/datasets/hm-campaign.json).

Все выходные каталоги должны отсутствовать. На машине с уже проведённой кампанией приведённые пути заняты: используйте отдельный клон с новыми путями результатов либо заранее согласуйте изменение всех путей, включая будущий lock. Не удаляйте существующие результаты ради повтора. После ошибки остановитесь, прочитайте `report.json`/`manifest.json` и проверьте завершение процесса; для повтора задайте новый путь результата. Загрузчик не требует повторно скачивать уже проверенные исходные файлы.

## 1. Окружение и источник

Нужен Python 3.12; исходный запуск выполнен на Python 3.12.14. Создайте отдельное окружение, если `.venv` отсутствует:

```powershell
py -3.12 -m venv .venv
$Python = (Resolve-Path '.venv/Scripts/python.exe').Path
& $Python -m pip install -r configs/datasets/hm-requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed' }

function Invoke-Hm {
    param([Parameter(Mandatory)][string[]]$ProjectArgs)
    & $Python @ProjectArgs
    if ($LASTEXITCODE -ne 0) { throw "H&M command failed: $($ProjectArgs[0])" }
}

Invoke-Hm -ProjectArgs @('-m','unittest','discover','-s','tests','-p','test_hm*.py')
Invoke-Hm -ProjectArgs @('-m','scripts.hm_download','--config','configs/datasets/hm-source.json','--output','data/raw/hm')
Invoke-Hm -ProjectArgs @('-m','scripts.hm_eda','--raw-dir','data/raw/hm','--output','artifacts/hm-eda-repro')
$Database = 'artifacts/hm-eda-repro/audit.duckdb'
```

Используются оригинальные таблицы [H&M Kaggle](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations), загруженные через [Microsoft mirror](https://huggingface.co/datasets/microsoft/hnm-search-data). Зафиксированная ревизия и SHA256 указаны в [hm-source.json](../configs/datasets/hm-source.json). Используются только три CSV; синтетические поисковые запросы/qrels, изображения и чужие обработанные таблицы исключены. Правила использования и ограничения зеркала описаны в [источнике отчёта](hm-pilot.md#источник).

EDA сохраняет базу с типизированными полями и сводный отчёт. Для EDA заданы 2 потока, лимит SQL-памяти 4GB и временных файлов 32GB. Подготовка SQL и расчёт предсказаний на CPU используют 4 потока, лимит SQL-памяти 2GB и временных файлов 8GB; на диске результатов нужно минимум 10GiB свободного места. CatBoost/pandas могут потреблять память сверх лимита SQL. Число CPU-потоков не управляет обучением на GPU. Аудит и отдельный отбор PVC используют 2 потока; автоматический PVC после CatBoost.fit может использовать число потоков по умолчанию. Эти настройки не ограничивают жёстко RSS, суммарную загрузку CPU или VRAM.

## 2. Collections и общий fixed-fit вызов

Selection оценивается на 2–8 сентября; даты прогноза в обучающих примерах: 12/19/26 августа. Когорты 20k выбираются по прошлой 90-дневной активности с hash seed 2026. У всех сравниваемых моделей одинаковые кандидаты C0-Q120 и полный набор уникальных целей Y.

```powershell
$Collections = 'artifacts/hm-campaign/collections'
$Train3 = @('2020-08-12','2020-08-19','2020-08-26') | ForEach-Object { "$Collections/$_-c0q120" }
$SelectionCollection = "$Collections/2020-09-02-c0q120"

foreach ($Anchor in @('2020-08-12','2020-08-19','2020-08-26','2020-09-02')) {
    Invoke-Hm -ProjectArgs @('-m','scripts.hm_experiment','collect','--database',$Database,
        '--output',"$Collections/$Anchor-c0q120",'--anchor',$Anchor,'--users','20000',
        '--policy','C0-Q120','--wall-seconds','1800')
}

function Invoke-HmFit {
    param([string[]]$TrainingCollections, [string]$ValidationCollection,
        [string]$OutputDirectory, [string]$FeatureNames = '', [string]$Family = 'strong',
        [int]$Iterations = 500, [int]$Depth = 8, [int]$ModelSeed = 2026,
        [string]$DecisionLockPath = '', [string]$TaskType = 'GPU')
    $FitWall = if ($TaskType -eq 'GPU') { '1800' } elseif ($Iterations -eq 500 -and $Depth -eq 8) { '3600' } else { '1800' }
    $ProjectArgs = @('-m','scripts.hm_experiment','fit','--train') + $TrainingCollections + @(
        '--validation',$ValidationCollection,'--output',$OutputDirectory,
        '--iterations',"$Iterations",'--depth',"$Depth",'--seed',"$ModelSeed",
        '--train-users','20000','--negative-sample','20','--wall-seconds',$FitWall,'--task-type',$TaskType)
    if ($FeatureNames) { $ProjectArgs += @('--feature-names-file',$FeatureNames) }
    else { $ProjectArgs += @('--feature-set',$Family) }
    if ($DecisionLockPath) { $ProjectArgs += @('--decision-lock',$DecisionLockPath) }
    if ($TaskType -eq 'GPU') {
        $ExternalWall = [int]$FitWall + 60
        $ProjectArgs += @('--external-job-timeout-seconds',"$ExternalWall")
        Invoke-Hm -ProjectArgs (@('-m','scripts.hm_job','--timeout',"$ExternalWall",'--') + $ProjectArgs)
    } else { Invoke-Hm -ProjectArgs $ProjectArgs }
}
```

CPU/SQL проверяют лимиты времени во время работы; принудительное прерывание не гарантируется. У EDA нет параметра CLI для ограничения времени. GPU не поддерживает Python callbacks: вспомогательная функция запускает всё обучение на GPU через `scripts.hm_job` с внешним лимитом 1860с и заявленным лимитом 1800с для остальных стадий. Значение `--external-job-timeout-seconds` совпадает с `hm_job --timeout`; само указание лимита в обработчике эксперимента не ограничивает время. Ненулевой код завершения останавливает следующие шаги. Обёртка не ограничивает жёстко CPU/RSS/VRAM. Исторические лимиты CPU для depth8, 3600/3660с, не применяются к GPU. Запускайте по одному тяжёлому процессу.

## 3. Ручная GPU-сетка и фиксированный победитель

Историческая CPU-сетка 2 сохранена в коммите `7f69656`; CPU M4 также остаётся отдельным историческим результатом. Для текущего эксперимента GPU выбран по измеренной скорости **до обучения на сгенерированных признаках**, независимо от GPU/CPU MAP. Поэтому ниже выполняются те же шесть заранее заданных конфигураций на GPU, затем M_GPU выбирается по прежнему правилу MAP и разрешения равенств. Это отдельная серия запусков; она не повторяет CPU побайтно.

Настройки GPU заданы явно: `task_type=GPU`, device0, gpu_ram_part0.5, pinned_memory_size256mb, Bayesian/bootstrap, bagging_temperature1, border_count128, Plain boosting, CPU data/inference threads4. Обучение на GPU недетерминированно даже с фиксированным seed. Настройки CPU по умолчанию, MVS и 254 границы, не переносятся автоматически. Параметры и сетка закреплены в `manual_tuning_gpu` конфигурации. [Официальные GPU ограничения](https://catboost.ai/docs/en/features/training-on-gpu).

```powershell
$Campaign = Get-Content 'configs/datasets/hm-campaign.json' -Encoding UTF8 -Raw | ConvertFrom-Json
$Grid = @($Campaign.manual_tuning_gpu.candidate_configs)
foreach ($Recipe in $Grid) {
    $Family = if ($Recipe.features -eq 'manual_pilot') { 'pilot' } else { 'strong' }
    Invoke-HmFit -TrainingCollections $Train3 -ValidationCollection $SelectionCollection `
        -OutputDirectory "artifacts/hm-campaign/gpu-manual-grid/$($Recipe.name)" `
        -Family $Family -Iterations $Recipe.iterations -Depth $Recipe.depth
}
$GridFits = @($Grid | ForEach-Object { "artifacts/hm-campaign/gpu-manual-grid/$($_.name)" })
Invoke-Hm -ProjectArgs (@('-m','scripts.hm_result_audit','--validation',$SelectionCollection,'--fits') +
    $GridFits + @('--output','artifacts/hm-campaign/audits/gpu-manual-grid','--database',$Database,'--wall-seconds','1800'))
$ChooseGpu = @'
from pathlib import Path
import json
from scripts.hm_final_lock import read_json, digest
root = Path.cwd()
campaign = read_json(root/'configs/datasets/hm-campaign.json')
audit_path = root/'artifacts/hm-campaign/audits/gpu-manual-grid/report.json'
audit = read_json(audit_path)
if audit['status'] != 'PASS' or len(audit['fits']) != 6:
    raise ValueError('Complete independent six-arm GPU audit required')
recipes = campaign['manual_tuning_gpu']['candidate_configs']
choices = []
for arm, recipe in zip(audit['fits'], recipes):
    path = root/'artifacts/hm-campaign/gpu-manual-grid'/recipe['name']/'report.json'
    report = read_json(path)
    if arm['report_sha256'] != digest(path) or report['hyperparameters']['task_type'] != 'GPU':
        raise ValueError('Audited GPU grid order/identity differs')
    nfeatures = sum(len(report['features'][kind]) for kind in ('numeric','categorical'))
    key = (-arm['metrics']['map_at_12_conditional'], nfeatures, recipe['iterations'], recipe['depth'], recipe['name'])
    choices.append((key,recipe))
winner = min(choices,key=lambda item:item[0])[1]
print(json.dumps(dict(manual_recipe=winner['name'], manual_features=winner['features'],
    iterations=winner['iterations'], depth=winner['depth'], seed=2026, threads=4),indent=2))
'@
Invoke-Hm -ProjectArgs @('-c',$ChooseGpu)
```

Сохраните напечатанный объект в своём `hm-campaign.json` как `post_manual_gpu_execution` **до** `prepare`. Это замораживает победителя GPU-сетки: максимальный selection MAP, при равенстве выбираются меньшее число признаков, деревьев, depth, затем имя ASC. CPU/GPU MAP не используется для выбора CPU или GPU. В исходном эксперименте общую конфигурацию меняет координатор после независимой проверки. В самостоятельном повторе собственная сетка может выбрать другой рецепт; его нужно отразить в собственном протоколе, не выдавая за исторический результат.

```powershell
$Campaign = Get-Content 'configs/datasets/hm-campaign.json' -Encoding UTF8 -Raw | ConvertFrom-Json
$Winner = $Campaign.post_manual_gpu_execution
if ($null -eq $Winner) { throw 'Freeze the independently audited GPU winner before generated fits' }
$Reference = "artifacts/hm-campaign/gpu-manual-grid/$($Winner.manual_recipe)"
$FrozenRecipe = @{Iterations=[int]$Winner.iterations; Depth=[int]$Winner.depth}
```

Используется уже обученная победившая модель; повторно обучать базу на GPU не нужно. Код, окружение и настройки остаются одинаковыми для all/selected/random, confirmation и final. Не переизбирайте M по их оценкам. Исторические коллекции CPU принимаются при совпадении хешей файлов и неизменном коде расчёта признаков; это не разрешает смешивать CPU и GPU модели внутри одного контраста.

## 4. Генерация, training-only выбор и random controls

`prepare` фиксирует M и 53/58 допустимых программ относительно Strong34/Pilot23 и три случайных набора по 12 признаков с seeds 101/102/103 **до** all-fit. `select` читает только all-модель, рассчитывает PredictionValuesChange на обучающих данных в 2 потока и выбирает top12; validation Pool и оценки на валидации не используются для выбора имён. Формулы, число деревьев и ручной рецепт не подбираются заново.

```powershell
$Study = 'artifacts/hm-campaign/feature-study'
$Selection = 'artifacts/hm-campaign/feature-selection'
Invoke-Hm -ProjectArgs @('-m','scripts.hm_select_features','prepare','--manual-fit',$Reference,
    '--validation-collection',$SelectionCollection,'--output',$Study)
Invoke-HmFit @FrozenRecipe -TrainingCollections $Train3 -ValidationCollection $SelectionCollection `
    -OutputDirectory 'artifacts/hm-campaign/generated/all' -FeatureNames "$Study/all_names.json"
Invoke-Hm -ProjectArgs @('-m','scripts.hm_select_features','select','--study',$Study,
    '--all-fit','artifacts/hm-campaign/generated/all','--output',$Selection)
Invoke-HmFit @FrozenRecipe -TrainingCollections $Train3 -ValidationCollection $SelectionCollection `
    -OutputDirectory 'artifacts/hm-campaign/generated/selected' -FeatureNames "$Selection/selected_names.json"
foreach ($Seed in @(101,102,103)) {
    Invoke-HmFit @FrozenRecipe -TrainingCollections $Train3 -ValidationCollection $SelectionCollection `
        -OutputDirectory "artifacts/hm-campaign/generated/random$Seed" -FeatureNames "$Study/random${Seed}_names.json"
}
$SelectionFits = @($Reference,'artifacts/hm-campaign/generated/all','artifacts/hm-campaign/generated/selected',
    'artifacts/hm-campaign/generated/random101','artifacts/hm-campaign/generated/random102','artifacts/hm-campaign/generated/random103')
Invoke-Hm -ProjectArgs (@('-m','scripts.hm_result_audit','--validation',$SelectionCollection,'--fits') +
    $SelectionFits + @('--output','artifacts/hm-campaign/audits/selection','--database',$Database,'--wall-seconds','1800'))
```

Порядок `--fits` существенен: selection audit присваивает arm00=M,01=all,02=selected,03/04/05=random101/102/103. Все модели используют одну training/validation Q/C/Y, одинаковые выбранные iterations/depth и sampler; M34/all87/selected46 либо M23/all81/selected35 входов. Число обучений различается: all требует дополнительного обучения для PVC; его стоимость учитывается отдельно. Три случайных набора дают ограниченную проверку и не доказывают превосходство над любым случайным набором.

## 5. Диагностическая confirmation

Неделя 9–15 сентября уже использовалась в раннем пилоте. Поэтому результаты служат только диагностикой: по ним нельзя менять M, параметры, выбранные признаки, seeds или варианты итогового сравнения. All не переобучается; сравниваются M, selected и те же три случайных набора.

```powershell
$ConfirmationCollection = "$Collections/2020-09-09-c0q120"
Invoke-Hm -ProjectArgs @('-m','scripts.hm_experiment','collect','--database',$Database,'--output',$ConfirmationCollection,
    '--anchor','2020-09-09','--users','20000','--policy','C0-Q120','--wall-seconds','1800')
$Train4 = @($Train3) + @($SelectionCollection)
$Bundles = [ordered]@{M="$Study/M_names.json"; selected="$Selection/selected_names.json";
    random101="$Study/random101_names.json"; random102="$Study/random102_names.json"; random103="$Study/random103_names.json"}
foreach ($Name in $Bundles.Keys) {
    Invoke-HmFit @FrozenRecipe -TrainingCollections $Train4 -ValidationCollection $ConfirmationCollection `
        -OutputDirectory "artifacts/hm-campaign/confirmation/$Name" -FeatureNames $Bundles[$Name]
}
$ConfirmationFits = @($Bundles.Keys | ForEach-Object { "artifacts/hm-campaign/confirmation/$_" })
Invoke-Hm -ProjectArgs (@('-m','scripts.hm_result_audit','--validation',$ConfirmationCollection,'--fits') +
    $ConfirmationFits + @('--output','artifacts/hm-campaign/audits/confirmation','--database',$Database,'--wall-seconds','1800'))
```

Для этих двух проверок создайте спецификации без чтения данных и моделей. Затем `hm_contrasts` пересчитает разности по независимо проверенным выгрузкам пользовательских метрик. Здесь анализируются уже полученные оценки; дополнительного подбора нет:

```powershell
$DevelopmentSpecs = @'
from pathlib import Path
import json
from scripts.hm_final_lock import digest, read_json
root = Path.cwd()
directory = root / 'artifacts/hm-campaign/contrasts'
directory.mkdir(parents=True, exist_ok=True)
for phase, selected, randoms in [('selection', 'arm-02', ['arm-03','arm-04','arm-05']),
                                  ('confirmation', 'arm-01', ['arm-02','arm-03','arm-04'])]:
    audit_path = root / f'artifacts/hm-campaign/audits/{phase}/report.json'
    if read_json(audit_path)['status'] != 'PASS':
        raise ValueError('PASS audit required')
    contrasts = [dict(name='selected_minus_M', positive=[selected], negative=['arm-00']),
                 dict(name='mean_random3_minus_M', positive=randoms, negative=['arm-00']),
                 dict(name='selected_minus_mean_random3', positive=[selected], negative=randoms)]
    contrasts += [dict(name=f'selected_minus_random{seed}', positive=[selected], negative=[arm])
                  for seed, arm in zip((101,102,103), randoms)]
    if phase == 'selection':
        contrasts.append(dict(name='all_minus_M', positive=['arm-01'], negative=['arm-00']))
    with (directory / f'{phase}.spec.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(dict(audit_report_sha256=digest(audit_path), contrasts=contrasts), stream, indent=2, allow_nan=False)
        stream.write('\n')
'@
Invoke-Hm -ProjectArgs @('-c',$DevelopmentSpecs)
foreach ($Phase in @('selection','confirmation')) {
    Invoke-Hm -ProjectArgs @('-m','scripts.hm_contrasts','--audit-dir',"artifacts/hm-campaign/audits/$Phase",
        '--spec',"artifacts/hm-campaign/contrasts/$Phase.spec.json",'--output',"artifacts/hm-campaign/contrasts/$Phase",'--wall-seconds','120')
}
```

Используется парный bootstrap по пользователям с положительными целями: percentile95, 2000 выборок, seed2026. Модели и неделя фиксированы. Для mean random3 сначала усредняются AP трёх моделей внутри пользователя, затем повторно выбираются пользователи. Selection остаётся разведочным этапом с учётом предыдущих решений; confirmation не становится независимым итоговым тестом.

## 6. Decision lock до любого final collection/fit

Сначала завершите все проверки этапов разработки. Затем зафиксируйте конфигурацию эксперимента, исходники и окружение на весь итоговый этап. Исторический `configs/datasets/hm-final-lock.json`, если он есть в клоне, сохраняется как свидетельство исходного запуска. Для нового повтора ниже создаётся отдельный `hm-final-lock-repro.json`; он не перезаписывает исторический контракт и также должен отсутствовать. Код ниже читает только JSON и потоково считает SHA файлов; он не подключается к DB и не загружает модели. Он сохраняет **полную** схему, проверяемую `hm_final_lock.load_lock`. Код останавливается, если нет входных файлов, аудит не получил PASS, изменился study или уже существуют итоговые результаты. Он создаёт локальный контракт нового повтора и не восстанавливает отсутствующие исторические файлы.

Список M берётся из отчёта победителя GPU-сетки. Порядок selected numeric/categorical берётся из отчёта обученной selected-модели и сверяется с selected names/registry. Параметры берутся из M_GPU; seed модели исключается из общей конфигурации, а два итоговых seeds фиксируются отдельно. Хеши будущих итоговых файлов ещё неизвестны: lock фиксирует идентичность исходных данных, схему признаков и пути. Созданный позже манифест добавит фактические хеши Q/C/Y и SHA lock; сам lock не переписывается.

```powershell
$DecisionLock = 'configs/datasets/hm-final-lock-repro.json'
$LockCode = @'
from copy import deepcopy
from pathlib import Path
import json
import sys
from scripts import hm_final_lock as gate

root = Path.cwd().resolve()
def need(condition, message):
    if not condition:
        raise ValueError(message)
def read(name):
    return gate.read_json(root / name)
def ref(name):
    return dict(path=name, sha256=gate.digest(root / name))

campaign_path = 'configs/datasets/hm-campaign.json'
campaign = read(campaign_path)
post = campaign['post_manual_gpu_execution']
manual_path = 'artifacts/hm-campaign/gpu-manual-grid/' + post['manual_recipe'] + '/report.json'
study_path = 'artifacts/hm-campaign/feature-study/manifest.json'
selection_path = 'artifacts/hm-campaign/feature-selection/manifest.json'
confirmation_path = 'artifacts/hm-campaign/audits/confirmation/report.json'
manual, study, selected = map(read, (manual_path, study_path, selection_path))
selected_fit = read('artifacts/hm-campaign/generated/selected/report.json')
for phase in ('gpu-manual-grid', 'selection', 'confirmation'):
    need(read(f'artifacts/hm-campaign/audits/{phase}/report.json')['status'] == 'PASS', 'PASS development audits required')
need(manual['status'] == selected_fit['status'] == 'completed', 'Complete reference/selected fits required')
need(all(m['training_user_limit'] == 20000 and m['negative_sample'] == 20 and m['sampling_seed'] == 2026
         for m in (manual, selected_fit)), 'Frozen development training policy required')
need(study['status'] == 'prepared' and selected['status'] == 'selected', 'Prepared study and selection required')
need(selected['study']['manifest_sha256'] == gate.digest(root/study_path), 'Study byte identity changed')
need(study['plan']['manual_fit']['report_sha256'] == gate.digest(root/manual_path), 'Manual reference changed')
names_path = 'artifacts/hm-campaign/feature-selection/selected_names.json'
need(gate.digest(root/names_path) == selected['files']['selected_names.json'], 'Selected names changed')
need(read(names_path) == selected['names'], 'Selected name order changed')
need(selected['names'] == selected['manual_names'] + selected['selected_programs'], 'Unexpected selected bundle')
need(len(selected['selected_programs']) == 12, 'Exactly twelve selected programs required')

anchors = campaign['final']['train_anchors']
need(anchors == gate.ANCHORS, 'Five fixed training weeks required')
collections = [f'artifacts/hm-campaign/collections/{anchor}-c0q120/manifest.json' for anchor in anchors]
manifests = [read(name) for name in collections]
database = manifests[0]['database']
contract = manifests[0]['features']
need(all(m['database'] == database and m['features'] == contract for m in manifests), 'Training source/schema mismatch')
source = Path(sys.argv[1]).resolve()
need(dict(sha256=gate.digest(source), bytes=source.stat().st_size) == database, 'Original DB bytes changed')
need(contract['digest'] == selected['feature_contract_digest'], 'Feature definitions changed')
registry = {entry['name']: entry['kind'] for entry in contract['registry']}
selected_features = {kind: [name for name in selected['names'] if registry[name] == kind]
                     for kind in ('numeric', 'categorical')}
manual_features = {kind: manual['features'][kind] for kind in ('numeric', 'categorical')}
need(selected_fit['features'] == dict(selected_features, contract_digest=contract['digest']), 'Actual selected fit order/schema mismatch')
need(selected['manual_names'] == manual_features['numeric'] + manual_features['categorical'], 'Manual input order mismatch')
need(post['manual_features'] in ('manual_pilot','strong_manual'), 'Declared manual feature set required')
need(set(manual_features['numeric'] + manual_features['categorical']) ==
     set(contract['feature_sets'][post['manual_features']]), 'Frozen manual feature set differs')
need(post['seed'] == 2026 and post['threads'] == 4, 'GPU model seed/thread recipe differs')
params = deepcopy(manual['hyperparameters'])
need(params.pop('random_seed') == 2026, 'Reference model seed changed')
need(params['iterations'] == post['iterations'] and params['depth'] == post['depth']
     and params['thread_count'] == 4 and params['task_type'] == 'GPU', 'Frozen GPU reference recipe changed')
need(selected_fit['hyperparameters'] == manual['hyperparameters'] and selected_fit['code'] == manual['code']
     and selected_fit['runtime'] == manual['runtime'], 'Selected fit must share manual recipe/source/runtime')
runtime = gate.runtime_identity()
need(runtime == manual['runtime'], 'Current runtime differs from development')
code_names = ('hm_experiment.py', 'hm_baseline.py', 'hm_retrieval.py', 'hm_feature_engine.py',
              'hm_result_audit.py', 'hm_final_lock.py', 'hm_select_features.py', 'hm_contrasts.py', 'hm_job.py')
code = {name: gate.digest(root/'scripts'/name) for name in code_names}
need(all(code[name] == value for name, value in manual['code'].items()), 'Manual producer source changed')

outputs = dict(collection='artifacts/hm-campaign/collections/2020-09-16-c0q120',
    fits=[f'artifacts/hm-campaign/final/{arm}' for arm in ('M2026','M2027','selected2026','selected2027')],
    audit='artifacts/hm-campaign/audits/final')
need(all(not (root/name).exists() for name in [outputs['collection'], *outputs['fits'], outputs['audit']]),
     'Final outputs already exist; inspect their receipts instead of creating another lock')
document = dict(format='hm-final-decision-lock-v1', campaign=ref(campaign_path),
    provenance=dict(manual=ref(manual_path), selection=ref(selection_path), confirmation=ref(confirmation_path)),
    database=database, feature_digest=contract['digest'], implementation=dict(code=code, runtime=runtime),
    final=dict(anchor='2020-09-16', horizon_days=7, policy='C0-Q120', users=20000, cohort_seed=2026,
               sampling_seed=2026, train_users=20000, negative_sample=20),
    train_collections=[ref(name) for name in collections],
    features=dict(M=manual_features, selected=selected_features), hyperparameters=params,
    outputs=outputs, contrasts=deepcopy(gate.CONTRASTS))
destination = (root/sys.argv[2]).resolve()
need(destination.is_relative_to(root/'configs/datasets'), 'New lock must stay in configs/datasets')
with destination.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write('\n')
lock = gate.load_lock(destination)
print(json.dumps(dict(status='locked', path=destination.relative_to(root).as_posix(), sha256=lock.sha256)))
'@
Invoke-Hm -ProjectArgs @('-c',$LockCode,$Database,$DecisionLock)
```

Не исправляйте отклонённый lock с учётом увиденных итоговых оценок. До доступа к итоговому этапу ошибки входов можно исправить: объясните причину, сохраните неуспешный файл и создайте новый контракт с новыми путями результатов. После lock не меняйте закреплённые конфигурации, код и свидетельства происхождения: любое изменение байтов приведёт к отказу. Результаты можно описывать в других файлах; это не меняет закреплённые файлы.

## 7. Единственный final: четыре модели и фиксированные контрасты

```powershell
$FinalCollection = "$Collections/2020-09-16-c0q120"
Invoke-Hm -ProjectArgs @('-m','scripts.hm_experiment','collect','--database',$Database,'--output',$FinalCollection,
    '--anchor','2020-09-16','--users','20000','--policy','C0-Q120','--wall-seconds','1800','--decision-lock',$DecisionLock)
$Train5 = @($Train4) + @($ConfirmationCollection)
foreach ($Arm in @('M','selected')) {
    $FeatureNames = if ($Arm -eq 'M') { "$Study/M_names.json" } else { "$Selection/selected_names.json" }
    foreach ($ModelSeed in @(2026,2027)) {
        Invoke-HmFit @FrozenRecipe -TrainingCollections $Train5 -ValidationCollection $FinalCollection `
            -OutputDirectory "artifacts/hm-campaign/final/$Arm$ModelSeed" -FeatureNames $FeatureNames `
            -ModelSeed $ModelSeed -DecisionLockPath $DecisionLock
    }
}
$FinalFits = @('M2026','M2027','selected2026','selected2027') | ForEach-Object { "artifacts/hm-campaign/final/$_" }
Invoke-Hm -ProjectArgs (@('-m','scripts.hm_result_audit','--validation',$FinalCollection,'--fits') +
    $FinalFits + @('--output','artifacts/hm-campaign/audits/final','--database',$Database,
    '--wall-seconds','1800','--decision-lock',$DecisionLock))

$FinalSpecCode = @'
from pathlib import Path
import json
import sys
from scripts import hm_final_lock as gate
root = Path.cwd()
lock = gate.load_lock(sys.argv[1])
audit_path = root/'artifacts/hm-campaign/audits/final/report.json'
if gate.read_json(audit_path)['status'] != 'PASS':
    raise ValueError('PASS final audit required')
spec = dict(audit_report_sha256=gate.digest(audit_path), contrasts=lock.data['contrasts'])
with (root/'artifacts/hm-campaign/contrasts/final.spec.json').open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(spec, stream, indent=2, allow_nan=False)
    stream.write('\n')
'@
Invoke-Hm -ProjectArgs @('-c',$FinalSpecCode,$DecisionLock)
Invoke-Hm -ProjectArgs @('-m','scripts.hm_contrasts','--audit-dir','artifacts/hm-campaign/audits/final',
    '--spec','artifacts/hm-campaign/contrasts/final.spec.json','--output','artifacts/hm-campaign/contrasts/final','--wall-seconds','120')
```

Итоговая проверка сохраняет четыре выгрузки пользовательских метрик с хешами. Эвристические, случайные и post-hoc сравнения не добавляются. Основной контраст сравнивает selected с M: сначала усредняются AP двух seeds модели **внутри пользователя**, затем выполняется парный bootstrap по пользователям. Также сообщаются два заранее заданных контраста по отдельным seeds. Предсказания моделей не объединяются; зависимые строки user×seed не используются как независимые наблюдения bootstrap. Неудачный или отрицательный результат не разрешает подобрать другие признаки, seed, число деревьев или очередную final-неделю.

В итог перенесите фактические количества Q/Q+/Y/C, MAP/Recall, oracle/coverage, seeds/CI, затраты и версии из отчётов и аудитов со статусом PASS. Проверка saved-top12 сверяет порядок внутри выгрузки, принадлежность элементов, полный Y и метрики, но не пересчитывает все оценки моделей. Локальный MAP получен на выборке пользователей с прошлой активностью и другой неделе; напрямую сравнивать его с таблицей лидеров Kaggle нельзя. Исходные данные и построчные файлы остаются локальными и не входят в Git; сводные выводы и команды должны оставаться в отчёте под Git.
