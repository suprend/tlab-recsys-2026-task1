"""council.side.task1_side_b (one read of half B for H9 and H11) on synthetic day tables under /tmp/tlab-sideb-*; no
REES46 data is read and the real heavy lock is never taken (a lock file under the temporary root, no process check).

The stand: synthetic days and extra tables (build_stand of test_side_task1), the reference fits made by exp.run (both
halves in their parquet), the new fits made by task1_side.fit_one (records, .cbm, <name>.A.parquet), and A results
written by hand: h9 with W = h9_rsm05 under the A verdict «без выигрыша», h11 with group 2 accepted. Each test runs on
its own copy of artifacts/side/<h>/ and the A result, so the single-use marker of one test does not touch another.

Point 8 of the B-step spec: a rerun is refused by the marker (and by the marker alone); verdict 1 and a missing W read
nothing and leave no marker; no --owner-yes (or a yes that does not name B 2019 and the hypothesis) refuses before
reading; rows of half B never reach an A function and the other way round; a recheck of A that differs stops the step
before any metric of B. Also: the happy paths of h9 and h11, the A result untouched, writes only under the roots.

Run: TASK1_PERIOD=2019 .venv/bin/python -m unittest council.tests.test_side_task1_b -v
"""
import ast
import contextlib
import json
import os
import re
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

if os.environ.get('TASK1_PERIOD', '2019') != '2019':
    raise unittest.SkipTest(f"TASK1_PERIOD={os.environ['TASK1_PERIOD']!r}: council.side.task1_side_b is REES46 2019 "
                            "only; run TASK1_PERIOD=2019 .venv/bin/python -m unittest council.tests.test_side_task1_b")

import duckdb
import numpy as np
import pandas as pd

from council import side as S
from council.side import task1_side as T
from council.side import task1_side_b as TB
from council.tests.test_side_task1 import build_stand, chdir, expected_small, write_parquet
from task1 import exp
from task1 import model as M

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'council' / 'side' / 'task1_side_b.py'
SMALL = dict(iterations=20, threads=2)
YES = 'да — чтение B 2019 для H9 и H11'
WHEN = '2026-10-22'
CREATED = []


def tmp_root() -> Path:
    p = Path(tempfile.mkdtemp(dir='/tmp', prefix='tlab-sideb-'))
    CREATED.append(p)
    return p


def tearDownModule():
    for p in CREATED:
        if str(p).startswith('/tmp/tlab-sideb-'):
            shutil.rmtree(p, ignore_errors=True)


def halves(frame_or_index) -> set:
    """The halves of the users of a frame (user_id) or of a qid index ('<anchor>:<user_id>')."""
    if isinstance(frame_or_index, pd.DataFrame) and 'user_id' in frame_or_index:
        users = frame_or_index['user_id'].to_numpy()
    else:
        users = np.array([int(q.split(':')[1]) for q in frame_or_index], dtype=np.int64)
    return set(exp.half(users)) if len(users) else set()


class Stand:
    root = days = extra = ref = None
    REFS = ('grid_Hp_s0', 'grid_Hp_s1', 'q2_d8', 'q3_d8_s1', 'agent_night20_r6_base', 'pl19_Hag_s0', 'pl19_Hag_s1')

    @classmethod
    def get(cls):
        if cls.root is None:
            root = tmp_root()
            cls.days, cls.extra = build_stand(root)
            cls.ref = root / 'ref'
            (root / 'refcwd').mkdir()
            cls.root = root
            with cls.patched(), chdir(root / 'refcwd'):
                ctx9 = cls.ctx('h9', root)
                for name in cls.REFS:
                    exp.run(name, **T.config(ctx9, T.EXPECTED[name][0]))
                for i in (0, 1):
                    T.fit_one(ctx9, f'h9_rsm05_s{i}', T.HP | T.SEEDS[i] | {'rsm': 0.5})
                ctx11 = cls.ctx('h11', root)
                T.fit_one(ctx11, 'h11_step_s1', T.R6BASE | T.SEEDS[1])
                for i in (0, 1):
                    T.fit_one(ctx11, f'h11_g2_s{i}', T.H | T.SEEDS[i] | {'extra': T.ROUNDS[2]})
            stamp = T.code_stamp()
            ctx9.out.write_json({'step': 'h9', 'status': 'ok', 'W': 'h9_rsm05', 'code': stamp,
                                 'verdict': 'H+ на A без выигрыша по rsm 0.5/0.3, глубине 10, l2 3/30'},
                                'h9-result.json', runs=True)
            rounds = [{'round': r, 'accepted': r == 2} for r in range(1, 7)]
            ctx11.out.write_json({'step': 'h11', 'status': 'ok', 'groups': 5, 'rounds': rounds, 'accepted': 1,
                                  'G_star': {'fits': ['h11_g2_s0', 'h11_g2_s1'], 'tables': T.ROUNDS[2]},
                                  'rule': 3, 'verdict': 'x', 'code': stamp}, 'h11-result.json', runs=True)
        return cls

    @classmethod
    @contextlib.contextmanager
    def patched(cls):
        with mock.patch.object(M, 'EXTRA', cls.extra), mock.patch.object(exp, 'OUT', cls.ref), \
                mock.patch.dict(T.EXPECTED, expected_small()):
            yield

    @classmethod
    def ctx(cls, h, root, **kw):
        (root / 'prot').mkdir(exist_ok=True)
        return T.Ctx(h, T.make_out(h, root / 'art', root / 'runs'), days=cls.days, ref_dir=cls.ref, over=dict(SMALL),
                     heavy_kw={'lock_path': root / 'heavy.lock', 'procs_fn': lambda: []}, wait=False,
                     check_fn=lambda: None, snapshot_roots={root / 'prot': 'incident'}, **kw)

    @classmethod
    def fresh(cls, h, yes=YES, edit=None, **kw):
        """A new root with a copy of artifacts/side/<h>/ and the A result (edited by `edit` if given)."""
        cls.get()
        root = tmp_root()
        shutil.copytree(cls.root / 'art' / h, root / 'art' / h)
        (root / 'runs').mkdir()
        res = json.loads((cls.root / 'runs' / f'{h}-result.json').read_text())
        if edit:
            edit(res)
        (root / 'runs' / f'{h}-result.json').write_text(json.dumps(res, ensure_ascii=False))
        return root, TB.Step(cls.ctx(h, root, **kw), yes, WHEN, 'test', expected_b=None)


def boom():
    return mock.Mock(side_effect=AssertionError('a day table was read'))


def written(root: Path) -> list:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())


# ---------------------------------------------------------------- the owner's yes

class OwnerYes(unittest.TestCase):
    def test_literal_yes(self):
        for h in ('h9', 'h11'):
            self.assertEqual(TB.check_owner(YES, WHEN, h), YES)
        bad = {'h9': ['да — чтение 2019 для H9', 'чтение B 2019 для H9', 'да — чтение B 2019 для H11',
                      'да — чтение B 2020 для H9', 'да — чтение B 2019 для H90', 'дано: B 2019 для H9', ''],
               'h11': ['да — чтение B 2019 для H9', 'да — чтение B 2019 для H1', 'да — чтение B 2019 для H110']}
        for h, texts in bad.items():
            for t in texts:
                with self.subTest(h=h, t=t), self.assertRaises(S.Refused):
                    TB.check_owner(t, WHEN, h)
        with self.assertRaises(S.Refused):
            TB.check_owner(YES, WHEN, 'h10')
        for when in ('22.10.2026', '', '2999-01-01'):
            with self.subTest(when=when), self.assertRaises(S.Refused):
                TB.check_owner(YES, when, 'h9')

    def test_large_groups_need_to_be_named(self):
        for size in (10, 15):
            with self.assertRaises(S.Refused):
                TB.check_owner(YES, WHEN, 'h11', size)
            TB.check_owner(f'да — чтение B 2019 для H11 группами по {size}', WHEN, 'h11', size)
        with self.assertRaises(S.Refused):
            TB.check_owner('да — чтение B 2019 для H11 группами по 15', WHEN, 'h11', 10)

    def test_main_refuses_before_reading(self):
        b = boom()
        with mock.patch.object(exp, 'read_day', b), mock.patch.object(exp, '_read', b), \
                mock.patch.object(TB, 'prepare', b), mock.patch.object(TB, 'run', b), mock.patch.object(TB, 'dry', b):
            for argv in (['h9'], ['h9', '--owner-date', WHEN], ['h11', '--owner-yes', YES],
                         ['h9', '--owner-yes', 'нет', '--owner-date', WHEN],
                         ['h9', '--owner-yes', 'да — чтение B 2019 для H11', '--owner-date', WHEN],
                         ['h11', '--owner-yes', YES, '--owner-date', WHEN, '--groups', '10'],
                         ['h9', '--owner-yes', YES, '--owner-date', WHEN, '--groups', '10'],
                         ['h10', '--owner-yes', YES, '--owner-date', WHEN]):
                with self.subTest(argv=argv), self.assertRaises(SystemExit) as e:
                    TB.main(argv)
                self.assertNotEqual(e.exception.code, 0)
        b.assert_not_called()

    def test_names(self):
        root = tmp_root()
        c9 = T.Ctx('h9', T.make_out('h9', root / 'art', root / 'runs'), check_fn=lambda: None)
        c10 = T.Ctx('h11', T.make_out('h11', root / 'art', root / 'runs'), groups=10, check_fn=lambda: None)
        self.assertEqual((TB.marker_name(c9), TB.result_b_name(c9)), ('B.started', 'h9-B-result.json'))
        self.assertEqual((TB.marker_name(c10), TB.result_b_name(c10)), ('B-L10.started', 'h11-L10-B-result.json'))


# ---------------------------------------------------------------- preconditions: nothing is read, no marker

class Preconditions(unittest.TestCase):
    def assert_refused_unread(self, h, edit=None, **kw):
        root, step = Stand.fresh(h, edit=edit, **kw)
        b = boom()
        with Stand.patched(), mock.patch.object(exp, 'read_day', b), mock.patch.object(TB, 'ref_b', b), \
                self.assertRaises(S.Refused):
            TB.run(step)
        b.assert_not_called()
        self.assertFalse((root / 'art' / h / 'B.started').exists())
        self.assertFalse((root / 'runs' / f'{h}-B-result.json').exists())
        self.assertFalse((root / 'heavy.lock').exists())

    def test_no_w_reads_nothing(self):
        self.assert_refused_unread('h9', lambda r: r.pop('W'))

    def test_verdict_1_reads_nothing(self):
        def one(r):
            r.update(rule=1, accepted=0, G_star={'fits': T.H_REF, 'tables': []},
                     rounds=[{'round': i, 'accepted': False} for i in range(1, 7)])
        self.assert_refused_unread('h11', one)

    def test_a_result_must_be_ok_with_the_same_task1_code(self):
        self.assert_refused_unread('h9', lambda r: r.update(status='refused'))
        self.assert_refused_unread('h9', lambda r: r['code'].update({'task1/exp.py': '0' * 64}))
        self.assert_refused_unread('h11', lambda r: r['G_star'].update(fits=['h11_g3_s0', 'h11_g3_s1']))
        self.assert_refused_unread('h11', groups=10)  # the yes does not name groups of 10

    def test_full_stamp_of_the_a_run(self):
        # task1_side.py changed since the A run: the current stamp differs in that file only
        root, step = Stand.fresh('h9')
        step.ctx.stamp = step.ctx.stamp | {'council/side/task1_side.py': '0' * 64}
        b = boom()
        with Stand.patched(), mock.patch.object(exp, 'read_day', b), self.assertRaises(S.Refused) as e:
            TB.run(step)
        b.assert_not_called()
        self.assertIn('code stamp', str(e.exception))
        self.assertFalse((root / 'art' / 'h9' / 'B.started').exists())
        # the A result agrees with the current code, a model record does not
        root, step = Stand.fresh('h9', edit=lambda r: r.update(code=r['code'] | {'council/side/__init__.py': '1' * 64}))
        step.ctx.stamp = step.ctx.stamp | {'council/side/__init__.py': '1' * 64}
        with Stand.patched(), mock.patch.object(exp, 'read_day', b), self.assertRaises(S.Refused) as e:
            TB.run(step)
        b.assert_not_called()
        self.assertIn('h9_rsm05_s0: fit with another code stamp', str(e.exception))

    def test_variant_after_the_main_read_needs_povtorno(self):
        yes10 = 'да — чтение B 2019 для H11 группами по 10'
        root, step = Stand.fresh('h11', yes=yes10, groups=10)
        none = {'marker': None, 'file': None, 'read': False}
        self.assertEqual(TB.prior_b(step.ctx, yes10), {'groups5': none, 'groups15': none, 'read': False})
        (root / 'runs' / 'h11-B-result.json').write_text(json.dumps({'status': 'refused', 'B_read': False}))
        self.assertFalse(TB.prior_b(step.ctx, yes10)['read'])  # a refusal before the marker spent nothing
        (root / 'runs' / 'h11-B-result.json').write_text(json.dumps({'status': 'ok', 'B_read': True,
                                                                        'verdict_B': 'на B не различено'}))
        b = boom()
        with Stand.patched(), mock.patch.object(exp, 'read_day', b), self.assertRaises(S.Refused) as e:
            TB.run(step)
        self.assertIn('повторно', str(e.exception))
        again = yes10 + ', повторно'
        info = TB.prior_b(step.ctx, again)
        self.assertEqual((info['read'], info['groups5']['verdict_B']), (True, 'на B не различено'))
        with Stand.patched(), mock.patch.object(exp, 'read_day', b), self.assertRaises(S.Refused) as e:
            TB.run(TB.Step(step.ctx, again, WHEN))
        self.assertIn('h11-L10-result.json', str(e.exception))  # past the prior check: no A result of the variant
        b.assert_not_called()

    def test_main_after_a_variant_needs_povtorno(self):
        yes = 'да — чтение B 2019 для H11'
        root, step = Stand.fresh('h11', yes=yes)
        self.assertFalse(TB.prior_b(step.ctx, yes)['read'])
        (root / 'art' / 'h11' / 'B-L15.started').write_text('{}')
        with self.assertRaises(S.Refused) as e:
            TB.prior_b(step.ctx, yes)
        self.assertIn('повторно', str(e.exception))
        info = TB.prior_b(step.ctx, yes + ', повторно')
        self.assertTrue(info['groups15']['read'])
        self.assertFalse(info['groups10']['read'])
        self.assertIsNone(TB.prior_b(Stand.fresh('h9')[1].ctx, yes))

    def test_model_must_match_its_record(self):
        root, step = Stand.fresh('h9')
        p = root / 'art' / 'h9' / 'runs.jsonl'
        recs = [json.loads(x) for x in p.read_text().splitlines()]
        recs[-1]['features'] += 1
        p.write_text(''.join(json.dumps(r) + '\n' for r in recs))
        b = boom()
        with Stand.patched(), mock.patch.object(exp, 'read_day', b), self.assertRaises(S.Refused):
            TB.run(step)
        b.assert_not_called()
        self.assertFalse((root / 'art' / 'h9' / 'B.started').exists())

    def test_without_yes_refuses(self):
        root, step = Stand.fresh('h9', yes='')
        b = boom()
        with Stand.patched(), mock.patch.object(exp, 'read_day', b), self.assertRaises(S.Refused):
            TB.run(step)
        b.assert_not_called()
        self.assertFalse((root / 'art' / 'h9' / 'B.started').exists())


# ---------------------------------------------------------------- the read itself

class Read(unittest.TestCase):
    def test_h9_once_and_rerun_refused(self):
        root, step = Stand.fresh('h9')
        a_file = root / 'runs' / 'h9-result.json'
        a_before = a_file.read_bytes()
        with Stand.patched():
            res = TB.run(step)
        self.assertEqual(res['status'], 'ok', res.get('reasons'))
        self.assertTrue(res['A_recheck_passed'])
        for r in res['path_A_recheck'].values():
            self.assertTrue(r['same_queries'])
            self.assertEqual(set(r['max_abs'].values()), {0.0})
        self.assertEqual(res['owner_yes'], YES)
        self.assertEqual(res['interpretation'], TB.H9_INTERPRETATION)
        self.assertIn('без выигрыша', res['A']['verdict_A'])  # B read under the A verdict «без выигрыша» with W
        self.assertEqual(res['replaces'], TB.REPLACES)
        self.assertEqual(res['mean']['ref'], T.HP_REF)
        self.assertEqual(res['mean']['new'], ['h9_rsm05_s0', 'h9_rsm05_s1'])
        self.assertEqual(len(res['by_seed']), 2)
        self.assertIn('эффект выбора', res['note'])
        ref = duckdb.sql(f"SELECT count(*) FROM read_parquet('{Stand.ref / 'grid_Hp_s0.parquet'}') "
                         "WHERE half = 'B'").fetchone()[0]
        self.assertEqual(res['B_queries'], ref)
        # the B verdict from the bootstrap of the two-seed means
        frames = {n: TB.ref_b(step.ctx, n) for n in T.HP_REF}
        for n in ('h9_rsm05_s0', 'h9_rsm05_s1'):
            f = duckdb.sql(f"SELECT * FROM read_parquet('{root / 'art' / 'h9' / f'{n}.B.parquet'}')").df()
            self.assertEqual(set(f.half), {'B'})
            self.assertEqual(halves(f.qid), {'B'})
            frames[n] = f.set_index('qid').sort_index()
        d, lo, hi = M.bootstrap_diff(sum(frames[n]['ndcg'] for n in T.HP_REF) / 2,
                                     sum(frames[n]['ndcg'] for n in ('h9_rsm05_s0', 'h9_rsm05_s1')) / 2,
                                     n=2000, seed=2026)
        self.assertEqual((res['mean']['d'], res['mean']['ci']), (float(d), [float(lo), float(hi)]))
        self.assertTrue(res['B_read'])
        # the A verdict file is untouched; the result lies beside it
        self.assertEqual(a_file.read_bytes(), a_before)
        self.assertTrue(res['A']['untouched'])
        saved = json.loads((root / 'runs' / 'h9-B-result.json').read_text())
        self.assertEqual(saved['verdict_B'], res['verdict_B'])
        marker = json.loads((root / 'art' / 'h9' / 'B.started').read_text())
        self.assertEqual(marker['owner_yes'], YES)
        new = [w for w in written(root) if w not in written_before(root, 'h9')]
        self.assertEqual(sorted(new), ['art/h9/B.started', 'art/h9/h9_rsm05_s0.B.parquet',
                                       'art/h9/h9_rsm05_s1.B.parquet', 'heavy.lock', 'runs/h9-B-result.json',
                                       'runs/queue.jsonl'])
        # a rerun is refused before anything is read; the marker alone refuses too
        b = boom()
        with Stand.patched(), mock.patch.object(exp, 'read_day', b), self.assertRaises(S.Refused):
            TB.run(step)
        (root / 'runs' / 'h9-B-result.json').unlink()
        with Stand.patched(), mock.patch.object(exp, 'read_day', b), self.assertRaises(S.Refused):
            TB.run(step)
        with self.assertRaises(S.Refused):
            TB.mark(step)
        b.assert_not_called()

    def test_h11_rules_on_b(self):
        root, step = Stand.fresh('h11')
        with Stand.patched():
            res = TB.run(step)
        self.assertEqual(res['status'], 'ok', res.get('reasons'))
        self.assertEqual(sorted(res['path_A_recheck']), ['h11_g2_s0', 'h11_g2_s1', 'h11_step_s1'])
        self.assertEqual(res['arms']['group'], ['h11_g2_s0', 'h11_g2_s1'])
        self.assertEqual(res['arms']['step'], [T.STEP_REF, 'h11_step_s1'])
        self.assertEqual((res['D']['ref'], res['E']['ref']), (T.ALL_REF, [T.STEP_REF, 'h11_step_s1']))
        self.assertIn(res['rule'], (2, 3, 4, 5))
        self.assertIn('подстроены под A', res['note'])
        self.assertTrue(res['A']['untouched'])
        self.assertTrue((root / 'art' / 'h11' / 'B.started').exists())
        self.assertFalse(any(w.endswith('.B.parquet') and 'h11_g2' not in w and 'h11_step_s1' not in w
                             for w in written(root)))
        with Stand.patched(), self.assertRaises(S.Refused):
            TB.run(step)

    def test_halves_never_cross(self):
        root, step = Stand.fresh('h9')
        seen = {'a': [], 'b': [], 'ref_b': [], 'metrics_b': []}
        orig = {k: getattr(TB, k) for k in ('score_a_rows', 'predict_b_rows', 'ref_b', 'metrics_b')}

        def score_a_rows(mod, rows):
            seen['a'].append(halves(rows))
            return orig['score_a_rows'](mod, rows)

        def predict_b_rows(mod, rows):
            seen['b'].append(halves(rows))
            return orig['predict_b_rows'](mod, rows)

        def ref_b(ctx, name):
            f = orig['ref_b'](ctx, name)
            seen['ref_b'].append(halves(f.index))
            return f

        def metrics_b(parts):
            f = orig['metrics_b'](parts)
            seen['metrics_b'].append(halves(f.index))
            return f
        with Stand.patched(), mock.patch.object(TB, 'score_a_rows', score_a_rows), \
                mock.patch.object(TB, 'predict_b_rows', predict_b_rows), \
                mock.patch.object(TB, 'ref_b', ref_b), mock.patch.object(TB, 'metrics_b', metrics_b):
            res = TB.run(step)
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(len(seen['a']), 6 * 2)
        self.assertEqual(len(seen['b']), 6 * 2)
        for k, half in (('a', 'A'), ('b', 'B'), ('ref_b', 'B'), ('metrics_b', 'B')):
            self.assertTrue(seen[k], k)
            self.assertTrue(all(s == {half} for s in seen[k]), (k, seen[k]))
        # the split itself: A and B rows of a day are disjoint and together the whole day
        d = date(2019, 11, 8)
        a, b = TB.split_day(Stand.days, d)
        full = exp.read_day(d, str(Stand.days))
        self.assertEqual((halves(a), halves(b)), ({'A'}, {'B'}))
        self.assertEqual(len(a) + len(b), len(full))
        pd.testing.assert_frame_equal(a, T.read_days('val', Stand.days, d))

    def test_a_recheck_mismatch_spends_nothing(self):
        root, step = Stand.fresh('h9')
        p = root / 'art' / 'h9' / 'h9_rsm05_s1.A.parquet'
        good = p.read_bytes()
        df = duckdb.sql(f"SELECT * FROM read_parquet('{p}')").df()
        df.loc[0, 'ndcg'] = df.loc[0, 'ndcg'] + 1e-9
        p.unlink()
        write_parquet(df, p)
        b = boom()
        with Stand.patched(), mock.patch.object(TB, 'predict_b_rows', b), mock.patch.object(TB, 'pass_b', b), \
                mock.patch.object(TB, 'mark', b), mock.patch.object(TB, 'ref_b', b), \
                mock.patch.object(TB, 'half_b', b), \
                self.assertRaises(SystemExit) as e:
            TB.run(step)
        b.assert_not_called()
        self.assertIn('refused', str(e.exception.code))
        res = json.loads((root / 'runs' / 'h9-B-result.json').read_text())
        self.assertEqual((res['status'], res['B_read'], res['marker']), ('refused', False, None))
        self.assertFalse(res['A_recheck_passed'])
        self.assertEqual(res['path_A_recheck']['h9_rsm05_s0']['max_abs']['ndcg'], 0.0)
        self.assertGreater(res['path_A_recheck']['h9_rsm05_s1']['max_abs']['ndcg'], 0.0)
        for k in ('verdict_B', 'mean', 'by_seed', 'B_queries', 'replaces'):
            self.assertNotIn(k, res)
        self.assertFalse(any(w.endswith('.B.parquet') for w in written(root)))
        self.assertFalse((root / 'art' / 'h9' / 'B.started').exists())
        # B is not spent: with the A file restored the read goes through
        p.write_bytes(good)
        with Stand.patched():
            res = TB.run(step)
        self.assertEqual((res['status'], res['B_read']), ('ok', True))
        self.assertTrue((root / 'art' / 'h9' / 'B.started').exists())

    def test_a_result_changed_while_waiting_for_the_lock(self):
        root, step = Stand.fresh('h9')
        a_file = root / 'runs' / 'h9-result.json'
        real = S.heavy_step

        @contextlib.contextmanager
        def heavy_step(*a, **k):
            r = json.loads(a_file.read_text())
            r['verdict'] = 'H+ недонастроен на A по оси h9_rsm05'
            a_file.write_text(json.dumps(r, ensure_ascii=False))
            with real(*a, **k) as lock:
                yield lock
        b = boom()
        with Stand.patched(), mock.patch.object(S, 'heavy_step', heavy_step), mock.patch.object(exp, 'read_day', b), \
                self.assertRaises(S.Refused) as e:
            TB.run(step)
        b.assert_not_called()
        self.assertIn('waiting for the lock', str(e.exception))
        self.assertFalse((root / 'art' / 'h9' / 'B.started').exists())
        self.assertFalse((root / 'runs' / 'h9-B-result.json').exists())

    def test_failure_after_the_marker_is_recorded(self):
        root, step = Stand.fresh('h9')
        with Stand.patched(), mock.patch.object(TB, 'predict_b_rows', mock.Mock(side_effect=MemoryError('x'))), \
                self.assertRaises(MemoryError):
            TB.run(step)
        res = json.loads((root / 'runs' / 'h9-B-result.json').read_text())
        self.assertEqual((res['status'], res['B_read']), ('failed', True))
        self.assertIn('MemoryError', res['error'])
        self.assertEqual(res['marker']['owner_yes'], YES)
        self.assertTrue((root / 'art' / 'h9' / 'B.started').exists())
        with Stand.patched(), self.assertRaises(S.Refused):
            TB.run(step)

    def test_incident_refuses(self):
        root, step = Stand.fresh('h9')
        orig = TB.half_b

        def half_b(*a):
            (root / 'prot' / 'new.txt').write_text('x')
            return orig(*a)
        with Stand.patched(), mock.patch.object(TB, 'half_b', half_b), self.assertRaises(SystemExit) as e:
            TB.run(step)
        self.assertEqual(e.exception.code, S.PROTECTED_EXIT)
        self.assertEqual(json.loads((root / 'runs' / 'h9-B-result.json').read_text())['status'], 'refused')

    def test_dry_reads_no_day_and_leaves_no_marker(self):
        root, step = Stand.fresh('h11')
        b = boom()
        with Stand.patched(), mock.patch.object(exp, 'read_day', b), mock.patch.object(TB, 'ref_b', b):
            d = TB.dry(step)
        b.assert_not_called()
        self.assertEqual(sorted(d['new']), ['h11_g2_s0', 'h11_g2_s1', 'h11_step_s1'])
        self.assertEqual(d['refs'], [T.STEP_REF] + T.ALL_REF + T.H_REF)
        self.assertFalse((root / 'art' / 'h11' / 'B.started').exists())


def written_before(root: Path, h: str) -> list:
    """The files a fresh copy starts with."""
    base = Stand.root / 'art' / h
    return sorted(['art/' + h + '/' + p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()]
                  + [f'runs/{h}-result.json'])


# ---------------------------------------------------------------- the rules on B, with boot_b replaced

class Rules(unittest.TestCase):
    def fake_boot(self, table, calls):
        def boot_b(frames, ref, new):
            key = (tuple(ref) if isinstance(ref, list) else ref, tuple(new) if isinstance(new, list) else new)
            calls.append(key)
            d, lo, hi = table.get(key, (0.0, -1.0, 1.0))
            return {'ref': ref, 'new': new, 'd': d, 'ci': [lo, hi]}
        return boot_b

    def test_h9_edges(self):
        pl = {'W': 'h9_d10', 'axis': {'depth': 10}}
        mean = (tuple(T.HP_REF), ('h9_d10_s0', 'h9_d10_s1'))
        eps = 1e-12
        for (d, lo), plateau in (((0.0015 + eps, 1e-6), False), ((0.0015, 1e-6), False),
                                 ((0.0015 - eps, 1e-6), True), ((0.002, 0.0), True), ((0.002, -1e-6), True)):
            calls = []
            with self.subTest(d=d, lo=lo), mock.patch.object(TB, 'boot_b', self.fake_boot({mean: (d, lo, 0.01)},
                                                                                           calls)):
                r = TB.compare_h9({}, pl)
                self.assertEqual('без выигрыша' in r['verdict_B'], plateau, r['verdict_B'])
                self.assertEqual('не на плато' in r['verdict_B'], not plateau, r['verdict_B'])
                self.assertEqual(calls, [mean, ('grid_Hp_s0', 'h9_d10_s0'), ('grid_Hp_s1', 'h9_d10_s1')])

    def test_h11_directions_and_texts(self):
        group = ['h11_g2_s0', 'h11_g2_s1']
        pl = {'G_star': group}
        d_key, e_key = (tuple(T.ALL_REF), tuple(group)), ((T.STEP_REF, 'h11_step_s1'), tuple(group))
        cases = {2: ((-2, -1), (1, 2)), 3: ((-1, 1), (1, 2)), 4: ((1, 2), (1, 2)), 5: ((-1, 1), (-1, 1))}
        for rule, (dci, eci) in cases.items():
            calls = []
            table = {d_key: (0.0, *dci), e_key: (0.0, *eci)}
            with self.subTest(rule=rule), mock.patch.object(TB, 'boot_b', self.fake_boot(table, calls)):
                r = TB.compare_h11({}, pl, {'accepted': 1}, 5)
                self.assertEqual(calls[:2], [d_key, e_key])  # D = group - all, E = group - step
                self.assertEqual(r['rule'], rule)
                self.assertEqual(r['verdict_B'], TB.H11_B_TEXT[rule])
                self.assertTrue(r['verdict_B'].startswith('на B'))
                self.assertEqual([c[0] for c in calls[2:]], [tuple(T.H_REF)] * 3)
        self.assertNotIn('на A групповой', ' '.join(TB.H11_B_TEXT.values()))  # «G* выбран на A» stays


# ---------------------------------------------------------------- AST guard

LATE_DAY = re.compile(r'2019-11-(1[4-9]|[23]\d)|2019-12|2020-')
WORD = re.compile(r'(?<![a-z])(test|refit|final|v2020|sealed)(?![a-z])')
ALLOWED = ('COMMITTED_B',)
HALF_B_USERS = ('split_day', 'ref_b', 'metrics_b', 'boot_b')
A_FUNCTIONS = ('score_a_rows', 'max_abs', 'recheck_passed')
FORBIDDEN_IMPORTS = ('task1.placebo', 'task1.posthoc', 'task1.leakcheck', 'task1.final', 'task1.replicate',
                     'council.broker', 'council.xfer.broker', 'council.reveal')


def violations(src: str) -> list:
    """Day tables only through split_day, read_parquet only in ref_b, the constant 'B' only as HALF_B and HALF_B only
    in the B functions, nothing of B in the A functions, no late day, no word test/refit/final/v2020/sealed outside
    docstrings and COMMITTED_B, no forbidden import, M.days only for a literal 'val'."""
    tree = ast.parse(src)
    docs, func, allowed = set(), {}, set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body and \
                isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
            docs.add(id(n.body[0].value))
        if isinstance(n, ast.FunctionDef):
            for c in ast.walk(n):
                func.setdefault(id(c), n.name)
        if isinstance(n, ast.Assign) and any(getattr(t, 'id', None) in ALLOWED for t in n.targets):
            allowed |= {id(c) for c in ast.walk(n.value) if isinstance(c, ast.Constant)}
    bad = []
    for n in ast.walk(tree):
        line = getattr(n, 'lineno', 0)
        f = func.get(id(n))
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            v = n.value.lower()
            if n.value == 'B' and f is not None:
                bad.append(f"constant 'B' in {f}, line {line}")
            if LATE_DAY.search(v):
                bad.append(f'a day after 2019-11-13, line {line}')
            if WORD.search(v) and id(n) not in allowed:
                bad.append(f'word {WORD.search(v).group(1)!r}, line {line}')
            if 'read_parquet' in v and f != 'ref_b':
                bad.append(f'read_parquet outside ref_b, line {line}')
        if isinstance(n, ast.Name) and n.id == 'HALF_B' and f is not None and f not in HALF_B_USERS:
            bad.append(f'HALF_B in {f}, line {line}')
        if isinstance(n, ast.Name) and f in A_FUNCTIONS and n.id in ('HALF_B', 'b_parts', 'ref_b', 'metrics_b'):
            bad.append(f'{n.id} in the A function {f}, line {line}')
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            if n.value.id == 'exp' and n.attr in ('_read', 'read_day') and f != 'split_day':
                bad.append(f'exp.{n.attr} outside split_day, line {line}')
            if n.value.id == 'exp' and n.attr in ('run', 'metrics', 'compare', 'main'):
                bad.append(f'exp.{n.attr}, line {line}')
            if n.value.id == 'M' and n.attr in ('load', 'main', 'DAYS'):
                bad.append(f'M.{n.attr}, line {line}')
            if n.value.id == 'T' and n.attr == 'read_days':
                bad.append(f'T.read_days (A only) in the B module, line {line}')
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'days' and \
                getattr(n.func.value, 'id', None) == 'M':
            if not (n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == 'val'):
                bad.append(f'M.days other than val, line {line}')
        if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'date' and len(n.args) == 3 and \
                all(isinstance(a, ast.Constant) for a in n.args):
            if tuple(a.value for a in n.args) > (2019, 11, 13):
                bad.append(f'a late date, line {line}')
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                [n.module or ''] + [f'{n.module}.{a.name}' for a in n.names]
            bad += [f'import {m}' for m in mods if m.startswith(FORBIDDEN_IMPORTS)]
    return bad


class Ast(unittest.TestCase):
    def test_module_is_clean(self):
        self.assertEqual(violations(MODULE.read_text(encoding='utf-8')), [])

    def test_snippets_are_caught(self):
        snippets = {
            'read_day': "def f(d, p):\n    return exp.read_day(d, p)\n",
            'pool': "def f(p):\n    return exp._read('train', p)\n",
            'b_in_a': "def score_a_rows(m, rows):\n    return rows[rows.half == HALF_B]\n",
            'b_const': "def f(df):\n    return df[df.half == 'B']\n",
            'half_b_elsewhere': "def g(df):\n    return HALF_B\n",
            'parquet': "def f(p):\n    return duckdb.sql(f\"SELECT * FROM read_parquet('{p}')\")\n",
            'days': "def f():\n    return M.days('train')\n",
            'late': "D = date(2019, 11, 18)\n",
            'late_str': "def f(x):\n    return f'{x}/2019-11-20.parquet'\n",
            'word': "def f():\n    return 'artifacts/task1/v2020'\n",
            'import': "from task1 import placebo\n",
            'a_reader': "def f(ctx, d):\n    return T.read_days('val', ctx.days, d)\n",
        }
        for k, src in snippets.items():
            with self.subTest(k):
                self.assertNotEqual(violations(src), [], k)
        self.assertEqual(violations("HALF_B = 'B'\ndef split_day(d, p):\n    return exp.read_day(d, p), HALF_B\n"), [])


if __name__ == '__main__':
    unittest.main()
