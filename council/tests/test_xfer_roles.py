"""council.xfer.roles, run.py and queue: halves, seeds, names, paths, one dataset per process, the heavy lock.

Each dataset is activated in its own subprocess (python -I -B), never in the test process: the adapters of the two
datasets must not meet in one process (contract §3 rule 1), and the REES46 tests share this process.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_xfer_roles -v
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np

from council.xfer import queue as Q
from council.xfer import roles
from task1 import exp

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
DATASETS = ('tinkoff', 'sber')
OTHER = {'tinkoff': 'sber', 'sber': 'tinkoff'}
COLLECTIONS = {
    'tinkoff': {'select': 'val-641', 'probe': 'probe-641', 'fit': 'train-461', 'test_anchor': '671'},
    'sber': {'select': 'val-2020-08-19', 'probe': 'probe-2020-08-19', 'fit': 'train-2020-06-10',
             'test_anchor': '2020-09-02'},
}


def _env(period='2020'):
    env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON')}
    env['TASK1_PERIOD'] = period
    return env


def _snap(p):
    """{path: mtime_ns} of a tree (None if it does not exist)."""
    p = Path(p)
    if not p.exists():
        return None
    return {str(Path(d) / n): (Path(d) / n).lstat().st_mtime_ns for d, dirs, files in os.walk(p) for n in dirs + files}


def _rmtree_tlab(path):
    """Remove a temporary tree this test created, only under /tmp/tlab-xfer-test-."""
    path = Path(path)
    if not str(path).startswith('/tmp/tlab-xfer-test-'):
        raise ValueError(path)
    for d, dirs, files in os.walk(path, topdown=False):
        for n in files:
            os.unlink(Path(d) / n)
        for n in dirs:
            os.rmdir(Path(d) / n)
    os.rmdir(path)


def _run(args, period='2020', timeout=300):
    return subprocess.run([PY, '-I', '-B', *args], cwd=ROOT, env=_env(period), capture_output=True, text=True,
                          timeout=timeout)


class HalfTest(unittest.TestCase):
    EXTREMES = [0, 1, 127, 128, 2**31, 2**32 - 1, 2**32, 2**63 - 1, 2**63, 2**63 + 1, 2**64 - 2, 2**64 - 1]

    def test_the_same_as_task1_exp_half(self):
        rng = np.random.default_rng(2026)
        ids = np.concatenate([rng.integers(0, 2**63, 5000, dtype=np.uint64) * np.uint64(2)
                              + rng.integers(0, 2, 5000, dtype=np.uint64),          # the whole uint64 range
                              rng.integers(0, 10**7, 5000, dtype=np.uint64),
                              np.array(self.EXTREMES, dtype=np.uint64)])
        self.assertTrue((ids > np.uint64(2**63)).any())
        expected = exp.half(ids)
        self.assertEqual(list(roles.halves(ids)), list(expected))
        self.assertEqual([roles.half(int(u)) for u in ids], list(expected))

    def test_wraparound_is_explicit(self):
        for u in self.EXTREMES:
            h = (u * roles.HALF_MULTIPLIER) % 2**64
            self.assertEqual(roles.half(u), 'A' if (h >> 7) % 2 == 0 else 'B', u)
            self.assertEqual(roles.half(u), str(exp.half(np.array([u], dtype=np.uint64))[0]), u)

    def test_int64_and_scalar_inputs(self):
        ids = np.arange(0, 20000, 7, dtype=np.int64)
        self.assertEqual(list(roles.halves(ids)), list(exp.half(ids)))
        self.assertEqual(roles.halves(12345).shape, (1,))
        self.assertEqual(roles.halves(12345)[0], roles.half(12345))

    def test_both_halves_are_large(self):
        h = roles.halves(np.arange(100000, dtype=np.uint64))
        self.assertTrue(0.45 < (h == 'A').mean() < 0.55)


class SeedsAndNamesTest(unittest.TestCase):
    def test_seeds(self):
        self.assertEqual([roles.plan_seed(r) for r in (1, 48)], [1001, 1048])
        for bad in (0, 49, 1.0, True, '3'):
            with self.assertRaises(ValueError):
                roles.plan_seed(bad)
        self.assertEqual(sum(len(s) for s in roles.TEST_FITS.values()), 14)
        self.assertEqual(sum(len(s) for s in roles.TEST_FITS_ALLP.values()), 2)
        self.assertEqual(roles.TEST_FITS['Hrp'], roles.TEST_SEEDS)
        self.assertEqual(roles.TEST_FITS['SEL'], roles.TEST_SEEDS)
        self.assertTrue(set(roles.TEST_FITS) | set(roles.TEST_FITS_ALLP) <= set(roles.ARMS))
        self.assertFalse(set(roles.CONFIRM_SEEDS) & {roles.plan_seed(r) for r in range(1, 49)})
        self.assertEqual(roles.placebo_key(641)[:2], [roles.PLACEBO_SEED, 0])

    def test_recipe_is_the_xfer_recipe(self):
        from scripts import xfer_common as xc
        self.assertEqual(roles.recipe_for(7), dict(xc.RECIPE, random_seed=7))
        self.assertEqual(roles.recipe_for(7)['random_seed'], 7)
        self.assertEqual(roles.recipe_for(7), roles.recipe_for(7.0))

    def test_roles(self):
        self.assertEqual(roles.SERIES['select'], 'dev')
        self.assertEqual(roles.COLLECTION_ROLES['select'], 'val')
        self.assertEqual(roles.COLLECTION_ROLES['fit'], 'train')
        self.assertEqual(roles.SERIES['test'], roles.COLLECTION_ROLES['test'])
        self.assertEqual(roles.PHASES, ('fit', 'select', 'probe', 'test'))

    def test_names(self):
        self.assertEqual(roles.sandbox_column('f_x_c3_gap_days'), 'ag_c3_gap_days')
        self.assertEqual(roles.sandbox_column('f_x_c3_gap_days_tw'), 'ag_c3_gap_days_tw')
        for bad in ('f_x_c5_gap', 'ag_c3_gap', 'f_x_c3_' + 'a' * 37, 'f_x_c3_Gap'):
            with self.assertRaises(ValueError):
                roles.sandbox_column(bad)
        self.assertEqual(roles.family_table('G3-2'), 'g3_2')
        self.assertEqual(roles.twin_table('G1-10'), 'g1_10_tw')
        self.assertEqual(roles.rb_table(2, 'repeat_gap'), 'rb2_repeat_gap')
        for k, slug in ((3, 'x'), (1, 'Bad'), (1, '')):
            with self.assertRaises(ValueError):
                roles.rb_table(k, slug)
        with self.assertRaises(ValueError):
            roles.family_table('G5-1')
        self.assertEqual(roles.council_columns_in(['ag_c1_x', 'ag_rb1_y', 'ag_plc_z', 'ag_cooc30', 'ag_mom_30']),
                         ['ag_c1_x', 'ag_plc_z', 'ag_rb1_y'])

    def test_the_agent_sets_have_no_council_names(self):
        for x in DATASETS:
            s = json.loads((ROOT / 'configs' / 'datasets' / f'xfer-{x}-set.json').read_text(encoding='utf-8'))
            cols = [c for p in s['proposals'] for c in p['columns']]
            self.assertTrue(cols, x)
            self.assertEqual(roles.council_columns_in(cols), [], x)


class PathsTest(unittest.TestCase):
    def test_paths_are_council_paths(self):
        xfer = (ROOT / 'artifacts' / 'xfer').resolve()
        seen = set()
        for x in DATASETS:
            p = roles.paths(x)
            files = [p.runs, p.out, p.fits, p.fit_records, p.probes, p.sidecars, p.reads, p.llm_log, p.prompts,
                     p.replies, p.queue_log, p.selection, p.approved, p.prereg(0), p.queue('plan'),
                     p.run_file('curation.json'), p.scores('plan', 'r07', 1007), p.probe_ref(641),
                     p.table('val-641', 'g1_1')]
            for f in files:
                self.assertFalse(f.resolve().is_relative_to(xfer), f)
                self.assertNotIn(OTHER[x], str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f))
            self.assertEqual(p.runs, ROOT / 'council' / 'runs' / f'xfer-{x}')
            self.assertEqual(p.out, ROOT / 'artifacts' / 'council' / f'xfer-{x}')
            self.assertEqual(p.scores('plan', 'r07', 1007), p.out / 'fits' / 'plan' / 'r07-1007' / 'scores.parquet')
            self.assertEqual(p.table('val-641', 'g1_1'), p.out / 'sidecars' / 'val-641' / 'g1_1.parquet')
            seen.add(p.llm)
        for bad in ('../x', 'a/b', '.hidden'):
            with self.assertRaises(ValueError):
                roles.paths('tinkoff').run_file(bad)
        with self.assertRaises(ValueError):
            roles.paths('tinkoff').queue('Plan 2')
        with self.assertRaises(Exception):
            roles.paths('rees46')
        self.assertEqual(seen, {Path('/tmp/tlab-council-llm-a'), Path('/tmp/tlab-council-llm-b')})

    def test_the_llm_dirs_name_no_dataset(self):
        for x in DATASETS:
            d = str(roles.llm_dir(x)).lower()
            for word in ('tinkoff', 'sber', 'xfer', 't-bank', 'rees46', 'kuper'):
                self.assertNotIn(word, d)

    def test_import_builds_nothing(self):
        """Importing roles and queue activates nothing; paths() on a root that does not exist names every file
        below it and creates none of them, nor the root; the default paths' existence does not change."""
        self.assertIsNone(roles._ACTIVE)
        root = Path(tempfile.mkdtemp(prefix='tlab-xfer-test-', dir='/tmp')) / 'not-created'
        defaults = [d for x in DATASETS for d in (roles.paths(x).runs, roles.paths(x).out, roles.paths(x).llm)]
        before = [d.exists() for d in defaults]
        try:
            for x in DATASETS:
                p = roles.paths(x, root)
                names = [p.fits, p.fit_records, p.probes, p.sidecars, p.reads, p.llm_log, p.prompts, p.replies,
                         p.queue_log, p.selection, p.approved, p.prereg(0), p.queue('plan'), p.scores('plan', 'r01', 1001),
                         p.probe_ref(641), p.table('val-641', 'g1_1'), p.runs, p.out, p.llm]
                self.assertTrue(all(n.is_relative_to(root) for n in names), x)
                self.assertEqual(p.root, root)
                self.assertFalse(any(n.exists() for n in names), x)
            self.assertFalse(root.exists())
            self.assertEqual([d.exists() for d in defaults], before)
            self.assertIsNone(roles._ACTIVE)
        finally:
            root.parent.rmdir()

    def test_roots(self):
        for good in ('/tmp/tlab-x', '/tmp/tlab-x/y/z', '/private/tmp/tlab-run'):
            self.assertEqual(roles.check_root(good), Path(good))
        for bad in ('/tmp', '/tmp/tlab-', '/tmp/other', '/tmp/tlab-x/../../etc', 'tlab-x', '/Users/tlab-x',
                    str(ROOT), '/tmp/x/tlab-y'):
            with self.assertRaises(ValueError, msg=bad):
                roles.check_root(bad)
            with self.assertRaises(ValueError, msg=bad):
                roles.paths('tinkoff', bad)
        p = roles.paths('sber', '/tmp/tlab-r')
        self.assertEqual(p.runs, Path('/tmp/tlab-r/council/runs/xfer-sber'))
        self.assertEqual(p.out, Path('/tmp/tlab-r/artifacts/council/xfer-sber'))
        self.assertEqual(p.llm, Path('/tmp/tlab-r/tlab-council-llm-b'))
        self.assertIsNone(roles.paths('sber').root)


PROCESS = textwrap.dedent('''
    import json, os, sys
    from pathlib import Path
    ROOT = Path(sys.argv[1]); x = sys.argv[2]; other = sys.argv[3]
    sys.path.append(str(ROOT))

    def snap(p):
        p = Path(p)
        if not p.exists():
            return None
        out = {}
        for d, dirs, files in os.walk(p):
            for n in dirs + files:
                q = Path(d) / n
                out[str(q)] = q.lstat().st_mtime_ns
        return out

    letter = {'tinkoff': 'a', 'sber': 'b'}[x]
    watched = [ROOT / 'council' / 'runs' / f'xfer-{x}', ROOT / 'artifacts' / 'council', Path(f'/tmp/tlab-council-llm-{letter}'),
               ROOT / 'artifacts' / 'xfer' / x]
    before = [snap(p) for p in watched]
    out = {}

    from council.xfer import roles
    ds = roles.activate(x)
    from scripts import xfer_common as xc
    first = xc.code_identity(x)
    import council.evidence, council.design
    from council.xfer import broker, compute, curate, fit, plan, queue, sandbox
    out['identity_after_evidence'] = xc.code_identity(x) == first
    out['identity_is_prereg'] = roles.identity(ds)['code'] == roles.prereg_code(ds)
    out['stamp'] = sorted(roles.council_stamp())
    out['collections'] = {ph: ds.collection(ph).name for ph in ('select', 'probe')}
    out['collections']['fit'] = ds.collection('fit', ds.fit_anchors[0]).name
    out['test'] = str(ds.test_anchor)
    out['test_collection'] = ds.collection('test').name
    out['fit_anchors'] = [str(a) for a in ds.fit_anchors]
    out['test_train'] = [str(a) for a in ds.test_train_anchors]
    out['s0'] = str(ds.s0_anchor)
    out['probe_anchors'] = [str(a) for a in ds.probe_anchors]
    out['phases'] = [ds.phase_of(a) for a in ds.test_train_anchors]
    out['K'] = ds.K
    out['qid'] = ds.qid(ds.s0_anchor, 18446744073709551615)
    out['same'] = roles.activate(x) is ds
    try:
        roles.activate(other)
        out['other'] = 'activated'
    except Exception as e:
        out['other'] = type(e).__name__
    try:
        ds.collection('fit')
        out['fit_without_anchor'] = 'returned'
    except ValueError:
        out['fit_without_anchor'] = 'ValueError'
    try:
        ds.collection('select', ds.fit_anchors[0])
        out['wrong_anchor'] = 'returned'
    except ValueError:
        out['wrong_anchor'] = 'ValueError'
    out['other_adapter_loaded'] = xc.ADAPTERS[other] in sys.modules
    try:
        roles.activate(x, root='/tmp/tlab-another-root')
        out['other_root'] = 'activated'
    except Exception as e:
        out['other_root'] = type(e).__name__
    out['identity'] = roles.identity(ds)
    out['fit_command'] = queue.fit_command(ds, Path('/tmp/q/spec.json'), Path('/tmp/q/stamp.json'),
                                           Path('/tmp/q/data.json'))
    # the old form (the stamp as JSON in argv) would have matched a foreign xfer process
    out['old_form_foreign'] = queue.is_foreign(' '.join(out['fit_command'][:-4] + ['--stamp', json.dumps(out['identity'])]))
    after = [snap(p) for p in watched]
    out['unchanged'] = {str(p): a == b for p, a, b in zip(watched, before, after)}
    print(json.dumps(out))
''')


ROOT_PROCESS = textwrap.dedent('''
    import json, sys
    from pathlib import Path
    ROOT = Path(sys.argv[1]); x = sys.argv[2]; root = Path(sys.argv[3])
    sys.path.append(str(ROOT))
    from council.xfer import roles
    ds = roles.activate(x, root=root)
    import council.evidence
    from council.xfer import broker, compute, curate, fit, plan, queue, sandbox
    out = {'runs': str(ds.paths.runs), 'out': str(ds.paths.out), 'llm': str(ds.paths.llm), 'root': str(ds.paths.root),
           'exists': root.exists(), 'same': roles.activate(x, root=root) is ds}
    try:
        roles.activate(x)
        out['default_root'] = 'activated'
    except Exception as e:
        out['default_root'] = type(e).__name__
    out['fit_command'] = queue.fit_command(ds, root / 's.json', root / 't.json', root / 'd.json')
    print(json.dumps(out))
''')


class ProcessTest(unittest.TestCase):
    """One subprocess per dataset: activation, identity, collections, no file created, the other dataset refused."""

    results = {}

    @classmethod
    def setUpClass(cls):
        for x in DATASETS:
            r = _run(['-c', PROCESS, str(ROOT), x, OTHER[x]])
            if r.returncode:
                raise AssertionError(f'{x}: {r.stderr[-3000:]}')
            cls.results[x] = json.loads(r.stdout.strip().splitlines()[-1])

    def test_nothing_is_created_or_touched(self):
        for x, r in self.results.items():
            self.assertTrue(all(r['unchanged'].values()), (x, r['unchanged']))

    def test_code_identity_survives_council_evidence(self):
        for x, r in self.results.items():
            self.assertTrue(r['identity_after_evidence'], x)
            self.assertTrue(r['identity_is_prereg'], x)

    def test_one_dataset_per_process(self):
        for x, r in self.results.items():
            self.assertEqual(r['other'], 'ContractError', x)
            self.assertFalse(r['other_adapter_loaded'], x)
            self.assertTrue(r['same'], x)

    def test_collections_and_anchors(self):
        for x, r in self.results.items():
            c = COLLECTIONS[x]
            self.assertEqual(r['collections'], {k: c[k] for k in ('select', 'probe', 'fit')}, x)
            self.assertEqual(r['test'], c['test_anchor'], x)
            self.assertTrue(r['test_collection'].endswith(c['test_anchor']), (x, r['test_collection']))
            self.assertEqual(r['test_train'], r['fit_anchors'] + [r['s0']], x)
            self.assertEqual(r['phases'], ['fit'] * len(r['fit_anchors']) + ['select'], x)
            self.assertEqual(r['probe_anchors'], [r['s0'], r['fit_anchors'][-1]], x)
            self.assertEqual(r['K'], {'tinkoff': 20, 'sber': 50}[x])
            self.assertEqual(r['qid'], f"{r['s0']}:18446744073709551615")
            self.assertEqual(r['fit_without_anchor'], 'ValueError')
            self.assertEqual(r['wrong_anchor'], 'ValueError')

    def test_root_of_the_process(self):
        for x in DATASETS:
            self.assertEqual(self.results[x]['other_root'], 'ContractError')
            root = Path(tempfile.mkdtemp(prefix='tlab-xfer-test-', dir='/tmp')) / 'root'
            try:
                r = _run(['-c', ROOT_PROCESS, str(ROOT), x, str(root)])
                self.assertEqual(r.returncode, 0, r.stderr[-3000:])
                out = json.loads(r.stdout.strip().splitlines()[-1])
                self.assertFalse(out['exists'])
                self.assertFalse(root.exists())
                self.assertTrue(out['same'])
                self.assertEqual(out['default_root'], 'ContractError')
                for k in ('runs', 'out', 'llm'):
                    self.assertTrue(out[k].startswith(str(root) + '/'), (k, out[k]))
                cmd = out['fit_command']
                self.assertEqual(cmd[cmd.index('--root') + 1], str(root))
                self.assertLess(cmd.index('--root'), cmd.index('fit-one'))
            finally:
                root.parent.rmdir()
        r = _run(['-c', ROOT_PROCESS, str(ROOT), 'tinkoff', '/tmp/not-a-tlab-root'])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('/tmp/tlab-', r.stderr)

    def test_fit_command_carries_no_stamp(self):
        for x, r in self.results.items():
            cmd = r['fit_command']
            self.assertIn('scripts/xfer_model.py', r['identity']['code'], x)
            self.assertTrue(r['old_form_foreign'], x)           # the check below would catch the old argv
            self.assertFalse(Q.is_foreign(' '.join(cmd)), (x, cmd))
            self.assertEqual(cmd[cmd.index('--stamp') + 1], '/tmp/q/stamp.json')
            self.assertEqual(cmd[cmd.index('--data') + 1], '/tmp/q/data.json')
            self.assertNotIn('--root', cmd)
            self.assertFalse(any('{' in a for a in cmd), cmd)

    def test_the_stamp_covers_the_package_and_design(self):
        for r in self.results.values():
            self.assertIn('council/design.py', r['stamp'])
            self.assertIn('council/xfer/roles.py', r['stamp'])
            self.assertIn('council/xfer/fit.py', r['stamp'])
            for m in ('broker', 'plan', 'queue', 'run'):
                self.assertIn(f'council/xfer/{m}.py', r['stamp'])
            for m in ('agents', 'sandbox', 'curate', 'compute', '__init__'):      # pinned by outputs (§12.1)
                self.assertNotIn(f'council/xfer/{m}.py', r['stamp'])


ROUTING = textwrap.dedent('''
    """Every stage of run.py reaches its function: the targets are replaced by recorders (nothing real runs)."""
    import json, sys, types
    from pathlib import Path
    ROOT = Path(sys.argv[1]); tmp = Path(sys.argv[2])
    sys.path.append(str(ROOT))
    from council.xfer import run, broker, compute, curate, fit, plan, queue, sandbox
    calls = {}
    stage = {}

    def recorder(target, ret=None, extra=None):
        def f(ds, *a, **k):
            calls[stage['now']] = {'target': target, 'root': str(ds.paths.root),
                                   'extra': extra(a, k) if extra else None}
            return ret
        return f

    agents = types.ModuleType('council.xfer.agents')
    for name in ('reference', 'wave1', 'cross_exam', 'author_replies', 'prereg1'):
        setattr(agents, name, recorder('agents.' + name, extra=(lambda a, k: list(a)) if name == 'reference' else None))
    sys.modules['council.xfer.agents'] = agents
    plan.path_queue = recorder('plan.path_queue', [])
    plan.prereg0 = recorder('plan.prereg0')
    plan.build = recorder('plan.build')
    plan.analyze = recorder('plan.analyze')
    plan.select = recorder('plan.select', extra=lambda a, k: [list(k.get('cut', ())), k.get('cut_plan')])
    plan.test_queue = recorder('plan.test_queue', [])
    plan.read_test = recorder('plan.read_test')
    queue.run = recorder('queue.run', [], lambda a, k: [str(a[0]), k.get('wait')])
    curate.stage = recorder('curate.stage')
    compute.stage = recorder('compute.stage', extra=lambda a, k: [k.get('threads')])
    broker.start_test = recorder('broker.start_test')
    sandbox.probe_stage = recorder('sandbox.probe_stage', {'cards': {}}, lambda a, k: {
        'cards': [c['id'] for c in a[0]], 'reference': {str(n): [p['table'] for p in v] for n, v in a[1].items()},
        'threads': k.get('threads'), 'gate': k['gate']()})
    fit.main = recorder('fit.main', 0, lambda a, k: list(a[0]))
    seen = []
    queue.heavy_now = lambda journals, lock_path=None: seen.append([str(j) for j in journals])   # not the real lock

    runs = tmp / 'council' / 'runs' / 'xfer-tinkoff'
    runs.mkdir(parents=True)
    (runs / 'cards-wave1.json').write_text(json.dumps({'cards': [{'id': 'G1-1'}]}))
    (runs / 'reference-rb1.json').write_text(json.dumps({'proposals': [{'table': 'rb1_x', 'level': 'user',
                                                                         'sql': 'SELECT 1', 'columns': []}]}))
    (tmp / 's.json').write_text('{}')
    (tmp / 't.json').write_text(json.dumps({'code': {'scripts/xfer_model.py': 'a'}}))
    (tmp / 'd.json').write_text(json.dumps({'frame': 'b'}))
    extra = {'queue': ['plan'], 'reference': ['--k', '2'], 'compute': ['--threads', '3'], 'evidence': ['--threads', '3'],
             'select': ['--cut', 'Rb1,Rb2'],
             'fit-one': ['--spec', str(tmp / 's.json'), '--stamp', str(tmp / 't.json'), '--data', str(tmp / 'd.json')]}
    for name in run.STAGES:
        if name in ('info', 'stages'):
            continue
        stage['now'] = name
        try:
            run.main(['--dataset', 'tinkoff', '--root', str(tmp), name, *extra.get(name, [])])
        except SystemExit as e:
            if e.code not in (0, None):
                raise
    calls['evidence']['journals'] = seen
    print(json.dumps(calls))
''')


class RunTest(unittest.TestCase):
    RUN = str(ROOT / 'council' / 'xfer' / 'run.py')

    def test_info(self):
        for x in DATASETS:
            r = _run([self.RUN, '--dataset', x, 'info'])
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            out = json.loads(r.stdout)
            self.assertEqual(out['dataset'], x)
            self.assertTrue(out['code_matches_prereg'])
            self.assertEqual(out['paths']['llm'], str(roles.llm_dir(x)))

    def test_stages(self):
        r = _run([self.RUN, '--dataset', 'tinkoff', 'stages'])
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertIn('fit-one', json.loads(r.stdout))

    def test_refusals(self):
        r = _run([self.RUN, '--dataset', 'tinkoff', 'info'], period='2019')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('TASK1_PERIOD', r.stderr)
        r = subprocess.run([PY, '-B', self.RUN, '--dataset', 'tinkoff', 'info'], cwd=ROOT, env=_env(),
                           capture_output=True, text=True, timeout=120)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('python -I', r.stderr)
        r = _run([self.RUN, '--dataset', 'tinkoff', 'queue'])
        self.assertNotEqual(r.returncode, 0)
        r = _run([self.RUN, '--dataset', 'tinkoff', 'info', '--data', '{}', '--bogus'])
        self.assertNotEqual(r.returncode, 0)

    def test_unset_period_is_set(self):
        env = {k: v for k, v in _env().items() if k != 'TASK1_PERIOD'}
        r = subprocess.run([PY, '-I', '-B', self.RUN, '--dataset', 'sber', 'stages'], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])

    def test_stages_on_a_test_root_leave_the_repository_alone(self):
        """Contract §8.8: stages run on a temporary root; artifacts/xfer, the council paths of the repository and
        the default LLM directories keep their listing and mtimes."""
        watched = [ROOT / 'artifacts' / 'xfer', ROOT / 'artifacts' / 'council',
                   *[roles.paths(x).runs for x in DATASETS], *[roles.llm_dir(x) for x in DATASETS]]
        before = [_snap(p) for p in watched]
        tmp = Path(tempfile.mkdtemp(prefix='tlab-xfer-test-', dir='/tmp'))
        try:
            for x in DATASETS:
                r = _run([self.RUN, '--dataset', x, '--root', str(tmp), 'info'])
                self.assertEqual(r.returncode, 0, r.stderr[-2000:])
                out = json.loads(r.stdout)
                self.assertEqual(out['paths']['root'], str(tmp))
                self.assertEqual(out['paths']['runs'], str(tmp / 'council' / 'runs' / f'xfer-{x}'))
                self.assertEqual(out['paths']['llm'], str(roles.llm_dir(x, tmp)))
            r = _run(['-c', ROUTING, str(ROOT), str(tmp)])
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            calls = json.loads(r.stdout.strip().splitlines()[-1])
        finally:
            _rmtree_tlab(tmp)
        self.assertEqual([_snap(p) for p in watched], before)
        expected = {
            'queue-path': 'plan.path_queue', 'queue': 'queue.run', 'prereg0': 'plan.prereg0',
            'reference': 'agents.reference', 'wave1': 'agents.wave1', 'evidence': 'sandbox.probe_stage',
            'cross': 'agents.cross_exam', 'authors': 'agents.author_replies', 'prereg1': 'agents.prereg1',
            'curate': 'curate.stage', 'compute': 'compute.stage', 'plan-build': 'plan.build', 'analyze': 'plan.analyze',
            'select': 'plan.select', 'start-test': 'broker.start_test', 'test-queue': 'plan.test_queue',
            'read-test': 'plan.read_test', 'fit-one': 'fit.main',
        }
        self.assertEqual({k: v['target'] for k, v in calls.items()}, expected)
        root = str(tmp)
        self.assertTrue(all(v['root'] == root for v in calls.values()), calls)
        self.assertEqual(calls['queue']['extra'], [str(tmp / 'council' / 'runs' / 'xfer-tinkoff' / 'queue-plan.json'), True])
        self.assertEqual(calls['reference']['extra'], [2])
        self.assertEqual(calls['compute']['extra'], [3])
        self.assertEqual(calls['select']['extra'], [['Rb1', 'Rb2'], False])
        ev = calls['evidence']['extra']
        self.assertEqual(ev['cards'], ['G1-1'])
        self.assertEqual(ev['reference'], {'1': ['rb1_x']})
        self.assertEqual(ev['threads'], 3)
        self.assertIsInstance(ev['gate'], list)          # the gate is a callable returning reasons
        self.assertEqual(calls['evidence']['journals'],
                         [[str(tmp / 'council' / 'runs' / f'xfer-{x}' / 'queue.jsonl') for x in DATASETS]])
        fit_argv = calls['fit-one']['extra']
        self.assertEqual(fit_argv[:2], ['--spec', str(tmp / 's.json')])
        self.assertEqual(json.loads(fit_argv[3]), {'code': {'scripts/xfer_model.py': 'a'}})   # read from the file
        self.assertEqual(json.loads(fit_argv[5]), {'frame': 'b'})

    def test_a_root_outside_tmp_tlab_is_refused(self):
        for bad in ('/tmp/other', str(ROOT)):
            r = _run([self.RUN, '--dataset', 'sber', '--root', bad, 'info'])
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('/tmp/tlab-', r.stderr)


class QueueTest(unittest.TestCase):
    REES46 = [
        '/Users/u/tlab-recsys-2026/.venv/bin/python -m council.fit --spec /tmp/plan_r01.json',
        'python -m council.queue plan',
        'python3 -m council.memory --trial 2',
        '.venv/bin/python -m council.agents compute --threads 8',
        '.venv/bin/python -I scripts/xfer_model.py --dataset tinkoff series dev',
        '.venv/bin/python -I -m scripts.xfer_agent --dataset sber sidecar',
        '/abs/path/.venv/bin/python -I /abs/path/scripts/xfer_sber.py build',
        'python3.12 scripts/xfer_tinkoff.py sidecar --dataset tinkoff',
        '/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -I scripts/xfer_model.py x',
        'python -m scripts.xfer_model --dataset sber series holdout',
    ]
    OURS = [
        '.venv/bin/python -I council/xfer/run.py --dataset tinkoff fit-one --spec /tmp/x.json',
        '.venv/bin/python -I council/xfer/run.py --dataset sber queue plan',
        'python -m council.xfer.run --dataset tinkoff compute',
        'python -m council.agents wave1',
        'python -m council.fitness',
        'python -m unittest council.tests.test_fit',
        'vim council/fit.py',
        'python -m council.xfer.queue',
        'grep scripts.py',
        'vim scripts/xfer_model.py',
        'nvim /Users/u/tlab-recsys-2026/scripts/xfer_agent.py',
        'grep -n training_block scripts/xfer_model.py',
        'rg scripts.xfer_ council',
        'git diff scripts/xfer_common.py',
        'less scripts/xfer_sber.py',
        'python -m unittest council.tests.test_xfer_roles',
        'python -c "print(1)" scripts/xfer_notes.txt',
    ]

    def test_patterns(self):
        for cmd in self.REES46:
            self.assertTrue(Q.is_foreign(cmd), cmd)
        for cmd in self.OURS:
            self.assertFalse(Q.is_foreign(cmd), cmd)

    def test_own_process_and_parent_are_excluded(self):
        procs = [(os.getpid(), 1, 'python -m council.queue plan'), (os.getppid(), 1, 'python -m council.fit'),
                 (999999, 1, 'python -m council.memory')]
        self.assertEqual([p for p, _ in Q.foreign(procs)], [999999])
        self.assertEqual(Q.foreign(procs, own={999999, os.getpid(), os.getppid()}), [])
        with self.assertRaises(Q.Busy):
            Q.check(procs)
        Q.check(procs[:2])

    def test_processes_lists_this_process(self):
        procs = Q.processes()
        self.assertIn(os.getpid(), [p for p, _, _ in procs])

    def test_lock_is_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'heavy.lock'
            f = Q.try_lock(path)
            self.assertIsNotNone(f)
            self.assertIsNone(Q.try_lock(path))
            self.assertIsNotNone(Q.lock_holder(path))
            Q.release(f)
            self.assertIsNone(Q.lock_holder(path))
            g = Q.try_lock(path)
            self.assertIsNotNone(g)
            Q.release(g)

    def test_heavy_waits_for_foreign_then_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'queue.jsonl'
            lock = Path(tmp) / 'heavy.lock'
            calls = {'n': 0}

            def procs():
                calls['n'] += 1
                return [(999999, 1, 'python -m council.fit --spec s.json')] if calls['n'] <= 2 else []

            slept = []
            with Q.heavy('compute', 'tinkoff', log=log, lock_path=lock, procs_fn=procs, sleep=slept.append,
                         poll=0.01, own=set()):
                self.assertIsNone(Q.try_lock(lock))
                holder = Q.lock_holder(lock)
                self.assertEqual(holder['what'], 'compute')
            self.assertEqual(len(slept), 2)
            events = [e['event'] for e in Q.entries(log)]
            self.assertEqual(events, ['wait', 'start', 'end'])
            self.assertTrue(Q.entries(log)[-1]['ok'])
            self.assertIsNone(Q.lock_holder(lock))

    def test_heavy_refuses_without_wait_and_releases_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'queue.jsonl'
            lock = Path(tmp) / 'heavy.lock'
            busy = lambda: [(999999, 1, 'python -m council.queue plan')]
            with self.assertRaises(Q.Busy):
                with Q.heavy('fit x', 'sber', log=log, lock_path=lock, procs_fn=busy, wait=False, own=set()):
                    self.fail('ran next to a foreign process')
            held = Q.try_lock(lock)
            with self.assertRaises(Q.Busy):
                with Q.heavy('fit y', 'sber', log=log, lock_path=lock, procs_fn=lambda: [], wait=False, own=set()):
                    self.fail('ran without the lock')
            Q.release(held)
            with self.assertRaises(KeyError):
                with Q.heavy('fit z', 'sber', log=log, lock_path=lock, procs_fn=lambda: [], own=set()):
                    raise KeyError('boom')
            self.assertIsNone(Q.lock_holder(lock))
            ev = Q.entries(log)
            self.assertEqual([e['event'] for e in ev], ['refused', 'refused', 'start', 'end'])
            self.assertFalse(ev[-1]['ok'])

    def test_heavy_journals_the_peak_rss(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'queue.jsonl'
            with Q.heavy('compute', 'tinkoff', log=log, lock_path=Path(tmp) / 'l', procs_fn=lambda: [], own=set()):
                pass
            end = Q.entries(log)[-1]
            self.assertEqual(end['event'], 'end')
            self.assertGreater(end['peak_gb'], 0.01)         # this test process holds numpy and pandas
            self.assertLess(end['peak_gb'], 64)               # bytes on macOS, KB on Linux: the unit is right
            self.assertEqual(Q.peaks(log), {'compute': end['peak_gb']})

    def test_the_lock_is_inherited_by_the_child(self):
        """pass_fds: the child keeps the flock after the parent closed its file (a parent that died)."""
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / 'heavy.lock'
            f = Q.try_lock(lock)
            flag = Path(tmp) / 'started'
            child = subprocess.Popen([PY, '-I', '-c', f'import pathlib, time; pathlib.Path({str(flag)!r}).touch(); '
                                      'time.sleep(2)'], pass_fds=(f.fileno(),))
            try:
                f.close()                                  # no LOCK_UN: the parent "dies"
                self.assertIsNone(Q.try_lock(lock), 'the child should hold the lock')
                child.wait(timeout=30)
                g = Q.try_lock(lock)
                self.assertIsNotNone(g, 'the lock is free once the child exits')
                Q.release(g)
            finally:
                if child.poll() is None:
                    child.kill()
            # spawn() is the queue's form of the same: the child sees the inherited descriptor
            f = Q.try_lock(lock)
            probe = f'import os; os.fstat({f.fileno()}); print("ok")'
            r = Q.spawn([PY, '-I', '-c', probe], f, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.stdout.strip(), 'ok', r.stderr)
            r = subprocess.run([PY, '-I', '-c', probe], capture_output=True, text=True, timeout=60)
            Q.release(f)
            self.assertNotEqual(r.returncode, 0)          # without pass_fds the descriptor is not inherited

    def test_light_gate(self):
        self.assertEqual(Q.light_gate('llm', procs=[(999999, 1, 'python -m council.fit --spec /nonexistent')],
                                      own=set(), heavy={'what': 'fit x', 'peak_gb': None}), [])
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / 'plan.json'
            plan.write_text(json.dumps({'recipe': 'plan'}))
            full = Path(tmp) / 'full.json'
            full.write_text(json.dumps({'recipe': 'full_val'}))
            p_plan = [(999999, 1, f'python -m council.fit --spec {plan}')]
            p_full = [(999999, 1, f'python -m council.fit --spec {full}')]
            p_bad = [(999999, 1, 'python -m council.fit --spec /nonexistent/x.json')]
            self.assertEqual(Q.light_gate('probe', procs=p_plan, own=set(), heavy={'what': 'fit a', 'peak_gb': 12.0}), [])
            self.assertEqual(Q.light_gate('probe', procs=p_plan, own=set(), heavy=None), [])
            self.assertEqual(len(Q.light_gate('probe', procs=p_full, own=set())), 1)
            self.assertEqual(len(Q.light_gate('probe', procs=p_bad, own=set())), 1)
            self.assertEqual(len(Q.light_gate('probe', procs=[], own=set(), heavy={'what': 'fit', 'peak_gb': 21.0})), 1)
            self.assertEqual(Q.light_gate('probe', procs=[], own=set(), heavy={'what': 'fit', 'peak_gb': 20.0}), [])
            unknown = Q.light_gate('probe', procs=[], own=set(), heavy={'what': 'compute', 'peak_gb': None})
            self.assertEqual(len(unknown), 1)
            self.assertIn('no journalled peak', unknown[0])
            for cmd in ('python -m council.memory full_test', 'python -m council.agents run compute'):
                found = Q.light_gate('probe', procs=[(999999, 1, cmd)], own=set())
                self.assertEqual(len(found), 1, cmd)
                self.assertIn('no known peak', found[0])
            self.assertEqual(Q.light_gate('llm', procs=[(999999, 1, 'python -m council.memory')], own=set()), [])
            with self.assertRaises(ValueError):
                Q.light_gate('compute', procs=[], own=set())

    def test_peaks_and_heavy_now(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'q.jsonl'
            Q.journal(log, {'event': 'peak', 'what': 'fit plan-r01-1001', 'peak_gb': 7.5})
            Q.journal(log, {'event': 'end', 'what': 'fit plan-r02-1002', 'peak_gb': 9.0})
            Q.journal(log, {'event': 'peak', 'what': 'fit b', 'peak_gb': None})
            Q.journal(log, {'event': 'end', 'what': 'compute', 'peak_gb': True})
            self.assertEqual(Q.peaks(log), {'fit plan-r01-1001': 7.5, 'fit plan-r02-1002': 9.0})
            lock = Path(tmp) / 'heavy.lock'
            journals = [log, Path(tmp) / 'missing.jsonl']
            self.assertIsNone(Q.heavy_now(journals, lock_path=lock))
            with Q.heavy('fit plan-r03-1003', 'tinkoff', lock_path=lock, procs_fn=lambda: [], own=set()):
                self.assertEqual(Q.heavy_now(journals, lock_path=lock), {'what': 'fit plan-r03-1003', 'peak_gb': 9.0})
            with Q.heavy('compute', 'tinkoff', lock_path=lock, procs_fn=lambda: [], own=set()):
                self.assertEqual(Q.heavy_now(journals, lock_path=lock), {'what': 'compute', 'peak_gb': None})
                self.assertTrue(Q.light_gate('probe', procs=[], own=set(), heavy=Q.heavy_now(journals, lock_path=lock)))
                with self.assertRaises(Q.Busy):
                    Q.light_wait('probe', journals, lock_path=lock, procs_fn=lambda: [], own=set(), wait=False)
            Q.light_wait('probe', journals, lock_path=lock, procs_fn=lambda: [], own=set(), wait=False)
            self.assertEqual(Q.journal(None, {'event': 'x'})['event'], 'x')

    def test_a_torn_last_journal_line_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'q.jsonl'
            Q.journal(log, {'event': 'end', 'what': 'fit a', 'peak_gb': 9.0})
            with log.open('a') as f:
                f.write('{"event": "end", "what": "fit b", "pe')
            self.assertEqual(Q.peaks(log), {'fit a': 9.0})
            with log.open('a') as f:
                f.write('\n' + json.dumps({'event': 'end', 'what': 'fit c', 'peak_gb': 1.0}) + '\n')
            with self.assertRaises(ValueError):
                Q.entries(log)

    def test_fit_command_and_inputs(self):
        ds = type('D', (), {'name': 'tinkoff', 'paths': roles.paths('tinkoff')})()
        with tempfile.TemporaryDirectory() as tmp:
            stamp = {'code': {'scripts/xfer_model.py': 'a' * 64, 'scripts/xfer_tinkoff.py': 'b' * 64},
                     'council': {'council/xfer/fit.py': 'c' * 64}}
            files = Q.write_inputs(Path(tmp), {'name': 'plan-r01-1001'}, stamp, {'frame': 'd' * 64})
            self.assertEqual([f.name for f in files], ['spec.json', 'stamp.json', 'data.json'])
            self.assertEqual(json.loads(files[1].read_text()), stamp)
            cmd = Q.fit_command(ds, *files)
        self.assertEqual(cmd[1], '-I')
        self.assertEqual(cmd[2], str(ROOT / 'council' / 'xfer' / 'run.py'))
        self.assertEqual(cmd[3:6], ['--dataset', 'tinkoff', 'fit-one'])
        self.assertEqual(cmd[cmd.index('--stamp') + 1], str(files[1]))
        self.assertFalse(Q.is_foreign(' '.join(cmd)))
        self.assertTrue(Q.is_foreign(' '.join(cmd + ['--stamp', json.dumps(stamp)])))   # what argv must not carry
        ds = type('D', (), {'name': 'sber', 'paths': roles.paths('sber', '/tmp/tlab-r')})()
        cmd = Q.fit_command(ds, Path('/tmp/tlab-r/s'), Path('/tmp/tlab-r/t'), Path('/tmp/tlab-r/d'))
        self.assertEqual(cmd[3:7], ['--dataset', 'sber', '--root', '/tmp/tlab-r'])


if __name__ == '__main__':
    unittest.main()
