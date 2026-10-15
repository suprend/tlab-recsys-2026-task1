# Fresh-clone prefix: zero-fit ranking claim replay (018 P0A)

This additive entry provides a public synthetic example and read-only replay of
explicitly authorized historical **train/selection** score packages. It neither
builds collections nor issues source/model acceptance. Source import, pending
collection bootstrap, planning and retraining remain future018 work; no such
commands are exposed as implemented.

## Source-free example

After separately permitted environment setup, from a fresh checkout:

```sh
uv sync --locked
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -m unittest tests.test_replay_ranking_claim
uv run --locked python -m scripts.replay_ranking_claim --package tests/fixtures/reproduction/manual18-small
```

The supplied public package contains **12 synthetic input rows**:3Q+3C+3fullY+
3scores. It contains no real user/item values. Its manifest SHA is pinned in the
entry; modified or arbitrary packages cannot claim the synthetic exemption.
Default execution prints aggregate JSON and writes no files. Python3.12 and the
locked environment are prerequisites; this example performs zero downloads,
source queries, model loads, native predictions or fits. It imports only the
standard library and existing006 `scripts.ranking_metrics` evaluator.

Literal example: one query's two tied candidates have numeric IDs2^60 and2^60+1;
the positive item2^60+1 ranks second. Its fullY also includes2^60+2 outsideC.
A second query has emptyC and a positive target; a third is mature zeroY. Thus
conditional-query Recall20=.25/AP20=.125/RR20=.25; NDCG20 is
`(1/log2(3))/(1+1/log2(3))/2`. Full targets determine denominators/IDCG. EmptyC
and zeroY remain separate; all-query/user estimands have their own weights.

## Package contract

`manifest.json` has strict keys/version/scope `ranking_claim_replay_package`,
stage synthetic/train/selection, K20, the four fixed estimands,
`raw_score_desc_product_id_asc`, `full_distinct_targets_not_intersected_with_C`,
horizon24h, availability_delay_seconds, UTC query_range,
label_available_before/source_observed_until, exact file map and optional
claim_metrics. See the public manifest for exact field spelling. `claim_metrics`
may contain a separately reviewed expected aggregate; None requests calculation
only and does not authenticate a historical published number by itself.

The four plain JSONL files have bounded lines and strict record schemas:

| File key | One record | Required order |
|---|---|---|
| queries | query_id:string,user_id:int64,anchor:UTC-Z,label_is_mature:bool | query_id ascending |
| candidates | query_id:string,product_id:int64 | query_id, numeric product_id ascending |
| targets | query_id:string,product_id:int64 (full distinctY) | same pair order |
| scores | query_id:string,product_id:int64,raw_score:finite number | same pair order |

Each reference has path/sha256/rows. IDs are exact parsed integers, with no
float conversion; duplicate keys, orphans, NULL/float/bool IDs, aliases/path
escapes, nonfinite scores and incomplete files fail. Scores must match **every**
C key exactly, including candidates that do not enter top20. Rankings use raw
score descending and exact numeric product ID ascending; scores are not rounded.
Only one query's≤220 candidates is sorted at a time. FullY is never intersected
with C. All Q are validated before any target stream opens. Maturity is checked
against anchor+24h+delay and the declared observed/available cutoff; censored Q
may not carry targets and count only in the appropriate censored counter.

Package Q order is canonical query-ID order. Converting historical positional
NPZ group arrays to this **keyed** format is the provider's explicit, separately
reviewed packaging step; this CLI never guesses a group-to-query map. Aggregation
order is canonical package order, so metric comparison uses absolute1e-12 and
strict counts/types/schema rather than a claim of bitwise identity with an
arbitrary historical summation order. No bootstrap or selection is performed.

## Private historical train/selection replay

Private ID-bearing Q/C/fullY/scores are not included in clone. A reviewer needs
separately granted access to a directory package and independently issued
manifest SHA, access contract and bounded execution approval. The API does not
manufacture them. No raw package redistribution or historical endorsement is
inferred from a supplied local hash.

```sh
uv run --locked python -m scripts.replay_ranking_claim --package artifacts/reproduction/study --expected-manifest-sha <externally-issued-sha> --access-contract artifacts/reproduction/access.json --issued-access-sha <externally-issued-sha> --execution-approval artifacts/reproduction/budget.json --issued-approval-sha <externally-issued-sha> --evidence-out artifacts/reproduction/replay-evidence.json
```

These are genuine implemented argument names; placeholders require an actual
external reviewer decision. All paths are project-relative and confined after
symlink resolution. The output parent must already exist. Evidence is optional,
exclusive and cannot be written inside the input package.

Access contract exact body: version1,scope
`reviewed_train_selection_ranking_replay_access`,approved:true,manifest ref,
stage,query_range,permissions with queries/candidates/targets/scores true and
confirmation/final false. Execution approval exact keys: version1,scope
`bounded_fullY_ranking_claim_replay`,approved:true,manifest ref,access ref,
code mapping exactly this entry and ranking_metrics.py hashes,limits
(cpu_seconds,wall_seconds,rss_bytes),claim_path,allowed_replay_attempts1,
allowed_fit_attempts0,allowed_native_predictions0. Both reference digests must
match the **original separately issued CLI SHA**, not a locally resealed substitute.
Strict bool/int types are enforced.

The approved claim path must be a new JSON file under
`artifacts/reproduction/claims/` (directory exists beforehand). Before opening
input row streams the entry exclusively consumes that attempt, flushes+fsyncs
file and directory, and retains the written raw SHA. Private inputs remain
read-only; the specifically approved audit claim is a necessary write even if
optional evidence is omitted. A failure/lost receipt does not grant retry or
allow deletion/replacement of the consumed claim. Another reviewer attempt needs
separate governance, not a renamed output directory.

This version intentionally supports only the current historical development
windows: train within2019-10-08..21 and selection within2019-10-22..24 UTC, with
label cutoff no later than the respective end. Confirmation/final stages and
renamed selection packages containing their ranges fail **before Q/Y streams**.
Per-query ranges/UTC midnight/maturity are rechecked before Y opens. Future or
other-dataset replay requires a separately reviewed interface revision; this
entry cannot bypass the coordinator's heldout source/prediction/Y-unlock flow.

## Resources, failure and proof limit

The process charges absolute SELF CPU including imports,≤300CPU/300wall seconds,
≤512MiB lifetime peakRSS, zero subprocesses. Explicit private limits may only
reduce those ceilings; train≤26000Q/5720000C, selection≤4000Q/880000C,
fullY≤2000000 rows overall. JSONL lines≤16KiB and metadata≤64KiB. Streaming and
per-query processing bound allocations; these are cooperative guards, not OS
hard memory/time caps or measured throughput guarantees on real packages.

File/authority hashes are verified from the actual consumed bytes and repinned.
All row streams close first; complete data and authority pins are then rechecked
before success evidence or resource sampling. Both evidence modes additionally
recheck small authority pins at terminal return.
Small post-evidence authority checks/fsync/exit tail remain charged by an
independent full-lifetime process receipt for private acceptance. Late own failed
markers, changed pins, cleanup/deadline/CPU/RSS errors prevent success; primary
failures survive secondary cleanup/writer errors. Requested failure evidence is
exclusive too. Failed partial files/claim remain visible. Exit0 and the final
external receipt are required beyond an evidence status file.

Aggregate output has no query/user/item identifiers. It proves calculation from
this anchored supplied package, not completeness of marketplace logging, source
feature formulas, actual training weights, native model fidelity, newly untouched
holdout, generalization or freedom from development selection bias. Historical
strong_control/recovered-source seals and accepted paths remain unchanged.

The synthetic suite models a fresh process by mocking only RUSAGE_CHILDREN to
zero within each fixture, restoring the prior outer counter afterward. Actual
SELF CPU/RSS remain measured. Dedicated positive/NaN descendant-counter probes
reject; production CLI's zero-child requirement is not weakened. This allows
scoped tests after unrelated earlier tests reaped subprocesses.
