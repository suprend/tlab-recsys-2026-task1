# Какие H&M-признаки сгенерированы и выбраны

В замороженном GPU-эксперименте ручной контроль M содержит 23 входа. Генератор перечислил 60 исторических user×attribute программ, исключил две формулы, уже присутствующие в M, и получил 58 допустимых дополнений. Модель M+all имеет 81 вход. По training-only PredictionValuesChange (PVC) из неё выбраны 12 программ; M+selected и каждый из трёх random controls имеют 35 входов.

Это описание фактически закреплённых определений и выбора, **без результатов качества**. Оно не доказывает превосходство selected над M, random controls или всеми ручными признаками Strong34. Источники определений — [feature engine](../scripts/hm_feature_engine.py) и [selector](../scripts/hm_select_features.py); команды воспроизведения — [hm-reproduce.md](hm-reproduce.md). Для понимания формул и наборов локальные данные, модели и manifests не нужны.

## Что автоматизировано

Человек задаёт роли таблиц, допустимые атрибуты, операции и окна. Здесь это:

- transactions: дата покупки, пользователь, article_id; articles: семантические свойства товара; candidates: пары пользователь–товар;
- пять измерений: `product_type_no`, `colour_group_code`, `department_no`, `garment_group_no`, `index_code`;
- три окна:7,28,90 дней;
- четыре операции: `count`, `share`, `recency`, `distinct_items`.

Код автоматически перечисляет агрегатную часть registry из 5×3×4=60 программ, сопоставляет семантически одинаковые формулы, компилирует исторические агрегаты и согласует имена с фактическими входами модели. Произвольные SQL/выражения и labels в этот интерфейс не передаются. Это фиксированная грамматика генерации и расчёта; выбор пространств и операторов остаётся ручным.

Из 60 исключены ровно две формулы M23:

| Семантическая программа | Уже имеющееся имя в M |
|---|---|
| `product_type_no`, count,28 дней | `affinity_type28` |
| `colour_group_code`, count,28 дней | `affinity_colour28` |

Поэтому eligible pool равен 58, а не 53: дедупликация проводится против **фактически выбранного M23**, а не против прежнего Strong34. Пять агрегатных aliases из Strong34 возвращаются в pool под прежними именами. Обозначим этот набор **A5**:

```json
[
  "affinity_type_share28",
  "affinity_colour_share28",
  "affinity_department28",
  "affinity_department_share28",
  "affinity_type_recency90"
]
```

Остальные шесть добавок Strong34 — explicit transforms `repeat_share28`, `demand7to28`, `price_compat28`, `price_compat28_valid`, `item_price28_missing`, `user_price28_missing`. Они не входят в эту четырёхоператорную грамматику и не добавляются в M+all81. Таким образом, all81 не является полным Strong34 с дополнительными признаками. Полный engine registry содержит 87 полей и может материализоваться целиком в общем кэше; фактический all-fit использует только выбранные 81. Шесть explicit Strong transforms в этот fit не входят.

`prepare` закрепил pool и random draws до all-fit. После обучения M+all на train anchors12/19/26 августа selector запросил `PredictionValuesChange` у сохранённой модели с `thread_count=2`, без `data`, validation Pool или validation metrics. Среди 58 eligible программ выбираются top12 по PVC DESC, при равенстве — по имени ASC. Ручные входы M сохранены независимо от их PVC. Код выравнивает значения важности по фактическому порядку 81 входа модели; это не выбор первых 12 элементов массива importance.

## Формулы и отсутствующие значения

Для cutoff `t`, пользователя `u`, кандидата `a` и окна `w` обозначим:

- `H_w(u,t)` — **мультимножество строк покупок** пользователя в `[t−w дней,t)`. Одинаковые строки сохранены;
- `N_w=len(H_w)` — число всех этих строк, включая строки товаров без доступного семантического атрибута;
- `v_d(a)` — значение измерения `d` кандидата;
- `A(d,w)` — строки из `H_w`, у которых значение того же измерения равно `v_d(a)`. SQL NULL не совпадает с NULL; если metadata/атрибут кандидата отсутствует, это множество пусто.

Четыре шаблона определены полностью:

| Операция | Формула для пользователя и кандидата | При отсутствии подходящих покупок |
|---|---|---|
| `count` | `C(d,w)=len(A(d,w))` |0 |
| `share` | `S(d,w)=C(d,w)/N_w` |0, также при `N_w=0` |
| `recency` | `R(d,w)=date_diff_days(max(date in A(d,w)),t)` |91 для **любого** окна 7/28/90 |
| `distinct_items` | `D(d,w)=len(unique(article_id in A(d,w)))` |0 |

`distinct_items` считает различные article_id, а не различные значения атрибута. Повторы увеличивают count/share numerator, но не число различных товаров. `share` делится на все пользовательские покупки в том же окне, а не только покупки с известными metadata. При recency вне выбранного окна результат 91, даже если есть более старая подходящая покупка внутри общей 90-дневной истории.

Все окна включают левую границу и исключают cutoff. Даты исходных событий имеют точность DATE, внутридневной порядок неизвестен. Article IDs и коды атрибутов сохраняются строками. Категориальный sentinel `__MISSING__` используется только при выдаче категориального входа модели; он не создаёт совпадение отсутствующих атрибутов в агрегатах. Свойства articles рассматриваются как статический snapshot — историческая доступность и изменения каталога этим не устанавливаются. Генератор не читает будущие покупки; downstream training PVC использует только обученную на прошлом модель.

## Фактические выбранные 12 программ

Это набор **S12** в порядке PVC. Значения взяты из одного закреплённого all-fit, а не усреднены по seeds. В формулах ниже `d` — атрибут из того же ряда; функции C/S/R/D определены выше.

| № | Точное имя | Измерение d | Операция / дни | Формула | Нет совпадений | PVC | Было в Strong34 |
|---:|---|---|---|---|---:|---:|---|
|1|`auto_product_type_no_share90`|`product_type_no`|share /90|S(d,90)|0|8.081873322787196|нет|
|2|`auto_index_code_recency90`|`index_code`|recency /90|R(d,90)|91|7.123249486646964|нет|
|3|`auto_product_type_no_distinct_items90`|`product_type_no`|distinct_items /90|D(d,90)|0|6.2137675740419605|нет|
|4|`affinity_type_recency90`|`product_type_no`|recency /90|R(d,90)|91|5.949890511264144|**да**|
|5|`auto_index_code_share28`|`index_code`|share /28|S(d,28)|0|4.1813475076994875|нет|
|6|`auto_product_type_no_count90`|`product_type_no`|count /90|C(d,90)|0|3.9065821401268113|нет|
|7|`auto_index_code_recency28`|`index_code`|recency /28|R(d,28)|91|3.114928618065152|нет|
|8|`auto_index_code_distinct_items7`|`index_code`|distinct_items /7|D(d,7)|0|2.291857082043925|нет|
|9|`auto_department_no_distinct_items90`|`department_no`|distinct_items /90|D(d,90)|0|2.236829434741777|нет|
|10|`auto_garment_group_no_share90`|`garment_group_no`|share /90|S(d,90)|0|1.6488797913625615|нет|
|11|`auto_garment_group_no_distinct_items7`|`garment_group_no`|distinct_items /7|D(d,7)|0|1.4933081804329267|нет|
|12|`auto_product_type_no_share7`|`product_type_no`|share /7|S(d,7)|0|1.4217349857296009|нет|

Пересечение S12∩A5 — **1 из 12**, только `affinity_type_recency90`, на позиции 4. Остальные 11 имён отсутствовали в Strong34, но это не доказательство 11 независимых новых источников информации: они используют ту же историю/metadata, могут быть коррелированы или выражаться через другие агрегаты. Например share90 использует count90 и уже имеющееся число пользовательских покупок за 90 дней.

Eligible ranking содержит 58 программ, выбранная часть —12. Ровно нулевых PVC **0 из 58** и **0 из 12**. У 12-й программы PVC `1.4217349857296009`, у 13-й (`auto_garment_group_no_recency90`) — `1.3989206906720781`: точного tie на границе нет. Отсутствие tie не доказывает устойчивость top12 к другому fit/seed; GPU обучение недетерминированно. Положительный PVC также не устанавливает причинную пользу признака или прирост out-of-sample MAP.

## Ручной M23 и порядок входов

Фактический M_GPU — GPU `manual_pilot500d8`:500 деревьев, depth8, model seed2026. Его ordered vector содержит 18 numeric и 5 categorical входов:

```json
[
  "u_tx7", "u_tx28", "u_tx90",
  "i_buyers7", "i_buyers28", "i_buyers90",
  "ui_tx7", "ui_tx28", "ui_tx90",
  "u_recency", "i_recency", "ui_recency",
  "item_price28", "user_price28",
  "affinity_type28", "affinity_colour28",
  "global_rank", "user_recent_rank",
  "product_type_no", "colour_group_code", "department_no",
  "index_code", "garment_group_no"
]
```

Первые группы — counts пользователей/товаров/пар за 7/28/90 дней,90-дневные recencies, средние исторические цены за 28 дней, два user×attribute counts и исторические ranks. Число покупателей товара и его средняя цена считаются по полной прошлой популяции. Пять категориальных входов — свойства кандидата. Точные ручные формулы/missing/rank caps доступны в [registry](../scripts/hm_feature_engine.py); ранги имеют fallback101/21, recencies91, отсутствующие средние цены 0.

`selected_names.json` логически содержит M23, затем S12 в порядке таблицы. CatBoost `FeaturesData` группирует numeric перед categorical: фактический selected-vector —18 ручных numeric,12 выбранных numeric, затем 5 categorical. Итого 30 numeric+5 categorical=35. Аналогично all81 содержит 76 numeric+5 categorical. Random namefiles содержат M23 и 12 дополнений в лексикографическом порядке; их model vectors группируются тем же способом. Ключи `customer_id`/`article_id` и label не являются модельными входами.

## Три фиксированных random controls

Для каждого seed101/102/103 до all-fit выполнено `numpy.default_rng(seed).choice(sorted_pool,12,replace=False)`, затем дополнения отсортированы по имени. Приведённые ниже наборы **R101/R102/R103** содержат только 12 добавлений; полный контроль — тот же M23 плюс эти 12, без выбора «лучшего random».

**R101**:

```json
[
  "auto_colour_group_code_count90",
  "auto_colour_group_code_share90",
  "auto_department_no_count90",
  "auto_department_no_distinct_items28",
  "auto_department_no_recency28",
  "auto_department_no_recency7",
  "auto_garment_group_no_recency28",
  "auto_garment_group_no_share28",
  "auto_index_code_distinct_items28",
  "auto_index_code_recency90",
  "auto_product_type_no_distinct_items90",
  "auto_product_type_no_recency28"
]
```

**R102**:

```json
[
  "affinity_type_share28",
  "auto_colour_group_code_distinct_items28",
  "auto_colour_group_code_recency90",
  "auto_department_no_count7",
  "auto_department_no_count90",
  "auto_department_no_recency28",
  "auto_garment_group_no_count7",
  "auto_garment_group_no_distinct_items7",
  "auto_garment_group_no_share90",
  "auto_index_code_count7",
  "auto_index_code_distinct_items90",
  "auto_product_type_no_share90"
]
```

**R103**:

```json
[
  "affinity_type_recency90",
  "auto_colour_group_code_count90",
  "auto_colour_group_code_distinct_items90",
  "auto_colour_group_code_recency7",
  "auto_department_no_count7",
  "auto_department_no_distinct_items7",
  "auto_garment_group_no_count28",
  "auto_garment_group_no_distinct_items28",
  "auto_garment_group_no_share90",
  "auto_index_code_share28",
  "auto_index_code_share90",
  "auto_product_type_no_recency28"
]
```

Пересечения относятся к **дополнениям**, а не к полным 35 входам, иначе общие 23 ручных входа скрывали бы различия:

| Набор | S12∩R: количество и точные имена | A5∩R: количество и точные имена |
|---|---|---|
|R101|**2**: `auto_index_code_recency90`, `auto_product_type_no_distinct_items90`|**0**: пусто|
|R102|**3**: `auto_garment_group_no_distinct_items7`, `auto_garment_group_no_share90`, `auto_product_type_no_share90`|**1**: `affinity_type_share28`|
|R103|**3**: `affinity_type_recency90`, `auto_garment_group_no_share90`, `auto_index_code_share28`|**1**: `affinity_type_recency90`|

Случайные контроли не обязаны быть непересекающимися с selected или между собой. Эти пересечения — описание заранее зафиксированных draws; они не дают основания заменять наборы после наблюдения качества. Средний random3-контраст должен усреднять AP внутри пользователя, затем ресэмплировать пользователей, а не выбирать лучший random score.

## Provenance и граница проверки

Фактические optional local manifests и namefiles находятся в ignored `artifacts/hm-campaign/feature-study/` и `feature-selection/`. Они содержат модельные provenance и локальные paths; документ выше переносит определения и списки, необходимые читателю без доступа к этим файлам.

| Identity | SHA256 / digest |
|---|---|
|study `manifest.json`, byte SHA256|`0746454b5d7184bc809ee55602ba2edf525d831c129fd523f490a97f0be29c4f`|
|selection `manifest.json`, byte SHA256|`b735c9e554a8cbff5c1ffbfdfc064104b56c9a2ae107f4c0cb416aa809327832`|
|study `plan_digest`|`2d55d8acb68ae04a7e3f801b35bab160af862a2172b8b36a2f74e8b3c40c26f0`|
|eligible `pool_digest`|`42f7e2414e350064cd4bee29bf5832b9d90b8a5a34dd74b7f67c32b29ed92505`|
|feature contract digest|`3a475c62bd2ac1b39803e6d5599da20ceb49892cec3f57ebcabcb7ea708b35ee`|
|selection payload digest|`be476fbc9c6d2a506c2d95fecfcc623342b306e57ac27009aafafebcae6f6647`|
|`selected_names.json`, byte SHA256|`0b2a92cb546abacb368c60e237ac5fa136387189f0244545a2c233396fdc56be`|
|all-fit identity|`8499556014459396da998ef9959a67a429ff818eb579b28fa77f90323e3bdeef`|
|all-model CBM, byte SHA256|`6dd35bd39cf5e256c7622dd378dd82f92b52062a1da3ff03a81316108faf33e9`|
|selector source SHA256|`a4ce7d5678af547577c7739a13d2bc008ddf89e4340d86393722ea74fc7bb055`|
|feature-engine source SHA256|`47e4de2e7282fc41d21a86687aa42a705cd14083380cff519a39c7444164a6a2`|

Byte SHA и canonical payload digests имеют разные области хеширования и не взаимозаменяемы. В selection manifest сохранены все 58 строк `pool_ranking`,81 имя `importance_model_order`, явные `importance_data=null`, `importance_thread_count=2` и правило сортировки. Это фиксирует конкретный выбор, не его статистическую устойчивость.

Независимый reviewer `hm_guard` уже загрузил сохранённую 81-input CBM и повторил native CPU2 PVC без Pool; точный ranking и выбранные имена подтверждены. Подготовка этого документа отдельно сверила только JSON/namefiles, SHA и исходные формулы; SQL, модели и повторный PVC для него не запускались. Подтверждение ranking не заменяет независимого аудита downstream predictions/метрик и не является доказательством причинного эффекта отдельных программ.
