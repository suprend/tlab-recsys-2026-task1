"""Opt-in toy native lifecycle check; UNRUN source, no research-quality claim."""
import os
import unittest


class DevelopmentTrainingNativeLifecycle(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('TLAB_RUN_NATIVE_TRAINING_TEST') == '1',
                         'Explicit native-test opt-in is required')
    def test_fit_select_copy_shrink_save_reload(self):
        import math
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import time
        from unittest.mock import patch

        start_wall, start_cpu = time.monotonic(), time.process_time()
        checks = 0

        def check():
            nonlocal checks
            checks += 1
            self.assertLess(time.monotonic() - start_wall, 60.0, 'Toy test wall guard')
            self.assertLess(time.process_time() - start_cpu, 45.0, 'Toy test CPU guard')

        check()
        import numpy as np
        from catboost import CatBoostClassifier
        from scripts import adaptive_tree_selection as selection
        from scripts import train_baselines as b
        from scripts.development_training import fit_development
        check()

        ceiling = 8
        names = ['toy_signal', 'toy_flag']
        train = b.Prepared(
            [('train-hit-a', 1, None, frozenset({12})),
             ('train-hit-b', 2, None, frozenset({22})),
             ('train-off-c', 3, None, frozenset({39})),
             ('train-empty-c', 4, None, frozenset({49}))],
            np.asarray([0, 0, 1, 1, 2, 2], dtype=np.int32),
            np.asarray([11, 12, 21, 22, 31, 32], dtype=np.int64),
            np.asarray([[-2, 1], [2, 0], [-1, 0], [1, 1], [-.5, 1], [.5, 0]],
                       dtype=np.float32),
            np.asarray([0, 1, 0, 1, 0, 0], dtype=np.int8), list(names))
        validation = b.Prepared(
            [('validation-hit-and-off-c', 5, None, frozenset({101, 999})),
             ('validation-off-c-only', 6, None, frozenset({888})),
             ('validation-empty-c', 7, None, frozenset({777})),
             ('validation-empty-y', 8, None, frozenset())],
            np.asarray([0, 0, 0, 1, 1, 3, 3], dtype=np.int32),
            np.asarray([103, 101, 102, 202, 201, 402, 401], dtype=np.int64),
            np.asarray([[.25, .5]] * 7, dtype=np.float32),
            np.asarray([0, 1, 0, 0, 0, 0, 0], dtype=np.int8), list(names))
        for data in (train, validation):
            self.assertEqual(data.y.tolist(),
                             [int(int(item) in data.queries[int(group)][3])
                              for item, group in zip(data.items, data.group)])

        model = CatBoostClassifier(
            iterations=ceiling, depth=2, learning_rate=.2, l2_leaf_reg=3,
            random_seed=17, task_type='CPU', thread_count=2, loss_function='Logloss',
            use_best_model=False, allow_writing_files=False, verbose=False,
            boosting_type='Plain', bootstrap_type='No', random_strength=0,
            boost_from_average=False, leaf_estimation_method='Newton',
            leaf_estimation_iterations=1, leaf_estimation_backtracking='No')
        native_fit, native_select = CatBoostClassifier.fit, selection.select_best_tree
        fit_calls, selector_calls = [], []

        def one_native_fit(instance, pool, **kwargs):
            self.assertEqual(fit_calls, [], 'A second physical fit is prohibited')
            self.assertIs(instance, model)
            self.assertEqual(set(kwargs), {'callbacks'})
            self.assertEqual(len(kwargs['callbacks']), 1)
            self.assertEqual(list(pool.get_weight()), [.5] * 6)
            fit_calls.append(instance)
            return native_fit(instance, pool, **kwargs)

        def one_full_selector(instance, data, *, maximum, check):
            self.assertEqual(selector_calls, [])
            self.assertIs(instance, model)
            self.assertIs(data, validation)
            self.assertEqual(instance.tree_count_, maximum)
            self.assertEqual(maximum, ceiling)
            selector_calls.append(instance)
            return native_select(instance, data, maximum=maximum, check=check)

        with patch.object(CatBoostClassifier, 'fit', one_native_fit), \
                patch.object(selection, 'select_best_tree', one_full_selector):
            result = fit_development(model, train, validation,
                                     max_iterations=ceiling, check=check)
        self.assertEqual(len(fit_calls), 1)
        self.assertEqual(len(selector_calls), 1)
        self.assertIs(result.full_model, model)
        self.assertIsNot(result.selected_model, model)
        self.assertEqual((result.trained_ceiling, model.tree_count_), (ceiling, ceiling))
        self.assertEqual(result.validation_support,
                         {'fullY_positive_queries': 3, 'candidate_rows': 5, 'informative_candidate_groups': 1})
        self.assertEqual(result.training_accounting['queries'], 4)
        self.assertEqual(result.training_accounting['empty_candidate_groups'], 1)
        self.assertEqual(result.training_accounting['row_weight_sum'], 3.0)
        self.assertEqual(len(result.validation_curve), ceiling)

        # Independent full-Y NDCG@20: no production layout/ranking/metric helpers.
        oracle_curve, prefix_scores = [], []
        for count in range(1, ceiling + 1):
            check()
            scores = np.asarray(model.predict(validation.x, prediction_type='RawFormulaVal',
                                              ntree_start=0, ntree_end=count, thread_count=2))
            self.assertEqual(scores.shape, (7,))
            self.assertTrue(np.isfinite(scores).all())
            # Identical feature rows force exact score ties and item-ID tiebreaks.
            self.assertTrue(np.equal(scores, scores[0]).all())
            prefix_scores.append(scores.copy())
            query_ndcg = []
            for group, (_, _, _, full_y) in enumerate(validation.queries):
                if not full_y:
                    continue
                rows = [i for i, value in enumerate(validation.group) if int(value) == group]
                ranked = sorted(rows, key=lambda i: (-float(scores[i]), int(validation.items[i])))
                dcg = sum(1 / math.log2(rank + 2) for rank, row in enumerate(ranked[:20])
                          if int(validation.items[row]) in full_y)
                ideal = sum(1 / math.log2(rank + 2) for rank in range(min(20, len(full_y))))
                query_ndcg.append(dcg / ideal)
            self.assertEqual(len(query_ndcg), 3)
            oracle_curve.append(sum(query_ndcg) / len(query_ndcg))
        for actual, expected in zip(result.validation_curve, oracle_curve):
            self.assertIs(type(actual), float)
            self.assertLessEqual(abs(actual - expected), 1e-12)
        peak = max(oracle_curve)
        expected_count = min(i + 1 for i, value in enumerate(oracle_curve)
                             if peak - value <= 1e-12)
        self.assertEqual(expected_count, 1)  # All prefixes tie; copy must really shrink.
        self.assertEqual(result.selected_trees, expected_count)
        self.assertEqual(result.selected_model.tree_count_, expected_count)
        self.assertEqual(model.tree_count_, ceiling)
        self.assertEqual(result.selected_model.feature_names_, names)

        check()
        selected_scores = np.asarray(result.selected_model.predict(
            validation.x, prediction_type='RawFormulaVal', thread_count=2))
        self.assertTrue(np.isfinite(selected_scores).all())
        self.assertEqual(selected_scores.shape, (7,))
        self.assertLessEqual(float(np.max(np.abs(selected_scores - prefix_scores[expected_count - 1]))),
                             1e-12)
        with TemporaryDirectory(prefix='tlab-native-development-toy-') as temporary:
            path = Path(temporary) / 'selected-toy.cbm'
            result.selected_model.save_model(str(path))
            check()
            reloaded = CatBoostClassifier()
            reloaded.load_model(str(path))
            self.assertEqual(reloaded.tree_count_, expected_count)
            self.assertEqual(reloaded.feature_names_, names)
            reloaded_scores = np.asarray(reloaded.predict(
                validation.x, prediction_type='RawFormulaVal', thread_count=2))
            self.assertEqual(reloaded_scores.shape, (7,))
            self.assertTrue(np.isfinite(reloaded_scores).all())
            self.assertLessEqual(float(np.max(np.abs(reloaded_scores - selected_scores))), 1e-12)
            check()
        self.assertFalse(Path(temporary).exists())
        retained_scores = np.asarray(model.predict(
            validation.x, prediction_type='RawFormulaVal', ntree_end=ceiling, thread_count=2))
        self.assertEqual(retained_scores.shape, (7,))
        self.assertTrue(np.isfinite(retained_scores).all())
        self.assertLessEqual(float(np.max(np.abs(retained_scores - prefix_scores[-1]))), 1e-12)
        self.assertEqual(model.tree_count_, ceiling)
        self.assertGreaterEqual(checks, ceiling)
        check()


if __name__ == '__main__':
    unittest.main()
