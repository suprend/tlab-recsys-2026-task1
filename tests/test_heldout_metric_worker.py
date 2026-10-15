"""Three synthetic raw rows; transport/lifecycle tests, no private Y or ML."""
from copy import deepcopy
from datetime import datetime,timedelta
import json,random
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import duckdb,numpy as np
from scripts import heldout_contract as h
from tests.oracles import heldout_metric_audit as core
from tests import test_heldout_prediction_worker as pred
fixtures=pred.fixtures
from tests.oracles import heldout_metric_worker as m

class MetricFixture(pred.PredictionFixture):
 def __init__(self,root):
  super().__init__(root);ref=self.write('fixture/prediction-proof.json',dict(synthetic=True));life=self.write('fixture/prediction-life.json',dict(synthetic=True))
  inventory=dict(version=1,scope='all_reserved_predictions_before_targets',decision_lock_sha256=h.digest(self.lock),created_at=self.prediction['created_at'],source_acceptance=self.refs['source_acceptance'],days=deepcopy(self.prediction['days']),output_verification=ref,lifetime_receipt=life,heldout_targets_opened=False)
  self.refs['prediction_inventory']=self.write('fixture/prediction-inventory.json',inventory)
  sealat=(h.utc(self.lock['sealed_at'])+timedelta(seconds=3)).strftime('%Y-%m-%dT%H:%M:%SZ');self.refs['prediction_acceptance']=self.write('fixture/prediction-acceptance.json',dict(approved=True,scope='reviewed_all_reserved_predictions_before_targets',run_id=self.run,inventory=self.refs['prediction_inventory'],sealed_at=sealat,fingerprints=dict(self.pins)))
  policy=dict(prediction_acceptance=self.refs['prediction_acceptance'],prediction_inventory_sha256=h.digest(inventory),decision_lock_sha256=h.digest(self.lock),periods=['confirmation25_reporting_only','final26_31_frozen'],no_adaptation=True,earliest_opened_at=sealat);self.refs['target_policy']=self.write('fixture/target-policy.json',policy)
  targetat=(h.utc(self.lock['sealed_at'])+timedelta(seconds=4)).strftime('%Y-%m-%dT%H:%M:%SZ');self.refs['target_execution']=self.write('fixture/target-execution.json',dict(approved=True,scope='report_only_reserved_fullY',run_id=self.run,target_policy=self.refs['target_policy'],sealed_at=targetat,fingerprints=dict(self.pins)))
  intent=dict(version=1,scope='report_only_reserved_fullY',**{k:policy[k] for k in ['prediction_acceptance','prediction_inventory_sha256','decision_lock_sha256','periods','no_adaptation']},opened_at=(h.utc(self.lock['sealed_at'])+timedelta(seconds=5)).strftime('%Y-%m-%dT%H:%M:%SZ'))
  days=[];epoch=datetime(1970,1,1)
  for day in inventory['days']:
   with np.load(root/day['predictions']['B']['artifact']['path'],allow_pickle=False) as z:
    queries=[(str(q),int(u),epoch+timedelta(microseconds=int(t))) for q,u,t in zip(z['query_ids'],z['user_ids'],z['anchors'])];days.append(dict(anchor=day['anchor'],queries=queries,calendar_maturity=z['calendar_maturity'],group=z['group'],items=z['items'],scores={'B':z['scores'],'W':z['scores']}))
  con=duckdb.connect(str(root/self.refs['source']['path']),read_only=True);con.execute('SET threads=2');con.execute('CREATE TEMP VIEW heldout_raw_events AS SELECT * FROM events')
  try:full=core.raw_targets(con,[q for d in days for q in d['queries']],lambda:None)
  finally:con.close()
  periods={};rankings={}
  # Author synthetic artifacts only. Core formula correctness is separately accepted;
  # these adapter tests exercise byte/domain/stage/private-output plumbing.
  for name,selected in [('confirmation25_reporting_only',days[:1]),('final26_31_frozen',days[1:])]:
   rows,support=core.ranked_rows(selected,full,lambda:None);metrics={s:core.evaluation(rows[s]) for s in ('B','W')};users=list(core.user_groups(rows['W']));rng=random.Random(2026);draws=[rng.choices(users,k=len(users)) for _ in range(200)]
   periods[name]=dict(anchors=[d['anchor'] for d in selected],metrics=metrics,ndcg_W_minus_B={e:0.0 if metrics['B'][e]['ndcg'] is not None else None for e in core.ESTIMANDS},paired_user_bootstrap={e:core.bootstrap(rows['W'],rows['B'],e,draws,lambda:None) for e in core.ESTIMANDS},support=support);rankings[name]=rows
  name=self.directory+'/targets_evaluation/full-targets.parquet';path=root/name;path.parent.mkdir(parents=True,exist_ok=True);con=duckdb.connect(':memory:');con.execute('CREATE TABLE targets(query_id VARCHAR,product_id BIGINT)');pairs=[(q,i) for q,items in full.items() for i in items]
  try:
   if pairs:con.executemany('INSERT INTO targets VALUES (?,?)',pairs)
   con.execute("COPY targets TO '"+str(path)+"' (FORMAT PARQUET)")
  finally:con.close()
  targetref=self.reference(name);name=self.directory+'/targets_evaluation/private-rankings.jsonl';path=root/name
  with path.open('w') as stream:
   for period in ('confirmation25_reporting_only','final26_31_frozen'):
    for side in ('B','W'):
     for row in rankings[period][side]:stream.write(json.dumps(dict(period=period,role=side,query_id=row['query_id'],user_id=row['user_id'],ranked_items=list(row['ordered']),targets=sorted(row['targets']),mature=True))+'\n')
  rankingref=self.reference(name);outputs={targetref['path']:targetref['sha256'],rankingref['path']:rankingref['sha256']}
  body=dict(version=1,scope='unaccepted_reserved_fullY_reporting',run_id=self.run,decision_lock=self.refs['lock'],choice=self.refs['choice'],source_acceptance=self.refs['source_acceptance'],source_manifest=self.refs['source_manifest'],prediction_acceptance=self.refs['prediction_acceptance'],prediction_inventory=self.refs['prediction_inventory'],target_execution=self.refs['target_execution'],target_policy=self.refs['target_policy'],actual_target_intent=intent,target_stage_opened_at=intent['opened_at'],target_stage_started_monotonic=1.0,fullY_started_at=intent['opened_at'],fullY_started_monotonic=1.01,periods=periods,private_outputs={'targets':targetref,'rankings':rankingref},outputs=outputs,labels_loaded=True,fit_attempt_count=0,native_prediction_count=0,environment={'synthetic_versions':True})
  self.evaluation=body;self.refs['evaluation_manifest']=self.write(self.directory+'/targets_evaluation/evaluation.json',body);allout=dict(outputs);allout[self.refs['evaluation_manifest']['path']]=self.refs['evaluation_manifest']['sha256']
  self.refs['evaluation_receipt']=self.write(self.directory+'/targets_evaluation/receipt.json',dict(status='role_complete_unaccepted',scope='reserved_reporting_targets_evaluation',role='targets_evaluation',run_id=self.run,inputs={k:self.refs[k] for k in ['lock','choice','source_acceptance','source_manifest','prediction_acceptance','prediction_inventory','target_policy']},outputs=allout,labels_loaded=True,fit_attempt_count=0,native_prediction_count=0))

class MetricWorker(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);p=patch.object(m,'ROOT',self.root);p.start();self.addCleanup(p.stop);self.f=MetricFixture(self.root);self.r=fixtures.FakeRole(self.f,m,'metric_oracle')
 def changed_evaluation(self):
  self.f.refs['evaluation_manifest']=self.f.write(self.f.refs['evaluation_manifest']['path'],self.f.evaluation);self.r=fixtures.FakeRole(self.f,m,'metric_oracle')
 def test_tiny_all7_fullY_four_estimands_and_private_rankings_core(self):
  result=m.perform(self.r);self.assertTrue(result['labels_loaded']);self.assertEqual(result['native_prediction_count'],0);e=json.loads((self.root/result['evidence']['path']).read_text());self.assertEqual(e['core']['fullY_pairs'],1)
  self.assertNotIn('private_targets',e['core']);self.assertNotIn('private_rankings',e['core']);self.assertGreater(e['core']['private_ranking_rows_checked'],0)
  self.assertGreaterEqual(e['core']['oracle_fullY_started_monotonic'],e['core']['oracle_target_stage_started_monotonic'])
  self.assertEqual(set(e),{'version','scope','run_id','context','execution_consumed','decision_lock','choice','inputs','core','environment'})
 def test_bad_actual_intent_stops_BEFORE_target_artifact_or_source_connection(self):
  self.f.evaluation['actual_target_intent']['opened_at']=self.f.lock['sealed_at'];self.changed_evaluation()
  with patch.object(m,'open_connection',side_effect=AssertionError('too early source/targets')),self.assertRaises(ValueError):m.perform(self.r)
  self.assertFalse(self.r.finished)
 def test_producer_fullY_clock_before_admission_rejects_before_SQL(self):
  self.f.evaluation['fullY_started_monotonic']=.5;self.changed_evaluation()
  with patch.object(m,'open_connection',side_effect=AssertionError('too early SQL')),self.assertRaisesRegex(ValueError,'monotonic chronology'):m.perform(self.r)
 def test_changed_saved_source_keys_rejected_BEFORE_producedY_read(self):
  day=self.f.prediction['days'][0];ref=day['predictions']['B']['artifact'];path=self.root/ref['path']
  with np.load(path,allow_pickle=False) as z:arrays={k:z[k] for k in z.files}
  arrays['user_ids'][0]+=1;np.savez(path,**arrays)
  # Original sealed NPZ pin blocks before target stage (not a data oracle claim).
  with self.assertRaises(ValueError):m.perform(self.r)
  self.assertFalse(self.r.finished)
 def test_private_ranking_wrong_exactID_or_extra_row_rejects(self):
  ref=self.f.evaluation['private_outputs']['rankings'];path=self.root/ref['path'];rows=path.read_text().splitlines();first=json.loads(rows[0]);first['user_id']=0;rows[0]=json.dumps(first);path.write_text('\n'.join(rows)+'\n')
  ref=self.f.reference(ref['path']);self.f.evaluation['private_outputs']['rankings']=ref;self.f.evaluation['outputs'][ref['path']]=ref['sha256'];self.f.refs['evaluation_manifest']=self.f.write(self.f.refs['evaluation_manifest']['path'],self.f.evaluation)
  receipt=json.loads((self.root/self.f.refs['evaluation_receipt']['path']).read_text());receipt['outputs'][ref['path']]=ref['sha256'];receipt['outputs'][self.f.refs['evaluation_manifest']['path']]=self.f.refs['evaluation_manifest']['sha256'];self.f.refs['evaluation_receipt']=self.f.write(self.f.refs['evaluation_receipt']['path'],receipt);self.r=fixtures.FakeRole(self.f,m,'metric_oracle')
  with self.assertRaisesRegex(ValueError,'private-ranking'):m.perform(self.r)
 def test_bad_fullY_source_value_not_merely_freshhash_rejects(self):
  ref=self.f.evaluation['private_outputs']['targets'];path=self.root/ref['path'];con=duckdb.connect(':memory:')
  try:con.execute('CREATE TABLE t AS SELECT * FROM read_parquet(?)',[str(path)]);con.execute('UPDATE t SET product_id=42');con.execute("COPY t TO '"+str(path)+"' (FORMAT PARQUET,OVERWRITE_OR_IGNORE)")
  finally:con.close()
  ref=self.f.reference(ref['path']);self.f.evaluation['private_outputs']['targets']=ref;self.f.evaluation['outputs'][ref['path']]=ref['sha256'];self.f.refs['evaluation_manifest']=self.f.write(self.f.refs['evaluation_manifest']['path'],self.f.evaluation)
  receipt=json.loads((self.root/self.f.refs['evaluation_receipt']['path']).read_text());receipt['outputs'][ref['path']]=ref['sha256'];receipt['outputs'][self.f.refs['evaluation_manifest']['path']]=self.f.refs['evaluation_manifest']['sha256'];self.f.refs['evaluation_receipt']=self.f.write(self.f.refs['evaluation_receipt']['path'],receipt);self.r=fixtures.FakeRole(self.f,m,'metric_oracle')
  with self.assertRaisesRegex(ValueError,'raw fullY mismatch'):m.perform(self.r)

if __name__=='__main__':unittest.main()
