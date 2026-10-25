import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
import pandas as pd

from scripts import rees_agent_test_ablation as A


def small_frame():
    return pd.DataFrame({'qid': ['2020-02-14:1', '2020-02-15:1', '2020-02-15:2'],
                         'ndcg': [.2, .3, .4], 'recall': [.3, .4, .5],
                         'purchase_ndcg': [np.nan, .1, .2],
                         'purchase_recall': [np.nan, .2, .3]})


class AblationTests(unittest.TestCase):
    def setUp(self):
        self.spec = A.read_json(A.ROOT / A.SPEC)

    def test_arm_is_exactly_hp_minus_dfs_without_mutation(self):
        before = json.dumps(self.spec, sort_keys=True)
        arm, spec = A.derive_arm(self.spec)
        hp = next(a for a in self.spec['arms'] if a['name'] == 'Hp')
        self.assertEqual(arm['name'], 'Hag')
        self.assertEqual(arm['config']['extra'], hp['config']['extra'][4:])
        self.assertEqual(len(arm['config']['extra']), 30)
        self.assertEqual({k: v for k, v in arm['config'].items() if k != 'extra'},
                         {k: v for k, v in hp['config'].items() if k != 'extra'})
        self.assertEqual(spec['features'], {'Hag': 146})
        self.assertEqual(before, json.dumps(self.spec, sort_keys=True))

    def test_changed_seed_cap_exclusion_rejected(self):
        for key, value in [('seeds', [[2026, 0]]), ('cap', 123), ('excluded', [])]:
            spec = json.loads(json.dumps(self.spec)); spec[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                A.derive_arm(spec)

    def test_wrong_or_duplicate_feature_membership_rejected(self):
        for position, value in [(0, 'dfs_new'), (5, 'dfs_other'), (5, None)]:
            spec = json.loads(json.dumps(self.spec))
            extras = next(a for a in spec['arms'] if a['name'] == 'Hp')['config']['extra']
            extras[position] = extras[4] if value is None else value
            with self.subTest(position=position, value=value), self.assertRaises(ValueError):
                A.derive_arm(spec)

    def test_output_cannot_overwrite_or_escape(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(A, 'ROOT', Path(tmp)):
            target = Path(tmp) / 'artifacts/task1/new'
            self.assertEqual(A.output_path(target), target.resolve())
            target.mkdir(parents=True)
            with self.assertRaises(FileExistsError): A.output_path(target)
            with self.assertRaises(ValueError): A.output_path(Path(tmp) / 'old')

    def test_exclusive_json_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'new.json'
            A.write_new(p, {'value': 1})
            with self.assertRaises(FileExistsError): A.write_new(p, {'value': 2})
            self.assertEqual(A.read_json(p), {'value': 1})

    def test_hash_mismatch_and_parent_path_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(A, 'ROOT', Path(tmp)):
            p = Path(tmp) / 'x'; p.write_text('original')
            hashes = {'x': A.digest(p)}; A.check_hashes(hashes)
            p.write_text('changed')
            with self.assertRaises(ValueError): A.check_hashes(hashes)
            with self.assertRaises(ValueError): A.check_hashes({'../x': 'invalid'})

    def test_pairing_checks_before_date_exclusions(self):
        a = small_frame()
        with self.assertRaisesRegex(ValueError, 'keys differ'):
            A.compare_frames(a, a, a.iloc[:-1], self.spec, {}, 0)
        b = a.copy(); b.loc[0, ['purchase_ndcg', 'purchase_recall']] = .3
        with self.assertRaisesRegex(ValueError, 'applicability differs'):
            A.compare_frames(a, a, b, self.spec, {}, 0)

    def test_both_contrast_directions_and_exclusions(self):
        dates = pd.date_range('2020-02-14', '2020-02-29').strftime('%Y-%m-%d').tolist()
        main_dates = [d for d in dates if d not in A.EXCLUDED]
        ids = np.arange(1, 79303)
        rows = [(main_dates[int(i) % 14], int(i)) for i in ids]
        rows += [(main_dates[(int(i) % 14 + 1) % 14], int(i)) for i in ids[:18354]]
        rows += [(d, 999999) for d in A.EXCLUDED]
        a = pd.DataFrame({'qid': [f'{d}:{u}' for d, u in rows], 'ndcg': .2,
                          'recall': .3, 'purchase_ndcg': .1, 'purchase_recall': .2})
        hp = a.copy(); hp['ndcg'] = .25
        hag = a.copy(); hag['ndcg'] = .23
        # Excluded-day effect is deliberately opposite; it must not enter the primary result.
        hag.loc[hag.qid.str.startswith(tuple(A.EXCLUDED)), 'ndcg'] = 0
        summary = {'queries': len(a), 'ndcg_by_seed': {'base': [.2, .2], 'Hp': [.25, .25]}}
        original = {'all_days': summary, 'primary': dict(summary, queries=97656)}
        def fake_bootstrap(delta, users, draws, seed):
            self.assertEqual(len(delta), 97656)
            self.assertEqual(len(set(users)), 79302)
            self.assertEqual((draws, seed), (2000, 20261025))
            mean = float(np.mean(delta))
            return {'mean_delta': mean, 'ci95': [mean, mean]}
        with patch.object(A.S, 'bootstrap', side_effect=fake_bootstrap):
            row, signature = A.compare_frames(a, hp, hag.iloc[::-1], self.spec, original, 0)
            self.assertAlmostEqual(row['contrasts']['Hag-base']['mean_delta'], .03)
            self.assertAlmostEqual(row['contrasts']['Hp-Hag']['mean_delta'], .02)
            self.assertEqual(row['days'], 14)
            wrong = (signature[0][:-1], signature[1][:-1])
            with self.assertRaisesRegex(ValueError, 'between seeds'):
                A.compare_frames(a, hp, hag, self.spec, original, 1, wrong)

    def test_plan_rejects_tuning_and_incomplete_manifest(self):
        arm, _ = A.derive_arm(self.spec)
        rep = SimpleNamespace(M=SimpleNamespace(days=lambda split: ['2020-01-15'] if split == 'refit' else ['2020-02-14']))
        exp = SimpleNamespace(DEFAULT={'iterations': 500})
        out = A.ROOT / 'artifacts/task1/unique'
        plan = {'format': 'rees-agent-test-ablation-plan-v1', 'status': A.STATUS,
                'source_spec': A.SPEC, 'source_summary': A.SUMMARY, 'arm': arm, 'features': 146,
                'seeds': A.SEEDS, 'cap': 140680, 'expected_queries': 97656,
                'expected_users': 79302, 'expected_days': 14, 'exclude_anchors': A.EXCLUDED,
                'bootstrap': A.BOOTSTRAP, 'contrasts': ['Hag-base', 'Hp-Hag'],
                'expected_recipe': exp.DEFAULT | arm['config'], 'output_dir': 'artifacts/task1/unique',
                'input_sha256': dict.fromkeys(A.input_paths(arm, rep), 'x'),
                'dependency_sha256': dict.fromkeys(A.DEPENDENCIES, 'x')}
        A.validate_plan(plan, arm, exp, rep, out)
        plan['bootstrap'] = {'draws': 100, 'rng_seed': 1}
        with self.assertRaisesRegex(ValueError, 'bootstrap'): A.validate_plan(plan, arm, exp, rep, out)
        plan['bootstrap'] = A.BOOTSTRAP
        del plan['dependency_sha256']['task1/model.py']
        with self.assertRaisesRegex(ValueError, 'dependency'): A.validate_plan(plan, arm, exp, rep, out)


if __name__ == '__main__':
    unittest.main()
