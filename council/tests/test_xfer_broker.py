"""council.xfer.broker on the synthetic world of test_xfer_fit (contract §3, §3.2, §10): fits are produced by
fit.run with a fake xm, the journal lives in a temporary git repository, evaluation labels come from fakes that
count their calls, the per-query metric goes through the real xm.evaluate (top_k inside) with a fake adapter
metric. The expected specs of plan/confirm/test come from plan.py functions patched to the specs of this world
(the tables of plan.py's own curations do not exist here); RealPlanTest derives them with the real plan.py.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_xfer_broker -v
"""
import dataclasses
import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pandas as pd

from council.tests.test_xfer_fit import ITEMS, S0, STAMP, TEST, USERS, Base, write_parquet
from council.xfer import broker, fit, plan, roles
from scripts import xfer_common as xc
from scripts import xfer_model as real_xm

K = 2
QUOTE = 'approved: «да, запускай C_test по tinkoff, final_labels можно»'
LINE = 'transcript: 6f57ee67 / да, запускай C_test по tinkoff, final_labels можно'
PLAN_TABLES = {1: ['g1_1'], 2: ['g2_1'], 3: ['g1_1', 'g2_1']}
TEST_TABLES = {13: ['g1_1'], 7: ['g2_1']}


def positives(anchor, user):
    return {int(user) % ITEMS, (int(user) + anchor) % ITEMS}


def has_target(user):
    return int(user) % 5 != 4


def labels_for(anchor, any_target=True):
    rows = [(u, i) for u in range(USERS) if has_target(u) for i in sorted(positives(anchor, u))]
    labels = pd.DataFrame(rows, columns=['user_id', 'item_id']).astype(np.int64)
    targets = pd.DataFrame({'user_id': np.arange(USERS, dtype=np.int64),
                            'n_targets': [len(positives(anchor, u)) if has_target(u) and any_target else 0
                                          for u in range(USERS)]})
    return labels, targets


def metric(ranked, queries, labels):
    """hits in the top K / min(K, n_targets); 0 for a query without ranked rows (as the adapters do)."""
    pos = set(zip(labels['user_id'].astype(int), labels['item_id'].astype(int)))
    hits = {}
    for u, i in zip(ranked['user_id'].astype(int), ranked['item_id'].astype(int)):
        hits[u] = hits.get(u, 0) + ((u, i) in pos)
    return pd.DataFrame({'user_id': queries['user_id'],
                         'value': [hits.get(int(u), 0) / min(K, int(n)) for u, n in
                                   zip(queries['user_id'], queries['n_targets'])]})


def expected(frame, anchor, users):
    """The metric of one score frame for `users`, computed without the broker."""
    out = {}
    for u in users:
        f = frame[frame.user_id == u].sort_values(['score', 'item_id'], ascending=[False, True]).head(K)
        out[u] = sum(int(i) in positives(anchor, u) for i in f.item_id) / min(K, len(positives(anchor, u)))
    return out


def half_users(half):
    return [u for u in range(USERS) if has_target(u) and (half is None or roles.halves(np.array([u]))[0] == half)]


class Broker(Base):
    def setUp(self):
        super().setUp()
        self.repo = self.w.root / 'repo'
        self.repo.mkdir(exist_ok=True)
        self.git('init', '-q')
        (self.repo / 'README').write_text('x')
        self.curation = self.ds.paths.run_file('curation.json')
        self.curation.parent.mkdir(parents=True, exist_ok=True)
        self.curation.write_text('{"families": "of this world"}\n')
        self.commit('init')
        self.label_calls = []
        self.ref = {}
        self.any_target = True
        world = self

        class Ctx:
            def __init__(self, dataset):
                self.K = K
                self.adapter = SimpleNamespace(metric=metric)

        def open_labels(collection):
            world.label_calls.append(('open', collection.name))
            return labels_for(int(collection.name.split('-')[1]), world.any_target)

        def final_labels(collection):
            world.label_calls.append(('final', collection.name))
            return labels_for(int(collection.name.split('-')[1]), world.any_target)

        fake = SimpleNamespace(Context=Ctx, evaluate=real_xm.evaluate, top_k=real_xm.top_k, open_labels=open_labels,
                               final_labels=final_labels, keys_digest=real_xm.keys_digest,
                               fit_dir=lambda dataset, series, arm, seed: self.w.xfer_dir(series, arm, seed),
                               read_metrics=lambda d, r: dict(self.ref['metrics']),
                               read_scores=lambda d, r: self.ref['scores'].copy())
        self.plan_calls = []

        def plan_specs(cur):
            world.plan_calls.append(('plan', cur))
            return [self.spec('plan', f'r{r:02d}', tables=t) for r, t in PLAN_TABLES.items()]

        def confirm_specs(cur, d):
            world.plan_calls.append(('confirm', cur, d))
            return [self.spec('confirm', 'SEL', s, tables=['g1_1']) for s in roles.CONFIRM_SEEDS]

        def test_specs(cur, selection, sha):
            world.plan_calls.append(('test', cur, selection, sha))
            return [self.spec('test', 'SEL', s, tables=t, selection_sha256=sha) for s, t in TEST_TABLES.items()]

        for p in (mock.patch.object(broker, 'xm', fake), mock.patch.object(plan, 'plan_specs', plan_specs),
                  mock.patch.object(plan, 'confirm_specs', confirm_specs),
                  mock.patch.object(plan, 'test_specs', test_specs)):
            p.start()
            self.started.append(p)

    def git(self, *args):
        return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false',
                               *args], cwd=self.repo, capture_output=True, text=True, check=True).stdout

    def commit(self, msg):
        self.git('add', '-A')
        self.git('commit', '-q', '--allow-empty', '-m', msg)

    def reads(self):
        return broker.reads(self.ds)

    def plan(self, n):
        spec = self.spec('plan', f'r{n:02d}', tables=PLAN_TABLES[n])
        fit.run(self.ds, spec)
        return spec['name']

    def append_record(self, rec):
        with self.ds.paths.fit_records.open('a') as f:
            f.write(json.dumps(rec) + '\n')

    def tamper(self, name, frame):
        """Replace the scores of `name` and its sha and keys in the record (a consistent but different file)."""
        rec = fit.records(self.ds)[name]
        s = rec['spec']
        path = self.ds.paths.scores(s['phase'], s['arm'], s['seed'])
        path.unlink()
        write_parquet(frame, path)
        rec['eval']['scores_sha256'] = xc.sha256_file(path)
        rec['eval']['keys_sha256'] = real_xm.keys_digest(frame)
        self.append_record(rec)

    def frame(self, name):
        s = fit.records(self.ds)[name]['spec']
        return xc.read_parquet(self.ds.paths.scores(s['phase'], s['arm'], s['seed']))


class SelectTest(Broker):
    def test_y_select_returns_only_per_query_values_of_half_b(self):
        names = [self.plan(1), self.plan(2)]
        out = broker.y_select(self.ds, names)
        self.assertEqual(list(out.columns), names)
        self.assertEqual(out.index.name, 'qid')
        self.assertTrue(all(str(d) == 'float64' for d in out.dtypes))
        users = half_users(roles.SELECT)
        self.assertEqual(list(out.index), [roles.Dataset.qid(S0, u) for u in users])
        for n in names:
            exp = expected(self.frame(n), S0, users)
            np.testing.assert_allclose(out[n].to_numpy(), [exp[u] for u in users])
        self.assertTrue(((out >= 0) & (out <= 1)).all().all())
        self.assertEqual(self.label_calls, [('open', f'val-{S0}')])
        rec = self.reads()[-1]
        self.assertEqual((rec['what'], rec['names']), ('y_select', names))
        self.assertEqual(set(rec), {'what', 'at', 'names', 'commit', 'scores'})          # no count of queries
        self.assertEqual(rec['scores'], {n: fit.records(self.ds)[n]['eval']['scores_sha256'] for n in names})
        self.assertEqual(rec['commit'], self.git('rev-parse', 'HEAD').strip())
        broker.y_select(self.ds, names[:1])                       # any number of reads
        self.assertEqual([r['what'] for r in self.reads()], ['y_select', 'y_select'])
        self.assertEqual(self.plan_calls[0], ('plan', {'families': 'of this world'}))

    def test_the_spec_must_be_the_committed_plan_spec(self):
        a = self.plan(1)
        # a record of r02 carrying other tables than the plan derives for r02 (file and record consistent)
        fit.run(self.ds, self.spec('plan', 'r02', tables=['g1_1']))
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, [a, 'plan-r02-1002'])
        fit.run(self.ds, fit.noise_specs(self.ds)[0])
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, ['noise-Hr-7'])               # not a fit of this read
        self.curation.write_text('{"families": "changed"}\n')
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, [a])                          # curation.json not committed
        self.commit('curation changed')
        broker.y_select(self.ds, [a])
        self.assertEqual(self.plan_calls[-1], ('plan', {'families': 'changed'}))
        self.curation.unlink()
        self.commit('no curation')
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, [a])
        self.assertEqual([r['what'] for r in self.reads()], ['y_select'])

    def test_confirm_specs_come_from_the_d_of_plan_result(self):
        specs = plan.confirm_specs(None, None)
        names = [s['name'] for s in specs]
        for s in specs:
            fit.run(self.ds, s)
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, names)                        # no plan-result.json: no confirmation
        result = self.ds.paths.run_file('plan-result.json')
        result.write_text(json.dumps({'D': []}))
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, names)                        # D empty: no confirmation
        result.write_text(json.dumps({'D': ['F2']}))
        out = broker.y_select(self.ds, names)
        self.assertEqual(list(out.columns), names)
        self.assertEqual(self.plan_calls[-1], ('confirm', {'families': 'of this world'}, ['F2']))

    def test_identity_collection_and_keys_of_the_record(self):
        a = self.plan(1)
        rec = fit.records(self.ds)[a]
        self.append_record(dict(rec, identity={'code': {}, 'council': {}}))
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, [a])                          # another identity than the current one
        self.append_record(rec)
        broker.y_select(self.ds, [a])
        self.ds.paths.prereg(0).write_text(json.dumps({'identity': {'code': {}, 'council': {'x': '1'}}}))
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, [a])                          # prereg-0 froze another identity
        self.ds.paths.prereg(0).write_text(json.dumps({'identity': STAMP}))
        broker.y_select(self.ds, [a])
        self.append_record(json.loads(json.dumps(rec).replace(f'val-{S0}', f'holdout-{TEST}')))
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, [a])                          # another eval collection
        self.append_record(rec)
        man = self.w.root / 'xfer' / 'collections' / f'val-{S0}' / 'manifest.json'
        text = man.read_text()
        man.write_text(text + ' ')
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, [a])                          # the collection was rebuilt
        man.write_text(text)
        bad = json.loads(json.dumps(rec))
        bad['eval']['keys_sha256'] = '0' * 64
        self.append_record(bad)
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, [a])                          # keys digest of the record
        self.assertEqual([r['what'] for r in self.reads()], ['y_select', 'y_select'])

    def test_a_name_is_never_read_with_other_scores(self):
        a = self.plan(1)
        broker.y_select(self.ds, [a])
        frame = self.frame(a)
        self.tamper(a, frame.assign(score=frame.score[::-1].to_numpy()))
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, [a])
        self.assertEqual(len(self.reads()), 1)

    def test_refusals_return_and_log_nothing(self):
        a, b = self.plan(1), self.plan(2)
        for names, err in ((['plan-r09-1009'], PermissionError), ([], ValueError), ([a, a], ValueError)):
            with self.assertRaises(err, msg=names):
                broker.y_select(self.ds, names)
        frame = self.frame(b)
        self.tamper(b, frame[frame.user_id != frame.user_id.iloc[0]].reset_index(drop=True))
        with self.assertRaises(ValueError):
            broker.y_select(self.ds, [a, b])                        # other queries
        with self.assertRaises(ValueError):
            broker.y_select(self.ds, [b])                           # a query of the half is not scored
        write_parquet(self.frame(a).assign(score=0.0), self.ds.paths.scores('plan', 'r01', 1001))
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, [a])                           # the file is not the one of its record
        self.assertFalse(self.ds.paths.reads.exists())
        self.assertEqual(self.label_calls, [('open', f'val-{S0}')])  # only the [b] read got to the labels

    def test_no_query_is_a_refusal(self):
        a = self.plan(1)
        self.any_target = False
        with self.assertRaises(ValueError):
            broker.y_select(self.ds, [a])
        self.assertFalse(self.ds.paths.reads.exists())

    def test_labels_only_under_the_default_root(self):
        ds = dataclasses.replace(self.ds, paths=dataclasses.replace(self.ds.paths, root=self.w.root))
        for key in ('select', 'test'):
            with self.assertRaises(PermissionError):
                broker.labels_of(ds, key)
        self.assertEqual(self.label_calls, [])

    def test_noise_explore_reads_half_a_once(self):
        specs = fit.noise_specs(self.ds)
        for s in specs:
            fit.run(self.ds, s)
        names = [s['name'] for s in specs]
        with self.assertRaises(PermissionError):
            broker.noise_explore(self.ds, names[:1])
        out = broker.noise_explore(self.ds, names)
        self.assertEqual(list(out.index), [roles.Dataset.qid(S0, u) for u in half_users(roles.EXPLORE)])
        self.assertEqual(list(out.columns), names)
        with self.assertRaises(PermissionError):
            broker.noise_explore(self.ds, names)
        self.assertEqual([r['what'] for r in self.reads()], ['noise_explore'])
        self.assertEqual(set(self.reads()[0]), {'what', 'at', 'names', 'commit', 'scores'})
        with self.assertRaises(PermissionError):
            broker.y_select(self.ds, names)                         # half A is not the select read

    def test_reads_tolerate_a_broken_last_line_and_never_glue_to_it(self):
        a = self.plan(1)
        broker.y_select(self.ds, [a])
        with self.ds.paths.reads.open('a') as f:
            f.write('{"what": "y_sel')
        n = len(self.label_calls)
        with mock.patch('sys.stderr'):
            self.assertEqual([r['what'] for r in self.reads()], ['y_select'])
            self.assertIsNone(broker.marker(self.ds))
            with self.assertRaises(SystemExit):
                broker.y_select(self.ds, [a])
        self.assertEqual(len(self.label_calls), n)                 # stopped before the labels

    def test_path_checks(self):
        sel, test = fit.path_specs(self.ds)
        with self.assertRaises(PermissionError):
            broker.path_check(self.ds, 'select')                    # not fitted yet
        fit.run(self.ds, sel)
        fit.run(self.ds, test)
        for series in ('dev', 'holdout'):
            path = self.w.xfer_dir(series) / 'report.json'
            report = xc.read_json(path)
            report.update(status='completed', dataset='tinkoff', series=series, arm='BA', seed=2026)
            path.write_text(json.dumps(report))
        users = half_users(None)
        mine = expected(self.frame(sel['name']), S0, users)
        self.ref['metrics'] = mine
        res = broker.path_check(self.ds, 'select')
        self.assertEqual(res, {'kind': 'select', 'name': 'path_select-Hr-2026', 'ref': 'dev/BA2026',
                               'same_queries': True, 'max_abs_diff': 0.0, 'ok': True})
        self.ref['metrics'] = mine | {users[0]: mine[users[0]] + 1e-6}
        self.assertFalse(broker.path_check(self.ds, 'select')['ok'])
        self.ref['metrics'] = {u: v for u, v in mine.items() if u != users[0]}
        res = broker.path_check(self.ds, 'select')
        self.assertEqual((res['same_queries'], res['max_abs_diff'], res['ok']), (False, float('inf'), False))
        self.assertEqual(self.label_calls, [('open', f'val-{S0}')] * 3)
        theirs = self.frame(test['name'])
        self.ref['scores'] = theirs.sample(frac=1, random_state=1)
        self.assertTrue(broker.path_check(self.ds, 'test')['ok'])
        self.ref['scores'] = theirs.assign(score=theirs.score + 1e-3)
        res = broker.path_check(self.ds, 'test')
        self.assertFalse(res['ok'])
        self.assertAlmostEqual(res['max_abs_diff'], 1e-3)
        self.assertEqual(len(self.label_calls), 3)                  # the test check reads no labels
        self.assertEqual([r['what'] for r in self.reads()], ['path_check:select'] * 3 + ['path_check:test'] * 2)
        for r in self.reads():
            self.assertEqual(set(r), {'what', 'at', 'names', 'commit', 'scores', 'ref', 'same_queries',
                                      'max_abs_diff', 'ok'})
        with self.assertRaises(ValueError):
            broker.path_check(self.ds, 'probe')


class GateTest(Broker):
    OTHER = 'xfer-sber'

    def approve(self, text):
        self.ds.paths.approved.parent.mkdir(parents=True, exist_ok=True)
        self.ds.paths.approved.write_text(text, encoding='utf-8')

    def other(self, text):
        path = self.ds.paths.runs.with_name(self.OTHER) / 'test-approved.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def select(self, content='{"arm": "SEL"}\n'):
        self.ds.paths.selection.parent.mkdir(parents=True, exist_ok=True)
        self.ds.paths.selection.write_text(content)

    def ready(self):
        self.approve(f'# test\n{QUOTE}\n{LINE}\n')
        self.select()
        self.commit('selection')

    def make_test_fits(self, sha):
        for s, t in TEST_TABLES.items():
            fit.run(self.ds, self.spec('test', 'SEL', s, tables=t, selection_sha256=sha))

    def test_start_test_refusals(self):
        bad = ['', f'{LINE}\n', f'{QUOTE}\n',
               f'approved: <цитата владельца с «да»>\n{LINE}\n',
               f'approved: ни о чём не спрашивай, да, tinkoff final_labels\n{LINE}\n',
               f'approved: запускай C_test\n{LINE}\n',
               f'{QUOTE}\ntranscript: 6f57ee67\n',
               f'{QUOTE}\ntranscript: <session> / <text>\n',
               'approved: да, запускай\ntranscript: 6f57ee67 / да, запускай\n',                # no dataset
               'approved: да, tinkoff\ntranscript: 6f57ee67 / да, tinkoff\n']                  # no final_labels
        self.select()
        self.commit('selection')
        for text in bad:
            self.approve(text)
            with self.assertRaises(PermissionError, msg=text):
                broker.start_test(self.ds)
        self.approve(f'{QUOTE}\n{LINE}\n')
        for text in (f'{QUOTE}\n{LINE}\n',
                     f'approved: да, sber, final_labels\n{LINE}\n',                   # the same transcript
                     'approved: да, sber, final_labels\ntranscript:   6f57ee67  /  да, запускай C_test по '
                     'tinkoff,  final_labels можно\n',                                  # the same, other spaces
                     f'{QUOTE}\ntranscript: 6f57ee67 / да, sber, final_labels\n'):     # the same quote
            self.other(text)
            with self.assertRaises(PermissionError, msg=text):
                broker.start_test(self.ds)
        self.other('approved: да, sber, final_labels\ntranscript: 6f57ee67 / да, sber, final_labels\n')
        self.ds.paths.selection.unlink()
        with self.assertRaises(PermissionError):
            broker.start_test(self.ds)                              # no selection.json
        self.select('{"arm": "other"}\n')
        with self.assertRaises(PermissionError):
            broker.start_test(self.ds)                              # uncommitted change
        self.commit('other selection')
        self.assertFalse(self.ds.paths.reads.exists())
        rec = broker.start_test(self.ds)
        self.assertEqual(rec['what'], broker.MARKER)
        self.assertEqual(rec['selection_sha256'], broker.selection_sha(self.ds))
        self.assertEqual(rec['selection_commit'], self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(rec['approved_sha256'], xc.sha256_file(self.ds.paths.approved))
        self.assertEqual(broker.marker(self.ds), rec)
        with self.assertRaises(PermissionError):
            broker.start_test(self.ds)                              # once
        self.assertEqual([r['what'] for r in self.reads()], [broker.MARKER])
        self.assertEqual(self.label_calls, [])

    def test_fit_needs_the_marker_and_c_test_reads_final_labels(self):
        self.ready()
        sha = broker.selection_sha(self.ds)
        with self.assertRaises(ValueError):
            fit.validate(self.ds, self.spec('test', 'SEL', 13, selection_sha256=sha, tables=['g1_1']))
        with self.assertRaises(PermissionError):
            broker.c_test(self.ds, ['test-SEL-13'])
        self.assertEqual(self.reads()[-1]['what'], 'c_test.refused')
        with self.assertRaises(PermissionError):
            broker.target_shares(self.ds)
        broker.start_test(self.ds)
        self.make_test_fits(sha)
        names = ['test-SEL-13', 'test-SEL-7']
        out = broker.c_test(self.ds, names)
        users = half_users(None)
        self.assertEqual(list(out.index), [roles.Dataset.qid(TEST, u) for u in users])
        self.assertEqual(list(out.columns), names)
        for n in names:
            exp = expected(self.frame(n), TEST, users)
            np.testing.assert_allclose(out[n].to_numpy(), [exp[u] for u in users])
        self.assertEqual(self.label_calls, [('final', f'holdout-{TEST}'), ('open', f'val-{S0}')])
        last = self.reads()[-1]
        self.assertEqual((last['what'], last['names'], last['selection_sha256']), ('c_test', names, sha))
        self.assertEqual(last['target_shares'], {'select': len(users) / USERS, 'test': len(users) / USERS})
        self.assertEqual(set(last['scores']), set(names))
        self.assertEqual(broker.target_shares(self.ds), last['target_shares'])
        self.assertEqual(len(self.label_calls), 2)                  # target_shares reads nothing
        self.assertEqual(self.plan_calls[-1], ('test', {'families': 'of this world'}, {'arm': 'SEL'}, sha))

    def test_c_test_refusals_are_logged_and_read_no_label(self):
        self.ready()
        sha = broker.selection_sha(self.ds)
        broker.start_test(self.ds)
        self.make_test_fits(sha)
        self.plan(1)
        good = fit.records(self.ds)['test-SEL-7']
        # test-SEL-7 with other tables than test_specs derives (file and record consistent with each other)
        bad = json.loads(json.dumps(good))
        bad['spec']['tables'] = ['g1_1', 'g2_1']
        self.append_record(bad)
        refusals = 0

        def refused(names, msg):
            nonlocal refusals
            with self.assertRaises(PermissionError, msg=msg):
                broker.c_test(self.ds, names)
            refusals += 1
            last = self.reads()[-1]
            self.assertEqual((last['what'], last['names']), ('c_test.refused', names), msg)
            self.assertTrue(last['reason'], msg)

        refused(['test-SEL-7'], 'the spec of the record is not the derived one')
        self.append_record(good)
        refused(['plan-r01-1001'], 'not a test fit')
        refused(['test-SEL-13', 'test-SEL-99'], 'no fit')
        self.approve(f'{LINE}\n')
        refused(['test-SEL-13'], 'the approval is gone')
        self.approve(f'{QUOTE}\n{LINE}\n')
        refused(['test-SEL-13'], 'test-approved.md is not the one of the marker')
        self.approve(f'# test\n{QUOTE}\n{LINE}\n')
        self.other(f'approved: да, sber, final_labels\n{LINE}\n')
        refused(['test-SEL-13'], 'the same transcript in the other dataset, another quote')
        self.other('')
        self.select('{"arm": "changed"}\n')
        refused(['test-SEL-13'], 'selection changed')
        self.commit('changed')
        self.select()
        refused(['test-SEL-13'], 'same bytes, uncommitted')
        self.commit('back')
        refused(['test-SEL-13'], 'same bytes, committed again after the marker')
        self.ds.paths.selection.unlink()
        refused(['test-SEL-13'], 'no selection.json')
        self.assertEqual(self.label_calls, [])
        whats = [r['what'] for r in self.reads()]
        self.assertEqual(whats, [broker.MARKER] + ['c_test.refused'] * refusals)

    def test_c_test_is_not_repeated_on_other_scores(self):
        self.ready()
        sha = broker.selection_sha(self.ds)
        broker.start_test(self.ds)
        self.make_test_fits(sha)
        broker.c_test(self.ds, ['test-SEL-13'])
        broker.c_test(self.ds, ['test-SEL-13'])                     # the same scores: the broker allows it
        frame = self.frame('test-SEL-13')
        self.tamper('test-SEL-13', frame.assign(score=frame.score[::-1].to_numpy()))
        with self.assertRaises(PermissionError):
            broker.c_test(self.ds, ['test-SEL-13'])
        self.assertEqual([r['what'] for r in self.reads()][-1], 'c_test.refused')
        self.assertEqual(len(self.label_calls), 4)


class RealPlanTest(Broker):
    """The expected specs from the real plan.py (no patch): plan_specs of the committed curation, test_specs of
    the committed selection and the marker sha."""

    def test_derivation(self):
        from council.tests.test_xfer_plan import curation
        for p in self.started[-3:]:
            p.stop()
        self.started = self.started[:-3]
        cur = curation()
        self.curation.write_text(json.dumps(cur))
        self.commit('curation')
        got = broker.expected_specs(self.ds, ['plan'], 'x')
        self.assertEqual(list(got.values()), plan.plan_specs(cur))
        with self.assertRaises(PermissionError):
            broker.expected_specs(self.ds, ['test'], 'x')            # no selection.json
        selection = {'D': [], 'tables': plan._arm_tables(cur, [], None)}
        self.ds.paths.selection.write_text(json.dumps(selection))
        self.commit('selection')
        with self.assertRaises(PermissionError):
            broker.expected_specs(self.ds, ['test'], 'x')            # no marker
        sha = broker.selection_sha(self.ds)
        broker.log(self.ds, broker.MARKER, [], selection_sha256=sha)
        got = broker.expected_specs(self.ds, ['test'], 'x')
        self.assertEqual(list(got.values()), plan.test_specs(cur, selection, sha))
        self.ds.paths.selection.write_text(json.dumps({'D': []}))
        self.commit('selection without tables')
        with self.assertRaises(PermissionError):
            broker.expected_specs(self.ds, ['test'], 'x')            # plan.py refuses it
        self.assertEqual(set(broker.expected_specs(self.ds, ['path_select', 'noise'], 'x')),
                         {'path_select-Hr-2026', 'noise-Hr-7', 'noise-Hr-11'})


if __name__ == '__main__':
    unittest.main()
