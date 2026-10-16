# Immutable RED transcript: scoped versioning metadata

The [original RED transcript](evidence/manual-oracle-null/red-tests.txt) is exact
unittest output, including a trailing space after `...` on its first line. Its
immutable identity is **2,142 bytes**, SHA256
`c1d0ed5612d6ee909ca28baa71360d925367bdd3ff2484bfd4534503136671e5`.
[Original acceptance](manual-oracle-null-code-acceptance.md) and
[publication pins](evidence/manual-oracle-null/publication.json) remain unchanged.

Two prior local Git episodes are **CLOSED FAILED**, with zero commits and zero
ref updates. Their exact original receipt identities are recorded here; those
local receipts are not claimed to have repository copies:

| Original receipt | Failure / closed terminal | SHA256 |
| --- | --- | --- |
| tlab-local-followup-checkpoint-execution-receipt-v1.json | preflight show-ref exit 128; terminal 1ba722 exit 1 | 0766d6a85db2608a6f07fe5bbef09306ad4d656f68e8dff97a57bf0b354bfc59 |
| tlab-local-followup-checkpoint-execution-receipt-v2.json | cached diff --check exit 2 on red-tests.txt:1; terminal e179c9 exit 1 | cb4ff556c07b49649888ac94f16fb041d829606baea3d45e9c521c0111269b67 |

The SAME owned alternate index is preserved at
`/private/tmp/tlab-followup-checkpoint-owned-ltb_nxlk/index`: 305,955 bytes, SHA256
`dd05f792fc5d96f783405e551b37eab5fd9a45861d9f39b2382cdf9c95116ac9`.
Neither episode is resumed or reclassified as PASS by this metadata proposal.

Root selected a separately scoped, reversible **normal two-file project edit**:
one root `.gitattributes` rule for this exact data filename and this note. It is
visible project metadata, not a global or code-check override. No transcript,
receipt, publication record or existing link is rewritten. There is no wildcard,
binary/diff suppression or new filter. The rule permits trailing EOL whitespace
throughout this one file, not just its first line. With current unset
`core.whitespace`, default EOF-blank-line and space-before-tab checks remain;
the string rule does **not** inherit arbitrary future custom whitespace flags.
`-text` prevents EOL normalization only; it is not a barrier to every possible
filter. Immutable SHA/bytes and staged raw-blob identity checks remain required.
[Git attribute semantics](https://git-scm.com/docs/gitattributes/2.36.0#_checking_whitespace_errors),
[Git whitespace flags](https://git-scm.com/docs/git-config/2.39.0#Documentation/git-config.txt-corewhitespace).

No new Git behavior has passed here. Exact-payload review and sole-coordinator
installation are separate from a later amended versioning request. Before any
Git continuation, Root needs a fresh inventory of the currently accepted 354+
files, the two installed metadata files and all actual current inputs, followed
by a new reviewed request and checks of effective scope and unchanged blobs.
The old 298 inventory/operation supplies no authority for that work. Code and
neighboring-file checks stay active; unexpected failures still stop dependent
actions rather than broadening the exception. This grants no external-push or
native-test/ML authority and changes no scientific result or resource allowance.
