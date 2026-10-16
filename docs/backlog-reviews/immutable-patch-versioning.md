# Immutable unified patches: exact-path classification

Stage 02's ordinary cached whitespace check **FAILED exit 2** after one successful `git add`: 15 trailing-space diagnostics in four immutable G02 `.diff` artifacts. The actual failure remains FAILED; its original receipt SHA256 is `7a2c4893e4f9aee2140c80d875567c1d7afa4a1e394b535684a8bcd9949f3dbc`, and raw checker stdout is `e341a8d7612105b511e6355a362d8c2c5251ddfecd2bf8e3597e5a755f12bed7`. These are local evidence identities, not invented repository links. The 52 staged blobs and all 432 worktree files remain exact; HEAD is the accepted commit01 `49a56ce5e5f7d2d55ad3b0e7d5af5baf6615ba2b`.

Static examination of all six `.diff`/`.patch` artifacts in the frozen inventory found 25 trailing lines. Every one is exactly **`b' '`**, a blank context line inside a counted unified-diff hunk. Its leading context marker is required by the patch format; trimming would change the accepted raw patch. Four files belong to G02 (15 lines); two belong to G03 (10 lines), whose actual cached check is still UNRUN.

| Immutable artifact | Raw SHA256 | Bytes | Exact space-only context lines |
|---|---|---:|---|
| [author-v1-v3.diff](evidence/development-cli-code-unit-v1/author-v1-v3.diff) | `3dedcc3ba18ad96c0652bcaeb69329ac70abb9482b4035f684e5194ee6f20544` | 8068 | 17, 18, 43, 68, 143 |
| [author-base-to-v2.diff](evidence/development-training-support-code-unit-v1/author-base-to-v2.diff) | `16a682fe62ade17bd5267c1b337e6ed8cc9ddde9cd9a4e35782f72a8b11b6e4c` | 11029 | 24, 25, 104, 110, 112, 125, 127 |
| [author-v1-to-v2-doc.diff](evidence/development-training-support-code-unit-v1/author-v1-to-v2-doc.diff) | `367679970db738565e5f1aa5edd409dc704ebcff4f9de9a695b200477a03b28e` | 1267 | 5 |
| [doc-v2-to-v3.diff](evidence/development-training-support-code-unit-v1/doc-v2-to-v3.diff) | `ada5c6a040d68ce78408b6e3341c7bf3d7d845e5d1f0cb7ada30b68f2a5e7561` | 3447 | 4, 6 |
| [author-v1-to-v2.diff](evidence/itemcf-extraction-code-unit-v1/author-v1-to-v2.diff) | `72380ba669ac7c583fce258832bfdba41ff4260ff590f3598faac056ea0f1408` | 3801 | 4, 9, 11, 27, 29, 33, 53, 66, 71 |
| [doc-v2-to-v3.diff](evidence/itemcf-extraction-code-unit-v1/doc-v2-to-v3.diff) | `9b923b690f65886bfeb7ea9ee1e0ab9685ab72d0b4f83fd4b9ed2807e67f18de` | 2259 | 6 |

Six literal pathname rules classify only these immutable data artifacts with `-text whitespace=-blank-at-eol`; the existing RED transcript rule and [its note](immutable-transcript-versioning.md) remain byte-identical. There is no wildcard, global checker setting, code-path exception, `-diff`/binary suppression or filter. `-text` prevents EOL normalization only. The whitespace rule permits EOL whitespace throughout each named file, not just these context lines; raw SHA/size/mode and raw staged-blob checks still bind every byte. Under the currently reviewed unset `core.whitespace`, default EOF and space-before-tab checks remain; arbitrary future custom flags are not inherited. This does not promise behavior for altered files or changed Git policy.

This is a metadata proposal, not an installation or checker PASS. After independently reviewed exact local installation, the accepted worktree map would change only `.gitattributes` and this new note: **433 unique paths**. A separate Root stage issue would add **only those two metadata files**, retaining the existing 52 staged blobs: combined G02 would have 54 staged paths (53 added, 1 modified). Only its later ordinary cached check and Root staged inspection can establish a new result. Old stage02 is never retroactively PASS; no reset/re-add/retry/commit follows from this note.

Six logical commits remain possible: commit01 is immutable history; `.gitattributes` intentionally appears again as an amendment in combined G02, so 434 cumulative path-visits mean 433 distinct files. Future preflights must use the explicitly updated 433-map and verify prior committed objects separately. No new driver, experiment, gate, native/data budget or external-publication permission is created. The exact original b760 push question remains unanswered.

## Later G05 archive EOF classification

At the 2026-10-16 G05 checkpoint, ordinary cached check fbeb09 FAILED exit 2 after one successful 309-path add. Commits 03 and 04 had completed; G05 commit and G06 had not started. Failed receipt SHA256: ef00bc83b8a7e0fad70ffa5ea5903689910aced926d1f91fe5c3094596d4f1d4. Original stage02 and metadata-preflight failures remain historical failures.

All 433 current payload files were examined for extra final LF bytes. Exactly these six immutable archived originals end with two LF bytes; those are the six actual diagnostics. The separately prepared 105 CODE/research candidate files have no such endings. These are bounded byte audits, not future checker PASS.

| Archived original | Raw SHA256 | Bytes | Final LF count |
|---|---|---:|---:|
| docs/research-lab/archives/wave054/tlab-wave054-consumer-b-source-pins.md | 187798bdf124229814aaa4c0956f72c7993c176490138e62b9b5f084245e2886 | 3557 | 2 |
| docs/research-lab/archives/wave056/tlab-wave056-validation-signal-b-FIRST.md | 5f02008410383537e4dedb347cf6bf8a601312355a164a9f6ed32d43923b1dbf | 5338 | 2 |
| docs/research-lab/archives/wave056/tlab-wave056-validation-signal-b-freeze.json | 41e9c83823dd41332346b730eea4fdc6504fbe7a2b07122bb6c83d865ea48c3e | 1248 | 2 |
| docs/research-lab/archives/wave056/tlab-wave056-validation-signal-b-pins.json | e6c29812ff2003b4cf755cb94da753ae740f05a9936277551dbb07331edf6b37 | 3013 | 2 |
| docs/research-lab/archives/wave057/tlab-wave057-tabpfn-a-FIRST.md | dae5eba7858e6cb03d3e3140a31643d0005ec546bd4189cbeab8e6fa1fca0ac4 | 4066 | 2 |
| docs/research-lab/archives/wave058/tlab-wave058-dfs-a-FIRST.md | 25a8085afc86b2347c4e48f3bbb2589747df8fd45ded6bd881a68e75a1c856fc | 3220 | 2 |

Six additional exact-path rules permit only blank-at-EOF in these named immutable data files with `-text whitespace=-blank-at-eof`. No wildcard, global setting, source-code exception, hook/filter/signing override or binary suppression is added. Existing transcript and six patch rules stay exact prefixes. Raw source and staged-blob SHA/size/modes still bind every archived byte. No archive is trimmed or normalized.

This later two-file metadata proposal changes only `.gitattributes` and this existing note in the accepted map; unique payload stays 433, other 431 paths stay exact. A new explicit operation may stage only those two files while preserving 309 staged archive blobs, giving 311 G05 paths (309 added, two modified); normal cached check must then pass before ordinary commit. This is distinct from the failed operation and does not relabel its result. With two later metadata overlaps, cumulative path-visits become 436 across the same six logical commits; prior commits remain immutable. Future actual checker/commit is UNRUN here. No runtime/data/ML/grant/external-publication authority follows.

## 2026-10-16 10:01 UTC — preflight SIDE064 original EOF classification

Root's bounded static audit of the next 114 archive candidates reported one extra-final-LF case: `docs/research-lab/archives/side064/tlab-side064-native-oracle-FIRST.md`, raw SHA256 `08da4345f551a8fc916ce3dbd9d1e8795b6e9e3e24994b2f9a4239b4908b1e94`, 2726 bytes, ending in exactly two LF bytes. The original historical FIRST and its exact archive copy are preserved. This proposal rechecks only that named body/copy and the two metadata bases; it does not claim a new audit of all 114 files.

This round has no failed cached whitespace checker: the issue was identified by static preflight before staging, and this proposal does not run a cached check. One additional literal pathname rule, `-text whitespace=-blank-at-eof`, classifies only this immutable archived data file. It is not a source-code exception, wildcard, global whitespace setting, hook/filter/signing override or normalization of the original. All prior metadata bytes remain exact prefixes; authored metadata ends with one LF.

Installation, any later actual cached check and the integrated local checkpoint remain separate Root actions. No test/native/runtime work or future external-publication permission follows. The completed exact b286 publication and old failures/history are unchanged.

## 2026-10-16 10:32 UTC — additional CODE19 immutable diff classification

Root's static preflight now covers the 114 archive candidates plus 19 CODE integration candidates. In addition to the SIDE064 EOF case above, it identified `docs/backlog-reviews/evidence/candidate-reachability-code/test-source-v1-to-v2.diff`, raw SHA256 `eb552f1ec96ea363db593ef0e5c62f668617293f39b698a23c2eefac34399df6`, 4369 bytes, ending in one LF. Lines 17, 61 and 63 are exactly `b' '`: required context markers inside counted unified-diff hunks. The source diff and its frozen packet copy were rechecked byte-for-byte here; neither is trimmed or normalized. This is a bounded metadata check, not a new CODE, native or runtime execution.

The two additions relative to the canonical metadata are exactly the SIDE064 `-text whitespace=-blank-at-eof` rule and this diff's `-text whitespace=-blank-at-eol` rule. Existing metadata and V1 candidate bytes stay exact prefixes. No wildcard, global whitespace override, source-code exception or hook/filter/signing change is introduced. This round has no failed cached checker: discovery was static before staging; an actual ordinary cached check remains pending. Installation and the integrated local checkpoint require a separate Root issue. The completed b286 publication gives no permission to publish a later payload.

## 2026-10-16 10:34 UTC — exact review-original EOF classification

Root's additional bounded static preflight of the integration review evidence identified three original identified-target review files, each ending in exactly two LF bytes and containing no trailing spaces or tabs. Their exact archived paths and identities are:

| Original review evidence | Raw SHA256 | Bytes |
|---|---|---:|
| [tlab-identified-target-wording-independent-review-v1.md](evidence/local-integration-20261016/identified-target-wording/tlab-identified-target-wording-independent-review-v1.md) | `53b86a23bb9f3f20ac19768c7e5b2fab7d9940c8cb61086774847dae592dfeb3` | 3481 |
| [tlab-identified-target-wording-independent-review-v1-pins.json](evidence/local-integration-20261016/identified-target-wording/tlab-identified-target-wording-independent-review-v1-pins.json) | `983161547dc0a3f63d76dfe8a6f73d8a80b7ae907fc56d4bcc38dac290e404da` | 6992 |
| [tlab-identified-target-wording-independent-review-v1-freeze.json](evidence/local-integration-20261016/identified-target-wording/tlab-identified-target-wording-independent-review-v1-freeze.json) | `dbcf396cec174f7c0a1d9a2a0dd7d87bc073b72c783deebf3c4947c4dd2904aa` | 1183 |

These originals remain byte-identical. Three additional literal `-text whitespace=-blank-at-eof` rules apply only to their named archival paths. This proposal therefore has five added rules relative to canonical metadata: one SIDE064 EOF rule, one CODE diff EOL rule, and three review EOF rules. Root's source classification covers 114 archive plus 19 CODE candidates and the selected review evidence; no test or cached checker was run for this metadata preparation, and no checker failed in this round. All prior canonical and V1/V2 metadata bytes stay exact prefixes. There is no wildcard, global/source-code exception, normalization, hook/filter/signing change, installation, commit or future-publication permission.

## 2026-10-16 11:47 UTC — wave066/067 source-archive EOF classification

The static preflight of the adopted 50-file wave066/067 source archive found exactly five immutable originals ending in two LF bytes. All 50 candidates have no trailing space/tab lines. The six original independent-review artifacts (report/pins/freeze for V1 and focused V2 closure) were also checked: each ends in one LF and has no trailing space/tab lines, so none needs an additional rule. This is a bounded byte inspection before staging; no cached checker failed or ran in this round.

| Immutable original | Raw SHA256 | Bytes | Final LF |
|---|---|---:|---:|
| [tlab-wave066-metadata-c-FIRST.md](../research-lab/archives/wave066/tlab-wave066-metadata-c-FIRST.md) | `c0db8af5e8a0b0e08dbd85062274ba0a316421d5203838af2a999b26ee60160a` | 2821 | 2 |
| [tlab-wave066-skeptic-freeze.json](../research-lab/archives/wave066/tlab-wave066-skeptic-freeze.json) | `94cac98383bc4ee88cb3c597a53eb096616aeddf4d39dedaa69c9503a2f1aca1` | 1689 | 2 |
| [tlab-wave066-skeptic-pins.json](../research-lab/archives/wave066/tlab-wave066-skeptic-pins.json) | `cce21cf86ae4934e2f717b247b1fdf2b82312c3a0aa76dfd9c7d818663ea74af` | 17109 | 2 |
| [tlab-wave066-skeptic-review.md](../research-lab/archives/wave066/tlab-wave066-skeptic-review.md) | `777ba550a662882d00c5a786bb35054adbf051ab02022909cc57e36db7490b36` | 4975 | 2 |
| [tlab-wave067-deliverable-a-FIRST.md](../research-lab/archives/wave067/tlab-wave067-deliverable-a-FIRST.md) | `26247e2bcb5ddfc41f772921e6d6a22d884da99db089798594a2a6b18da62172` | 2738 | 2 |

Five additional literal `-text whitespace=-blank-at-eof` rules classify only these archived data paths. Their raw FIRST/critic bytes remain untouched. The existing 18 exact rules and this note's full prior body remain byte-exact prefixes; newly authored metadata ends in exactly one LF. There is no wildcard, global/source-code exception, normalization, hook/filter/signing bypass or binary suppression. Earlier checker failures retain their historical outcomes.

The archive's source adoption closes its documentation findings only. This preparation does not install files, stage, commit, run a builder/collector/native CLI, borrow a budget, or authorize external publication. A later finite Root issue must bind the actual installation and ordinary cached check. No builder/collection/native-CLI PASS is inferred from source review.
