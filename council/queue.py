"""A resumable queue of council fits (contract §3, §4): a JSON list of specs of council.fit, each in its own
`python -m council.fit` process, strictly one at a time, so the peak memory of a record is the peak of its fit.

The whole queue is validated before the first fit. A fit whose file and record exist with the same spec is skipped (a
stopped queue goes on); a file without a record or with another spec stops the queue; a failed fit stops it with its
exit code. The code stamp and the data fingerprint of each fit (fit.data_stamp) are taken once, at the start; every
fit must start and end with them, and a done fit with another fingerprint stops the queue.

  TASK1_PERIOD=2020 .venv/bin/python -m council.queue queue.json
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from council import fit, roles


def load(path):
    """The normalized specs of a queue file; SystemExit on any invalid spec or a repeated name."""
    queue = json.loads(Path(path).read_text())
    if not isinstance(queue, list) or not queue:
        raise SystemExit(f'{path}: a queue is a non-empty JSON list of specs')
    specs = []
    for x in queue:
        try:
            specs.append(fit.validate(x))
        except ValueError as e:
            raise SystemExit(f'{path}: {e}') from None
    names = [s['name'] for s in specs]
    if len(set(names)) != len(names):
        raise SystemExit(f'{path}: repeated fit names')
    return specs


def run(path):
    specs = load(path)
    stamp = fit.code_stamp()
    data = {s['name']: fit.data_stamp(s) for s in specs}  # taken once, like the code stamp
    for s in specs:
        if fit.done(s, data[s['name']]):
            print(json.dumps({'name': s['name'], 'skipped': 'done with the same spec'}), flush=True)
            continue
        with tempfile.TemporaryDirectory(prefix='council-queue-') as tmp:
            f = Path(tmp) / f"{s['name']}.json"
            f.write_text(json.dumps(s))
            r = subprocess.run([sys.executable, '-m', 'council.fit', '--spec', str(f), '--stamp', json.dumps(stamp),
                                '--data', json.dumps(data[s['name']])],
                               cwd=roles.ROOT)
        if r.returncode:
            print(json.dumps({'name': s['name'], 'failed': r.returncode}), file=sys.stderr, flush=True)
            raise SystemExit(r.returncode)
        if not fit.done(s, data[s['name']]):
            raise SystemExit(f"{s['name']}: the fit ended without writing its file")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit('usage: python -m council.queue queue.json')
    run(argv[0])


if __name__ == '__main__':
    main()
