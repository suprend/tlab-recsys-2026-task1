"""Synthetic tests of the guards and helpers of scripts/otto2_pool.py (no OTTO data is read)."""
import unittest
from unittest import mock

import duckdb
import numpy as np

from scripts import otto_common as oc
from scripts import otto2_pool as op


class SourcesTest(unittest.TestCase):
    def test_parse_source(self):
        self.assertEqual(op.parse_source('4:all'), (4, None))
        self.assertEqual(op.parse_source('2:100'), (2, 100))
        with self.assertRaises(oc.ContractError):
            op.parse_source('5:all')

    def test_fit_refuses_repeated_folds_and_f2_beyond_its_sidecars(self):
        with mock.patch.object(op.om.Context, 'contract', side_effect=AssertionError('reached the context')):
            with self.assertRaises(oc.ContractError):
                op.fit('x', [(4, None), (4, 10)])
            with self.assertRaises(oc.ContractError):
                op.fit('x', [(2, None)])
            with self.assertRaises(oc.ContractError):
                op.fit('x', [(2, oc.N_T + 1)])


class ChosenSessionsTest(unittest.TestCase):
    def test_first_labelled_covered_sessions_per_type_in_sha_order(self):
        con = duckdb.connect()
        rows = [(s, j, 1) for s in range(1, 41) for j in (0, 1, 2) if s % (j + 1) == 0]
        con.execute('CREATE TABLE lab (session BIGINT, tc INTEGER, aid BIGINT)')
        con.executemany('INSERT INTO lab VALUES (?, ?, ?)', rows)
        covered = list(range(1, 31))
        got = op.chosen_sessions(con, covered, 5)
        for j, t in enumerate(oc.TYPES):
            labelled = [s for s in covered if s % (j + 1) == 0]
            self.assertEqual(got[t], oc.first_in_order(labelled, 5))
        every = op.chosen_sessions(con, covered, None)
        self.assertEqual(sorted(every['clicks']), covered)


class AverageTest(unittest.TestCase):
    def test_mean_of_raw_scores(self):
        class Fixed:
            def __init__(self, v):
                self.v = np.asarray(v, dtype=float)

            def predict(self, pool, **kwargs):
                return self.v
        avg = op.Average([Fixed([1, 2]), Fixed([3, 6])])
        np.testing.assert_allclose(avg.predict(None, prediction_type='RawFormulaVal'), [2, 4])


if __name__ == '__main__':
    unittest.main()
