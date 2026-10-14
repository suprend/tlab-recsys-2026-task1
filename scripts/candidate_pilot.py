"""Past-only popular/recent retrieval; full targets are joined after C exists."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

import duckdb

from scripts.anchor_pilot import RunDeadline, StageLedger, _dict_rows, directory_bytes, naive_utc, peak_rss_bytes, save_json, utc
from scripts.protocol_manifest import build_run_manifest, load_run_manifest, sha256_file, validate_protocol, write_run_manifest
from scripts.temporal_contract import history_window

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def _direct_stage(name, operation):
    return operation()


def validate_queries(con, config):
    """Reject malformed/future Q; this does not reconstruct the sampling proof."""
    bad = con.execute('''SELECT count(*) FROM pilot_queries WHERE query_id IS NULL
        OR query_id='' OR user_id IS NULL OR anchor IS NULL OR label_is_mature IS NULL OR anchor<CAST(? AS TIMESTAMP)
        OR anchor>=CAST(? AS TIMESTAMP) OR anchor<>date_trunc('day',anchor)''',
        [naive_utc(utc(config['pilot']['start'])), naive_utc(utc(config['pilot']['end']))]).fetchone()[0]
    counts = con.execute('SELECT count(*),count(DISTINCT query_id),count(DISTINCT (user_id,anchor)) FROM pilot_queries').fetchone()
    if bad or counts[0] != counts[1] or counts[0] != counts[2]:
        raise ValueError('Queries must be unique, nonnull user-days at declared UTC anchors')
    maximum = con.execute('SELECT coalesce(max(n),0) FROM (SELECT count(*) n FROM pilot_queries GROUP BY anchor)').fetchone()[0]
    if counts[0] > config['budget']['max_anchors'] or maximum > config['query']['max_users_per_day']:
        raise ValueError('Input query count exceeds declared sampling budget')


def create_candidates(con, config, *, stage=_direct_stage):
    """Read only events and Q; never inspect Y when generating candidates.

    Popularity counts distinct purchase users. Recent counts distinct IDs,
    including bought products. Source overlap is deduplicated without refill.
    Empty sources remain empty; the contract does not invent availability.
    """
    config = validate_protocol(config)
    validate_queries(con, config)
    spec = config['candidates']
    if spec['max_unique'] < spec['popular_limit'] + spec['recent_limit']:
        raise ValueError('v1 no-refill union requires max_unique >= the sum of source quotas')
    con.execute('''CREATE OR REPLACE TEMP TABLE pilot_candidates (
        query_id VARCHAR,product_id BIGINT,from_popular BOOLEAN,from_recent BOOLEAN,
        popularity_distinct_users BIGINT,popular_source_rank BIGINT,recent_source_rank BIGINT,
        last_user_event_time TIMESTAMP)''')
    sizes, plans = [], []
    anchors = [row[0] for row in con.execute('SELECT DISTINCT anchor FROM pilot_queries ORDER BY anchor').fetchall()]
    for raw_anchor in anchors:
        anchor = raw_anchor.replace(tzinfo=UTC)
        popular_window = history_window(anchor, timedelta(hours=spec['popular_window_hours']))
        recent_window = history_window(anchor, timedelta(hours=spec['recent_window_hours']))
        con.execute('CREATE OR REPLACE TEMP TABLE pilot_day_queries AS SELECT query_id,user_id,anchor FROM pilot_queries WHERE anchor=?', [raw_anchor])
        sql = '''SELECT product_id,count(DISTINCT user_id)::BIGINT popularity_distinct_users
            FROM events WHERE event_time>=? AND event_time<? AND event_type='purchase'
            AND product_id IS NOT NULL AND user_id IS NOT NULL GROUP BY product_id'''
        params = [naive_utc(popular_window.start), raw_anchor]
        plans.append({'anchor': anchor, 'source': 'popular', 'scan_start': popular_window.start,
                      'scan_end_exclusive': anchor, 'explain_estimate_only': '\n'.join(r[1] for r in con.execute('EXPLAIN '+sql,params).fetchall())})
        stage('popular_counts_'+anchor.strftime('%Y-%m-%d'), lambda: con.execute('CREATE OR REPLACE TEMP TABLE pilot_popularity AS '+sql,params))
        con.execute('''CREATE OR REPLACE TEMP TABLE pilot_popular_top AS SELECT product_id,
            popularity_distinct_users,row_number() OVER(ORDER BY popularity_distinct_users DESC,product_id) popular_source_rank
            FROM pilot_popularity ORDER BY popularity_distinct_users DESC,product_id LIMIT ?''', [spec['popular_limit']])
        types = ','.join('?' for _ in spec['recent_event_types'])
        recent_sql = f'''SELECT q.query_id,e.product_id,max(e.event_time) last_user_event_time,
            row_number() OVER(PARTITION BY q.query_id ORDER BY max(e.event_time) DESC,e.product_id) recent_source_rank
            FROM events e JOIN pilot_day_queries q ON e.user_id=q.user_id
            WHERE e.event_time>=? AND e.event_time<? AND e.event_type IN ({types})
              AND e.product_id IS NOT NULL GROUP BY q.query_id,e.product_id
            QUALIFY recent_source_rank<=?'''
        recent_params = [naive_utc(recent_window.start),raw_anchor,*spec['recent_event_types'],spec['recent_limit']]
        plans.append({'anchor': anchor, 'source': 'recent', 'scan_start': recent_window.start,
                      'scan_end_exclusive': anchor, 'explain_estimate_only': '\n'.join(r[1] for r in con.execute('EXPLAIN '+recent_sql,recent_params).fetchall())})
        stage('recent_'+anchor.strftime('%Y-%m-%d'),lambda: con.execute('CREATE OR REPLACE TEMP TABLE pilot_recent_top AS '+recent_sql,recent_params))
        stage('union_'+anchor.strftime('%Y-%m-%d'),lambda: con.execute('''INSERT INTO pilot_candidates
            WITH source_rows AS (
                SELECT q.query_id,p.product_id,true from_popular,false from_recent,
                    p.popular_source_rank,NULL::BIGINT recent_source_rank,NULL::TIMESTAMP last_user_event_time
                FROM pilot_day_queries q CROSS JOIN pilot_popular_top p
                UNION ALL
                SELECT query_id,product_id,false,true,NULL::BIGINT,recent_source_rank,last_user_event_time
                FROM pilot_recent_top), deduplicated AS (
                SELECT query_id,product_id,bool_or(from_popular) from_popular,bool_or(from_recent) from_recent,
                    min(popular_source_rank) popular_source_rank,min(recent_source_rank) recent_source_rank,
                    max(last_user_event_time) last_user_event_time FROM source_rows GROUP BY query_id,product_id)
            SELECT d.query_id,d.product_id,d.from_popular,d.from_recent,coalesce(p.popularity_distinct_users,0),
                d.popular_source_rank,d.recent_source_rank,d.last_user_event_time
            FROM deduplicated d LEFT JOIN pilot_popularity p USING(product_id)'''))
        sizes.append({'anchor': anchor,
            'popular_count_keys': con.execute('SELECT count(*) FROM pilot_popularity').fetchone()[0],
            'popular_source_items':con.execute('SELECT count(*) FROM pilot_popular_top').fetchone()[0],
            'recent_source_pairs':con.execute('SELECT count(*) FROM pilot_recent_top').fetchone()[0]})
    stats = con.execute('''SELECT count(*),count(DISTINCT (query_id,product_id)) FROM pilot_candidates''').fetchone()
    if stats[0] != stats[1] or stats[0] > config['budget']['max_candidate_pairs']:
        raise ValueError('Candidate uniqueness or row budget violated')
    overflow = con.execute('''SELECT count(*) FROM (SELECT query_id,count(*) n FROM pilot_candidates
        GROUP BY query_id HAVING n>?)''',[spec['max_unique']]).fetchone()[0]
    if overflow:
        raise ValueError('Per-query candidate budget violated')
    return {'source_state':sizes,'scan_plans':plans,'candidate_rows':stats[0]}


def verify_catalog(con, config, *, stage=_direct_stage):
    """Independent full necessary past scan, not a catalog derived from Y."""
    last = con.execute('SELECT max(anchor) FROM pilot_queries').fetchone()[0]
    if last is None:
        return
    stage('candidate_catalog_verification', lambda: con.execute('''CREATE OR REPLACE TEMP TABLE pilot_candidate_first_seen AS
        SELECT e.product_id,min(e.event_time) first_seen FROM events e
        SEMI JOIN (SELECT DISTINCT product_id FROM pilot_candidates) c USING(product_id)
        WHERE e.event_time>=? AND e.event_time<? GROUP BY e.product_id''',
        [naive_utc(utc(config['source']['start'])),last]))
    invalid = con.execute('''SELECT count(*) FROM pilot_candidates c JOIN pilot_queries q USING(query_id)
        LEFT JOIN pilot_candidate_first_seen f USING(product_id) WHERE f.first_seen IS NULL OR f.first_seen>=q.anchor''').fetchone()[0]
    if invalid:
        raise ValueError('Candidate outside strict-past observed catalog')


def coverage_report(con):
    """All-target denominators, including cold and nonretrieved purchases."""
    # Artifact integrity is checked after C exists, so target validation cannot
    # influence retrieval. Binary Y forbids duplicate/orphan/partial labels.
    label_counts = con.execute('SELECT count(*),count(DISTINCT (query_id,product_id)) FROM pilot_labels').fetchone()
    invalid_labels = con.execute('''SELECT count(*) FROM pilot_labels l LEFT JOIN pilot_queries q USING(query_id)
        WHERE q.query_id IS NULL OR l.product_id IS NULL OR l.catalog_seen_before IS NULL
        OR l.pair_seen_before IS NULL OR NOT q.label_is_mature''').fetchone()[0]
    if invalid_labels or label_counts[0] != label_counts[1]:
        raise ValueError('Labels must be unique binary targets of mature, existing queries')
    inconsistent_catalog = con.execute('''SELECT count(*) FROM pilot_labels l JOIN pilot_candidates c USING(query_id,product_id)
        WHERE NOT l.catalog_seen_before''').fetchone()[0]
    if inconsistent_catalog:
        raise ValueError('Retrieved target contradicts strict-past catalog diagnosis')
    con.execute('''CREATE OR REPLACE TEMP TABLE pilot_coverage AS
        WITH pool AS (SELECT query_id,count(*) candidate_count,
            count(*) FILTER(WHERE from_popular) popular_count,
            count(*) FILTER(WHERE from_recent) recent_count,
            count(*) FILTER(WHERE from_popular AND from_recent) overlap_count
            FROM pilot_candidates GROUP BY query_id), outcomes AS (
            SELECT l.query_id,count(*) target_count,
                count(*) FILTER(WHERE l.catalog_seen_before) catalog_targets,
                count(*) FILTER(WHERE c.product_id IS NOT NULL) retrieved_targets,
                count(*) FILTER(WHERE c.from_popular) popular_targets,
                count(*) FILTER(WHERE c.from_recent) recent_targets,
                count(*) FILTER(WHERE l.pair_seen_before) repeat_targets,
                count(*) FILTER(WHERE l.pair_seen_before AND c.product_id IS NOT NULL) retrieved_repeat_targets,
                count(*) FILTER(WHERE NOT l.pair_seen_before) new_pair_targets,
                count(*) FILTER(WHERE NOT l.pair_seen_before AND c.product_id IS NOT NULL) retrieved_new_pair_targets
            FROM pilot_labels l LEFT JOIN pilot_candidates c USING(query_id,product_id) GROUP BY l.query_id)
        SELECT q.query_id,q.user_id,q.anchor,q.label_is_mature,
            coalesce(p.candidate_count,0) candidate_count,coalesce(p.popular_count,0) popular_count,
            coalesce(p.recent_count,0) recent_count,coalesce(p.overlap_count,0) overlap_count,
            CASE WHEN q.label_is_mature THEN coalesce(y.target_count,0) END target_count,
            CASE WHEN q.label_is_mature THEN coalesce(y.catalog_targets,0) END catalog_targets,
            CASE WHEN q.label_is_mature THEN coalesce(y.retrieved_targets,0) END retrieved_targets,
            y.popular_targets,y.recent_targets,y.repeat_targets,y.retrieved_repeat_targets,
            y.new_pair_targets,y.retrieved_new_pair_targets
        FROM pilot_queries q LEFT JOIN pool p USING(query_id) LEFT JOIN outcomes y USING(query_id)''')
    return _dict_rows(con.execute('''SELECT anchor,count(*) queries,
        count(*) FILTER(WHERE label_is_mature) mature_queries,
        count(*) FILTER(WHERE target_count>0) positive_queries,
        count(*) FILTER(WHERE candidate_count=0) empty_candidate_queries,
        sum(candidate_count)::BIGINT candidate_rows,min(candidate_count) min_candidates,
        avg(candidate_count) mean_candidates,max(candidate_count) max_candidates,
        sum(overlap_count)::BIGINT source_overlap_pairs,
        coalesce(sum(target_count),0)::BIGINT all_targets,
        coalesce(sum(catalog_targets),0)::BIGINT catalog_targets,
        coalesce(sum(retrieved_targets),0)::BIGINT retrieved_targets,
        coalesce(sum(popular_targets),0)::BIGINT popular_targets,
        coalesce(sum(recent_targets),0)::BIGINT recent_targets,
        avg(catalog_targets*1.0/nullif(target_count,0)) catalog_recall_positive_macro,
        avg(retrieved_targets*1.0/nullif(target_count,0)) candidate_recall_positive_macro,
        count(*) FILTER(WHERE label_is_mature AND retrieved_targets>0 AND retrieved_targets<candidate_count) informative_ranking_queries,
        coalesce(sum(repeat_targets),0)::BIGINT repeat_targets,
        coalesce(sum(retrieved_repeat_targets),0)::BIGINT retrieved_repeat_targets,
        coalesce(sum(new_pair_targets),0)::BIGINT new_pair_targets,
        coalesce(sum(retrieved_new_pair_targets),0)::BIGINT retrieved_new_pair_targets
        FROM pilot_coverage GROUP BY anchor ORDER BY anchor'''))


def build_candidates(con, config, *, stage=_direct_stage):
    result=create_candidates(con,config,stage=stage)
    verify_catalog(con,config,stage=stage)
    result['daily_coverage']=stage('coverage_after_generation',lambda:coverage_report(con))
    return result


def run(anchor_directory, output_root, *, seconds=1800):
    started=time.monotonic()
    deadline=RunDeadline(seconds,started_at=started)
    anchor_directory,output_root=anchor_directory.resolve(),output_root.resolve()
    anchor_manifest=load_run_manifest(anchor_directory/'run.json')
    anchor_report=json.loads((anchor_directory/'report.json').read_text())
    if anchor_report['status']!='complete' or anchor_report['run_id']!=anchor_manifest['run_id']:
        raise ValueError('Only complete matching anchor runs may supply Q/Y')
    config=anchor_manifest['identity']['protocol']
    output_root.relative_to(ROOT/'artifacts')
    source_hashes=anchor_manifest['identity']['input_hashes']
    if len(source_hashes)!=1:
        raise ValueError('Expected exactly one fingerprinted source DuckDB')
    source_name,source_hash=next(iter(source_hashes.items()))
    db=ROOT/source_name
    def fingerprint(path):
        deadline.check()
        digest=sha256_file(path)
        deadline.check()
        return digest
    if fingerprint(db)!=source_hash:
        raise ValueError('Source DB changed since anchor generation')
    files={name:ROOT/anchor_manifest['artifact_refs'][name] for name in ['queries','labels']}
    inputs={source_name:source_hash,**{path.relative_to(ROOT).as_posix():fingerprint(path)
        for path in [anchor_directory/'run.json',anchor_directory/'report.json',*files.values()]}}
    code={name:fingerprint(ROOT/name) for name in ['uv.lock','scripts/candidate_pilot.py',
        'scripts/anchor_pilot.py','scripts/protocol_manifest.py','scripts/temporal_contract.py']}
    manifest=build_run_manifest(config,code_hashes=code,input_hashes=inputs,components=[],artifact_refs={},
        created_at=datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'))
    directory=output_root/manifest['run_id']
    directory.mkdir(parents=True,exist_ok=False)
    temp=directory/'temp'
    temp.mkdir()
    con=duckdb.connect(str(db),read_only=True)
    ledger=StageLedger(temp,con,deadline)
    report={'status':'running','run_id':manifest['run_id'],'anchor_run_id':anchor_manifest['run_id'],
        'stages':ledger.rows,'protocol':config,'source_overlap_policy':'deduplicate_union_no_refill',
        'score_ties':'popular count desc then product_id asc; recent last time desc then product_id asc',
        'limits':{'threads':2,'duckdb_memory':'2GB','max_spill':'2GB','wall_seconds':seconds,'process_rss_ceiling_bytes':6*2**30}}
    timer=deadline.interrupt_timer(con)
    manifest['artifact_refs']['report']=(directory/'report.json').relative_to(ROOT).as_posix()
    try:
        deadline.check()
        con.execute('SET threads=2')
        con.execute("SET memory_limit='2GB'")
        con.execute("SET max_temp_directory_size='2GB'")
        con.execute('SET temp_directory=?',[str(temp)])
        con.execute('SET preserve_insertion_order=false')
        for table,name in [('pilot_queries','queries'),('pilot_labels','labels')]:
            deadline.check()
            con.execute(f'CREATE TEMP TABLE {table} AS SELECT * FROM read_parquet(?)',[str(files[name])])
        def guarded_stage(name,operation):
            deadline.check()
            result=ledger(name,operation)
            deadline.check()
            if peak_rss_bytes()>6*2**30:
                raise MemoryError('Process high-water RSS exceeded6GiB')
            return result
        report.update(build_candidates(con,config,stage=guarded_stage))
        for table,name in [('pilot_candidates','candidates'),('pilot_coverage','query_coverage')]:
            path=directory/(name+'.parquet')
            order='query_id,product_id' if table=='pilot_candidates' else 'query_id'
            guarded_stage('export_'+name,lambda table=table,path=path,order=order:con.execute(
                f'COPY (SELECT * FROM {table} ORDER BY {order}) TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(path)]))
            manifest['artifact_refs'][name]=path.relative_to(ROOT).as_posix()
        deadline.check()
        report['status']='complete'
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        timer.cancel()
        con.close()
        report.update(seconds=time.monotonic()-started,process_peak_rss_bytes=peak_rss_bytes(),temp_disk_bytes_after_close=directory_bytes(temp))
        save_json(directory/'report.json',report)
        write_run_manifest(manifest,directory/'run.json')
        print(json.dumps({'status':report['status'],'run_id':manifest['run_id'],'seconds':report['seconds'],
            'report':str(directory/'report.json')}),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--anchor-run',required=True,type=Path)
    parser.add_argument('--output-root',type=Path,default=ROOT/'artifacts/candidate-pilot')
    args=parser.parse_args()
    run(args.anchor_run,args.output_root)


if __name__=='__main__':
    main()
