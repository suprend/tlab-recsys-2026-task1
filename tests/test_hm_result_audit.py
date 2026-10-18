"""Independent witnesses for exported H&M metrics; no model training/prediction."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import hm_result_audit as audit


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


def fixture(root,heuristic_ranks=False):
    """Hand-enumerated Q/C/Y and two saved scorers; fake model bytes never loaded."""
    import duckdb
    validation=root/'validation';validation.mkdir()
    database=root/'source.duckdb'
    source=duckdb.connect(str(database))
    source.execute('CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR)')
    source.execute("""INSERT INTO transactions VALUES ('2020-09-01','u1','a'),('2020-09-01','u2','c'),
        ('2020-09-02','u1','a'),('2020-09-03','u1','off-C'),('2020-09-09','u2','right-boundary-excluded')""")
    source.close()
    con=duckdb.connect(':memory:')
    def parquet(name,sql,folder=validation):
        con.sql(sql).write_parquet(str(folder/name))
    parquet('users.parquet',"SELECT u customer_id,sha256(u || ':2026') cohort_hash,2::INTEGER full_candidate_count FROM (VALUES ('u1'),('u2')) t(u) ORDER BY cohort_hash")
    parquet('targets.parquet',"SELECT * FROM (VALUES ('u1','a'),('u1','off-C')) t(customer_id,article_id) ORDER BY customer_id,article_id")
    frame="SELECT *,2::INTEGER full_candidate_count,.5::DOUBLE query_weight FROM (VALUES ('u1','a',true),('u1','b',false),('u2','c',false),('u2','d',false)) t(customer_id,article_id,label)"
    if heuristic_ranks:
        frame="""SELECT *,CASE WHEN article_id IN ('a','c') THEN 2 ELSE 1 END AS global_rank,
            CASE WHEN article_id='a' THEN 1 WHEN article_id='b' THEN 2 ELSE 21 END AS user_recent_rank
            FROM ("""+frame+')'
    parquet('frame.parquet',frame)
    code={'hm_result_audit.py':hash_file(Path(audit.__file__))}
    files={name:hash_file(validation/name) for name in ('frame.parquet','users.parquet','targets.parquet')}
    candidate_digest=hashlib.sha256()
    for user,article in [('u1','a'),('u1','b'),('u2','c'),('u2','d')]:
        for value in (user,article):
            value=value.encode();candidate_digest.update(len(value).to_bytes(4,'big'));candidate_digest.update(value)
    canonical=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    manifest=dict(format='hm-experiment-collection-v1',status='completed',anchor='2020-09-02',horizon_days=7,
                  cohort_seed=2026,requested_users=2,policy='C0-Q120',code=code,files=files,
                  database={'sha256':hash_file(database),'bytes':database.stat().st_size},features={'digest':'fixture'},
                  candidate_identity=candidate_digest.hexdigest(),qcy_identity=canonical({k:files[k] for k in ('users.parquet','targets.parquet')}))
    write_json(validation/'manifest.json',manifest)
    inputs=[{'anchor':'2020-08-26','manifest_sha256':'0'*64,'qcy_identity':'1'*64,'candidate_identity':'2'*64},
            {'anchor':manifest['anchor'],'manifest_sha256':hash_file(validation/'manifest.json'),
             'qcy_identity':manifest['qcy_identity'],'candidate_identity':manifest['candidate_identity']}]
    metrics=dict(queries=2,positive_queries=1,empty_target_queries=1,map_at_12_conditional=.5,recall_at_12_conditional=.5,
                 map_at_12_all_queries_empty_zero=.25,recall_at_12_all_queries_empty_zero=.25,
                 candidate_query_coverage_conditional=1.,candidate_target_coverage_micro=.5,
                 oracle_map_at_12_conditional=.5,distinct_query_target_pairs=2)
    fits=[]
    for index in range(2):
        folder=root/f'fit-{index}';folder.mkdir();fits.append(folder)
        predictions="SELECT * FROM (VALUES ('u1','a',1,.9),('u1','b',2,.8),('u2','c',1,.7),('u2','d',2,.6)) t(customer_id,article_id,rank,score)"
        ap=.5
        if index:
            predictions="SELECT * FROM (VALUES ('u1','b',1,.9),('u1','a',2,.8),('u2','c',1,.7),('u2','d',2,.6)) t(customer_id,article_id,rank,score)"
            ap=.25
        parquet('predictions-top12.parquet',predictions,folder)
        parquet('query-metrics.parquet',f"SELECT * FROM (VALUES ('u1',2,2,1,1,{ap},.5,.5),('u2',0,2,0,0,0.,0.,0.)) t(customer_id,targets,candidate_count,hits12,covered,ap12,recall12,oracle_ap12)",folder)
        (folder/'model.cbm').write_bytes(b'never parsed or predicted')
        fit_metrics=dict(metrics,map_at_12_conditional=ap,map_at_12_all_queries_empty_zero=ap/2)
        report=dict(format='hm-experiment-fit-v1',status='completed',fit_count=1,actual_trees=150,
                    inputs=inputs,features={'numeric':['x'],'categorical':[],'contract_digest':'fixture'},
                    hyperparameters={'iterations':150},training_user_limit=2,negative_sample=0,sampling_seed=2026,
                    code=code,runtime={},files={name:hash_file(folder/name) for name in ('model.cbm','query-metrics.parquet','predictions-top12.parquet')},
                    validation_metrics=fit_metrics,validation_population={'selected_queries':2,'full_candidate_rows':4,'target_pairs':2})
        report['fit_identity']=canonical(dict(inputs=inputs,features=report['features'],hyperparameters=report['hyperparameters'],
            train_users=2,negative_sample=0,sampling_seed=2026,code=code,runtime={}))
        write_json(folder/'report.json',report)
    con.close()
    return validation,fits,database


class QueryMetricTests(unittest.TestCase):
    def test_full_truth_offcandidate_and_no_purchase_denominators(self):
        positive=audit.evaluate_query([('01',1,.9),('02',2,.1)],{'01','outside'},2,1)
        empty=audit.evaluate_query([('x',1,.2)],set(),1,0)
        self.assertEqual(positive['ap12'],.5)
        self.assertEqual(positive['recall12'],.5)
        self.assertEqual(positive['oracle_ap12'],.5)
        total=audit.aggregate_queries({'p':positive,'empty':empty})
        self.assertEqual(total['map_at_12_conditional'],.5)
        self.assertEqual(total['map_at_12_all_queries_empty_zero'],.25)
        self.assertEqual(total['candidate_target_coverage_micro'],.5)
        self.assertEqual(total['queries'],2)

    def test_precision_uses_hit_positions_and_k_capped_full_truth(self):
        rows=[('a',1,3.),('b',2,2.),('c',3,1.)]
        metric=audit.evaluate_query(rows,{'a','c','outside'},3,2)
        self.assertAlmostEqual(metric['ap12'],(1+2/3)/3)
        truth={f'{i:02d}' for i in range(20)}
        pred=[(f'{i:02d}',i+1,20-i) for i in range(12)]
        self.assertEqual(audit.evaluate_query(pred,truth,20,20)['ap12'],1)

    def test_ties_require_string_article_order(self):
        self.assertEqual(audit.evaluate_query([('01',1,.1),('02',2,.1)],{'01'},2,1)['ap12'],1)
        with self.assertRaisesRegex(ValueError,'ordering'):
            audit.evaluate_query([('02',1,.1),('01',2,.1)],{'01'},2,1)

    def test_duplicate_rank_gap_nonfinite_and_incomplete_predictions_rejected(self):
        for rows in ([('01',1,.2),('01',2,.1)],[('01',1,.2),('02',3,.1)],
                     [('01',1,float('nan')),('02',2,.1)],[('01',1,.2)]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):
                audit.evaluate_query(rows,{'01'},2,1)

    def test_export_and_query_identity_mismatch_are_rejected(self):
        values={'u':audit.evaluate_query([('a',1,1)],{'a','off'},1,1)}
        audit.check_export(values,copy.deepcopy(values))
        bad=copy.deepcopy(values);bad['u']['ap12']=1
        with self.assertRaisesRegex(ValueError,'disagree'):
            audit.check_export(values,bad)
        with self.assertRaisesRegex(ValueError,'complete Q'):
            audit.check_export(values,{})

    def test_paired_bootstrap_is_deterministic_positive_user_only(self):
        a={'p':{'targets':2,'ap12':.1},'q':{'targets':1,'ap12':.4},'empty':{'targets':0,'ap12':0}}
        b={'p':{'targets':2,'ap12':.3},'q':{'targets':1,'ap12':.6},'empty':{'targets':0,'ap12':0}}
        result=audit.paired_bootstrap(a,b)
        self.assertEqual(result,audit.paired_bootstrap(a,b))
        self.assertEqual(result['queries'],2)
        self.assertAlmostEqual(result['mean_delta'],.2)
        for bound in result['percentile_95']:
            self.assertAlmostEqual(bound,.2)
        with self.assertRaisesRegex(ValueError,'identical users'):
            audit.paired_bootstrap(a,{'p':b['p']})

    def test_no_positive_queries_produce_explicit_null_uncertainty(self):
        result=audit.paired_bootstrap({'e':{'targets':0,'ap12':0}},{'e':{'targets':0,'ap12':0}})
        self.assertIsNone(result['mean_delta'])
        self.assertIsNone(result['percentile_95'])

    def test_output_collision_and_outside_artifacts_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'artifacts'):
                audit.audit(Path(temp)/'missing',[],Path(temp)/'new')
        with tempfile.TemporaryDirectory(dir=audit.ROOT/'artifacts') as temp:
            with self.assertRaises(FileExistsError):
                audit.audit(Path(temp)/'missing',[],Path(temp))


class SavedArtifactTests(unittest.TestCase):
    def test_optional_heuristics_exact_scores_fullY_and_same_query_comparisons(self):
        import duckdb
        with tempfile.TemporaryDirectory(dir=audit.ROOT/'artifacts') as temp:
            root=Path(temp)
            validation,fits,_=fixture(root,heuristic_ranks=True)
            con=duckdb.connect(':memory:')
            try:
                recency=audit.heuristic_predictions(con,validation/'frame.parquet','recency',audit.Deadline(30))
                popularity=audit.heuristic_predictions(con,validation/'frame.parquet','popularity',audit.Deadline(30))
                self.assertEqual(recency['u1'],[('a',1,-1002.),('b',2,-2001.)])
                self.assertEqual(popularity['u1'],[('b',1,-1002.),('a',2,-2001.)])
                # Equal recency fallback21 resolves by global rank.
                self.assertEqual(recency['u2'],[('d',1,-21001.),('c',2,-21002.)])
                tied=root/'tied.parquet'
                con.sql("SELECT * FROM (VALUES ('u','02',1,21),('u','01',1,21)) t(customer_id,article_id,global_rank,user_recent_rank)").write_parquet(str(tied))
                for method in ('recency','popularity'):
                    self.assertEqual([row[0] for row in audit.heuristic_predictions(con,tied,method,audit.Deadline(30))['u']],['01','02'])
            finally:
                con.close()
            report=audit.audit(validation,fits,root/'audit',wall_seconds=30)
            self.assertEqual(report['heuristics']['status'],'evaluated')
            recent=report['heuristics']['recency']['metrics']
            popular=report['heuristics']['popularity']['metrics']
            self.assertEqual(recent['queries'],2)
            self.assertEqual(recent['distinct_query_target_pairs'],2)
            self.assertEqual(recent['map_at_12_conditional'],.5)
            self.assertEqual(popular['map_at_12_conditional'],.25)
            self.assertEqual(recent['map_at_12_all_queries_empty_zero'],.25)
            self.assertEqual(report['fit_vs_recency'][0]['mean_delta'],0.)
            self.assertEqual(report['fit_vs_recency'][1]['mean_delta'],-.25)
            exported=report['heuristics']['recency']['private_query_metrics']
            self.assertEqual(hash_file(root/'audit'/exported['file']),exported['sha256'])

    def test_null_cached_user_denominators_rejected_after_valid_identity_updates(self):
        import duckdb
        with tempfile.TemporaryDirectory(dir=audit.ROOT/'artifacts') as temp:
            root=Path(temp)
            validation,fits,database=fixture(root)
            con=duckdb.connect(':memory:')
            replacement=root/'null-user-counts.parquet'
            con.execute('CREATE TEMP TABLE input_users AS SELECT * FROM read_parquet(?)',
                        [str(validation/'users.parquet')])
            con.sql('''SELECT customer_id,cohort_hash,NULL::INTEGER AS full_candidate_count
                FROM input_users''').write_parquet(str(replacement))
            con.close()
            (validation/'users.parquet').write_bytes(replacement.read_bytes())
            manifest=json.loads((validation/'manifest.json').read_text(encoding='utf-8'))
            manifest['files']['users.parquet']=hash_file(validation/'users.parquet')
            manifest['qcy_identity']=audit.canonical_digest({k:manifest['files'][k] for k in ('users.parquet','targets.parquet')})
            write_json(validation/'manifest.json',manifest)
            for folder in fits:
                report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
                report['inputs'][-1].update(manifest_sha256=hash_file(validation/'manifest.json'),
                                            qcy_identity=manifest['qcy_identity'])
                report['fit_identity']=audit.canonical_digest(dict(inputs=report['inputs'],features=report['features'],
                    hyperparameters=report['hyperparameters'],train_users=report['training_user_limit'],
                    negative_sample=report['negative_sample'],sampling_seed=report['sampling_seed'],
                    code=report['code'],runtime=report['runtime']))
                write_json(folder/'report.json',report)
            with self.assertRaisesRegex(ValueError,'represent every full query'):
                audit.audit(validation,fits,root/'audit',database,30)
            saved=json.loads((root/'audit/report.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['status'],'FAIL')
            self.assertEqual(saved['error']['check'],'Candidate rows must represent every full query')

    def test_full_saved_artifacts_source_rebuild_and_paired_comparison(self):
        with tempfile.TemporaryDirectory(dir=audit.ROOT/'artifacts') as temp:
            root=Path(temp)
            validation,fits,database=fixture(root)
            report=audit.audit(validation,fits,root/'audit',database,30)
            self.assertEqual(report['status'],'PASS')
            self.assertEqual(report['heuristics']['status'],'unavailable')
            self.assertEqual(report['fit_vs_recency'],[])
            self.assertTrue(report['source_rebuild'].startswith('PASS'))
            self.assertEqual(report['fits'][0]['metrics']['map_at_12_conditional'],.5)
            self.assertEqual(report['comparisons'][0]['mean_delta'],-.25)
            self.assertEqual(report['comparisons'][0]['percentile_95'],[-.25,-.25])
            self.assertTrue((root/'audit/arm-00-query-metrics.parquet').exists())

    def test_inconsistent_saved_metric_is_rejected_even_with_matching_file_hash(self):
        import duckdb
        with tempfile.TemporaryDirectory(dir=audit.ROOT/'artifacts') as temp:
            root=Path(temp)
            validation,fits,_=fixture(root)
            con=duckdb.connect(':memory:')
            wrong=root/'wrong.parquet'
            con.sql("SELECT * FROM (VALUES ('u1',2,2,1,1,1.,.5,.5),('u2',0,2,0,0,0.,0.,0.)) t(customer_id,targets,candidate_count,hits12,covered,ap12,recall12,oracle_ap12)").write_parquet(str(wrong))
            con.close()
            # Replace only this owned synthetic file, then update its integrity hash.
            destination=fits[0]/'query-metrics.parquet'
            destination.write_bytes(wrong.read_bytes())
            report=json.loads((fits[0]/'report.json').read_text(encoding='utf-8'))
            report['files']['query-metrics.parquet']=hash_file(destination)
            write_json(fits[0]/'report.json',report)
            with self.assertRaisesRegex(ValueError,'per-query metrics disagree'):
                audit.audit(validation,[fits[0]],root/'audit',wall_seconds=30)
            self.assertEqual(json.loads((root/'audit/report.json').read_text())['status'],'FAIL')


if __name__=='__main__':
    unittest.main()
