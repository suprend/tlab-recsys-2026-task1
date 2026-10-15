# Source-only core and supplied-score replay independent evidence

15 October 2026. Aggregate/synthetic only. Accepted source core has no actual heldout execution permission; supplied-score replay demonstrates a relocated12-row public prefix, not source regeneration or retraining. Original failure logs and repaired probes remain here. Combined current492-test suite PASS34.165s, ResourceWarning=error. Original temporary/home paths are sanitized for publication; original source/log SHA256 below.

## tlab-heldout-source-independent.py

Original SHA256 1ac436ecc9a5fbeee88032c618b03df6d503e40488160756b4c4655cfdb1eeab.

```python
import sys,unittest
from datetime import timedelta
from unittest.mock import patch
sys.path.insert(0,'<repository>')
from tests.test_heldout_source import HeldoutSource as AuthorFixture,ROWS,T,BIG,definitions
from scripts import heldout_source as m
class Independent(unittest.TestCase):
 def setUp(self):
  self.f=AuthorFixture('test_exact48h_anchor_global_peers_raw_bag_and_bigint');self.f.setUp();self.addCleanup(self.f.tearDown)
 def test_random_user_bundle_exact_independent_24h_values(self):
  self.f.rows();result=self.f.build(choice='R1')
  rows=self.f.con.execute('SELECT DISTINCT user_id,auto_user_view_count_24h,auto_user_cart_count_24h,auto_user_purchase_count_24h FROM heldout_base_features b JOIN heldout_extra_features a USING(query_id,product_id)').fetchall()
  self.assertEqual({r[0]:r[1:] for r in rows},{1:(2,0,0),2:(0,1,0),3:(0,0,1),BIG:(1,0,0)})
  self.assertEqual(len(result['extra_schema']),3);self.assertFalse(result['source_formula_acceptance'])
 def test_random_item_distinct_bundle_raw_duplicates_not_distinct_buyers(self):
  self.f.rows();self.f.build(choice='R2')
  rows=self.f.con.execute('SELECT DISTINCT product_id,auto_item_view_count_distinct_24h_user_id,auto_item_cart_count_distinct_168h_user_id,auto_item_purchase_count_distinct_24h_user_id FROM heldout_extra_features').fetchall()
  self.assertEqual({r[0]:r[1:] for r in rows},{10:(1,0,0),20:(0,1,0),30:(0,0,1),BIG:(1,0,0)})
 def test_build_no_source_files_target_builder_and_choice_switch_removes_extras(self):
  self.f.rows()
  pool,l,c=definitions('I2');poolb,lb,cb=definitions('B')
  with patch('builtins.open',side_effect=AssertionError('no files')),patch('io.open',side_effect=AssertionError('no path files')):
   m.build_day(self.f.con,'2019-10-25T00:00:00Z',pool,l,authenticated_choice=c)
   m.build_day(self.f.con,'2019-10-25T00:00:00Z',poolb,lb,authenticated_choice=cb)
  names={r[0] for r in self.f.con.execute('SHOW TABLES').fetchall()}
  self.assertNotIn('heldout_extra_features',names);self.assertNotIn('pilot_labels',names)
  self.assertEqual(len(self.f.con.execute('DESCRIBE manual_features').fetchall()),45)
if __name__=='__main__':unittest.main(defaultTest='Independent')
```

## tlab-heldout-source-author-independent.log

Original SHA256 ad368d41decbeef0bc947e66f74d4c1d1309793df0a34d54dba1ee8e700f5387.

```text
..............
----------------------------------------------------------------------
Ran 14 tests in 0.755s

OK
```

## tlab-heldout-source-independent-final.log

Original SHA256 44a7e9776c7ac775e446dbefc9bb7c7c6b3081183a38cfd3dfe4c447dacfc80e.

```text
...
----------------------------------------------------------------------
Ran 3 tests in 0.345s

OK
```

## tlab018-p0a-independent-terminal.py

Original SHA256 e4d4ac23d764689c61049839c6f700e350cb2f43952d192daf31d379d4225c68.

```python
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,'<repository>')
from tests.test_replay_ranking_claim import ReplayTests
from scripts import replay_ranking_claim as r
class Independent(unittest.TestCase):
 def setUp(self):
  self.fixture=ReplayTests('test_public_literal_four_estimands_bigint_ties_fullY_emptyC_no_writes');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
 def test_closed_stream_changed_authority_cannot_return_without_evidence(self):
  obj=r.Replay(str(self.fixture.package.relative_to(self.fixture.root)));original=r.Rows.close;done=[False]
  def close(stream):
   original(stream)
   if not done[0]:
    done[0]=True
    p=self.fixture.package/'manifest.json';p.write_bytes(p.read_bytes()+b' ')
  with patch.object(r.Rows,'close',close):
   with self.assertRaisesRegex(ValueError,'authority_changed'):obj.run()
  self.assertTrue(done[0])
 def test_closed_stream_changed_data_cannot_write_verified_evidence(self):
  obj=r.Replay(str(self.fixture.package.relative_to(self.fixture.root)),evidence_out='review.json');original=r.Rows.close;done=[False]
  def close(stream):
   original(stream)
   if not done[0]:
    done[0]=True
    p=self.fixture.package/'scores.jsonl';p.write_bytes(p.read_bytes()+b' ')
  with patch.object(r.Rows,'close',close):
   with self.assertRaisesRegex(ValueError,'data_changed'):obj.run()
  self.assertFalse((self.fixture.root/'review.json').exists());self.assertTrue(done[0])
if __name__=='__main__':unittest.main()
```

## tlab018-p0a-independent-terminal-v1.log

Original SHA256 46ec757c143ab690aa0fb7f86e5fec7cdfc058315a63aea4838e52829aaa92ab.

```text
FF..................
======================================================================
FAIL: test_closed_stream_changed_authority_cannot_return_without_evidence (__main__.Independent.test_closed_stream_changed_authority_cannot_return_without_evidence)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab018-p0a-independent-terminal.py", line 18, in test_closed_stream_changed_authority_cannot_return_without_evidence
    with self.assertRaisesRegex(ValueError,'authority_changed'):obj.run()
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_closed_stream_changed_data_cannot_write_verified_evidence (__main__.Independent.test_closed_stream_changed_data_cannot_write_verified_evidence)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab018-p0a-independent-terminal.py", line 28, in test_closed_stream_changed_data_cannot_write_verified_evidence
    with self.assertRaisesRegex(ValueError,'data_changed'):obj.run()
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

----------------------------------------------------------------------
Ran 20 tests in 0.099s

FAILED (failures=2)
```

## tlab018-p0a-independent-terminal-v3.log

Original SHA256 2fa071fe977705bfef05c7a955446f9d9708d3d39ffd9f8494d5d07911cb1f1c.

```text
........................
----------------------------------------------------------------------
Ran 24 tests in 0.107s

OK
```

## tlab018-p0a-relocated-smoke.py

Original SHA256 5c64096b24d2fb8094852fb5525151fc57c64a24e7e009c0fc62542160aebd8a.

```python
from pathlib import Path
import json,hashlib,shutil,subprocess,sys,tempfile,ast
root=Path('<repository>');freeze=json.loads(Path('<temporary>/tlab018-p0a-replay-freeze-v3.json').read_text())
for name,sha in freeze.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,name
with tempfile.TemporaryDirectory(prefix='tlab relocated public ') as tmp:
    dest=Path(tmp);names=['scripts/replay_ranking_claim.py','scripts/ranking_metrics.py',*[p for p in freeze if p.startswith('tests/fixtures/')]]
    for name in names:
        p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,p)
    before={str(p.relative_to(dest)):hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob('*') if p.is_file()}
    actual=subprocess.run([sys.executable,'-B','-m','scripts.replay_ranking_claim','--package','tests/fixtures/reproduction/manual18-small'],cwd=dest,capture_output=True,text=True,timeout=15)
    assert actual.returncode==0,actual.stderr+actual.stdout
    body=json.loads(actual.stdout);assert body['status']=='computed_verified_package_replay'
    assert body['metrics']['query_count']==3 and body['fit_attempt_count']==0 and body['native_prediction_count']==0 and body['execution_consumed'] is None
    after={str(p.relative_to(dest)):hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob('*') if p.is_file()}
    assert before==after and not (dest/'data').exists() and not (dest/'artifacts').exists() and not (dest/'.venv').exists()
    output=dict(status='passed',scope='relocated_public_prefix_only_using_existing_Python_not_environment_reinstall_or_private_historical_replay',copied_files=len(names),path_contains_spaces=True,exit_code=actual.returncode,query_count=3,source_rows=12,files_unchanged=True,no_data_artifacts_venv_in_relocated_root=True,fit_attempt_count=0,native_prediction_count=0,reported_CPU_seconds=body['process_cpu_seconds'],reported_RSS_bytes=body['process_peak_rss_bytes'])
Path('<temporary>/tlab018-p0a-relocated-smoke.json').write_text(json.dumps(output,indent=2,sort_keys=True)+'\n');print(json.dumps(output,sort_keys=True))
old=ast.parse(Path('<temporary>/tlab018-p0a-replay-v2/scripts/replay_ranking_claim.py').read_text());new=ast.parse((root/'scripts/replay_ranking_claim.py').read_text())
def methods(tree):
    result={}
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)):
            if isinstance(node,ast.ClassDef):
                for f in node.body:
                    if isinstance(f,ast.FunctionDef):result[node.name+'.'+f.name]=ast.dump(f,include_attributes=False)
            else:result[node.name]=ast.dump(node,include_attributes=False)
    return result
a,b=methods(old),methods(new);assert set(a)==set(b);changed=[n for n in a if a[n]!=b[n]];assert changed==['Replay.run'],changed
print(json.dumps({'v2_to_v3_AST_changed':changed,'other_functions_unchanged':len(a)-1}))
```

## tlab018-p0a-relocated-smoke.json

Original SHA256 12d7cd94194641492d2efe291f0b07abf034fe65040fa1c040516c776c3f500f.

```text
{
  "copied_files": 7,
  "exit_code": 0,
  "files_unchanged": true,
  "fit_attempt_count": 0,
  "native_prediction_count": 0,
  "no_data_artifacts_venv_in_relocated_root": true,
  "path_contains_spaces": true,
  "query_count": 3,
  "reported_CPU_seconds": 0.030243,
  "reported_RSS_bytes": 25165824,
  "scope": "relocated_public_prefix_only_using_existing_Python_not_environment_reinstall_or_private_historical_replay",
  "source_rows": 12,
  "status": "passed"
}
```

## tlab018-p0a-relocated-smoke.log

Original SHA256 dd4e7ffb8ac84cda5f906d582aa0b9effef94e217f0d7d656d563322f40f3e05.

```text
{"copied_files": 7, "exit_code": 0, "files_unchanged": true, "fit_attempt_count": 0, "native_prediction_count": 0, "no_data_artifacts_venv_in_relocated_root": true, "path_contains_spaces": true, "query_count": 3, "reported_CPU_seconds": 0.030243, "reported_RSS_bytes": 25165824, "scope": "relocated_public_prefix_only_using_existing_Python_not_environment_reinstall_or_private_historical_replay", "source_rows": 12, "status": "passed"}
{"v2_to_v3_AST_changed": ["Replay.run"], "other_functions_unchanged": 33}
```

## tlab-all-tests-heldout-and-replay.log

Original SHA256 7b281231525792c66ec44441957427eba9d75f8a217eda4d4617d5445f329c38.

```text
...........{"status": "failed", "run_id": "43b83f778ea592494449584339d4fda612dc851eece76a239ce6f425594ae803", "seconds": 0.006232167001144262, "report": "/private/var/folders/gb/j1q8qm811b3gjd3gk93fh22h0000gn/T/tmppl7d4lru/artifacts/pilot/43b83f778ea592494449584339d4fda612dc851eece76a239ce6f425594ae803/report.json"}
.....................................................{"report":"worker/bedec6fde5e3e9293ae4b1525f0321d91b136ecd9f4b63043565813484ec96fb/report.json","status":"complete_produced_unreviewed"}
.{"approval_path":"approval.json","proposal":"artifacts/feature-program-invocations/776e9a9d0f9744de8a6fdc32c58d051e/proposal.json","run_id":"5e6f48cd99bd81380578ad7c86d5eb9798022899567597292fe792238c20a43f","status":"awaiting_exact_execution_approval"}
.{"approval_path":"approval.json","proposal":"artifacts/feature-program-invocations/73ded9a8ff90406283fad5a900cfab3b/proposal.json","run_id":"bd4e3aa9017233a7d972528c75b4056faf2ab118644efffcb83b2dc7475c26a9","status":"awaiting_exact_execution_approval"}
.{"approval_path":"approval.json","proposal":"artifacts/feature-program-invocations/6ac96f7102d4449f90ddcf7964786de1/proposal.json","run_id":"28ad81356a4f4bb1ef0dc2c578c5bb5a029dce466574a851f0d3689b1024ae08","status":"awaiting_exact_execution_approval"}
{"directory":"artifacts/feature-program-invocations/6ac96f7102d4449f90ddcf7964786de1","run_id":"28ad81356a4f4bb1ef0dc2c578c5bb5a029dce466574a851f0d3689b1024ae08","status":"model_outputs_verified_pending_external_acceptance"}
..{"approval_path":"approval.json","proposal":"artifacts/feature-program-invocations/97039e87c69f4345b811c726fcadc455/proposal.json","run_id":"fcd19a4f65315ce5bc407051cd23760f652e7f4010f1d296776ffcb3cbe0b51d","status":"awaiting_exact_execution_approval"}
{"directory":"artifacts/feature-program-invocations/97039e87c69f4345b811c726fcadc455","run_id":"fcd19a4f65315ce5bc407051cd23760f652e7f4010f1d296776ffcb3cbe0b51d","status":"model_outputs_verified_pending_external_acceptance"}
.{"approval_path":"approval.json","proposal":"artifacts/feature-program-invocations/811200c396354ffc9789ff89d11bf482/proposal.json","run_id":"fd21923200623c8c06c1d7519a41a378716c860c549cf3ac582c6430bbdde516","status":"awaiting_exact_execution_approval"}
.{"approval_path":"approval.json","proposal":"artifacts/feature-program-invocations/e8bca906faf94a8d97e44c422ed2e87d/proposal.json","run_id":"ce76b9ac65eba40e1850a267a21e5e257fe23dc37a3fdc04f3ef2b34fcdfd900","status":"awaiting_exact_execution_approval"}
.{"approval_path":"approval.json","proposal":"artifacts/feature-program-invocations/2152077172104be3a066a48ff345cbe8/proposal.json","run_id":"cd255e96a1a86b502b35a0eb5382b8502e9f4d1231976cf056505ff230942f17","status":"awaiting_exact_execution_approval"}
.........................................................................................................................{"status": "failed", "run_id": null, "seconds": 0.0024802080006338656, "report": "/private/var/folders/gb/j1q8qm811b3gjd3gk93fh22h0000gn/T/tmpdesl_il2/artifacts/manual-features/attempt-5a54c06d78ad47b1b8b160da982f1bc3/report.json"}
.{"status": "failed", "run_id": "c841f36e8d948a2a7a872acd4fd10a5160b39a4de006dd48d2862322be50464d", "seconds": 0.005733458001486724, "report": "/private/var/folders/gb/j1q8qm811b3gjd3gk93fh22h0000gn/T/tmpcplyw0tu/artifacts/manual-features/c841f36e8d948a2a7a872acd4fd10a5160b39a4de006dd48d2862322be50464d/report.json"}
.{"status": "failed", "run_id": null, "seconds": 0.0004098329991393257, "report": "/private/var/folders/gb/j1q8qm811b3gjd3gk93fh22h0000gn/T/tmpo86xpc5v/artifacts/manual-features/attempt-11fff3e9f2174b34a05e65b6b415d687/report.json"}
.{"status": "complete", "run_id": "c841f36e8d948a2a7a872acd4fd10a5160b39a4de006dd48d2862322be50464d", "seconds": 0.03241520899973693, "report": "/private/var/folders/gb/j1q8qm811b3gjd3gk93fh22h0000gn/T/tmpb5dbphot/artifacts/manual-features/c841f36e8d948a2a7a872acd4fd10a5160b39a4de006dd48d2862322be50464d/report.json"}
{"status": "complete", "run_id": "31eb9817863de99ae6f2936de8322922f1545938dddcd466bbad0e185e33feed", "seconds": 0.03296754199982388, "report": "/private/var/folders/gb/j1q8qm811b3gjd3gk93fh22h0000gn/T/tmpb5dbphot/artifacts/manual-features/31eb9817863de99ae6f2936de8322922f1545938dddcd466bbad0e185e33feed/report.json"}
.{"status": "complete", "run_id": "c841f36e8d948a2a7a872acd4fd10a5160b39a4de006dd48d2862322be50464d", "seconds": 0.032458208999742055, "report": "/private/var/folders/gb/j1q8qm811b3gjd3gk93fh22h0000gn/T/tmpw1mhcjk4/artifacts/manual-features/c841f36e8d948a2a7a872acd4fd10a5160b39a4de006dd48d2862322be50464d/report.json"}
.{"status": "failed", "run_id": null, "seconds": 0.003886041002260754, "report": "/private/var/folders/gb/j1q8qm811b3gjd3gk93fh22h0000gn/T/tmpi1jx_95j/artifacts/manual-features/attempt-3ad4a525fe764f4b8d05efda1b2d64df/report.json"}
............................................{"status": "complete_produced_unreviewed", "run_id": "3fdaccecc9d3d0abd53017435f7b2e3f53edf7eefe59a438c43b44fd6acec239", "seconds": 0.07656233300076565, "process_cpu_user_system_seconds": 0.08538499999999871}
{"status": "failed", "run_id": null, "seconds": 0.0035291659987706225, "process_cpu_user_system_seconds": 0.0031800000000004047}
.{"status": "failed", "run_id": "3fdaccecc9d3d0abd53017435f7b2e3f53edf7eefe59a438c43b44fd6acec239", "seconds": 0.07550574999913806, "process_cpu_user_system_seconds": 0.08407200000000081}
.{"status": "failed", "run_id": "3fdaccecc9d3d0abd53017435f7b2e3f53edf7eefe59a438c43b44fd6acec239", "seconds": 0.08219070899940562, "process_cpu_user_system_seconds": 0.09203500000000098}
.{"status": "failed", "run_id": "3fdaccecc9d3d0abd53017435f7b2e3f53edf7eefe59a438c43b44fd6acec239", "seconds": 700.0997672920021, "process_cpu_user_system_seconds": 0.09348800000000068}
.{"status": "failed", "run_id": "3fdaccecc9d3d0abd53017435f7b2e3f53edf7eefe59a438c43b44fd6acec239", "seconds": 0.020522709000942996, "process_cpu_user_system_seconds": 0.01980299999999957}
{"status": "failed", "run_id": null, "seconds": 0.0003750420000869781, "process_cpu_user_system_seconds": null}
.{"status": "failed", "run_id": "3fdaccecc9d3d0abd53017435f7b2e3f53edf7eefe59a438c43b44fd6acec239", "seconds": 0.0635098749989993, "process_cpu_user_system_seconds": 0.06979199999999786}
.{"status": "failed", "run_id": "3fdaccecc9d3d0abd53017435f7b2e3f53edf7eefe59a438c43b44fd6acec239", "seconds": 0.06782583300082479, "process_cpu_user_system_seconds": 0.07491399999999793}
.{"status": "failed", "run_id": "3fdaccecc9d3d0abd53017435f7b2e3f53edf7eefe59a438c43b44fd6acec239", "seconds": 0.034182540999609046, "process_cpu_user_system_seconds": 0.03554199999999952}
..{"status": "failed", "run_id": null, "seconds": 0.0007024999977147672, "process_cpu_user_system_seconds": 0.00019100000000094042}
.{"status": "failed", "run_id": "3fdaccecc9d3d0abd53017435f7b2e3f53edf7eefe59a438c43b44fd6acec239", "seconds": 0.0751046250006766, "process_cpu_user_system_seconds": 0.08369000000000071}
.{"status": "failed", "run_id": null, "seconds": 0.0005581660007010214, "process_cpu_user_system_seconds": 8.500000000211116e-05}
.{"status": "failed", "run_id": null, "seconds": 0.0028342920013528783, "process_cpu_user_system_seconds": 0.002342999999999762}
{"status": "failed", "run_id": null, "seconds": 0.0026173330006713513, "process_cpu_user_system_seconds": 0.0022550000000016723}
{"status": "failed", "run_id": null, "seconds": 0.002583292000053916, "process_cpu_user_system_seconds": 0.0022349999999988768}
{"status": "failed", "run_id": null, "seconds": 0.0025722499995026737, "process_cpu_user_system_seconds": 0.002223000000000752}
{"status": "failed", "run_id": null, "seconds": 0.0025755409988050815, "process_cpu_user_system_seconds": 0.0022289999999998145}
.......................................................................................................{"status": "recovered_source_verified_pending_external_acceptance", "directory": "artifacts/feature-program-source-oracle/905b94fc274f46a5b1db600eb22a9dc4", "source_calculations": 0, "fit_attempt_count": 0}
.{"status": "recovered_source_verified_pending_external_acceptance", "directory": "artifacts/feature-program-source-oracle/ce4924c657a34488ab09df76e9cf5c9b", "source_calculations": 0, "fit_attempt_count": 0}
.............................................................{"status": "recovery_verified_pending_external_acceptance", "directory": "artifacts/strong-recoveries/1b472dc0a7474cfe862ef3beb330c45c", "fit_attempt_count": 0}
....{"status": "recovery_verified_pending_external_acceptance", "directory": "artifacts/strong-recoveries/fe22ab86aab742d689dd3d4b5317142e", "fit_attempt_count": 0}
.{"status": "recovery_verified_pending_external_acceptance", "directory": "artifacts/strong-recoveries/244b772cfde34dea8fc790e90479568c", "fit_attempt_count": 0}
..{"status": "recovery_verified_pending_external_acceptance", "directory": "artifacts/strong-recoveries/6a692e78145a4b3eaa903da90e932608", "fit_attempt_count": 0}
.{"status": "recovery_verified_pending_external_acceptance", "directory": "artifacts/strong-recoveries/28eeb542f37c4c4489a69c787264f2bc", "fit_attempt_count": 0}
.{"status": "recovery_verified_pending_external_acceptance", "directory": "artifacts/strong-recoveries/6373bdcee6c0442693ef07ce8c76f8c3", "fit_attempt_count": 0}
................................................................
----------------------------------------------------------------------
Ran 492 tests in 34.165s

OK
```
