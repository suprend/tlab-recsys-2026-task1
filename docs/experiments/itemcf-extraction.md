# ItemCF source extraction (optional TLAB-012 / HYP-001)

`scripts.itemcf_extraction.extract_itemcf_snapshot` supplies the existing
`project_itemcf` kernel with complete source-derived inputs. It does not execute
an experiment, rank recommendations or train a model.

Pass a tuple of at most 100 `ItemCFQuery(query_id, user_id, candidates)` values,
each with a distinct bounded query ID and at most 220 distinct exact signed
BIGINT candidate IDs. Candidate and query order are preserved, including queries
with no candidates. Float, bool and NULL IDs are rejected. The common `b` is an
aware, second-precision UTC midnight. Any accepted zero-offset timezone is
normalized to `timezone.utc` before subtracting seven days, preserving the
anchor instant across seasonal timezone transitions.
`SourceContract(rows, start, end)` declares
authenticated typed9 row count and half-open UTC coverage containing `[b-7d,b)`.

The zero-argument injected opener must return a fresh **read-only DuckDB
connection** to the caller-authenticated source. This function owns that returned
connection and closes it on success, SQL/limit/callback failure, or interrupt.
The opener owns cleanup if it fails before returning. A close error cannot replace
an existing primary exception. Schema verification requires the fixed nine
`events` fields/types from `source_import`; it does not authenticate source bytes,
validate every timestamp or prove row-count/content completeness. The opener and
source contract are trusted caller obligations, not grants issued by this module.

History and global graph use only `view` on `[b-7d,b)`. The source timestamp
contract is naive-UTC `TIMESTAMP` with second precision. History removes NULL
products before per-user/item latest-time aggregation and cap21. Ordering is
latest time descending, SHA256 of the UTF8 canonical signed decimal product ID
ascending, then exact product ID ascending. Global audiences contain every
eligible non-NULL user, including users outside the query cohort; duplicates add
no votes. They are never restricted to capped histories. Returned `latest21`
and exact `C ∪ H21` posting maps feed the existing kernel unchanged. Every key
exists, including a known-empty `()`; absent or incomplete extraction fails.

`ExtractionLimits(max_scan_rows, max_members, max_work)` is mandatory. Before
opening the source or invoking `check`, `2 * source.rows` must fit both descriptor
and work limits. It conservatively budgets two full source passes: the history
SELECT and global posting SELECT. An empty query batch or empty required union
may skip work but gets no descriptor discount. The schema query is metadata.
For 42,448,764 rows the descriptor is 84,897,528, so the former 30,000,000 limit
rejects this full-source plan. This says nothing about a separately authenticated
pruned source's plan or actual physical scan count.

`max_members` counts distinct global required-item/user pairs once, across the
batch. Per-query maps share immutable posting tuples; the kernel's own member
limit applies separately to the vectors used by each query. The posting SELECT
uses `LIMIT max_members+1`; the extra pair proves overflow and aborts the entire
call, rather than returning truncated vectors as zeros. `max_work` charges the
two-pass descriptor plus Python input/result/member/key visits. No partial
snapshots are returned on refusal. SQL grouping, sorting, native allocation and
source reading still require the caller's external CPU/wall/RSS/spill guard.
`check()` runs around SQL/fetches and during bounded Python processing; it cannot
hard-interrupt a blocked native call. These limits are not hard native resource
bounds, measured IO, or authentication/content evidence.

Five CODE-unit tests passed on 2026-10-16 with actual terminal exit 0 and known
reap. They exercised real DuckDB SQL on tiny invented typed9 databases and the
existing projection kernel: the 36-event/41-input case (mean `3/260`, max `3/13`,
28 distinct posting memberships), pre-opener full-source refusal, signed-decimal
hash ties, member-overflow refusal/cleanup, and the London seasonal-transition
preflight with exact seven-day UTC coverage and no opener/SQL. The window
outsider is one **second** before the lower endpoint. See the
[review and acceptance](../backlog-reviews/itemcf-extraction-code-review.md) and
[exact Root receipt](../backlog-reviews/evidence/itemcf-extraction-code-unit-v1/root-code-unit-acceptance.json).

The observed peak RSS was 122,044,416 bytes; this is neither a hard memory bound
nor a whole-tree instantaneous sum. The fixture's 128 MB engine setting is not a
process RSS allowance, and 64 MiB is not promised. CatBoost was not imported;
ML fits and real-source reads were zero. This establishes the listed tiny-input
semantics, not whole-source completeness, 100-query feasibility, recommendation
quality, cross-validation or a real-data pilot. Native training-helper execution
remains UNRUN; no pilot, training allocation or new mandatory gate follows.
