"""Frozen-code review probes; only tiny invented relations and /tmp NPZ."""
import ast
import hashlib
import io
import json
import os
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
BASE = Path('/tmp/tlab-development-day-parity-v1-independent-inputs')
SOURCE = BASE / 'tlab-development-day-parity-v1.py'
TESTS = BASE / 'tlab-test-development-day-parity-v1.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == 'aa5ddc8d033bbd7f51fa4a75ff9162f953a957d8eb379b68277d07125e9e8811'
assert hashlib.sha256(TESTS.read_bytes()).hexdigest() == 'f3548b322177362f0b29bff4e863ed47078e2bf88ca82801598e83799a17f982'

# The sole AST adaptation points author tests at this exact frozen source.
tree = ast.parse(TESTS.read_bytes(), filename=str(TESTS))
changes = 0
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and node.value == '/tmp/tlab-development-day-parity-v1.py':
        node.value = str(SOURCE)
        changes += 1
assert changes == 1
module = types.ModuleType('frozen_author_tests')
module.__file__ = str(TESTS)
exec(compile(tree, str(TESTS), 'exec'), module.__dict__)
p, np = module.p, module.np


def fixture():
    obj = module.Parity('test_complete_positive_global_mapping_and_nonprefix_extras')
    obj.setUp()
    return obj


outcomes = {}
log = io.StringIO()
result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(module.Parity))
outcomes['frozen_author_suite'] = dict(tests=result.testsRun, success=result.wasSuccessful(), failures=len(result.failures), errors=len(result.errors))
assert result.wasSuccessful()

# The same corrupt B value is first rejected with the ordinary input relation.
f = fixture()
try:
    f.con.execute("UPDATE new_b SET item_distinct_viewers_7d=99 WHERE query_id='d-selected'")
    try:
        f.compare()
    except ValueError as exc:
        outcomes['ordinary_corrupt_base_control'] = dict(rejected=True, error=str(exc))
    else:
        raise AssertionError('Ordinary corrupted B control must reject')
finally:
    f.tearDown()

# Caller-owned views are allowed by the declared API. A legal distinct input
# view collides with an internal replacement view and loses its corrupt rows.
f = fixture()
try:
    f.con.execute("UPDATE new_b SET item_distinct_viewers_7d=99 WHERE query_id='d-selected'")
    f.con.execute('CREATE TEMP VIEW parity_day_b AS SELECT * FROM new_b')
    f.tables['new_b'] = 'parity_day_b'
    before = f.con.execute("SELECT item_distinct_viewers_7d FROM parity_day_b WHERE query_id='d-selected' ORDER BY product_id").fetchall()
    answer = f.compare()
    after = f.con.execute("SELECT item_distinct_viewers_7d FROM parity_day_b WHERE query_id='d-selected' ORDER BY product_id").fetchall()
    assert before == [(99,), (99,)] and after == [(7,), (7,)]
    outcomes['reserved_view_collision'] = dict(accepted=True, before=before, after=after, returned_status=answer['status'], candidate_count=answer['candidate_count'])
finally:
    f.tearDown()

# All arrays stay tiny: the validated archive has2 rows and its replacement3.
# Observe actual numpy allocation shapes after the second budget check seam.
f = fixture()
try:
    with tempfile.TemporaryDirectory(prefix='tlab-parity-independent-npz-') as tmp:
        path = Path(tmp) / 'scores.npz'
        original = dict(group=np.array([1, 3], dtype=np.int32), product_id=np.array([10, 11], dtype=np.int64), raw_score=np.array([.1, .2], dtype=np.float64))
        replacement = dict(group=np.array([1, 3, 1], dtype=np.int32), product_id=np.array([10, 11, 12], dtype=np.int64), raw_score=np.array([.1, .2, .3], dtype=np.float64))
        np.savez_compressed(path, **original)
        calls = 0
        observed_shapes = []
        actual_read_array = np.lib.format.read_array

        def traced_read_array(*args, **kwargs):
            array = actual_read_array(*args, **kwargs)
            observed_shapes.append(list(array.shape))
            return array

        def seam():
            global calls
            module.check()
            calls += 1
            if calls == 2:
                np.savez_compressed(path, **replacement)

        with patch.object(np.lib.format, 'read_array', side_effect=traced_read_array):
            try:
                p._npz(f.con, path, 'replacement_probe', check=seam, rows=2)
            except ValueError as exc:
                outcomes['npz_reopen_after_header_validation'] = dict(eventually_rejected=True, error=str(exc), validated_rows=2, allocated_shapes=observed_shapes, replacement_rows=3, checks=calls)
            else:
                raise AssertionError('Replacement shape must eventually reject')
        assert observed_shapes == [[3], [3], [3]], observed_shapes
finally:
    f.tearDown()

module.check()
r = resource.getrusage(resource.RUSAGE_SELF)
receipt = dict(scope='independent frozen PARITYv1 tiny probes only', original_source_sha256='aa5ddc8d033bbd7f51fa4a75ff9162f953a957d8eb379b68277d07125e9e8811', original_test_sha256='f3548b322177362f0b29bff4e863ed47078e2bf88ca82801598e83799a17f982', AST_adaptation=dict(path_constants=changes, implementation_changes=0), outcomes=outcomes, cpu_seconds=r.ru_utime+r.ru_stime, wall_seconds=time.monotonic()-START, peak_rss_bytes=r.ru_maxrss*(1 if sys.platform=='darwin' else 1024), bounds=dict(cpu_seconds=60,wall_seconds=120,rss_bytes=512*2**20,threads=2), fixture=dict(queries=4,candidate_pairs=8,event_rows=0,largest_NPZ_array_rows=3,models=0,fits=0,Y=0), guard_attempts=module.ATTEMPTS, actual_data_reads=0, project_writes=0, children=0, runtime_grant=False)
out = Path('/tmp/tlab-development-day-parity-v1-independent-probe-results.json')
with out.open('x') as f:
    json.dump(receipt, f, indent=2)
    f.write('\n')
with Path('/tmp/tlab-development-day-parity-v1-independent-author-suite.log').open('x') as f:
    f.write(log.getvalue())
print(json.dumps(receipt, sort_keys=True))
