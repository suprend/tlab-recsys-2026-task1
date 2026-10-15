# Round066 — standalone report должен различать local verification и clean reproduction

**Focused read-only deliverable audit, 15 октября2026.** Прочитаны текущие README, [рабочий отчёт](../progress-report.md), последние опубликованные состояния [backlog](../backlog.md), [018 workflow](../experiments/verification-workflow.md), [fresh-clone audit](../backlog-reviews/tlab-fresh-clone-reproducibility-audit.md) и историческая CPU-environment note. Ни source/model artifacts, ни WIP, ни query-level targets не открывались; jobs/tests отсутствуют. **Нового implementation defect или новой HYP не установлено.** Полезный результат — точная редакционная граница для уже существующего reproduction/report seam.

## Конкретное расхождение scopes

В начале progress-report стоит: «Собран воспроизводимый пайплайн». Без дальнейшего уточнения это можно прочитать как end-to-end reproduction из clone. Между тем README явно сообщает: ignored collections/models/approvals не входят в clone, полное восстановление и выдача fresh approvals ещё не реализованы.018 принимает существующие sealed manual18 artifacts; это иной workflow. Сам report ниже признаёт незавершённое центральное сравнение.

Таким образом, не найдено скрытого факта corruption или фальсифицированного результата. Найдена **слишком широкая начальная формулировка** относительно собственного явного README caveat. Для standalone PDF/технического отчёта читатель не должен искать ограничение по нескольким links. Это refinement существующего fresh-clone finding, не ещё одна задача «построить общий verifier».

[Официальная SIGIR artifact policy](https://sigir.org/general-information/acm-sigir-artifact-badging/) различает functional/reusable/available artifact и воспроизведение основных результатов другой командой. Она требует ясных build/run instructions, versioned code и связанных inputs; доступность кода не тождественна reproduced numerical result. Это первичное основание различения claims, **не** утверждение, что T-Academy требует SIGIR badge, container, публикацию пользовательских данных либо конкретный deployment backend.

## Минимальная честная замена

Предлагаемый текст: «Собран и независимо проверен локальный pipeline формирования Q/C/Y/F и CPU-обучения на закреплённых inputs. Публичны код, протокол и агрегированный audit; fresh-clone восстановление всей цепочки и выдача новых source approvals пока не завершены. Доступные synthetic проверки и historical artifact replay имеют отдельные инструкции и scope».

Последнее предложение допустимо только со ссылками на действительно существующие entrypoints; не выдумывать CLI или готовность metrics replay из050/063. Если самодостаточный replay ещё не опубликован, написать «их границы описаны» вместо «имеют инструкции». Замена не требует запуска, новых fits, source scans, acceptance-writing или ослабления pin guards.

## Status synchronization — тот же issue, не новая очередь

Progress-report говорит о четырёх019 конфигурациях и memory gate в будущем времени. README и опубликованный accepted019 review уже сообщают завершённый bounded control, но README честно предупреждает, что основной отчёт старее. Следовательно, это документированная разница snapshot, а не evidence против принятого019. Перед итоговым отчётом достаточно одного актуального snapshot с точной ссылкой на019 accepted output evidence; исторические preparation notes, например CPU-environment «реальные модели ещё не обучались», сохраняются как датированные audit records.

По последнему публичному backlog016 source producer экспортировал partitions, но terminal wide inspection завершилась failure; actual source/model acceptance HOLD, recovery ещё review-only. Наличие exports не позволяет написать «selected12 source-correct» или «четыре automation arms завершены». Детали failure, unused-oracle recovery и cumulative budgets остаются в canonical evidence; здесь они не пересчитывались и исполнение не одобряется.

| Итоговый claim | Необходимое уже существующее основание |
|---|---|
| Symbolic generation работает | Accepted code/tiny review, bounded schema/templates/closure |
| Selected12 source-correct | Успешный независимый actual formula/coverage/terminal proof; пока не выведен из exports |
| Automation quality известна | Принятые matched attempts и frozen selector; не source producer completion |
| Historical numbers воспроизводятся | Exact supplied input/model/prediction bytes и выполненный replay, не только hashes |
| Clean rerun доступен | Закрытый018/README workflow новой identity и fresh reviewed decisions |

## Что сохранять без дополнительных исследований

README корректно раскрывает whole-month EDA и отсутствие использования reserved query-level targets для выбора. Report уже различает no-impression labels, observed catalogue proxy, event-time availability assumption, cold/outside-C targets и отрицательный009 результат. Их не надо заменять общими обещаниями «полностью causal», «ничего будущего не читали» или «весь B source-exhaustive». OldB sampled numeric scope остаётся прежним.

В [проверенном task1 record](../task1-requirements.md) automation generation/calculation и экспериментальная проверка названы исследовательским путём. Поэтому честный ограниченный отрицательный результат потенциально содержателен; volume notes или красивое слово reproducible не компенсируют незавершённую actual proof chain. Это не гарантия оценки задания и не повод расширять поиск.

**No-add outcome:** нового backlog item/HYP/implementation нет. Coordinator может включить scoped opening и snapshot019/016 в существующую финализацию README/report, сохранив original audit notes. Текущую утверждённую инженерную работу это не задерживает; непройденные gates не превращаются в обещание завершения.
