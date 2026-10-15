# Independent016 runner v1 source

Original SHA256 2642bad31567c725489f2f7388f721a851ff39ce944b979070fca2db19257bff. Temporary traceback roots sanitized for publication; synthetic fixture source/assertions unchanged. No actual model/source execution.

```python
import json,unittest
from pathlib import Path
from unittest.mock import patch
from tests import test_feature_program_experiment as a
from scripts import strong_baseline as lifecycle
m=a.m

class ObserverRepin(a.OwnerLifecycle):
 def test_independent_observer_request_mutation_must_reject_pending_source(self):
  directory=self.root/'observer-test';directory.mkdir()
  parent=dict(run_id='a'*64,identity=dict(source_run_id='b'*64,oracle_source=dict(path='oracle.py',sha256='c'*64)),execution_approval=dict(path='approved.json',sha256='d'*64),budget_claim=dict(path=m.CLAIM,sha256='e'*64))
  producer=dict(candidates=a.candidates(),winner=a.candidates()[0],children=[])
  for cid in m.IDS[1:]:
   child=dict(worker_report=dict(candidate_id=cid))
   child.update({n:dict(path=cid+'/'+n,sha256='f'*64) for n in ['report','manifest','slot','context','launch']});producer['children'].append(child)
  m._write(directory/'run.json',{'run_id':parent['run_id']});m._write(directory/'producer-report.json',producer)
  budget=m.Budget(177.72,self_cpu=m._self_cpu,children_cpu=m._children_cpu,rss=m._rss)
  def fake_child(argv,log,**kwargs):
   context=m._read(Path(argv[argv.index('--context')+1]))[0];request=context['request'];now=m.time.monotonic()
   evidence=dict(version=1,status='verified',scope=m.ROLE+'_independent_model_output_observer',run_id=parent['run_id'],source_run_id='b'*64,
    context_sha256=argv[argv.index('--issued-context-sha256')+1],request=request,producer_manifest=context['producer_manifest'],producer_report=context['producer_report'],oracle_source=context['oracle_source'],
    fit_attempt_count=0,observer_refits=0,source_regenerations=0,allocated_slots=4,checked_slots=list(m.IDS[1:]),candidate_records=producer['candidates'],winner=producer['winner'],
    worker_proofs={child['worker_report']['candidate_id']:{n:child[n] for n in ['report','manifest','slot','context','launch']} for child in producer['children']},
    proof_limits='Synthetic binding only, no actual model proof',paired_bootstrap={},process_cpu_seconds=0.,reaped_children_cpu_seconds=0,process_peak_rss_bytes=64,
    started_monotonic=now,finished_monotonic=now)
   m._write(m._local(context['output_path']),evidence)
   # Change the actual request after the child has read its original bound bytes.
   path=m._local(request['path']);path.write_bytes(path.read_bytes()+b' ')
   return 0
  # Exercise real _observer rather than setUp's owner-plumbing fake.
  original=m._observer.__wrapped__ if hasattr(m._observer,'__wrapped__') else None
  # Access the frozen function from a separate source snapshot; no changed code.
  import importlib.util
  spec=importlib.util.spec_from_file_location('observer_original',Path(a.__file__).resolve().parents[1]/'scripts/feature_program_experiment.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with patch.object(module,'ROOT',self.root),patch.object(module.time,'monotonic',m.time.monotonic),patch.object(module,'_self_cpu',m._self_cpu),patch.object(module,'_children_cpu',m._children_cpu),patch.object(lifecycle,'run_process',side_effect=fake_child):
   with self.assertRaisesRegex(ValueError,'request|authority|changed'):
    module._observer(directory,parent,producer,budget)

r=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([ObserverRepin('test_independent_observer_request_mutation_must_reject_pending_source')]))
raise SystemExit(0 if r.wasSuccessful() else 1)
```
