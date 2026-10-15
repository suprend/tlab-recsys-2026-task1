"""Two focused pure regressions; no main/native/model execution."""
import ast, copy, hashlib, io, json, pathlib, resource, signal, sys, time, types, unittest
START=time.monotonic(); signal.signal(signal.SIGALRM,signal.SIG_DFL); signal.alarm(15)
resource.setrlimit(resource.RLIMIT_CPU,(14,15))
SOURCE=pathlib.Path('/tmp/tlab-two-accepted-models-validation-once-v2.py')
raw=SOURCE.read_bytes(); ns={'__name__':'pure_boundary_validation'}
exec(compile(raw,str(SOURCE),'exec'),ns)

class BoundaryRegressions(unittest.TestCase):
    def test_authenticated_snapshot_is_the_consumed_source_and_json(self):
        class ReplacingPath:
            def __init__(self,first,later): self.first=first; self.later=later; self.opens=0
            def open(self,mode):
                self.opens+=1
                return io.BytesIO(self.first if self.opens==1 else self.later)
        real_pathlib=ns['pathlib']; ns['pathlib']=types.SimpleNamespace(Path=lambda p:p)
        try:
            src=ReplacingPath(b'def value():\n    return "authenticated"\n',b'def value():\n    return "substituted"\n')
            captured=ns['snapshot'](src,hashlib.sha256(src.first).hexdigest())
            selected=ns['select_functions'](captured,('value',))
            self.assertEqual(selected['value'](),'authenticated'); self.assertEqual(src.opens,1)
            doc=ReplacingPath(b'{"models":{"B":"accepted"}}',b'{"models":{"B":"substituted"}}')
            self.assertEqual(json.loads(ns['snapshot'](doc,hashlib.sha256(doc.first).hexdigest()))['models']['B'],'accepted')
            self.assertEqual(doc.opens,1)
            with self.assertRaises(ValueError): ns['snapshot'](ReplacingPath(b'abcd',b''),hashlib.sha256(b'abcd').hexdigest(),limit=3)
            with self.assertRaises(ValueError): ns['snapshot'](ReplacingPath(b'good',b''),'0'*64)
        finally: ns['pathlib']=real_pathlib
        tree=ast.parse(raw); main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        calls=[n for n in ast.walk(main) if isinstance(n,ast.Call)]
        self.assertFalse(any(isinstance(n.func,ast.Attribute) and n.func.attr=='read_bytes' for n in calls))
        json_calls=[n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='loads']
        self.assertEqual(len(json_calls),2)
        self.assertTrue(all(isinstance(n.args[0],ast.Call) and isinstance(n.args[0].func,ast.Name) and n.args[0].func.id=='snapshot' for n in json_calls))

    def test_primary_baseexception_and_late_failures_cannot_be_pass(self):
        class VerificationAbort(BaseException): pass
        primary=VerificationAbort('original'); report={}; order=[]
        def fail(name,error):
            def call(): order.append(name); raise error
            return call
        actions=[('model_rehash',fail('model_rehash',OSError('hash'))),('resources',fail('resources',RuntimeError('resource')))]
        try: ns['finalize'](report,primary,actions,fail('result_write',ValueError('write')))
        except BaseException as caught: self.assertIs(caught,primary)
        else: self.fail('primary exception disappeared')
        self.assertEqual(order,['model_rehash','resources','result_write'])
        self.assertEqual(report['status'],'FAILED'); self.assertEqual(report['primary_error'],{'stage':'verification','type':'VerificationAbort'})
        self.assertEqual([x['stage'] for x in report['secondary_failures']],order)
        late=OSError('late'); report={}; persisted=[]
        try: ns['finalize'](report,None,[('model_rehash',fail('late',late))],lambda:persisted.append(copy.deepcopy(report)))
        except BaseException as caught: self.assertIs(caught,late)
        else: self.fail('late failure accepted')
        self.assertEqual(persisted[0]['status'],'FAILED')
        report={}; persisted=[]; write_error=OSError('close/fsync')
        def late_write(): persisted.append(copy.deepcopy(report)); raise write_error
        try: ns['finalize'](report,None,[],late_write)
        except BaseException as caught: self.assertIs(caught,write_error)
        else: self.fail('persistence failure accepted')
        self.assertEqual(report['status'],'FAILED')
        self.assertEqual(persisted[0]['status'],'VERIFIED_PENDING_EXTERNAL_ACCEPTANCE')
        self.assertTrue(persisted[0]['external_acceptance_required'])
        self.assertNotEqual(persisted[0]['status'],'PASS')
        successful={}; ns['finalize'](successful,None,[],lambda:None)
        self.assertEqual(successful['status'],'VERIFIED_PENDING_EXTERNAL_ACCEPTANCE')

suite=unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryRegressions)
result=unittest.TextTestRunner(verbosity=2).run(suite)
usage=resource.getrusage(resource.RUSAGE_SELF)
peak=usage.ru_maxrss if sys.platform=='darwin' else usage.ru_maxrss*1024
assert 'catboost' not in sys.modules
assert all(not p.exists() and not p.is_symlink() for p in (ns['GRANT'],ns['OUT'],ns['CACHE']))
assert time.monotonic()-START<=20 and usage.ru_utime+usage.ru_stime<=15 and peak<=128*2**20
record={'version':2,'tests_run':result.testsRun,'unique_focused_methods':2,'failures':len(result.failures),'errors':len(result.errors),'success':result.wasSuccessful(),'script_sha256':hashlib.sha256(raw).hexdigest(),'wall_body_seconds':time.monotonic()-START,'cpu_self_seconds':usage.ru_utime+usage.ru_stime,'peak_self_rss_bytes':peak,'catboost_imported':False,'actual_model_reads_hashes_loads':0,'grant_and_once_paths_absent':True,'scope':'snapshot-consumption and primary-BaseException/finalization boundaries only; no main/native/process/project writes'}
with pathlib.Path('/tmp/tlab-two-model-validation-boundary-pure-result-v2.json').open('x') as f: json.dump(record,f,indent=2,sort_keys=True); f.write('\n')
signal.alarm(0)
if not result.wasSuccessful(): raise SystemExit(1)
