# Журнал новых исследовательских идей

Обновлён 15 октября 2026, 05:33 UTC / 08:33 МСК. Этот журнал отделяет новые механизмы от уточнений прежнего backlog. Статус «исследуется» означает текущую работу, а не готовый результат или разрешение эксперимента. Отложенные результаты25–31 остаются закрыты.

## Три независимые линии

| Линия и раунд | Начало в журнале | Вопрос | Результат и статус |
|---|---|---|---|
| Feature/automation, F001 | 15.10.2026 05:22 UTC | Новые группы признаков и методы автоматического поиска, первичные работы2024–2026 | [Первый независимый draft сдан:4 кандидата](brainstorm-f001.md), [ledger](brainstorm-f001-ledger.json); cross-review ожидается |
| Retrieval/session, R001 | 15.10.2026 05:22 UTC | Retrieval, сессии, повторные покупки и replenishment | Процесс прерван до сданного draft; завершение не подтверждено |
| Models/loss/transfer, M001 | 15.10.2026 05:22 UTC | Новые learner/objective/transfer механизмы сверх уже записанных ALS, generic boosting и auxiliary heads | [Первый независимый draft сдан:5 кандидатов](brainstorm-m001.md), [ledger](brainstorm-m001-ledger.json); cross-review ожидается |

Время в таблице — момент регистрации линий, а не утверждение точного начала каждого агентского процесса. Сданные раунды связаны ниже; независимые cross-reviews будут добавлены после их завершения. В каждом раунде ожидаются3–5 конкретных кандидатов с первичными источниками, доступными входами, контргипотезой, проверкой дублей и самым дешёвым опровергающим опытом. Количество статей и заметок не равно количеству новых гипотез.

## Реестр кандидатов новых раундов

| Кандидат | Связь с existing/new HYP | Решение | Основание |
|---|---|---|---|
| NB-F01 | Новая candidate-specific pre-purchase context recurrence | Draft, ждёт novelty/source review | Сходство текущего контекста с историей перед прошлой покупкой именно кандидата; matched last-any-purchase control |
| NB-F02 | Censoring-aware residual waiting-time prior | Draft, ждёт feasibility/novelty review | Условная вероятность повторного события в24h, censored spells и source coverage; fitted estimation оплачивается |
| NB-F03 | Action-role-directed category association | Draft, ждёт независимой критики | Направленные session/bucket transitions против pooled/symmetric control; peer ambiguity не упорядочивается |
| NB-F04 | Source-only temporal reliability allocation | Draft, условная новизна | Выбор одного bundle по прошлой применимости/drift против seeded random; стабильность не равна predictive utility |
| M001-C1 | Time-aligned teacher supervision | Deferred proposal, cross-review ожидается | Меняется supervision student; old/fresh teacher age confounded training prefix, новый budget нужен |
| M001-C2 | Candidate-domain quantile-weighted top20 loss | Design candidate, cross-review ожидается | Полный C, exact threshold/tie/gradient contract ещё надо выбрать |
| M001-C3 | Shared-weight TabM regularization | Deferred proposal, dependency/resource review | Конкретные member adapters при общих матрицах; disagreement не calibrated uncertainty |
| M001-C4 | Local labelled in-context rows | Resource-blocked design proposal | Retrieval зрелых training rows для контекста inference; frozen weights/backend/license не проверены |
| M001-C5 | Bilateral positive denoising | Сохранённый отказ для текущего плана | При singleton positive новый positive-side механизм исчезает; support ещё не измерен |
| R001 | Reconstruction pending | Незавершённая линия после прерывания | Незавершённый draft не считается сданным результатом |

Кандидат получает стабильный ID своего раунда. После дедупликации он либо связывается с существующим HYP как refinement/duplicate, либо становится новым HYP с явной дельтой механизма. `needs-pilot`, `deferred`, `rejected` отделяются от права исполнения. Отказы сохраняются: недостаточные входы, дублирование, несоответствие ресурсу или слабая идентификация эффекта не стираются из истории.

## Уточнения, которые не считаются новыми идеями

| Записка | Связь | Статус и причина |
|---|---|---|
| [Query sampling и estimand](refinement-query-sampling-estimand.md) | Текущий протокол оценки и веса | Refinement: уточняет популяцию и знаменатели, не предлагает новую модель |
| [Приоритет будущего retrieval](refinement-post-heldout-retrieval-priority.md) | TLAB012 / HYP001 и candidate research | Refinement: существующий ItemCF cost gate, без нового бюджета |
| [Multi-behavior auxiliary](refinement-multibehavior-auxiliary.md) | HYP065 / прежняя multi-task ветвь | Refinement: отделяет next-any от next-purchase; запуск отложен |
| [Category text controls](refinement-category-text-controls.md) | TLAB010 / HYP003/085/086 | Refinement: lexical identity, hierarchy и semantics — разные проверки |

[Старые74 раунда](index.md) сохраняют research/audit историю; они не переименовываются в новые brainstorm-раунды. [Canonical backlog](../backlog.md) отдельно хранит принятое исполнение и отложенные ветви.

## Архивирование первых результатов — 05:33 UTC

Сохранены два реально сданных независимых отчёта и их исходные ledgers:9 candidate IDs, включая один явный отказ. [Freeze](brainstorm-f001-m001-freeze.json) связывает точные первые bytes; выводы пока не прошли cross-review. Имена будущих HYP не назначены, ни один pilot не запускался. Файлы отчётов сохранены без изменения авторского текста; их приоритеты и proposed caps не являются разрешениями на выполнение.

Предыдущая строка R001 описывала запуск до прерывания. Его завершение не подтверждено; новая независимая retrieval-линия восстанавливает этот пробел. Текущая расширенная команда после рестарта регистрируется отдельно по фактическому запуску, чтобы не выдавать исторические процессы за активные.

## Следующие решения

Сначала сдача трёх независимых раундов, затем ротация cross-review и сравнение novelty/стоимости. Следующие темы выбираются по найденным пробелам, а не ради счётчика HYP. Любой будущий pilot требует отдельной development/label reservation, matched baseline, заранее заданных метрик и предела стоимости. Нынешние015/016, выбранные модели и heldout policy новыми идеями не изменяются.
