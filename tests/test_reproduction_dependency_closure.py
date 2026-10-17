"""Check the published source tuple without importing project/native modules.

This checks source consistency, not CLI execution or historical018 acceptance.
"""
import ast
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECIPE_PATH = 'configs/reproduction/frozen-bw-oct2019.json'
COMMAND_PATH = 'scripts/reproduce_frozen_comparison.py'
# Membership is intentional: dropping a dependency and repinning the recipe
# must not silently shrink the advertised production closure.
DEPENDENCY_PATHS = frozenset((
    'pyproject.toml',
    'scripts/anchor_pilot.py',
    'scripts/candidate_pilot.py',
    'scripts/development_collection.py',
    'scripts/feature_programs.py',
    'scripts/heldout_contract.py',
    'scripts/heldout_predictions.py',
    'scripts/inference_data.py',
    'scripts/manual_features.py',
    'scripts/metadata_price_features.py',
    'scripts/model_data.py',
    'scripts/program_model_data.py',
    'scripts/protocol_manifest.py',
    'scripts/ranking_metrics.py',
    'scripts/source_import.py',
    'scripts/strong_baseline.py',
    'scripts/temporal_contract.py',
    'scripts/train_baselines.py',
    'uv.lock',
))


def literal_assignment(command, name):
    """Inspect only module-level assignments; never execute command bytes."""
    values = [node.value for node in ast.parse(command).body
              if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == name
                      for target in node.targets)]
    if len(values) != 1:
        raise ValueError('Expected one module-level ' + name + ' assignment')
    return ast.literal_eval(values[0])


def verify_tuple(recipe_raw, command_raw, sources):
    recipe_pin = literal_assignment(command_raw, 'RECIPE_SHA256')
    if recipe_pin != hashlib.sha256(recipe_raw).hexdigest():
        raise ValueError('Production recipe/command SHA256 mismatch')
    dependencies = json.loads(recipe_raw)['dependencies']
    if set(dependencies) != DEPENDENCY_PATHS or set(sources) != DEPENDENCY_PATHS:
        raise ValueError('Production dependency membership changed')
    core_paths = {'scripts/' + name + '.py'
                  for name in literal_assignment(command_raw, 'CORE_ORDER')}
    if not core_paths <= set(dependencies):
        raise ValueError('Production core is absent from pinned dependencies')
    for name, expected in dependencies.items():
        if hashlib.sha256(sources[name]).hexdigest() != expected:
            raise ValueError('Frozen dependency differs: ' + name)


class ReproductionDependencyClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The positive input is always the actual published files. Negative
        # cases copy these byte snapshots in memory, never a toy core/recipe.
        cls.recipe = (ROOT / RECIPE_PATH).read_bytes()
        cls.command = (ROOT / COMMAND_PATH).read_bytes()
        cls.sources = {name: (ROOT / name).read_bytes() for name in DEPENDENCY_PATHS}

    def test_actual_production_recipe_command_and_all_dependencies_agree(self):
        verify_tuple(self.recipe, self.command, self.sources)

    def test_each_altered_production_dependency_is_rejected(self):
        verify_tuple(self.recipe, self.command, self.sources)
        for name, raw in self.sources.items():
            with self.subTest(dependency=name):
                altered = dict(self.sources)
                altered[name] = raw + b'\n# altered dependency\n'
                with self.assertRaises(ValueError) as caught:
                    verify_tuple(self.recipe, self.command, altered)
                self.assertEqual(str(caught.exception), 'Frozen dependency differs: ' + name)

    def test_recipe_byte_change_is_rejected_even_when_json_is_unchanged(self):
        verify_tuple(self.recipe, self.command, self.sources)
        with self.assertRaisesRegex(ValueError, 'Production recipe/command SHA256 mismatch'):
            verify_tuple(self.recipe + b'\n', self.command, self.sources)

    def test_command_recipe_pin_change_is_rejected(self):
        verify_tuple(self.recipe, self.command, self.sources)
        pin = literal_assignment(self.command, 'RECIPE_SHA256').encode('ascii')
        altered = self.command.replace(pin, b'0' * 64, 1)
        self.assertNotEqual(altered, self.command)
        with self.assertRaisesRegex(ValueError, 'Production recipe/command SHA256 mismatch'):
            verify_tuple(self.recipe, altered, self.sources)

    def test_dropping_a_dependency_and_repinning_recipe_is_rejected(self):
        verify_tuple(self.recipe, self.command, self.sources)
        recipe = json.loads(self.recipe)
        del recipe['dependencies']['scripts/train_baselines.py']
        altered_recipe = json.dumps(recipe).encode('utf8')
        pin = literal_assignment(self.command, 'RECIPE_SHA256').encode('ascii')
        altered_command = self.command.replace(
            pin, hashlib.sha256(altered_recipe).hexdigest().encode('ascii'), 1)
        with self.assertRaisesRegex(ValueError, 'Production dependency membership changed'):
            verify_tuple(altered_recipe, altered_command, self.sources)


if __name__ == '__main__':
    unittest.main()
