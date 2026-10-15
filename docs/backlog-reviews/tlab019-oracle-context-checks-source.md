# Historical019 observer evidence: context-checks

Paths normalized for privacy. This archive records an earlier review state or a synthetic/API check, not a new execution. Only tests/oracles/strong_output_audit.py is the final accepted observer entry.

```python
import importlib.util,unittest,tempfile,hashlib,ast
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
p=Path('tlab-verify019-outputs.py');s=importlib.util.spec_from_file_location('audit',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
class Checks(unittest.TestCase):
 def fixture(self,root):
  directory=root/'artifacts/strong-invocations/tiny';directory.mkdir(parents=True)
  ctx=dict(version=1,scope='independent_strong_baseline_verifier',run_id='0'*64,project_root=str(root),invocation_directory='artifacts/strong-invocations/tiny',request_sha256='1'*64,producer_manifest={},producer_report={},allocation=dict(cpu_seconds=1,deadline_monotonic=o.START+100,rss_bytes=7*2**30),expected_verifier_source=dict(path=str(p.resolve()),sha256='2'*64),issued_at_monotonic=o.START-1,output_path='artifacts/strong-invocations/tiny/verification.json',failed_output_path='artifacts/strong-invocations/tiny/verification.failed.json')
  path=directory/'verification-context.json';path.write_bytes(o.canonical(ctx).encode());return path,ctx
 def test_verified_snapshot_is_only_context_read(self):
  with tempfile.TemporaryDirectory() as temporary:
   path,c=self.fixture(Path(temporary).resolve());raw=path.read_bytes();issued=hashlib.sha256(raw).hexdigest();wrong=deepcopy(c);wrong['allocation']['cpu_seconds']=300;calls=[];read=Path.read_bytes
   def changing(p):
    if p==path:calls.append(p);return raw if len(calls)==1 else o.canonical(wrong).encode()
    return read(p)
   with patch.object(Path,'read_bytes',changing),patch.object(o.Observer,'sha',side_effect=lambda self,p: '2'*64 if p.resolve()!=path else issued,autospec=True):
    obs=o.Observer(path,issued_context_sha256=issued)
   self.assertEqual(len(calls),1);self.assertEqual(obs.allocation['cpu_seconds'],1)
 def test_wrong_issuer_never_reaches_parser(self):
  with tempfile.TemporaryDirectory() as temporary:
   path,c=self.fixture(Path(temporary).resolve())
   with patch.object(o,'read_raw_json',side_effect=AssertionError('untrusted parse')) as parser:
    with self.assertRaisesRegex(ValueError,'issuer launch digest'):o.Observer(path,issued_context_sha256='f'*64)
    parser.assert_not_called()
 def test_native_checked_functions_ast_unchanged_after_parser_delta(self):
  before=ast.parse(Path('tlab-verify019-outputs-18d45-reviewed.py').read_text());after=ast.parse(p.read_text())
  def nodes(tree):
   return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)}
  a,b=nodes(before),nodes(after)
  for n in ['model','effective_learning_rate','same']:self.assertEqual(a[n],b[n])
if __name__=='__main__':unittest.main(verbosity=2)

```
