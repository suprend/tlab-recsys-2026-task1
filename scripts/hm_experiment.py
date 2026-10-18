"""Reusable bounded development collection and single-fit runner for H&M.

Reserved final dates require an explicit immutable decision lock. All row-level
outputs are restricted to this checkout's ignored artifacts/ tree.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import shutil
import sys
import threading
import time
import traceback

from scripts import hm_baseline as pilot

ROOT = Path(__file__).resolve().parents[1]
LAST_ANCHOR = date(2020, 9, 9)
SEED = 2026
POLICIES = ('C0-Q120', 'C1-Q120')
RESERVED = {'customer_id', 'article_id', 'label', 'query_weight', 'full_candidate_count', 'anchor'}


class Deadline:
    def __init__(self, seconds):
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('A finite positive wall limit is required')
        self.started = time.monotonic()
        self.expires = self.started + seconds

    def check(self):
        if time.monotonic() >= self.expires:
            raise TimeoutError('Declared wall limit exceeded')

    def interrupt_sql(self, connection):
        timer = threading.Timer(max(0, self.expires-time.monotonic()), connection.interrupt)
        timer.daemon = True
        timer.start()
        return timer


def sha256_file(path, deadline=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            if deadline:
                deadline.check()
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def candidate_digest(connection, deadline):
    """Hash ordered keys in bounded batches, without a giant string_agg value."""
    digest=hashlib.sha256()
    cursor=connection.execute('SELECT customer_id,article_id FROM hm_candidates ORDER BY customer_id,article_id')
    while block:=cursor.fetchmany(8192):
        deadline.check()
        for row in block:
            for value in row:
                encoded=value.encode('utf-8')
                digest.update(len(encoded).to_bytes(4,'big'))
                digest.update(encoded)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n',
                          encoding='utf-8', newline='\n')


def new_private_output(output):
    path = Path(output).resolve()
    allowed = (ROOT/'artifacts').resolve()
    if path == allowed or not path.is_relative_to(allowed):
        raise ValueError('Row-level outputs must be a new directory inside checkout artifacts/')
    path.mkdir(parents=True, exist_ok=False)
    return path


def check_anchor(anchor):
    cutoff = date.fromisoformat(anchor) if isinstance(anchor, str) else anchor
    if cutoff > LAST_ANCHOR:
        raise ValueError('Development runner rejects anchors after 2020-09-09')
    return cutoff


def connection_for(database, output):
    import duckdb
    con = duckdb.connect(str(Path(database).resolve()), read_only=True)
    con.execute('SET threads=4')
    con.execute("SET memory_limit='2GB'")
    con.execute('SET preserve_insertion_order=false')
    temp = output/'duckdb-temp'
    temp.mkdir()
    con.execute('SET temp_directory=?', [str(temp)])
    con.execute("SET max_temp_directory_size='8GB'")
    return con


def resource_preflight(output):
    free=shutil.disk_usage(output).free
    if free<10*1024**3:
        raise OSError('Output filesystem requires at least10GiB free for bounded spill')
    return dict(output_disk_free_bytes=free,min_free_bytes=10*1024**3,
                max_temp_directory_size='8GB',duckdb_memory_limit='2GB',threads=4)


def runtime_identity():
    return dict(python=platform.python_version(), platform=platform.platform(),
                packages={name:importlib.metadata.version(name) for name in
                          ('duckdb', 'numpy', 'pandas', 'catboost')},
                threads=4, duckdb_memory_limit='2GB')


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def feature_contract(result):
    """Validate the feature engine manifest before attaching any outcomes."""
    registry = result.registry
    if isinstance(registry, dict):
        registry = [dict(value, name=name) for name, value in registry.items()]
    if isinstance(registry, tuple):
        registry=list(registry)
    if not isinstance(registry, list) or not registry:
        raise ValueError('Feature registry must be a nonempty list/dictionary')
    specs = {}
    for entry in registry:
        if is_dataclass(entry):
            entry=asdict(entry)
        name = entry['name']
        kind = entry.get('kind', entry.get('dtype'))
        if kind in ('float', 'float32', 'float64', 'integer', 'int', 'number'):
            kind = 'numeric'
        if kind in ('string', 'varchar', 'category'):
            kind = 'categorical'
        if name in specs or name in RESERVED or kind not in ('numeric', 'categorical'):
            raise ValueError('Invalid feature registry name/kind')
        specs[name] = dict(entry, kind=kind)
    sets = result.feature_sets
    if not isinstance(sets, dict):
        raise ValueError('Feature sets must be a dictionary of name lists')
    sets={key:list(names) for key,names in sets.items()}
    for names in sets.values():
        if len(set(names)) != len(names) or not set(names) <= set(specs):
            raise ValueError('Feature set is missing unique registered names')
    if not set(specs) <= set(result.frame.columns) or not {'customer_id', 'article_id'} <= set(result.frame.columns):
        raise ValueError('Feature frame does not match registry')
    if RESERVED.intersection(set(result.frame.columns)-{'customer_id', 'article_id'}):
        raise ValueError('Outcome/weight/anchor columns must not enter feature engine output')
    return {'registry': list(specs.values()), 'feature_sets': sets, 'digest': result.digest}


def collect(database, output, anchor, users, policy, wall_seconds=1800, decision_lock=None):
    final_lock = None
    if decision_lock is None:
        cutoff = check_anchor(anchor)
    else:
        from scripts import hm_final_lock as gate
        from scripts.hm_feature_engine import feature_manifest
        final_lock = gate.load_lock(decision_lock)
        source = Path(database).resolve()
        gate.authorize_collect(final_lock, dict(output=private_relative(output), anchor=str(anchor),
            users=users, policy=policy, cohort_seed=SEED, horizon_days=7),
            dict(sha256=sha256_file(source), bytes=source.stat().st_size), feature_manifest()['digest'])
        cutoff = date.fromisoformat(str(anchor))
    if users < 1 or policy not in POLICIES:
        raise ValueError('Positive user count and supported policy required')
    deadline = Deadline(wall_seconds)
    output = new_private_output(output)
    report = dict(format='hm-experiment-collection-v1', status='running', anchor=cutoff.isoformat(),
                  policy=policy, requested_users=users, cohort_seed=SEED, horizon_days=7,
                  history='[anchor-90d,anchor)', target='[anchor,anchor+7d)',
                  private_data='All parquet files contain real IDs; ignored artifacts only.')
    if final_lock is not None:
        report['final_lock_sha256'] = final_lock.sha256
    con = timer = None
    try:
        report['resources']=resource_preflight(output)
        from scripts.hm_retrieval import create_candidates
        from scripts.hm_feature_engine import build_features
        source = Path(database).resolve()
        stat = source.stat()
        report['database'] = dict(sha256=sha256_file(source, deadline), bytes=stat.st_size)
        if final_lock is not None and report['database'] != final_lock.data['database']:
            raise ValueError('Final database changed since lock authorization')
        report['runtime'] = runtime_identity()
        report['code'] = {p.name:sha256_file(p, deadline) for p in (
            Path(__file__), ROOT/'scripts/hm_retrieval.py', ROOT/'scripts/hm_feature_engine.py',
            ROOT/'scripts/hm_baseline.py')}
        con = connection_for(source, output)
        timer = deadline.interrupt_sql(con)
        create_candidates(con, cutoff, users, SEED)
        con.execute('''CREATE TEMP TABLE hm_candidates AS SELECT customer_id,article_id,
            source,source_rank,candidate_rank FROM hm_r_candidates WHERE policy=?''', [policy])
        deadline.check()
        built = build_features(con, cutoff.isoformat(), candidates_table='hm_candidates')
        report['features'] = feature_contract(built)
        con.register('_hm_feature_frame', built.frame)
        bad = con.execute('''SELECT count(*) FROM (
            (SELECT customer_id,article_id FROM hm_candidates EXCEPT SELECT customer_id,article_id FROM _hm_feature_frame)
            UNION ALL
            (SELECT customer_id,article_id FROM _hm_feature_frame EXCEPT SELECT customer_id,article_id FROM hm_candidates))''').fetchone()[0]
        duplicate = con.execute('''SELECT count(*) FROM (SELECT customer_id,article_id,count(*) n
            FROM _hm_feature_frame GROUP BY customer_id,article_id HAVING n<>1)''').fetchone()[0]
        if bad or duplicate:
            raise ValueError('Feature frame must preserve exact unique candidate keys')
        # Full future truth is first accessed after construction of cohort/candidates/features.
        con.execute('''CREATE TEMP TABLE hm_exp_targets AS SELECT DISTINCT t.customer_id,t.article_id
            FROM transactions t JOIN hm_r_users u USING(customer_id)
            WHERE t.t_dat>=?::DATE AND t.t_dat<?::DATE+INTERVAL '7 days' ''',
                    [cutoff.isoformat(),cutoff.isoformat()])
        con.execute('''CREATE TEMP TABLE hm_exp_frame AS SELECT f.*,
            (t.article_id IS NOT NULL)::BOOLEAN AS label,
            count(*) OVER(PARTITION BY f.customer_id)::INTEGER AS full_candidate_count,
            1.0/count(*) OVER(PARTITION BY f.customer_id) AS query_weight
            FROM _hm_feature_frame f LEFT JOIN hm_exp_targets t USING(customer_id,article_id)''')
        queries = con.execute('SELECT count(*) FROM hm_r_users').fetchone()[0]
        represented = con.execute('SELECT count(DISTINCT customer_id) FROM hm_exp_frame').fetchone()[0]
        if represented != queries or queries == 0:
            raise ValueError('Every history-selected query must have candidate rows')
        for table, filename in [('hm_exp_frame','frame.parquet'),('hm_exp_targets','targets.parquet')]:
            con.sql(f'SELECT * FROM {table} ORDER BY customer_id,article_id').write_parquet(str(output/filename))
        con.sql('''SELECT u.customer_id,sha256(u.customer_id || ':2026') AS cohort_hash,
            count(c.article_id)::INTEGER AS full_candidate_count
            FROM hm_r_users u LEFT JOIN hm_candidates c USING(customer_id)
            GROUP BY u.customer_id ORDER BY cohort_hash,u.customer_id''').write_parquet(str(output/'users.parquet'))
        names = [d[0] for d in con.execute('SELECT count(*) candidate_rows,count(*) FILTER(WHERE label) positive_rows FROM hm_exp_frame').description]
        values = con.fetchone()
        report['population'] = dict(zip(names, values), selected_queries=queries,
                                    target_pairs=con.execute('SELECT count(*) FROM hm_exp_targets').fetchone()[0])
        report['files'] = {name:sha256_file(output/name, deadline) for name in
                           ('frame.parquet','users.parquet','targets.parquet')}
        # These hashes establish identical Q/C/Y across all arms reusing this cache.
        report['qcy_identity'] = canonical_digest({k:report['files'][k] for k in ('users.parquet','targets.parquet')})
        report['candidate_identity'] = candidate_digest(con,deadline)
        after = source.stat()
        if (stat.st_size,stat.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise ValueError('Source database changed during collection')
        deadline.check()
        report['status'] = 'completed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = dict(type=type(exc).__name__, message=str(exc)[:2048],
                               traceback=traceback.format_exc(limit=12)[-8192:])
        raise
    finally:
        if timer:
            timer.cancel()
        if con:
            con.close()
        report['elapsed_seconds'] = round(time.monotonic()-deadline.started,3)
        write_json(output/'manifest.json', report)
    return report


def nested_users(users_frame, limit=None):
    """Use the same history-only SHA256 ordering as original retrieval."""
    if users_frame['customer_id'].duplicated().any():
        raise ValueError('Duplicate query in users cache')
    expected = users_frame['customer_id'].map(lambda u:pilot.cohort_key(u,SEED))
    if not (users_frame['cohort_hash']==expected).all():
        raise ValueError('Cached cohort ordering does not match seed2026')
    if limit is not None and limit<1:
        raise ValueError('Training user limit must be positive')
    ordered=users_frame.sort_values(['cohort_hash','customer_id'])
    if limit is not None and limit>len(ordered):
        raise ValueError('Requested training cohort exceeds cached query population')
    return ordered if limit is None else ordered.head(limit)


def sample_training_rows(frame, anchor, negative_sample=0):
    """Uniform hash-ranked negatives; inverse inclusion weights retain full-C loss.

    The seed is fixed independently of model seed. Positive rows and every query
    survive. No missing target is injected. Full candidate denominator is cached
    before sampling and is never recomputed from this smaller frame.
    """
    import numpy as np
    if negative_sample not in (0,20):
        raise ValueError('Negative sample must be 0 (full) or 20')
    if frame.empty or frame.duplicated(['customer_id','article_id']).any():
        raise ValueError('Training keys must be nonempty and unique')
    counts=frame.groupby('customer_id')['article_id'].transform('count').to_numpy()
    original=frame['full_candidate_count'].to_numpy()
    if not np.array_equal(counts,original) or not np.allclose(frame['query_weight'],1.0/original,rtol=1e-12,atol=0):
        raise ValueError('Full candidate rows/weights must be intact before sampling')
    output=frame.copy()
    output['inclusion_probability']=1.0
    if negative_sample:
        neg=output.loc[~output['label'].astype(bool),['customer_id','article_id']].copy()
        neg['_hash']=[hashlib.sha256(f'{anchor}|{u}|{a}|{SEED}'.encode()).hexdigest()
                      for u,a in zip(neg['customer_id'],neg['article_id'])]
        neg=neg.sort_values(['customer_id','_hash','article_id'])
        nneg=neg.groupby('customer_id')['article_id'].transform('count')
        neg['_pi']=np.minimum(negative_sample,nneg)/nneg
        kept=neg.groupby('customer_id',sort=False).head(negative_sample)
        mask=output['label'].astype(bool) | output.index.isin(kept.index)
        output=output.loc[mask].copy()
        output.loc[kept.index,'inclusion_probability']=kept['_pi']
    output['fit_weight']=output['query_weight']/output['inclusion_probability']
    if set(output['customer_id'])!=set(frame['customer_id']) or int(output['label'].sum())!=int(frame['label'].sum()):
        raise RuntimeError('Sampling lost a query/positive')
    return output.sort_values(['customer_id','article_id']).reset_index(drop=True)


def read_manifest(path, deadline, final_lock=None):
    path=Path(path).resolve()
    manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format')!='hm-experiment-collection-v1' or manifest.get('status')!='completed':
        raise ValueError('Completed collection manifest required')
    if final_lock is None or manifest['anchor'] <= LAST_ANCHOR.isoformat():
        check_anchor(manifest['anchor'])
    elif (manifest['anchor'] != '2020-09-16' or
          path != (ROOT/final_lock.data['outputs']['collection']).resolve() or
          manifest.get('final_lock_sha256') != final_lock.sha256):
        raise ValueError('Final evaluation manifest differs from validated decision lock')
    if manifest.get('cohort_seed')!=SEED or manifest.get('policy') not in POLICIES:
        raise ValueError('Collection policy/cohort mismatch')
    for name in ('frame.parquet','users.parquet','targets.parquet'):
        if manifest['files'].get(name)!=sha256_file(path/name,deadline):
            raise ValueError('Collection byte identity changed')
    return manifest


def choose_features(manifest, feature_set='pilot', feature_names=None):
    contract=manifest['features']
    specs={s['name']:s for s in contract['registry']}
    alias={'pilot':'manual_pilot','strong':'strong_manual'}
    names=list(feature_names) if feature_names is not None else list(contract['feature_sets'][alias[feature_set]])
    if not names or len(set(names))!=len(names) or not set(names)<=set(specs) or set(names)&RESERVED:
        raise ValueError('Unique registered feature names required')
    numeric=[n for n in names if specs[n]['kind']=='numeric']
    categorical=[n for n in names if specs[n]['kind']=='categorical']
    return numeric,categorical


def load_part(con, path, manifest, names, train_users=None, negative_sample=None):
    import numpy as np
    users=con.execute('SELECT * FROM read_parquet(?)',[str(path/'users.parquet')]).fetchdf()
    selected=nested_users(users,train_users)
    con.register('_hm_selected_users',selected[['customer_id']])
    keys=con.execute('''SELECT f.customer_id,f.article_id,f.label,f.query_weight,f.full_candidate_count
        FROM read_parquet(?) f JOIN _hm_selected_users u USING(customer_id)
        ORDER BY f.customer_id,f.article_id''',[str(path/'frame.parquet')]).fetchdf()
    if set(keys['customer_id'])!=set(selected['customer_id']):
        raise ValueError('Cached candidate rows do not represent every query')
    if negative_sample is not None:
        kept=sample_training_rows(keys,manifest['anchor'],negative_sample)
    else:
        kept=sample_training_rows(keys,manifest['anchor'],0)
    con.register('_hm_kept',kept[['customer_id','article_id','fit_weight','inclusion_probability']])
    projection=','.join('f.'+quote(n) for n in names)
    frame=con.execute(f'''SELECT f.customer_id,f.article_id,f.label,f.query_weight,f.full_candidate_count,
        s.fit_weight,s.inclusion_probability,{projection} FROM read_parquet(?) f
        JOIN _hm_kept s USING(customer_id,article_id) ORDER BY f.customer_id,f.article_id''',
                      [str(path/'frame.parquet')]).fetchdf()
    targets={u:set() for u in selected['customer_id']}
    for u,a in con.execute('''SELECT t.customer_id,t.article_id FROM read_parquet(?) t
        JOIN _hm_selected_users u USING(customer_id) ORDER BY t.customer_id,t.article_id''',
                           [str(path/'targets.parquet')]).fetchall():
        targets[u].add(a)
    if frame['label'].dtype.kind!='b' or not np.array_equal(frame['label'].to_numpy(),
            np.fromiter((a in targets[u] for u,a in zip(frame['customer_id'],frame['article_id'])),dtype=bool)):
        raise ValueError('Cached labels are inconsistent with complete targets')
    summary=dict(anchor=manifest['anchor'],selected_queries=len(selected),full_candidate_rows=len(keys),
                 fit_rows=len(frame),positive_rows=int(frame['label'].sum()),
                 target_pairs=sum(map(len,targets.values())),positive_queries=sum(bool(v) for v in targets.values()),
                 min_inclusion_probability=float(frame['inclusion_probability'].min()),
                 weighted_positive_mass=float(frame.loc[frame['label'],'fit_weight'].sum()),
                 weighted_negative_mass=float(frame.loc[~frame['label'],'fit_weight'].sum()))
    return frame,targets,summary


def model_arrays(frame,numeric,categorical):
    import numpy as np
    numbers=np.ascontiguousarray(frame[numeric].to_numpy(dtype=np.float32))
    if not np.isfinite(numbers).all():
        raise ValueError('Model numeric features must be finite')
    cats=frame[categorical].fillna('__MISSING__').astype(str).to_numpy(dtype=object)
    return numbers,cats


def model_pool(numeric_data,cat_data,numeric_names,cat_names,labels=None,weights=None):
    from catboost import FeaturesData,Pool
    # FeaturesData requires absent blocks to be None (rather than zero-column arrays).
    features=FeaturesData(num_feature_data=numeric_data if numeric_names else None,
                          cat_feature_data=cat_data if cat_names else None,
                          num_feature_names=numeric_names if numeric_names else None,
                          cat_feature_names=cat_names if cat_names else None)
    return Pool(features,label=labels,weight=weights)


def write_private_predictions(con,output,collection,scores):
    import numpy as np
    import pandas as pd
    order=np.lexsort((collection.articles,-scores,collection.users))
    predictions={u:[] for u in collection.targets}
    candidates={u:set() for u in collection.targets}
    top_rows=[]
    for i in order:
        u,a=collection.users[i],collection.articles[i]
        candidates[u].add(a)
        if len(predictions[u])<12:
            predictions[u].append(a)
            top_rows.append((u,a,len(predictions[u]),float(scores[i])))
    metrics=[]
    for u,truth in collection.targets.items():
        hit=len(set(predictions[u])&truth)
        covered=len(candidates[u]&truth)
        metrics.append((u,len(truth),len(candidates[u]),hit,covered,
                        pilot.average_precision(predictions[u],truth),hit/len(truth) if truth else 0.0,
                        min(covered,12)/min(len(truth),12) if truth else 0.0))
    frames={'predictions-top12.parquet':pd.DataFrame(top_rows,columns=['customer_id','article_id','rank','score']),
            'query-metrics.parquet':pd.DataFrame(metrics,columns=['customer_id','targets','candidate_count','hits12',
                                                                  'covered','ap12','recall12','oracle_ap12'])}
    for filename,frame in frames.items():
        con.register('_hm_private_export',frame)
        con.sql('SELECT * FROM _hm_private_export ORDER BY customer_id').write_parquet(str(output/filename))


def private_relative(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def fixed_parameters(iterations, depth, seed):
    return dict(iterations=iterations, depth=depth, learning_rate=0.05, l2_leaf_reg=10,
                loss_function='Logloss', random_seed=seed, thread_count=4, task_type='CPU',
                verbose=False, allow_writing_files=False)


def fit(train_paths,validation_path,output,feature_set='pilot',feature_names=None,
        iterations=150,depth=6,seed=SEED,train_users=None,negative_sample=0,wall_seconds=1800,decision_lock=None):
    if not train_paths or len(set(map(str,train_paths)))!=len(train_paths):
        raise ValueError('Distinct training collection paths required')
    if iterations<1 or not 1<=depth<=12 or negative_sample not in (0,20):
        raise ValueError('Invalid fixed-fit parameters')
    deadline=Deadline(wall_seconds)
    final_lock = final_arm = None
    if decision_lock is not None:
        from scripts import hm_final_lock as gate
        final_lock = gate.load_lock(decision_lock)
        train_paths = [Path(p).resolve() for p in train_paths]
        validation_path = Path(validation_path).resolve()
        # Training caches always use the development guard, even with a lock.
        train_manifests = [read_manifest(p, deadline) for p in train_paths]
        validation_manifest = read_manifest(validation_path, deadline, final_lock)
        numeric, categorical = choose_features(validation_manifest, feature_set, feature_names)
        train_inputs = [dict(anchor=m['anchor'], manifest_sha256=sha256_file(p/'manifest.json', deadline),
            qcy_identity=m['qcy_identity'], candidate_identity=m['candidate_identity'])
            for p, m in zip(train_paths, train_manifests)]
        final_arm = gate.authorize_fit(final_lock, dict(output=private_relative(output),
            validation=private_relative(validation_path), numeric=numeric, categorical=categorical,
            hyperparameters=fixed_parameters(iterations, depth, seed), train_users=train_users,
            negative_sample=negative_sample, sampling_seed=SEED), train_inputs, validation_path/'manifest.json')
    output=new_private_output(output)
    report=dict(format='hm-experiment-fit-v1',status='running',fit_count=0,
                selection='One fixed-tree fit; no eval_set, early stopping or parameter search',
                training_user_limit=train_users,negative_sample=negative_sample,sampling_seed=SEED)
    if final_lock is not None:
        report.update(final_lock_sha256=final_lock.sha256, final_arm=final_arm)
    con=timer=None
    try:
        report['resources']=resource_preflight(output)
        import duckdb
        import numpy as np
        from catboost import CatBoostClassifier
        train_paths=[Path(p).resolve() for p in train_paths]
        validation_path=Path(validation_path).resolve()
        manifests=[read_manifest(p,deadline) for p in train_paths]
        val_manifest=read_manifest(validation_path,deadline,final_lock)
        anchors=[date.fromisoformat(m['anchor']) for m in manifests]
        val_anchor=date.fromisoformat(val_manifest['anchor'])
        if len(set(anchors))!=len(anchors) or any(a+timedelta(days=7)>val_anchor for a in anchors):
            raise ValueError('Training target periods must finish before validation anchor')
        for m in manifests:
            if m['policy']!=val_manifest['policy'] or m['features']!=val_manifest['features'] or m['database']!=val_manifest['database']:
                raise ValueError('Collections must share policy, feature contract and database identity')
        numeric_names,cat_names=choose_features(val_manifest,feature_set,feature_names)
        names=numeric_names+cat_names
        report['features']=dict(numeric=numeric_names,categorical=cat_names,contract_digest=val_manifest['features']['digest'])
        report['inputs']=[dict(anchor=m['anchor'],manifest_sha256=sha256_file(p/'manifest.json',deadline),
                               qcy_identity=m['qcy_identity'],candidate_identity=m['candidate_identity'])
                          for p,m in zip(train_paths+[validation_path],manifests+[val_manifest])]
        report['runtime']=runtime_identity()
        report['code']={p.name:sha256_file(p,deadline) for p in (Path(__file__),ROOT/'scripts/hm_baseline.py')}
        parameters=fixed_parameters(iterations,depth,seed)
        report['hyperparameters']=parameters
        identity_payload=dict(inputs=report['inputs'],features=report['features'],
            hyperparameters=parameters,train_users=train_users,negative_sample=negative_sample,sampling_seed=SEED,
            code=report['code'],runtime=report['runtime'])
        if final_lock is not None:
            identity_payload.update(final_lock_sha256=final_lock.sha256, final_arm=final_arm)
        report['fit_identity']=canonical_digest(identity_payload)
        # An in-memory DB is enough for cached parquet scans; its spills remain ignored.
        con=duckdb.connect(':memory:')
        con.execute('SET threads=4')
        con.execute("SET memory_limit='2GB'")
        temp=output/'duckdb-temp'
        temp.mkdir()
        con.execute('SET temp_directory=?',[str(temp)])
        con.execute("SET max_temp_directory_size='8GB'")
        timer=deadline.interrupt_sql(con)
        training=[]
        report['training_populations']=[]
        for path,manifest in zip(train_paths,manifests):
            deadline.check()
            frame,_,summary=load_part(con,path,manifest,names,train_users,negative_sample)
            numbers,cats=model_arrays(frame,numeric_names,cat_names)
            training.append((numbers,cats,frame['label'].to_numpy(dtype=np.int8),frame['fit_weight'].to_numpy(dtype=np.float64)))
            report['training_populations'].append(summary)
            del frame
        numbers=np.concatenate([p[0] for p in training])
        cats=np.concatenate([p[1] for p in training])
        labels=np.concatenate([p[2] for p in training])
        weights=np.concatenate([p[3] for p in training])
        del training
        if len(np.unique(labels))!=2:
            raise ValueError('Training needs both naturally retrieved label classes')
        deadline.check()
        pool=model_pool(numbers,cats,numeric_names,cat_names,labels,weights)
        class WallCallback:
            def after_iteration(self, info):
                report['last_training_iteration']=int(info.iteration)
                if info.iteration % 50 == 0:
                    print(json.dumps(dict(iteration=int(info.iteration),
                        elapsed_seconds=round(time.monotonic()-deadline.started,3)),ensure_ascii=True),
                        file=sys.stderr,flush=True)
                return time.monotonic()<deadline.expires
        model=CatBoostClassifier(**parameters)
        report['fit_count']=1
        report['last_training_iteration']=0
        model.fit(pool,callbacks=[WallCallback()])
        deadline.check()
        if model.tree_count_!=iterations:
            raise RuntimeError('Fixed-tree fit incomplete')
        report['actual_trees']=model.tree_count_
        model.save_model(str(output/'model.cbm'))
        del pool,numbers,cats,labels,weights
        frame,targets,summary=load_part(con,validation_path,val_manifest,names,None,None)
        numbers,cats=model_arrays(frame,numeric_names,cat_names)
        validation=pilot.Collection(numbers,cats,frame['label'].to_numpy(),frame['query_weight'].to_numpy(),
            frame['customer_id'].to_numpy(),frame['article_id'].to_numpy(),targets,summary)
        deadline.check()
        scores=model.predict_proba(model_pool(numbers,cats,numeric_names,cat_names),thread_count=4)[:,1]
        report['validation_population']=summary
        report['validation_metrics']=pilot.rank_collection(validation,scores=scores)
        write_private_predictions(con,output,validation,scores)
        report['files']={name:sha256_file(output/name,deadline) for name in
                         ('model.cbm','query-metrics.parquet','predictions-top12.parquet')}
        deadline.check()
        report['status']='completed'
    except Exception as exc:
        report['status']='failed'
        report['error']=dict(type=type(exc).__name__, message=str(exc)[:2048],
                             traceback=traceback.format_exc(limit=12)[-8192:])
        raise
    finally:
        if timer:
            timer.cancel()
        if con:
            con.close()
        report['elapsed_seconds']=round(time.monotonic()-deadline.started,3)
        write_json(output/'report.json',report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    collect_parser=sub.add_parser('collect')
    collect_parser.add_argument('--database',type=Path,required=True)
    collect_parser.add_argument('--output',type=Path,required=True)
    collect_parser.add_argument('--anchor',required=True)
    collect_parser.add_argument('--users',type=int,required=True)
    collect_parser.add_argument('--policy',choices=POLICIES,required=True)
    collect_parser.add_argument('--wall-seconds',type=float,default=1800)
    fit_parser=sub.add_parser('fit')
    fit_parser.add_argument('--train',type=Path,nargs='+',required=True)
    fit_parser.add_argument('--validation',type=Path,required=True)
    fit_parser.add_argument('--output',type=Path,required=True)
    group=fit_parser.add_mutually_exclusive_group()
    group.add_argument('--feature-set',choices=('pilot','strong'),default='pilot')
    group.add_argument('--feature-names-file',type=Path)
    fit_parser.add_argument('--iterations',type=int,default=150)
    fit_parser.add_argument('--depth',type=int,default=6)
    fit_parser.add_argument('--seed',type=int,default=SEED)
    fit_parser.add_argument('--train-users',type=int)
    fit_parser.add_argument('--negative-sample',type=int,choices=(0,20),default=0)
    fit_parser.add_argument('--wall-seconds',type=float,default=1800)
    collect_parser.add_argument('--decision-lock',type=Path)
    fit_parser.add_argument('--decision-lock',type=Path)
    args=parser.parse_args(argv)
    try:
        if args.command=='collect':
            result=collect(args.database,args.output,args.anchor,args.users,args.policy,args.wall_seconds,args.decision_lock)
        else:
            names=json.loads(args.feature_names_file.read_text(encoding='utf-8')) if args.feature_names_file else None
            if names is not None and (not isinstance(names,list) or not all(isinstance(n,str) for n in names)):
                raise ValueError('Feature names file must contain a JSON string list')
            result=fit(args.train,args.validation,args.output,args.feature_set,names,args.iterations,args.depth,
                       args.seed,args.train_users,args.negative_sample,args.wall_seconds,args.decision_lock)
    except Exception as exc:
        print(json.dumps(dict(status='failed',error_type=type(exc).__name__,output=args.output.as_posix())))
        return 1
    print(json.dumps(dict(status=result['status'],output=args.output.resolve().as_posix())))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
