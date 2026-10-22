"""council.side.coverage (H13) on a synthetic REES46-shaped database under /tmp/tlab-side-*; no real data is read.

Checks: the tail of T_fit before S0; the database is opened read-only (a write fails) with threads 4 and 4GB;
the six current sources come from task1.build's SQL; per query the union's hits never exceed the targets, a
unique hit is a hit of one source only, new-source rows at K are monotone in K, hits outside the union do not
exceed hits; the days6 check matches a days6 table built by task1.build from the same database; the light gate
journals light-start/-end in the side journal and waits while a `-m council.(queue|fit|memory)` process
lives, taking the protected snapshot only after that wait; run() writes only under the temporary roots and the database file is
unchanged; the efficiency contrast decides on synthetic counts; --dry opens nothing under artifacts/ or data/.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_side_coverage -v
"""
import hashlib
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from council import side as S
from council.side import coverage as C
from council.tests.test_side_tinkoff_anchor import run_dry, tmp_root

ROOT = Path(__file__).resolve().parents[2]
ANCHORS = ['2020-01-29', '2020-01-30']


def synthetic_db(path: Path, seed=0, users=300, items=400):
    """Events of 2020-01-10..01-31 with clustered sessions (items of a cluster are co-viewed and co-bought)."""
    import duckdb
    from task1 import data
    rng = np.random.default_rng(seed)
    clusters = 20
    item_cluster = rng.integers(0, clusters, items)
    by_cluster = [np.flatnonzero(item_cluster == c) for c in range(clusters)]
    rows = []
    start = datetime(2020, 1, 10)
    for u in range(users):
        fav = rng.integers(0, clusters, 2)
        for d in range(22):
            if rng.random() > 0.45:
                continue
            sess = f'{u}-{d}'
            c = by_cluster[fav[rng.integers(0, 2)]]
            t = start + timedelta(days=d, hours=int(rng.integers(0, 20)))
            for j in range(int(rng.integers(2, 8))):
                p = int(c[rng.integers(0, len(c))])
                t += timedelta(minutes=int(rng.integers(1, 9)))
                kind = 'view'
                r = rng.random()
                if r < 0.12:
                    kind = 'cart'
                elif r < 0.17:
                    kind = 'purchase'
                rows.append((t, kind, 1000 + p, 50 + int(item_cluster[p]), f'cat{item_cluster[p] % 5}.sub',
                             f'b{p % 30}', round(float(rng.uniform(1, 100)), 2), 10 ** 6 + u, sess))
    df = pd.DataFrame(rows, columns=list(data.SCHEMA))
    con = duckdb.connect(str(path))
    cols = ', '.join(f'{c} {t}' for c, t in data.SCHEMA.items())
    con.execute(f'CREATE TABLE events ({cols})')
    con.register('_ev', df)
    con.execute('INSERT INTO events SELECT * FROM _ev ORDER BY event_time')
    data.derive(con)
    con.close()


def build_days6(db: Path, out: Path, days):
    """days6 tables of the synthetic database by task1.build itself (its connect with the database patched)."""
    from datetime import date
    from unittest import mock
    from task1 import build
    with mock.patch.object(build, 'DB', db):
        con = build.connect(threads=2)
        for d in days:
            build.build_day(con, date.fromisoformat(d), out)
        con.close()


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tmp_root()
        cls.db = cls.root / 'rees46-synthetic.duckdb'
        synthetic_db(cls.db)
        cls.digest = hashlib.sha256(cls.db.read_bytes()).hexdigest()
        cls.days6 = cls.root / 'days6'
        build_days6(cls.db, cls.days6, ANCHORS)
        cls.tmp = cls.root / 'duckdb-tmp'


class Spec(unittest.TestCase):
    def test_tail(self):
        s = C.spec()
        self.assertEqual(s['anchors'], ['2020-01-29', '2020-01-30', '2020-01-31', '2020-02-01', '2020-02-02'])
        self.assertEqual(s['duckdb'], {'threads': 4, 'memory_limit': '4GB', 'read_only': True,
                                       'temp': str(C.DUCKDB_TMP)})
        self.assertTrue(s['db'].endswith('rees46-2020.duckdb'))
        C.check_days(s)
        with self.assertRaises(S.Refused):
            C.check_days(s | {'anchors': ['2020-02-03']})
        with self.assertRaises(S.Refused):
            C.tail_days(['2020-02-01', '2020-02-02', '2020-02-03'], 2, before='2020-02-03')


class Database(Base):
    def test_read_only_and_settings(self):
        con = C.attach_db(self.db, self.tmp)
        try:
            self.assertEqual(con.execute("SELECT current_setting('threads')").fetchone()[0], 4)
            mem = con.execute("SELECT current_setting('memory_limit')").fetchone()[0]
            self.assertTrue(mem.startswith(('3.7', '4')), mem)
            with self.assertRaises(Exception):
                con.execute('CREATE TABLE src.main.x (a INT)')
            with self.assertRaises(Exception):
                con.execute('DELETE FROM src.events')
            self.assertGreater(con.execute('SELECT count(*) FROM src.events').fetchone()[0], 1000)
        finally:
            con.close()

    def test_anchor_invariants(self):
        con = C.attach_db(self.db, self.tmp)
        try:
            pq, info = C.anchor_queries(con, ANCHORS[0])
        finally:
            con.close()
        self.assertGreater(len(pq), 10)
        self.assertGreater(info['i2v_vocab'], 3)
        self.assertTrue((pq['hits_U'] <= pq['n_targets']).all())
        for s in C.CURRENT:
            self.assertTrue((pq[f'uhits_{s}'] <= pq[f'hits_{s}']).all())
            self.assertTrue((pq[f'hits_{s}'] <= pq['hits_U']).all())
            self.assertTrue((pq[f'urows_{s}'] <= pq[f'rows_{s}']).all())
        self.assertTrue((sum(pq[f'rows_{s}'] for s in C.CURRENT) >= pq['rows_U']).all())
        for s in C.NEW:
            for a, b in zip(C.K_GRID, C.K_GRID[1:]):
                self.assertTrue((pq[f'rows_{s}_{a}'] <= pq[f'rows_{s}_{b}']).all())
                self.assertTrue((pq[f'hits_{s}_{a}'] <= pq[f'hits_{s}_{b}']).all())
            for k in C.K_GRID:
                self.assertTrue((pq[f'rows_{s}_{k}'] <= k).all())
                self.assertTrue((pq[f'nhits_{s}_{k}'] <= pq[f'hits_{s}_{k}']).all())
                self.assertTrue((pq[f'nrows_{s}_{k}'] <= pq[f'rows_{s}_{k}']).all())
                self.assertTrue((pq[f'hits_{s}_{k}'] <= pq['n_targets']).all())
        self.assertGreater(pq['rows_i2v_50'].sum(), 0)
        self.assertGreater(pq['rows_cp1_50'].sum(), 0)
        self.assertGreater(pq['hits_i2v_200'].sum(), 0)
        chk = C.days6_check(ANCHORS[0], self.days6)
        self.assertEqual(chk, (int(pq['hits_U'].sum()), int(pq.loc[pq['rows_U'] > 0, 'n_targets'].sum())))

    def test_run(self):
        out = S.Out(C.NAME, self.root / 'art', self.root / 'runs')
        prot = self.root / 'prot'
        prot.mkdir(exist_ok=True)
        (prot / 'f').write_text('x')
        s = C.spec() | {'anchors': ANCHORS}
        res = C.run(out, s, wait=False, gate_kw={'lock_path': self.root / 'heavy.lock', 'procs_fn': lambda: []},
                    protected=[prot], db=self.db, days6=self.days6, draws=200, tmp=self.tmp)
        self.assertEqual(res['status'], 'ok')
        self.assertTrue(res['build_match'])
        self.assertEqual(set(res['days']), set(ANCHORS))
        self.assertIn(res['pooled']['weakest_current'], C.CURRENT)
        self.assertEqual(set(res['primary']), set(C.PRIMARY))
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), self.digest)
        written = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*')
                         if p.is_file() and not p.relative_to(self.root).as_posix().startswith(
                             ('days6/', 'duckdb-tmp/', 'prot/', 'rees46-synthetic', 'heavy.lock')))
        self.assertEqual(written, ['art/coverage/per_query.parquet', 'runs/coverage.json', 'runs/queue.jsonl'])
        events = [json.loads(x)['event'] for x in (self.root / 'runs' / 'queue.jsonl').read_text().splitlines()]
        self.assertEqual(events[0], 'light-start')
        self.assertEqual(events[-1], 'light-end')
        stored = json.loads((self.root / 'runs' / 'coverage.json').read_text())
        self.assertEqual(stored['spec_digest'], C.spec_digest(s))


class Gate(unittest.TestCase):
    def test_rees46_filter(self):
        procs = [(1, 0, 'python -m council.queue c_val'), (2, 0, 'python -m council.fit --plan'),
                 (3, 0, 'python -m council.memory --arm ALLP'), (4, 0, 'python scripts/xfer_model.py fit'),
                 (5, 0, 'python -I council/side/coverage.py')]
        self.assertEqual([p for p, _ in C.rees46_heavy(procs, own=set())], [1, 2, 3])

    def test_waits_for_rees46_then_snapshots(self):
        """The run waits while `-m council.queue` lives; what that step writes meanwhile is not a change."""
        root = tmp_root()
        out = S.Out(C.NAME, root / 'art', root / 'runs')
        prot = root / 'prot'
        prot.mkdir()
        calls = []

        def procs():
            calls.append(1)
            if len(calls) <= 3:
                (prot / f'fit{len(calls)}').write_text('x')
                return [(4242, 1, 'python -m council.queue c_val')]
            return []
        db = root / 'db.duckdb'
        synthetic_db(db, users=120, items=150)
        res = C.run(out, C.spec() | {'anchors': ANCHORS[:1]}, wait=True,
                    gate_kw={'lock_path': root / 'heavy.lock', 'procs_fn': procs, 'sleep': lambda _: None},
                    protected=[prot], db=db, days6=root / 'none', draws=50, tmp=root / 't')
        self.assertEqual(res['status'], 'ok')
        events = [json.loads(x) for x in out.journal.read_text().splitlines()]
        self.assertTrue(any(e['event'] == 'light-wait' and 'rees46 heavy' in e.get('reason', '') for e in events))
        with self.assertRaises(Exception):
            C.wait_rees46(out, wait=False, procs_fn=lambda: [(9, 1, 'python -m council.fit')])


class Stats(unittest.TestCase):
    def frame(self, n, new_hits, new_rows, weak_hits, weak_rows, seed=0):
        rng = np.random.default_rng(seed)
        d = {'n_targets': np.full(n, 2), 'hits_U': np.ones(n, int), 'rows_U': np.full(n, 300)}
        for s in C.CURRENT:
            d |= {f'hits_{s}': np.ones(n, int), f'uhits_{s}': rng.binomial(1, 0.2, n), f'rows_{s}': np.full(n, 50),
                  f'urows_{s}': np.full(n, 40)}
        d[f'uhits_{C.CURRENT[0]}'] = rng.binomial(weak_rows, weak_hits / weak_rows, n)
        d[f'urows_{C.CURRENT[0]}'] = np.full(n, weak_rows)
        for s in C.NEW:
            for k in C.K_GRID:
                d |= {f'hits_{s}_{k}': np.zeros(n, int), f'rows_{s}_{k}': np.full(n, k),
                      f'nhits_{s}_{k}': rng.binomial(new_rows, new_hits / new_rows, n),
                      f'nrows_{s}_{k}': np.full(n, new_rows)}
        return pd.DataFrame(d)

    def test_decisions(self):
        pq = self.frame(2000, new_hits=0.5, new_rows=40, weak_hits=0.05, weak_rows=40)
        p = C.pooled(pq)
        self.assertEqual(p['weakest_current'], C.CURRENT[0])
        res = C.primary(pq, p['weakest_current'], draws=300)
        self.assertEqual({v['decision'] for v in res.values()}, {'окупается'})
        pq = self.frame(2000, new_hits=0.05, new_rows=40, weak_hits=0.5, weak_rows=40)
        res = C.primary(pq, C.CURRENT[0], draws=300)
        self.assertEqual({v['decision'] for v in res.values()}, {'не окупается'})


class Dry(unittest.TestCase):
    def test_dry(self):
        r = run_dry('coverage')
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertTrue(d['dry'])
        self.assertTrue(d['gate'].startswith('light_wait(probe)'))


if __name__ == '__main__':
    unittest.main()
