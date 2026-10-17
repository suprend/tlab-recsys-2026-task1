# Independent actual publication receipt review — exact429

**ACTUAL RECEIPT / SOURCE CONSISTENCY PASS. No supported discrepancy found.** This review issues no new operational grant.

Independently read the five specified files in `/tmp/tlab-publication-429-actual-v1`: `preflight.json`, `PR-update.json`, `PR-update.stdout`, `PR-update.stderr`, and `remote-readback.json`; compared their bytes and structured values with frozen SOURCE V2 and the prior independent SOURCE freeze. All 39 metadata consistency checks passed, with no failed check.

`remote-readback.json` matches Root's supplied SHA256 `63ffce0b7bb190c872867ab1500077380ea119a27e2e1a9133fbaaed6af1cff8` (3,749 bytes). It reports all ten checks true, exact PR/head429, private repository, OPEN draft PR1, research branch, base main and unchanged main. Its returned PR body exactly matches frozen V2 UTF-8 bytes: 1,983 bytes, SHA256 `699ce89d1ae460b945a551fd771593a79834a8c425056d6a3a3501c258cebdc3`. The returned title exactly matches the frozen title after removing its single terminal LF: actual58 bytes versus file59 bytes; frozen-file SHA256 `cc1d3a8c70362713f53c00d34f500d2488ea76ca64ed21b5636948ef2682bb12`, actual-title SHA256 `0311a244cf37ea811d0c0d7d7dc274c86689ada7a2bb5513706d7f8d461bc26a`. That expected terminal-newline difference is not a title mismatch.

The earlier preflight is consistent with remote476/local429 and binds prior independent SOURCE report SHA256 `f0991e62643c0bd324a6fbc9a16f0a56d8a428627c878d0b852913ec62f9466e`. PR-update stdout is exactly the PR1 URL plus LF, stderr is empty, and both hashes match the recorded exit0 receipt. Its `remote_readback_pending=true` is the earlier01:42:02 phase; the later01:42:38 readback closes that pending state.

The supplied actual tool records are consistent: push initial697b52/session37651/finale02de3/CLOSED0; PR update initial95ca2c/session1615/finalf38be2/CLOSED0. Root additionally supplied readback initial6b5087/session64799/final043aea/CLOSED0 and successful normal automatic approval review with no rejection. These are Root's tool-session/network/approval observations; this reviewer did not execute or independently replay those sessions or network calls.

Independently read current local Git metadata: HEAD and saved origin research ref both `429da06ef766f2c326824e8747179cf3b3da0c01`; active branch `codex/research-features-and-targets`; tree `04622ed9d32582dedce801a01cd08a58ba2769ff`; checkout CLEAN. Local main and saved origin main both `f38d5899ab53606413e0ba380ea5c7917103e031`, equal to the receipt's supplied remote main. The claim that remote main was unchanged across publication remains Root's network assertion; current local refs and supplied receipt agree.

All frozen SOURCE V2 outputs and the prior independent SOURCE report/pins/title/body bindings are unchanged. The prior qualified publication privacy/claim review therefore continues to apply to the exact published source and PR narrative. No new runtime, native, data, model quality or leak-freedom claim is introduced by this receipt review.

No network, Git mutations, project imports, tests, runtime, SQL, DB/Parquet/models or venv access was performed. The verdict establishes local byte/hash/receipt/source consistency; actual external state and successful normal auto-review are supplied Root evidence. Root's final adoption can reference this report after reading it.
