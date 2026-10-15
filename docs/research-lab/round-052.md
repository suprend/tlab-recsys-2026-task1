# Round052 — capability contract переносимой feature automation

**Предложение будущего adapter conformance, без реализации и quality claims.** Это сужение [011](round-011.md), [040](round-040.md), [043](round-043.md), [048](round-048.md): не новый dataset list или pool8, а проверяемая граница между unsupported program, наблюдаемым нулём и неизвестным условным ключом. Данные/архивы/модели не открывались, fits и code changes отсутствуют. Текущий005/016 не становится универсальным адаптером от этого описания.

## Первичные основания

Woodwork различает physical type, logical type и semantic tags; пользователь может уточнять inferred types. Объявленный primary index уникален и теряет стандартные tags своего logical type. Это полезная защита nominal IDs, но библиотека не выводит из Integer смысл «измерение», бизнес-единицу события или полноту logging. [Официальная документация Woodwork0.31.0](https://woodwork.alteryx.com/en/stable/guides/logical_types_and_semantic_tags.html).

Featuretools позволяет объявлять secondary time index для полей, становящихся известными позже создания строки. Его default cutoff включает данные ровно на cutoff, а endpoint на границе training window зависит от настройки. Следовательно, одинаковое имя timestamp или включённый temporal mode не удостоверяют наш `[t−W,t)` и отсутствие global peers. [Handling Time, Featuretools1.31.0](https://docs.featuretools.com/en/stable/getting_started/handling_time.html).

Feast описывает per-entity point-in-time retrieval и TTL. Текущая документация отдельно различает event-time filtering и opt-in created-time filtering; default created timestamp разрешает dedup, но не исключает поздний backfill. Даже opt-in предполагает, что created timestamp действительно отражает доступность. Это не гарантия наличия delivery clock в произвольном dataset. [Официальные PIT joins](https://docs.feast.dev/getting-started/concepts/point-in-time-joins).

OneBM приводит конкретное ручное исправление parser: `ad_id` первоначально трактовался как numerical, затем объявлен categorical. Авторский пример показывает значимость semantics annotation; его label-distribution transforms не входят автоматически в наш vocabulary. [OneBM, §V-D](https://arxiv.org/html/1706.00327v1). Ни один источник не предоставляет готового доказательства всех предлагаемых ниже contracts.

## Минимальная декларация до исполнения AST

Достаточен versioned adapter manifest и результат его проверки, без нового feature framework. Декларации утверждает человек; source inspection впоследствии проверяет согласованность, но sample observations не превращаются в универсальные constraints.

| Обязательство | Минимальные поля/вопросы | Что запрещает gate |
|---|---|---|
| EventFact | Nominal U/I, raw row unit, action mapping, duplicate/null/orphan policy | Invoice/quantity/property update не становится view или несколькими событиями |
| Clocks | Time units/precision/timezone, event/available roles, endpoints, source coverage intervals | Угаданные UTC, seconds, availability или стабильный порядок peers |
| PropertyState | Embedded-event либо changelog; field/entity grain, validity/availability, bucket conflict/carry-forward | Future catalog backfill и fanout всех revisions в count |
| Query context | Exact Q/C keys, source-local sampling/eligibility/catalog/maturity definitions | Q population из будущих positives; замена C для повышения coverage |
| Provenance | Source/version/digest, adapter/policy/schema hashes, compiler/AST/representation, assumptions | Reuse feature cache после смены action mapping или metadata resolver |

Для event count единица — сохранённая raw row, для distinct — non-null множество явно названного противоположного entity key, для recency — секунды от последнего eligible event полного observed prefix. Quantity3 в одной invoice line не означает три logged purchases. Product keys нельзя преобразовать в float32; model numeric representation относится к значениям features, а не join keys.

Action coverage требуется отдельно от общего временного интервала: наличие purchase logs за месяц не доказывает logging views. Непрерывность интервала, outage и population scope должны декларироваться; support произвольных gaps у текущего005 здесь не заявляется. Первая активность пользователя не является началом source coverage или регистрации. Unknown timezone/available_at либо блокирует соответствующий strict claim, либо остаётся явно утверждённым offline assumption, никогда implicit inference по имени.

## Три разных состояния и разрешённые результаты

| Состояние | Пример | Правильная реакция |
|---|---|---|
| Структурно unavailable | Dataset содержит только transaction lines, view channel отсутствует | View AST unsupported; не добавлять0 или «missing=false» |
| Известное пустое множество | View channel наблюдается, полный declared window, eligible rows нет | Count/distinct0; recencyNULL с существующим missing flag |
| Неизвестное условие | Category field имеется, latest eligible bucket конфликтует/NULL | Noncategory counts остаются; category-conditioned valueNULL по declared policy |
| Неполный observed window | Source начался послеt−W либо имеется declared gap | Count0 может описывать наблюдаемую часть; coverage<1 не даёт утверждать полный истинный0 |

Полностью отсутствующее category поле отличается от неизвестной category конкретного item. Первый случай не должен автоматически легализовать original full manual18/B41 через заполнение NULL; нужен отдельный заранее объявленный reduced-schema experiment. Второй уже имеет row-level missing convention. Причины unsupported/unknown можно хранить в conformance evidence; это не разрешение добавлять новые model masks и превышать physical-column budget.

Та же дисциплина применяется к portability quality claim: совпадение count semantics не сохраняет original target/calendar/C/manual control. Новый source-local B требуется описать до outcomes. Нельзя назвать drop-in reproduction эксперимент, где отсутствующий канал был молча удалён, а затем по validation выбран другой bundle.

## Будущий adversarial drill≤32literal rows,0fits

Предлагается одна заранее записанная suite с максимум26input rows:10events,6property revisions,4Q,6C; schema variants меняют декларации, не скачивают источник. Literal expected tables задают keyed output/value/missing/coverage и expected rejection отдельно от compiler.

1. Две одинаковые cart rows U→X за час доT: raw pair count2, distinct cart users1. Additional property revisions не увеличивают2. Перестановка global peers не меняет output; transport index не становится event order.
2. Тот же event bag без views проверяется под двумя manifests: view channel declared complete даёт observed view count0; channel unsupported должен отклонить view program. Unknown action token не молча отбрасывается: нужен заранее выбранный reject/mapping policy.
3. Cart ровноT−24h включён, cart ровноT исключён. Единственный cart8days назад даёт weekly count0, full-prefix recency691200s и missing=false. Source-startT−1h даёт coverage1/24 для непрерывного24h window, независимо от user age.
4. CategoryA→event→CategoryB доT различает historical event category и query-current property. Latest known+NULL bucket даёт unknown без older backoff. Correction с valid_time<T, available_at>T исключена; property update не создаёт business event.
5. Q с empty C сохраняется в domain report; NULL user/item key и ID`2^60+1` проверяют reject/exact transport. Conditional unknown не превращается в known zero, и off-C category products остаются в соответствующем denominator.

Будущий pass подтверждает только declared mechanics на witnesses. Он не доказывает actual logging completeness, доступность полей в прошлом, перенос качества или экономию труда.

## Два конкретных backlog уточнения

Первое: в существующий future adapter gate добавить machine-readable **capability decision по каждой requested AST**: supported/rejected с причиной и exact dependency set; manifest change обязан менять value identity. Unsupported программу нельзя автоматически заменить другой после freeze. Второе: обязать adapter conformance report сохранять literal expected results и rejection cases выше, а также различать structurally unavailable, observed empty и conditional unknown. Это refinement существующих generalization/verification задач, без нового HYP, datasets, operators или allowance. Execution/resource approval и actual source verification остаются отдельными будущими решениями.
