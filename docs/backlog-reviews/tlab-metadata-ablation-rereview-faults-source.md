# Independent synthetic model-data/ablation audit archive

Historical exact-version audit, with only machine paths made portable. Extract dependent archived helpers into the system temporary directory before use. Initial model-data overflow assertion mismatch and initial terminal-decision faults remain evidence for their original versions. Archiving claims no new execution or actual fitting.

```python
import ast
from pathlib import Path
source=(Path(__import__('tempfile').gettempdir())/'tlab-metadata-ablation-independent-faults.py').read_text()
tree=ast.parse(source)
keep=[]
for node in tree.body:
 if isinstance(node,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.ClassDef)) or isinstance(node,ast.Assign) and node.lineno<25:
  keep.append(node)
 elif isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='insert':keep.append(node)
source=ast.unparse(ast.Module(body=keep,type_ignores=[]))
source=source.replace("if fault == 'terminal_resource' and Path(path).name == 'run.json':", "if fault in {'terminal_resource','secondary_policy'} and Path(path).name == 'run.json':")
source=source.replace("return real_write(path, body)","if fault == 'secondary_policy' and body.get('terminal_decision_receipt_tail'): raise OSError('SECONDARY policy writer')\n            return real_write(path, body)")
source=source.replace("elif fault in {'terminal_resource', 'terminal_write'}:","elif fault in {'terminal_resource', 'terminal_write', 'secondary_policy'}:")
source=source.replace("details['contradictory_retention_on_failed_run'] = report['decision'].get('retain_metadata_block') is True", "assert report['decision'].get('retain_metadata_block') is False\n            assert report['decision']['feature_choice'] == 'base41' if fault in {'terminal_resource','secondary_policy'} else 'stop' in report['decision']['feature_choice']\n            if fault == 'secondary_policy':\n                assert isinstance(err,MemoryError) and 'TERMINAL resource' in str(err)\n                assert markers and any('SECONDARY policy writer' in e['error'] for e in report.get('secondary_errors',[]))\n            details['contradictory_retention_on_failed_run'] = False")
source=source.replace("return details", "claim_path=f.root/a.CLAIM\n        if details['claim_exists']:\n            claim_before=claim_path.read_bytes()\n            audit=Mock();audit.directory=f.root/'new-output';audit.report={}\n            rejected=rejects(lambda:a.consume_claim(dict(run_id='b'*64),audit),FileExistsError)\n            assert claim_path.read_bytes()==claim_before\n            details['changed_plan_global_retry_rejected']=rejected\n        return details")
exec(compile(source,'original-independent-harness-selected-definitions','exec'))
results=[]
for fault in [None,'terminal_resource','terminal_write','secondary_policy']:
 run('narrow_runtime_'+str(fault),lambda fault=fault:runtime(fault=fault))
def body_primary_terminal_secondary():
 with tempfile.TemporaryDirectory(prefix='tlab-ablation-rereview-',dir='/tmp') as tmp:
  directory=Path(tmp)/'artifacts';real_write=c._atomic_json;primary=ValueError('PRIMARY body integrity')
  def writer(path,body):
   if Path(path).name=='run.json':raise MemoryError('SECONDARY terminal memory')
   return real_write(path,body)
  caught=None
  with patch.object(c,'_atomic_json',side_effect=writer):
   try:
    with a.AblationAudit(directory,seconds=10,scope=a.ROLE) as audit:
     audit.manifest=dict(synthetic=True);audit.report['decision']=dict(retain_metadata_block=True);raise primary
   except BaseException as e:caught=e
  report=b._read_json(next(directory.glob('*/report.json')))
  assert caught is primary and report['error_type']=='ValueError' and report['error']=='PRIMARY body integrity'
  assert not report['decision']['retain_metadata_block'] and 'stop' in report['decision']['feature_choice']
  assert any(e['error']=='SECONDARY terminal memory' for e in report['terminal_errors'])
  return dict(primary_identity_preserved=True,status=report['status'],decision=report['decision'],secondary_preserved=True)
run('body_primary_before_terminal_secondary',body_primary_terminal_secondary)
protected=[(Path(__import__('tempfile').gettempdir())/'tlab-metadata-ablation-independent-review.md'),(Path(__import__('tempfile').gettempdir())/'tlab-metadata-ablation-independent-faults.py'),(Path(__import__('tempfile').gettempdir())/'tlab-metadata-ablation-independent-results.json'),ROOT/'scripts/metadata_price_collection.py']
protected_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
assert before==hashes()
out=dict(before=before,after=hashes(),protected=protected_hashes,cases=results,wall_seconds=time.monotonic()-START,cpu_seconds=time.process_time()-CPU,maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,scope='narrow synthetic/mocked only; zero actual matrices/native Pool/native fits/source/approvals')
(Path(__import__('tempfile').gettempdir())/'tlab-metadata-ablation-rereview-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
if any(r['status']=='FAIL' for r in results):sys.exit(1)

```
