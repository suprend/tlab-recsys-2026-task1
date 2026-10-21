import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from scripts import hm_ma_placebo as pl


def block(n=50):
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({'customer_id': np.repeat(np.arange(n//5), 5), 'article_id': np.tile(np.arange(5), n//5),
                          'a': rng.normal(size=n), 'b': rng.integers(0, 3, size=n).astype(float)})
    frame.loc[[3, 7, 11], 'a'] = np.nan
    return frame


class Permute(unittest.TestCase):
    def test_keys_stay_values_move_together(self):
        frame = block()
        out = pl.permute(frame, ['a', 'b'], 2026, '2020-09-16')
        pd.testing.assert_frame_equal(out[['customer_id', 'article_id']], frame[['customer_id', 'article_id']])
        rows = lambda f: sorted(map(tuple, f[['a', 'b']].fillna(-99).to_numpy().tolist()))
        self.assertEqual(rows(out), rows(frame))
        self.assertEqual(out['a'].isna().sum(), 3)
        self.assertFalse(out[['a', 'b']].fillna(-99).equals(frame[['a', 'b']].fillna(-99)))
        perm = pl.permutation(len(frame), 2026, '2020-09-16')
        np.testing.assert_array_equal(out['a'].to_numpy(), frame['a'].to_numpy()[perm])
        np.testing.assert_array_equal(out['b'].to_numpy(), frame['b'].to_numpy()[perm])

    def test_deterministic_and_keyed_by_seed_and_anchor(self):
        p = pl.permutation(100, 2026, '2020-09-16')
        np.testing.assert_array_equal(p, pl.permutation(100, 2026, '2020-09-16'))
        self.assertFalse((p == pl.permutation(100, 2027, '2020-09-16')).all())
        self.assertFalse((p == pl.permutation(100, 2026, '2020-09-09')).all())

    def test_input_not_modified(self):
        frame = block()
        copy = frame.copy()
        pl.permute(frame, ['a', 'b'], 2026, '2020-09-16')
        pd.testing.assert_frame_equal(frame, copy)


class Reading(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(pl.reading([(0.003, [0.001, 0.005]), (0.002, [0.0001, 0.004])]), pl.READINGS[0])
        self.assertEqual(pl.reading([(0.001, [-0.001, 0.003]), (-0.001, [-0.003, 0.0])]), pl.READINGS[1])
        self.assertEqual(pl.reading([(-0.003, [-0.005, -0.001]), (-0.002, [-0.004, -0.0001])]), pl.READINGS[2])
        self.assertEqual(pl.reading([(0.003, [0.001, 0.005]), (0.001, [-0.001, 0.003])]), pl.READINGS[3])
        self.assertEqual(pl.reading([(-0.003, [-0.005, -0.001]), (0.001, [-0.001, 0.003])]), pl.READINGS[3])
        self.assertEqual(pl.reading([(0.0, [0.0, 0.002]), (0.0, [0.0, 0.002])]), pl.READINGS[1])


def fake_report(seed, n, status='completed'):
    return dict(format=pl.ma.FIT_FORMAT, arm='MA', seed=seed, status=status,
                inputs=[dict(anchor='2020-09-16', role='validation')], training_populations=[],
                validation_population=dict(anchor='2020-09-16', fit_rows=n))


def patched(tmp):
    return [mock.patch.object(pl, 'committed', return_value='abc'),
            mock.patch.object(pl.kaggle, 'private_path', side_effect=lambda p: Path(p))]


class Fit(unittest.TestCase):
    def run_fit(self, fake, tmp):
        with contextlib.ExitStack() as stack:
            for patch in patched(tmp):
                stack.enter_context(patch)
            stack.enter_context(mock.patch.object(pl.ma, 'fit_ma', fake))
            return pl.fit(2026, ['t'], 'v', Path(tmp)/'sidecars', 'p', Path(tmp)/'out')

    def test_wraps_sidecar_rows_and_marks_report(self):
        frame = block()
        seen = []

        def fake_fit_ma(seed, train, sidecars, prereg, output, validation, threads, wall_seconds):
            seen.append(pl.ma.sidecar_rows(None, frame, Path(sidecars)/'2020-09-16'/'agent.parquet', ['a', 'b']))
            output.mkdir()
            (output/'report.json').write_text(json.dumps(fake_report(seed, len(frame))))

        original = pl.ma.sidecar_rows
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(pl.ma, 'sidecar_rows', lambda con, f, path, columns: f):
            r = self.run_fit(fake_fit_ma, tmp)
            self.assertEqual(r['arm'], pl.ARM)
            self.assertEqual(r['status'], 'completed')
            self.assertEqual(r['placebo']['permuted'], [dict(anchor='2020-09-16', rows=len(frame))])
            self.assertEqual(r['placebo']['commit'], 'abc')
            pd.testing.assert_frame_equal(seen[0], pl.permute(frame, ['a', 'b'], 2026, '2020-09-16'))
        self.assertIs(pl.ma.sidecar_rows, original)

    def test_unpermuted_anchor_fails_the_fit(self):
        def fake_fit_ma(seed, train, sidecars, prereg, output, validation, threads, wall_seconds):
            output.mkdir()  # the patch never ran: no anchor was permuted
            (output/'report.json').write_text(json.dumps(fake_report(seed, 50)))

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                self.run_fit(fake_fit_ma, tmp)
            stored = json.loads((Path(tmp)/'out'/'report.json').read_text())
            self.assertEqual((stored['arm'], stored['status']), (pl.ARM, 'failed'))

    def test_failed_fit_is_marked_too(self):
        def failing(seed, train, sidecars, prereg, output, validation, threads, wall_seconds):
            output.mkdir()
            (output/'report.json').write_text(json.dumps(dict(arm='MA', status='failed')))
            raise ValueError('boom')

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self.run_fit(failing, tmp)
            self.assertEqual(json.loads((Path(tmp)/'out'/'report.json').read_text())['arm'], pl.ARM)

    def test_existing_output_is_never_touched(self):
        def fake_fit_ma(*args):
            raise AssertionError('fit_ma must not run')

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'out'
            out.mkdir()
            (out/'report.json').write_text('{"arm": "MA", "status": "completed"}')
            before = (out/'report.json').read_bytes()
            with self.assertRaises(FileExistsError):
                self.run_fit(fake_fit_ma, tmp)
            self.assertEqual((out/'report.json').read_bytes(), before)

    def test_validation_required(self):
        with mock.patch.object(pl, 'committed', return_value='abc'):
            with self.assertRaises(ValueError):
                pl.fit(2026, ['t'], None, 's', 'p', 'o')


def write_fit(root, name, arm, seed, ap12, **change):
    import duckdb
    path = Path(root)/name
    path.mkdir()
    users = pd.DataFrame(dict(customer_id=[f'u{i:02d}' for i in range(len(ap12))],
                              targets=[1 if a is not None else 0 for a in ap12],
                              ap12=[a if a is not None else 0.0 for a in ap12]))
    duckdb.sql(f"COPY (SELECT * FROM users) TO '{path/'query-metrics.parquet'}' (FORMAT PARQUET)")
    positive = [a for a in ap12 if a is not None]
    report = dict(format=pl.kaggle.FIT_FORMAT if arm == 'M' else pl.ma.FIT_FORMAT, arm=arm, seed=seed,
                  status='completed', validation_metrics=dict(map_at_12_conditional=sum(positive)/len(positive)),
                  files={'query-metrics.parquet': pl.experiment.sha256_file(path/'query-metrics.parquet')},
                  inputs=[dict(anchor='2020-09-16', role='validation')], training_populations=[],
                  validation_population=dict(anchor='2020-09-16', fit_rows=50),
                  hyperparameters=dict(depth=8, random_seed=seed), runtime=dict(catboost='1'), database='db',
                  features=dict(contract_digest='c', numeric=['x'] if arm == 'M' else ['x', 'a'], categorical=[]),
                  agent=dict(columns=['a']), code=dict(m='1'))
    if arm == pl.ARM:
        report['placebo'] = dict(commit='abc', code={'own': '1'},
                                 permuted=[dict(anchor='2020-09-16', rows=50)])
    report.update(change)
    (path/'report.json').write_text(json.dumps(report))
    return path


class Read(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        rng = np.random.default_rng(1)
        self.base = [float(x) for x in rng.uniform(0, 0.3, 40)]+[None]*10

    def tearDown(self):
        self.tmp.cleanup()

    def fits(self, ma_shift=0.1, pl_shift=0.0, **placebo_change):
        shift = lambda s: [None if a is None else a+s for a in self.base]
        paths = dict(ma=[write_fit(self.root, f'MA{s}', 'MA', s, shift(ma_shift)) for s in (2026, 2027)],
                     m=[write_fit(self.root, f'M{s}', 'M', s, shift(0.0)) for s in (2026, 2027)],
                     pl=[write_fit(self.root, f'MApl{s}', pl.ARM, s, shift(pl_shift), **placebo_change)
                         for s in (2026, 2027)])
        return paths

    def read(self, paths, output='result.json'):
        with mock.patch.object(pl, 'ROOT', self.root), mock.patch.object(pl, 'committed', return_value='head'), \
                mock.patch.object(pl, 'unchanged_since', return_value=True), \
                mock.patch.object(pl, 'own_code', return_value={'own': '1'}), \
                mock.patch.object(pl.kaggle, 'private_path', side_effect=lambda p: Path(p)):
            return pl.read(paths['ma'], paths['pl'], paths['m'], self.root/output)

    def test_directions_and_reading(self):
        r = self.read(self.fits(ma_shift=0.1, pl_shift=-0.02))
        for seed in ('2026', '2027'):
            self.assertAlmostEqual(r['D'][seed]['d'], 0.12)
            self.assertAlmostEqual(r['P'][seed]['d'], -0.02)
            self.assertAlmostEqual(r['MA_minus_M'][seed]['d'], 0.1)
        self.assertEqual(r['reading'], pl.READINGS[0])
        self.assertEqual(r['commit'], 'abc')
        self.assertTrue((self.root/'result.json').is_file())

    def test_identical_placebo_is_not_distinguishable(self):
        self.assertEqual(self.read(self.fits(ma_shift=0.1, pl_shift=0.1))['reading'], pl.READINGS[1])

    def test_refusals(self):
        cases = [dict(runtime=dict(catboost='2')), dict(placebo=dict(commit='other', code={'own': '1'},
                 permuted=[dict(anchor='2020-09-16', rows=50)])),
                 dict(placebo=dict(commit='abc', code={'own': '1'}, permuted=[])),
                 dict(validation_metrics=dict(map_at_12_conditional=0.5))]
        for i, change in enumerate(cases):
            with self.subTest(i=i):
                self.tmp.cleanup()
                self.tmp = tempfile.TemporaryDirectory()
                self.root = Path(self.tmp.name).resolve()
                paths = self.fits()
                if i == 1:  # one of the two placebo fits from another commit
                    write_fit(self.root, 'other', pl.ARM, 2027, self.base,
                              **change)
                    paths['pl'][1] = self.root/'other'
                else:
                    paths['pl'] = [write_fit(self.root, f'x{s}', pl.ARM, s, self.base, **change)
                                   for s in (2026, 2027)]
                with self.assertRaises(ValueError):
                    self.read(paths)

    def test_existing_output_refused(self):
        paths = self.fits()
        (self.root/'result.json').write_text('{}')
        with self.assertRaises(FileExistsError):
            self.read(paths)


if __name__ == '__main__':
    unittest.main()
