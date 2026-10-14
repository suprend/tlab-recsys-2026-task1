# TLAB-002: независимая проверка protocol/run manifest

15 октября 2026. **Окончательный verdict после повторной проверки: accept для TLAB-002.** Finding исправлен, revised scoped suite фактически прошёл: 16 tests, exit 0. Подробности — в audit amendment в конце. Acceptance относится к protocol/run-manifest scope; TLAB-003 требует собственной проверки фактического sampling/labels и бюджета.

**Первоначальный verdict: material changes.** Далее сохранён первоначальный review до исправления: фактические тесты проходят, но обязательный gate доступности fitted component к первому query не представлен в schema. До исправления этого пункта независимый accept TLAB-002 не выдан; реальный TLAB-003 остаётся за acceptance gate. Это не запрещает отдельную synthetic подготовку.

Scope: полностью прочитаны четыре owned файла — [validator](../../scripts/protocol_manifest.py), [tests](../../tests/test_protocol_manifest.py), [7d config](../../configs/protocols/clock-7d.json), [48h config](../../configs/protocols/clock-48h.json). Сопоставлены с [TLAB-002/003](../backlog.md), [target review 01–04](../target-research/review-01-04.md), [05–08](../target-research/review-05-08.md) и конкретным поручением проверить `fit_cutoff/available_at ≤ first query`. Все четыре файла были untracked; пустой обычный diff не использован как доказательство отсутствия изменений. Проверены полные actual files.

Reviewer не менял repo/Git/data/env/code, не устанавливал зависимости, не обучал модели и не запускал subagents. WIP TLAB-003 не импортировался и не выполнялся.

## Фактические результаты

Запущена только разрешённая unittest-группа:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_protocol_manifest.py -v
```

**Exit 0; Ran 15 tests in 0.011s; OK.** Дополнительно исполнен короткий in-memory repro вызовов только TLAB-002 API: отсутствие `available_at` принимается, его явное добавление отклоняется как unknown. Там же проверены детерминированность ID и чувствительность к изменению code hash/component cutoff. Реальные данные и файлы моделей не читались; hashes в repro — условные синтетические значения.

## Material finding: P1 — отсутствует время доступности компонента

Место: [`_components`, строки 177–189](../../scripts/protocol_manifest.py#L177), [build identity](../../scripts/protocol_manifest.py#L192).

Schema component разрешает ровно `name`, `fit_cutoff`, `refresh_policy`. Проверка отклоняет fit cutoff позже первого pilot query, но не хранит и не проверяет `available_at`. Fit cutoff описывает границу данных обучения; он сам по себе не доказывает, что fitted state уже доступен прогнозу. Например, state с допустимыми входами до 7 октября может быть опубликован только 9 октября и не должен обслуживать query 8 октября.

Точный воспроизводимый пример из корня проекта:

```python
from scripts.protocol_manifest import load_protocol, build_run_manifest

config = load_protocol('configs/protocols/clock-7d.json')
kwargs = dict(
    code_hashes={'scripts/protocol_manifest.py': 'a' * 64,
                 'uv.lock': 'b' * 64},
    input_hashes={'data/synthetic.csv': 'c' * 64},
    artifact_refs={}, created_at='2026-10-15T00:00:00Z',
)
component = {
    'name': 'encoder',
    'fit_cutoff': '2019-10-07T00:00:00Z',
    'refresh_policy': 'frozen_parameters_past_history',
}
build_run_manifest(config, components=[component], **kwargs)  # accepted
late = dict(component, available_at='2019-10-09T00:00:00Z')
build_run_manifest(config, components=[late], **kwargs)
```

Фактический второй результат: `ValueError: component: missing=[], unknown=['available_at']`. Это отклонение неизвестного поля, а не реализация временного gate; даже допустимое `available_at` схема не сможет сохранить. Первый принятый manifest вообще не позволяет отличить доступное state от поздно опубликованного.

**Минимально необходимое исправление:** добавить обязательный UTC `available_at` в component schema и проверять его не позже первого query; сохранить имеющийся fit-cutoff gate. Зафиксировать согласованную причинную связь fit cutoff/availability — консервативно `fit_cutoff ≤ available_at ≤ pilot.start`. Поле естественно попадёт в identity через существующий `components`; не помещать его в исключённые provenance fields. `available_at` означает доступность state на логической replay-оси, а не сегодняшнее wall-clock время ретроспективного обучения.

Нужны компактные regression cases: missing availability; допустимое равенство first query; поздняя availability при раннем fit cutoff; недопустимый порядок cutoff/availability; изменение допустимой availability меняет run ID. Фикстура `fixed_prior` тоже должна явно объявлять availability. Исправление не требует raw scan, новой зависимости или обучения. Код reviewer не исправлял.

## Что уже соответствует контракту

- **Strict JSON/version/types:** duplicate keys и NaN/Infinity отклоняются при загрузке; unknown/missing fields проверяются на вложенных уровнях. `version=1`, `provisional_pilot`, UTC и policy constants проверяются с точным типом; bool не принимается как integer. Endpoints обязательны и bool. [Parsing](../../scripts/protocol_manifest.py#L20), [protocol validation](../../scripts/protocol_manifest.py#L70).
- **Время и censoring:** second-resolution Z timestamps, source/pilot containment и UTC midnight обязательны. Максимальный lookback eligibility/popularity/recent должен полностью помещаться перед первым query. Последний daily anchor — `pilot.end−1d`; его horizon проверяется принятым TLAB-001 с right endpoint и availability delay. При одинаковом H/delay это покрывает также все более ранние queries. [Maturity/lookback](../../scripts/protocol_manifest.py#L96).
- **Два конфигурационных варианта:** фактически отличаются только eligibility 168h против 48h. Оба — 00:00 UTC, development 8–10 октября, raw history, global read-before-update, binary distinct purchases `[t,t+24h)`, caps 2000 пользователей/день и 220 candidates. Их нельзя объединять в одну population; статусы явно provisional.
- **Sampling и budgets:** schema требует обозначение label-independent hash sampling; caps согласованы с объявленными bounds. Это проверка декларации, не доказательство фактического sampling до labels. Реализацию hash selection и независимость Y от C проверять в TLAB-003/004; в текущем модуле sampling и target extraction отсутствуют.
- **Identity:** canonical JSON сортирует object keys; protocol, code/input hashes и components входят в SHA-256 identity. Artifact references и created_at исключены, но валидируются. Actual repro подтвердил одинаковый ID для одинаковых inputs, разные ID при изменении code hash и component cutoff; tests подтверждают изменение seed/input hash, tamper detection и roundtrip. Изменение физического кода влияет на ID только если исполнитель действительно пересчитал его hash: проверка claimed hashes с диском намеренно оставлена executor, что явно документировано. [Identity](../../scripts/protocol_manifest.py#L192).
- **Scope исполнения:** новые imports — stdlib и принятый temporal contract. `sha256_file` потоковый, вызывается только явно; данный review и suite не сканировали dataset. Version 1 намеренно принимает только clock pilot, не выдаёт provisional config за утверждённый финальный протокол.

## Неблокирующее усиление numeric validation

`availability_delay_seconds` проверяется снизу, но не сверху. In-memory repro с `10**30` заканчивается `OverflowError: Python int too large to convert to C int` при построении timedelta, тогда как прочие недопустимые значения дают ожидаемый `ValueError`. Это fail-closed и не создаёт утечку в принятых configs, поэтому отдельным material finding не объявляется. При исправлении schema разумно ограничить delay доступным диапазоном source либо явно преобразовать overflow в validation error; один regression case достаточен.

**Условие повторной приёмки:** исправлен обязательный `available_at` gate, scoped manifest tests и новый temporal repro проходят, независимый reviewer проверил actual diff. Чистые 15 PASS текущей версии этого условия не заменяют. Других material findings в просмотренном scope не найдено.

## Audit amendment: фактическая повторная проверка исправления

15 октября 2026, после сообщения о заморозке revised files. Повторно прочитаны те же четыре owned файла полностью; TLAB-003 и остальные WIP файлы не читались и не исполнялись. Исправление проверено по actual code, а не по сообщению автора.

В [`_components`](../../scripts/protocol_manifest.py#L177) `available_at` теперь обязательное поле. Оба timestamp проходят прежний строгий UTC parser; условия `available_at < fit_cutoff` и `available_at > pilot_start` отклоняются. Следовательно, accepted component выполняет `fit_cutoff ≤ available_at ≤ first_query`; прежний запрет future fit cutoff сохранён логически через эти два неравенства. Равенство допустимо. Existing fixture `fixed_prior` теперь явно указывает availability ровно на первом query.

Полный component object, включая `available_at`, по-прежнему структурно входит в [identity](../../scripts/protocol_manifest.py#L209). Поле не перенесено в artifact_refs/created_at и потому влияет на run ID. Конфигурации по-прежнему различаются только eligibility; дополнительных dependencies/data scans не появилось.

Добавленный [regression scenario](../../tests/test_protocol_manifest.py#L169) фактически проверяет:

- ранний fit cutoff при поздней availability отклоняется именно temporal gate;
- availability раньше fit cutoff отклоняется;
- два допустимых availability дают разные run IDs;
- missing availability отклоняется;
- общий manifest fixture с `fit_cutoff=available_at=first_query` принимается прочими roundtrip/identity tests.

Повторно исполнена **только** та же scoped команда, с `PYTHONDONTWRITEBYTECODE=1`: **exit 0; Ran 16 tests in 0.012s; OK.** Первоначальные 15 PASS и первоначальный repro выше сохранены как история обнаружения; новая версия уже не принимает component из первоначального repro без обязательного availability.

**Final verdict: accept.** Единственный material finding закрыт. Неблокирующая оговорка об oversized availability delay остаётся fail-closed hardening item; она не меняет безопасность двух принятых configs. Приёмка TLAB-002 снимает именно manifest prerequisite для ограниченного TLAB-003, но не подтверждает correctness ещё не проверенного pilot executor, его реальный runtime/RAM, label-independent hash selection или независимость Y от C. Reviewer не запускал реальный pilot и не менял repo/Git/code/data/env.
