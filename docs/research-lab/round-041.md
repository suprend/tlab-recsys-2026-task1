# Round041 — переносимость исполнения, а не только feature programs

**Статус: документационный аудит и предложения; запусков, тестов, установок, обучения и новых разрешений нет.** Проверены опубликованные принятые runners и hardware plan; рабочие изменения019/016 не исследовались. [README](../../README.md) описывает Mac36ГБ как исходную машину и Windows32ГБ/RTX3070 как будущую возможность после измерения. Это намерение не доказывает переносимость lifecycle, telemetry или обученной модели.

## Что действительно переносится

Логический контракт признаков — typed AST, raw-event bag, строгий past, Q/C, правила metadata/NULL/coverage и физическая схема — можно проверять независимо от ОС. Совпадение keyed integer counts при одинаковых исходных отношениях является разумным требованием будущего adapter proof. Из этого не следуют одинаковые wheel, process counters, пути, расход памяти, скорость или побитовое равенство обученных predictions. Программа и backend исполнения имеют разные обязательства.

Фактическая среда MacCPU описана в [cpu-environment](../experiments/cpu-environment.md). В принятых [anchor_pilot](../../scripts/anchor_pilot.py) и [verify_development](../../scripts/verify_development.py) `resource` импортируется обязательно. Python3.12 предоставляет этот модуль только на Unix. Поэтому current Windows runner неподдерживаем уже на границе импорта; наличие Windows CatBoost этого не исправляет. Это установленный по коду предел, не результат сегодняшнего Windows запуска. [Python resource](https://docs.python.org/3.12/library/resource.html).

| Среда | Документированная возможность | Текущая граница доказательства |
|---|---|---|
| MacCPU | Принятые локальные runners, две нити в принятых вычислительных путях | Acceptance относится к закреплённым версиям и конкретным проверенным путям |
| LinuxCPU | Unix resource/POSIX API позволяют построить похожий backend | Нет проведённого здесь conformance proof; RSS units отличаются |
| WindowsCPU | CatBoost публикует Windows wheels | Текущий обязательный resource import и POSIX lifecycle требуют отдельного adapter review |
| WindowsGPU | Библиотека документирует CUDA-сборки | Ни GPU availability, ни текущая policy/settings/model equivalence не доказаны |

[CatBoost platform table](https://catboost.ai/docs/en/installation/python-installation-method-pip-install) различает CPU-only macOS wheels и CUDA-enabled Linux/Windows wheels. Она не подтверждает установленную конфигурацию будущего ПК. GPU-обучение недетерминировано из-за порядка floating-point суммирования; CPU/GPU также имеют различия параметров и defaults. Поэтому замена `task_type` создаёт новый экспериментальный вопрос, а не перенос уже принятого результата. [CatBoost FAQ](https://catboost.ai/docs/en/concepts/faq).

## CPU и RSS имеют разные области учёта

Принятый RSS helper оставляет Darwin значение без множителя, остальные платформы умножает на1024. Современный официальный XNU man source определяет `ru_maxrss` в bytes; Linux man page — в KiB. Старый архивный Apple man page с kilobytes противоречит современному источнику, поэтому его нельзя использовать как подтверждение текущей единицы. Ветка «всё кроме Darwin» сама по себе не доказывает единицы любого другого Unix. Будущий backend должен иметь явный platform/unit contract и отклонять неизвестную комбинацию. [Apple XNU](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/man/man2/getrusage.2), [Linux getrusage](https://man7.org/linux/man-pages/man2/getrusage.2.html).

`ru_maxrss` — process high-water mark: его нельзя складывать по стадиям или обнулять вычитанием начального peak. Linux CHILDREN RSS означает максимум крупнейшего ребёнка, не суммарный пик дерева. Следовательно, parent+child peak sum может быть консервативной policy bound при объявленной последовательности, но не измерением одновременного resident footprint всего job. Для нескольких живых процессов требуется отдельно определённая область наблюдения.

CPU SELF учитывает user+system текущего процесса, включая его потоки. CHILDREN становится доступен для завершённых, собранных через wait детей; живой worker ещё не представлен итоговой дельтой. Предложение из [strong-worker-design](../backlog-reviews/strong-worker-design.md) считать свежие parent SELF + reaped CHILDREN логично при контролируемом дереве. Receipt ребёнка нужен для reconciliation, а не повторного прибавления уже учтённого CPU. Аналитический пример: parent10с + child20с =30с, не50с после повторного добавления receipt. Недоступная стоимость остаётся unknown, а не0. Это требования к будущему исполнению, не сегодняшняя проверка019.

## Завершение процесса тоже является контрактом

Python определяет `start_new_session=True` как POSIX `setsid`; `os.killpg` доступен Unix. Windows console groups и TerminateProcess имеют другую семантику. `Popen.communicate(timeout)` сам ребёнка не убивает; обработчик должен завершить его и собрать результат. Даже `run(timeout)`, завершающий непосредственного child, не доказывает cleanup всех descendants. [subprocess](https://docs.python.org/3.12/library/subprocess.html), [os.killpg](https://docs.python.org/3.12/library/os.html#os.killpg).

Опубликованный worker design предусматривает process-group TERM/KILL/reap. Его нельзя представлять как capability всех ранее принятых in-process runners. Предлагаемое минимальное обязательство backend: владение конкретной группой, ограниченное ожидание, учёт хвостов cleanup, доказанный reap и failed/unknown outcome при неполной очистке. Отсутствие receipt или неоднозначный exit code не разрешают назвать причину OOM без дополнительного свидетельства. Success разрешается только после cleanup и последних resource checks.

DuckDB `memory_limit` ограничивает buffer manager; vectors, results и некоторые aggregate states выделяют память вне него. Поэтому database/profile memory не заменяет RSS Python, NumPy и CatBoost. Profiling по умолчанию охватывает SELECT, а не все операции; неполный профиль не равен нулевой стоимости подготовки/экспорта. [DuckDB pragmas](https://duckdb.org/docs/current/configuration/pragmas). Две нити ограничивают конкретные вызовы, но wall×2 не является измеренным CPU; ожидание диска и cleanup меняют соотношение.

## Минимальный будущий proof без моделей

Предлагается отдельный tiny conformance drill, только после будущего разрешения. Литеральные counter fixtures проверяют эквивалентность1ГиБ как1073741824bytes/1048576KiB и отказ на неизвестной единице; synthetic counters проверяют SELF/CHILDREN без двойного счёта и живого ребёнка с ещё нулевым CHILDREN. Управляемые короткие child fixtures покрывают обычный exit, игнорирование TERM, KILL/reap, import failure и missing receipt. Подменённые clock/RSS после close должны давать failed evidence, а не success. Никакой реальной перегрузки памяти или обучения для этих обязательств не требуется; сегодня drill не выполнялся и бюджет ему не предоставлен.

Для независимого rerun отчёт должен закреплять ОС/архитектуру, Python/wheel/lock/code hashes, backend units, CPU scope, эффективные thread/settings, storage/temp/cache context и cleanup outcome. Время Mac не является прогнозом Windows/Linux. Допуски floating-point сравнения и ranking tie policy фиксируются до результата; аппаратная разница не оправдывает позднюю подгонку acceptance. Итоговая граница проста: semantic feature portability — проверяемая цель; перенос telemetry/lifecycle и GPU остаётся отдельным недоказанным capability.
