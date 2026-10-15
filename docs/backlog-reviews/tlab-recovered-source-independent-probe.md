# Independent recovered-source consumer probe

Archived actual review script. Publication changes only the machine-specific project root to the current project directory; tests and assertions are unchanged. Original SHA256 `3e1d4b7903d73724f1ab2fc5fb822bf0d3cacd06a57b6f8537aee7fcea6534e9`. Run from the repository root. This archive was not rerun for publication.

```python
from pathlib import Path
import importlib.util,hashlib,sys,unittest
from unittest.mock import patch
root=Path.cwd().resolve();sys.path.insert(0,str(root))
sp=importlib.util.spec_from_file_location('source_author',root/'tests/test_recovered_feature_source.py');a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a);c=a.c
class Independent(a.RecoveredSourceTests):
    def test_independent_late_acceptance_mutation_cannot_return_accepted(self):
        native=c.receipts._sha;fired=[]
        def inject(path,check):
            answer=native(path,check)
            if not fired:
                fired.append(True);self.path.write_bytes(self.path.read_bytes()+b' ')
            return answer
        with patch.object(c.receipts,'_sha',side_effect=inject):
            with self.assertRaisesRegex(ValueError,'acceptance changed'):c.verify_source_acceptance(self.path)
    def test_independent_escaping_symlink_stops_before_streaming(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'private';target.write_text('do not read')
            link=self.root/'inputs/base';link.unlink();link.symlink_to(target)
            with patch.object(c.receipts,'_sha',side_effect=AssertionError('Must not stream outside')):
                with self.assertRaisesRegex(ValueError,'escapes project'):c.verify_source_acceptance(self.path)
    def test_independent_changed_evidence_rejects_before_delegate(self):
        self.put(self.d+'/evidence.json',dict(status='verified',checked_scalar_values=0))
        with self.assertRaisesRegex(ValueError,'Changed source receipt'):c.verify_source_acceptance(self.path)
        c.owner_rules.validate_evidence.assert_not_called()
    def test_independent_first_streaming_guard_preserves_no_skip_contract(self):
        with patch.object(c.receipts,'_sha',side_effect=TimeoutError('Stopped first streaming authentication')):
            with self.assertRaisesRegex(TimeoutError,'Stopped first'):c.verify_source_acceptance(self.path)
suite=unittest.defaultTestLoader.loadTestsFromTestCase(a.RecoveredSourceTests)
suite.addTests(Independent(n) for n in unittest.defaultTestLoader.getTestCaseNames(Independent) if n.startswith('test_independent_'))
r=unittest.TextTestRunner(verbosity=2).run(suite)
if not r.wasSuccessful():raise SystemExit(1)
class BeforePlan(Exception):pass
path=root/'artifacts/acceptance/tlab016-recovered-source-verified.json'
with patch.object(c.source,'prepare_plan',side_effect=BeforePlan('before paid107-plan')):
    try:c.verify_source_acceptance(path)
    except BeforePlan:print('ACTUAL_SMALL_GATE_PASS_before_paid107_plan;0largebytes;notfullverification')
    else:raise AssertionError('No source lineage gate')
expected={'scripts/recovered_feature_source.py':'f3d203bb6cb6f808485981d1a47c3a7d361edcf2579080bae474c500059ad6e5',
 'tests/test_recovered_feature_source.py':'dff5b04a4f42e71b3794feb0f0e0bb082855d9ba3fe8b70f3b70eda29bb63a05',
 'docs/experiments/recovered-feature-source.md':'6a42df789f075b455cfea6fd19eb17af7c0d77cf45c872062d4b37df1ea66376'}
for name,digest in expected.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
print('3_frozen_SHA_PASS')
```
