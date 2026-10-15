# Source-fact audit rounds043–046

15 октября2026. Самопроверка первичных источников и силы утверждений; это не новая independent code/source acceptance. Исходные тексты сохранены, явные appendices добавлены к043/045/046.044 содержательной поправки не потребовал. Данные/архивы, модели и WIP не открывались; jobs/tests/fits/LLM calls не выполнялись. Новых hypotheses, budgets и approvals нет.

## Подтверждённые факты

**Retailrocket043.** Индексированный текст [publisher Kaggle card](https://www.kaggle.com/retailrocket/ecommerce-dataset/home) повторно подтверждает CC BY-NC-SA4.0, version2/987.5MB, view/addtocart/transaction,4.5месяца,2756101events/1407580visitors,20275902property rows/417053items и1669tree rows. Weekly snapshots compressed в property change log и раскрытые categoryid/available также подтверждены. Прямое представление карточки пустое; archives/headers не инспектировались. Milliseconds→UTC остаётся нашей adapter assumption по13-digit Unix example; exact endpoints, delivery availability, download access и реальный memory footprint неизвестны. Выбор Retailrocket как наиболее удобного pilot — наше инженерное суждение, не сравнительный результат издателя.

**Pruning044.** Разделение DFS relational generation, ExploreKit meta-ranking/wrapper evaluation и OpenFE FeatureBoost/pruning соответствует связанным первичным работам. B/retrieval aliases, named grains и current005 constraints — repository-specific inference; papers не доказывают их. Shared aggregate planning не приписывается статьям как measured speedup нашего pipeline. Equal values/correlation/quality score не названы universal semantic proof.

**Property testing045.** [QuickCheck](https://www.cs.tufts.edu/~nr/cs257/archive/john-hughes/quick.pdf) поддерживает attribution о specifications/generators/conditional properties. [Chen et al.1998](https://www.cse.ust.hk/~scc/publ/CS98-01-metamorphictesting.pdf) — исходная primary metamorphic работа; PDF text extraction частично повреждён, readable publisher-indexed abstract подтверждает follow-up-test attribution. [NoREC](https://www.manuelrigger.at/preprints/NoREC.pdf)/[TLP](https://www.manuelrigger.at/preprints/TLP.pdf) подтверждают описанные query comparison/TRUE-FALSE-NULL механизмы. Конкретные feature invariants, surviving count×2/wrong-window mutants и acceptance bank — наши spec-derived предложения, не авторские empirical findings этих papers.

## Содержательные уточнения

**043: отрицательная estimate.** Первоначальное «опровергает заявленное улучшение» слишком сильное без uncertainty qualifier. Appendix уточняет: observed gain/decision predicate не получен; point estimate<0 не доказывает true effect<0. CI через0 не устанавливает ни знак, ни эквивалентность. Новое правило выбора не вводится.

**045: MAX-recency.** Это неоднозначное сокращение, не нужный aggregate над готовыми recencies. Appendix явно задаёт `R=t−MAX(timestamp)`; при merge готовых recencies одинаковогоt применяется MIN non-NULL, а при полностью пустой eligible history остаётсяNULL. Transformations также должны сохранять допустимый integer range. Исходные partition formulas не переписаны.

**046: inputs/calls.** [CAAFE appendixD](https://papers.neurips.cc/paper_files/paper/2023/file/8c2df4c35cdbee764ebb9e9d0acd5197-Paper-Conference.pdf) показывает Class samples в prompt. Значит10training rows нельзя описывать как заведомо label-free; appendix046 добавляет прямую видимость training labels, отдельно от validation feedback.10iterations/10random validation splits и error feedback подтверждены§3.

[FeatLLM§3.2](https://arxiv.org/html/2404.09491v2) включает **ещё один LLM parsing stage** rules→Python code; original046 его не выделял. Это важно для полного call ledger. Predictor — nonnegative linear logits+softmax, cross-entropy training; общее «linear predictor» допустимо, но «обычная linear regression» было бы неточно. Temperature0.5/bagging/shuffle подтверждены appendixD.

[LLM-FE arXivv2](https://arxiv.org/html/2503.14434v2) подтверждает validation-score memory,3islands/3programs per prompt/20LLM samples и local evaluation limits30s/2GB. Эти числа не преобразованы в точный whole-search call/fit/CPU count. OpenReview challenge не обходился; другой publication version полностью не проверен. Equal-score clustering — авторский memory heuristic; запрет считать его AST dedup — наш обоснованный вывод.

Итог: corrections касаются силы вывода, неоднозначного formula shorthand и недостающей information/call stage. Исходные proposals остаются prospective; tests passing, paper benchmarks и indexed card facts не выдаются за actual source/runtime acceptance нашего эксперимента.
