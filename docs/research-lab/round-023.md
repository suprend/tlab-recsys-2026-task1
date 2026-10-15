# Research lab, round023: граница claims purchase ranking

15 октября 2026. Primary-source synthesis по [target01–08](../target-research/index.md), [evaluator006](../../scripts/ranking_metrics.py) и [backlog](../backlog.md). Без raw/scans, новых metrics/replicates, fits, загрузки datasets или изменений Root/C11 кода и approvals. Здесь уточняется итоговая интерпретация009/016; текущие independent source audits не подменяются новой проверкой и не объявляются завершёнными этой запиской. HYP131/132 остаются reserved refinements reporting, не новым quality mechanism.

## Что оценивает существующий эксперимент

Accepted fixed-clock query q=(u,t) выбирается по past eligibility7d и заранее заданному hash sampling, до labels. История `<t`; target `Yq` — distinct product IDs зарегистрированных purchase в `[t,t+24h)`, только mature horizons. Cq — общий past-only union, без вставки будущих positives. Источники target notes содержат прежние альтернативы endpoints/eligibility; они не заменяют этот versioned accepted contract.

Conditional macro-query NDCG@20 — среднее normalized discounted совпадения списка с **непустыми зарегистрированными Yq**. Recall@20 делит найденные товары на все distinct targets. Full Y включает холодные товары и targets вне C; идеальный DCG тоже использует полное Y. Mature query с положительным Y и пустым C имеет0, а не исчезает. При empty Y значения006 undefined; zero conventions и user-macro — отдельно названные estimands, censored rows не становятся zeros. Full здесь означает полноту зарегистрированных purchase labels в объявленном горизонте, **не** наблюдение preferences/potential outcomes для всех товаров.

Fixed Q/C/Y позволяет эмпирически сравнить два scoring pipelines на одинаковых ситуациях и исходах лога.009 controlled feature-block ablation и016 сравнение automatic bundles с frozen tuned B могут установить изменение **offline предсказательной ranking метрики** при принятой population/settings/budget policy. Это полезный проверяемый результат для задачи автоматизации. Парность устраняет смену evaluation rows между моделями; она не рандомизирует воздействие на покупателей. Повышение NDCG не является процентом дополнительных покупок, revenue lift или utility новой recommendation policy.

## Почему population остаётся условной

Past eligibility не использует будущий исход, но ограничивает задачу недавно наблюдавшейся аудиторией. Это не все зарегистрированные пользователи, не visitor arrivals и не реальные impression opportunities. Midnight query может существовать у пользователя, который не вернулся. Hash query sampling — выбор evaluation cohort, не propensity назначения товара покупателю.

Условие `Yq≠∅` определено будущим outcome: оно допустимо как заявленный ranking estimand, но результат относится к наблюдённым purchase-positive queries, а не ко всем возможностям выдачи. При действительном вмешательстве состав покупателей мог бы измениться; нынешний positive-only contrast не идентифицирует эффект среди будущих покупателей новой политики. All-query zero metric не решает это: она смешивает observed activity fraction и conditional ranking, не оценивает калибровку purchase probability или полезность воздержания.

BCE label0 на candidate означает «purchase этого товара не зарегистрирован в mature H». Это не known negative impression, не disliked и не доказанный отказ после показа. Прошлый view/cart также не идентифицирует recommendation exposure, position, availability или intent. Поэтому обучаемый predictive risk допустим в своём явном контексте, но его object/query weights не являются treatment propensity weights. PairLogit informative-group support — ещё одна описанная training-population особенность, не causal preference experiment.

## Четыре первичных источника и граница IPS

[Schnabel et al., ICML2016](https://proceedings.mlr.press/v48/schnabel16.pdf) моделируют selection bias наблюдаемых ratings и вводят observation propensities для оценки/обучения; обсуждают их estimation и misspecification. Это не утверждение, что missing propensity всегда делает любую causal задачу невозможной, и не готовый proof для нашего purchase-set NDCG. Нужны определённый observation/treatment mechanism, целевой estimand и обоснованные assumptions, которых текущий лог не задаёт.

[Joachims–Swaminathan–Schnabel, WSDM2017](https://www.cs.cornell.edu/~tj/publications/joachims_etal_17a.pdf) корректируют biased clicks через examination/position propensity model и специальные intervention evidence. Search click, product view и purchase — разные observation processes. Отсутствие rank/impression context нельзя устранить переименованием view count в examination probability.

[Swaminathan–Joachims, NeurIPS2015](https://www.cs.cornell.edu/~tj/publications/swaminathan_joachims_15d.pdf) задают logged records `(x,a,r,p)`, гдеp — probability actiona у исторической policy. Для target policyπ веса `w=π(a|x)/p`; IPS использует `Σwr/n`, SNIPS — `Σwr/Σw`. Их results требуют соответствующих distribution/support assumptions; SNIPS в общем не unbiased при конечной выборке. Self-normalization не создаёт наблюдения при нулевом overlap, не устраняет unmeasured confounding и не восстанавливает отсутствующий denominator экспозиции. Clipping меняет bias/variance tradeoff, не добавляет идентификацию.

View frequency, purchase/view ratio, popularity source score и offline C sampling probability не являютсяp logging policy. Item-level propensity не автоматически заменяет joint slate/position mechanism. Обучение propensity model на этих counts без action/exposure contract добавило бы недоказанные assumptions, а не independent evidence. IPS/SNIPS implementation, дополнительные metrics или data collection этой запиской не предлагаются. [Ji et al., temporal evaluation](https://arxiv.org/abs/2010.11060) отдельно показывает global-time leakage: strict-past устраняет соответствующую недопустимость информации, но не доказывает causal identification или stationarity.

## Catalog и один conceptual witness

U(t)=prior-observed products — catalog proxy, не stock. Товар может быть давно unavailable, впервые появиться послеt, иметь неизвестную offer price. Full-Y outside-U/C misses сохраняются; их удаление ради «реалистичного ассортимента» без availability evidence изменило бы задачу. Прошлый price observation не обещает цену рекомендации.

Предлагаемый0-fit conceptual counterexample, **без исполнения**: одинаковый прошлый log и organic purchaseX дают Y={X}, поэтому scorerX выигрывает offline у scorerY. Два гипотетических мира согласованы с этими наблюдениями: в первом показX приводит к покупке, показY — нет; во втором показX отвлекает и покупки нет, показY вызывает покупку. Реальная organic покупка без этих новых interventions одинакова. Offline input/metrics не различают миры, а causal ordering противоположен. Это witness недостаточности информации, не оценка силы эффекта в REES46 и не запрос нового эксперимента.

## Минимальная формулировка финального отчёта

«На заранее определённых mature daily queries recently observed users и fixed past-only C модель улучшила/не улучшила conditional full-Y NDCG@20 относительно frozen B. Y отражает зарегистрированные distinct purchases следующего24h; outside-C/cold targets остаются misses. Сравнение observational/offline; causal recommendation lift, stock feasibility и перенос на будущие даты не установлены».

Рядом сохраняются уже объявленные support/coverage/zero/C-empty/censored counts, repeat/explore/cold/history/day/missing-context slices **в доступной evidence scope**, точные protocol/ties/model pins, adaptive selection history и cost ledger. Новых обязательных slices/looks нет. User-bootstrap уточняется round019: условен на датах/fitted pipelines, selection CI screening-only. Prospective confirmation требует отдельного chronology contract с двумя временными шкалами, без утверждения нового schedule; control019 и016 exact settings/budgets остаются отдельными gates. Ни extra fits, causal claim, метод установки или новый бюджет не выданы.
