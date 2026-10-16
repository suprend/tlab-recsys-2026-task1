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
