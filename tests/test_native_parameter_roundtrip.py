"""Metadata-only regression for the captured fixed-model parameter roundtrip."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import unittest

from scripts import heldout_predictions as production
from tests.oracles import heldout_prediction_audit as oracle


class FakeNative:
    """Expose captured metadata only; every native operation is forbidden."""
    def __init__(self, fixture, *, params=None, tree=None, names=None, indices=None):
        self.params = deepcopy(fixture['loaded_parameters'] if params is None else params)
        self.tree_count_ = fixture['tree_count'] if tree is None else tree
        self.feature_names_ = list(fixture['feature_names'] if names is None else names)
        self.indices = deepcopy(dict(cat=fixture['cat_feature_indices'], text=fixture['text_feature_indices'],
                                     embedding=fixture['embedding_feature_indices']) if indices is None else indices)

    def get_all_params(self): return deepcopy(self.params)
    def get_cat_feature_indices(self): return self.indices.get('cat', [])
    def get_text_feature_indices(self): return self.indices.get('text', [])
    def get_embedding_feature_indices(self): return self.indices.get('embedding', [])
    def load_model(self, *args, **kwargs): raise AssertionError('No model loading in metadata tests')
    def predict(self, *args, **kwargs): raise AssertionError('No prediction in metadata tests')
    def fit(self, *args, **kwargs): raise AssertionError('No fitting in metadata tests')


class NativeParameterRoundtripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parent / 'fixtures' / 'native_parameter_roundtrip.json'
        cls.fixture = json.loads(path.read_text(encoding='utf-8'))

    def setUp(self):
        f = self.fixture
        # A syntactically valid synthetic reference, never a model-file claim.
        self.spec = dict(model=dict(path='tests/fixtures/native_parameter_roundtrip.json',
            sha256=f['provenance']['source_capture_sha256']), feature_names=list(f['feature_names']),
            trained_iterations=300, scoring_prefix=300, population=26000,
            effective_parameters=deepcopy(f['expected_parameters']))
        self.params = deepcopy(f['loaded_parameters'])
        self.expected = self.spec['effective_parameters']['bayesian_matrix_reg']
        self.loaded = self.params['bayesian_matrix_reg']

    def checks(self, *, params=None, spec=None, **metadata):
        spec = deepcopy(self.spec if spec is None else spec)
        params = self.params if params is None else params
        yield lambda: production.verify_model(FakeNative(self.fixture, params=params, **metadata), spec)
        def independent():
            oracle.model_spec(spec, 41)
            oracle.native_model(FakeNative(self.fixture, params=params, **metadata), spec)
        yield independent

    def reject(self, **kwargs):
        for index, check in enumerate(self.checks(**kwargs)):
            with self.subTest(verifier=index), self.assertRaises(ValueError): check()

    def test_captured_complete_parameter_state_is_accepted_without_native_work(self):
        self.assertEqual(len(self.params), 40)
        self.assertEqual(len(self.spec['feature_names']), 41)
        self.assertEqual({k for k in self.params if self.params[k] != self.spec['effective_parameters'][k]},
                         {'bayesian_matrix_reg', 'learning_rate'})
        self.assertNotEqual(self.expected, self.loaded)
        before = deepcopy([self.spec, self.params])
        for check in self.checks(): check()
        self.assertEqual([self.spec, self.params], before)

    def test_bayesian_list_descendants_cannot_use_scalar_alias(self):
        for wrap in (lambda v: [v], lambda v: [[v]]):
            spec = deepcopy(self.spec); params = deepcopy(self.params)
            spec['effective_parameters']['bayesian_matrix_reg'] = wrap(self.expected)
            params['bayesian_matrix_reg'] = wrap(self.loaded)
            self.reject(spec=spec, params=params)
        for compare in (lambda e, a: production._same(e, a), lambda e, a: oracle.native_equal(a, e)):
            with self.assertRaises(ValueError):
                compare([{'bayesian_matrix_reg': self.expected}], [{'bayesian_matrix_reg': self.loaded}])

    def test_next_float32_and_nonalias_inside_same_bin_are_rejected(self):
        bits = struct.unpack('!I', struct.pack('!f', self.expected))[0]
        next_value = struct.unpack('!f', struct.pack('!I', bits + 1))[0]
        same_bin = self.expected + 1e-10
        self.assertEqual(struct.pack('!f', same_bin), struct.pack('!f', self.expected))
        self.assertNotEqual(same_bin, self.loaded)
        for actual in (next_value, same_bin):
            params = deepcopy(self.params); params['bayesian_matrix_reg'] = actual
            self.reject(params=params)

    def test_unrelated_and_nested_float_fields_keep_original_precision(self):
        for nested in (False, True):
            spec = deepcopy(self.spec); params = deepcopy(self.params)
            spec['effective_parameters']['metadata'] = {'bayesian_matrix_reg': self.expected} if nested else self.expected
            params['metadata'] = {'bayesian_matrix_reg': self.loaded} if nested else self.loaded
            self.reject(spec=spec, params=params)

    def test_existing_learning_rate_scalar_and_list_tolerance_is_preserved(self):
        expected = self.spec['effective_parameters']['learning_rate']; actual = self.params['learning_rate']
        for compare in (lambda e, a: production._same(e, a, ('learning_rate',)),
                        lambda e, a: oracle.native_equal(a, e, ('learning_rate',))):
            for wrap in (lambda v: v, lambda v: [v], lambda v: [[v]]): compare(wrap(expected), wrap(actual))
            with self.assertRaises(ValueError): compare([expected], [expected + 1e-8])

    def test_parameter_types_finiteness_and_exact_schema_remain_strict(self):
        for actual in (True, 0, float('nan'), float('inf')):
            params = deepcopy(self.params); params['bayesian_matrix_reg'] = actual
            self.reject(params=params)
        for change in ('missing', 'extra', 'bool_integer'):
            params = deepcopy(self.params)
            if change == 'missing': del params['bayesian_matrix_reg']
            elif change == 'extra': params['unrecognized'] = 0.0
            else: params['iterations'] = True
            self.reject(params=params)

    def test_fixed_parameters_native_tree_feature_order_and_numeric_state_remain_strict(self):
        params = deepcopy(self.params); params['depth'] = 7; self.reject(params=params)
        for tree in (299, 300.0): self.reject(tree=tree)
        names = list(self.spec['feature_names']); names[0], names[1] = names[1], names[0]
        self.reject(names=names)
        for kind in ('cat', 'text', 'embedding'): self.reject(indices={kind: [0]})


if __name__ == '__main__': unittest.main()
