import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts import ranking_metrics as evaluator
from scripts import replay_ranking_claim as r
FIXTURE=Path(__file__).resolve().parent/'fixtures/reproduction/manual18-small'
ENTRY=Path(r.__file__).resolve()

class ReplayTests(unittest.TestCase):
 def setUp(self):
  actual_getrusage=r.resource.getrusage
  def fresh_counter(which):
   if which==r.resource.RUSAGE_CHILDREN:return types.SimpleNamespace(ru_utime=0.,ru_stime=0.)
   return actual_getrusage(which)
  counter_patch=patch.object(r.resource,'getrusage',fresh_counter);counter_patch.start();self.addCleanup(counter_patch.stop)
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
  self.package=self.root/r.PUBLIC_PACKAGE;self.package.parent.mkdir(parents=True);shutil.copytree(FIXTURE,self.package)
  (self.root/'scripts').mkdir();self.source=self.root/'scripts/replay_ranking_claim.py';self.source.write_bytes(ENTRY.read_bytes())
  (self.root/'scripts/ranking_metrics.py').write_bytes(Path(evaluator.__file__).read_bytes())
  for obj,name,value in [(r,'ROOT',self.root),(r,'__file__',str(self.source)),(evaluator,'__file__',str(self.root/'scripts/ranking_metrics.py'))]:
   p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
  (self.root/'artifacts/reproduction/claims').mkdir(parents=True);self.args={}
 def manifest(self):return r.parse((self.package/'manifest.json').read_bytes())
 def rows(self,kind):return [r.parse(b) for b in (self.package/(kind+'.jsonl')).read_bytes().splitlines()]
 def save(self,kind,rows):
  raw=''.join(r.canonical(v)+'\n' for v in rows).encode();(self.package/(kind+'.jsonl')).write_bytes(raw)
  m=self.manifest();m['files'][kind].update(rows=len(rows),sha256=hashlib.sha256(raw).hexdigest());self.write_manifest(m)
 def write_manifest(self,m):
  raw=(json.dumps(m,sort_keys=True,indent=2)+'\n').encode();(self.package/'manifest.json').write_bytes(raw)
  return hashlib.sha256(raw).hexdigest()
 def private(self):
  m=self.manifest();m.update(stage='selection',query_range=dict(start='2019-10-22T00:00:00Z',end='2019-10-24T00:00:00Z'),label_available_before='2019-10-24T00:00:00Z',source_observed_until='2019-11-01T00:00:00Z');self.write_manifest(m)
  q=self.rows('queries')
  for x in q:x['anchor']='2019-10-23T00:00:00Z' if x['query_id']=='b' else '2019-10-22T00:00:00Z'
  self.save('queries',q);return self.authorize()
 def authorize(self):
  m=self.manifest();sha=hashlib.sha256((self.package/'manifest.json').read_bytes()).hexdigest();ref=dict(path=str((self.package/'manifest.json').relative_to(self.root)),sha256=sha)
  access=dict(version=1,scope='reviewed_train_selection_ranking_replay_access',approved=True,manifest=ref,stage=m['stage'],query_range=m['query_range'],permissions=dict(queries=True,candidates=True,targets=True,scores=True,confirmation=False,final=False))
  def write(path,value):
   raw=(r.canonical(value)+'\n').encode();(self.root/path).write_bytes(raw);return dict(path=path,sha256=hashlib.sha256(raw).hexdigest())
  ar=write('access.json',access)
  approval=dict(version=1,scope=r.ROLE,approved=True,manifest=ref,access=ar,code={n:hashlib.sha256((self.root/n).read_bytes()).hexdigest() for n in ['scripts/replay_ranking_claim.py','scripts/ranking_metrics.py']},limits=dict(cpu_seconds=300,wall_seconds=300,rss_bytes=512*2**20),claim_path='artifacts/reproduction/claims/once.json',allowed_replay_attempts=1,allowed_fit_attempts=0,allowed_native_predictions=0)
  br=write('budget.json',approval)
  self.args=dict(expected_manifest_sha=sha,access_contract=ar['path'],issued_access_sha=ar['sha256'],execution_approval=br['path'],issued_approval_sha=br['sha256'])
  return self.args
 def replay(self,**kwargs):return r.replay(str(self.package.relative_to(self.root)),**dict(self.args,**kwargs))
 def test_public_literal_four_estimands_bigint_ties_fullY_emptyC_no_writes(self):
  import math
  before=sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'));result=self.replay();after=sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'));self.assertEqual(before,after)
  m=result['metrics'];d=(1/math.log2(3))/(1+1/math.log2(3))
  for e,rec,ndcg,ap,rr in [('conditional_macro_query',.25,d/2,.125,.25),('all_query_zero',1/6,d/3,1/12,1/6),('conditional_user_macro',.25,d/2,.125,.25),('all_user_macro_zero',.125,d/4,.0625,.125)]:
   for key,v in [('recall',rec),('ndcg',ndcg),('average_precision',ap),('reciprocal_rank',rr)]:self.assertAlmostEqual(m[e][key],v)
  self.assertEqual(m['query_count'],3);self.assertEqual(m['positive_user_count'],1)
  self.assertEqual(result['counts'],dict(candidate_rows=3,target_rows=3,score_rows=3,empty_candidate_queries=1,targets_outside_candidates=2));self.assertEqual(result['native_prediction_count'],0)
 def test_private_anchored_package_once_consumed_before_stream(self):
  self.private();obj=r.Replay(str(self.package.relative_to(self.root)),**self.args);result=obj.run();self.assertIsNotNone(result['execution_consumed'])
  with patch.object(r.Rows,'__iter__',side_effect=AssertionError('repeat data read')):
   with self.assertRaises(FileExistsError):self.replay()
 def test_private_missing_anchor_or_authority_never_opens_rows(self):
  self.private();bad=dict(self.args);bad['expected_manifest_sha']=None;self.args=bad
  with patch.object(r.Rows,'__iter__',side_effect=AssertionError('unapproved rows read')):
   with self.assertRaises(ValueError):self.replay()
 def test_heldout_stage_and_disguised_range_closed_before_targets(self):
  self.private();m=self.manifest();m['stage']='final';self.write_manifest(m);self.authorize()
  with patch.object(r.Rows,'__iter__',side_effect=AssertionError('closed data read')):
   with self.assertRaises(ValueError):self.replay()
  m['stage']='selection';m['query_range']=dict(start='2019-10-25T00:00:00Z',end='2019-10-26T00:00:00Z');self.write_manifest(m);self.authorize()
  with patch.object(r.Rows,'__iter__',side_effect=AssertionError('disguised heldout data read')):
   with self.assertRaises(ValueError):self.replay()
 def test_bad_query_maturity_rejects_before_Y_open(self):
  self.private();m=self.manifest();m['label_available_before']='2019-10-23T00:00:00Z';self.write_manifest(m);self.authorize();seen=[];original=r.Rows.__iter__
  def rows(obj):seen.append(obj.kind);return original(obj)
  with patch.object(r.Rows,'__iter__',rows):
   with self.assertRaises(ValueError):self.replay()
  self.assertEqual(seen,['queries'])
 def test_prospective_censored_counter_not_fake_zero_targets(self):
  self.private();q=self.rows('queries');q[1]['label_is_mature']=False;self.save('queries',q);self.save('targets',[v for v in self.rows('targets') if v['query_id']!='b'])
  m=self.manifest();m['label_available_before']='2019-10-23T00:00:00Z';self.write_manifest(m);self.authorize();result=self.replay()
  self.assertEqual(result['metrics']['censored_query_count'],1);self.assertEqual(result['metrics']['mature_query_count'],2);self.assertEqual(result['metrics']['nonempty_query_count'],1)
 def test_fresh_resealed_duplicate_or_orphan_or_replaced_score_keys_reject(self):
  self.private();s=self.rows('scores');s[-1]['product_id']=5;self.save('scores',s);self.authorize()
  with self.assertRaises(ValueError):self.replay()
 def test_censored_query_with_target_is_rejected(self):
  self.private();q=self.rows('queries');q[1]['label_is_mature']=False;self.save('queries',q);m=self.manifest();m['label_available_before']='2019-10-23T00:00:00Z';self.write_manifest(m);self.authorize()
  with self.assertRaises(ValueError):self.replay()
 def test_duplicate_query_pair_NULL_and_nonfinite_rows_rejected(self):
  # Direct bounded Rows probes avoid creating >32 data rows or authorization
  # bypasses in the production entry.
  for kind,rows in [('queries',[self.rows('queries')[0]]*2),('candidates',[self.rows('candidates')[0]]*2),('targets',[dict(query_id='a',product_id=None)]),('scores',[dict(query_id='a',product_id=1,raw_score=True)])]:
   raw=''.join(r.canonical(v)+'\n' for v in rows).encode();p=self.root/'bad.jsonl';p.write_bytes(raw)
   with self.subTest(kind=kind),self.assertRaises(ValueError):list(r.Rows(p,kind,dict(rows=len(rows),sha256=hashlib.sha256(raw).hexdigest()),lambda:None))
  with self.assertRaises(ValueError):r.parse(b'{"raw_score":NaN}')
  with self.assertRaises(ValueError):r.parse(b'{"x":1,"x":2}')
 def test_runtime_code_drift_and_boolean_approval_reject_before_data(self):
  self.private();(self.root/'scripts/ranking_metrics.py').write_text('changed')
  with patch.object(r.Rows,'__iter__',side_effect=AssertionError('data read')):
   with self.assertRaises(ValueError):self.replay()
 def test_path_escape_and_mutated_synthetic_manifest_reject(self):
  m=self.manifest();m['files']['targets']['path']='../outside';self.write_manifest(m)
  with self.assertRaises(ValueError):self.replay()
  m['files']['targets']['path']='targets.jsonl';m['claim_metrics']={};self.write_manifest(m)
  with self.assertRaises(ValueError):self.replay()
 def test_exclusive_evidence_and_late_failure_marker(self):
  output='evidence.json';result=self.replay(evidence_out=output);self.assertEqual(r.parse((self.root/output).read_bytes()),result)
  with self.assertRaises(ValueError):self.replay(evidence_out=output)
  (self.root/output).unlink();original=r.exclusive
  def write(path,body):
   value=original(path,body)
   if path.name=='evidence.json':path.with_suffix('.failed.json').write_text('{}')
   return value
  with patch.object(r,'exclusive',write):
   with self.assertRaises(ValueError):self.replay(evidence_out=output)
 def test_terminal_close_cap_and_secondary_error_preserve_failure(self):
  obj=r.Replay(str(self.package.relative_to(self.root)),evidence_out='close.json');original=r.Rows.close
  def close(stream):original(stream);obj.budget.deadline=0
  with patch.object(r.Rows,'close',close):
   with self.assertRaises(TimeoutError):obj.run()
  self.assertFalse((self.root/'close.json').exists());self.assertTrue((self.root/'close.failed.json').exists())
 def test_failed_private_claim_remains_and_cannot_refill(self):
  self.private();s=self.rows('scores');s[-1]['query_id']='orphan';self.save('scores',s);self.authorize()
  with self.assertRaises(ValueError):self.replay()
  self.assertTrue((self.root/'artifacts/reproduction/claims/once.json').exists())
  with self.assertRaises(FileExistsError):self.replay()



 def test_strict_budget_bool_counters_reject_before_rows(self):
  self.private();p=self.root/self.args['execution_approval'];b=r.parse(p.read_bytes());b['allowed_replay_attempts']=True
  raw=(r.canonical(b)+'\n').encode();p.write_bytes(raw);self.args['issued_approval_sha']=hashlib.sha256(raw).hexdigest()
  with patch.object(r.Rows,'__iter__',side_effect=AssertionError('rows opened')):
   with self.assertRaises(ValueError):self.replay()
 def test_close_CPU_RSS_or_cleanup_error_never_writes_success(self):
  original=r.Rows.close
  for mode,expected in [('CPU',TimeoutError),('RSS',MemoryError),('close',OSError)]:
   obj=r.Replay(str(self.package.relative_to(self.root)),evidence_out=mode+'.json')
   def close(stream):
    original(stream)
    if mode=='CPU':obj.budget.cpu=lambda:301
    elif mode=='RSS':obj.budget.rss=lambda:512*2**20+1
    else:raise OSError('cleanup')
   with self.subTest(mode=mode),patch.object(r.Rows,'close',close):
    with self.assertRaises(expected):obj.run()
    self.assertFalse((self.root/(mode+'.json')).exists())
 def test_primary_body_error_survives_secondary_cleanup_failure(self):
  self.private();s=self.rows('scores');s[-1]['product_id']=5;self.save('scores',s);self.authorize();original=r.Rows.close
  def close(stream):original(stream);raise OSError('secondary cleanup')
  with patch.object(r.Rows,'close',close):
   with self.assertRaisesRegex(ValueError,'exact_C_score_key_multiset'):self.replay()



 def test_unknown_nonfinite_CPU_or_RSS_cannot_yield_verified_result(self):
  for used,peak in [(float('nan'),1),(-1.,1),(0.,0),(0.,True)]:
   obj=r.Replay(str(self.package.relative_to(self.root)))
   with self.subTest(used=used,peak=peak),patch.object(obj.budget,'cpu',return_value=used),patch.object(obj.budget,'rss',return_value=peak):
    with self.assertRaises(ValueError):obj.run()



 def test_close_mutates_manifest_rejected_without_evidence(self):
  obj=r.Replay(str(self.package.relative_to(self.root)));original=r.Rows.close;done=[False]
  def close(stream):
   original(stream)
   if not done[0]:
    done[0]=True;p=self.package/'manifest.json';p.write_bytes(p.read_bytes()+b' ')
  with patch.object(r.Rows,'close',close):
   with self.assertRaisesRegex(ValueError,'authority_changed'):obj.run()
 def test_close_mutates_scores_rejected_before_evidence_write(self):
  obj=r.Replay(str(self.package.relative_to(self.root)),evidence_out='terminal.json');original=r.Rows.close;done=[False]
  def close(stream):
   original(stream)
   if not done[0]:
    done[0]=True;p=self.package/'scores.jsonl';p.write_bytes(p.read_bytes()+b' ')
  with patch.object(r.Rows,'close',close):
   with self.assertRaisesRegex(ValueError,'data_changed'):obj.run()
  self.assertFalse((self.root/'terminal.json').exists())



 def test_positive_or_unknown_child_counter_is_rejected(self):
  previous=r.resource.getrusage
  for value in (1.,float('nan')):
   def bad(which):
    if which==r.resource.RUSAGE_CHILDREN:return types.SimpleNamespace(ru_utime=value,ru_stime=0.)
    return previous(which)
   with self.subTest(value=value),patch.object(r.resource,'getrusage',bad):
    with self.assertRaises(ValueError):r.Budget().guard()
 def test_fresh_fixture_isolates_and_restores_outer_reaped_counter(self):
  previous=r.resource.getrusage
  def outer(which):
   if which==r.resource.RUSAGE_CHILDREN:return types.SimpleNamespace(ru_utime=9.,ru_stime=1.)
   return previous(which)
  with patch.object(r.resource,'getrusage',outer):
   helper=ReplayTests('test_public_literal_four_estimands_bigint_ties_fullY_emptyC_no_writes');helper.setUp()
   try:
    self.assertEqual(r.resource.getrusage(r.resource.RUSAGE_CHILDREN).ru_utime,0.)
    self.assertGreater(r.Budget().cpu(),0.)
    self.assertGreater(r.Budget().rss(),0)
   finally:helper.doCleanups()
   self.assertEqual(r.resource.getrusage(r.resource.RUSAGE_CHILDREN).ru_utime,9.)

if __name__=='__main__':unittest.main()
