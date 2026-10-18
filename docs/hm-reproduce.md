# Воспроизведение H&M: данные, признаки и замороженное сравнение

Это последовательность canonical CLI из корня репозитория для PowerShell на Windows. Она не требует PersonalOS, локального launcher или диагностического harness из ignored `artifacts/`. Агент на рабочей машине запускал Python через PersonalOS `pas.ps1` и отдельный project-venv subprocess; это особенность его окружения, а не зависимость проекта.

Команды ниже **не являются отчётом об их выполнении в свежем clone**. Такой полный повтор ещё не проверен. Исходные данные, DB, CBM и построчные результаты не входят в Git. Совпадение метрик до последнего знака и побайтное равенство моделей на другой системе не обещаются. Проверенные результаты и ограничения находятся в [отчёте](hm-pilot.md), действующий протокол — в [campaign config](../configs/datasets/hm-campaign.json).

Все выходные каталоги должны отсутствовать. На машине с уже проведённой кампанией приведённые пути заняты: используйте отдельный checkout с новыми outputs либо заранее согласованно измените весь набор путей, включая будущий lock. Не удаляйте существующие результаты ради повтора. После ошибки остановитесь, прочитайте `report.json`/`manifest.json` и проверьте завершение процесса; повтор получает новый output. Скачать уже проверенные raw-файлы повторно downloader не требует.

## 1. Окружение и источник

Нужен установленный Python 3.12; измеренная среда использовала Python 3.12.14. Создайте отдельное окружение, если `.venv` отсутствует:

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

Источник — оригинальные таблицы [H&M Kaggle](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations), транспорт — [Microsoft mirror](https://huggingface.co/datasets/microsoft/hnm-search-data), pinned revision и SHA256 — в [hm-source.json](../configs/datasets/hm-source.json). Используются только три CSV; synthetic search queries/qrels, изображения и чужие processed-таблицы исключены. Правила использования и ограничения зеркала описаны в [источнике отчёта](hm-pilot.md#источник).

EDA сохраняет typed DB и агрегированный отчёт. EDA использует2 потока, SQL cap4GB и spill cap32GB. SQL/подготовка и CPU inference experiment runner используют4 потока, SQL cap2GB, spill cap8GB и минимум10GiB свободного места на output volume; CatBoost/pandas могут потреблять память сверх SQL cap. Собственное GPU обучение не управляется этим CPU thread count. Audit и отдельный PVC selector используют2 потока; внутренний auto-PVC после CatBoost.fit может использовать свой default thread count. Это не hard RSS/aggregate CPU/VRAM containment.

## 2. Collections и общий fixed-fit вызов

Selection оценивается на2–8 сентября с train anchors12/19/26 августа. Когорты20k выбираются по прошлой90-дневной активности и hash seed2026. Candidates C0-Q120 и полный distinct Y сохраняются общими для всех сравниваемых моделей.

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

CPU/SQL deadlines cooperative; у EDA нет CLI wall-time параметра. GPU не поддерживает Python callbacks: helper запускает все GPU fits через canonical `scripts.hm_job` с внешним wall1860с и декларацией1800с для остальных стадий. Значение `--external-job-timeout-seconds` совпадает с `hm_job --timeout`; декларация в самом experiment runner не является ограничителем. Ненулевой exit code останавливает следующие шаги. Wrapper не задаёт hard CPU/RSS/VRAM cap. Исторический CPU depth8 envelope3600/3660с не применяется к GPU. Операции дорогие, запускайте один heavy worker за раз.

## 3. Ручная GPU-сетка и фиксированный победитель

Историческая CPU-сетка2 сохранена в commit `7f69656`; CPU M4 также остаётся отдельным историческим результатом. Активная кампания выбрала GPU по измеренной скорости **до любых generated fits**, независимо от сравнения GPU/CPU MAP. Поэтому ниже выполняются те же шесть finite recipes на одном GPU backend, затем M_GPU выбирается прежним правилом MAP/ties. Это новая backend-ветвь, а не побайтное повторение CPU.

GPU recipe явный: `task_type=GPU`, device0, gpu_ram_part0.5, pinned_memory_size256mb, Bayesian/bootstrap, bagging_temperature1, border_count128, Plain boosting, CPU data/inference threads4. GPU обучение недетерминированно даже с фиксированным seed; CPU defaults MVS и254 borders не переносятся молча. Параметры и grid закреплены в `manual_tuning_gpu` config. [Официальные GPU ограничения](https://catboost.ai/docs/en/features/training-on-gpu).

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

Сохраните напечатанный объект в своём `hm-campaign.json` как `post_manual_gpu_execution` **до** `prepare`. Это замораживает победителя GPU-сетки: максимальный selection MAP, ties — меньше features, деревьев, depth, имя ASC. CPU/GPU MAP не используется для выбора backend. В измеренной кампании единственный общий config меняет координатор после проверки аудитора. В самостоятельном повторе собственная сетка может выбрать другой рецепт; его нужно отразить в собственном протоколе, не выдавая за исторический результат.

```powershell
$Campaign = Get-Content 'configs/datasets/hm-campaign.json' -Encoding UTF8 -Raw | ConvertFrom-Json
$Winner = $Campaign.post_manual_gpu_execution
if ($null -eq $Winner) { throw 'Freeze the independently audited GPU winner before generated fits' }
$Reference = "artifacts/hm-campaign/gpu-manual-grid/$($Winner.manual_recipe)"
$FrozenRecipe = @{Iterations=[int]$Winner.iterations; Depth=[int]$Winner.depth}
```

Победивший fit используется напрямую: нового GPU reference fit нет. Один source/runtime/recipe сохраняется для all/selected/random, confirmation и final. Не переизбирайте M по их scores. Исторические CPU collections принимаются по закреплённым byte hashes и неизменному pure feature engine; это не разрешает смешивать CPU и GPU модели внутри одного контраста.

## 4. Генерация, training-only выбор и random controls

`prepare` фиксирует M и53/58 допустимых программ относительно Strong34/Pilot23 и три случайных набора12 с seeds101/102/103 **до** all-fit. `select` читает только all-модель, применяет training-derived PredictionValuesChange с2 потоками, выбирает top12; validation Pool и validation scores для выбора имён не используются. Формулы, число деревьев и ручной рецепт не подбираются заново.

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

Порядок `--fits` существенен: selection audit присваивает arm00=M,01=all,02=selected,03/04/05=random101/102/103. Все модели используют одну training/validation Q/C/Y, одинаковые выбранные iterations/depth и sampler; M34/all87/selected46 либо M23/all81/selected35 входов. Число fit-вариантов различается: all — дополнительный fit для PVC; его стоимость учитывается отдельно. Три random draws — ограниченный контроль, а не доказательство превосходства над любым случайным набором.

## 5. Диагностическая confirmation

Неделя9–15 сентября уже встречалась в раннем пилоте. Здесь это диагностика без изменения M, параметров, selected names, seeds или final arms по полученным scores. All не переобучается; сравниваются M, selected и те же три random bundles.

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

Для этих двух development audits создайте specs без чтения данных/моделей; then `hm_contrasts` пересчитывает разности из независимо проверенных per-user exports. Это анализ уже выполненных оценок, не дополнительный подбор:

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

Bootstrap — paired positive-user percentile95,2000 draws seed2026, условный на фиксированных моделях и неделе. Для mean random3 сначала усредняются AP трёх моделей внутри пользователя, затем ресэмплируются пользователи. Selection после предыдущих решений остаётся exploratory; confirmation не превращается в независимый final.

## 6. Decision lock до любого final collection/fit

Сначала завершите и проверьте все development audits. Затем заморозьте текущий campaign config, исходники и окружение на весь final. Исторический `configs/datasets/hm-final-lock.json`, когда он присутствует в clone, сохраняется как свидетельство исходного запуска. Для нового повтора ниже создаётся отдельный `hm-final-lock-repro.json`; он не перезаписывает исторический контракт и также должен отсутствовать. Следующий bounded metadata-only snippet читает JSON и потоковые SHA файлов; не соединяется с DB и не загружает модели. Он сохраняет **полную** схему, проверяемую `hm_final_lock.load_lock`. При отсутствии входов, не-PASS audit, изменённом study или существующих final outputs останавливается. Это создание нового локального контракта данного повтора, не восстановление отсутствующих исторических файлов.

Список M берётся из report победителя GPU-сетки, порядок selected numeric/categorical — из фактически обученного selected report и сверяется с selected names/registry. Параметры берутся из M_GPU, model seed исключается из общего recipe; два final seeds фиксируются отдельно. Будущие final cache hashes ещё неизвестны: lock фиксирует source/schema/paths; produced manifest позже прикрепит actual Q/C/Y hashes и SHA lock, сам lock не переписывается.

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

Не исправляйте не прошедший lock по увиденным final scores. До final доступа ошибки входов исправляются с явным объяснением, сохранением неуспешного файла и новым контрактом/output-набором. После lock не меняйте закреплённые config/code/provenance files; даже изменение их байтов приведёт к отказу. Документирование результатов в других файлах разрешённые identities не меняет.

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

Final audit оставляет четыре hashed per-user exports и не добавляет heuristic/random/posthoc comparisons. Основной контраст — selected против M: сначала среднее AP двух model seeds **внутри пользователя**, затем paired user bootstrap. Также сообщаются два заранее фиксированных seed-specific контраста. Это не score ensemble и не bootstrap по зависимым user×seed строкам. Неудачный или отрицательный результат не разрешает подобрать другие признаки, seed, число деревьев или очередную final-неделю.

В итог перенесите actual Q/Q+/Y/C counts, MAP/Recall, oracle/coverage, seeds/CI, затраты и версии из PASS audits/reports. У saved-top12 audit есть граница: он сверяет порядок внутри экспорта, membership, полный Y и метрики, но не пересчитывает все model scores заново. Local MAP на sampled history-active аудитории и другой неделе не является Kaggle leaderboard benchmark. Raw/post-row файлы остаются локальными ignored дополнениями; агрегированные выводы и необходимые команды должны оставаться в tracked отчёте.
