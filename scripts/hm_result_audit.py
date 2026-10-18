"""Audit saved H&M development predictions independently; never fit or predict.

Full cached Q/C/Y and optional original source are checked. Saved top12 scores
prove ordering within that export; scores for omitted candidates are unavailable,
so this audit does not establish that exports are the model's true global top12.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
TOLERANCE = 1e-12
QUERY_FIELDS = ('targets','candidate_count','hits12','covered','ap12','recall12','oracle_ap12')


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical_digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def close(actual, expected):
    if actual is None or expected is None:
        return actual is None and expected is None
    return math.isfinite(float(actual)) and math.isfinite(float(expected)) and abs(float(actual)-float(expected)) <= TOLERANCE


class Deadline:
    def __init__(self, seconds):
        require(math.isfinite(seconds) and seconds > 0, 'Finite positive wall limit required')
        self.started = time.monotonic()
        self.expires = self.started + seconds

    def check(self):
        if time.monotonic() >= self.expires:
            raise TimeoutError('Independent audit exceeded wall limit')


def file_digest(path, deadline):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024**2), b''):
            deadline.check()
            digest.update(block)
    return digest.hexdigest()


def evaluate_query(predictions, truth, candidate_count, covered):
    """Independent AP from rank positions; Y includes all off-candidate truth."""
    truth = set(truth)
    require(len(predictions)==min(12,candidate_count), 'Prediction count must fill available top12')
    require(0 <= covered <= min(candidate_count,len(truth)), 'Invalid candidate coverage')
    require(len(set(a for a,_,_ in predictions))==len(predictions), 'Duplicate predicted article')
    require([rank for _,rank,_ in predictions]==list(range(1,len(predictions)+1)), 'Prediction ranks must be contiguous')
    require(all(isinstance(a,str) and math.isfinite(float(score)) for a,_,score in predictions), 'Invalid prediction ID/score')
    require(predictions==sorted(predictions,key=lambda row:(-float(row[2]),row[0])), 'Prediction score/tie ordering is inconsistent')
    hits, numerator = 0, 0.0
    for article, rank, _ in predictions:
        if article in truth:
            hits += 1
            numerator += hits/rank
    require(hits <= covered, 'Predicted hits exceed candidate-covered truth')
    size = len(truth)
    return dict(targets=size,candidate_count=candidate_count,hits12=hits,covered=covered,
                ap12=numerator/min(size,12) if size else 0.0,
                recall12=hits/size if size else 0.0,
                oracle_ap12=min(covered,12)/min(size,12) if size else 0.0)


def aggregate_queries(per_query):
    values=list(per_query.values())
    positive=[row for row in values if row['targets']]
    total=sum(row['targets'] for row in values)
    mean=lambda key,rows:sum(row[key] for row in rows)/len(rows) if rows else None
    return dict(queries=len(values),positive_queries=len(positive),empty_target_queries=len(values)-len(positive),
                map_at_12_conditional=mean('ap12',positive),recall_at_12_conditional=mean('recall12',positive),
                map_at_12_all_queries_empty_zero=mean('ap12',values),recall_at_12_all_queries_empty_zero=mean('recall12',values),
                candidate_query_coverage_conditional=sum(row['covered']>0 for row in positive)/len(positive) if positive else None,
                candidate_target_coverage_micro=sum(row['covered'] for row in values)/total if total else None,
                oracle_map_at_12_conditional=mean('oracle_ap12',positive),distinct_query_target_pairs=total)


def check_export(per_query, exported):
    require(set(per_query)==set(exported), 'Per-query export must include exact complete Q')
    for user, values in per_query.items():
        require(set(QUERY_FIELDS)<=set(exported[user]), 'Missing exported per-query fields')
        require(all(close(values[key],exported[user][key]) for key in QUERY_FIELDS), 'Exported per-query metrics disagree')


def paired_bootstrap(reference, alternative, deadline=None, draws=2000, seed=2026):
    import numpy as np
    require(set(reference)==set(alternative), 'Paired arms require identical users')
    require(all(reference[u]['targets']==alternative[u]['targets'] for u in reference), 'Paired arms require identical Y sizes')
    users=sorted(u for u in reference if reference[u]['targets']>0)
    differences=np.asarray([alternative[u]['ap12']-reference[u]['ap12'] for u in users],dtype=float)
    result=dict(metric='conditional MAP@12 difference',unit='positive validation user',queries=len(users),draws=draws,seed=seed,
                mean_delta=float(differences.mean()) if users else None,percentile_95=None,
                interpretation='Descriptive fixed-model/single-week interval; no equivalence or generalization claim')
    if users:
        rng=np.random.default_rng(seed)
        means=[]
        for _ in range(draws):
            if deadline:
                deadline.check()
            means.append(float(differences[rng.integers(0,len(users),size=len(users))].mean()))
        result['percentile_95']=[float(x) for x in np.quantile(means,[0.025,0.975])]
    return result


def code_identity(stored, deadline):
    require(isinstance(stored,dict) and bool(stored), 'Producer code identities required')
    comparison={}
    for name,digest in stored.items():
        require(Path(name).name==name and bool(re.fullmatch('[0-9a-f]{64}',digest)), 'Invalid producer code identity')
        path=ROOT/'scripts'/name
        comparison[name]=dict(recorded_sha256=digest,current_source_matches=file_digest(path,deadline)==digest if path.is_file() else None)
    return comparison


def heuristic_predictions(connection, frame_path, method, deadline):
    """Rank complete cached C; omit outcome columns and preserve exact pilot scores."""
    require(method in ('recency','popularity'), 'Unknown heuristic')
    fields={d[0] for d in connection.execute('SELECT * FROM read_parquet(?) LIMIT 0',[str(frame_path)]).description}
    if not {'global_rank','user_recent_rank'} <= fields:
        return None
    invalid=connection.execute('''SELECT count(*) FROM read_parquet(?)
        WHERE global_rank IS NULL OR user_recent_rank IS NULL OR NOT isfinite(global_rank)
        OR NOT isfinite(user_recent_rank)''',[str(frame_path)]).fetchone()[0]
    require(invalid==0, 'Heuristic ranks must be finite and nonnull')
    score='-(user_recent_rank*1000.0+global_rank)' if method=='recency' else '-(global_rank*1000.0+user_recent_rank)'
    cursor=connection.execute(f'''WITH scored AS (SELECT customer_id,article_id,{score} AS score
        FROM read_parquet(?)), ranked AS (SELECT *,row_number() OVER
        (PARTITION BY customer_id ORDER BY score DESC,article_id ASC) AS rank FROM scored)
        SELECT customer_id,article_id,rank,score FROM ranked WHERE rank<=12 ORDER BY customer_id,rank''',[str(frame_path)])
    predictions={}
    while rows:=cursor.fetchmany(8192):
        deadline.check()
        for user,article,rank,value in rows:
            predictions.setdefault(user,[]).append((article,rank,value))
    return predictions


def audit(validation, fits, output, database=None, wall_seconds=1800):
    import duckdb
    import pandas as pd
    deadline=Deadline(wall_seconds)
    output=Path(output).resolve()
    allowed=(ROOT/'artifacts').resolve()
    require(output!=allowed and output.is_relative_to(allowed), 'New output must be inside checkout artifacts/')
    output.mkdir(parents=True,exist_ok=False)
    report=dict(format='hm-independent-result-audit-v1',status='running',fits=[],comparisons=[],fit_vs_recency=[],
                scope='Independent cached fullQ/C/Y and saved-top12 metrics; optional source Q/Y rebuild; no model fit/prediction',
                limitation='Ordering is checked inside saved top12 only; omitted model scores and feature formulas are not re-evaluated.',
                tolerance=TOLERANCE)
    con=timer=None
    try:
        require(shutil.disk_usage(output).free>=10*1024**3, 'At least10GiB output free space required')
        validation=Path(validation).resolve()
        manifest_path=validation/'manifest.json'
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        require(manifest.get('format')=='hm-experiment-collection-v1' and manifest.get('status')=='completed', 'Completed collection required')
        require(manifest['anchor'] in ('2020-09-02','2020-09-09') and manifest['horizon_days']==7 and manifest['cohort_seed']==2026,
                'Audit accepts frozen development anchors Sep02/Sep09 only')
        for name in ('frame.parquet','users.parquet','targets.parquet'):
            require(file_digest(validation/name,deadline)==manifest['files'][name], 'Collection artifact SHA256 mismatch')
        require(canonical_digest({name:manifest['files'][name] for name in ('users.parquet','targets.parquet')})==manifest['qcy_identity'], 'Collection Q/Y identity mismatch')
        report['collection']=dict(anchor=manifest['anchor'],policy=manifest['policy'],manifest_sha256=file_digest(manifest_path,deadline),
                                  qcy_identity=manifest['qcy_identity'],candidate_identity=manifest['candidate_identity'],
                                  code=code_identity(manifest['code'],deadline),database_identity=manifest['database'])
        require(bool(fits) and len(set(Path(p).resolve() for p in fits))==len(fits), 'Distinct fit directories required')
        source_stat=None
        if database is not None:
            database=Path(database).resolve()
            source_stat=database.stat()
            require(file_digest(database,deadline)==manifest['database']['sha256'] and source_stat.st_size==manifest['database']['bytes'], 'Original database identity mismatch')
        con=duckdb.connect(str(database) if database is not None else ':memory:',read_only=database is not None)
        con.execute('SET threads=2')
        con.execute("SET memory_limit='2GB'")
        con.execute('SET preserve_insertion_order=false')
        temp=output/'duckdb-temp'
        temp.mkdir()
        con.execute('SET temp_directory=?',[str(temp)])
        con.execute("SET max_temp_directory_size='8GB'")
        timer=threading.Timer(max(0,deadline.expires-time.monotonic()),con.interrupt)
        timer.daemon=True
        timer.start()
        def count(sql,params=None):
            deadline.check()
            return con.execute(sql,params or []).fetchone()[0]
        con.execute('CREATE TEMP TABLE a_users AS SELECT * FROM read_parquet(?)',[str(validation/'users.parquet')])
        con.execute('CREATE TEMP TABLE a_targets AS SELECT customer_id,article_id FROM read_parquet(?)',[str(validation/'targets.parquet')])
        con.execute('CREATE TEMP TABLE a_candidates AS SELECT customer_id,article_id,label,full_candidate_count,query_weight FROM read_parquet(?)',[str(validation/'frame.parquet')])
        for table in ('a_targets','a_candidates'):
            require(count(f'''SELECT count(*) FROM (SELECT customer_id,article_id,count(*) n FROM {table} GROUP BY ALL HAVING n<>1)''')==0,'Duplicate cached Q/Y/C key')
            require(count(f'''SELECT count(*) FROM {table} x WHERE customer_id IS NULL OR article_id IS NULL OR NOT EXISTS(SELECT 1 FROM a_users u WHERE u.customer_id=x.customer_id)''')==0,'Cached IDs must belong to Q')
        require(count('SELECT count(*)-count(DISTINCT customer_id) FROM a_users')==0 and count('SELECT count(*) FROM a_users')>0, 'Unique nonempty cached Q required')
        require(count("SELECT count(*) FROM a_users WHERE customer_id IS NULL OR cohort_hash<>sha256(customer_id || ':2026') OR cohort_hash IS NULL")==0, 'Cached cohort hash mismatch')
        con.execute('CREATE TEMP TABLE a_sizes AS SELECT customer_id,count(*) n FROM a_candidates GROUP BY customer_id')
        require(count('''SELECT count(*) FROM a_users u LEFT JOIN a_sizes s USING(customer_id)
            WHERE s.n IS NULL OR u.full_candidate_count IS NULL OR s.n<>u.full_candidate_count''')==0,
                'Candidate rows must represent every full query')
        require(count('''SELECT count(*) FROM a_candidates c JOIN a_sizes s USING(customer_id)
            WHERE c.full_candidate_count IS NULL OR c.full_candidate_count<>s.n OR c.query_weight IS NULL
            OR NOT isfinite(c.query_weight) OR abs(c.query_weight-1.0/s.n)>1e-12 OR c.label IS NULL
            OR c.label<>EXISTS(SELECT 1 FROM a_targets t WHERE t.customer_id=c.customer_id AND t.article_id=c.article_id)''')==0,'Cached label/denominator/weight mismatch')
        candidate_digest=hashlib.sha256()
        cursor=con.execute('SELECT customer_id,article_id FROM a_candidates ORDER BY customer_id,article_id')
        while rows:=cursor.fetchmany(8192):
            deadline.check()
            for row in rows:
                for value in row:
                    encoded=value.encode('utf-8')
                    candidate_digest.update(len(encoded).to_bytes(4,'big'))
                    candidate_digest.update(encoded)
        require(candidate_digest.hexdigest()==manifest['candidate_identity'],'Candidate key identity mismatch')
        if database is not None:
            anchor=manifest['anchor']
            con.execute("""CREATE TEMP TABLE a_raw_users AS SELECT DISTINCT customer_id FROM transactions
                WHERE t_dat>=?::DATE-INTERVAL '90 days' AND t_dat<?::DATE
                ORDER BY sha256(customer_id || ':2026'),customer_id LIMIT ?""",[anchor,anchor,manifest['requested_users']])
            con.execute("""CREATE TEMP TABLE a_raw_targets AS SELECT DISTINCT t.customer_id,t.article_id
                FROM transactions t JOIN a_raw_users u USING(customer_id)
                WHERE t.t_dat>=?::DATE AND t.t_dat<?::DATE+INTERVAL '7 days'""",[anchor,anchor])
            for actual,expected,columns in (('a_users','a_raw_users','customer_id'),('a_targets','a_raw_targets','customer_id,article_id')):
                require(count(f'''SELECT count(*) FROM ((SELECT {columns} FROM {actual} EXCEPT SELECT {columns} FROM {expected})
                    UNION ALL (SELECT {columns} FROM {expected} EXCEPT SELECT {columns} FROM {actual}))''')==0,'Source-rebuilt Q/fullY mismatch')
            report['source_rebuild']='PASS: raw history-only SHA256 Q and full distinct weekly Y'
        else:
            report['source_rebuild']='NOT REQUESTED: cached Q/C/Y only'
        users=[row[0] for row in con.execute('SELECT customer_id FROM a_users ORDER BY customer_id').fetchall()]
        truth={u:set() for u in users}
        for user,article in con.execute('SELECT customer_id,article_id FROM a_targets').fetchall():
            truth[user].add(article)
        counts=dict(con.execute('SELECT customer_id,n FROM a_sizes').fetchall())
        coverage=dict(con.execute('''SELECT c.customer_id,count(*) FROM a_candidates c JOIN a_targets t USING(customer_id,article_id) GROUP BY c.customer_id''').fetchall())
        def export_queries(values,filename):
            rows=[dict(customer_id=user,**row) for user,row in values.items()]
            con.register('_audit_per_query',pd.DataFrame(rows))
            con.sql('SELECT * FROM _audit_per_query ORDER BY customer_id').write_parquet(str(output/filename))
            return {'file':filename,'sha256':file_digest(output/filename,deadline)}
        heuristic_values={}
        report['heuristics']={'status':'unavailable','reason':'Cached frame does not contain both global_rank and user_recent_rank'}
        for method in ('recency','popularity'):
            predicted=heuristic_predictions(con,validation/'frame.parquet',method,deadline)
            if predicted is None:
                break
            require(set(predicted)==set(users),'Heuristic ranking must retain complete Q')
            values={}
            for user in users:
                deadline.check()
                values[user]=evaluate_query(predicted[user],truth[user],counts[user],coverage.get(user,0))
            heuristic_values[method]=values
            if report['heuristics']['status']=='unavailable':
                report['heuristics']={'status':'evaluated','scope':'Same full cached Q/C/Y; fixed pilot score formulas, article ID tie break; no fit'}
            formula='-(user_recent_rank*1000+global_rank)' if method=='recency' else '-(global_rank*1000+user_recent_rank)'
            report['heuristics'][method]=dict(score_formula=formula,metrics=aggregate_queries(values),
                private_query_metrics=export_queries(values,f'heuristic-{method}-query-metrics.parquet'))
        all_query_values=[]
        for index,fit_path in enumerate(fits):
            deadline.check()
            fit_path=Path(fit_path).resolve()
            producer=json.loads((fit_path/'report.json').read_text(encoding='utf-8'))
            require(producer.get('format')=='hm-experiment-fit-v1' and producer.get('status')=='completed' and producer['fit_count']==1,'Completed single fit required')
            require(producer['actual_trees']==producer['hyperparameters']['iterations'],'Fixed-tree fit did not complete')
            expected_input=dict(anchor=manifest['anchor'],manifest_sha256=report['collection']['manifest_sha256'],
                                qcy_identity=manifest['qcy_identity'],candidate_identity=manifest['candidate_identity'])
            require(producer['inputs'][-1]==expected_input,'Fit validation provenance differs from supplied cache')
            val_date=date.fromisoformat(manifest['anchor'])
            require(len({m['anchor'] for m in producer['inputs'][:-1]})==len(producer['inputs'])-1 and bool(producer['inputs'][:-1]) and
                    all(date.fromisoformat(m['anchor'])+timedelta(days=7)<=val_date for m in producer['inputs'][:-1]),'Fit training label periods overlap validation')
            payload=dict(inputs=producer['inputs'],features=producer['features'],hyperparameters=producer['hyperparameters'],
                         train_users=producer['training_user_limit'],negative_sample=producer['negative_sample'],sampling_seed=producer['sampling_seed'],
                         code=producer['code'],runtime=producer['runtime'])
            require(canonical_digest(payload)==producer['fit_identity'],'Fit provenance identity mismatch')
            require(producer['features']['contract_digest']==manifest['features']['digest'],'Feature contract provenance mismatch')
            for name in ('model.cbm','query-metrics.parquet','predictions-top12.parquet'):
                require(file_digest(fit_path/name,deadline)==producer['files'][name],'Fit artifact SHA256 mismatch')
            con.execute('CREATE OR REPLACE TEMP TABLE a_predictions AS SELECT * FROM read_parquet(?)',[str(fit_path/'predictions-top12.parquet')])
            require(count('''SELECT count(*) FROM a_predictions p WHERE customer_id IS NULL OR article_id IS NULL OR
                NOT EXISTS(SELECT 1 FROM a_candidates c WHERE c.customer_id=p.customer_id AND c.article_id=p.article_id)''')==0,'Prediction is outside candidate set')
            predictions={u:[] for u in users}
            for user,article,rank,score in con.execute('SELECT customer_id,article_id,rank,score FROM a_predictions ORDER BY customer_id,rank').fetchall():
                predictions[user].append((article,rank,score))
            per_query={}
            for user in users:
                deadline.check()
                per_query[user]=evaluate_query(predictions[user],truth[user],counts[user],coverage.get(user,0))
            cursor=con.execute('SELECT * FROM read_parquet(?)',[str(fit_path/'query-metrics.parquet')])
            columns=[d[0] for d in cursor.description]
            exported={}
            for row in cursor.fetchall():
                values=dict(zip(columns,row))
                require(values['customer_id'] not in exported,'Duplicate query in metric export')
                exported[values.pop('customer_id')]=values
            check_export(per_query,exported)
            aggregate=aggregate_queries(per_query)
            require(set(aggregate)==set(producer['validation_metrics']) and all(close(value,producer['validation_metrics'][key]) for key,value in aggregate.items()),'Reported aggregate metrics disagree')
            require(producer['validation_population']['selected_queries']==len(users) and producer['validation_population']['full_candidate_rows']==sum(counts.values()) and
                    producer['validation_population']['target_pairs']==sum(map(len,truth.values())),'Reported validation population disagrees')
            filename=f'arm-{index:02d}-query-metrics.parquet'
            report['fits'].append(dict(arm=index,fit_directory=fit_path.as_posix(),report_sha256=file_digest(fit_path/'report.json',deadline),
                                       fit_identity=producer['fit_identity'],code=code_identity(producer['code'],deadline),metrics=aggregate,
                                       private_query_metrics=export_queries(per_query,filename)))
            all_query_values.append(per_query)
            if 'recency' in heuristic_values:
                report['fit_vs_recency'].append(dict(reference='recency',alternative_arm=index,
                    **paired_bootstrap(heuristic_values['recency'],per_query,deadline)))
        for index in range(1,len(all_query_values)):
            report['comparisons'].append(dict(reference_arm=0,alternative_arm=index,
                **paired_bootstrap(all_query_values[0],all_query_values[index],deadline)))
        if database is not None:
            after=database.stat()
            require((source_stat.st_size,source_stat.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'Source database changed during audit')
        deadline.check()
        report['checker_sha256']=file_digest(Path(__file__),deadline)
        report['resources']=dict(threads=2,duckdb_memory='2GB',spill_limit='8GB',wall_seconds=wall_seconds)
        report['status']='PASS'
    except Exception as error:
        report['status']='FAIL'
        report['error']={'type':type(error).__name__}
        if isinstance(error,(ValueError,TimeoutError)):
            report['error']['check']=str(error)
        raise
    finally:
        if timer is not None:
            timer.cancel()
        if con is not None:
            con.close()
        report['elapsed_seconds']=round(time.monotonic()-deadline.started,3)
        (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation',type=Path,required=True)
    parser.add_argument('--fits',type=Path,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--database',type=Path)
    parser.add_argument('--wall-seconds',type=float,default=1800)
    args=parser.parse_args(argv)
    try:
        report=audit(args.validation,args.fits,args.output,args.database,args.wall_seconds)
    except Exception as error:
        print(json.dumps({'status':'FAIL','error_type':type(error).__name__,'output':args.output.as_posix()}))
        return 1
    print(json.dumps({'status':report['status'],'output':args.output.resolve().as_posix()}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
