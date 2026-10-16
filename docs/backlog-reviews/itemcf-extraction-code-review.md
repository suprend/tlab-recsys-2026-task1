# ItemCF extraction: CODE review and accepted tiny-input execution

The V2 extractor and five tests passed one actual CODE-unit execution on
2026-10-16. [Root's exact acceptance](evidence/itemcf-extraction-code-unit-v1/root-code-unit-acceptance.json)
records terminal `4b8796`, exit 0, known reap and unchanged source/test pins.
[Tests](evidence/itemcf-extraction-code-unit-v1/tests.txt) report 5 run, 0 failures,
0 errors and 0 skipped. This is optional TLAB-012/HYP-001 preparation, not an
actual recommendation experiment or completion of the deferred pilot.

| Review stage | Disposition and preserved evidence |
| --- | --- |
| Original independent A/B on V1 | No findings in those reviews; [A](evidence/itemcf-extraction-code-unit-v1/independent-a-original-v1.md) and [B](evidence/itemcf-extraction-code-unit-v1/independent-b-original-v1.md) remain unchanged. They missed the later Root DST finding. |
| B wording erratum | [Erratum](evidence/itemcf-extraction-code-unit-v1/independent-b-wording-erratum-v2.md) distinguishes excluded events at the anchor from included other query actors; it is not a new V2 code acceptance. |
| Root DST P2 and V2 fix | [Finding](evidence/itemcf-extraction-code-unit-v1/root-DST-finding-v2.json), [exact diff](evidence/itemcf-extraction-code-unit-v1/author-v1-to-v2.diff) and [focused A closure](evidence/itemcf-extraction-code-unit-v1/independent-a-DST-closure-v2.md): normalize the accepted zero-offset anchor to UTC before seven-day arithmetic. |
| Unit-runner cleanup P2 | [Original](evidence/itemcf-extraction-code-unit-v1/runner-original-P2-review-v1.md) and [V2 closure](evidence/itemcf-extraction-code-unit-v1/runner-P2-closure-v2.md) preserve failure evidence and require known reap. Closure was source-only, without a cleanup-fault execution. |
| Actual V2 five-method unit | [Child result](evidence/itemcf-extraction-code-unit-v1/child-result.json), [inner result](evidence/itemcf-extraction-code-unit-v1/result.json), [outer receipt](evidence/itemcf-extraction-code-unit-v1/outer-receipt.json) and [terminal](evidence/itemcf-extraction-code-unit-v1/terminal.json) support Root's final accepted exit. |

The main fixture used 36 invented typed9 events + 2 queries + 3 candidates,
28 distinct posting memberships, and literal expected ItemCF mean `3/260` and
max `3/13`. Other cases covered four tied-item events, member overflow/close,
pre-opener source refusal and the empty-query London DST preflight. No CatBoost
import, model fit, actual source dataset read or native training-helper execution
occurred. Native training-helper body remains UNRUN.

Observed peak RSS was 122,044,416 bytes, not a hard limit or whole-tree sum.
The outer profile's 0.968927 seconds and tool-observed 0.924617 seconds have
different scopes and are retained separately. CPU profiles exclude some receipt/
exit tail and are not summed as proven disjoint full-tree cost. The receipt and
terminal together close this one execution; no resource balance is inferred.

The result supports these tiny-input semantics only. Caller source authentication,
fresh read-only opener and external native-query limits remain obligations;
whole-source completeness, 100-query feasibility, ranking benefit and CV remain
unestablished. No optional pilot or ML allocation is issued. Original author
manifests/freezes and failed-review history are archived unchanged. Generated
fixture databases, complete temporary trees, issued requests/private grants and
runner executables are excluded from this publication packet.
