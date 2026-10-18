"""Reserve v2 customer IDs from pre-cutoff history, without accessing test Y.

The production entry point pins the v2 contract and original typed database.
Only transactions.t_dat/customer_id and the six old users.parquet projections
are read. No old manifest, feature frame, target, model or outcome is opened.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
CONFIG_SHA256 = '84f3e2db341358a72ae7938c90af0696f5926b91faba746f61b801a7f7cd8b8b'
DATABASE_SHA256 = 'cc346f6c680c915936c0f50c1ff80ed36bd9a7c21a6cd5e2d41f005d0f2a1579'
DATABASE_BYTES = 1164980224
ANCHORS = ('2020-08-05', '2020-08-12', '2020-08-19', '2020-08-26',
           '2020-09-02', '2020-09-09', '2020-09-16')
CACHE_ANCHORS = ANCHORS[1:]
CUTOFF = date(2020, 9, 16)
SALT = 'hm-v2-customer-test-20261018'
OLD_USERS = 20000
NEW_USERS = 20000
MIN_FREE_BYTES = 10 * 1024**3


class Deadline:
    def __init__(self, seconds):
        if not 0 < seconds <= 1800:
            raise ValueError('wall_seconds must be positive and at most1800')
        self.expires = time.monotonic() + seconds

    def check(self):
        if time.monotonic() >= self.expires:
            raise TimeoutError('Reservation wall deadline exceeded')

    def interrupt(self, con):
        timer = threading.Timer(max(0, self.expires-time.monotonic()), con.interrupt)
        timer.daemon = True
        timer.start()
        return timer


def sha256_file(path, deadline=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            if deadline is not None:
                deadline.check()
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False)+'\n', encoding='utf-8', newline='\n')


def load_config(path):
    path = Path(path).resolve()
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != CONFIG_SHA256:
        raise ValueError('Reservation requires the frozen v2 config bytes')
    config = json.loads(payload.decode('utf-8'))
    holdout = config['customer_holdout']
    if (config['version'] != 2 or holdout['anchor'] != CUTOFF.isoformat()
            or holdout['users'] != 20000 or holdout['history_days'] != 90
            or holdout['salt'] != SALT):
        raise ValueError('Customer reservation contract differs from fixed protocol')
    return config


def cached_user_paths():
    return {anchor: ROOT/'artifacts'/'hm-campaign'/'collections'/f'{anchor}-c0q120'/'users.parquet'
            for anchor in CACHE_ANCHORS}


def id_digest(con, table, order, deadline):
    digest = hashlib.sha256()
    # Identifiers/order are private constant choices, not caller-controlled SQL.
    if (table, order) not in {('hm_auto_reserved', 'reservation_rank'),
                             ('hm_auto_excluded', 'customer_id')}:
        raise ValueError('Unsupported ID digest relation')
    cursor = con.execute(f'SELECT customer_id FROM {table} ORDER BY {order}')
    while block := cursor.fetchmany(8192):
        deadline.check()
        for (customer,) in block:
            encoded = customer.encode('utf-8')
            digest.update(len(encoded).to_bytes(4, 'big'))
            digest.update(encoded)
    return digest.hexdigest()


def construct_reservation(con, cache_paths, *, old_users=20000, new_users=20000,
                          deadline=None):
    """Construct private TEMP ID relations; small limits are for tiny fixtures.

    Production calls only with fixed20k limits. Cache paths are fixed at the
    entry point. Historical global aggregates may later include these users;
    supervised query sets must explicitly remain disjoint from the reservation.
    """
    deadline = deadline or Deadline(1800)
    if set(cache_paths) != set(CACHE_ANCHORS):
        raise ValueError('Exactly the six original cached cohorts are required')
    if not (isinstance(old_users, int) and not isinstance(old_users, bool)
            and isinstance(new_users, int) and not isinstance(new_users, bool)
            and 0 < old_users <= 20000 and 0 < new_users <= 20000):
        raise ValueError('Invalid reservation cohort limits')
    earliest = date.fromisoformat(ANCHORS[0])-timedelta(days=90)
    # This is the ONLY source-table scan. There is no post-cutoff predicate,
    # article column, label construction, target file or positive-count access.
    con.execute('''CREATE TEMP TABLE hm_auto_history AS
        SELECT t_dat,customer_id FROM transactions
        WHERE t_dat >= ?::DATE AND t_dat < ?::DATE''',
                [earliest.isoformat(), CUTOFF.isoformat()])
    invalid = con.execute('''SELECT count(*) FROM hm_auto_history WHERE customer_id IS NULL
        OR NOT regexp_full_match(customer_id,'[0-9a-f]{64}')''').fetchone()[0]
    if invalid:
        raise ValueError('Historical customer IDs must be nonmissing64hex strings')
    con.execute('CREATE TEMP TABLE hm_auto_old (anchor DATE,customer_id VARCHAR)')
    reconstructed = []
    for anchor in ANCHORS:
        deadline.check()
        con.execute('''INSERT INTO hm_auto_old
            SELECT ?::DATE,customer_id FROM (
              SELECT DISTINCT customer_id FROM hm_auto_history
              WHERE t_dat >= ?::DATE-INTERVAL '90 days' AND t_dat < ?::DATE
              ORDER BY sha256(customer_id || ':2026'),customer_id LIMIT ?
            )''', [anchor, anchor, anchor, old_users])
        count = con.execute('SELECT count(*) FROM hm_auto_old WHERE anchor=?::DATE', [anchor]).fetchone()[0]
        if count != old_users:
            raise ValueError('Insufficient past users to reconstruct a full old cohort')
        reconstructed.append({'anchor': anchor, 'users': count})
    con.execute('''CREATE TEMP TABLE hm_auto_excluded AS
        SELECT DISTINCT customer_id FROM hm_auto_old ORDER BY customer_id''')
    inputs = []
    for anchor in CACHE_ANCHORS:
        deadline.check()
        path = Path(cache_paths[anchor]).resolve()
        if path.name != 'users.parquet':
            raise ValueError('Only old users.parquet files may be opened')
        before = path.stat()
        digest = sha256_file(path, deadline)
        con.execute('''CREATE OR REPLACE TEMP TABLE hm_auto_actual AS
            SELECT customer_id FROM read_parquet(?)''', [str(path)])
        total, unique, nulls = con.execute('''SELECT count(*),count(DISTINCT customer_id),
            count(*) FILTER (WHERE customer_id IS NULL) FROM hm_auto_actual''').fetchone()
        if total != old_users or unique != total or nulls:
            raise ValueError('Old cached query cohort has wrong size/duplicates/missing IDs')
        missing = con.execute('''SELECT count(*) FROM hm_auto_actual a
            WHERE NOT EXISTS(SELECT 1 FROM hm_auto_excluded e WHERE e.customer_id=a.customer_id)''').fetchone()[0]
        if missing:
            raise ValueError('Actual old queries are not covered by reconstructed exclusion union')
        # Check each corresponding cohort too: fail if a wrong old file was supplied.
        mismatch = con.execute('''SELECT count(*) FROM hm_auto_actual a WHERE NOT EXISTS(
            SELECT 1 FROM hm_auto_old e WHERE e.anchor=?::DATE AND e.customer_id=a.customer_id)''',
                               [anchor]).fetchone()[0]
        if mismatch:
            raise ValueError('Actual old queries differ from their history-only anchor reconstruction')
        after = path.stat()
        if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                or sha256_file(path, deadline) != digest):
            raise ValueError('Old users file changed during reservation')
        inputs.append({'anchor': anchor, 'path': path.as_posix(), 'bytes': before.st_size,
                       'sha256': digest, 'users': total, 'covered_by_reconstruction': True})
    con.execute('''CREATE TEMP TABLE hm_auto_eligible AS
        SELECT DISTINCT h.customer_id FROM hm_auto_history h
        WHERE h.t_dat >= ?::DATE-INTERVAL '90 days' AND h.t_dat < ?::DATE
          AND NOT EXISTS(SELECT 1 FROM hm_auto_excluded e WHERE e.customer_id=h.customer_id)''',
                [CUTOFF.isoformat(), CUTOFF.isoformat()])
    con.execute('''CREATE TEMP TABLE hm_auto_reserved AS
        SELECT customer_id,sha256(customer_id || ':' || ?) AS cohort_hash,
          row_number() OVER(ORDER BY sha256(customer_id || ':' || ?),customer_id) AS reservation_rank
        FROM hm_auto_eligible ORDER BY cohort_hash,customer_id LIMIT ?''', [SALT, SALT, new_users])
    count = con.execute('SELECT count(*) FROM hm_auto_reserved').fetchone()[0]
    if count != new_users:
        raise ValueError('Insufficient unused history-eligible customers')
    overlap = con.execute('''SELECT count(*) FROM hm_auto_reserved r
        JOIN hm_auto_excluded e USING(customer_id)''').fetchone()[0]
    if overlap:
        raise ValueError('Reserved and excluded customers overlap')
    deadline.check()
    return {'reconstructed_cohorts': reconstructed, 'actual_old_cohorts': inputs,
            'excluded_users': con.execute('SELECT count(*) FROM hm_auto_excluded').fetchone()[0],
            'remaining_history_eligible_users': con.execute('SELECT count(*) FROM hm_auto_eligible').fetchone()[0],
            'reserved_users': count, 'overlap_users': overlap,
            'reserved_ordered_ids_sha256': id_digest(con, 'hm_auto_reserved', 'reservation_rank', deadline),
            'excluded_ordered_ids_sha256': id_digest(con, 'hm_auto_excluded', 'customer_id', deadline)}


def reserve(database, output, *, config=None, wall_seconds=1800):
    import duckdb
    started = time.monotonic()
    deadline = Deadline(wall_seconds)
    config = Path(config) if config is not None else ROOT/'configs'/'datasets'/'hm-auto-v2.json'
    load_config(config)
    output = Path(output).resolve()
    allowed = (ROOT/'artifacts'/'hm-auto-v2').resolve()
    if (not allowed.is_relative_to(ROOT.resolve()) or output == allowed
            or not output.is_relative_to(allowed)):
        raise ValueError('Reservation output must be a new child of artifacts/hm-auto-v2')
    if output.exists():
        raise FileExistsError('Reservation output already exists')
    database = Path(database).resolve()
    before = database.stat()
    if before.st_size != DATABASE_BYTES or sha256_file(database, deadline) != DATABASE_SHA256:
        raise ValueError('Reservation requires the original pinned typed database')
    output.mkdir(parents=True, exist_ok=False)
    report = {'format': 'hm-auto-v2-customer-reservation-v1', 'status': 'running',
              'private_data': 'Real customer IDs; ignored artifacts only; no test outcomes accessed.'}
    con = timer = None
    try:
        free = shutil.disk_usage(output).free
        if free < MIN_FREE_BYTES:
            raise OSError('At least10GiB output free space is required')
        spill = output/'duckdb-temp'
        spill.mkdir()
        con = duckdb.connect(str(database), read_only=True)
        timer = deadline.interrupt(con)
        con.execute('SET threads=2')
        con.execute("SET memory_limit='2GB'")
        con.execute('SET preserve_insertion_order=false')
        con.execute('SET temp_directory=?', [str(spill)])
        con.execute("SET max_temp_directory_size='8GB'")
        counts = construct_reservation(con, cached_user_paths(), old_users=OLD_USERS,
                                       new_users=NEW_USERS, deadline=deadline)
        con.execute('''COPY (SELECT customer_id,cohort_hash,reservation_rank FROM hm_auto_reserved
            ORDER BY reservation_rank) TO ? (FORMAT PARQUET,COMPRESSION ZSTD)''',
                    [str(output/'reserved-users.parquet')])
        con.execute('''COPY (SELECT customer_id FROM hm_auto_excluded ORDER BY customer_id)
            TO ? (FORMAT PARQUET,COMPRESSION ZSTD)''', [str(output/'excluded-users.parquet')])
        deadline.check()
        after = database.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Source database changed during reservation')
        if sha256_file(config, deadline) != CONFIG_SHA256:
            raise ValueError('Frozen v2 config changed during reservation')
        report.update(status='completed', config={'path': config.resolve().as_posix(), 'sha256': CONFIG_SHA256},
                      source={'path': Path(__file__).resolve().as_posix(), 'sha256': sha256_file(__file__, deadline)},
                      database={'sha256': DATABASE_SHA256, 'bytes': DATABASE_BYTES, 'opened_read_only': True},
                      cutoff=CUTOFF.isoformat(), history_days=90,
                      source_scan={'columns': ['t_dat', 'customer_id'],
                                   'interval': '[2020-05-07,2020-09-16)', 'upper_exclusive': True},
                      old_cohort_rule="sha256(customer_id + ':2026'),customer_id; first20000 per anchor",
                      reservation_rule=f"sha256(customer_id + ':{SALT}'),customer_id; first20000 after exclusions",
                      counts_history_only=counts, no_test_targets_or_features=True,
                      future_training_requirement='All v2 supervised query IDs must be disjoint from reserved IDs.',
                      resources={'threads': 2, 'duckdb_memory': '2GB', 'spill_limit': '8GB',
                                 'min_free_bytes': MIN_FREE_BYTES, 'output_free_bytes_before': free,
                                 'wall_seconds': wall_seconds, 'hard_rss_limit': False},
                      files={name: {'sha256': sha256_file(output/name, deadline), 'bytes': (output/name).stat().st_size}
                             for name in ('reserved-users.parquet', 'excluded-users.parquet')},
                      elapsed_seconds=round(time.monotonic()-started, 3))
        write_json(output/'manifest.json', report)
        return report
    except Exception as error:
        report.update(status='failed', error_type=type(error).__name__,
                      elapsed_seconds=round(time.monotonic()-started, 3))
        write_json(output/'manifest.json', report)
        raise
    finally:
        if timer is not None:
            timer.cancel()
            timer.join(timeout=1)
        if con is not None:
            con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--wall-seconds', type=float, default=1800)
    args = parser.parse_args()
    report = reserve(args.database, args.output, config=args.config, wall_seconds=args.wall_seconds)
    print(json.dumps({'status': report['status'], 'reserved_users': report['counts_history_only']['reserved_users']}))


if __name__ == '__main__':
    main()
