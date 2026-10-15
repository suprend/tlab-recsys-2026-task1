# Historical438 choice consumer and external admission audit

15 October 2026. Thirteen unique synthetic consumer cases PASS; actual bounded metadata stopped intentionally before first438-pin stream, no successful full authentication/native model/large input bytes. Original SHA256 below, local temporary/home roots sanitized only for publication. The external model admission script is audit material, not a rerunnable approval command: exclusive historical output paths already exist. Initial wrong arm outcome assertion stopped before any seal and was corrected to the exact accepted arm_complete schema; no producer/observer/fit was repeated. Both admission attempts and terminal tail are covered by declared10CPU upper, not described as exact measured initial CPU.

## tlab-model-choice-consumer-author-independent.log

Original SHA256 5e616bfb40387e583f02c4f4ab58d6b2e03276d2058e19621ee88386ce2426b9.

```text
..........
----------------------------------------------------------------------
Ran 10 tests in 0.774s

OK
```

## tlab-model-choice-consumer-independent.py

Original SHA256 82263c6a855cf9f7b8612a5a3df95c421df1c66ea6da067611c498cd0a4957b7.

```python
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,'<repository>')
from tests.test_feature_program_control import ChoiceConsumer as Fixture
from scripts import feature_program_control as c
class Independent(unittest.TestCase):
 def setUp(self):
  self.f=Fixture('test_exact438_returns_only_frozen_B_W_authority_no_model_API');self.f.setUp();self.addCleanup(self.f.doCleanups)
 def test_late_parsed_lifetime_mutation_after_paid_stream_rejects(self):
  original=c._pins;seen=[False]
  def mutate(mapping,check):
   original(mapping,check)
   if len(mapping)==438 and not seen[0]:
    seen[0]=True;p=self.f.root/self.f.f['d']/'external-lifetime.json';p.write_bytes(p.read_bytes()+b' ')
  with patch.object(c,'_pins',side_effect=mutate):
   with self.assertRaisesRegex(ValueError,'changed'):self.f.verify()
  self.assertTrue(seen[0])
 def test_guard_interrupts_full_stream_without_returning_choice(self):
  count=[0]
  def check():
   count[0]+=1
   if count[0]>60:raise TimeoutError('independent stream stop')
  with self.assertRaisesRegex(TimeoutError,'independent stream stop'):self.f.verify(check=check)
  self.assertGreater(count[0],60)
 def test_returned_choice_does_not_alias_receipt_models(self):
  result=self.f.verify();result['authenticated_choice']['models']['W']['feature_names'][0]='modified'
  again=self.f.verify();self.assertEqual(again['authenticated_choice']['models']['W']['feature_names'][0],'f0')
if __name__=='__main__':unittest.main(defaultTest='Independent')
```

## tlab-model-choice-consumer-independent.log

Original SHA256 0f33d4d10faf2557bcb3ac3b3d61a5e13331ab51e9e80de7dc95efb2a31932e8.

```text
...
----------------------------------------------------------------------
Ran 3 tests in 0.312s

OK
```

## tlab-model-choice-actual-metadata-gate.py

Original SHA256 d367ff415d6e1fc097688abba6adf22485ad27000d8e7ff67a37c579937a58ea.

```python
from pathlib import Path
import json,sys
from unittest.mock import patch
sys.path.insert(0,'<repository>')
from scripts import feature_program_control as c,heldout_predictions as p
from tests.test_heldout_predictions import NativeFake
read=c._read;ledger=[];boundary={}
def snapshot(path,check):
    body,sha=read(path,check);ledger.append(dict(path=str(Path(path).relative_to(c.ROOT)),bytes=Path(path).stat().st_size));return body,sha
def stop(mapping,check):boundary['first_paid_pin_count']=len(mapping);raise Boundary('before full private-byte stream')
class Boundary(Exception):pass
with patch.object(c,'_read',side_effect=snapshot),patch.object(c,'_pins',side_effect=stop):
    try:c.verify_choice(c.ROOT/'artifacts/acceptance/tlab016-feature-program-models-verified.json')
    except Boundary:pass
    else:raise AssertionError('No paid boundary reached')
assert boundary['first_paid_pin_count']==438
# Critical native-setting/return-shape compatibility from bounded actual receipts
# only. NativeFake does not load CBMs, predict, or prove runtime native fidelity.
a=json.loads((c.ROOT/'artifacts/acceptance/tlab016-feature-program-models-verified.json').read_text());life=json.loads((c.ROOT/a['external_lifetime']['path']).read_text());d=Path(life['owner_report']['path']).parent
manifest=json.loads((c.ROOT/d/'run.json').read_text());i=manifest['identity'];s=a['selected_spec']
b=dict(model=dict(path=i['baseline']['model_path'],sha256=a['fingerprints'][i['baseline']['model_path']]),feature_names=i['feature_names'],trained_iterations=300,scoring_prefix=300,population=26000,effective_parameters=i['native_reference'])
w=dict(model=s['model'],feature_names=s['feature_names'],trained_iterations=300,scoring_prefix=300,population=26000,effective_parameters=s['native_effective_parameters'])
for spec in [b,w]:p.verify_model(NativeFake(spec,0),spec)
out=dict(status='passed',scope='actual_bounded_metadata_before_first_paid_stream_only_not_full_choice_verification',first_paid_pin_count=438,read_metadata=ledger,total_first_gate_metadata_bytes=sum(r['bytes'] for r in ledger),large_streams=0,CBM_loads=0,native_predictions=0,fits=0,actual_receipt_native_critical_setting_shape_compatible=True)
Path('<temporary>/tlab-model-choice-actual-metadata-gate.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='read_metadata'},sort_keys=True))
```

## tlab-model-choice-actual-metadata-gate.json

Original SHA256 e36c6ecc1fe0e18dcf014899cf895a5ff25890e196d72c6e9a63f36cafdd6ec2.

```text
{
  "CBM_loads": 0,
  "actual_receipt_native_critical_setting_shape_compatible": true,
  "first_paid_pin_count": 438,
  "fits": 0,
  "large_streams": 0,
  "native_predictions": 0,
  "read_metadata": [
    {
      "bytes": 90426,
      "path": "artifacts/acceptance/tlab016-feature-program-models-verified.json"
    },
    {
      "bytes": 1175,
      "path": "artifacts/feature-program-invocations/3a0bf8f0834949c7ab2119a1d2acaef7/external-lifetime.json"
    },
    {
      "bytes": 843,
      "path": "artifacts/feature-program-invocations/3a0bf8f0834949c7ab2119a1d2acaef7/external-admission.json"
    },
    {
      "bytes": 113490,
      "path": "artifacts/feature-program-invocations/3a0bf8f0834949c7ab2119a1d2acaef7/report.json"
    },
    {
      "bytes": 103221,
      "path": "artifacts/feature-program-invocations/3a0bf8f0834949c7ab2119a1d2acaef7/run.json"
    },
    {
      "bytes": 90960,
      "path": "artifacts/feature-program-invocations/3a0bf8f0834949c7ab2119a1d2acaef7/producer-report.json"
    },
    {
      "bytes": 93996,
      "path": "artifacts/feature-program-invocations/3a0bf8f0834949c7ab2119a1d2acaef7/proposal.json"
    },
    {
      "bytes": 2497,
      "path": "artifacts/feature-program-invocations/3a0bf8f0834949c7ab2119a1d2acaef7/winner.json"
    },
    {
      "bytes": 61343,
      "path": "artifacts/feature-program-invocations/3a0bf8f0834949c7ab2119a1d2acaef7/observer/evidence.json"
    }
  ],
  "scope": "actual_bounded_metadata_before_first_paid_stream_only_not_full_choice_verification",
  "status": "passed",
  "total_first_gate_metadata_bytes": 557951
}
```

## tlab-model-choice-actual-metadata-gate.log

Original SHA256 30b6c4b3cd59d6d65cff84800556dfbd13ed9c3aa1f5c4d87f5e8dca89013b65.

```text
{"CBM_loads": 0, "actual_receipt_native_critical_setting_shape_compatible": true, "first_paid_pin_count": 438, "fits": 0, "large_streams": 0, "native_predictions": 0, "scope": "actual_bounded_metadata_before_first_paid_stream_only_not_full_choice_verification", "status": "passed", "total_first_gate_metadata_bytes": 557951}
```

## tlab016-seal-model-output-v1-failed.py

Original SHA256 0844c0851c0954e697bafb3642d2bbe82642c1aa868844e304b1ef1b3ef8cb18.

```python
import time
START=time.monotonic()
import resource,sys,json,hashlib,math,re,os
from pathlib import Path
R=Path('<repository>');D=R/'artifacts/feature-program-invocations/3a0bf8f0834949c7ab2119a1d2acaef7';RUN='e1a63fa2c156d87b014b27b1d421bec5ebb35aefcde623f4c0c3d1ce2e636110'
def canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return Path(p).resolve().relative_to(R).as_posix()
def read(p):return json.loads(Path(p).read_text())
def ref(p):return dict(path=rel(p),sha256=sha(p))
def match(a,b):
 if type(a) is not type(b):return False
 if isinstance(a,dict):return a.keys()==b.keys() and all(match(a[k],b[k]) for k in a)
 if isinstance(a,list):return len(a)==len(b) and all(match(x,y) for x,y in zip(a,b))
 if type(a) is float:return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=1e-12
 return a==b
def merge(*maps):
 out={}
 for mapping in maps:
  for k,v in mapping.items():assert k not in out or out[k]==v,(k,'conflicting pin');out[k]=v
 return out
def verify(mapping):
 for path,digest in mapping.items():assert sha(R/path)==digest,(path,'changed actual output/authority')
def exclusive(p,body):
 p.parent.mkdir(parents=True,exist_ok=True);raw=(canon(body)+'\n').encode()
 with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 return ref(p)
r=read(D/'report.json');m=read(D/'run.json');p=read(D/'producer-report.json');e=read(D/'observer/evidence.json');proposal=read(D/'proposal.json');i=m['identity']
assert r['status']=='model_outputs_verified_pending_external_acceptance' and r['run_id']==m['run_id']==p['run_id']==e['run_id']==RUN
assert hashlib.sha256(canon(i).encode()).hexdigest()==RUN and i==proposal['identity']
assert r['fit_attempt_count']==p['fit_attempt_count']==4 and r['sum_metric_looks']==p['sum_metric_looks']==4 and r['observer_calls']==1
assert all(r[k] is False and p[k] is False for k in ['unknown_live_fit','unknown_metric_looks','heldout_labels_opened']) and r['active_slot'] is None and p['active_slot'] is None
assert e['status']=='verified' and e['scope']=='fixed_procedure_feature_program_experiment_independent_model_output_observer'
assert e['fit_attempt_count']==e['observer_refits']==e['source_regenerations']==0 and e['allocated_slots']==4 and e['checked_slots']==['I1','I2','R1','R2']
assert e['selection_query_count']==4000 and e['selection_candidate_rows']==817149 and e['reaped_children_cpu_seconds']==0
assert match(e['candidate_records'],p['candidates']) and match(e['winner'],p['winner']) and match(r['winner'],p['winner'])
approval=R/'artifacts/acceptance/tlab016-four-fit-execution.json';assert sha(approval)=='47f9b523bbaef4844c50bd453edf2d21b202f9c4aa295cffa74a3f7ef67f55b6'
a=read(approval);assert a==dict(version=1,approved=True,scope=i['role'],run_id=RUN,fingerprints=i['fingerprints']) and len(i['fingerprints'])==374
known={}
for name,digest in [('tlab016-recovered-source-verified.json','5d6741bf5156b19b3076b999d4bded20fe561a6ef0f6a6338e6799263438b42f'),('tlab019-strong-control-verified.json','a7cb383d9a75ac20ebd910fee384cb23eb8e255138df693a100942795e0ef692')]:
 path=R/'artifacts/acceptance'/name;assert sha(path)==digest;known=merge(known,read(path)['fingerprints'],{rel(path):digest})
extra=set(i['fingerprints'])-set(known)
assert extra=={'artifacts/feature-program-study/fit-owner.claim.json','configs/features/automation-selection.json','scripts/feature_program_experiment.py','scripts/program_model_data.py','scripts/recovered_feature_source.py','scripts/strong_control.py','tests/oracles/feature_program_model_audit.py'}
assert not set(known)-set(i['fingerprints']) and all(i['fingerprints'][k]==v for k,v in known.items())
verify({k:v for k,v in i['fingerprints'].items() if k in extra or k.endswith('.py') or k=='uv.lock'})
assert i['oracle_source']['sha256']=='e7d34647450dd8c55e7b1e6aeed8ed050be91316027388136394f69c8246b814'
assert i['fingerprints']['scripts/feature_program_experiment.py']=='55fb8f483815218908cbdd626fda0a274502e7ac5bbbef20d211882c18e36aad'
assert i['paid_source_cpu_seconds']==r['source_paid_cpu_seconds']==177.72 and r['source_prefix_verified'] is True
verify(m['outputs']);verify(r['observer']['authority_pins'])
assert e['producer_manifest']==ref(D/'run.json') and e['producer_report']==ref(D/'producer-report.json')
assert r['producer_manifest']==ref(D/'run.json') and r['producer_report']==ref(D/'producer-report.json')
assert e['execution_consumed']['path']==rel(D/'observer/execution.consumed.json')
assert not list(D.rglob('*.cleanup-failed.json')) and not list(D.rglob('report.failed.json')) and not (D/'observer/evidence.failed.json').exists()
assert [c['worker_report']['candidate_id'] for c in r['children']]==['I1','I2','R1','R2']
assert len(m['outputs'])==46 and len(r['observer']['authority_pins'])==12
for child in r['children']:
 w=child['worker_report'];cid=w['candidate_id'];proof=e['worker_proofs'][cid]
 assert child['exit_code']==0 and w['status']=='complete_produced_unreviewed' and w['fit_attempt_count']==1 and w['outcome']=='fit_complete'
 assert w['actual_reaped_children_cpu_seconds']==0 and w['actual_entry_cpu_seconds']<=child['actual_reaped_cpu_seconds']<=w['allocation']['cpu_seconds']
 assert w['process_peak_rss_bytes']<=7*2**30 and w['finished_monotonic']<=w['allocation']['deadline_monotonic']
 assert len(w['look_reservations'])==1 and w['look_reservations'][0]['status'].startswith('seen_')
 assert proof['status']=='saved_model_and_input_witness_replayed' and proof['all_query_rankings_identical'] is True
 assert proof['complete_trained_iterations']==proof['scoring_prefix']==300
 assert w['training']['queries']==26000 and w['training']['candidate_rows']==5317058 and abs(w['training']['row_weight_sum']-26000)<1e-8
 assert len(w['feature_names'])==44 and len(w['physical_delta'])==3 and w['actual_model_parameters']['depth']==6 and w['actual_model_parameters']['l2_leaf_reg']==30
 assert w['train_matrix_proof']==proof['train_matrix_proof'] and w['selection_matrix_proof']==proof['selection_matrix_proof']
 for field in ['report','manifest','slot','context','launch']:assert child[field]==proof[field]
# Independent literal frozen selector over already seen records; no new metric computation.
by={c['candidate_id']:c for c in e['candidate_records']};assert set(by)=={'B','I1','I2','R1','R2'}
floor=by['B']['metrics']['conditional_macro_query']['recall']-.002
feasible=[c for c in by.values() if c['status']=='verified_success' and c['metrics']['conditional_macro_query']['recall']>=floor]
maximum=max(c['metrics']['conditional_macro_query']['ndcg'] for c in feasible)
winner=min([c for c in feasible if c['metrics']['conditional_macro_query']['ndcg']>=maximum-1e-12],key=lambda c:(c['added_physical_columns'],c['candidate_id']))
assert match(winner,e['winner']) and winner['candidate_id']=='R2' and i['slots']['R2']['bundle_id']=='L05'
assert r['finished_monotonic']<=r['original_absolute_deadline_monotonic'] and r['seconds']<3600 and r['charged_study_cpu_seconds']<7200
assert r['conservative_job_peak_rss_bytes']==6357811200 and r['conservative_job_peak_rss_bytes']<8*2**30
log=Path('<temporary>/tlab016-four-fit-live.log').read_bytes();text=log.decode();assert re.search(r'^real 882\.30$',text,re.M) and re.search(r'^user 1495\.11$',text,re.M) and re.search(r'^sys 21\.91$',text,re.M)
assert r['actual_new_owner_cpu_seconds']<=1517.03 and r['seconds']<=882.31
logpath=D/'external-time.log'
with logpath.open('xb') as f:f.write(log)
lifetime=dict(version=1,scope='reaped_full_lifetime_feature_program_model_owner',run_id=RUN,explicitly_reaped_exit_code=0,
 owner_precise_cpu_seconds=r['actual_new_owner_cpu_seconds'],owner_precise_wall_seconds=r['seconds'],
 external_rounded=dict(real_seconds=882.30,user_seconds=1495.11,system_seconds=21.91,process_peak_rss_bytes=6231343104),
 charged_owner_cpu_upper_seconds=1517.03,charged_owner_wall_upper_seconds=882.31,
 source_paid_cpu_upper_seconds=177.72,production_and_oracle_cpu_upper_seconds=1694.75,
 conservative_job_peak_rss_bytes=r['conservative_job_peak_rss_bytes'],external_log=ref(logpath),owner_report=ref(D/'report.json'),
 original_absolute_deadline_monotonic=r['original_absolute_deadline_monotonic'],failed_source_remains_failed=True,
 proof='external_time_plus_explicit_reap_and_canonical_SELF_plus_reaped_CHILDREN_once_no_refits')
liferef=exclusive(D/'external-lifetime.json',lifetime)
boot={k:{n:v for n,v in b.items() if n!='samples'} for k,b in e['paired_bootstrap'].items()}
metric_rows={cid:dict(status=c['status'],added_physical_columns=c['added_physical_columns'],metrics=c['metrics']) for cid,c in by.items()}
aggregate=dict(version=1,scope='accepted_development_feature_program_comparison',run_id=RUN,winner='R2',winner_bundle='L05',candidate_records=metric_rows,
 primary_development_delta_ndcg=winner['metrics']['conditional_macro_query']['ndcg']-by['B']['metrics']['conditional_macro_query']['ndcg'],
 descriptive_best_I_minus_best_R=max(by[c]['metrics']['conditional_macro_query']['ndcg'] for c in ['I1','I2'])-max(by[c]['metrics']['conditional_macro_query']['ndcg'] for c in ['R1','R2']),
 paired_bootstrap_descriptive=boot,fit_attempt_count=4,metric_looks=4,independent_observer_calls=1,observer_refits=0,
 train_queries=26000,train_candidate_rows=5317058,selection_queries=4000,selection_candidate_rows=817149,selection_positive_queries=73,selection_fullY_pairs=96,
 trained_iterations=300,scoring_prefix=300,base_model_columns=41,per_arm_added_physical_columns=3,
 production_and_oracle_cpu_upper_seconds=1694.75,external_wall_upper_seconds=882.31,conservative_job_peak_rss_bytes=6357811200,
 heldout_targets_opened=False,source_failed_invocation_preserved=True,
 interpretation='development_selection_mixed_typed_automation_not_rule_guided_superiority_or_heldout_quality',proof_limits=e['proof_limits'])
proofdir=R/'docs/backlog-reviews';proofs=[]
name='tlab016-feature-program-model-aggregate.json';exclusive(proofdir/name,aggregate);proofs.append(ref(proofdir/name))
text='''# Feature-program models: independently verified development result

15 October 2026. **ACCEPT for the original fixed four-model development execution and saved outputs.** This is not heldout acceptance, a new fit/search allowance or evidence of rule-guided superiority.

Exactly four original slots ran with the accepted manual learner:26000 training queries,300 trained/300 scored,depth6/L2=30, query-balanced weights and unchanged B41 plus each slot's three physical fields. All four fits, four metric looks and the single zero-fit independent observer completed. The original once-owner was explicitly reaped exit0. No refill, source regeneration, observer retry or reserved target access occurred.

| Candidate | Bundle | Conditional query NDCG20 | Recall20 |
|---|---|---:|---:|
'''
for cid in ['B','I1','I2','R1','R2']:
 c=by[cid];values=c['metrics']['conditional_macro_query'];text+='| '+cid+' | '+('manual41' if cid=='B' else i['slots'][cid]['bundle_id'])+' | '+f"{values['ndcg']:.12f}"+' | '+f"{values['recall']:.12f}"+' |\n'
text+='''
The prospectively frozen all4+B selector chose **R2/L05**, adding item distinct viewers24h, item distinct cart users168h and item distinct purchase users24h. Its NDCG gain over B is0.0060921489430381, on the same4000 selection queries with only73 positive queries and96 fullY pairs. I2 failed the frozen Recall guard and is ineligible. Best2I minus best2R is descriptive and negative; a random-slot winner supports this bounded mixed typed allocation, not rule-guided superiority. The selected development comparison's paired200-user bootstrap interval is[-0.0032065371558182,0.0212938294320838]; it is descriptive after selection and does not establish a generalization improvement.

The independent observer reconstructed expected B41+3 matrices and query mass, replayed all817149 saved selection score keys for each arm, checked native full/prefix300 parameters/feature order and exact per-query rankings, recomputed four fullY estimands and every paired bootstrap draw, and independently reproduced the global selector. It performed0 fits and0 source regenerations. Native training weights cannot be recovered from CBM; matrix witnesses plus reviewed worker code/receipts retain that limit. Prior B source formula proofs are reused, not newly exhaustive.

The canonical owner measured1517.013057 CPU seconds; external user+system rounded1517.02 with a conservative full-lifetime upper1517.03. Add the separately accepted177.72 source/failed-source-recovery prefix once:1694.75 CPU seconds for source+four fits+observer. External wall upper882.31s; conservative parent+maximum-child RSS6357811200bytes<8GiB. External admission checks are separately bounded within10CPU seconds and charged conservatively, yielding total upper1704.75<original7200. The original source producer remains failed, and its immutable recovery proof remains the basis of these features.

Whole B/W choice, simulated positive compute interval and all25–31 predictions must still be sealed before reserved queryY/evaluation. Reporting-only25 and frozen26–31 remain future gates. No heldout result or task completion is claimed.
'''
name='tlab016-feature-program-model-verification.md'
with (proofdir/name).open('x') as f:f.write(text)
proofs.append(ref(proofdir/name))
name='tlab016-feature-program-model-oracle.md'
text='''# Accepted independent feature-program model observer

The actual sole observer source SHA256 is e7d34647450dd8c55e7b1e6aeed8ed050be91316027388136394f69c8246b814. [Exact reviewed code/interface](tlab016-model-observer-independent-rereview.md), [runner review](tlab016-model-runner-code-rereview-v2.md) and [red/green review evidence](tlab016-model-v2-review-evidence.md) precede the actual execution. Observer entry consumed its original exclusive execution record before paid input streaming. Its parent-bound request/context/claim/launch/source/producer/evidence pins were rechecked, including failure markers and exit-tail resource accounting.

Actual evidence verifies all four original slot matrices and saved full/prefix models/score arrays, exact rankings, fullY metrics, selected identity and descriptive bootstrap, with0 refits/source regenerations. Expected input calculation is independent of the production model loader and feature compiler; historical accepted source proof scope is reused. [Aggregate output](tlab016-feature-program-model-aggregate.json) and [acceptance rationale](tlab016-feature-program-model-verification.md) state the scientific/resource limits. This source/aggregate note is an immutable proof input, not a standalone external approval or a new observer opportunity.
'''
with (proofdir/name).open('x') as f:f.write(text)
proofs.append(ref(proofdir/name))
actual_cpu=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime
assert actual_cpu<8 and time.monotonic()-START<30
admission=dict(version=1,scope='external_model_admission_not_extra_oracle',run_id=RUN,
 measured_self_cpu_through_proof_preparation_seconds=actual_cpu,measured_wall_through_proof_preparation_seconds=time.monotonic()-START,
 charged_full_admission_cpu_upper_seconds=10,unmeasured_finalization_margin='included_in_declared10s_upper_not_claimed_measured',
 rehashed='original_output_and_small_authority_code_only_large_inputs_reused_from_single_paid_observer',refits=0,oracle_retries=0,
 external_lifetime=liferef,source_and_owner_cpu_upper_seconds=1694.75,total_study_with_admission_cpu_upper_seconds=1704.75)
admref=exclusive(D/'external-admission.json',admission)
extra_refs=[ref(D/n) for n in ['proposal.json','run.json','report.json','producer-report.json','winner.json','external-time.log','external-lifetime.json','external-admission.json']]
fps=merge(i['fingerprints'],m['outputs'],r['observer']['authority_pins'],{v['path']:v['sha256'] for v in extra_refs+proofs})
verify(m['outputs']);verify(r['observer']['authority_pins']);assert not list(D.rglob('report.failed.json')) and not (D/'observer/evidence.failed.json').exists()
selected=dict(candidate_id='R2',bundle_id='L05',model=ref(R/winner['model_path']),scores=ref(R/winner['score_path']),
 feature_names=winner['feature_names'],population=26000,trained_iterations=300,scoring_prefix=300,depth=6,l2_leaf_reg=30,
 physical_delta=i['slots']['R2']['physical_delta'],native_effective_parameters=next(c['worker_report']['actual_model_parameters'] for c in r['children'] if c['worker_report']['candidate_id']=='R2'))
body=dict(version=1,approved=True,scope='reviewed_fixed_procedure_feature_program_models',run_id=RUN,
 fingerprints=fps,selected_spec=selected,external_lifetime=liferef,external_admission=admref,
 proof_limits=e['proof_limits'],heldout_targets_opened=False,source_failed_invocation_preserved=True)
acceptance=R/'artifacts/acceptance/tlab016-feature-program-models-verified.json';out=exclusive(acceptance,body)
Path('<temporary>/tlab016-model-output-proof-files.json').write_text(json.dumps([v['path'] for v in proofs]))
Path('<temporary>/tlab016-model-output-admission-result.json').write_text(canon(dict(acceptance=out,fingerprint_count=len(fps),selected_spec=selected,lifetime=lifetime,admission=admission))+'\n')
print(canon(dict(acceptance=out,fingerprint_count=len(fps),winner='R2',production_and_oracle_cpu_upper_seconds=1694.75,total_cpu_upper_with_admission=1704.75,admission_measured_cpu=actual_cpu,fit_attempts=4,observer_calls=1)))
```

## tlab016-seal-model-output-v1-failed.txt

Original SHA256 87e76f8685a73a7e42ec88ea99d92bf605822624218cf1210e5a675bff9440a4.

```text
Initial external admission AssertionError: expected fit_complete instead of reviewed arm_complete; before any output writes. Original audit SHA256 0844c0851c0954e697bafb3642d2bbe82642c1aa868844e304b1ef1b3ef8cb18. Producer and original independent observer remained successful/unchanged; no fit/oracle retry.
```

## tlab016-seal-model-output.py

Original SHA256 8430c74f6a22c81c8f09edc6726ccad20a48f03a25e5d0505423597319272680.

```python
import time
START=time.monotonic()
import resource,sys,json,hashlib,math,re,os
from pathlib import Path
R=Path('<repository>');D=R/'artifacts/feature-program-invocations/3a0bf8f0834949c7ab2119a1d2acaef7';RUN='e1a63fa2c156d87b014b27b1d421bec5ebb35aefcde623f4c0c3d1ce2e636110'
def canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return Path(p).resolve().relative_to(R).as_posix()
def read(p):return json.loads(Path(p).read_text())
def ref(p):return dict(path=rel(p),sha256=sha(p))
def match(a,b):
 if type(a) is not type(b):return False
 if isinstance(a,dict):return a.keys()==b.keys() and all(match(a[k],b[k]) for k in a)
 if isinstance(a,list):return len(a)==len(b) and all(match(x,y) for x,y in zip(a,b))
 if type(a) is float:return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=1e-12
 return a==b
def merge(*maps):
 out={}
 for mapping in maps:
  for k,v in mapping.items():assert k not in out or out[k]==v,(k,'conflicting pin');out[k]=v
 return out
def verify(mapping):
 for path,digest in mapping.items():assert sha(R/path)==digest,(path,'changed actual output/authority')
def exclusive(p,body):
 p.parent.mkdir(parents=True,exist_ok=True);raw=(canon(body)+'\n').encode()
 with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 return ref(p)
r=read(D/'report.json');m=read(D/'run.json');p=read(D/'producer-report.json');e=read(D/'observer/evidence.json');proposal=read(D/'proposal.json');i=m['identity']
assert r['status']=='model_outputs_verified_pending_external_acceptance' and r['run_id']==m['run_id']==p['run_id']==e['run_id']==RUN
assert hashlib.sha256(canon(i).encode()).hexdigest()==RUN and i==proposal['identity']
assert r['fit_attempt_count']==p['fit_attempt_count']==4 and r['sum_metric_looks']==p['sum_metric_looks']==4 and r['observer_calls']==1
assert all(r[k] is False and p[k] is False for k in ['unknown_live_fit','unknown_metric_looks','heldout_labels_opened']) and r['active_slot'] is None and p['active_slot'] is None
assert e['status']=='verified' and e['scope']=='fixed_procedure_feature_program_experiment_independent_model_output_observer'
assert e['fit_attempt_count']==e['observer_refits']==e['source_regenerations']==0 and e['allocated_slots']==4 and e['checked_slots']==['I1','I2','R1','R2']
assert e['selection_query_count']==4000 and e['selection_candidate_rows']==817149 and e['reaped_children_cpu_seconds']==0
assert match(e['candidate_records'],p['candidates']) and match(e['winner'],p['winner']) and match(r['winner'],p['winner'])
approval=R/'artifacts/acceptance/tlab016-four-fit-execution.json';assert sha(approval)=='47f9b523bbaef4844c50bd453edf2d21b202f9c4aa295cffa74a3f7ef67f55b6'
a=read(approval);assert a==dict(version=1,approved=True,scope=i['role'],run_id=RUN,fingerprints=i['fingerprints']) and len(i['fingerprints'])==374
known={}
for name,digest in [('tlab016-recovered-source-verified.json','5d6741bf5156b19b3076b999d4bded20fe561a6ef0f6a6338e6799263438b42f'),('tlab019-strong-control-verified.json','a7cb383d9a75ac20ebd910fee384cb23eb8e255138df693a100942795e0ef692')]:
 path=R/'artifacts/acceptance'/name;assert sha(path)==digest;known=merge(known,read(path)['fingerprints'],{rel(path):digest})
extra=set(i['fingerprints'])-set(known)
assert extra=={'artifacts/feature-program-study/fit-owner.claim.json','configs/features/automation-selection.json','scripts/feature_program_experiment.py','scripts/program_model_data.py','scripts/recovered_feature_source.py','scripts/strong_control.py','tests/oracles/feature_program_model_audit.py'}
assert not set(known)-set(i['fingerprints']) and all(i['fingerprints'][k]==v for k,v in known.items())
verify({k:v for k,v in i['fingerprints'].items() if k in extra or k.endswith('.py') or k=='uv.lock'})
assert i['oracle_source']['sha256']=='e7d34647450dd8c55e7b1e6aeed8ed050be91316027388136394f69c8246b814'
assert i['fingerprints']['scripts/feature_program_experiment.py']=='55fb8f483815218908cbdd626fda0a274502e7ac5bbbef20d211882c18e36aad'
assert i['paid_source_cpu_seconds']==r['source_paid_cpu_seconds']==177.72 and r['source_prefix_verified'] is True
verify(m['outputs']);verify(r['observer']['authority_pins'])
assert e['producer_manifest']==ref(D/'run.json') and e['producer_report']==ref(D/'producer-report.json')
assert r['producer_manifest']==ref(D/'run.json') and r['producer_report']==ref(D/'producer-report.json')
assert e['execution_consumed']['path']==rel(D/'observer/execution.consumed.json')
assert not list(D.rglob('*.cleanup-failed.json')) and not list(D.rglob('report.failed.json')) and not (D/'observer/evidence.failed.json').exists()
assert [c['worker_report']['candidate_id'] for c in r['children']]==['I1','I2','R1','R2']
assert len(m['outputs'])==46 and len(r['observer']['authority_pins'])==12
for child in r['children']:
 w=child['worker_report'];cid=w['candidate_id'];proof=e['worker_proofs'][cid]
 assert child['exit_code']==0 and w['status']=='complete_produced_unreviewed' and w['fit_attempt_count']==1 and w['outcome']=='arm_complete'
 assert w['actual_reaped_children_cpu_seconds']==0 and w['actual_entry_cpu_seconds']<=child['actual_reaped_cpu_seconds']<=w['allocation']['cpu_seconds']
 assert w['process_peak_rss_bytes']<=7*2**30 and w['finished_monotonic']<=w['allocation']['deadline_monotonic']
 assert len(w['look_reservations'])==1 and w['look_reservations'][0]['status'].startswith('seen_')
 assert proof['status']=='saved_model_and_input_witness_replayed' and proof['all_query_rankings_identical'] is True
 assert proof['complete_trained_iterations']==proof['scoring_prefix']==300
 assert w['training']['queries']==26000 and w['training']['candidate_rows']==5317058 and abs(w['training']['row_weight_sum']-26000)<1e-8
 assert len(w['feature_names'])==44 and len(w['physical_delta'])==3 and w['actual_model_parameters']['depth']==6 and w['actual_model_parameters']['l2_leaf_reg']==30
 assert w['train_matrix_proof']==proof['train_matrix_proof'] and w['selection_matrix_proof']==proof['selection_matrix_proof']
 for field in ['report','manifest','slot','context','launch']:assert child[field]==proof[field]
# Independent literal frozen selector over already seen records; no new metric computation.
by={c['candidate_id']:c for c in e['candidate_records']};assert set(by)=={'B','I1','I2','R1','R2'}
floor=by['B']['metrics']['conditional_macro_query']['recall']-.002
feasible=[c for c in by.values() if c['status']=='verified_success' and c['metrics']['conditional_macro_query']['recall']>=floor]
maximum=max(c['metrics']['conditional_macro_query']['ndcg'] for c in feasible)
winner=min([c for c in feasible if c['metrics']['conditional_macro_query']['ndcg']>=maximum-1e-12],key=lambda c:(c['added_physical_columns'],c['candidate_id']))
assert match(winner,e['winner']) and winner['candidate_id']=='R2' and i['slots']['R2']['bundle_id']=='L05'
assert r['finished_monotonic']<=r['original_absolute_deadline_monotonic'] and r['seconds']<3600 and r['charged_study_cpu_seconds']<7200
assert r['conservative_job_peak_rss_bytes']==6357811200 and r['conservative_job_peak_rss_bytes']<8*2**30
log=Path('<temporary>/tlab016-four-fit-live.log').read_bytes();text=log.decode();assert re.search(r'^real 882\.30$',text,re.M) and re.search(r'^user 1495\.11$',text,re.M) and re.search(r'^sys 21\.91$',text,re.M)
assert r['actual_new_owner_cpu_seconds']<=1517.03 and r['seconds']<=882.31
logpath=D/'external-time.log'
with logpath.open('xb') as f:f.write(log)
lifetime=dict(version=1,scope='reaped_full_lifetime_feature_program_model_owner',run_id=RUN,explicitly_reaped_exit_code=0,
 owner_precise_cpu_seconds=r['actual_new_owner_cpu_seconds'],owner_precise_wall_seconds=r['seconds'],
 external_rounded=dict(real_seconds=882.30,user_seconds=1495.11,system_seconds=21.91,process_peak_rss_bytes=6231343104),
 charged_owner_cpu_upper_seconds=1517.03,charged_owner_wall_upper_seconds=882.31,
 source_paid_cpu_upper_seconds=177.72,production_and_oracle_cpu_upper_seconds=1694.75,
 conservative_job_peak_rss_bytes=r['conservative_job_peak_rss_bytes'],external_log=ref(logpath),owner_report=ref(D/'report.json'),
 original_absolute_deadline_monotonic=r['original_absolute_deadline_monotonic'],failed_source_remains_failed=True,
 proof='external_time_plus_explicit_reap_and_canonical_SELF_plus_reaped_CHILDREN_once_no_refits')
liferef=exclusive(D/'external-lifetime.json',lifetime)
boot={k:{n:v for n,v in b.items() if n!='samples'} for k,b in e['paired_bootstrap'].items()}
metric_rows={cid:dict(status=c['status'],added_physical_columns=c['added_physical_columns'],metrics=c['metrics']) for cid,c in by.items()}
aggregate=dict(version=1,scope='accepted_development_feature_program_comparison',run_id=RUN,winner='R2',winner_bundle='L05',candidate_records=metric_rows,
 primary_development_delta_ndcg=winner['metrics']['conditional_macro_query']['ndcg']-by['B']['metrics']['conditional_macro_query']['ndcg'],
 descriptive_best_I_minus_best_R=max(by[c]['metrics']['conditional_macro_query']['ndcg'] for c in ['I1','I2'])-max(by[c]['metrics']['conditional_macro_query']['ndcg'] for c in ['R1','R2']),
 paired_bootstrap_descriptive=boot,fit_attempt_count=4,metric_looks=4,independent_observer_calls=1,observer_refits=0,
 train_queries=26000,train_candidate_rows=5317058,selection_queries=4000,selection_candidate_rows=817149,selection_positive_queries=73,selection_fullY_pairs=96,
 trained_iterations=300,scoring_prefix=300,base_model_columns=41,per_arm_added_physical_columns=3,
 production_and_oracle_cpu_upper_seconds=1694.75,external_wall_upper_seconds=882.31,conservative_job_peak_rss_bytes=6357811200,
 heldout_targets_opened=False,source_failed_invocation_preserved=True,
 interpretation='development_selection_mixed_typed_automation_not_rule_guided_superiority_or_heldout_quality',proof_limits=e['proof_limits'])
proofdir=R/'docs/backlog-reviews';proofs=[]
name='tlab016-feature-program-model-aggregate.json';exclusive(proofdir/name,aggregate);proofs.append(ref(proofdir/name))
text='''# Feature-program models: independently verified development result

15 October 2026. **ACCEPT for the original fixed four-model development execution and saved outputs.** This is not heldout acceptance, a new fit/search allowance or evidence of rule-guided superiority.

Exactly four original slots ran with the accepted manual learner:26000 training queries,300 trained/300 scored,depth6/L2=30, query-balanced weights and unchanged B41 plus each slot's three physical fields. All four fits, four metric looks and the single zero-fit independent observer completed. The original once-owner was explicitly reaped exit0. No refill, source regeneration, observer retry or reserved target access occurred.

| Candidate | Bundle | Conditional query NDCG20 | Recall20 |
|---|---|---:|---:|
'''
for cid in ['B','I1','I2','R1','R2']:
 c=by[cid];values=c['metrics']['conditional_macro_query'];text+='| '+cid+' | '+('manual41' if cid=='B' else i['slots'][cid]['bundle_id'])+' | '+f"{values['ndcg']:.12f}"+' | '+f"{values['recall']:.12f}"+' |\n'
text+='''
The prospectively frozen all4+B selector chose **R2/L05**, adding item distinct viewers24h, item distinct cart users168h and item distinct purchase users24h. Its NDCG gain over B is0.0060921489430381, on the same4000 selection queries with only73 positive queries and96 fullY pairs. I2 failed the frozen Recall guard and is ineligible. Best2I minus best2R is descriptive and negative; a random-slot winner supports this bounded mixed typed allocation, not rule-guided superiority. The selected development comparison's paired200-user bootstrap interval is[-0.0032065371558182,0.0212938294320838]; it is descriptive after selection and does not establish a generalization improvement.

The independent observer reconstructed expected B41+3 matrices and query mass, replayed all817149 saved selection score keys for each arm, checked native full/prefix300 parameters/feature order and exact per-query rankings, recomputed four fullY estimands and every paired bootstrap draw, and independently reproduced the global selector. It performed0 fits and0 source regenerations. Native training weights cannot be recovered from CBM; matrix witnesses plus reviewed worker code/receipts retain that limit. Prior B source formula proofs are reused, not newly exhaustive.

The canonical owner measured1517.013057 CPU seconds; external user+system rounded1517.02 with a conservative full-lifetime upper1517.03. Add the separately accepted177.72 source/failed-source-recovery prefix once:1694.75 CPU seconds for source+four fits+observer. External wall upper882.31s; conservative parent+maximum-child RSS6357811200bytes<8GiB. External admission checks are separately bounded within10CPU seconds and charged conservatively, yielding total upper1704.75<original7200. The original source producer remains failed, and its immutable recovery proof remains the basis of these features.

The initial external admission audit expected an incorrect worker outcome constant and stopped before creating seals. The actual reviewed outcome is arm_complete; the narrow assertion was corrected. No producer, observer or fit was repeated. Both small admission attempts are covered by the declared10CPU admission upper.

Whole B/W choice, simulated positive compute interval and all25–31 predictions must still be sealed before reserved queryY/evaluation. Reporting-only25 and frozen26–31 remain future gates. No heldout result or task completion is claimed.
'''
name='tlab016-feature-program-model-verification.md'
with (proofdir/name).open('x') as f:f.write(text)
proofs.append(ref(proofdir/name))
name='tlab016-feature-program-model-oracle.md'
text='''# Accepted independent feature-program model observer

The actual sole observer source SHA256 is e7d34647450dd8c55e7b1e6aeed8ed050be91316027388136394f69c8246b814. [Exact reviewed code/interface](tlab016-model-observer-independent-rereview.md), [runner review](tlab016-model-runner-code-rereview-v2.md) and [red/green review evidence](tlab016-model-v2-review-evidence.md) precede the actual execution. Observer entry consumed its original exclusive execution record before paid input streaming. Its parent-bound request/context/claim/launch/source/producer/evidence pins were rechecked, including failure markers and exit-tail resource accounting.

Actual evidence verifies all four original slot matrices and saved full/prefix models/score arrays, exact rankings, fullY metrics, selected identity and descriptive bootstrap, with0 refits/source regenerations. Expected input calculation is independent of the production model loader and feature compiler; historical accepted source proof scope is reused. [Aggregate output](tlab016-feature-program-model-aggregate.json) and [acceptance rationale](tlab016-feature-program-model-verification.md) state the scientific/resource limits. This source/aggregate note is an immutable proof input, not a standalone external approval or a new observer opportunity.
'''
with (proofdir/name).open('x') as f:f.write(text)
proofs.append(ref(proofdir/name))
actual_cpu=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime
assert actual_cpu<8 and time.monotonic()-START<30
admission=dict(version=1,scope='external_model_admission_not_extra_oracle',run_id=RUN,
 measured_self_cpu_through_proof_preparation_seconds=actual_cpu,measured_wall_through_proof_preparation_seconds=time.monotonic()-START,
 charged_full_admission_cpu_upper_seconds=10,unmeasured_finalization_margin='included_in_declared10s_upper_not_claimed_measured',
 rehashed='original_output_and_small_authority_code_only_large_inputs_reused_from_single_paid_observer',refits=0,oracle_retries=0,
 external_lifetime=liferef,source_and_owner_cpu_upper_seconds=1694.75,total_study_with_admission_cpu_upper_seconds=1704.75)
admref=exclusive(D/'external-admission.json',admission)
extra_refs=[ref(D/n) for n in ['proposal.json','run.json','report.json','producer-report.json','winner.json','external-time.log','external-lifetime.json','external-admission.json']]
fps=merge(i['fingerprints'],m['outputs'],r['observer']['authority_pins'],{v['path']:v['sha256'] for v in extra_refs+proofs})
verify(m['outputs']);verify(r['observer']['authority_pins']);assert not list(D.rglob('report.failed.json')) and not (D/'observer/evidence.failed.json').exists()
selected=dict(candidate_id='R2',bundle_id='L05',model=ref(R/winner['model_path']),scores=ref(R/winner['score_path']),
 feature_names=winner['feature_names'],population=26000,trained_iterations=300,scoring_prefix=300,depth=6,l2_leaf_reg=30,
 physical_delta=i['slots']['R2']['physical_delta'],native_effective_parameters=next(c['worker_report']['actual_model_parameters'] for c in r['children'] if c['worker_report']['candidate_id']=='R2'))
body=dict(version=1,approved=True,scope='reviewed_fixed_procedure_feature_program_models',run_id=RUN,
 fingerprints=fps,selected_spec=selected,external_lifetime=liferef,external_admission=admref,
 proof_limits=e['proof_limits'],heldout_targets_opened=False,source_failed_invocation_preserved=True)
acceptance=R/'artifacts/acceptance/tlab016-feature-program-models-verified.json';out=exclusive(acceptance,body)
Path('<temporary>/tlab016-model-output-proof-files.json').write_text(json.dumps([v['path'] for v in proofs]))
Path('<temporary>/tlab016-model-output-admission-result.json').write_text(canon(dict(acceptance=out,fingerprint_count=len(fps),selected_spec=selected,lifetime=lifetime,admission=admission))+'\n')
print(canon(dict(acceptance=out,fingerprint_count=len(fps),winner='R2',production_and_oracle_cpu_upper_seconds=1694.75,total_cpu_upper_with_admission=1704.75,admission_measured_cpu=actual_cpu,fit_attempts=4,observer_calls=1)))
```
