# TLAB016 selector: независимый scope/tie critic

15 октября2026. **Вердикт: algorithm design ACCEPT; doc requires one material wording correction.** Проверены переданный draft, [exact JSON](../../configs/features/automation-selection.json) и [doc](../experiments/feature-program-selection.md). Код selector ещё не рецензируется. Live019/016 scores, модели, targets, SQL, fits и WIP не читались/не выполнялись; правил и бюджета не добавлено.

Проверенные SHA: config `3bb1e4f63f32160135daaee95d257f571f394af25f4b74378ba2785be12b5ac0`; doc `ab7cd0b0515a633f91b63784f0184e067171ecd8c32840f8d750a8f5ee2edb16`. Первичный readthrough счёл files согласованными; отдельный analytical witness ниже выявил неверное следствие в пояснении. Эта история сохранена: финальный verdict относится к найденному counterexample, а не к первоначальному impression.

## Material finding: chosen winner может улучшать B меньше epsilon

Doc утверждает: “A new arm can therefore replace B only when its NDCG exceeds B by more than the tolerance.” Для **выбранного arm** это неверно при согласованном global band и lexical tie.

Пусть ε=1e−12, все candidates проходят Recall/source gates: B=.5, R2=B+1.5ε — global maximum, I1=B+.75ε; остальные arms ниже. Band начинается сB+.5ε. Поэтому B исключён, I1/R2 остаются, и I1 выигрывает по lexical candidateID при одинаковых3columns. ПолученныйW−B=.75ε≤ε.

Минимальная поправка: feasible **global maximum** должен превышать B больше чем наε, чтобы исключитьB. ВыбранныйW в этом случае имеет положительный point contrast, который может быть≤ε. Не менять algorithm и не добавлять отдельныйW>B+ε gate: это изменило бы уже согласованное поведение. Tiny point gain также не является practical/statistical promotion proof. Counterexample аналитический, не выполненный fit/test.

## Остальные контрпримеры

**Global band и nontransitivity.** I1=.5−1.5ε, I2=.5−.75ε, R1=.5, B=.49. Единый band содержитI2/R1, выбираетсяI2. Pairwise fold I1→I2→R1 может сохранитьI1 на первом «tie» и затем выбратьR1, получив иной результат. Нельзя обновлять band от промежуточного winner или зависеть от input order.

**Все contrasts отрицательные.** ЕслиB=.4 и все arms<.4, B является maximum и выигрывает по0added columns. PrimaryW−B=0. Negative здесь означаетcontrast; rawNDCG ограничен[0,1]. Если лучшийarm превосходитB лишь на.5ε, B остаётся в band и выигрывает. Если maximum вышеB на2ε, B внеband; дальнейшийwinner определяется общим правилом, как показывает finding.

**Recall boundary.** ПриBRecall=.600 floor=.598: равенство feasible, меньшеfloor — нет. Сначала фильтроватьRecall, затем искатьNDCGmaximum. NDCGepsilon не переносится наRecall. Missing/nonfinite metrics отклоняются, а не заменяются0. B проходит собственныйfloor, но no-change не отменяет accepted source/model integrity.

**Collisions/failures.** ExactJSON явно задаёт collision как consumed/ineligible, безrefill. Она не создаёт второй независимый quality result; unexecuted slot не masquerades completedfit. Actual опубликованныйdraw имеет четыреunique bundles. Knownresourcefailure оплачивается иineligible; integrity/API/unknownSTOP не разрешает выдатьBfallback как успешный scope. Invocation сresourcepartial не доказывает, что четыре завершённыхальтернативы проиграли.

## Scope и remaining gates

Config/doc соответствуют draft по `{B,I1,I2,R1,R2}`, общим accepted019 population/weights/settings/trained iterations/scoring prefix, full-Y conditional query-macro NDCG/Recall20, inclusive floor, global band, physical B0/arms3 включая masks и lexical IDs. CPU/AST/tree/depth ties отсутствуют. B выигрывает, когда входит в band; максимум ищется среди всей candidate family.

Primary — sealed W−B, причём W может равняться B. Best-of-two I−best-of-two R остаётся descriptive development screening из существующих opportunities, без нового bootstrap/test/holdout reselection. Пустая feasible группа даёт undefined comparison. Gain random winner относится к mixed typed automation, а не rule-guided superiority. Если W=B и heldout не имеет positive support, conditional estimand undefined, хотя тождество scorers известно.

До execution acceptance нужны точные candidate statuses/order/pins, actual019 proof, source/feature acceptance, finite metric representation, floor arithmetic, immutable allocation/decision, global four-fit claim, shared remaining ledger и обе decision clocks. JSON minimum_delta и doc floor должны реализовать одно declared comparison без дополнительного Recall tolerance. Reporting-only holdout сохраняет models/programs и training/scoring policy. Actual prediction seals до queryY opening и simulated maturity+positive compute остаются отдельными gates. Этот review не выдаёт fit/calendar/source approval и просит исправить только отмеченное пояснение.

## Narrow re-review: correction accepted

Actual corrected paragraph повторно прочитан. **Final ACCEPT design/doc only.** Теперь исключениеB связано с feasible GLOBALMAX>B+ε, а собственный gain выбранногоW прямо допускает положительное значение≤ε из-за другого maximum arm и lexical tie. Analytical finding закрыт без изменения алгоритма; исходный counterexample и первоначальный wording verdict выше сохранены.

JSON SHA осталась `3bb1e4f63f32160135daaee95d257f571f394af25f4b74378ba2785be12b5ac0`; corrected doc SHA `1f7ac673560f4191152b1647210fd09e40997e00099a97e1624dec69418ab843`. Execution/selector implementation, inputs, fit claim, calendar/prediction seals и actual outcomes этим delta не принимаются. Новых looks/rules/fits нет.
