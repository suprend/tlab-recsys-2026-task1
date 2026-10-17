"""HYP-053 coverage-only pilot. C0 stays exact; no model or feature-search claim."""
from __future__ import annotations

import time
EPISODE_START = time.monotonic()

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import resource

import duckdb

from scripts import candidate_pilot as core
from scripts.anchor_pilot import RunDeadline, StageLedger, directory_bytes, peak_rss_bytes, save_json
from scripts.protocol_manifest import load_run_manifest, sha256_file, validate_protocol

ROOT = Path(core.__file__).resolve().parents[1]
SPEC = dict(version=1, hypothesis='HYP-053', baseline='P200_R20_no_refill',
            treatment='P140_R20_K3x20_no_refill', window_hours=168,
            profile='distinct_latest_view_products_known_event_bucket_category',
            membership='latest_global_past_bucket_no_older_backoff',
            source_order=['P', 'R', 'K1', 'K2', 'K3'], bootstrap_draws=1000, bootstrap_seed=2026)


def need(ok, message):
    if not ok:
        raise ValueError(message)


def direct(_name, operation):
    return operation()


def rows(con, sql, params=None):
    cursor = con.execute(sql, params or [])
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def round_robin_capped(sources):
    """NEXT UNSEEN per turn, within independently capped source lists only."""
    offsets, seen, result = [0] * len(sources), set(), []
    while True:
        emitted = False
        for index, source in enumerate(sources):
            while offsets[index] < len(source):
                item = source[offsets[index]]
                offsets[index] += 1
                if item not in seen:
                    seen.add(item)
                    result.append(item)
                    emitted = True
                    break
        if not emitted:
            return result


def create_policies(con, config, *, stage=direct, check=lambda: None):
    """Only events and pilot_queries are read. Labels need not exist."""
    config = validate_protocol(config)
    s = config['candidates']
    need(config['pilot'] == {'start':'2019-10-08T00:00:00Z','end':'2019-10-11T00:00:00Z'} and
         config['budget']['max_anchors'] <= 6000 and config['budget']['max_candidate_pairs'] <= 1320000 and
         config['query']['eligibility_hours'] == 48 and config['target']['horizon_hours'] == 24 and
         config['target']['include_anchor'] is True and config['target']['include_end'] is False,
         'Fixed8-10Oct B48h/24h development pilot only')
    need(con.execute('SELECT count(*) FROM pilot_queries').fetchone()[0] > 0, 'Nonempty immutable Q required')
    need(s['popular_limit'] == 200 and s['recent_limit'] == 20 and s['max_unique'] == 220 and
         s['popular_window_hours'] == s['recent_window_hours'] == 168 and
         s['recent_event_types'] == ['view', 'cart', 'purchase'], 'Exact accepted C0 arm required')
    need(con.execute('SELECT count(*) FROM pilot_queries WHERE label_is_mature IS DISTINCT FROM true').fetchone()[0] == 0,
         'This pilot requires all queries mature; never turn censoring into zero')
    con.execute('CREATE OR REPLACE TEMP TABLE cc_pop(anchor TIMESTAMP,product_id BIGINT,buyers BIGINT)')

    def capture(name, operation):
        result = stage(name, operation)
        if name.startswith('popular_counts_'):
            check()
            stage('snapshot_' + name, lambda: con.execute('''INSERT INTO cc_pop
                SELECT d.anchor,p.product_id,p.popularity_distinct_users FROM pilot_popularity p
                CROSS JOIN (SELECT DISTINCT anchor FROM pilot_day_queries) d'''))
        return result

    baseline = core.create_candidates(con, config, stage=capture)
    core.verify_catalog(con, config, stage=stage)
    con.execute('''CREATE OR REPLACE TEMP TABLE cc_sources AS
        SELECT 'C0' arm,query_id,product_id,'P' src,popular_source_rank source_rank,0 priority
        FROM pilot_candidates WHERE from_popular UNION ALL
        SELECT 'C0',query_id,product_id,'R',recent_source_rank,1 FROM pilot_candidates WHERE from_recent UNION ALL
        SELECT 'C1',query_id,product_id,'P',popular_source_rank,0 FROM pilot_candidates
        WHERE from_popular AND popular_source_rank<=140 UNION ALL
        SELECT 'C1',query_id,product_id,'R',recent_source_rank,1 FROM pilot_candidates WHERE from_recent''')
    con.execute('''CREATE OR REPLACE TEMP TABLE cc_membership(anchor TIMESTAMP,product_id BIGINT,
        category_id BIGINT,missing BOOLEAN,ambiguous BOOLEAN,latest_timestamp TIMESTAMP)''')
    con.execute('''CREATE OR REPLACE TEMP TABLE cc_support(query_id VARCHAR,view_products BIGINT,
        known_products BIGINT,missing_products BIGINT,ambiguous_products BIGINT,selected_categories BIGINT)''')
    con.execute('''CREATE OR REPLACE TEMP TABLE cc_profiles(query_id VARCHAR,category_id BIGINT,
        product_support BIGINT,last_view TIMESTAMP,category_rank BIGINT)''')
    start = core.naive_utc(core.utc(config['source']['start']))
    for (anchor,) in con.execute('SELECT DISTINCT anchor FROM pilot_queries ORDER BY anchor').fetchall():
        check()
        day = anchor.strftime('%Y%m%d')
        lower = anchor - timedelta(hours=168)

        def sql(label, statement, params=None):
            return stage(label + '_' + day, lambda: con.execute(statement, params or []))

        sql('membership_latest', '''CREATE OR REPLACE TEMP TABLE cc_latest AS
            SELECT product_id,max(event_time) latest_timestamp FROM events
            WHERE event_time>=? AND event_time<? AND product_id IS NOT NULL GROUP BY product_id''', [start, anchor])
        sql('membership_bucket', '''INSERT INTO cc_membership SELECT ?,l.product_id,
            CASE WHEN count(DISTINCT e.category_id)=1 AND count(*) FILTER(WHERE e.category_id IS NULL)=0
                 THEN min(e.category_id) END category_id,
            count(DISTINCT e.category_id)=0 missing,
            count(DISTINCT e.category_id)>1 OR (count(DISTINCT e.category_id)>0 AND
                count(*) FILTER(WHERE e.category_id IS NULL)>0) ambiguous,l.latest_timestamp
            FROM cc_latest l JOIN events e ON e.product_id=l.product_id AND e.event_time=l.latest_timestamp
            WHERE e.event_time>=? AND e.event_time<? GROUP BY l.product_id,l.latest_timestamp''', [anchor, start, anchor])
        sql('latest_user_views', '''CREATE OR REPLACE TEMP TABLE cc_view_latest AS
            SELECT q.query_id,q.user_id,e.product_id,max(e.event_time) latest_view FROM pilot_queries q
            JOIN events e ON e.user_id=q.user_id WHERE q.anchor=? AND e.event_type='view'
            AND e.event_time>=? AND e.event_time<? AND e.product_id IS NOT NULL
            GROUP BY q.query_id,q.user_id,e.product_id''', [anchor, lower, anchor])
        sql('view_bucket', '''CREATE OR REPLACE TEMP TABLE cc_view_bucket AS
            SELECT v.query_id,v.product_id,v.latest_view,
            CASE WHEN count(DISTINCT e.category_id)=1 AND count(*) FILTER(WHERE e.category_id IS NULL)=0
                 THEN min(e.category_id) END category_id,
            count(DISTINCT e.category_id)=0 missing,
            count(DISTINCT e.category_id)>1 OR (count(DISTINCT e.category_id)>0 AND
                count(*) FILTER(WHERE e.category_id IS NULL)>0) ambiguous
            FROM cc_view_latest v JOIN events e ON e.user_id=v.user_id AND e.product_id=v.product_id
                AND e.event_time=v.latest_view AND e.event_type='view'
            GROUP BY v.query_id,v.product_id,v.latest_view''')
        sql('profiles', '''INSERT INTO cc_profiles SELECT query_id,category_id,count(*) product_support,
            max(latest_view) last_view,row_number() OVER(PARTITION BY query_id
                ORDER BY count(*) DESC,max(latest_view) DESC,category_id ASC) category_rank
            FROM cc_view_bucket WHERE category_id IS NOT NULL GROUP BY query_id,category_id''')
        sql('profile_support', '''INSERT INTO cc_support SELECT q.query_id,count(v.product_id),
            count(v.product_id) FILTER(WHERE v.category_id IS NOT NULL),
            count(v.product_id) FILTER(WHERE v.missing),count(v.product_id) FILTER(WHERE v.ambiguous),
            (SELECT count(*) FROM cc_profiles p WHERE p.query_id=q.query_id AND category_rank<=3)
            FROM pilot_queries q LEFT JOIN cc_view_bucket v USING(query_id) WHERE q.anchor=? GROUP BY q.query_id''', [anchor])
        sql('category_source', '''INSERT INTO cc_sources SELECT 'C1',p.query_id,m.product_id,
            'K'||CAST(p.category_rank AS VARCHAR),
            row_number() OVER(PARTITION BY p.query_id,p.category_rank
                ORDER BY coalesce(b.buyers,0) DESC,m.product_id ASC) source_rank,
            CAST(p.category_rank+1 AS INTEGER) priority
            FROM cc_profiles p JOIN pilot_queries q USING(query_id)
            JOIN cc_membership m ON m.anchor=q.anchor AND m.category_id=p.category_id
            LEFT JOIN cc_pop b ON b.anchor=m.anchor AND b.product_id=m.product_id
            WHERE q.anchor=? AND p.category_rank<=3 QUALIFY source_rank<=20''', [anchor])
        check()
    con.execute('CREATE OR REPLACE TEMP TABLE cc_lists(arm VARCHAR,query_id VARCHAR,product_id BIGINT,position BIGINT)')
    grouped = rows(con, '''SELECT arm,query_id,
        list(product_id ORDER BY source_rank) FILTER(WHERE src='P') P,
        list(product_id ORDER BY source_rank) FILTER(WHERE src='R') R,
        list(product_id ORDER BY source_rank) FILTER(WHERE src='K1') K1,
        list(product_id ORDER BY source_rank) FILTER(WHERE src='K2') K2,
        list(product_id ORDER BY source_rank) FILTER(WHERE src='K3') K3
        FROM cc_sources GROUP BY arm,query_id ORDER BY arm,query_id''')
    batch = []
    for group in grouped:
        check()
        order = round_robin_capped([group[name] or [] for name in SPEC['source_order']])
        batch.extend((group['arm'], group['query_id'], item, position) for position, item in enumerate(order, 1))
        if len(batch) >= 4096:
            con.executemany('INSERT INTO cc_lists VALUES (?,?,?,?)', batch)
            batch.clear()
    if batch:
        con.executemany('INSERT INTO cc_lists VALUES (?,?,?,?)', batch)
    con.execute('''CREATE OR REPLACE TEMP TABLE cc_sizes AS SELECT q.query_id,p.arm,count(l.product_id) candidate_count
        FROM pilot_queries q CROSS JOIN (VALUES ('C0'),('C1')) p(arm)
        LEFT JOIN cc_lists l ON l.query_id=q.query_id AND l.arm=p.arm GROUP BY q.query_id,p.arm''')
    need(con.execute('SELECT coalesce(max(candidate_count),0) FROM cc_sizes').fetchone()[0] <= 220, 'Candidate cap')
    need(con.execute('SELECT count(*) FROM cc_lists').fetchone()[0] <= 2 * config['budget']['max_candidate_pairs'], 'Total candidate cap')
    need(con.execute('''SELECT count(*) FROM cc_lists l JOIN pilot_queries q USING(query_id)
        LEFT JOIN cc_membership m ON m.anchor=q.anchor AND m.product_id=l.product_id
        WHERE m.product_id IS NULL OR m.latest_timestamp>=q.anchor''').fetchone()[0] == 0, 'C outside strict-past U')
    con.execute('''CREATE OR REPLACE TEMP TABLE cc_eval_lists AS
        SELECT 'native' cohort,* FROM cc_lists UNION ALL SELECT 'matched',l.* FROM cc_lists l
        JOIN (SELECT query_id,min(candidate_count) m FROM cc_sizes GROUP BY query_id) s USING(query_id)
        WHERE l.position<=s.m''')
    return dict(baseline=baseline, source_rows=con.execute('SELECT count(*) FROM cc_sources').fetchone()[0],
                native_rows=con.execute('SELECT count(*) FROM cc_lists').fetchone()[0])


def compare_original_baseline(con, path, expected_sha):
    need(sha256_file(path) == expected_sha, 'Cached baseline hash differs')
    con.execute('CREATE OR REPLACE TEMP TABLE cc_original AS SELECT * FROM read_parquet(?)', [str(path)])
    need(con.execute('''SELECT count(*) FROM ((SELECT * FROM pilot_candidates EXCEPT ALL SELECT * FROM cc_original)
        UNION ALL (SELECT * FROM cc_original EXCEPT ALL SELECT * FROM pilot_candidates))''').fetchone()[0] == 0,
        'C0 differs from independently cached accepted parquet; no silent rebase')


def seal_candidates(con, directory, *, check=lambda: None):
    """Physically seal both lists and Q before the caller imports labels."""
    sealed = {}
    for table in ('pilot_queries', 'pilot_candidates', 'cc_eval_lists', 'cc_sources', 'cc_support', 'cc_profiles', 'cc_membership'):
        check()
        path = directory / (table + '.parquet')
        need(not path.exists(), 'Never overwrite candidate seal')
        con.execute('COPY (SELECT * FROM ' + table + ') TO ? (FORMAT PARQUET,COMPRESSION ZSTD)', [str(path)])
        sealed[table] = dict(path=str(path), sha256=sha256_file(path), bytes=path.stat().st_size)
    save_json(directory / 'candidate-seal.json', dict(version=1, label_reads=0, files=sealed))
    return sealed


def evaluate_policies(con, sealed):
    for table, item in sealed.items():
        need(sha256_file(Path(item['path'])) == item['sha256'], 'Sealed candidate file changed')
        if table in ('pilot_queries', 'cc_eval_lists'):
            con.execute('CREATE OR REPLACE TEMP TABLE ' + table + ' AS SELECT * FROM read_parquet(?)', [item['path']])
    counts = con.execute('SELECT count(*),count(DISTINCT (query_id,product_id)) FROM pilot_labels').fetchone()
    need(counts[0] == counts[1], 'Duplicate fullY target')
    need(con.execute('''SELECT count(*) FROM pilot_labels y LEFT JOIN pilot_queries q USING(query_id)
        WHERE q.query_id IS NULL OR y.product_id IS NULL OR y.catalog_seen_before IS NULL
        OR y.pair_seen_before IS NULL OR q.label_is_mature IS DISTINCT FROM true''').fetchone()[0] == 0, 'Invalid/mature fullY')
    need(con.execute('''SELECT count(*) FROM pilot_labels y JOIN cc_eval_lists l USING(query_id,product_id)
        WHERE NOT y.catalog_seen_before''').fetchone()[0] == 0, 'Retrieved target contradicts catalog')
    con.execute('''CREATE OR REPLACE TEMP TABLE cc_coverage AS
        WITH target AS (SELECT query_id,count(*) targets,count(*) FILTER(WHERE pair_seen_before) repeats,
            count(*) FILTER(WHERE NOT pair_seen_before) new_pairs FROM pilot_labels GROUP BY query_id),
        hits AS (SELECT l.cohort,l.arm,l.query_id,count(*) candidates,count(y.product_id) hits,
            count(y.product_id) FILTER(WHERE y.pair_seen_before) repeat_hits,
            count(y.product_id) FILTER(WHERE NOT y.pair_seen_before) new_hits FROM cc_eval_lists l
            LEFT JOIN pilot_labels y USING(query_id,product_id) GROUP BY l.cohort,l.arm,l.query_id)
        SELECT q.query_id,q.user_id,q.anchor,c.cohort,c.arm,coalesce(t.targets,0) targets,
            coalesce(t.repeats,0) repeats,coalesce(t.new_pairs,0) new_pairs,
            coalesce(h.candidates,0) candidates,coalesce(h.hits,0) hits,
            coalesce(h.repeat_hits,0) repeat_hits,coalesce(h.new_hits,0) new_hits
        FROM pilot_queries q CROSS JOIN (VALUES ('native','C0'),('native','C1'),('matched','C0'),('matched','C1')) c(cohort,arm)
        LEFT JOIN target t USING(query_id) LEFT JOIN hits h ON h.query_id=q.query_id AND h.cohort=c.cohort AND h.arm=c.arm''')
    con.execute('''CREATE OR REPLACE TEMP TABLE cc_target_changes AS SELECT y.query_id,y.product_id,m.cohort,
        CASE WHEN b.product_id IS NULL THEN 'gained' ELSE 'lost' END direction,
        NOT y.pair_seen_before new_pair
        FROM pilot_labels y CROSS JOIN (VALUES ('native'),('matched')) m(cohort)
        LEFT JOIN cc_eval_lists b ON b.query_id=y.query_id AND b.product_id=y.product_id AND b.arm='C0' AND b.cohort=m.cohort
        LEFT JOIN cc_eval_lists t ON t.query_id=y.query_id AND t.product_id=y.product_id AND t.arm='C1' AND t.cohort=m.cohort
        WHERE (b.product_id IS NULL AND t.product_id IS NOT NULL)
           OR (b.product_id IS NOT NULL AND t.product_id IS NULL)''')
    con.execute('''CREATE OR REPLACE TEMP TABLE cc_changes AS SELECT q.query_id,m.cohort,
        count(c.product_id) FILTER(WHERE c.direction='gained') gained,
        count(c.product_id) FILTER(WHERE c.direction='lost') lost,
        count(c.product_id) FILTER(WHERE c.direction='gained' AND c.new_pair) new_gained,
        count(c.product_id) FILTER(WHERE c.direction='lost' AND c.new_pair) new_lost
        FROM pilot_queries q CROSS JOIN (VALUES ('native'),('matched')) m(cohort)
        LEFT JOIN cc_target_changes c ON c.query_id=q.query_id AND c.cohort=m.cohort GROUP BY q.query_id,m.cohort''')
    summaries = rows(con, '''SELECT cohort,arm,count(*) queries,count(*) FILTER(WHERE targets>0) positive_queries,
        sum(targets) targets,sum(hits) hits,sum(repeats) repeat_targets,sum(repeat_hits) repeat_hits,
        sum(new_pairs) new_targets,sum(new_hits) new_hits,sum(candidates) candidate_rows,
        count(*) FILTER(WHERE candidates=0) emptyC,count(*) FILTER(WHERE candidates<220) underfilled,
        avg(hits*1.0/nullif(targets,0)) positive_query_macro_recall,
        sum(hits)*1.0/nullif(sum(targets),0) micro_recall FROM cc_coverage GROUP BY cohort,arm ORDER BY cohort,arm''')
    changes = rows(con, 'SELECT cohort,sum(gained) gained,sum(lost) lost,sum(new_gained) new_gained,sum(new_lost) new_lost FROM cc_changes GROUP BY cohort ORDER BY cohort')
    for change in changes:
        pair = {r['arm']: r for r in summaries if r['cohort'] == change['cohort']}
        need(pair['C1']['hits'] - pair['C0']['hits'] == change['gained'] - change['lost'], 'Gain/loss accounting')
    return dict(cells=summaries, changes=changes,
                by_day=rows(con, '''SELECT anchor,cohort,arm,count(*) queries,sum(targets) targets,sum(hits) hits,
                    avg(hits*1.0/nullif(targets,0)) positive_query_macro_recall FROM cc_coverage GROUP BY anchor,cohort,arm ORDER BY anchor,cohort,arm'''),
                support=rows(con, 'SELECT sum(view_products) view_products,sum(known_products) known_products,sum(missing_products) missing_products,sum(ambiguous_products) ambiguous_products FROM cc_support'),
                candidate_metadata=rows(con, '''SELECT l.cohort,l.arm,count(*) candidate_rows,
                    count(*) FILTER(WHERE m.category_id IS NOT NULL) known_category_rows,
                    count(*) FILTER(WHERE m.missing) missing_category_rows,
                    count(*) FILTER(WHERE m.ambiguous) ambiguous_category_rows
                    FROM cc_eval_lists l JOIN pilot_queries q USING(query_id)
                    JOIN cc_membership m ON m.anchor=q.anchor AND m.product_id=l.product_id GROUP BY l.cohort,l.arm ORDER BY l.cohort,l.arm'''))


def export_target_changes(con, directory, *, check=lambda: None):
    """Private post-label evidence; public report keeps aggregate counts only."""
    artifacts = {}
    for table, name, order in (('cc_target_changes', 'target-changes.parquet', 'query_id,cohort,product_id'),
                               ('cc_changes', 'query-changes.parquet', 'query_id,cohort')):
        check()
        path = directory / name
        need(not path.exists(), 'Never overwrite target-change evidence')
        con.execute('COPY (SELECT * FROM ' + table + ' ORDER BY ' + order + ') TO ? (FORMAT PARQUET,COMPRESSION ZSTD)', [str(path)])
        check()
        artifacts[name] = dict(path=str(path), sha256=sha256_file(path), bytes=path.stat().st_size)
    return artifacts


def paired_bootstrap(con, *, draws=1000, seed=2026, check=lambda: None):
    """Whole-user resampling; undefined-positive draws are counted, never redrawn."""
    grouped = {}
    for row in rows(con, 'SELECT * FROM cc_coverage ORDER BY query_id,cohort,arm'):
        entry = grouped.setdefault(row['user_id'], {})
        key = row['cohort'], row['arm']
        total, positive = entry.get(key, (0.0, 0))
        if row['targets']:
            total += row['hits'] / row['targets']
            positive += 1
        entry[key] = total, positive
    users = sorted(grouped)
    values = {'native': [], 'matched': []}
    undefined = 0
    rng = random.Random(seed)
    for _ in range(draws):
        check()
        selected = rng.choices(users, k=len(users)) if users else []
        totals = {(cohort, arm): [0.0, 0] for cohort in values for arm in ('C0', 'C1')}
        for user in selected:
            for key, (total, count) in grouped[user].items():
                totals[key][0] += total
                totals[key][1] += count
        if not totals[('native', 'C0')][1]:
            undefined += 1
            continue
        for cohort in values:
            values[cohort].append(totals[(cohort, 'C1')][0] / totals[(cohort, 'C1')][1] -
                                totals[(cohort, 'C0')][0] / totals[(cohort, 'C0')][1])
    result = dict(draws=draws, seed=seed, undefined_draws=undefined, redrawn=0,
                  estimand='positive-fullY-query-macro Recall C1-C0; user clusters')
    for cohort, vector in values.items():
        vector.sort()
        result[cohort] = dict(valid_draws=len(vector), ci95=None if undefined or not vector else
                            [vector[int(.025 * (len(vector)-1))], vector[int(.975 * (len(vector)-1))]])
    return result


def run(anchor_run, baseline_run, baseline_sha, output, *, cpu=1200, wall=1800, rss=6*2**30, spill=2*2**30):
    started, cpu_started = EPISODE_START, 0.0
    deadline = RunDeadline(wall, started_at=started)
    output = output.resolve()
    need(not output.exists(), 'Fresh output directory required')
    anchor = load_run_manifest(anchor_run / 'run.json')
    baseline = load_run_manifest(baseline_run / 'run.json')
    for directory, manifest in ((anchor_run, anchor), (baseline_run, baseline)):
        completed = json.loads((directory / 'report.json').read_text())
        need(completed['status'] == 'complete' and completed['run_id'] == manifest['run_id'], 'Complete accepted input run required')
    config = anchor['identity']['protocol']
    source_refs = anchor['identity']['input_hashes']
    need(len(source_refs) == 1, 'One accepted source DB required')
    source_name, source_sha = next(iter(source_refs.items()))
    need(not Path(source_name).is_absolute() and '..' not in Path(source_name).parts, 'Relative source path required')
    source = ROOT / source_name
    paths = {name: ROOT / anchor['artifact_refs'][name] for name in ('queries', 'labels')}
    baseline_path = ROOT / baseline['artifact_refs']['candidates']
    input_refs = {str(source): source_sha, **{str(directory/name): sha256_file(directory/name)
        for directory in (anchor_run, baseline_run) for name in ('run.json', 'report.json')}}
    label_expected = baseline['identity']['input_hashes'].get(paths['labels'].relative_to(ROOT).as_posix())
    need(label_expected is not None, 'Accepted fullY fingerprint required')
    input_refs[str(paths['labels'])] = label_expected  # Declared now; body authentication follows C seal.
    input_refs[str(baseline_path)] = baseline_sha

    def check():
        deadline.check()
        if time.process_time()-cpu_started > cpu:
            raise TimeoutError('Inclusive CPU ceiling')
        if peak_rss_bytes() > rss:
            raise MemoryError('Observed RSS ceiling')
        if output.exists():
            scratch = directory_bytes(output/'temp') if (output/'temp').exists() else 0
            if scratch > spill or directory_bytes(output)-scratch > 256*2**20:
                raise OSError('Separate scratch/output ceiling')

    for path, expected in [(source, source_sha), (paths['queries'], baseline['identity']['input_hashes'].get(paths['queries'].relative_to(ROOT).as_posix()))]:
        check()
        need(expected is not None and sha256_file(path) == expected, 'Accepted data fingerprint mismatch: ' + str(path))
        input_refs[str(path)] = expected
    need(baseline['identity']['input_hashes'].get(source_name) == source_sha, 'Baseline data source differs')
    code_paths = [Path(__file__), Path(core.__file__), ROOT/'scripts/manual_features.py', ROOT/'scripts/protocol_manifest.py', ROOT/'scripts/anchor_pilot.py', ROOT/'scripts/temporal_contract.py', ROOT/'uv.lock']
    identity = dict(spec=SPEC, protocol=config, inputs=input_refs, cached_baseline_sha256=baseline_sha,
                    source_code={str(path): sha256_file(path) for path in code_paths})
    run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    temp = output / 'temp'
    temp.mkdir()
    report = dict(status='running', run_id=run_id, identity=identity, fits=0, model_predictions=0,
                  limits=dict(cpu=cpu, wall=wall, rss=rss, spill=spill, threads=2), quality_claim=False)
    save_json(output/'run.json', report)
    con = timer = ledger = None
    primary = None
    try:
        con = duckdb.connect(str(source), read_only=True)
        timer = deadline.interrupt_timer(con)
        ledger = StageLedger(temp, con, deadline)
        con.execute('SET threads=2')
        con.execute("SET memory_limit='2GB'")
        con.execute('SET max_temp_directory_size=?', [str(spill)+'B'])
        con.execute('SET temp_directory=?', [str(temp)])
        con.execute('CREATE TEMP TABLE pilot_queries AS SELECT * FROM read_parquet(?)', [str(paths['queries'])])

        def stage(name, operation):
            check()
            result = ledger(name, operation)
            check()
            return result

        report['construction'] = create_policies(con, config, stage=stage, check=check)
        compare_original_baseline(con, baseline_path, baseline_sha)
        sealed = seal_candidates(con, output, check=check)
        check()
        # Even the target-body hash follows physical sealing and exact independent C0 parity.
        need(sha256_file(paths['labels']) == label_expected, 'Accepted fullY body fingerprint differs')
        con.execute('CREATE TEMP TABLE pilot_labels AS SELECT * FROM read_parquet(?)', [str(paths['labels'])])
        report['coverage'] = evaluate_policies(con, sealed)
        report['target_change_artifacts'] = export_target_changes(con, output, check=check)
        report['bootstrap'] = paired_bootstrap(con, check=check)
        con.execute("COPY cc_coverage TO ? (FORMAT PARQUET,COMPRESSION ZSTD)", [str(output/'query-coverage.parquet')])
        for path, expected in input_refs.items():
            check()
            need(sha256_file(Path(path)) == expected, 'Late input mutation')
        check()
        report['status'] = 'complete_coverage_only_pending_review'
    except BaseException as error:
        primary = error
        report.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        errors = []
        operations = []
        if timer is not None:
            operations.append(('timer_cancel', timer.cancel))
        if con is not None:
            operations.append(('connection_close', con.close))
        for name, operation in operations:
            try:
                operation()
            except BaseException as error:
                errors.append((name, error))
        report.update(stages=[] if ledger is None else ledger.rows, seconds=time.monotonic()-started, cpu_seconds_prefix=time.process_time()-cpu_started,
                      peak_rss_bytes=peak_rss_bytes(), cleanup_errors=[dict(operation=n,error_type=type(e).__name__) for n,e in errors],
                      complete_process_exit_pending=True)
        if errors:
            report['status'] = 'failed'
        try:
            save_json(output/'report.json', report)
        except BaseException as error:
            errors.append(('report_write', error))
        if errors:
            group = BaseExceptionGroup('Pilot finalization failures: '+','.join(n for n,_ in errors), [e for _,e in errors])
            if primary is None:
                raise group
            try:
                primary.add_note(str(group))
            except BaseException:
                pass
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--anchor-run', type=Path, required=True)
    parser.add_argument('--baseline-run', type=Path, required=True)
    parser.add_argument('--baseline-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.anchor_run.resolve(), args.baseline_run.resolve(), args.baseline_sha256, args.output)


if __name__ == '__main__':
    main()
