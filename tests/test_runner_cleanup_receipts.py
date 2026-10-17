"""Real tiny runner paths with a forwarding connection that fails only on close."""
from contextlib import ExitStack
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import duckdb

from scripts import anchor_pilot as a
from scripts import candidate_pilot as c
from scripts import heuristic_baselines as h
from scripts import manual_features as m
from tests import test_heuristic_baselines as fixtures

ROOT = Path(__file__).resolve().parents[1]


class CloseFaultConnection:
    """Delegate SQL/profiling/interrupt to the actual synthetic connection."""
    def __init__(self, real, error):
        self.real = real
        self.error = error
        self.close_calls = 0
        self.closed_real = False

    def __getattr__(self, name):
        return getattr(self.real, name)

    def close(self):
        self.close_calls += 1
        self.real.close()
        self.closed_real = True
        raise self.error


class RunnerCleanupReceiptTests(unittest.TestCase):
    def setUp(self):
        original = fixtures.fixture

        def full_fixture(con):
            original(con)
            con.execute('ALTER TABLE events ADD COLUMN category_id BIGINT DEFAULT 100')
            con.execute('CREATE TABLE ingest_metadata(source_sha256 VARCHAR)')
            con.execute("INSERT INTO ingest_metadata VALUES ('synthetic-source')")

        # Build and seal real toy DB/Q/Y/C before faulting connection creation.
        with patch.object(fixtures, 'fixture', side_effect=full_fixture):
            fixtures.ProvenanceRunnerTests.setUp(self)
        for module in [a, c, m]:
            active = patch.object(module, 'ROOT', self.root)
            active.start()
            self.addCleanup(active.stop)
        (self.root / 'scripts/manual_features.py').write_text(
            (ROOT / 'scripts/manual_features.py').read_text())
        self.registry = self.root / 'configs/features/manual-18.json'
        self.registry.parent.mkdir(parents=True)
        self.registry.write_text((ROOT / 'configs/features/manual-18.json').read_text())

    def output(self, runner, suffix):
        if runner == 'heuristic':
            return self.root / 'artifacts/heuristic-baselines' / suffix
        return self.root / 'artifacts' / (runner + '-' + suffix)

    def execute(self, runner, output):
        if runner == 'manual':
            return m.run(self.candidate, self.registry, output, acceptance_path=self.acceptance_path)
        if runner == 'anchor':
            return a.run(ROOT / 'configs/protocols/clock-48h.json', self.db, output)
        if runner == 'candidate':
            return c.run(self.anchor, output)
        return h.run(self.candidate, self.acceptance_path, output, replicates=2)

    def receipt(self, output):
        paths = list(output.glob('*/report.json'))
        self.assertEqual(len(paths), 1)
        return paths[0], json.loads(paths[0].read_text())

    def exercise_fault(self, runner, primary=None):
        output = self.output(runner, 'fault')
        close_error = OSError('unique synthetic close fault')
        real_connect = duckdb.connect
        connections = []

        def connect(*args, **kwargs):
            connection = CloseFaultConnection(real_connect(*args, **kwargs), close_error)
            connections.append(connection)
            return connection

        # Raise only after the real compiler/ranker has completed on toy data.
        module, operation = {
            'manual': (m, 'create_manual_features'),
            'anchor': (a, 'build_pilot'),
            'candidate': (c, 'build_candidates'),
            'heuristic': (h, 'report_rankings'),
        }[runner]
        original = getattr(module, operation)
        completed = []

        def fail_after_real_operation(*args, **kwargs):
            original(*args, **kwargs)
            completed.append(True)
            raise primary

        expected = primary if primary is not None else close_error
        with ExitStack() as stack:
            stack.enter_context(patch('duckdb.connect', side_effect=connect))
            if primary is not None:
                stack.enter_context(patch.object(module, operation, side_effect=fail_after_real_operation))
            with self.assertRaises(type(expected)) as caught:
                self.execute(runner, output)
        self.assertIs(caught.exception, expected)
        self.assertEqual(len(connections), 1)  # no automatic retry/new connection
        self.assertEqual(connections[0].close_calls, 1)
        self.assertTrue(connections[0].closed_real)
        path, report = self.receipt(output)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error_type'], type(expected).__name__)
        self.assertEqual(report['error'], str(expected))
        self.assertEqual(report['cleanup_errors'], [dict(operation='close_connection',
            error_type='OSError', error='unique synthetic close fault')])
        self.assertIn('process_peak_rss_bytes', report)
        self.assertIn('seconds', report)
        self.assertIn('temp_disk_bytes_after_close', report)
        if runner != 'heuristic':
            self.assertTrue((path.parent / 'run.json').is_file())
        if primary is not None:
            self.assertEqual(completed, [True])
        elif runner == 'manual':
            self.assertTrue((path.parent / 'features.parquet').is_file())
        elif runner == 'anchor':
            self.assertTrue((path.parent / 'queries.parquet').is_file())
            self.assertTrue((path.parent / 'labels.parquet').is_file())
        elif runner == 'candidate':
            self.assertTrue((path.parent / 'candidates.parquet').is_file())
        else:
            self.assertTrue((path.parent / 'rankings.jsonl').is_file())

    def test_successful_bodies_with_close_fault_persist_failed_receipts_and_raise(self):
        for runner in ['manual', 'anchor', 'candidate', 'heuristic']:
            with self.subTest(runner=runner):
                self.exercise_fault(runner)

    def test_primary_timeout_identity_and_both_causes_survive_close_fault(self):
        for runner in ['manual', 'anchor', 'candidate', 'heuristic']:
            with self.subTest(runner=runner):
                self.exercise_fault(runner, TimeoutError('unique primary timeout'))

    def test_primary_base_exception_also_survives_cleanup(self):
        self.exercise_fault('manual', KeyboardInterrupt('unique primary interrupt'))

    def test_healthy_connections_still_complete_without_cleanup_errors(self):
        for runner in ['manual', 'anchor', 'candidate', 'heuristic']:
            with self.subTest(runner=runner):
                output = self.output(runner, 'healthy')
                result = self.execute(runner, output)
                _, report = self.receipt(output)
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(report['status'], 'complete')
                self.assertNotIn('cleanup_errors', report)
                self.assertTrue(all(row['status'] == 'complete' for row in report['stages']))


if __name__ == '__main__':
    unittest.main()
