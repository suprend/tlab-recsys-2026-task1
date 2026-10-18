"""Explicit reserved-customer H&M test collection and fixed locked fits.

Customer-test entry points require the separate v2 customer decision lock.
The history-only candidate helper deliberately accepts an explicit Q relation;
it never selects or replaces customers using the historical seed2026 cohort.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
import re
import time
import traceback

from scripts import hm_experiment as legacy
from scripts.hm_experiment import load_part,model_arrays,model_pool

ANCHOR = '2020-09-16'
SALT = 'hm-v2-customer-test-20261018'
ROOT = Path(__file__).resolve().parents[1]
COLLECTION_FORMAT = 'hm-auto-holdout-collection-v2'
FIT_FORMAT = 'hm-auto-holdout-fit-v2'


def gate_module():
    from scripts import hm_auto_holdout_lock
    return hm_auto_holdout_lock


def require(condition,message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    path = Path(path)
    require(path.stat().st_size<=2*1024**2,'Bounded JSON metadata required')
    def pairs(items):
        result = {}
        for key,value in items:
            require(key not in result,'Duplicate JSON property')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON constant')
    def number(value):
        parsed=float(value)
        require(math.isfinite(parsed),'Nonfinite JSON number')
        return parsed
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=reject,parse_float=number)


def checkout_path(value):
    path = (ROOT/Path(value)).resolve()
    require(path.is_relative_to(ROOT.resolve()),'Checkout path required')
    return path


def deadline_for(seconds):
    require(type(seconds) in (int,float) and math.isfinite(seconds) and 0<seconds<=1800,
            'Finite positive wall deadline at most1800 required')
    return legacy.Deadline(seconds)


def new_output(value):
    path = Path(value).resolve()
    allowed = (ROOT/'artifacts/hm-auto-v2/customer-test').resolve()
    require(allowed.is_relative_to(ROOT.resolve()) and path!=allowed and path.is_relative_to(allowed),
            'New customer-test child output required')
    path.mkdir(parents=True,exist_ok=False)
    return path


def file_pin(pin,deadline):
    path = checkout_path(pin['path'])
    require(path.stat().st_size==pin['bytes'] and legacy.sha256_file(path,deadline)==pin['sha256'],
            'Locked private file bytes differ')
    return path


def id_digest(con,table,order,deadline):
    require((table,order) in {('hm_holdout_reserved','reservation_rank'),('hm_holdout_excluded','customer_id')},
            'Known ID digest relation required')
    import hashlib
    digest = hashlib.sha256()
    cursor = con.execute(f'SELECT customer_id FROM {table} ORDER BY {order}')
    while block:=cursor.fetchmany(8192):
        deadline.check()
        for (value,) in block:
            encoded=value.encode('utf-8')
            digest.update(len(encoded).to_bytes(4,'big'));digest.update(encoded)
    return digest.hexdigest()


def locked_sources(plan,deadline):
    require(legacy.sha256_file(plan.path,deadline)==plan.sha256,'Decision lock changed')
    implementation = plan.data['implementation']
    require(legacy.runtime_identity()==implementation['runtime'],'Locked runtime changed')
    for name,sha in implementation['code'].items():
        require(Path(name).name==name and legacy.sha256_file(ROOT/'scripts'/name,deadline)==sha,
                'Locked implementation source changed')


def reserved_tables(con,plan,deadline):
    """After authorization, prove exact reserved IDs and old-query exclusion."""
    reservation = plan.data['reservation']
    manifest_path = checkout_path(reservation['manifest']['path'])
    require(legacy.sha256_file(manifest_path,deadline)==reservation['manifest']['sha256'],
            'Reservation manifest changed')
    manifest = read_json(manifest_path)
    require(manifest['status']=='completed' and manifest['no_test_targets_or_features'] is True,
            'Completed history-only reservation required')
    reserved = file_pin(reservation['files']['reserved-users.parquet'],deadline)
    excluded = file_pin(reservation['files']['excluded-users.parquet'],deadline)
    con.execute('''CREATE TEMP TABLE hm_holdout_reserved AS
        SELECT customer_id,cohort_hash,reservation_rank FROM read_parquet(?)''',[str(reserved)])
    con.execute('CREATE TEMP TABLE hm_holdout_excluded AS SELECT customer_id FROM read_parquet(?)',[str(excluded)])
    n = plan.data['cohort']['users']
    count,unique,ranks,minimum,maximum,bad = con.execute('''SELECT count(*),count(DISTINCT customer_id),
        count(DISTINCT reservation_rank),min(reservation_rank),max(reservation_rank),count(*) FILTER(
          WHERE customer_id IS NULL OR cohort_hash IS NULL OR reservation_rank IS NULL
          OR NOT regexp_full_match(customer_id,'[0-9a-f]{64}')
          OR cohort_hash<>sha256(customer_id || ':' || ?)) FROM hm_holdout_reserved''',[SALT]).fetchone()
    require((count,unique,ranks,minimum,maximum,bad)==(n,n,n,1,n,0),'Reserved IDs/hash/ranks differ')
    ordering_bad = con.execute('''SELECT count(*) FROM(SELECT reservation_rank,
        row_number() OVER(ORDER BY cohort_hash,customer_id) expected FROM hm_holdout_reserved)
        WHERE reservation_rank<>expected''').fetchone()[0]
    require(not ordering_bad,'Reservation hash order differs')
    excluded_count,excluded_unique,invalid = con.execute('''SELECT count(*),count(DISTINCT customer_id),
        count(*) FILTER(WHERE customer_id IS NULL OR NOT regexp_full_match(customer_id,'[0-9a-f]{64}'))
        FROM hm_holdout_excluded''').fetchone()
    require(excluded_count==excluded_unique==manifest['counts_history_only']['excluded_users'] and not invalid,
            'Excluded customer IDs differ')
    require(id_digest(con,'hm_holdout_reserved','reservation_rank',deadline)==reservation['reserved_ordered_ids_sha256']
            and id_digest(con,'hm_holdout_excluded','customer_id',deadline)==reservation['excluded_ordered_ids_sha256'],
            'Reservation ordered ID digest differs')
    overlap = con.execute('SELECT count(*) FROM hm_holdout_reserved JOIN hm_holdout_excluded USING(customer_id)').fetchone()[0]
    require(not overlap,'Reserved customers overlap the historical exclusion union')
    originals = manifest['counts_history_only']['actual_old_cohorts']
    require([item['anchor'] for item in originals]==['2020-08-12','2020-08-19','2020-08-26',
            '2020-09-02','2020-09-09','2020-09-16'],'All six old actual query cohorts required')
    paths = {}
    for item in originals:
        path = file_pin(item,deadline)
        paths[path] = item['sha256']
    for item in plan.data['train_collections']:
        path = file_pin(item['users'],deadline)
        require(path not in paths or paths[path]==item['users']['sha256'],'Old-query byte pin differs')
        paths[path] = item['users']['sha256']
    for path in paths:
        deadline.check()
        con.execute('CREATE OR REPLACE TEMP TABLE hm_holdout_old_q AS SELECT customer_id FROM read_parquet(?)',[str(path)])
        uncovered = con.execute('''SELECT count(*) FROM hm_holdout_old_q q WHERE NOT EXISTS(
            SELECT 1 FROM hm_holdout_excluded e WHERE e.customer_id=q.customer_id)''').fetchone()[0]
        require(not uncovered,'Old supervised query IDs are absent from the exclusion union')
        train_overlap = con.execute('SELECT count(*) FROM hm_holdout_old_q JOIN hm_holdout_reserved USING(customer_id)').fetchone()[0]
        require(not train_overlap,'Reserved customers overlap supervised query IDs')
    return dict(reserved_users=n,excluded_overlap_users=0,training_overlap_users=0)


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',value):
        raise ValueError('Simple relation identifier required')
    return '"'+value+'"'


def create_reserved_candidates(con, reserved_table='hm_holdout_reserved', *, anchor=ANCHOR, expected_users=20000):
    """Exact C0-Q120 for caller-provided customers; no outcomes/features.

    Production is fixed to20k IDs; tiny fixtures may specify a smaller count.
    Only pre-anchor transactions are read. All historical users contribute to
    global item buyers; Q is exactly the supplied unique history-eligible IDs.
    """
    if str(anchor) != ANCHOR or type(expected_users) is not int or not 0 < expected_users <= 20000:
        raise ValueError('Reserved candidates require Sep16 and positive bounded query count')
    table = identifier(reserved_table)
    fields = {row[0]:row[1].upper() for row in con.execute(f'DESCRIBE {table}').fetchall()}
    if fields.get('customer_id') != 'VARCHAR':
        raise ValueError('Reserved customer IDs must have VARCHAR type')
    count,unique,invalid = con.execute(f'''SELECT count(*),count(DISTINCT customer_id),
        count(*) FILTER(WHERE customer_id IS NULL OR NOT regexp_full_match(customer_id,'[0-9a-f]{{64}}'))
        FROM {table}''').fetchone()
    if count != expected_users or unique != count or invalid:
        raise ValueError('Reserved query IDs must be exact unique nonmissing64hex customers')
    con.execute('''CREATE TEMP TABLE hm_holdout_history AS
        SELECT t_dat,customer_id,article_id FROM transactions
        WHERE t_dat >= ?::DATE-INTERVAL '90 days' AND t_dat < ?::DATE''',[anchor,anchor])
    missing = con.execute(f'''SELECT count(*) FROM {table} q WHERE NOT EXISTS(
        SELECT 1 FROM hm_holdout_history h WHERE h.customer_id=q.customer_id)''').fetchone()[0]
    if missing:
        raise ValueError('Reserved customer lacks pre-cutoff90d history')
    con.execute('''CREATE TEMP TABLE hm_holdout_items AS
        SELECT article_id,buyers7,row_number() OVER(ORDER BY buyers7 DESC,article_id) global_rank FROM(
          SELECT article_id,count(DISTINCT customer_id) FILTER(
            WHERE t_dat >= ?::DATE-INTERVAL '7 days') buyers7
          FROM hm_holdout_history GROUP BY article_id)''',[anchor])
    if con.execute('SELECT count(*) FROM hm_holdout_items').fetchone()[0] < 120:
        raise ValueError('Observed90d catalog has fewer than120 articles')
    con.execute(f'''CREATE TEMP TABLE hm_holdout_recent AS
        SELECT customer_id,article_id,source_rank FROM(
          SELECT h.customer_id,h.article_id,row_number() OVER(
            PARTITION BY h.customer_id ORDER BY max(h.t_dat) DESC,h.article_id) source_rank
          FROM hm_holdout_history h JOIN {table} q USING(customer_id)
          GROUP BY h.customer_id,h.article_id) WHERE source_rank<=20''')
    con.execute(f'''CREATE TEMP TABLE hm_candidates AS
        WITH initial AS(
          SELECT customer_id,article_id,'recent' AS source,source_rank,1 priority FROM hm_holdout_recent
        ), global_unseen AS(
          SELECT q.customer_id,g.article_id,'global' AS source,g.global_rank source_rank,4 priority,
            row_number() OVER(PARTITION BY q.customer_id ORDER BY g.global_rank) refill_rank
          FROM {table} q CROSS JOIN hm_holdout_items g
          WHERE g.global_rank<=200 AND NOT EXISTS(
            SELECT 1 FROM hm_holdout_recent r WHERE r.customer_id=q.customer_id AND r.article_id=g.article_id)
        ), selected AS(
          SELECT * FROM initial UNION ALL
          SELECT customer_id,article_id,source,source_rank,priority FROM global_unseen g
          WHERE g.refill_rank<=120-(SELECT count(*) FROM initial r WHERE r.customer_id=g.customer_id)
        ) SELECT customer_id,article_id,source,source_rank,
          row_number() OVER(PARTITION BY customer_id ORDER BY priority,source_rank,article_id) candidate_rank
          FROM selected''')
    invalid = con.execute('''SELECT count(*) FROM(
        SELECT customer_id,count(*) n,count(DISTINCT article_id) unique_n FROM hm_candidates GROUP BY customer_id)
        WHERE n<>120 OR unique_n<>120''').fetchone()[0]
    represented = con.execute('SELECT count(DISTINCT customer_id) FROM hm_candidates').fetchone()[0]
    if invalid or represented != expected_users:
        raise ValueError('CustomQ C0-Q120 candidate-size/key invariant failed')
    return con.sql('SELECT * FROM hm_candidates ORDER BY customer_id,candidate_rank')


def attach_outcomes(con,anchor=ANCHOR):
    """Caller must first authorize, build Q/C, then register the feature frame."""
    require(anchor==ANCHOR,'Customer-test outcome anchor differs')
    columns = {row[0] for row in con.execute('DESCRIBE _hm_holdout_feature_frame').fetchall()}
    require(not {'label','query_weight','full_candidate_count'}.intersection(columns),
            'Feature frame must precede labels and weights')
    mismatch = con.execute('''SELECT count(*) FROM(
        (SELECT customer_id,article_id FROM hm_candidates EXCEPT SELECT customer_id,article_id FROM _hm_holdout_feature_frame)
        UNION ALL(SELECT customer_id,article_id FROM _hm_holdout_feature_frame EXCEPT SELECT customer_id,article_id FROM hm_candidates))''').fetchone()[0]
    duplicate = con.execute('''SELECT count(*) FROM(SELECT customer_id,article_id,count(*) n
        FROM _hm_holdout_feature_frame GROUP BY 1,2 HAVING n<>1)''').fetchone()[0]
    require(not mismatch and not duplicate,'Feature engine must preserve exact unique candidate keys')
    con.execute('''CREATE TEMP TABLE hm_exp_targets AS SELECT DISTINCT t.customer_id,t.article_id
        FROM transactions t JOIN hm_holdout_reserved q USING(customer_id)
        WHERE t.t_dat>=?::DATE AND t.t_dat<?::DATE+INTERVAL '7 days' ''',[anchor,anchor])
    con.execute('''CREATE TEMP TABLE hm_exp_frame AS SELECT f.*, (t.article_id IS NOT NULL)::BOOLEAN AS label,
        count(*) OVER(PARTITION BY f.customer_id)::INTEGER full_candidate_count,
        1.0/count(*) OVER(PARTITION BY f.customer_id) query_weight
        FROM _hm_holdout_feature_frame f LEFT JOIN hm_exp_targets t USING(customer_id,article_id)''')


def context_fresh(plan,deadline):
    locked_sources(plan,deadline)
    reservation = plan.data['reservation']
    require(legacy.sha256_file(checkout_path(reservation['manifest']['path']),deadline)==reservation['manifest']['sha256'],
            'Reservation manifest changed')
    for pin in reservation['files'].values():
        file_pin(pin,deadline)
    for item in plan.data['train_collections']:
        require(legacy.sha256_file(checkout_path(item['manifest']['path']),deadline)==item['manifest']['sha256'],
                'Locked training manifest changed')
        file_pin(item['users'],deadline)


def stop_sql(timer,con):
    if timer is not None:
        timer.cancel();timer.join(timeout=1)
    if con is not None:
        con.close()


def collect(database,output,decision_lock,expected_lock_sha256,wall_seconds=1800):
    deadline = deadline_for(wall_seconds)
    gate = gate_module()
    plan = gate.load_lock(decision_lock,expected_lock_sha256)
    gate.authorize_collect(plan,Path(database),Path(output))
    deadline.check()
    # No DB connection or row-level read occurs above this authorization line.
    output = new_output(output)
    report = dict(format=COLLECTION_FORMAT,status='running',holdout_lock_sha256=plan.sha256,
        anchor=ANCHOR,horizon_days=7,policy='C0-Q120',requested_users=plan.data['cohort']['users'],
        cohort=plan.data['cohort'],reservation_manifest_sha256=plan.data['reservation']['manifest']['sha256'],
        reserved_ordered_ids_sha256=plan.data['reservation']['reserved_ordered_ids_sha256'],
        excluded_ordered_ids_sha256=plan.data['reservation']['excluded_ordered_ids_sha256'],
        private_data='Real reserved customer IDs and outcomes; ignored local customer-test artifacts only.',
        history='[anchor-90d,anchor)',target='[anchor,anchor+7d)')
    con = timer = None
    try:
        report['resources'] = legacy.resource_preflight(output)
        source = Path(database).resolve()
        before = source.stat()
        report['database'] = {key:plan.data['database'][key] for key in ('sha256','bytes')}
        report['code'] = dict(plan.data['implementation']['code'])
        report['runtime'] = legacy.runtime_identity()
        locked_sources(plan,deadline)
        con = legacy.connection_for(source,output)
        timer = deadline.interrupt_sql(con)
        report['id_checks'] = reserved_tables(con,plan,deadline)
        create_reserved_candidates(con,expected_users=plan.data['cohort']['users'])
        deadline.check()
        from scripts.hm_feature_engine import build_features
        built = build_features(con,ANCHOR,candidates_table='hm_candidates')
        report['features'] = legacy.feature_contract(built)
        train_manifest = read_json(checkout_path(plan.data['train_collections'][0]['manifest']['path']))
        require(report['features']==train_manifest['features'],'Frozen train/holdout feature contracts differ')
        con.register('_hm_holdout_feature_frame',built.frame)
        deadline.check()
        attach_outcomes(con)
        for table,filename in [('hm_exp_frame','frame.parquet'),('hm_exp_targets','targets.parquet')]:
            con.sql(f'SELECT * FROM {table} ORDER BY customer_id,article_id').write_parquet(str(output/filename))
        con.sql('''SELECT q.customer_id,q.cohort_hash,q.reservation_rank,count(c.article_id)::INTEGER full_candidate_count
            FROM hm_holdout_reserved q LEFT JOIN hm_candidates c USING(customer_id)
            GROUP BY q.customer_id,q.cohort_hash,q.reservation_rank ORDER BY q.reservation_rank''').write_parquet(str(output/'users.parquet'))
        rows,positives = con.execute('SELECT count(*),count(*) FILTER(WHERE label) FROM hm_exp_frame').fetchone()
        n = plan.data['cohort']['users']
        require(rows==120*n,'Every reserved query must have120 full candidate rows')
        report['population'] = dict(candidate_rows=rows,positive_rows=positives,selected_queries=n,
            target_pairs=con.execute('SELECT count(*) FROM hm_exp_targets').fetchone()[0])
        report['files'] = {name:legacy.sha256_file(output/name,deadline) for name in
                           ('frame.parquet','users.parquet','targets.parquet')}
        report['qcy_identity'] = legacy.canonical_digest({name:report['files'][name] for name in ('users.parquet','targets.parquet')})
        report['candidate_identity'] = legacy.candidate_digest(con,deadline)
        report['construction_order'] = ['authorize_lock','reserved_Q_disjoint_history','C0-Q120','feature_engine','fullY','labels']
        after = source.stat()
        require((before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'Database changed during collection')
        context_fresh(plan,deadline)
        deadline.check()
        report['status'] = 'completed'
    except Exception as error:
        report.update(status='failed',error=dict(type=type(error).__name__,message=str(error)[:2048],
            traceback=traceback.format_exc(limit=12)[-8192:]))
        raise
    finally:
        stop_sql(timer,con)
        report['elapsed_seconds'] = round(time.monotonic()-deadline.started,3)
        legacy.write_json(output/'manifest.json',report)
    return report


def read_holdout_manifest(collection,plan,deadline):
    collection = Path(collection).resolve()
    manifest = read_json(collection/'manifest.json')
    require(manifest.get('format')==COLLECTION_FORMAT and manifest.get('status')=='completed'
            and manifest.get('holdout_lock_sha256')==plan.sha256,'Completed locked custom-cohort collection required')
    require('cohort_seed' not in manifest and manifest['cohort']==plan.data['cohort']
            and manifest['anchor']==ANCHOR and manifest['horizon_days']==7 and manifest['policy']=='C0-Q120'
            and manifest['requested_users']==plan.data['cohort']['users'],'Custom cohort contract differs')
    reservation = plan.data['reservation']
    require(manifest['reservation_manifest_sha256']==reservation['manifest']['sha256']
            and manifest['reserved_ordered_ids_sha256']==reservation['reserved_ordered_ids_sha256']
            and manifest['excluded_ordered_ids_sha256']==reservation['excluded_ordered_ids_sha256']
            and manifest['id_checks']==dict(reserved_users=plan.data['cohort']['users'],excluded_overlap_users=0,training_overlap_users=0),
            'Custom cohort reservation provenance differs')
    require(manifest['database']=={key:plan.data['database'][key] for key in ('sha256','bytes')}
            and manifest['code']==plan.data['implementation']['code']
            and manifest['runtime']==plan.data['implementation']['runtime'],'Collection source/runtime/database differs')
    for name in ('frame.parquet','users.parquet','targets.parquet'):
        require(legacy.sha256_file(collection/name,deadline)==manifest['files'][name],'Customer-test cache bytes changed')
    require(manifest['qcy_identity']==legacy.canonical_digest({name:manifest['files'][name] for name in ('users.parquet','targets.parquet')}),
            'Customer-test Q/Y identity differs')
    return manifest


def load_holdout(con,collection,manifest,names,plan,deadline):
    """Full-C/full-Y adapter with explicit reserved Q; never nested_users2026."""
    import numpy as np
    collection = Path(collection)
    id_checks = reserved_tables(con,plan,deadline)
    require(id_checks==manifest['id_checks'],'Custom cohort ID checks differ')
    users = con.execute('SELECT * FROM read_parquet(?) ORDER BY reservation_rank',[str(collection/'users.parquet')]).fetchdf()
    expected = con.execute('SELECT * FROM hm_holdout_reserved ORDER BY reservation_rank').fetchdf()
    require(len(users)==len(expected) and list(users['customer_id'])==list(expected['customer_id'])
            and list(users['cohort_hash'])==list(expected['cohort_hash'])
            and list(users['reservation_rank'])==list(expected['reservation_rank'])
            and users['full_candidate_count'].notna().all() and (users['full_candidate_count']==120).all(),
            'Cached explicit reserved Q differs')
    projection = ','.join('f.'+legacy.quote(name) for name in names)
    frame = con.execute(f'''SELECT f.customer_id,f.article_id,f.label,f.query_weight,f.full_candidate_count,{projection}
        FROM read_parquet(?) f ORDER BY f.customer_id,f.article_id''',[str(collection/'frame.parquet')]).fetchdf()
    require(set(frame['customer_id'])==set(expected['customer_id']) and len(frame)==120*len(expected),
            'Full cached candidate frame must represent exactly reserved Q')
    require((frame.groupby('customer_id').size()==120).all(),'Each reserved query requires120 candidates')
    frame = legacy.sample_training_rows(frame,ANCHOR,0)
    targets = {user:set() for user in expected['customer_id']}
    rows = con.execute('SELECT customer_id,article_id FROM read_parquet(?) ORDER BY customer_id,article_id',
                       [str(collection/'targets.parquet')]).fetchall()
    require(len(rows)==len(set(rows)),'Full target pairs must be unique')
    for user,article in rows:
        require(user in targets and isinstance(article,str),'Targets must belong to reserved Q and preserve string IDs')
        targets[user].add(article)
    require(frame['label'].dtype.kind=='b' and np.array_equal(frame['label'].to_numpy(),
        np.fromiter((article in targets[user] for user,article in zip(frame['customer_id'],frame['article_id'])),dtype=bool)),
        'Cached labels differ from full distinct targets')
    summary = dict(anchor=ANCHOR,selected_queries=len(expected),full_candidate_rows=len(frame),fit_rows=len(frame),
        positive_rows=int(frame['label'].sum()),target_pairs=sum(map(len,targets.values())),
        positive_queries=sum(bool(value) for value in targets.values()),min_inclusion_probability=1.,
        weighted_positive_mass=float(frame.loc[frame['label'],'fit_weight'].sum()),
        weighted_negative_mass=float(frame.loc[~frame['label'],'fit_weight'].sum()))
    require(manifest['population']==dict(candidate_rows=len(frame),positive_rows=summary['positive_rows'],
        selected_queries=len(expected),target_pairs=summary['target_pairs']),'Collection population differs from rows')
    con.execute('CREATE TEMP TABLE hm_candidates AS SELECT customer_id,article_id FROM read_parquet(?)',
                [str(collection/'frame.parquet')])
    require(legacy.candidate_digest(con,deadline)==manifest['candidate_identity'],'Candidate key identity differs')
    return frame,targets,summary


def model_class():
    from catboost import CatBoostClassifier
    return CatBoostClassifier


def fit_identity(report):
    return legacy.canonical_digest(dict(inputs=report['inputs'],features=report['features'],
        hyperparameters=report['hyperparameters'],train_users=report['training_user_limit'],
        negative_sample=report['negative_sample'],sampling_seed=report['sampling_seed'],
        code=report['code'],runtime=report['runtime'],holdout_lock_sha256=report['holdout_lock_sha256'],
        holdout_arm=report['holdout_arm'],reservation_manifest_sha256=report['reservation_manifest_sha256'],cohort=report['cohort']))


def fit(arm,seed,train_paths,collection,output,decision_lock,expected_lock_sha256,
        wall_seconds=1800,external_job_timeout_seconds=1860):
    deadline = deadline_for(wall_seconds)
    require(type(external_job_timeout_seconds) in (int,float) and external_job_timeout_seconds==1860,
            'Caller must declare the fixed external1860-second owned Job')
    gate = gate_module()
    plan = gate.load_lock(decision_lock,expected_lock_sha256)
    train_paths = [Path(path).resolve() for path in train_paths]
    collection = Path(collection).resolve()
    authorized = gate.authorize_fit(plan,arm,seed,train_paths,collection,Path(output))
    deadline.check()
    # No cache, reserved IDs, labels, Pool or model is opened before authorization.
    manifest = read_holdout_manifest(collection,plan,deadline)
    manifests = []
    for path,item in zip(train_paths,plan.data['train_collections']):
        require(path==checkout_path(item['manifest']['path']).parent
                and legacy.sha256_file(path/'manifest.json',deadline)==item['manifest']['sha256'],
                'Locked training path/manifest differs')
        current = legacy.read_manifest(path,deadline)
        require(current['anchor']==item['anchor'] and current['features']==manifest['features']
                and current['policy']==manifest['policy'] and current['database']==manifest['database'],
                'Training/holdout feature or data contract differs')
        manifests.append(current)
    require(len(train_paths)==len(manifests)==len(plan.data['train_collections'])==5,'Exactly five locked training collections required')
    features = authorized['features']
    numeric,categorical = legacy.choose_features(manifest,feature_names=features['numeric']+features['categorical'])
    require(features==dict(numeric=numeric,categorical=categorical),'Locked ordered model feature vector differs')
    training_rule = plan.data['training']
    output = new_output(output)
    report = dict(format=FIT_FORMAT,status='running',fit_count=0,holdout_lock_sha256=plan.sha256,holdout_arm=arm,
        reservation_manifest_sha256=plan.data['reservation']['manifest']['sha256'],cohort=plan.data['cohort'],
        selection='Frozen v2 customer test; no selection, validation Pool or early stopping',
        training_user_limit=training_rule['train_users'],negative_sample=training_rule['negative_sample'],
        sampling_seed=training_rule['sampling_seed'],fit_index=authorized['fit_index'])
    con = timer = None
    try:
        report['resources'] = legacy.resource_preflight(output)
        report['resources'].update(external_job_timeout_seconds=1860,prediction_task_type='CPU',
            native_training_deadline='Caller-owned external Job required; this declaration is not enforcement',gpu_training_nondeterministic=True)
        report['code'] = dict(plan.data['implementation']['code'])
        report['runtime'] = legacy.runtime_identity()
        report['features'] = dict(features,contract_digest=manifest['features']['digest'])
        report['hyperparameters'] = dict(authorized['hyperparameters'])
        report['inputs'] = [dict(anchor=value['anchor'],manifest_sha256=legacy.sha256_file(path/'manifest.json',deadline),
            qcy_identity=value['qcy_identity'],candidate_identity=value['candidate_identity'])
            for path,value in zip(train_paths+[collection],manifests+[manifest])]
        report['fit_identity'] = fit_identity(report)
        locked_sources(plan,deadline)
        import duckdb
        import numpy as np
        con = duckdb.connect(':memory:')
        con.execute('SET threads=4');con.execute("SET memory_limit='2GB'")
        spill = output/'duckdb-temp';spill.mkdir()
        con.execute('SET temp_directory=?',[str(spill)]);con.execute("SET max_temp_directory_size='8GB'")
        timer = deadline.interrupt_sql(con)
        # Check every training user's disjointness before supervised cache loading.
        reserved_tables(con,plan,deadline)
        training = []
        names = numeric+categorical
        report['training_populations'] = []
        for path,current in zip(train_paths,manifests):
            deadline.check()
            frame,_,summary = load_part(con,path,current,names,training_rule['train_users'],training_rule['negative_sample'])
            reserved_overlap = set(frame['customer_id']).intersection(
                user[0] for user in con.execute('SELECT customer_id FROM hm_holdout_reserved').fetchall())
            require(not reserved_overlap,'Supervised training frame overlaps reserved customers')
            numbers,cats = model_arrays(frame,numeric,categorical)
            training.append((numbers,cats,frame['label'].to_numpy(dtype=np.int8),frame['fit_weight'].to_numpy(dtype=np.float64)))
            report['training_populations'].append(summary)
            del frame
        numbers=np.concatenate([part[0] for part in training]);cats=np.concatenate([part[1] for part in training])
        labels=np.concatenate([part[2] for part in training]);weights=np.concatenate([part[3] for part in training])
        del training
        require(len(np.unique(labels))==2,'Training needs both naturally retrieved label classes')
        pool = model_pool(numbers,cats,numeric,categorical,labels,weights)
        model = model_class()(**report['hyperparameters'])
        deadline.check();report['fit_count']=1
        model.fit(pool)
        report['actual_trees'] = model.tree_count_
        require(model.tree_count_==500,'Frozen GPU fit must complete500 trees')
        resolved = model.get_all_params();report['resolved_model_parameters']=resolved
        for key in ('task_type','iterations','depth','l2_leaf_reg','random_seed','bootstrap_type','border_count','boosting_type'):
            require(resolved.get(key)==report['hyperparameters'][key],'Resolved GPU recipe differs')
        report['last_training_iteration']=model.tree_count_
        deadline.check();model.save_model(str(output/'model.cbm'))
        del pool,numbers,cats,labels,weights
        # The fit used prior reserved TEMP tables; validation starts a fresh
        # namespace to make full-Q validation independent of training selection.
        for table in ('hm_holdout_reserved','hm_holdout_excluded','hm_holdout_old_q'):
            con.execute(f'DROP TABLE IF EXISTS temp.{table}')
        frame,targets,summary = load_holdout(con,collection,manifest,names,plan,deadline)
        numbers,cats = model_arrays(frame,numeric,categorical)
        validation = legacy.pilot.Collection(numbers,cats,frame['label'].to_numpy(),frame['query_weight'].to_numpy(),
            frame['customer_id'].to_numpy(),frame['article_id'].to_numpy(),targets,summary)
        deadline.check()
        scores = model.predict_proba(model_pool(numbers,cats,numeric,categorical),thread_count=4)[:,1]
        require(np.isfinite(scores).all(),'Prediction scores must be finite')
        report['validation_population']=summary
        report['validation_metrics']=legacy.pilot.rank_collection(validation,scores=scores)
        legacy.write_private_predictions(con,output,validation,scores)
        report['files']={name:legacy.sha256_file(output/name,deadline) for name in
                         ('model.cbm','query-metrics.parquet','predictions-top12.parquet')}
        require(read_holdout_manifest(collection,plan,deadline)==manifest,'Customer-test manifest changed during fit')
        context_fresh(plan,deadline);deadline.check();report['status']='completed'
    except Exception as error:
        report.update(status='failed',error=dict(type=type(error).__name__,message=str(error)[:2048],
            traceback=traceback.format_exc(limit=12)[-8192:]))
        raise
    finally:
        stop_sql(timer,con)
        report['elapsed_seconds']=round(time.monotonic()-deadline.started,3)
        legacy.write_json(output/'report.json',report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    command=sub.add_parser('collect')
    command.add_argument('--database',type=Path,required=True)
    command=sub.add_parser('fit')
    command.add_argument('--arm',choices=('M','E'),required=True)
    command.add_argument('--seed',type=int,choices=(2026,2027),required=True)
    command.add_argument('--train',type=Path,nargs='+',required=True)
    command.add_argument('--collection',type=Path,required=True)
    command.add_argument('--external-job-timeout-seconds',type=float,default=1860)
    for command in sub.choices.values():
        command.add_argument('--decision-lock',type=Path,required=True)
        command.add_argument('--expected-lock-sha256',required=True)
        command.add_argument('--output',type=Path,required=True)
        command.add_argument('--wall-seconds',type=float,default=1800)
    args=parser.parse_args(argv)
    try:
        if args.command=='collect':
            result=collect(args.database,args.output,args.decision_lock,args.expected_lock_sha256,args.wall_seconds)
        else:
            result=fit(args.arm,args.seed,args.train,args.collection,args.output,args.decision_lock,
                args.expected_lock_sha256,args.wall_seconds,args.external_job_timeout_seconds)
    except Exception as error:
        print(json.dumps(dict(status='failed',error_type=type(error).__name__,message=str(error)[:2048])))
        return 1
    print(json.dumps(dict(status=result['status'],output=args.output.resolve().as_posix())))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
