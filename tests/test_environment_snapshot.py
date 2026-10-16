"""Stdlib-only unit regression for the actual environment_snapshot body.

The project module is never imported. Version dependencies are explicit doubles.
One fresh child checks kernel metadata; on Darwin it also checks the real cold
legacy platform denial. This does not establish native CLI behavior.
"""
import sys


def _metadata_child(source_name, fixture_name):
    import signal
    try:
        import resource
    except ImportError:
        resource = None
    if resource is not None:
        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    if hasattr(signal, 'alarm'):
        signal.alarm(5)
    assert sys.flags.isolated and sys.flags.dont_write_bytecode and sys.flags.no_site

    class StdlibOnly:
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split('.')[0] not in sys.stdlib_module_names:
                raise ImportError('Non-stdlib import denied: ' + fullname)
            return None
    sys.meta_path.insert(0, StdlibOnly())

    import ast
    import hashlib
    import importlib.metadata as metadata
    import json
    import os
    from pathlib import Path
    import platform
    from types import ModuleType

    def assert_cold():
        assert getattr(platform, '_platform_cache', {}) == {}
        assert getattr(platform, '_uname_cache', None) is None
    assert_cold()
    assert 'subprocess' not in sys.modules
    versions = dict(catboost='unit-catboost', duckdb='unit-duckdb', numpy='unit-numpy')
    doubles = {}
    for name, value in versions.items():
        assert name not in sys.modules
        module = ModuleType(name)
        module.__version__ = value
        module.__unit_version_double__ = True
        sys.modules[name] = doubles[name] = module
    installed = dict(versions)
    metadata.version = lambda name: installed[name]

    # All synthetic fixture writes finish before the audit is installed.
    fixture = Path(fixture_name)
    roots = {}
    for case in ['match', *versions, 'missing', 'duplicate']:
        root = fixture/case
        root.mkdir()
        rows = list(versions.items())
        if case in versions:
            rows = [(key, 'wrong-lock' if key == case else value) for key, value in rows]
        elif case == 'missing':
            rows = rows[1:]
        elif case == 'duplicate':
            rows += [('catboost', versions['catboost'])]
        (root/'uv.lock').write_text(''.join(
            '[[package]]\nname = '+json.dumps(key)+'\nversion = '+json.dumps(value)+'\n'
            for key, value in rows))
        roots[case] = root
    source = Path(source_name).read_bytes()
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef) and node.name == 'environment_snapshot']
    assert len(nodes) == 1
    namespace = dict(ROOT=roots['match'], duckdb=doubles['duckdb'], np=doubles['numpy'])
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual-environment_snapshot>', 'exec'), namespace)
    snapshot = namespace['environment_snapshot']
    original_uname = getattr(os, 'uname', None)
    if original_uname is None:
        kernel_name = sys.platform
    else:
        kernel = original_uname()  # Direct syscall; never populate platform's caches.
        kernel_name = '-'.join((kernel.sysname, kernel.release, kernel.machine))
    expected = dict(python=sys.version, platform=kernel_name, loaded_packages=versions)
    assert_cold()

    forbidden = []
    class Forbidden(ValueError):
        pass
    def audit(event, args):
        if event == 'import' and args[0].split('.')[0] not in sys.stdlib_module_names:
            raise ImportError('Non-stdlib import denied: '+args[0])
        write = event == 'open' and args[2] & (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        process = event in {'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.fork', 'os.forkpty', 'pty.spawn'} or event.startswith(('os.exec', 'os.spawn'))
        if write or process:
            stack = []
            frame = sys._getframe(1)
            while frame is not None:
                stack.append((frame.f_code.co_filename, frame.f_code.co_name))
                frame = frame.f_back
            forbidden.append(dict(event=event, path=args[0] if write else None,
                                  flags=args[2] if write else None, stack=stack))
            raise Forbidden('Forbidden metadata side effect: '+event)
    sys.addaudithook(audit)

    def rejects(operation, message):
        try:
            operation()
        except ValueError as error:
            assert str(error) == message
        else:
            raise AssertionError('Expected dependency/format rejection')

    result = snapshot(platform_format='kernel')
    assert result == expected and set(result) == {'python', 'platform', 'loaded_packages'}
    assert type(result['python']) is str and type(result['platform']) is str
    assert type(result['loaded_packages']) is dict
    for name in versions:
        message = 'Loaded/installed dependency differs from lock: '+name
        namespace['ROOT'] = roots[name]
        rejects(lambda: snapshot(platform_format='kernel'), message)
        namespace['ROOT'] = roots['match']
        installed[name] = 'wrong-installed'
        rejects(lambda: snapshot(platform_format='kernel'), message)
        installed[name] = versions[name]
        doubles[name].__version__ = 'wrong-loaded'
        rejects(lambda: snapshot(platform_format='kernel'), message)
        doubles[name].__version__ = versions[name]
    for case in ('missing', 'duplicate'):
        namespace['ROOT'] = roots[case]
        rejects(lambda: snapshot(platform_format='kernel'),
                'Loaded/installed dependency differs from lock: catboost')
    namespace['ROOT'] = roots['match']
    if original_uname is None:
        assert snapshot(platform_format='kernel')['platform'] == sys.platform
    else:
        del os.uname
        try:
            assert snapshot(platform_format='kernel')['platform'] == sys.platform
        finally:
            os.uname = original_uname
    rejects(lambda: snapshot(platform_format='unknown'), 'Unknown environment platform format: unknown')
    assert forbidden == []
    assert_cold()

    # Separate compatibility mock, NOT the evidence for the cold legacy denial.
    original_platform = platform.platform
    legacy_calls = []
    def legacy_double():
        legacy_calls.append('legacy')
        return 'unit-legacy-platform'
    platform.platform = legacy_double
    try:
        assert snapshot()['platform'] == 'unit-legacy-platform'
        assert snapshot(platform_format='legacy')['platform'] == 'unit-legacy-platform'
        assert legacy_calls == ['legacy', 'legacy']
    finally:
        platform.platform = original_platform
    assert forbidden == []
    assert_cold()

    # This actual denial witness is scoped to the diagnosed Darwin stdlib path.
    legacy_witness = dict(status='NOT_APPLICABLE', reason='Actual cold legacy probe is Darwin-scoped')
    if sys.platform == 'darwin':
        try:
            snapshot()
        except Forbidden:
            assert len(forbidden) == 1
            event = forbidden[0]
            assert event['event'] == 'open' and event['path'] == os.devnull
            assert event['flags'] & os.O_RDWR
            assert (platform.__file__, 'from_subprocess') in event['stack']
            assert (sys.modules['subprocess'].__file__, '_get_devnull') in event['stack']
            legacy_witness = dict(status='EXPECTED_FORBIDDEN_OPEN', path=event['path'], real_stdlib_stack=True)
        else:
            raise AssertionError('Cold Darwin legacy route did not hit the actual forbidden open')
    assert all(sys.modules[name] is module and module.__unit_version_double__
               for name, module in doubles.items())
    assert not any(name == 'scripts' or name.startswith('scripts.') for name in sys.modules)
    print(json.dumps(dict(source_sha256=hashlib.sha256(source).hexdigest(), kernel_metadata=result,
                          kernel_forbidden_events=0, legacy_witness=legacy_witness,
                          separate_legacy_mock_assertion=True,
                          cold_cache_asserted_without_priming=True, dependency_bodies_imported=False,
                          project_modules_imported=False, mismatches_rejected=11,
                          bounds=dict(CPU_hard_seconds=3 if resource is not None else None,
                                      wall_alarm_seconds=5 if hasattr(signal, 'alarm') else None)), sort_keys=True))
    return 0


_CHILD = __name__ == '__main__' and sys.argv[1:2] == ['--metadata-child']
if not _CHILD:
    import hashlib
    import json
    import os
    from pathlib import Path
    import subprocess
    import tempfile
    import time
    import unittest

    class EnvironmentSnapshot(unittest.TestCase):
        def test_actual_helper_kernel_and_cold_legacy_side_effects(self):
            try:
                import resource
            except ImportError:
                resource = None
            source = Path(__file__).resolve().parents[1]/'scripts/train_baselines.py'
            source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
            usage_before = resource.getrusage(resource.RUSAGE_CHILDREN) if resource is not None else None
            with tempfile.TemporaryDirectory(prefix='environment-snapshot-') as temporary:
                command = [sys.executable, '-I', '-B', '-S', str(Path(__file__).resolve()),
                           '--metadata-child', str(source), temporary]
                started = time.monotonic()
                with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, cwd=temporary) as child:
                    try:
                        stdout, stderr = child.communicate(input=b'', timeout=6)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.communicate(timeout=2)
                        self.fail('Metadata child exceeded bounded wait; killed and reaped')
                    self.assertIsNotNone(child.returncode)
                    self.assertEqual(child.returncode, 0, stderr.decode(errors='replace'))
                    self.assertEqual(stderr, b'')
                launch_to_reap = time.monotonic()-started
            receipt = json.loads(stdout)
            self.assertEqual(receipt['source_sha256'], source_sha)
            self.assertEqual(receipt['kernel_forbidden_events'], 0)
            self.assertFalse(receipt['dependency_bodies_imported'])
            self.assertFalse(receipt['project_modules_imported'])
            self.assertEqual(receipt['legacy_witness']['status'],
                             'EXPECTED_FORBIDDEN_OPEN' if sys.platform == 'darwin' else 'NOT_APPLICABLE')
            usage_after = resource.getrusage(resource.RUSAGE_CHILDREN) if resource is not None else None
            print(json.dumps(dict(child_returncode=child.returncode, child_reaped=True,
                                  child_CPU_seconds=None if resource is None else
                                      (usage_after.ru_utime+usage_after.ru_stime)-(usage_before.ru_utime+usage_before.ru_stime),
                                  launch_to_reap_wall_seconds=launch_to_reap,
                                  child_receipt=receipt), sort_keys=True))


if __name__ == '__main__':
    if _CHILD:
        if len(sys.argv) != 4:
            raise SystemExit('Expected source and owned fixture paths')
        raise SystemExit(_metadata_child(sys.argv[2], sys.argv[3]))
    unittest.main()
