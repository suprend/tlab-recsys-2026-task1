# Optional TLAB-012 source CODE — V2 UTC-window repair, UNRUN

Root identified a supported V1 P2: a datetime can have UTC offset zero at the
anchor while retaining a timezone with seasonal rules. For London on 2020-10-26,
subtracting seven local calendar days crosses the offset transition and produces
the wrong UTC lower endpoint. V1 can therefore reject correct exact-seven-day
source coverage before opening the source. The confirming stdlib calculation
belongs to Root; this preparation did not import or execute either candidate.

The production diff only imports `timezone` and normalizes accepted `b` with
`b.astimezone(timezone.utc)` before daily validation/subtraction. `_clock` and its
accepted input domain are unchanged; the same anchor instant is preserved. SQL,
IDs, history/posting semantics, budgets, opener ownership, kernel and all other
production functions remain unchanged. Exact inverse text transport restores
the entire V1 source. The four original test method ASTs are unchanged.

The fifth prepared method uses the real extraction function with the London
anchor, explicit UTC coverage 2020-10-19 through 2020-10-26, zero-row descriptor,
empty query tuple and a forbidden opener. Its expected result is `()` with no
opens. It creates no database and issues no SQL. The existing test module still
has its V1 DuckDB import for the other fixtures; no module was imported here.
The new method and all earlier methods remain UNRUN.

Both V2 Python candidates AST-parse/compile. The V1 candidates, manifest and all
eight sourcepins remained byte-identical during preparation. Exact source/test/
doc changes are in `/tmp/tlab-itemcf-extraction-v1-to-v2.diff` (SHA
72380ba669ac7c583fce258832bfdba41ff4260ff590f3598faac056ea0f1408).
The common V2 publication manifest is
`/tmp/tlab-itemcf-extraction-manifest-v2.json` (SHA
599f2abff91e8ca2fb0c20721d3c47ebb6467d94f55f99eb25e69836c994221b).

The stdlib copy/AST/hash preparation body observed 0.013248 CPU seconds,
0.014418 wall seconds and ru_maxrss 23,707,648 native macOS byte units. This is
neither full process lifetime nor total author preparation cost. Candidate/test
imports, DuckDB/SQL, real data/models/Y, native ML, helpers, network, canonical/
Git writes and new runtime grants remain zero. V1 reviews are evidence only for
V1; Root's affected independent review and any bounded unit execution are next.
