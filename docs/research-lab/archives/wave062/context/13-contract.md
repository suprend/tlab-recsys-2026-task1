# Synthetic compiler canary — SOURCE ONLY / UNRUN

The candidate checks the executed compiler/retrieval half of Root's accepted
wave060 analytical witness. It does not execute tsfresh, a temporal bank/binner,
model loader, training, prediction, metrics or the ordinary CLI.

There is one unittest method with two isolated, sequential `:memory:` DuckDB
connections. Each contains four literal view events, one supplied query and one
candidate produced by unchanged `create_candidates`. User101/item201/category301
and query `fixture-q` are fixed. UTC anchor is 2019-10-08T00:00Z; source coverage
is declared complete for [Oct1,Nov1), legal clock48h pilot [Oct8,Oct11), and
query maturity is true consistently with the complete24h horizon. There are no
other events, targets or label relations. Source TIMESTAMP uses naive UTC wall
clocks, as the existing compiler does. Complete synthetic coverage makes absent
rows known zeros; this is not a claim about real source coverage or sampling.

The four midpoint times represent 162 zero bins followed by A=(1,0,1,1,0,1)
or B=(1,1,1,0,0,1). First/last are 18:30/23:30 on Oct7. A has the other views
at20:30/21:30; B at19:30/20:30. The histories differ before compilation.

Frozen061A pins supply every expected value as literal source constants,
corroborated by060C and its distinct critic. Expected values are never calculated
from compiler expressions or output. Actual source functions supply C, the
manual18 features, typed registries and actual numeric order. The canary checks:

- exact recent-only C, purchase popularity0, popular rank NULL, recent rank1,
  last-user-event23:30 and physical candidate schema;
- all41 names in frozen order, original39 numeric physical types and two
  derived FLOAT expressions, float32 values and separate exact NULL masks;
- both missing coordinates (`popular_source_rank`, purchase recency), all
  explicit missing flags, complete source coverage1, category shares1,
  first-observation ages19800s and view recencies1800s;
- every L01–L08 generated three-field physical delta, order/type, literal
  count/distinct/recency/missingness, and unchanged named B41 projection;
- cross-history equality after each independently checked literal result.

The real compiler emits45 physical fields, of which39 are numeric model
coordinates. `numeric_feature_names` is a real pure production helper. The last
two coordinates are generated only inside existing matrix-loader queries.
The test explicitly copies their exact label-free SQL expressions, including
FLOAT casts and masked-array conversion, and never invokes the loaders that
join Y. Thus a future PASS establishes compiler/retrieval plus this projection
on this fixture. It does not establish loader/CLI end-to-end parity, cohort
sampling, native model correctness, multi-anchor equivalence or utility.
Combined48 typed output is projected by frozen names, never treated as a B41
prefix. No production API or source changes are proposed.

The analytical bank differences remain literal historical results, not tests:
peaks n1 A/B=1/0, above-mean runs2/3, lag1=1637/6847 versus3401/6847,
lag2=3400/6806 versus1636/6806. Peaks n2=0 and below-mean run162 coincide.
No tsfresh dependency is added and no bank implementation correctness is claimed.

Future scope is8 fabricated events+2Q,2 generated C,2 candidate builds and18
manual-compiler calls (base+eight bundles per history). DuckDB/numpy package
imports and synthetic SQL are expected; CatBoost/tsfresh imports are blocked
within the body. There are0 fits, predictions, model/data/archive/Parquet/Y
reads, downloads, subprocess calls or fixture DB files. Both connections close
in `finally`. DuckDB threads2, engine memory64MB and spill0B are settings, not
a hard process/whole-tree RSS bound. Runtime/RSS/cost are unmeasured.

The exact future proposed command is in `future-command.json`; it uses ordinary
unittest discovery against this TMP candidate and imports the currently pinned
production source/configs read-only. It is **NOT ISSUED**. Root must first review
the source and separately issue an ordinary finite CODE operation, rechecking
source freshness and choosing external limits/receipts. The consumed50CPU/65wall
native allowance cannot fund it; historical scientific CPU remainder stays
UNKNOWN. There is no new ID, gate, experiment grant or publication authority.

Preparation used only source/JSON text, stdlib AST compile/hash work and own TMP
writes. No production/test/package import, SQL, fixture, Git/attribute probe,
real data/model/Y, network, helper or canonical action occurred. One guessed
source-discovery path `scripts/feature_collection.py` was absent; it was not used.
The actual schema seams were located in feature_programs/train_baselines and
read directly. Broad combined read outputs were truncated; critical APIs and
literal tables were reread in bounded sections. No truncated full-read claim is
made. This candidate remains outside the protected current432 Git slice.
