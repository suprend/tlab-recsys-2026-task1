# Candidate generation — согласованный исследовательский пакет

15 октября 2026. Завершены12 независимых studies и3 grouped cross-reviews. Исходные proposals сохранены; material corrections явно отмечены. Новые источники не реализованы автоматически и не объявлены quality wins.

| Направление | Исследование | Решение |
|---|---|---|
| Exhaustive reference | [01 exact catalog](01-exact-reference.md) | Observed U(t), dot scoring отличается от полного CatBoost |
| Popularity | [02 trends/quotas](02-popularity.md) | Accepted004 purchase-distinct-users7d |
| Repeat interest | [03 recent/history](03-recent-repeat.md) | Acceptedrecent20, retainbought |
| Metadata | [04 category/brand/price](04-category-brand-price.md) | Одна возможная P1source, newprotocol |
| ItemCF | [05 item neighbors](05-itemcf.md) | Альтернативная P1source, buildcostgate |
| UserCF/audience | [06 user/audience](06-usercf-audience.md) | Deferred после discovery/cost/actualsizechecks |
| Factor retrieval | [07 ALS/BPR](07-als-bpr.md) | ALSfold-in first; snapshotnegative semantics explicit |
| Neural retrieval | [08 pooling/sequence](08-two-tower-sequence.md) | Optionalfit, cold/OOV support, featurepurposeотдельно |
| Serving | [09 exact/ANN](09-vector-search.md) | Exactblockdot прежде measuredANNneed |
| Text | [10 lexical/dense](10-text-retrieval.md) | Identity/prefix/expansioncontrols;dense deferred |
| Fusion | [11 quota/RRF](11-fusion.md) | Oneprefusionpool дляrule-onlyclaim |
| Evaluation | [12 coverage/budget](12-evaluation-budget.md) | FullY, actualsize, costledger, gained/lost |

[Review01–04](review-01-04.md), [review05–08](review-05-08.md), [review09–12](review-09-12.md) покрывают всю серию.

P0 остаётся accepted004: P200 по distinct purchase-users7d +R20 distinct all-event pastitems7d, union/dedup безrefill, max220, boughtitemsсохраняются. U(t) — proxyknowncatalog, неstock и неfullOctoberinventory раннегоanchor. Истории всехпользователей/metadata исключаютglobaltimestamppeers; fittedparameters/index/statistics availablebeforequery. Zero/empty/OOV/ambiguity/low-support раздельны. Latestglobalmetadatabucket безolder-cleanbackoff; historicaleventcategory не currentreclassification.

Первое возможное sourceextension — один cheapcategory/lexical либо boundedItemCF, выбранный prospectively после strongB/costgate. Refilling220 иpop220 требуют reviewednewconfig; v1cap200необходится. Output100/220 неограничивает graphΣm²/postings/fit/indexcost. Sources ALS/neural требуютотдельногоrepresentationfit, frozenlateweights нельзяисправитьcatalogfilter. Textcode/brandимеютмалоеmetadata space иmassiveties, single-tokenbrandTFIDF=identity. ExactIP/cosineгеометрииразличны, ANNRecallagainstexact неpurchaseRecall.

Retrievaleffect: fullYRecall + gainedtargets −losttargets послеreplacement/cap; nativepolicy иmatchedactualsize показываютсярядом. Equalmaximumquota неравноequalactualC, refill/supportexhaustion заранееversioned. Fusion-only сравнение удерживаетprefusionpool/depth. Featureautomation/rankerablation сохраняет fixedQ/C/fullY ивнешний006criterion. Evalfuturepositives никогданевставляются; текущий017/008Cнетронут. Pooledsupportcoverage×in-supportRecall=pooledall-targetRecall, непроизведениемacroсредних. MaturezeroYqueriesсохраняются, censoredненулевыелэйблы.

Следующийpilot100labelblindqueries включает независимыеtiny/source/topK/tie/peer/OOV/overlaporacles, actualbuild/scan/state/search/exportcost, RSS/spill/deadline/errorledger. Авторскиеbudgets не складываются. Новыеsourcefits не вытесняютtask1: tunedmanualboosting и boundedfeatureautomation016 наfixedC. Confirmation закрыт доpositive decisiongap иfrozenclaim/control; expandedselection96targets ограничиваетprecision.

[Backlog](../backlog.md) · [Target research](../target-research/index.md) · [Task1](../task1-requirements.md).
