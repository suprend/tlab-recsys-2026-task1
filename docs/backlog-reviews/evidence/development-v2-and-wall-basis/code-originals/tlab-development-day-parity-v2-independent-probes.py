"""Narrow V2 repair transport; original V1 attacks are retained separately."""
import ast
import hashlib
import io
import json
from pathlib import Path
import resource
import signal
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

START = time.monotonic()
resource.setrlimit(resource.RLIMIT_CPU, (59, 60))
signal.alarm(115)
BASE = Path('/tmp/tlab-development-day-parity-v2-independent-inputs')
SOURCE = BASE / 'tlab-development-day-parity-v2.py'
TESTS = BASE / 'tlab-test-development-day-parity-v2.py'
V1 = Path('/tmp/tlab-development-day-parity-v1-independent-inputs')
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == 'ae133b9f8725ba99883d604609a29a62201f070a6cd7a81ddf9460488e011baa'
assert hashlib.sha256(TESTS.read_bytes()).hexdigest() == '23385a8061ed378cf68fda0e69b593c2598b06393f186473ad79734ab96ef6a7'
original = BASE / 'tlab-development-day-parity-v1-independent-probes.py'
assert hashlib.sha256(original.read_bytes()).hexdigest() == '516f5641046d90f8423b6c88498b282af49da5f0fa0c2132b0eb966b8860a627'

old_ast = ast.parse((V1 / 'tlab-development-day-parity-v1.py').read_bytes())
new_ast = ast.parse(SOURCE.read_bytes())
old_functions = {n.name:ast.dump(n, include_attributes=False) for n in old_ast.body if isinstance(n, ast.FunctionDef)}
new_functions = {n.name:ast.dump(n, include_attributes=False) for n in new_ast.body if isinstance(n, ast.FunctionDef)}
changed_functions = [n for n in old_functions if old_functions[n] != new_functions[n]]
assert changed_functions == ['compare_tables', '_npz', 'verify_request']
assert set(old_functions) == set(new_functions)
old_fixture = next(n for n in ast.parse((V1 / 'tlab-test-development-day-parity-v1.py').read_bytes()).body if isinstance(n, ast.ClassDef))
new_fixture = next(n for n in ast.parse(TESTS.read_bytes()).body if isinstance(n, ast.ClassDef))
for method in ['setUp', 'tearDown', 'compare']:
    before = next(n for n in old_fixture.body if isinstance(n, ast.FunctionDef) and n.name == method)
    after = next(n for n in new_fixture.body if isinstance(n, ast.FunctionDef) and n.name == method)
    assert ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False)

test_tree = ast.parse(TESTS.read_bytes(), filename=str(TESTS))
path_changes = 0
for node in ast.walk(test_tree):
    if isinstance(node, ast.Constant) and node.value == '/tmp/tlab-development-day-parity-v2.py':
        node.value = str(SOURCE)
        path_changes += 1
assert path_changes == 1
module = types.ModuleType('frozen_v2_author_tests')
module.__file__ = str(TESTS)
exec(compile(test_tree, str(TESTS), 'exec'), module.__dict__)
p, np = module.p, module.np
log = io.StringIO()
suite = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(module.Parity))
assert suite.wasSuccessful()
outcomes = {'frozen_author_suite':dict(tests=suite.testsRun, failures=len(suite.failures), errors=len(suite.errors), success=suite.wasSuccessful())}


def fixture():
    f = module.Parity('test_complete_positive_global_mapping_and_nonprefix_extras')
    f.setUp()
    return f


# Same original corrupt-value SQL and alias; expect rejection with no mutation.
f = fixture()
try:
    f.con.execute("UPDATE new_b SET item_distinct_viewers_7d=99 WHERE query_id='d-selected'")
    f.con.execute('CREATE TEMP VIEW parity_day_b AS SELECT * FROM new_b')
    f.tables['new_b'] = 'parity_day_b'
    before = f.con.execute("SELECT item_distinct_viewers_7d FROM parity_day_b WHERE query_id='d-selected' ORDER BY product_id").fetchall()
    calls = []
    actual_run = p.run

    def traced_run(*args, **kwargs):
        calls.append(args[1])
        return actual_run(*args, **kwargs)

    with patch.object(p, 'run', side_effect=traced_run):
        try:
            f.compare()
        except ValueError as exc:
            error = str(exc)
        else:
            raise AssertionError('Reserved alias must reject')
    after = f.con.execute("SELECT item_distinct_viewers_7d FROM parity_day_b WHERE query_id='d-selected' ORDER BY product_id").fetchall()
    assert error == 'Reserved internal relation names forbidden' and calls == []
    assert before == after == [(99,), (99,)]
    outcomes['original_reserved_view_collision'] = dict(rejected=True, error=error, comparator_SQL_calls=len(calls), before=before, after=after)
finally:
    f.tearDown()

# Same original2-row archive and3-row replacement bytes. V2 added a read/check,
# so transport fires after all three headers rather than old check ordinal2.
f = fixture()
try:
    with tempfile.TemporaryDirectory(prefix='tlab-parity-v2-independent-npz-') as tmp:
        path = Path(tmp) / 'scores.npz'
        original_arrays = dict(group=np.array([1, 3], dtype=np.int32), product_id=np.array([10, 11], dtype=np.int64), raw_score=np.array([.1, .2], dtype=np.float64))
        replacement = dict(group=np.array([1, 3, 1], dtype=np.int32), product_id=np.array([10, 11, 12], dtype=np.int64), raw_score=np.array([.1, .2, .3], dtype=np.float64))
        np.savez_compressed(path, **original_arrays)
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        header_count = 0
        changed = False
        shapes = []
        actual_header = np.lib.format.read_array_header_1_0
        actual_array = np.lib.format.read_array

        def traced_header(*args, **kwargs):
            global header_count
            answer = actual_header(*args, **kwargs)
            header_count += 1
            return answer

        def traced_array(*args, **kwargs):
            answer = actual_array(*args, **kwargs)
            shapes.append(list(answer.shape))
            return answer

        def seam():
            global changed
            module.check()
            if header_count >= 3 and not changed:
                np.savez_compressed(path, **replacement)
                changed = True

        with patch.object(np.lib.format, 'read_array_header_1_0', side_effect=traced_header), patch.object(np.lib.format, 'read_array', side_effect=traced_array):
            frame = p._npz(f.con, path, 'replacement_probe', check=seam, rows=2, expected_sha=expected)
        assert changed and shapes == [[2], [2], [2]]
        assert frame.product_id.tolist() == [10, 11]
        f.con.unregister('replacement_probe')
        try:
            p._hash(path, expected, module.check, cap=262144)
        except ValueError as exc:
            pin_error = str(exc)
        else:
            raise AssertionError('Original byte pin must reject replaced path')
        outcomes['original_post_header_NPZ_replacement'] = dict(changed_path=True, validated_rows=2, replacement_rows=3, allocated_shapes=shapes, loaded_items=frame.product_id.tolist(), original_expected_sha_supplied=True, final_original_pin_rejected=True, final_pin_error=pin_error)
finally:
    f.tearDown()

module.check()
r = resource.getrusage(resource.RUSAGE_SELF)
receipt = dict(scope='independent narrow PARITYv2 repair replay', source_sha256='ae133b9f8725ba99883d604609a29a62201f070a6cd7a81ddf9460488e011baa', tests_sha256='23385a8061ed378cf68fda0e69b593c2598b06393f186473ad79734ab96ef6a7', original_V1_probe_sha256='516f5641046d90f8423b6c88498b282af49da5f0fa0c2132b0eb966b8860a627', changed_source_functions=changed_functions, identical_fixture_methods=['setUp','tearDown','compare'], transport_adaptations=['one author test module-path constant points to exact frozen V2','alias assertion expects pre-SQL rejection instead of V1 false pass','NPZ race fires after three validated headers instead of old ordinal2 because V2 added bounded snapshot check','private expected_sha argument exercises closed-adapter NPZ binding','NPZ assertion expects original2-row allocation and final path-pin rejection'], outcomes=outcomes, cpu_seconds=r.ru_utime+r.ru_stime, wall_seconds=time.monotonic()-START, peak_rss_bytes=r.ru_maxrss*(1 if sys.platform=='darwin' else 1024), bounds=dict(cpu_seconds=60,wall_seconds=120,rss_bytes=512*2**20,threads=2), fixture=dict(queries=4,candidate_pairs=8,event_rows=0,largest_NPZ_array_rows=3,models=0,fits=0,Y=0), guard_attempts=module.ATTEMPTS, real_data_reads=0, project_writes=0, children=0, actual_closed_positive_adapter_run=False, runtime_grant=False)
with Path('/tmp/tlab-development-day-parity-v2-independent-probe-results.json').open('x') as f:
    json.dump(receipt, f, indent=2)
    f.write('\n')
with Path('/tmp/tlab-development-day-parity-v2-independent-author-suite.log').open('x') as f:
    f.write(log.getvalue())
print(json.dumps(receipt, sort_keys=True))
