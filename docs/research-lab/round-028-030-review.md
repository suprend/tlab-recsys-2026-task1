# Independent critic028–030 — ACCEPT RESEARCH/DESIGN DIRECTION

2026-10-15. Прочитаны raw028/029/030, verified task1 paraphrase, actual005 contract и прежний026 critic. Compiler/tests/materialization/PRNG/data/models/Pool/fits не исполнялись; Root019/coordinator016 WIP не открывался и не менялся. Это research/design review, **не implementation/execution acceptance**. Материальных новых mathematical/source ошибок не найдено; ниже точные future evidence boundaries.

**Generation claim.**029/030 правильно требуют реальный переход schema annotations→parameterized template instantiation→typed AST/signature/dedup/closure. Чтение восьми готовыхJSON и выбор IDs удостоверяют automatic selection из human pool, но не generation. Три families030 реализуют узкую содержательную генерацию, если правила действительно связывают supplied roles/capabilities/operators и deterministic policy, а не возвращают константный manifest. Window/companion maps, восемьpatterns и staticI остаются явным human prior. Final code inspection и meaningful binding/rejection cases должны подтвердить эту границу; совпадение одного output с ожидаемыми8L само по себе недостаточно.

Первичные claims корректны: [DFS](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf) отделяет relational synthesis от model pipeline/tuning; [Featuretools](https://docs.featuretools.com/en/stable/getting_started/primitives.html) документирует `features_only=True` именно как definitions-only output; [AutoCross](https://arxiv.org/html/1904.12857v2) использует beam search и обучаемый field-wiseLR. Это не реализации этих методов вTLAB и не их качество/скорость на наших данных. Property specifications/custom generators из [QuickCheck](https://www.cs.tufts.edu/~nr/cs257/archive/john-hughes/quick.pdf) не превращают конечный edge-bank в universal proof. NoREC/TLP/метаморфики здесь правильно дополняют literal/list expected values, не заменяя их.

**Actual005 compatibility.**Все named cores030 укладываются в безопасные names, grains U/P/I, count/count_distinct/observed recency005. Counts имеют column=null, distinct — exact canonical entity key, recency — event_time/observed. Для выбранныхI=L02/L06 и переданныхR=L01/L05 нужны11новыхregistry cores:3+2+3+3. Compiler автоматически выдаёт одинBOOL recency_missing, итого **12новыхphysicalcolumns**, по3на slot. Existing24/168coverage и metadata/contextB не являются новыми additions; registry расширяется B+cores. `_missing` не отдельный разрешённый core. Current005 numeric conversion не легализует округление source IDs, implicitNULL→0 recency или raw-ID model inputs.

Exact typed/named delta относительно FINAL019 B, core/output order, suffix flag и every-key coverage должны проверяться позже по actual emitted schema. Symbolic inspection8bundles не разрешает materialize24columns для отбора. Данные capabilities/clock/availability задаются reviewer; переименование physical roles не означает, что frozen005 умеет ingest произвольный raw schema. Unsupported cart/view/оператор должен быть reject до SQL, а не observed0. Никаких log/sum/nested/categorical/learned additions здесь не открыто.

**Полный независимый handgold для L01/L05.**Fixture026 неизменён:9events,4Q,5C; S=1Oct,T=10Oct, peerT/future excluded, duplicates сохраняются. Числа ниже получены вручную, не compiler/reference execution.

| Candidate pair | L01: user view24,cart24,purchase24 | L05: item distinct viewusers24,cartusers168,purchaseusers24 |
|---|---|---|
| U,X |(1,2,1)|(1,1,1)|
| U,Y |(1,2,1)|(1,0,0)|
| U,Z |(1,2,1)|(0,0,0)|
| V,X |(1,0,0)|(1,1,1)|
| V,Y |(1,0,0)|(1,0,0)|

UcartX duplicated даётraw2, но distinctcartusersX=1. VcartX−8d не входит168h; VpurchaseY−25h не входит24h. UcartY ровноT и UpurchaseY послеT не учитываются. Z без истории имеет noncategory counts/distinct0; user-level L01 не становится0 из-за отсутствия истории Z. Это также literal witness против user→pair/item grain substitution. Gold L02/L06 всех5C сохранён в `tlab-research-lab-round-026-review.md`.

Остальные опубликованные028paper goldens статически верны: L03(U,Y)=(1,0,1),L04(U,X)=(1,1,1),L07(V,Y)=(691200,false,0),L08(U,Y)=(NULL,true,0). Нельзя переносить эти значения на расширенный boundary bag без новых literal expectations.9+4+5=18inputrows, остаётся14до32; paper calculations всех8bundles не являются numerical producer materialization. EmptyC queries следующего дня сохраняются вQ, но F остаётся5rows. Source coverage определяется bounds, не first event.

**Draw/evidence/budget.**Переданный parent definition-probe freeze даётR1=L01/R2=L05 приRandom2026, все4selected bundles уникальны. PRNG мной не пересчитывался. Uniform with-replacement/fullsorted8 и whole-bundle collisions acrossI/R/no redraw должны оставаться exact pinned law, даже когда этот конкретный draw collision-free. Будущие meaningful fault fixtures должны отдельно проверить collision consumption, без разрешения перезапускать factual draw.

029 верно отделяет engineering generation/calculation correctness от quality/speed/generalization/commission claims. Accepted bounded019selection не доказывает global optimum; отрицательный или budget-limited016result не превращается в superiority и не финансирует новые seeds/datasets/fits. New additions не повышают sampled numerical manual18 oracle018 до exhaustiveB proof. Actual source/every-row addition audit, matchesQ/C/Y/settings/trainediterations/scoringprefix и honest cost/history остаются отдельными gates.≤12newcolumns/4fits/2CPUh не расширены; HYP137/138 stable refinements.

Audit note: необязательный поиск `tlab016*` не разрешил glob и завершился ошибкой lookup; новых files/evidence из него нет, WIP code не прочитан. Draw attribution выше намеренно ограничена переданным freeze. Это не скрытый successful test или implementation acceptance.
