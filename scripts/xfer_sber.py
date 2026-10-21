"""SberMarket adapter of the agent-transfer experiment (dataset S).

Contract: docs/xfer-design.md (common) and docs/xfer-sber-design.md (this set);
the interface is fixed in the docstring of scripts/xfer_common.py. Frames use
``user_id`` and ``item_id`` (= product_id); anchors are ISO dates at midnight.

Storage (common contract 1.1): ``load`` writes the events (orders with lines, one
header per order, and their lines) to the events database and to day partitions
``{orders,lines}/d=YYYY-MM-DD/`` (paths from ``xc.events_path``); tables without
time go to the static database (``xc.static_path``). Every read of events after the load goes through
``history`` (base, candidates, Pop, labels) or ``views`` (the agent): both read only
the day partitions strictly before their cut and filter ``ts`` again.

Run as ``python -I scripts/xfer_sber.py load|collect ...``; without -I it refuses.
stdout carries one JSON line.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import weakref

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # ``python -I`` omits the script directory; the checkout goes after the stdlib.
    sys.path.append(str(ROOT))

from scripts import xfer_common as xc  # noqa: E402

DATASET = 'sber'
LOAD_FORMAT = 'xfer-sber-load-v1'
RECEIPT_FORMAT = 'xfer-sber-submission-v1'

# ---------------------------------------------------------------- time, queries, anchors (doc 1, 2)

W = 14
K = 50
N = 20_000
NEGATIVES = 20
TRAIN_ANCHORS = ('2020-06-10', '2020-06-24', '2020-07-08', '2020-07-22', '2020-08-05')
VAL_ANCHOR = '2020-08-19'
HOLDOUT_ANCHOR = '2020-09-02'
KAGGLE_ANCHOR = '2020-09-17'
PROBE_ANCHOR = VAL_ANCHOR
PROBE_USERS = 5_000
QUERY_CAP = {'train': N, 'val': N, 'holdout': 30_000, 'kaggle': None, 'probe': None}
CHUNK = xc.KAGGLE_CHUNK[DATASET]   # users per base-feature chunk (values do not depend on it)
AGENT_DAYS = 120                   # agent views: [A - 120 days, A) (coordinator decision, time rule)
POP_WINDOW_DAYS = 28               # Pop (doc 5) is fixed and does not follow base.json
REPEAT_SHARE_DAYS = 90
CODE_CUTOFF = HOLDOUT_ANCHOR       # retailer and city codes are ranked on orders before it
MEMORY = '12GB'
SPILL = '32GB'
ARMS_ALL = ['Pop', 'B', 'BA', 'BApl']

# ---------------------------------------------------------------- raw files (doc 0, 9)

ORDERS_FILE = 'kaggle_tab_1345/tab_1_orders.csv'
CATEGORIES_FILE = 'kaggle_tab_1345/tab_3_categories.csv'
CITY_FILE = 'tab_6_city.csv'
SUBMISSION_FILE = 'sample_submission.csv'
LINES_GLOB = 'sbermarket_tab_2_*/tab_2_products_*.csv'
VERIFY_FILE = 'kaggle-verify.json'
RAW_ORDERS = (('user_id', 'BIGINT'), ('order_id', 'BIGINT'), ('order_created_time', 'TIMESTAMP'),
              ('retailer', 'VARCHAR'), ('store_id', 'BIGINT'), ('platform', 'VARCHAR'))
RAW_LINES = (('user_id', 'BIGINT'), ('order_id', 'BIGINT'), ('line_item_id', 'BIGINT'), ('price', 'DOUBLE'),
             ('quantity', 'BIGINT'), ('discount', 'DOUBLE'), ('product_name', 'VARCHAR'), ('product_id', 'BIGINT'),
             ('brand_name', 'VARCHAR'), ('master_category_id', 'DOUBLE'), ('parent_category_id', 'BIGINT'))
RAW_CATEGORIES = (('id', 'BIGINT'), ('name', 'VARCHAR'), ('parent_id', 'BIGINT'))
RAW_CITY = (('store_id', 'BIGINT'), ('city_name', 'VARCHAR'))
RAW_SUBMISSION = (('Id', 'BIGINT'), ('Predicted', 'VARCHAR'))

# ---------------------------------------------------------------- event partitions and agent views (doc 6.1, 6.2)

ORDERS_SCHEMA = (('order_id', 'BIGINT'), ('user_id', 'BIGINT'), ('ts', 'TIMESTAMP'), ('retailer', 'VARCHAR'),
                 ('store_id', 'BIGINT'), ('platform', 'VARCHAR'), ('city_name', 'VARCHAR'))
LINES_SCHEMA = (('order_id', 'BIGINT'), ('user_id', 'BIGINT'), ('ts', 'TIMESTAMP'), ('product_id', 'BIGINT'),
                ('line_item_id', 'BIGINT'), ('price', 'DOUBLE'), ('quantity', 'BIGINT'), ('discount', 'DOUBLE'),
                ('brand_name', 'VARCHAR'), ('master_category_id', 'BIGINT'))
CATEGORIES_SCHEMA = (('id', 'BIGINT'), ('name', 'VARCHAR'), ('parent_id', 'BIGINT'))
VIEW_SCHEMA = {'orders': ORDERS_SCHEMA, 'lines': LINES_SCHEMA, 'categories': CATEGORIES_SCHEMA}
CATEGORIES_PARQUET = 'categories.parquet'
DAY_DIR = re.compile(r'd=([0-9]{4}-[0-9]{2}-[0-9]{2})')
LEVELS = {'pair': ['user_id', 'product_id'], 'user': ['user_id'], 'item': ['product_id']}
SOURCES = ('repeat', 'pop_retailer', 'global')

# ---------------------------------------------------------------- SQL rules (doc 6.3)

ANCHOR_SQL = "TIMESTAMP '{A}'"
PROBE_TIMEOUTS = {'pair': 40.0, 'user': 40.0, 'item': 120.0}
PROBE_BUDGET = {'pair_user_seconds': 180.0, 'item_seconds': 360.0}
MAX_ROWS = 20_000_000
# The H&M list (hm_agent_sandbox.FORBIDDEN) verbatim ...
HM_FORBIDDEN = (
    r'transactions|customers|frame|labels?|targets?|hm_\w+|_hm_\w+|'
    r'read_\w+|parquet_\w+|csv|json\w*|glob|getenv|query|query_table|duckdb_\w+|information_schema|pg_catalog|'
    r'sqlite_master|pragma\w*|current_setting|sniff_\w+|checkpoint|force_checkpoint|which_secret|'
    r'attach|detach|copy|export|import|install|load|set|reset|use|call|create|drop|insert|update|delete|alter|'
    r'random|setseed|uuid|gen_random_uuid|now|today|current_date|current_time|current_timestamp|get_current_time|'
    r'sample|tablesample')
# ... plus the raw tables and files of this set, time constructors, interval constructors other than
# INTERVAL n DAY, absolute calendar functions and wall clocks (doc 6.3). These words are matched also
# inside identifiers joined by '_' (user_profiles, product_properties).
EXTRA_FORBIDDEN = (r'tab_\w+|sample_submission|product_name|propert\w*|profiles?|bdate|gender|'
                   r'make_\w+|strptime|try_strptime|strftime|to_timestamp|to_date|epoch_\w+|'
                   r'to_(?:microseconds|milliseconds|seconds|minutes|hours|days|weeks|months|quarters|years|'
                   r'decades|centuries|millennia)|julian|yearweek|current_\w+|get_current_\w+|'
                   r'transaction_timestamp|statement_timestamp|localtimestamp|localtime')
FORBIDDEN = re.compile(r'\b(' + HM_FORBIDDEN + r')\b', re.I)
EXTRA = re.compile(r'(?<![A-Za-z0-9])(' + EXTRA_FORBIDDEN + r')(?![A-Za-z0-9])', re.I)
WORD_FORBIDDEN = r'ago'                                 # ago(INTERVAL ...): the wall clock; whole word only
WORDS = re.compile(r'\b(' + WORD_FORBIDDEN + r')\b', re.I)
RAISING = re.compile(r'\b(error|strptime|regexp_\w+)\s*\(', re.I)
BATCH = re.compile(r'\b(cand|users)\b', re.I)
STATEMENT = re.compile(r'(select|with)\b', re.I)
ANCHOR = re.compile(r"\b(?i:timestamp)\s*'\{A\}'")
DATE_LITERAL = re.compile(r"'\s*[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}")
TYPED_LITERAL = re.compile(r"\b(date|time|timestamp\w*|datetime|interval)\s*'", re.I)
INTERVAL_WORD = re.compile(r'\binterval\b', re.I)
INTERVAL_DAYS = re.compile(r'\binterval\s+[0-9]+\s+days?\b', re.I)
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
# Time rule (doc 6.3): what may surround a time value. See check_time.
TIME_NAME = re.compile(r'(?:.*_)?ts', re.I)          # ts and *_ts: the only names a time value may carry
PASS_THROUGH = {'min', 'max', 'first', 'last', 'any_value', 'arbitrary'}
ARG_BY = {'arg_max', 'arg_min', 'max_by', 'min_by', 'argmax', 'argmin'}
DIFFERENCES = {'date_diff', 'datediff', 'date_sub', 'datesub'}
DATE_PARTS = {'date_part', 'datepart', 'extract'}
# Calendar parts finer than a month: the data lie within one year, so doy, week, month and quarter would be
# absolute dates.
PERIODIC_PARTS = {'dow', 'isodow', 'dayofweek', 'weekday', 'day', 'dayofmonth', 'hour', 'hours', 'minute',
                  'minutes', 'second', 'seconds', 'millisecond', 'milliseconds', 'microsecond', 'microseconds'}
PERIODIC_FUNCTIONS = {'dayofweek', 'isodow', 'weekday', 'day', 'dayofmonth', 'hour', 'minute', 'second',
                      'millisecond', 'microsecond'}
DURATION_PARTS = {'week', 'weeks', 'day', 'days', 'hour', 'hours', 'minute', 'minutes', 'second', 'seconds',
                  'millisecond', 'milliseconds', 'microsecond', 'microseconds'}
TRUNCATE_PARTS = DURATION_PARTS
TIME_SOURCES = {'orders': {'ts'}, 'lines': {'ts'}}   # the only columns that hold time values
TIME_COMBINE = {'greatest', 'least', 'coalesce', 'ifnull'}
TRUNCATE = {'date_trunc', 'datetrunc'}
VALUE_WINDOWS = {'lag', 'lead', 'first_value', 'last_value', 'nth_value'} | PASS_THROUGH
TIMED = {'T', 'AE'}
PLAIN = {'F', 'I', 'N'}

# ---------------------------------------------------------------- prompt (common contract 3, doc 6.5)

PROMPT_CONSTANTS = dict(W=W, K=K, N=N, negatives=NEGATIVES, trees=500, depth=8, learning_rate=0.05,
                        l2_leaf_reg=10, border_count=128, timeout_pair_user=40, timeout_item=120,
                        budget_pair_user=180, budget_item=360, rounds=6, proposals=5,
                        agent_days=AGENT_DAYS)
WARNING = ('All valid columns will enter the model without selection. Superfluous and noisy columns hurt: '
           'a few strong, non-redundant signals are needed. User-level columns work only through interactions.')
NUMBER_TOKEN = re.compile(r'(?<![A-Za-z0-9_.@])\d+(?:\.\d+)?(?![A-Za-z0-9_])')


class SqlRuleError(ValueError):
    """A proposal breaks the SQL rules of this set."""


# ---------------------------------------------------------------- small helpers

def _date(value):
    """ISO date text of an anchor (a date at midnight)."""
    if isinstance(value, _dt.datetime):
        xc.require(value.time() == _dt.time(0), 'Anchors are midnights')
        value = value.date()
    if isinstance(value, _dt.date):
        return value.isoformat()
    text = str(value)
    xc.require(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', text) is not None, f'Anchor {value!r} is not YYYY-MM-DD')
    return _dt.date.fromisoformat(text).isoformat()


def _shift(anchor, days):
    return (_dt.date.fromisoformat(_date(anchor)) + _dt.timedelta(days=days)).isoformat()


def _literal(text):
    return "'" + str(text).replace("'", "''") + "'"


def _ts(anchor):
    return f"TIMESTAMP '{_date(anchor)}'"


def _columns(schema):
    return ', '.join(name for name, _ in schema)


def _csv_columns(schema):
    return '{' + ', '.join(f'{_literal(name)}: {_literal(kind)}' for name, kind in schema) + '}'


def _connect(threads, memory=MEMORY, database=':memory:', read_only=False):
    """DuckDB connection with its own spill directory, removed when the connection is collected."""
    import duckdb
    xc.require(type(threads) is int and 1 <= threads <= 12, 'threads must be 1..12')
    temp = Path(tempfile.mkdtemp(prefix='xfer-sber-'))
    con = duckdb.connect(database, read_only=read_only)
    weakref.finalize(con, shutil.rmtree, str(temp), True)
    con.execute(f'SET threads={threads}')
    con.execute('SET memory_limit=?', [memory])
    con.execute('SET temp_directory=?', [str(temp)])
    con.execute('SET max_temp_directory_size=?', [SPILL])
    con.execute('SET enable_progress_bar=false')
    con.execute('SET preserve_insertion_order=true')
    return con


def _day_files(parts, table, before):
    """Partition files of ``table`` whose day is strictly before ``before``, by day."""
    root = Path(parts)/table
    cut = _date(before)
    files, directories = [], []
    if not root.is_dir():
        return files, directories
    for day_dir in sorted(root.iterdir()):
        match = DAY_DIR.fullmatch(day_dir.name)
        if not match or not day_dir.is_dir() or match.group(1) >= cut:
            continue
        directories.append(str(day_dir.resolve())+'/')
        files.extend(str(p.resolve()) for p in sorted(day_dir.glob('*.parquet')))
    return files, directories


def _event_view(files, schema, before, since=None, shifts=None):
    """SELECT over the partition files, filtered to ``[since, before)`` (typed empty when no file).

    ``shifts``: column -> (files, column) whose minimum over the same window is subtracted from it.
    """
    if not files:
        return 'SELECT ' + ', '.join(f'CAST(NULL AS {kind}) AS {name}' for name, kind in schema) + ' WHERE false'
    listing = ', '.join(_literal(f) for f in files)
    lower = '' if since is None else f'ts >= {_ts(since)} AND '
    where = f'WHERE {lower}ts < {_ts(before)}'
    columns = []
    for name, _ in schema:
        if shifts and name in shifts:
            base_files, base_column = shifts[name]
            base = ', '.join(_literal(f) for f in base_files)
            columns.append(f'{name} - (SELECT min({base_column}) FROM read_parquet([{base}], '
                           f'hive_partitioning=false) {where}) AS {name}')
        else:
            columns.append(name)
    return f'SELECT {", ".join(columns)} FROM read_parquet([{listing}], hive_partitioning=false) {where}'


def anchors():
    """Anchors, roles and series of doc 2."""
    train = list(TRAIN_ANCHORS)
    return dict(
        W=W, N=N, K=K,
        roles=dict(train=train, val=[VAL_ANCHOR], holdout=[HOLDOUT_ANCHOR], kaggle=[KAGGLE_ANCHOR],
                   probe=[PROBE_ANCHOR]),
        series=dict(
            dev=dict(train=train, eval=VAL_ANCHOR, eval_role='val', arms=list(ARMS_ALL)),
            holdout=dict(train=train+[VAL_ANCHOR], eval=HOLDOUT_ANCHOR, eval_role='holdout', arms=list(ARMS_ALL)),
            final=dict(train=train[1:]+[VAL_ANCHOR, HOLDOUT_ANCHOR], eval=KAGGLE_ANCHOR, eval_role='kaggle',
                       arms=['B', 'BA', 'BApl'])),
        anchor_role={**{a: 'train' for a in train}, VAL_ANCHOR: 'val', HOLDOUT_ANCHOR: 'holdout',
                     KAGGLE_ANCHOR: 'kaggle'},
        queries=dict(QUERY_CAP), holdout=HOLDOUT_ANCHOR, probe=PROBE_ANCHOR, probe_users=PROBE_USERS,
        kaggle_chunk=CHUNK)


# ---------------------------------------------------------------- load

def _verify_entries(raw):
    data = json.loads((raw/VERIFY_FILE).read_text(encoding='utf-8'))
    entries = {f['name']: f for f in data.get('files', [])}
    xc.require(entries, f'{VERIFY_FILE} lists no files')
    return entries


def _header(path):
    with open(path, 'rb') as stream:
        line = stream.readline()
    return line.decode('utf-8').rstrip('\r\n')


def _read_csv(files, schema):
    listing = '[' + ', '.join(_literal(f) for f in files) + ']'
    return (f"read_csv({listing}, header=true, auto_detect=false, delim=',', quote='\"', escape='\"', "
            f"columns={_csv_columns(schema)})")


def load(raw, output, threads=4, memory='16GB'):
    """Raw CSV -> events database, event partitions, static database and load.json (doc 9).

    Every CSV is hashed and compared with kaggle-verify.json, every header with the
    expected column list; the CSVs are read with explicit types. Orders without
    lines and lines without a header are dropped; a repeated header keeps the row
    with the smallest (retailer, store_id).
    """
    started = time.monotonic()
    raw = Path(raw).resolve()
    output = Path(output).resolve()
    xc.require(output == xc.output_dir(DATASET, 'load').resolve(), 'load writes only into artifacts/xfer/sber/load')
    paths = xc.events_path(DATASET)
    db, parts = Path(paths['db']), Path(paths['parts'])
    static = xc.static_path(DATASET)

    entries = _verify_entries(raw)
    lines_files = sorted(p.relative_to(raw).as_posix() for p in raw.glob(LINES_GLOB))
    listed_lines = sorted(n for n in entries if re.fullmatch(r'sbermarket_tab_2_[^/]+/tab_2_products_[^/]+\.csv', n))
    xc.require(lines_files and lines_files == listed_lines, 'Line files on disk differ from kaggle-verify.json')
    wanted = [ORDERS_FILE, CATEGORIES_FILE, CITY_FILE, SUBMISSION_FILE, *lines_files]
    csvs = sorted(n for n in entries if n.endswith('.csv'))
    hashes = {}
    for name in csvs:
        xc.require(entries[name].get('matches', True) is True, f'{name} did not match the archive')
        digest = xc.sha256_file(raw/name)
        xc.require(digest == entries[name]['sha256'], f'SHA-256 of {name} differs from {VERIFY_FILE}')
        hashes[name] = digest
    xc.require(set(wanted) <= set(hashes), 'A loaded CSV is not listed in kaggle-verify.json')
    for name, schema in ((ORDERS_FILE, RAW_ORDERS), (CATEGORIES_FILE, RAW_CATEGORIES), (CITY_FILE, RAW_CITY),
                         (SUBMISSION_FILE, RAW_SUBMISSION), *((n, RAW_LINES) for n in lines_files)):
        header = _header(raw/name)
        xc.require(header == ','.join(c for c, _ in schema), f'Header of {name} is {header!r}')
    hashed = time.monotonic()

    output = xc.new_output(output)
    temp = output/'duckdb-temp'
    report = dict(format=LOAD_FORMAT, dataset=DATASET, status='running', raw=hashes, threads=threads, memory=memory)
    con = None
    try:
        import duckdb
        con = duckdb.connect(str(db))
        con.execute(f'SET threads={int(threads)}')
        con.execute('SET memory_limit=?', [memory])
        con.execute('SET temp_directory=?', [str(temp)])
        con.execute('SET max_temp_directory_size=?', [SPILL])
        con.execute('SET enable_progress_bar=false')
        con.execute('SET preserve_insertion_order=true')
        con.execute(f'CREATE TEMP TABLE raw_orders AS SELECT * FROM {_read_csv([raw/ORDERS_FILE], RAW_ORDERS)}')
        keep = ', '.join(c for c, _ in RAW_LINES if c != 'product_name')
        con.execute(f'CREATE TEMP TABLE raw_lines AS SELECT {keep} FROM '
                    f'{_read_csv([raw/n for n in lines_files], RAW_LINES)}')
        con.execute(f'CREATE TEMP TABLE raw_categories AS SELECT * FROM '
                    f'{_read_csv([raw/CATEGORIES_FILE], RAW_CATEGORIES)}')
        con.execute(f'CREATE TEMP TABLE raw_city AS SELECT * FROM {_read_csv([raw/CITY_FILE], RAW_CITY)}')
        con.execute(f'CREATE TEMP TABLE raw_submission AS SELECT row_number() OVER () AS position, * FROM '
                    f'{_read_csv([raw/SUBMISSION_FILE], RAW_SUBMISSION)}')
        read_done = time.monotonic()

        def one(sql, *args):
            return con.execute(sql, list(args)).fetchone()

        facts = {}
        r = one('''SELECT count(*), count(DISTINCT user_id), CAST(min(order_created_time) AS VARCHAR),
            CAST(max(order_created_time) AS VARCHAR), count(DISTINCT retailer), count(DISTINCT store_id),
            count(DISTINCT order_id), count(*) FILTER (WHERE retailer IS NULL OR store_id IS NULL OR platform IS NULL
            OR user_id IS NULL OR order_id IS NULL OR order_created_time IS NULL) FROM raw_orders''')
        facts['orders'] = dict(rows=r[0], users=r[1], first=r[2], last=r[3], retailers=r[4], stores=r[5],
                               distinct_order_id=r[6], rows_with_null=r[7])
        r = one('''SELECT count(*), sum(n), count(*) FILTER (WHERE users > 1 OR times > 1),
            count(*) FILTER (WHERE retailers > 1), count(*) FILTER (WHERE stores > 1), max(n)
            FROM (SELECT order_id, count(*) n, count(DISTINCT user_id) users, count(DISTINCT order_created_time) times,
                  count(DISTINCT retailer) retailers, count(DISTINCT store_id) stores
                  FROM raw_orders GROUP BY 1 HAVING count(*) > 1)''')
        facts['orders'].update(repeated_order_ids=r[0], repeated_rows=r[1] or 0, repeated_user_or_time_differs=r[2],
                               repeated_retailer_differs=r[3], repeated_store_differs=r[4], max_rows_per_order=r[5])
        xc.require(facts['orders']['rows_with_null'] == 0, 'orders carry NULL fields')
        xc.require(r[2] == 0, 'Repeated order headers disagree on user_id or time')
        facts['orders']['platforms'] = [x[0] for x in con.execute(
            'SELECT DISTINCT platform FROM raw_orders ORDER BY 1').fetchall()]
        r = one('''SELECT count(*), count(DISTINCT order_id), count(DISTINCT user_id), count(DISTINCT product_id),
            min(product_id), max(product_id), count(*) FILTER (WHERE product_id = 0),
            count(DISTINCT line_item_id), count(*) FILTER (WHERE master_category_id IS NULL),
            count(DISTINCT master_category_id),
            count(*) FILTER (WHERE master_category_id IS NOT NULL AND master_category_id <> trunc(master_category_id)),
            count(*) FILTER (WHERE parent_category_id IS NULL), count(DISTINCT parent_category_id),
            count(*) FILTER (WHERE brand_name IS NULL), count(DISTINCT brand_name),
            min(price), max(price), count(*) FILTER (WHERE price = 0), min(discount), max(discount),
            count(*) FILTER (WHERE discount < 0), count(*) FILTER (WHERE price + discount <= 0),
            min(quantity), max(quantity),
            count(*) FILTER (WHERE user_id IS NULL OR order_id IS NULL OR product_id IS NULL OR line_item_id IS NULL
                             OR price IS NULL OR quantity IS NULL OR discount IS NULL)
            FROM raw_lines''')
        names = ('rows', 'orders', 'users', 'products', 'product_id_min', 'product_id_max', 'product_zero_rows',
                 'distinct_line_item_id', 'category_null_rows', 'categories', 'category_not_integer_rows',
                 'parent_category_null_rows', 'parent_categories', 'brand_null_rows', 'brands', 'price_min',
                 'price_max', 'price_zero_rows', 'discount_min', 'discount_max', 'discount_negative_rows',
                 'price_plus_discount_not_positive_rows', 'quantity_min', 'quantity_max', 'rows_with_null_key')
        facts['lines'] = dict(zip(names, r))
        xc.require(facts['lines']['category_not_integer_rows'] == 0, 'master_category_id is not integer')
        xc.require(facts['lines']['rows_with_null_key'] == 0, 'lines carry NULL keys or numbers')
        xc.require(facts['lines']['distinct_line_item_id'] == facts['lines']['rows'], 'line_item_id repeats')
        facts['lines']['products_with_several_categories'] = one('''SELECT count(*) FROM (SELECT product_id
            FROM raw_lines GROUP BY 1 HAVING count(DISTINCT master_category_id) > 1)''')[0]
        xc.require(facts['lines']['products_with_several_categories'] == 0, 'A product has several categories')
        facts['lines']['repeated_order_product_pairs'] = one('''SELECT count(*) FROM (SELECT order_id, product_id
            FROM raw_lines GROUP BY 1, 2 HAVING count(*) > 1)''')[0]

        con.execute('''CREATE TEMP TABLE hdr AS SELECT order_id, user_id, order_created_time AS ts,
            retailer AS retailer_name, store_id, platform FROM (SELECT *, row_number() OVER (PARTITION BY order_id
            ORDER BY retailer, store_id, platform) AS rn FROM raw_orders) WHERE rn = 1''')
        con.execute('CREATE TEMP TABLE line_orders AS SELECT order_id, any_value(user_id) AS user_id, '
                    'count(DISTINCT user_id) AS users, count(*) AS n FROM raw_lines GROUP BY 1')
        xc.require(one('SELECT count(*) FROM line_orders WHERE users > 1')[0] == 0, 'A line order has several users')
        r = one('''SELECT count(*), sum(l.n), count(DISTINCT l.user_id) FROM line_orders l
            ANTI JOIN hdr h USING (order_id)''')
        facts['lines'].update(orders_without_header=r[0], rows_without_header=r[1] or 0,
                              users_without_header=r[2])
        r = one('''SELECT count(*), count(DISTINCT h.user_id) FROM hdr h ANTI JOIN line_orders l USING (order_id)''')
        facts['orders'].update(orders_without_lines=r[0], users_of_orders_without_lines=r[1])
        mismatch = one('SELECT count(*) FROM line_orders l JOIN hdr h USING (order_id) WHERE l.user_id <> h.user_id')[0]
        xc.require(mismatch == 0, 'A line user differs from its order header')
        con.execute('CREATE TEMP TABLE ev_orders AS SELECT h.* FROM hdr h SEMI JOIN line_orders USING (order_id)')
        r = one('SELECT count(*), CAST(min(ts) AS VARCHAR), CAST(max(ts) AS VARCHAR) FROM ev_orders')
        facts['orders'].update(orders_with_lines=r[0], with_lines_first=r[1], with_lines_last=r[2],
                               header_rows_dropped=facts['orders']['rows']-facts['orders']['distinct_order_id'])

        r = one('SELECT count(*), count(DISTINCT id) FROM raw_categories')
        facts['categories'] = dict(rows=r[0], distinct_id=r[1])
        xc.require(r[0] == r[1], 'categories.id repeats')
        facts['lines']['categories_missing'] = one('''SELECT count(DISTINCT master_category_id) FROM raw_lines
            WHERE master_category_id IS NOT NULL AND CAST(master_category_id AS BIGINT) NOT IN
            (SELECT id FROM raw_categories)''')[0]
        r = one('SELECT count(*), count(DISTINCT store_id), count(DISTINCT city_name) FROM raw_city')
        facts['city'] = dict(rows=r[0], stores=r[1], cities=r[2])
        xc.require(r[0] == r[1], 'city.store_id repeats')
        facts['orders']['stores_missing_in_city'] = one('''SELECT count(DISTINCT store_id) FROM raw_orders
            WHERE store_id NOT IN (SELECT store_id FROM raw_city)''')[0]
        r = one('''SELECT count(*), count(DISTINCT Id), min(Id), max(Id),
            count(*) FILTER (WHERE len(string_split(trim(Predicted), ' ')) <> 50) FROM raw_submission''')
        facts['submission'] = dict(rows=r[0], distinct_id=r[1], id_min=r[2], id_max=r[3], rows_not_50=r[4])
        xc.require(r[0] == r[1], 'sample_submission Id repeats')

        cutoff = _ts(CODE_CUTOFF)
        con.execute(f'''CREATE TEMP TABLE retailer_codes AS
            WITH early AS (SELECT DISTINCT retailer_name FROM ev_orders WHERE ts < {cutoff}),
                 late AS (SELECT DISTINCT retailer_name FROM ev_orders WHERE retailer_name NOT IN
                          (SELECT retailer_name FROM early)),
                 ranked AS (SELECT retailer_name, dense_rank() OVER (ORDER BY retailer_name) AS r FROM early
                            UNION ALL
                            SELECT retailer_name, (SELECT count(*) FROM early)
                                   + dense_rank() OVER (ORDER BY retailer_name) FROM late)
            SELECT 'r' || lpad(CAST(r AS VARCHAR), 2, '0') AS code, retailer_name AS retailer, r AS rank
            FROM ranked ORDER BY r''')
        con.execute(f'''CREATE TEMP TABLE city_codes AS
            WITH named AS (SELECT o.ts, c.city_name FROM ev_orders o JOIN raw_city c USING (store_id)),
                 early AS (SELECT DISTINCT city_name FROM named WHERE ts < {cutoff}),
                 late AS (SELECT DISTINCT city_name FROM named WHERE city_name NOT IN (SELECT city_name FROM early)),
                 ranked AS (SELECT city_name, dense_rank() OVER (ORDER BY city_name) AS r FROM early
                            UNION ALL
                            SELECT city_name, (SELECT count(*) FROM early)
                                   + dense_rank() OVER (ORDER BY city_name) FROM late)
            SELECT 'c' || lpad(CAST(r AS VARCHAR), 3, '0') AS code, city_name, r AS rank FROM ranked ORDER BY r''')
        r = one('SELECT max(rank), count(*) FROM retailer_codes')
        xc.require(r[0] is None or r[0] <= 99, 'More than 99 retailers: two-digit codes do not fit')
        facts['codes'] = dict(retailers=r[1], early_retailers=one(f'''SELECT count(DISTINCT retailer_name)
            FROM ev_orders WHERE ts < {cutoff}''')[0])
        r = one('SELECT max(rank), count(*) FROM city_codes')
        xc.require(r[0] is None or r[0] <= 999, 'More than 999 cities: three-digit codes do not fit')
        facts['codes']['cities'] = r[1]

        con.execute('''CREATE TABLE orders AS SELECT o.order_id, o.user_id, o.ts, rc.code AS retailer, o.store_id,
            o.platform, cc.code AS city_name FROM ev_orders o JOIN retailer_codes rc ON rc.retailer = o.retailer_name
            LEFT JOIN raw_city c USING (store_id) LEFT JOIN city_codes cc ON cc.city_name = c.city_name
            ORDER BY o.ts, o.order_id''')
        con.execute('''CREATE TABLE lines AS SELECT l.order_id, l.user_id, o.ts, l.product_id, l.line_item_id, l.price,
            l.quantity, l.discount, l.brand_name, CAST(l.master_category_id AS BIGINT) AS master_category_id
            FROM raw_lines l JOIN ev_orders o USING (order_id) ORDER BY o.ts, l.order_id, l.line_item_id''')
        r = one('SELECT count(*), count(DISTINCT user_id), count(DISTINCT product_id) FROM lines')
        facts['events'] = dict(orders=one('SELECT count(*) FROM orders')[0], lines=r[0], line_users=r[1],
                               products=r[2], orders_without_retailer_code=one(
                                   'SELECT count(*) FROM orders WHERE retailer IS NULL')[0],
                               orders_without_city=one('SELECT count(*) FROM orders WHERE city_name IS NULL')[0])
        xc.require(facts['events']['orders'] == facts['orders']['orders_with_lines'], 'Event orders lost a row')

        con.execute(f'ATTACH {_literal(static)} AS st')
        con.execute('CREATE TABLE st.retailer_codes AS SELECT code, retailer FROM retailer_codes ORDER BY code')
        con.execute('CREATE TABLE st.city_codes AS SELECT code, city_name FROM city_codes ORDER BY code')
        con.execute('CREATE TABLE st.categories AS SELECT id, name, parent_id FROM raw_categories ORDER BY id')
        con.execute('CREATE TABLE st.city AS SELECT store_id, city_name FROM raw_city ORDER BY store_id')
        con.execute('CREATE TABLE st.submission AS SELECT position, Id AS user_id FROM raw_submission ORDER BY position')
        built = time.monotonic()

        parts.mkdir()
        con.execute('SET threads=1')  # one writer keeps one file per day in insertion order
        for table, schema in (('orders', ORDERS_SCHEMA), ('lines', LINES_SCHEMA)):
            con.execute(f'''COPY (SELECT {_columns(schema)}, strftime(ts, '%Y-%m-%d') AS d FROM {table})
                TO {_literal(parts/table)} (FORMAT PARQUET, PARTITION_BY (d))''')
        (parts/'categories').mkdir()
        con.execute(f'''COPY (SELECT {_columns(CATEGORIES_SCHEMA)} FROM st.categories ORDER BY id)
            TO {_literal(parts/'categories'/CATEGORIES_PARQUET)} (FORMAT PARQUET)''')
        con.execute(f'SET threads={int(threads)}')
        con.execute('DETACH st')
        files = {}
        for path in sorted(parts.rglob('*.parquet')):
            rows = one('SELECT count(*) FROM read_parquet(?)', str(path))[0]
            files[path.relative_to(parts).as_posix()] = dict(rows=rows, sha256=xc.sha256_file(path))
        for table in ('orders', 'lines'):
            written = sum(e['rows'] for rel, e in files.items() if rel.startswith(table+'/'))
            xc.require(written == facts['events'][table], f'Partitions of {table} lost rows')
        facts['events']['days'] = len({rel.split('/')[1] for rel in files if rel.startswith('lines/')})
        con.close()
        con = None
        report.update(status='completed', facts=facts, partitions=files,
                      files={p.name: xc.sha256_file(p) for p in (db, static)},
                      module=dict(xfer_sber=xc.sha256_file(Path(__file__)),
                                  xfer_common=xc.sha256_file(Path(xc.__file__))),
                      seconds=dict(hash=round(hashed-started, 1), read=round(read_done-hashed, 1),
                                   build=round(built-read_done, 1), partitions=round(time.monotonic()-built, 1),
                                   total=round(time.monotonic()-started, 1)))
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}'[:2000])
        raise
    finally:
        if con is not None:
            con.close()
        shutil.rmtree(temp, ignore_errors=True)
        xc.atomic_json(output/'load.json', report)
    for path in output.rglob('*'):
        if path.is_file():
            path.chmod(0o444)  # events and static are read by everything else; nothing rewrites them
    return report


# ---------------------------------------------------------------- history and views (common 1.1, doc 1, 6.2)

def history(before, purpose, threads=4):
    """In-memory connection with ``orders`` and ``lines`` strictly before ``before``.

    Also ``retailer_names(retailer, retailer_name)`` and static tables under ``st``.
    For ``before`` after A_holdout the holdout window must be open for ``purpose``.
    """
    before = _date(before)
    if purpose == 'collect-holdout':
        xc.require(before <= _shift(HOLDOUT_ANCHOR, W), 'collect-holdout reads no further than A_holdout + W')
    if before > HOLDOUT_ANCHOR:
        xc.require_window(DATASET, purpose)
    parts = xc.events_path(DATASET)['parts']
    con = _connect(threads)
    try:
        for table, schema in (('orders', ORDERS_SCHEMA), ('lines', LINES_SCHEMA)):
            files, _ = _day_files(parts, table, before)
            con.execute(f'CREATE VIEW {table} AS {_event_view(files, schema, before)}')
        con.execute(f'ATTACH {_literal(xc.static_path(DATASET))} AS st (READ_ONLY)')
        con.execute('CREATE VIEW retailer_names AS SELECT code AS retailer, retailer AS retailer_name '
                    'FROM st.retailer_codes')
    except BaseException:
        con.close()
        raise
    return con


def views(A, purpose):
    """Agent views at anchor A (doc 6.2): days and ts in [A - AGENT_DAYS days, A), for every purpose.

    The lower cut makes every point of the agent's data anchor-relative: the global min(ts) or the ts of a
    fixed order is about A - AGENT_DAYS days, not a calendar date (the data start long before any anchor).
    order_id and line_item_id grow with time (absolute clocks), so they are shifted by their minimum over
    the whole window: order_id by that of orders in both tables (the join is kept), line_item_id by that
    of lines. The window, not a batch of users, fixes the shift.
    """
    A = _date(A)
    if A > HOLDOUT_ANCHOR:
        xc.require_window(DATASET, purpose)
    since = _shift(A, -AGENT_DAYS)
    parts = Path(xc.events_path(DATASET)['parts'])
    files, directories, selects, window = [], [], {}, {}
    for table in ('orders', 'lines'):
        table_files, table_dirs = _day_files(parts, table, A)
        keep = [i for i, d in enumerate(table_dirs) if DAY_DIR.search(d).group(1) >= since]
        table_dirs = [table_dirs[i] for i in keep]
        window[table] = [f for f in table_files if any(f.startswith(d) for d in table_dirs)]
        files.extend(window[table])
        directories.extend(table_dirs)
    shifts = dict(orders={'order_id': (window['orders'], 'order_id')},
                  lines={'order_id': (window['orders'], 'order_id'),
                         'line_item_id': (window['lines'], 'line_item_id')})
    for table in ('orders', 'lines'):
        selects[table] = _event_view(window[table], VIEW_SCHEMA[table], A, since, shifts[table])
    categories = (parts/'categories'/CATEGORIES_PARQUET).resolve()
    files.append(str(categories))
    directories.append(str(categories.parent)+'/')
    selects['categories'] = f'SELECT {_columns(CATEGORIES_SCHEMA)} FROM read_parquet({_literal(categories)})'
    return dict(anchor=A, files=files, directories=directories, views=selects,
                schema={name: [list(c) for c in schema] for name, schema in VIEW_SCHEMA.items()},
                levels={k: list(v) for k, v in LEVELS.items()}, items='SELECT DISTINCT product_id FROM lines',
                keys=dict(user_id='user_id', item_id='product_id'), anchor_sql=ANCHOR_SQL)


# ---------------------------------------------------------------- SQL rules (doc 6.3)

def _is_anchor(node):
    child = node.get('child') if node.get('class') == 'CAST' else None
    return (isinstance(child, dict) and child.get('class') == 'CONSTANT' and
            (child.get('value') or {}).get('value') == '{A}' and
            (node.get('cast_type') or {}).get('id') == 'TIMESTAMP' and not node.get('try_cast'))


def _constant_only(node):
    """No column, subquery, star or parameter anywhere below (a literal expression)."""
    if isinstance(node, list):
        return all(_constant_only(n) for n in node)
    if not isinstance(node, dict):
        return True
    if node.get('class') in ('COLUMN_REF', 'SUBQUERY', 'STAR', 'PARAMETER', 'POSITIONAL_REFERENCE', 'WINDOW'):
        return False
    return all(_constant_only(v) for v in node.values())


def _constant_text(node):
    if node.get('class') == 'CONSTANT' and not (node.get('value') or {}).get('is_null'):
        return str((node.get('value') or {}).get('value')).lower()
    return None


class _Source:
    """A FROM item seen by column references: its alias and output columns (name -> kind).

    ``opaque``: its column names are not all known, but none of them is a time value (unknown tables,
    table functions, VALUES, unnamed output columns).
    """

    def __init__(self, alias, columns, opaque=False):
        self.alias = (alias or '').lower() or None
        self.columns = {}
        for name, kind in columns:
            if name:
                key = str(name).lower()
                self.columns[key] = _join_kind(self.columns.get(key), kind)
        self.opaque = opaque


def _join_kind(old, new):
    """The kind of a name with several possible bindings: a time value if any binding is one."""
    if old is None:
        return new
    for kind in ('T', 'AE'):
        if kind in (old, new):
            return kind
    return old if old == new else 'F'


def _join_all(kinds):
    kind = None
    for k in kinds:
        kind = _join_kind(kind, k)
    return kind


def _type_keys(cast_type):
    """Every STRUCT/UNION field name in a cast type tree."""
    if isinstance(cast_type, list):
        return [k for item in cast_type for k in _type_keys(item)]
    if not isinstance(cast_type, dict):
        return []
    keys = [str(cast_type['first']).lower()] if isinstance(cast_type.get('first'), str) else []
    return keys + [k for value in cast_type.values() for k in _type_keys(value)]


def _type_ids(cast_type):
    """Every type id in a cast type tree (STRUCT, MAP, LIST, ARRAY and UNION children included)."""
    if isinstance(cast_type, list):
        return [i for item in cast_type for i in _type_ids(item)]
    if not isinstance(cast_type, dict):
        return []
    ids = [str(cast_type['id']).upper()] if isinstance(cast_type.get('id'), str) else []
    return ids + [i for key, value in cast_type.items() if key != 'id' for i in _type_ids(value)]


def _is_time_type(type_id):
    return 'TIME' in type_id or 'DATE' in type_id or 'INTERVAL' in type_id


class _TimeRule:
    """Kinds of expressions under the time rule of doc 6.3.

    T: a time value. Its only sources are the column ts of the views orders and lines; it stays a time
    value through a column of a WITH query or subquery that selects it (named ts or *_ts), through min, max,
    first, last, any_value, arg_max/arg_min by it, lag/lead/first_value/last_value, CAST to DATE or
    TIMESTAMP, date_trunc to day/hour/minute/second/week, greatest/least/coalesce/CASE of time values and
    +/- INTERVAL n DAY. AE: the anchor TIMESTAMP '{A}' +/- INTERVAL n DAY. I: INTERVAL n DAY. N: NULL.
    F: everything else, including fields of structs and every value of an unknown source.

    T and AE may only be compared with T or AE, subtracted from T or AE, passed to date_diff/date_sub with
    T or AE and a part of at most a week, or reduced to a periodic part (dow, day of month, hour, minute,
    second). No cast may produce a time type anywhere in its type (no STRUCT(x TIMESTAMP) either). A time
    value may carry only the name ts or *_ts, and those names only time values. Everything else is refused.
    """

    def __init__(self):
        self.scopes = []      # innermost last: dict(sources=[_Source], aliases={name: kind}, params=set())
        self.ctes = []        # innermost last: {name: (columns, opaque)}

    def fail(self, message):
        raise SqlRuleError(message + "; times are used only as ts compared with TIMESTAMP '{A}' +/- INTERVAL n "
                           "DAY, differences and date_diff between ts and the anchor, or periodic parts")

    def plain(self, kind, what):
        if kind in TIMED:
            self.fail(f'a time value is not allowed in {what}')
        return kind

    # -------- statements and query nodes; a node gives (columns [(name or None, kind)], opaque)

    def statement(self, tree):
        statements = tree.get('statements') or []
        if len(statements) != 1:
            raise SqlRuleError('exactly one statement is allowed')
        self.node(statements[0].get('node') or {})

    def node(self, node):
        kind = node.get('type')
        ctes = {}
        self.ctes.append(ctes)
        try:
            for entry in (node.get('cte_map') or {}).get('map') or []:
                value = entry.get('value') or {}
                if value.get('aliases'):
                    self.fail('column aliases of a WITH query are not allowed')
                query = (value.get('query') or {}).get('node') or {}
                if query.get('type') == 'RECURSIVE_CTE_NODE':
                    self.fail('WITH RECURSIVE is not allowed')
                ctes[str(entry.get('key', '')).lower()] = self.node(query)
            if kind == 'SELECT_NODE':
                return self.select(node)
            if kind == 'SET_OPERATION_NODE':
                return self.set_operation(node)
            self.fail(f'query node {kind} is not allowed')
        finally:
            self.ctes.pop()

    def set_operation(self, node):
        (left, left_opaque), (right, right_opaque) = (self.node(node.get('left') or {}),
                                                      self.node(node.get('right') or {}))
        timed = any(k in TIMED for _, k in left + right)
        if timed:
            if 'BY_NAME' in str(node.get('setop_type', '')).upper() or left_opaque or right_opaque or \
                    len(left) != len(right):
                self.fail('a set operation with time values needs the same explicit columns on both sides')
            for (_, a), (_, b) in zip(left, right):
                if (a in TIMED and b not in TIMED | {'N'}) or (b in TIMED and a not in TIMED | {'N'}):
                    self.fail('a set operation may not mix time and non-time values in one column')
            columns = [(name, a if a != 'N' else b) for (name, a), (_, b) in zip(left, right)]
        else:
            columns = left
        output = (columns, left_opaque or right_opaque)
        self.scopes.append(dict(sources=[_Source(None, columns, output[1])], aliases={}, params=set()))
        try:
            self.modifiers(node)
        finally:
            self.scopes.pop()
        return output

    def modifiers(self, node):
        for modifier in node.get('modifiers') or []:
            for order in modifier.get('orders') or []:
                self.expr(order.get('expression'))
            for key in ('limit', 'offset'):
                if modifier.get(key):
                    self.plain(self.expr(modifier[key]), 'LIMIT or OFFSET')
            for target in modifier.get('distinct_on_targets') or []:
                self.expr(target)

    def select(self, node):
        scope = dict(sources=[], aliases={}, params=set())
        self.scopes.append(scope)
        try:
            self.table(node.get('from_table') or {'type': 'EMPTY'}, scope)
            columns, opaque = [], False
            for item in node.get('select_list') or []:
                if item.get('class') == 'STAR':
                    star, star_opaque = self.star(item, scope)
                    columns.extend(star)
                    opaque = opaque or star_opaque
                    continue
                kind = self.expr(item)
                name = item.get('alias') or ((item.get('column_names') or [None])[-1]
                                             if item.get('class') == 'COLUMN_REF' else None)
                self.named(name, kind)
                columns.append((name, kind))
                opaque = opaque or not name
                if item.get('alias'):
                    key = item['alias'].lower()
                    scope['aliases'][key] = _join_kind(scope['aliases'].get(key), kind)
            for key in ('where_clause', 'having', 'qualify'):
                if node.get(key):
                    self.plain(self.expr(node[key]), key.split('_')[0].upper())
            for expression in node.get('group_expressions') or []:
                self.expr(expression)
            self.modifiers(node)
            return columns, opaque
        finally:
            self.scopes.pop()

    def named(self, name, kind):
        timed_name = bool(name) and TIME_NAME.fullmatch(str(name)) is not None
        if kind in TIMED and not timed_name:
            self.fail('a selected time value must be named ts or *_ts')
        if timed_name and kind not in TIMED | {'N'}:
            self.fail(f'the name {name} is reserved for time values')

    def star(self, item, scope):
        if item.get('columns') or item.get('expr') is not None or item.get('rename_list'):
            self.fail('COLUMNS(...) and * RENAME are not allowed')
        relation = str(item.get('relation_name') or '').lower()
        sources = [s for s in scope['sources'] if not relation or s.alias == relation]
        if relation and not sources:
            self.fail(f'unknown relation {relation} in {relation}.*')
        # EXCLUDE is ignored: listing an excluded column only makes later references stricter.
        columns = [(name, kind) for s in sources for name, kind in s.columns.items()]
        for entry in item.get('replace_list') or []:
            key = str(entry.get('key', '')).lower()
            kind = self.expr(entry.get('value'))
            self.named(key, kind)
            columns = [(name, kind if name == key else k) for name, k in columns]
        return columns, any(s.opaque for s in sources)

    # -------- FROM

    def table(self, ref, scope):
        kind = ref.get('type')
        alias = ref.get('alias') or None
        if ref.get('column_name_alias'):
            self.fail('column aliases of a table are not allowed')
        if ref.get('at_clause'):
            self.fail('AT (...) is not allowed')
        if kind == 'BASE_TABLE':
            name = str(ref.get('table_name', ''))
            if ref.get('schema_name') or ref.get('catalog_name') or not IDENTIFIER.fullmatch(name):
                self.fail('tables are named by plain identifiers only')
            key = name.lower()
            cte = next((level[key] for level in reversed(self.ctes) if key in level), None)
            if cte is not None:
                source = _Source(alias or key, *cte)
            elif key in TIME_SOURCES:
                source = _Source(alias or key, [(c, 'T' if c in TIME_SOURCES[key] else 'F')
                                                for c, _ in VIEW_SCHEMA[key]])
            else:
                source = _Source(alias or key, [], opaque=True)    # categories, cand, users: no times
            scope['sources'].append(source)
        elif kind == 'JOIN':
            self.table(ref.get('left') or {}, scope)
            self.table(ref.get('right') or {}, scope)
            if ref.get('condition'):
                self.plain(self.expr(ref['condition']), 'a join condition')
        elif kind == 'SUBQUERY':
            columns, opaque = self.node((ref.get('subquery') or {}).get('node') or {})
            scope['sources'].append(_Source(alias, columns, opaque))
        elif kind == 'TABLE_FUNCTION':
            name = (ref.get('function') or {}).get('function_name')
            self.fail(f'table functions in FROM ({name}(...)) are not allowed; read orders, lines, categories, '
                      'cand and users')
        elif kind == 'EXPRESSION_LIST':
            for row in ref.get('values') or []:
                for value in row:
                    self.plain(self.expr(value), 'VALUES')
            scope['sources'].append(_Source(alias, [], opaque=True))
        elif kind != 'EMPTY':
            self.fail(f'table reference {kind} is not allowed')

    # -------- expressions

    def expr(self, node):
        if node is None:
            return 'N'
        kind = node.get('class')
        handler = getattr(self, 'x_' + str(kind).lower(), None)
        if handler is None:
            if kind in ('PARAMETER', 'POSITIONAL_REFERENCE', 'STAR'):
                self.fail(f'{kind.lower()} is not allowed here')
            for value in node.values():
                for child in (value if isinstance(value, list) else [value]):
                    if isinstance(child, dict) and 'class' in child:
                        self.plain(self.expr(child), f'{kind}')
            return 'F'
        return handler(node)

    def x_column_ref(self, node):
        names = [str(n).lower() for n in node.get('column_names') or []]
        if not names:
            self.fail('an empty column reference')
        if len(names) >= 3:
            self.fail(f'{".".join(names)}: names of three or more parts are not allowed; write alias.column')
        if len(names) == 2:
            return self.qualified(*names)
        name, maybe = names[0], False
        for scope in reversed(self.scopes):
            kinds = [s.columns[name] for s in scope['sources'] if name in s.columns]
            if name in scope['aliases']:
                kinds.append(scope['aliases'][name])
            if name in scope['params']:
                kinds.append('F')
            if kinds:
                if maybe and TIME_NAME.fullmatch(name):
                    self.fail(f'{name} is ambiguous here: a closer FROM item may have a column {name}; '
                              'write alias.' + name)
                return _join_all(kinds)
            if any(s.alias == name for s in scope['sources']):
                self.fail(f'the table {name} may not be used as a value')
            maybe = maybe or any(s.opaque for s in scope['sources'])   # it may bind there (never to a time)
        if maybe:
            return 'F'
        self.fail(f'unknown column {name}')

    def qualified(self, first, column):
        """alias.column, or struct.field. A matching alias without the column falls through to the outer
        scopes as in DuckDB; every possible binding counts."""
        maybe = False
        for scope in reversed(self.scopes):
            sources = [s for s in scope['sources'] if s.alias == first]
            bound = [s.columns[column] for s in sources if column in s.columns]
            if bound:
                if maybe and TIME_NAME.fullmatch(column):
                    self.fail(f'{first}.{column} is ambiguous here: a closer FROM item {first} may have a column '
                              f'{column}; rename the alias')
                return _join_all(bound)
            if sources:
                maybe = maybe or any(s.opaque for s in sources)
                continue
            kinds = [s.columns[first] for s in scope['sources'] if first in s.columns]
            if first in scope['aliases']:
                kinds.append(scope['aliases'][first])
            if first in scope['params']:
                kinds.append('F')
            if kinds:
                return self.field(_join_all(kinds), [column])
        if maybe:
            return 'F'
        self.fail(f'unknown column {first}.{column}')

    def field(self, kind, rest):
        if rest and kind in TIMED:
            self.fail('a time value has no fields')
        return 'F' if rest else kind

    def x_lambda_ref(self, node):
        self.fail('lambda functions (x -> ..., lambda x: ...) are not allowed')

    def x_constant(self, node):
        value = node.get('value') or {}
        if value.get('is_null'):
            return 'N'
        if value.get('value') == '{A}':
            self.fail("the anchor is written only as TIMESTAMP '{A}'")
        return 'F'

    def x_cast(self, node):
        if _is_anchor(node):
            return 'AE'
        for key in _type_keys(node.get('cast_type') or {}):
            if TIME_NAME.fullmatch(key):
                self.fail(f'a struct field may not be named {key}; ts and *_ts name only time values')
        ids = _type_ids(node.get('cast_type') or {})
        target = ids[0] if ids else ''
        if any(i == 'UNBOUND' for i in ids):
            self.fail('casts are only to built-in types')
        if any(_is_time_type(i) for i in ids[1:]):
            self.fail(f'a cast to {target} with a time type inside is not allowed')
        child = self.expr(node.get('child'))
        if child == 'N':
            return 'N'
        if child == 'T' and (target == 'DATE' or target.startswith('TIMESTAMP')):
            return 'T'
        if child in TIMED:
            self.fail(f'a time value may not be cast to {target}')
        if _is_time_type(target):
            self.fail(f'a value may not be cast to {target}')
        return 'F'

    def x_comparison(self, node):
        return self.compare([self.expr(node.get('left')), self.expr(node.get('right'))])

    def x_between(self, node):
        return self.compare([self.expr(node.get(k)) for k in ('input', 'lower', 'upper')])

    def compare(self, kinds):
        if any(k in TIMED for k in kinds) and not all(k in TIMED | {'N'} for k in kinds):
            self.fail('a time value may only be compared with ts or the anchor')
        return 'F'

    def x_conjunction(self, node):
        for child in node.get('children') or []:
            self.plain(self.expr(child), 'AND/OR')
        return 'F'

    def x_operator(self, node):
        kind = node.get('type')
        kinds = [self.expr(c) for c in node.get('children') or []]
        if kind in ('COMPARE_IN', 'COMPARE_NOT_IN'):
            return self.compare(kinds)
        if kind in ('OPERATOR_IS_NULL', 'OPERATOR_IS_NOT_NULL'):
            return 'F'
        if kind == 'OPERATOR_COALESCE':
            return self.combine(kinds)
        for k in kinds:
            self.plain(k, kind.lower())
        return 'F'

    def combine(self, kinds):
        if any(k in TIMED for k in kinds):
            if not all(k in TIMED | {'N'} for k in kinds):
                self.fail('greatest, least and coalesce may not mix times with other values')
            return 'T' if 'T' in kinds else 'AE'
        return 'N' if kinds and all(k == 'N' for k in kinds) else 'F'

    def x_case(self, node):
        results = []
        for check in node.get('case_checks') or []:
            self.plain(self.expr(check.get('when_expr')), 'a CASE condition')
            results.append(self.expr(check.get('then_expr')))
        results.append(self.expr(node.get('else_expr')))
        return self.combine(results)

    def x_subquery(self, node):
        columns, _ = self.node((node.get('subquery') or {}).get('node') or {})
        kind = node.get('subquery_type')
        if kind in ('EXISTS', 'NOT_EXISTS'):
            return 'F'
        first = columns[0][1] if columns else 'F'
        if node.get('child') is not None:
            return self.compare([self.expr(node['child']), first])
        return first

    def x_lambda(self, node):
        self.fail('lambda functions (x -> ..., lambda x: ...) are not allowed')

    def x_window(self, node):
        name = str(node.get('function_name', '')).lower()
        kinds = [self.expr(c) for c in node.get('children') or []]
        for expression in node.get('partitions') or []:
            self.expr(expression)
        for order in (node.get('orders') or []) + (node.get('arg_orders') or []):
            self.expr(order.get('expression'))
        for key in ('filter_expr', 'start_expr', 'end_expr', 'offset_expr'):
            if node.get(key):
                self.plain(self.expr(node[key]), 'a window frame or filter')
        default = self.expr(node.get('default_expr')) if node.get('default_expr') else 'N'
        if kinds and kinds[0] == 'T' and name in VALUE_WINDOWS and default in TIMED | {'N'} and \
                all(k in PLAIN for k in kinds[1:]):
            return 'T'
        if name == 'count':
            return 'F'
        for k in kinds + [default]:
            self.plain(k, f'window function {name}')
        return 'F'

    def x_function(self, node):
        name = str(node.get('function_name', '')).lower()
        children = node.get('children') or []
        for child in children:
            key = str(child.get('alias') or '')
            if key and TIME_NAME.fullmatch(key):
                self.fail(f'a struct key or named argument may not be {key}; ts and *_ts name only time values')
        if node.get('filter'):
            self.plain(self.expr(node['filter']), 'FILTER')
        for order in (node.get('order_bys') or {}).get('orders') or []:
            self.expr(order.get('expression'))
        if name == 'to_days' and _constant_only(children):
            return 'I'                            # INTERVAL n DAY (other forms are refused as text)
        kinds = [self.expr(c) for c in children]
        if not any(k in TIMED for k in kinds):
            if name.startswith('to_') and name != 'to_days':
                self.fail(f'{name} is not allowed')
            return 'F'
        if name in PASS_THROUGH and len(kinds) == 1:
            return kinds[0]
        if name in ARG_BY and len(kinds) == 2 and kinds[0] in {'T'} | PLAIN and kinds[1] in {'T'} | PLAIN:
            return 'T' if kinds[0] == 'T' else 'F'
        if name == 'count':
            return 'F'
        if name == '-' and len(kinds) == 2:
            if kinds[0] in TIMED and kinds[1] in TIMED:
                return 'F'                        # a duration between two times
            if kinds[0] in TIMED and kinds[1] == 'I':
                return kinds[0]
        if name == '+' and len(kinds) == 2:
            pair = sorted(kinds)
            if pair in (['I', 'T'], ['AE', 'I']):
                return 'T' if 'T' in pair else 'AE'
        if name in DIFFERENCES and len(kinds) == 3 and _constant_text(children[0]) in DURATION_PARTS and \
                kinds[1] in TIMED and kinds[2] in TIMED:
            return 'F'
        if name in DATE_PARTS and len(kinds) == 2 and kinds[1] == 'T' and \
                _constant_text(children[0]) in PERIODIC_PARTS:
            return 'F'
        if name in PERIODIC_FUNCTIONS and kinds == ['T']:
            return 'F'
        if name in TRUNCATE and len(kinds) == 2 and kinds[1] == 'T' and \
                _constant_text(children[0]) in TRUNCATE_PARTS:
            return 'T'
        if name in TIME_COMBINE:
            return self.combine(kinds)
        self.fail(f'{name}() of a time value is not allowed')


def check_time(sql):
    """The time rule of doc 6.3 on the DuckDB parse tree (see _TimeRule)."""
    import duckdb
    con = duckdb.connect()
    try:
        text = con.execute('SELECT json_serialize_sql(?)', [sql]).fetchone()[0]
    finally:
        con.close()
    tree = json.loads(text)
    if tree.get('error'):
        raise SqlRuleError(f"the statement does not parse: {tree.get('error_message', '')}"[:300])
    _TimeRule().statement(tree)


def check_sql(sql, level):
    """All SQL rules of this set (doc 6.3): H&M 1.3 with TIMESTAMP '{A}', extra words, the time rule."""
    if level not in LEVELS:
        raise SqlRuleError('level must be pair, user or item')
    if not isinstance(sql, str) or not sql.strip():
        raise SqlRuleError('sql must be a non-empty string')
    body = sql.strip()
    if body.endswith(';'):
        body = body[:-1].rstrip()
    if ';' in body:
        raise SqlRuleError('exactly one statement is allowed; ";" may only end it')
    if '--' in body or '/*' in body:
        raise SqlRuleError('comments are not allowed')
    if '$' in body:
        raise SqlRuleError('$ (dollar quoting, parameters) is not allowed')
    if not STATEMENT.match(body):
        raise SqlRuleError('the statement must start with SELECT or WITH')
    rest = ANCHOR.sub(' ', body)
    if '{' in rest or '}' in rest:
        raise SqlRuleError("the anchor is written only as TIMESTAMP '{A}'; no other {...} is allowed")
    if DATE_LITERAL.search(rest) or TYPED_LITERAL.search(rest):
        raise SqlRuleError("date and time literals are not allowed; write times relative to TIMESTAMP '{A}'")
    if len(INTERVAL_WORD.findall(rest)) != len(INTERVAL_DAYS.findall(rest)):
        raise SqlRuleError('intervals are written only as INTERVAL n DAY, without quotes')
    hit = FORBIDDEN.search(rest) or EXTRA.search(rest) or WORDS.search(rest) or RAISING.search(rest)
    if hit:
        raise SqlRuleError(f'forbidden table, function or command: {hit.group(0)}')
    if level == 'item':
        hit = BATCH.search(rest)
        if hit:
            raise SqlRuleError(f'an item query must not use {hit.group(0)}: its values are cached per process')
    check_time(body)


def sql_rules():
    return dict(forbidden=EXTRA_FORBIDDEN + '|' + WORD_FORBIDDEN, hm_forbidden=HM_FORBIDDEN, check=check_sql, anchor=ANCHOR_SQL,
                anchor_pattern=ANCHOR.pattern, levels={k: list(v) for k, v in LEVELS.items()},
                timeouts=dict(PROBE_TIMEOUTS), budget=dict(PROBE_BUDGET), max_rows=MAX_ROWS)


# ---------------------------------------------------------------- base (doc 3, 4)

FEATURES = (
    ('up_orders', 'number of distinct orders of the user before A that contain the product (repeated lines of an '
                  'order count once)', '0 when none'),
    ('up_share', 'up_orders / u_orders', '0 when none'),
    ('up_days_since_last', 'days from the latest order of the user with the product to A (fractional, from seconds)',
     'NULL when the user never bought the product'),
    ('up_mean_interval', '(time of the latest minus time of the earliest order of the user with the product) / '
                         '(up_orders - 1), in days', 'NULL when up_orders < 2'),
    ('up_due', 'up_days_since_last / up_mean_interval',
     'NULL when either is NULL or up_mean_interval = 0'),
    ('up_qty_total', 'sum of quantity over all lines of the product of the user before A, repeated lines included',
     '0 when none'),
    ('up_last_price', 'price of the product line in the latest order of the user with the product (latest ts, then '
                      'largest order_id; with several lines, the largest line_item_id)', 'NULL when none'),
    ('up_discount_share', 'mean of discount / (price + discount) over the lines of the product of the user with '
                          'price + discount > 0 (negative discounts kept)', 'NULL when there are no such lines'),
    ('repeat_rank', 'position of the product in the full repeat order of the user (source a, without its depth cut)',
     'NULL when the user never bought the product'),
    ('popr_rank', 'position of the product in the full pop-retailer order of the main retailer of the user (source '
                  'b, without its depth cut)', 'NULL when nobody bought the product at that retailer in the window'),
    ('glob_rank', 'position of the product in the full global order (source c)',
     'NULL when nobody bought the product in the window'),
    ('u_orders', 'number of distinct orders of the user before A', 'never missing'),
    ('u_orders_28', 'orders of the user in [A - 28 days, A)', '0 when none'),
    ('u_days_since_last', 'days from the latest order of the user to A', 'never missing'),
    ('u_mean_basket', 'mean over the orders of the user of the number of distinct products in the order',
     'never missing'),
    ('u_mean_gap', '(time of the latest minus time of the earliest order of the user) / (u_orders - 1), in days',
     'NULL when u_orders < 2'),
    ('u_main_share', 'orders of the user at the main retailer / u_orders', 'never missing'),
    ('p_buyers_28', 'distinct users who bought the product in the global window of source c', '0 when none'),
    ('p_buyers_28_main', 'distinct users who bought the product at the main retailer of the user in the window of '
                         'source b', '0 when none'),
    ('p_repeat_share', 'among users who bought the product in [A - 90 days, A), the share with at least 2 distinct '
                       'orders containing it in that interval', 'NULL when nobody bought it in the interval'),
    ('uc_share', 'orders of the user that contain a product of the same category as the product / u_orders; the '
                 'category of a product is its non-NULL master_category_id in the history before A',
     'NULL when the product has no category; 0 when no such order'),
    ('main_retailer', 'code of the main retailer of the user (categorical)', 'never missing'),
)
# Optional base-dev features: not in initial_base(); a base lists the ones it uses (initial_base(extra=...)).
OPTIONAL_FEATURES = (
    ('up_orders_28', 'number of distinct orders of the user in [A - 28 days, A) that contain the product',
     '0 when none'),
    ('up_last5_share', 'share of the last 5 orders of the user before A (by time descending, then order_id '
                       'descending) that contain the product; the denominator is min(5, u_orders)', '0 when none'),
    ('up_in_last_order', '1 when the latest order of the user before A (latest time, then largest order_id) '
                         'contains the product, else 0', '0 when none'),
    ('up_days_since_first', 'days from the earliest order of the user with the product to A (fractional, from '
                            'seconds)', 'NULL when the user never bought the product'),
    ('p_buyers_7', 'distinct users who bought the product over all orders in [A - 7 days, A)', '0 when none'),
    ('p_trend', 'p_buyers_7 / p_buyers_28', 'NULL when p_buyers_28 = 0'),
    ('p_buyers_28_main_share', 'p_buyers_28_main / p_buyers_28', 'NULL when p_buyers_28 = 0'),
    ('up_qty_mean', 'up_qty_total / number of lines of the product of the user before A (repeated lines included)',
     'NULL when there are no such lines'),
    ('uc_days_since_last', 'days from the latest order of the user with a line of a product of the same category '
                           'as the product to A (fractional, from seconds); categories as in uc_share',
     'NULL when the product has no category or there is no such order'),
)
CATEGORICAL = ('main_retailer',)
FEATURE_SQL = {
    'up_orders': 'COALESCE(up.up_orders, 0)',
    'up_share': 'COALESCE(up.up_orders, 0) / u.u_orders',
    'up_days_since_last': "date_diff('second', up.last_ts, {a}) / 86400.0",
    'up_mean_interval': "CASE WHEN up.up_orders >= 2 THEN date_diff('second', up.first_ts, up.last_ts) / 86400.0 "
                        "/ (up.up_orders - 1) END",
    'up_due': "CASE WHEN up.up_orders >= 2 AND up.last_ts > up.first_ts THEN (date_diff('second', up.last_ts, {a}) "
              "/ 86400.0) / (date_diff('second', up.first_ts, up.last_ts) / 86400.0 / (up.up_orders - 1)) END",
    'up_qty_total': 'COALESCE(up.qty, 0)',
    'up_last_price': 'up.last_price',
    'up_discount_share': 'up.disc',
    'repeat_rank': 'up.repeat_rank',
    'popr_rank': 'r.rnk',
    'glob_rank': 'g.rnk',
    'u_orders': 'u.u_orders',
    'u_orders_28': 'u.u_orders_28',
    'u_days_since_last': 'u.u_days_since_last',
    'u_mean_basket': 'ub.basket',
    'u_mean_gap': 'u.u_mean_gap',
    'u_main_share': 'u.u_main_share',
    'p_buyers_28': 'COALESCE(g.buyers, 0)',
    'p_buyers_28_main': 'COALESCE(r.buyers, 0)',
    'p_repeat_share': 'pr.share',
    'uc_share': 'CASE WHEN pc.cat IS NULL THEN NULL ELSE COALESCE(uc.n, 0) / u.u_orders END',
    'main_retailer': 'u.main_retailer',
    'up_orders_28': 'COALESCE(up.up_orders_28, 0)',
    'up_last5_share': 'COALESCE(rc.n5, 0) / least(5, u.u_orders)',
    'up_in_last_order': 'COALESCE(rc.in_last, 0)',
    'up_days_since_first': "date_diff('second', up.first_ts, {a}) / 86400.0",
    'p_buyers_7': 'COALESCE(p7.buyers, 0)',
    'p_trend': 'CASE WHEN g.buyers > 0 THEN COALESCE(p7.buyers, 0) / g.buyers END',
    'p_buyers_28_main_share': 'CASE WHEN g.buyers > 0 THEN COALESCE(r.buyers, 0) / g.buyers END',
    'up_qty_mean': 'up.qty / up.n_lines',
    'uc_days_since_last': "CASE WHEN pc.cat IS NOT NULL THEN date_diff('second', uc.last_ts, {a}) / 86400.0 END",
}
RANK_COLUMNS = ('repeat_rank', 'popr_rank', 'glob_rank')
CANDIDATE_KEYS = ('per_query', 'window_days', 'repeat_depth', 'pop_retailer_depth')


def candidate_policy(per_query=200, repeat_depth=150, pop_retailer_depth=100, window_days=28):
    """Candidate policy of doc 3 with its English description (the prompt shows it from base.json)."""
    text = [
        f'Up to {per_query} candidates per query, all statistics from the history before A.',
        'Main retailer of the user: the retailer with the most distinct orders of the user; ties by the later last '
        'order of the user there, then by retailer code.',
        f'(a) repeat: the distinct products the user bought before A, by the number of distinct orders with the '
        f'product descending, then the time of the latest such order descending, then product_id; the first '
        f'{repeat_depth}.',
        f'(b) pop-retailer: products by distinct buyers at the main retailer in [A - {window_days} days, A) '
        f'descending, then product_id; the first {pop_retailer_depth}.',
        f'(c) global: products by distinct buyers over all orders in [A - {window_days} days, A) descending, then '
        f'product_id.',
        f'Union: (a) in its order, then (b) without (a), then (c) without (a) and (b), until exactly {per_query} '
        f'candidates. Source ranks repeat_rank, popr_rank and glob_rank are positions in the full orders.',
    ]
    return dict(name=f'S-R{repeat_depth}-P{pop_retailer_depth}-G{per_query}', per_query=per_query,
                window_days=window_days, repeat_depth=repeat_depth, pop_retailer_depth=pop_retailer_depth,
                sources=[dict(name='repeat', rank='repeat_rank', depth=repeat_depth),
                         dict(name='pop_retailer', rank='popr_rank', depth=pop_retailer_depth),
                         dict(name='global', rank='glob_rank', depth=None)],
                text=text)


def initial_base(extra=(), **policy):
    """The starting B of doc 3-4 (the coordinator freezes base.json from it).

    ``extra``: names of OPTIONAL_FEATURES appended in the given order (base-dev); without it the base is
    exactly the initial one.
    """
    optional = {n: (f, m) for n, f, m in OPTIONAL_FEATURES}
    xc.require(all(n in optional for n in extra), f'Unknown optional features {sorted(set(extra) - set(optional))}')
    features = [dict(name=n, formula=f, missing=m) for n, f, m in FEATURES]
    features += [dict(name=n, formula=optional[n][0], missing=optional[n][1]) for n in extra]
    return xc.make_base(DATASET, candidate_policy(**policy), features, list(CATEGORICAL))


def _policy(base):
    xc.check_base(base, DATASET)
    cand = base['candidates']
    policy = {k: cand.get(k) for k in CANDIDATE_KEYS}
    xc.require(all(type(v) is int and v > 0 for v in policy.values()), 'Candidate policy needs positive integers')
    xc.require(policy['repeat_depth'] <= policy['per_query'], 'repeat depth exceeds the candidates per query')
    # Pop (doc 5) stays inside the candidates (coordinator decision): the same window, at least K from (b)
    # and room for K products of (b) and (c) after (a).
    xc.require(policy['window_days'] == POP_WINDOW_DAYS, f'window_days must be {POP_WINDOW_DAYS} (Pop window)')
    xc.require(policy['pop_retailer_depth'] >= K, f'pop_retailer_depth must be at least K = {K}')
    xc.require(policy['per_query'] - policy['repeat_depth'] >= K, f'per_query - repeat_depth must be at least K = {K}')
    known = {n: (f, m) for n, f, m in FEATURES + OPTIONAL_FEATURES}
    for feature in base['features']:
        xc.require(feature['name'] in known, f"Base feature {feature['name']} has no implementation")
        xc.require((feature['formula'], feature['missing']) == known[feature['name']],
                   f"Base feature {feature['name']} differs from its implementation text")
    xc.require(set(base['categorical']) <= set(CATEGORICAL), 'Unknown categorical feature')
    return policy


# ---------------------------------------------------------------- candidates and features

def _anchor_tables(con, A, window_days):
    """Per-anchor tables over all users: source orders (b), (c) and product statistics."""
    a = _ts(A)
    con.execute(f'''CREATE OR REPLACE TEMP TABLE w_recent AS SELECT l.user_id, l.product_id, o.retailer
        FROM lines l JOIN orders o USING (order_id) WHERE l.ts >= {a} - INTERVAL {int(window_days)} DAY''')
    con.execute('''CREATE OR REPLACE TEMP TABLE g_rank AS SELECT product_id, buyers,
        row_number() OVER (ORDER BY buyers DESC, product_id) AS rnk
        FROM (SELECT product_id, count(DISTINCT user_id) AS buyers FROM w_recent GROUP BY 1)''')
    con.execute('''CREATE OR REPLACE TEMP TABLE r_rank AS SELECT retailer, product_id, buyers,
        row_number() OVER (PARTITION BY retailer ORDER BY buyers DESC, product_id) AS rnk
        FROM (SELECT retailer, product_id, count(DISTINCT user_id) AS buyers FROM w_recent GROUP BY 1, 2)''')


def _product_tables(con, A):
    a = _ts(A)
    con.execute(f'''CREATE OR REPLACE TEMP TABLE p_rep AS SELECT product_id,
        avg(CASE WHEN n >= 2 THEN 1.0 ELSE 0.0 END) AS share
        FROM (SELECT user_id, product_id, count(DISTINCT order_id) AS n FROM lines
              WHERE ts >= {a} - INTERVAL {REPEAT_SHARE_DAYS} DAY GROUP BY 1, 2) GROUP BY 1''')
    con.execute('''CREATE OR REPLACE TEMP TABLE p_cat AS SELECT product_id, max(master_category_id) AS cat
        FROM lines GROUP BY 1''')
    con.execute(f'''CREATE OR REPLACE TEMP TABLE p_b7 AS SELECT l.product_id, count(DISTINCT l.user_id) AS buyers
        FROM lines l JOIN orders o USING (order_id) WHERE l.ts >= {a} - INTERVAL 7 DAY GROUP BY 1''')


def _user_tables(con, A):
    """Tables of the users in ``cu``: their orders, lines, main retailer and repeat order."""
    a = _ts(A)
    con.execute('''CREATE OR REPLACE TEMP TABLE c_orders AS SELECT o.order_id, o.user_id, o.ts, o.retailer,
        n.retailer_name FROM orders o JOIN cu USING (user_id) LEFT JOIN retailer_names n USING (retailer)''')
    con.execute('''CREATE OR REPLACE TEMP TABLE c_lines AS SELECT l.user_id, l.order_id, l.ts, l.product_id,
        l.line_item_id, l.price, l.quantity, l.discount FROM lines l JOIN cu USING (user_id)''')
    con.execute('''CREATE OR REPLACE TEMP TABLE c_main AS SELECT user_id, retailer AS main_retailer FROM (
        SELECT user_id, retailer, row_number() OVER (PARTITION BY user_id ORDER BY n DESC, last DESC,
               retailer_name, retailer) AS rn
        FROM (SELECT user_id, retailer, any_value(retailer_name) AS retailer_name, count(DISTINCT order_id) AS n,
                     max(ts) AS last FROM c_orders GROUP BY 1, 2)) WHERE rn = 1''')
    con.execute(f'''CREATE OR REPLACE TEMP TABLE c_user AS SELECT o.user_id, m.main_retailer,
        CAST(count(DISTINCT o.order_id) AS DOUBLE) AS u_orders,
        CAST(count(DISTINCT o.order_id) FILTER (WHERE o.ts >= {a} - INTERVAL 28 DAY) AS DOUBLE) AS u_orders_28,
        date_diff('second', max(o.ts), {a}) / 86400.0 AS u_days_since_last,
        CASE WHEN count(DISTINCT o.order_id) >= 2 THEN date_diff('second', min(o.ts), max(o.ts)) / 86400.0
             / (count(DISTINCT o.order_id) - 1) END AS u_mean_gap,
        count(DISTINCT o.order_id) FILTER (WHERE o.retailer = m.main_retailer) / count(DISTINCT o.order_id)
            AS u_main_share
        FROM c_orders o JOIN c_main m USING (user_id) GROUP BY o.user_id, m.main_retailer''')
    con.execute('''CREATE OR REPLACE TEMP TABLE c_basket AS SELECT user_id, avg(np) AS basket FROM (
        SELECT user_id, order_id, count(DISTINCT product_id) AS np FROM c_lines GROUP BY 1, 2) GROUP BY 1''')
    con.execute(f'''CREATE OR REPLACE TEMP TABLE c_up AS SELECT *, row_number() OVER (PARTITION BY user_id
        ORDER BY up_orders DESC, last_ts DESC, product_id) AS repeat_rank FROM (
        SELECT user_id, product_id, count(DISTINCT order_id) AS up_orders, min(ts) AS first_ts, max(ts) AS last_ts,
               sum(quantity) AS qty, max_by(price, [epoch_us(ts), order_id, line_item_id]) AS last_price,
               avg(discount / (price + discount)) FILTER (WHERE price + discount > 0) AS disc,
               count(DISTINCT order_id) FILTER (WHERE ts >= {a} - INTERVAL 28 DAY) AS up_orders_28,
               count(*) AS n_lines
        FROM c_lines GROUP BY 1, 2)''')
    con.execute('''CREATE OR REPLACE TEMP TABLE c_last AS SELECT user_id, order_id, row_number() OVER (
        PARTITION BY user_id ORDER BY ts DESC, order_id DESC) AS rn FROM c_orders''')
    con.execute('''CREATE OR REPLACE TEMP TABLE c_recent AS SELECT l.user_id, l.product_id,
        count(DISTINCT l.order_id) AS n5, max(CASE WHEN o.rn = 1 THEN 1 ELSE 0 END) AS in_last
        FROM c_lines l JOIN c_last o ON o.user_id = l.user_id AND o.order_id = l.order_id WHERE o.rn <= 5
        GROUP BY 1, 2''')


def _candidates(con, policy):
    """Union of doc 3 for the users in ``cu`` into ``c_cand(user_id, product_id, src, slot)``."""
    total, ra, rb = policy['per_query'], policy['repeat_depth'], policy['pop_retailer_depth']
    con.execute(f'''CREATE OR REPLACE TEMP TABLE c_cand AS
        WITH listed AS (
            SELECT user_id, product_id, 1 AS src, repeat_rank AS pos FROM c_up WHERE repeat_rank <= {ra}
            UNION ALL
            SELECT m.user_id, r.product_id, 2, r.rnk FROM c_main m JOIN r_rank r ON r.retailer = m.main_retailer
            WHERE r.rnk <= {rb}
            UNION ALL
            SELECT u.user_id, g.product_id, 3, g.rnk FROM cu u CROSS JOIN g_rank g WHERE g.rnk <= {total+ra+rb}),
        first AS (SELECT user_id, product_id, min(src) AS src, arg_min(pos, src) AS pos FROM listed GROUP BY 1, 2)
        SELECT user_id, product_id, src, slot FROM (
            SELECT *, row_number() OVER (PARTITION BY user_id ORDER BY src, pos) AS slot FROM first)
        WHERE slot <= {total}''')


def _feature_select(base, A):
    a = _ts(A)
    parts = []
    for name in xc.base_feature_names(base):
        expr = FEATURE_SQL[name].format(a=a)
        parts.append(f'{expr} AS {name}' if name in CATEGORICAL else f'CAST({expr} AS DOUBLE) AS {name}')
    return ', '.join(parts)


def _frame_chunk(con, base, A, policy):
    """Candidates and base features of the users in ``cu``; appended to ``frame_rows``."""
    _user_tables(con, A)
    _candidates(con, policy)
    con.execute('''CREATE OR REPLACE TEMP TABLE c_uc AS SELECT l.user_id, c.cat, count(DISTINCT l.order_id) AS n,
        max(l.ts) AS last_ts FROM c_lines l JOIN p_cat c USING (product_id) WHERE c.cat IS NOT NULL GROUP BY 1, 2''')
    features = _feature_select(base, A)
    con.execute(f'''INSERT INTO frame_rows SELECT c.user_id, c.product_id AS item_id,
        CASE c.src WHEN 1 THEN 'repeat' WHEN 2 THEN 'pop_retailer' ELSE 'global' END AS source, {features}
        FROM c_cand c JOIN c_user u USING (user_id) LEFT JOIN c_basket ub USING (user_id)
        LEFT JOIN c_up up ON up.user_id = c.user_id AND up.product_id = c.product_id
        LEFT JOIN g_rank g ON g.product_id = c.product_id
        LEFT JOIN r_rank r ON r.retailer = u.main_retailer AND r.product_id = c.product_id
        LEFT JOIN p_rep pr ON pr.product_id = c.product_id
        LEFT JOIN p_cat pc ON pc.product_id = c.product_id
        LEFT JOIN c_uc uc ON uc.user_id = c.user_id AND uc.cat = pc.cat
        LEFT JOIN c_recent rc ON rc.user_id = c.user_id AND rc.product_id = c.product_id
        LEFT JOIN p_b7 p7 ON p7.product_id = c.product_id''')


def _build_frame(con, base, A, users, chunk=CHUNK):
    """frame_rows for the sorted ``users`` (list of ints), chunk by chunk; checks exactly per_query each."""
    policy = _policy(base)
    _anchor_tables(con, A, policy['window_days'])
    _product_tables(con, A)
    numeric = [n for n in xc.base_feature_names(base) if n not in CATEGORICAL]
    columns = ', '.join(['user_id BIGINT', 'item_id BIGINT', 'source VARCHAR',
                         *[f'{n} VARCHAR' if n in CATEGORICAL else f'{n} DOUBLE'
                           for n in xc.base_feature_names(base)]])
    con.execute(f'CREATE OR REPLACE TEMP TABLE frame_rows ({columns})')
    import pandas as pd
    ordered = sorted(int(u) for u in users)
    for start in range(0, len(ordered), chunk):
        con.register('cu_frame', pd.DataFrame({'user_id': pd.Series(ordered[start:start+chunk], dtype='int64')}))
        con.execute('CREATE OR REPLACE TEMP TABLE cu AS SELECT user_id FROM cu_frame')
        con.unregister('cu_frame')
        _frame_chunk(con, base, A, policy)
    short = con.execute(f'''SELECT count(*) FROM (SELECT u.user_id, count(f.item_id) AS n
        FROM (SELECT unnest(?::BIGINT[]) AS user_id) u LEFT JOIN frame_rows f USING (user_id) GROUP BY 1)
        WHERE n <> {policy['per_query']}''', [ordered]).fetchone()[0]
    xc.require(short == 0, f'{short} users do not get exactly {policy["per_query"]} candidates')
    return numeric


def _register_users(con, name, users):
    import pandas as pd
    frame = pd.DataFrame({'user_id': pd.Series(sorted({int(u) for u in users}), dtype='int64')})
    con.register(f'{name}_frame', frame)
    con.execute(f'CREATE OR REPLACE TEMP TABLE {name} AS SELECT user_id FROM {name}_frame')
    con.unregister(f'{name}_frame')


def _query_order(con, table, limit):
    order = xc.QUERY_ORDER_SQL.format(column='user_id')
    tail = '' if limit is None else f' LIMIT {int(limit)}'
    return [int(r[0]) for r in con.execute(f'SELECT user_id FROM {table} ORDER BY {order}, user_id{tail}').fetchall()]


def _read_users_file(path):
    path = Path(path)
    if path.suffix == '.parquet':
        return [int(u) for u in xc.read_parquet(path, ['user_id'])['user_id']]
    if path.suffix == '.json':
        return [int(u) for u in json.loads(path.read_text(encoding='utf-8'))]
    return [int(line) for line in path.read_text(encoding='utf-8').split() if line.strip()]


def collect(A, role, base, output, users=None, threads=xc.THREADS['collect'], chunk=CHUNK):
    """Collection of doc 2 / common 7 into the new directory ``output``; returns the manifest."""
    started = time.monotonic()
    A = _date(A)
    xc.require(role in xc.ROLES, f'Unknown role {role!r}')
    xc.require(A in anchors()['roles'][role], f'{A} is not an anchor of role {role}')
    policy = _policy(base)
    xc.require(role != 'probe' or users is not None, 'The probe collection needs its users')
    xc.require(role != 'holdout' or users is None, 'The holdout collection takes every query')
    output = Path(output)
    xc.require(not output.exists(), f'{output} exists; a collection goes to a new directory')
    if role == 'holdout':
        xc.require(output.resolve() == xc.current_holdout_collection(DATASET, A).resolve(),
                   'The holdout collection goes only to the current holdout collection path')
    if users is not None:
        xc.require(role == 'probe' or output.resolve().is_relative_to(xc.output_dir(DATASET, 'base-dev').resolve()),
                   'A user restriction is allowed only for the probe or under base-dev/')
    purpose = {'holdout': 'collect-holdout', 'kaggle': 'collect-kaggle', 'probe': 'probe'}.get(role, 'collect')
    if role in ('holdout', 'kaggle'):
        # Before new_output: a refused collection leaves no empty directory at the canonical path.
        xc.require_window(DATASET, purpose)
    code = xc.code_identity(DATASET)
    output = xc.new_output(output)
    hist = future = None
    counts = {}
    extra = dict(purpose=purpose, threads=threads, chunk=chunk, policy=base['candidates'].get('name'),
                 users_restricted=users is not None)
    try:
        hist = history(A, purpose, threads)
        if users is not None:
            _register_users(hist, 'restrict', users)
            extra['users_restricted_count'] = len({int(u) for u in users})
        known_users = 'SELECT DISTINCT user_id FROM orders'
        targets = None
        if role in ('train', 'val', 'holdout'):
            future = history(_shift(A, W), purpose, threads)
            window = future.execute(f'''SELECT user_id, order_id FROM (SELECT user_id, order_id, row_number() OVER
                (PARTITION BY user_id ORDER BY ts, order_id) AS rn FROM orders WHERE ts >= {_ts(A)}) WHERE rn = 1''').df()
            _register_users(hist, 'window_users', window['user_id'])
            pool_sql = (f'SELECT user_id FROM window_users SEMI JOIN ({known_users}) h USING (user_id)' +
                        (' SEMI JOIN restrict USING (user_id)' if users is not None else ''))
            hist.execute(f'CREATE TEMP TABLE pool AS {pool_sql}')
            pool = hist.execute('SELECT count(*) FROM pool').fetchone()[0]
            queries = _query_order(hist, 'pool', QUERY_CAP[role])
            future.register('first_frame', window)
            _register_users(future, 'queries', queries)
            targets = future.execute('''SELECT DISTINCT f.user_id, l.product_id AS item_id FROM first_frame f
                SEMI JOIN queries q USING (user_id) JOIN lines l ON l.order_id = f.order_id
                ORDER BY 1, 2''').df()
            future.close()
            future = None
            extra.update(pool=int(pool), cap=QUERY_CAP[role], window_end=_shift(A, W))
        elif role == 'kaggle':
            hist.execute(f'''CREATE TEMP TABLE pool AS SELECT s.user_id FROM st.submission s
                SEMI JOIN ({known_users}) h USING (user_id)''' +
                         (' SEMI JOIN restrict USING (user_id)' if users is not None else ''))
            queries = _query_order(hist, 'pool', None)
            fallback = [int(r[0]) for r in hist.execute(f'''SELECT s.user_id FROM st.submission s
                ANTI JOIN ({known_users}) h USING (user_id) ORDER BY s.position''').fetchall()]
            extra.update(pool=len(queries), submission_ids=hist.execute(
                'SELECT count(*) FROM st.submission').fetchone()[0], fallback_ids=len(fallback))
        else:  # probe
            _register_users(hist, 'pool', users)
            missing = hist.execute(f'SELECT count(*) FROM pool ANTI JOIN ({known_users}) h USING (user_id)'
                                   ).fetchone()[0]
            xc.require(missing == 0, f'{missing} probe users have no history before {A}')
            queries = _query_order(hist, 'pool', None)
            extra.update(pool=len(queries))
        xc.require(queries, f'No queries for role {role} at {A}')
        _build_frame(hist, base, A, queries, chunk)
        names = xc.base_feature_names(base)
        cols = ', '.join(['user_id', 'item_id', *names])
        hist.execute(f'''COPY (SELECT {cols} FROM frame_rows ORDER BY user_id, item_id)
            TO {_literal(output/xc.FRAME_FILE)} (FORMAT PARQUET)''')
        hist.execute(f'''COPY (SELECT user_id, item_id, source FROM frame_rows ORDER BY user_id, item_id)
            TO {_literal(output/'sources.parquet')} (FORMAT PARQUET)''')
        rows, n_users = hist.execute('SELECT count(*), count(DISTINCT user_id) FROM frame_rows').fetchone()
        by_source = dict(hist.execute('SELECT source, count(*) FROM frame_rows GROUP BY 1 ORDER BY 1').fetchall())
        counts.update(queries=len(queries), users=int(n_users), rows=int(rows),
                      rows_by_source={s: int(by_source.get(s, 0)) for s in SOURCES})

        sealed = None
        if targets is not None:
            hist.register('targets_frame', targets)
            hist.execute('CREATE TEMP TABLE target_pairs AS SELECT user_id, item_id FROM targets_frame')
            hist.unregister('targets_frame')
            label_sql = '''SELECT f.user_id, f.item_id, (t.item_id IS NOT NULL) AS label FROM frame_rows f
                LEFT JOIN target_pairs t ON t.user_id = f.user_id AND t.item_id = f.item_id
                ORDER BY f.user_id, f.item_id'''
            target_sql = '''SELECT user_id, count(*) AS n_targets FROM target_pairs GROUP BY 1 ORDER BY 1'''
            bad = hist.execute('''SELECT count(*) FROM (SELECT user_id FROM frame_rows EXCEPT
                SELECT user_id FROM target_pairs)''').fetchone()[0]
            xc.require(bad == 0, 'A query has no target')

            def write_labels(directory):
                hist.execute(f"COPY ({label_sql}) TO {_literal(Path(directory)/'labels.parquet')} (FORMAT PARQUET)")
                hist.execute(f"COPY ({target_sql}) TO {_literal(Path(directory)/'targets.parquet')} (FORMAT PARQUET)")
            if role == 'holdout':
                sealed = xc.write_sealed(output, write_labels)
            else:
                write_labels(output)
                positives, positive_queries, n_targets = hist.execute(f'''SELECT count(*) FILTER (WHERE label),
                    count(DISTINCT user_id) FILTER (WHERE label), (SELECT count(*) FROM target_pairs)
                    FROM ({label_sql})''').fetchone()
                counts.update(positive_rows=int(positives), positive_queries=int(positive_queries),
                              n_targets=int(n_targets))
        if role == 'kaggle':
            _write_kaggle_aux(hist, output, fallback, queries)
        manifest = xc.write_manifest(output, DATASET, role, A, counts, base, code, sealed=sealed,
                                     extra=dict(extra, seconds=round(time.monotonic()-started, 1)))
    finally:
        for con in (future, hist):
            if con is not None:
                con.close()
    return manifest


def _write_kaggle_aux(con, output, fallback, queries):
    """Fallback Ids, known products and the fill orders (b), (c) for assemble (doc 7)."""
    import pandas as pd
    xc.write_parquet(pd.DataFrame({'user_id': pd.Series(fallback, dtype='int64')}), output/'fallback.parquet')
    con.execute(f'''COPY (SELECT DISTINCT product_id AS item_id FROM lines ORDER BY 1)
        TO {_literal(output/'known.parquet')} (FORMAT PARQUET)''')
    con.execute(f'''COPY (SELECT rnk AS rank, product_id AS item_id FROM g_rank WHERE rnk <= {3*K} ORDER BY rnk)
        TO {_literal(output/'global_top.parquet')} (FORMAT PARQUET)''')
    con.execute(f'''COPY (SELECT retailer, rnk AS rank, product_id AS item_id FROM r_rank WHERE rnk <= {2*K}
        ORDER BY retailer, rnk) TO {_literal(output/'retailer_top.parquet')} (FORMAT PARQUET)''')
    _register_users(con, 'scoring', queries)
    _main_retailers(con, 'scoring')
    con.execute(f'''COPY (SELECT user_id, main_retailer AS retailer FROM all_main ORDER BY user_id)
        TO {_literal(output/'user_retailer.parquet')} (FORMAT PARQUET)''')


def _main_retailers(con, users_table):
    con.execute(f'''CREATE OR REPLACE TEMP TABLE all_main AS SELECT user_id, retailer AS main_retailer FROM (
        SELECT user_id, retailer, row_number() OVER (PARTITION BY user_id ORDER BY n DESC, last DESC,
               retailer_name, retailer) AS rn
        FROM (SELECT o.user_id, o.retailer, any_value(n.retailer_name) AS retailer_name,
                     count(DISTINCT o.order_id) AS n, max(o.ts) AS last
              FROM orders o JOIN {users_table} USING (user_id) LEFT JOIN retailer_names n USING (retailer)
              GROUP BY 1, 2)) WHERE rn = 1''')


# ---------------------------------------------------------------- Pop (doc 5)

def pop(A, users, k=K, threads=xc.THREADS['collect']):
    """(b) of the main retailer in its order, then (c) without (b); first k. No base.json."""
    import pandas as pd
    A = _date(A)
    con = history(A, 'pop', threads)
    try:
        _anchor_tables(con, A, POP_WINDOW_DAYS)
        _register_users(con, 'pop_users', users)
        _main_retailers(con, 'pop_users')
        result = con.execute(f'''WITH listed AS (
                SELECT m.user_id, r.product_id, 1 AS src, r.rnk AS pos FROM all_main m
                JOIN r_rank r ON r.retailer = m.main_retailer WHERE r.rnk <= {int(k)}
                UNION ALL
                SELECT u.user_id, g.product_id, 2, g.rnk FROM pop_users u CROSS JOIN g_rank g WHERE g.rnk <= {2*int(k)}),
            first AS (SELECT user_id, product_id, min(src) AS src, arg_min(pos, src) AS pos FROM listed GROUP BY 1, 2)
            SELECT user_id, item_id, rank FROM (SELECT user_id, product_id AS item_id,
                row_number() OVER (PARTITION BY user_id ORDER BY src, pos) AS rank FROM first)
            WHERE rank <= {int(k)} ORDER BY user_id, rank''').df()
    finally:
        con.close()
    return result.astype({'user_id': 'int64', 'item_id': 'int64', 'rank': 'int64'}) if len(result) else pd.DataFrame(
        {'user_id': pd.Series(dtype='int64'), 'item_id': pd.Series(dtype='int64'), 'rank': pd.Series(dtype='int64')})


# ---------------------------------------------------------------- training rows and metric (doc 1, 4.1)

def negative_hash(anchor, user_id, item_id, seed=xc.SAMPLE_SEED):
    """Python reference of the negative hash: sha256('YYYY-MM-DD|user|product|2026'), lowercase hex."""
    return hashlib.sha256(f'{_date(anchor)}|{int(user_id)}|{int(item_id)}|{int(seed)}'.encode('utf-8')).hexdigest()


def training_rows(frame, labels, A, seed=xc.SAMPLE_SEED):
    """All positives plus the NEGATIVES negatives per query with the smallest hash; weights of doc 4.1.

    ``frame`` is restricted to the capped queries and holds every candidate row of
    them. Returns the frame rows kept, with ``label``, ``query_weight``,
    ``inclusion_probability`` and ``weight``, in ``user_id, item_id`` order.
    """
    import duckdb
    import numpy as np
    A = _date(A)
    xc.require(len(frame) and not frame.duplicated(['user_id', 'item_id']).any(), 'Training keys must be unique')
    con = duckdb.connect()
    try:
        con.register('f', frame[['user_id', 'item_id']])
        con.register('lb', labels[['user_id', 'item_id', 'label']])
        kept = con.execute(f'''WITH j AS (
                SELECT f.user_id, f.item_id, CAST(lb.label AS BOOLEAN) AS label,
                       count(*) OVER (PARTITION BY f.user_id) AS n_cand
                FROM f LEFT JOIN lb ON lb.user_id = f.user_id AND lb.item_id = f.item_id),
            neg AS (SELECT user_id, item_id, row_number() OVER (PARTITION BY user_id ORDER BY h, item_id) AS rn,
                           count(*) OVER (PARTITION BY user_id) AS n_neg
                    FROM (SELECT user_id, item_id, sha256(? || '|' || CAST(user_id AS VARCHAR) || '|' ||
                                 CAST(item_id AS VARCHAR) || '|' || CAST(? AS VARCHAR)) AS h
                          FROM j WHERE NOT label))
            SELECT j.user_id, j.item_id, j.label, 1.0 / j.n_cand AS query_weight,
                   CASE WHEN j.label THEN 1.0 ELSE least({NEGATIVES}, n.n_neg) / n.n_neg END AS inclusion_probability,
                   j.label IS NULL AS missing
            FROM j LEFT JOIN neg n ON n.user_id = j.user_id AND n.item_id = j.item_id
            WHERE j.label IS NULL OR j.label OR n.rn <= {NEGATIVES}
            ORDER BY j.user_id, j.item_id''', [A, int(seed)]).df()
    finally:
        con.close()
    xc.require(not kept['missing'].any(), 'A frame row has no label')
    kept = kept.drop(columns='missing')
    kept['weight'] = kept['query_weight'] / kept['inclusion_probability']
    out = frame.merge(kept, on=['user_id', 'item_id'], how='inner', validate='one_to_one')
    out = out.sort_values(['user_id', 'item_id']).reset_index(drop=True)
    xc.require(set(out['user_id']) == set(frame['user_id']), 'Sampling lost a query')
    xc.require(int(out['label'].sum()) == int(labels.merge(frame[['user_id', 'item_id']])['label'].astype(bool).sum()),
               'Sampling lost a positive')
    xc.require(np.isfinite(out['weight']).all(), 'Non-finite weights')
    return out


def rank_scores(scores, k=K):
    """``user_id, item_id, rank`` from ``user_id, item_id, score``: score DESC, then item_id ASC; first k."""
    import numpy as np
    order = np.lexsort((scores['item_id'].to_numpy(), -scores['score'].to_numpy(dtype=float),
                        scores['user_id'].to_numpy()))
    ranked = scores.iloc[order][['user_id', 'item_id']].reset_index(drop=True)
    ranked['rank'] = ranked.groupby('user_id').cumcount() + 1
    return ranked[ranked['rank'] <= k].reset_index(drop=True)


def metric(ranked, targets, labels, k=K):
    """AP@50 per query of ``targets`` (doc 1): (1/min(50, M)) * sum_k rel_k * P@k; no ranked rows -> 0.

    Relevance comes from ``labels`` (candidate rows); a ranked item without a label
    is refused, because its relevance is unknown.
    """
    import pandas as pd
    t = targets[targets['n_targets'] >= 1][['user_id', 'n_targets']]
    xc.require(not t['user_id'].duplicated().any(), 'targets repeat a query')
    r = ranked[ranked['rank'] <= k][['user_id', 'item_id', 'rank']]
    xc.require(not r.duplicated(['user_id', 'rank']).any() and not r.duplicated(['user_id', 'item_id']).any(),
               'ranked repeats a rank or an item')
    xc.require(set(r['user_id']) <= set(t['user_id']), 'ranked has users outside the queries')
    joined = r.merge(labels[['user_id', 'item_id', 'label']], on=['user_id', 'item_id'], how='left')
    xc.require(not joined['label'].isna().any(), 'A ranked item has no label (not a candidate)')
    joined['rel'] = joined['label'].astype(bool).astype(float)
    joined = joined.sort_values(['user_id', 'rank'])
    joined['hits'] = joined.groupby('user_id')['rel'].cumsum()
    joined['term'] = joined['rel'] * joined['hits'] / joined['rank']
    sums = joined.groupby('user_id')['term'].sum()
    out = t.set_index('user_id')
    value = sums.reindex(out.index).fillna(0.0) / out['n_targets'].clip(upper=k)
    return pd.DataFrame({'user_id': out.index.astype('int64'), 'value': value.to_numpy(dtype=float)}).sort_values(
        'user_id').reset_index(drop=True)


# ---------------------------------------------------------------- Kaggle file (doc 7)

def check_submission(path, ids, known, k=K):
    """Re-check a submission: header, the Ids of ``ids`` in that order, k distinct known ids, LF endings."""
    data = Path(path).read_bytes()
    xc.require(data.endswith(b'\n') and b'\r' not in data, 'Every line must end with LF')
    lines = data.decode('utf-8').split('\n')[:-1]
    xc.require(lines and lines[0] == 'Id,Predicted', 'Header must be Id,Predicted')
    seen, order = set(), []
    known = set(known)
    for line in lines[1:]:
        head, _, tail = line.partition(',')
        xc.require(head.isdigit() and str(int(head)) == head, f'Bad Id {head!r}')
        user = int(head)
        xc.require(user not in seen, f'Id {user} repeats')
        seen.add(user)
        order.append(user)
        items = tail.split(' ')
        xc.require(len(items) == k and all(x.isdigit() and str(int(x)) == x for x in items),
                   f'Id {user} must carry {k} product ids')
        values = [int(x) for x in items]
        xc.require(len(set(values)) == k, f'Id {user} repeats a product id')
        xc.require(set(values) <= known, f'Id {user} carries an unknown product id')
    xc.require(seen == set(int(i) for i in ids), 'Id set differs from sample_submission')
    xc.require(order == [int(i) for i in ids], 'Id order differs from sample_submission')
    return dict(rows=len(lines)-1)


def assemble(scores, output, collection=None):
    """Kaggle file from the scores of the kaggle frame: ``.part``, re-check, rename, receipt (doc 7)."""
    import duckdb
    import pandas as pd
    output = Path(output).resolve()
    xc.require(output.suffix == '.csv', 'The submission is a .csv file')
    xc.require(output.is_relative_to((xc.ROOT/'artifacts'/'xfer').resolve()), 'Submissions live under artifacts/xfer')
    receipt = output.with_suffix('.json')
    xc.require(not output.exists() and not receipt.exists(), f'Refusing to overwrite {output}')
    collection = Path(collection) if collection is not None else xc.output_dir(
        DATASET, 'collections', xc.collection_name('kaggle', KAGGLE_ANCHOR))
    manifest = xc.read_collection(collection, DATASET, 'kaggle')
    known = set(int(x) for x in xc.read_parquet(collection/'known.parquet')['item_id'])
    fallback = [int(x) for x in xc.read_parquet(collection/'fallback.parquet')['user_id']]
    glob = [int(x) for x in xc.read_parquet(collection/'global_top.parquet').sort_values('rank')['item_id']]
    rtop = xc.read_parquet(collection/'retailer_top.parquet').sort_values(['retailer', 'rank'])
    by_retailer = {r: [int(x) for x in g['item_id']] for r, g in rtop.groupby('retailer')}
    user_retailer = dict(zip(xc.read_parquet(collection/'user_retailer.parquet')['user_id'].astype(int),
                             xc.read_parquet(collection/'user_retailer.parquet')['retailer']))
    static = duckdb.connect(str(xc.static_path(DATASET)), read_only=True)
    try:
        ids = [int(r[0]) for r in static.execute('SELECT user_id FROM submission ORDER BY position').fetchall()]
    finally:
        static.close()
    scores = scores[['user_id', 'item_id', 'score']]
    xc.require(pd.api.types.is_numeric_dtype(scores['score']) and bool(scores['score'].map(math.isfinite).all()),
               'Scores must be finite')
    xc.require(not scores.duplicated(['user_id', 'item_id']).any(), 'Scores repeat a (user, item) pair')
    con = duckdb.connect()
    try:
        con.register('scored', scores[['user_id', 'item_id']])
        frame = _literal(collection/xc.FRAME_FILE)
        frame_users = {int(r[0]) for r in con.execute(f'SELECT DISTINCT user_id FROM read_parquet({frame})').fetchall()}
        outside = con.execute(f'''SELECT count(*) FROM scored s ANTI JOIN read_parquet({frame}) f
            ON f.user_id = s.user_id AND f.item_id = s.item_id''').fetchone()[0]
    finally:
        con.close()
    xc.require(outside == 0, f'{outside} scored pairs are not rows of the kaggle frame')
    xc.require(set(scores['user_id'].astype(int)) == frame_users, 'Scores must cover exactly the kaggle frame users')
    ranked = rank_scores(scores, K)
    lists = {int(u): [int(x) for x in g['item_id']] for u, g in ranked.groupby('user_id')}
    filled = []
    for user, items in lists.items():
        if len(items) < K:
            have = set(items)
            for item in by_retailer.get(user_retailer.get(user), []) + glob:
                if len(items) == K:
                    break
                if item not in have:
                    items.append(item)
                    have.add(item)
            filled.append(user)
    fallback_list = glob[:K]
    xc.require(len(fallback_list) == K, 'The global order has fewer than K products')
    fallback_set = set(fallback)
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_name(output.name+'.part')
    xc.require(not part.exists(), f'{part} exists')
    with part.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('Id,Predicted\n')
        for user in ids:
            if user in lists:
                items = lists[user]
            else:
                xc.require(user in fallback_set, f'Id {user} has neither scores nor a fallback')
                items = fallback_list
            stream.write(f'{user},{" ".join(str(x) for x in items)}\n')
    try:
        check = check_submission(part, ids, known, K)
    except Exception:
        part.unlink()
        raise
    os.replace(part, output)
    record = dict(format=RECEIPT_FORMAT, dataset=DATASET, file=output.name, sha256=xc.sha256_file(output),
                  rows=check['rows'], scoring=len(lists), fallback=len([u for u in ids if u not in lists]),
                  filled=len(filled), fallback_items=fallback_list, filled_users=sorted(filled)[:1000],
                  collection=collection.name, collection_manifest_sha256=xc.sha256_file(collection/xc.MANIFEST_FILE),
                  collection_created_utc=manifest.get('created_utc'), created_utc=xc.utc_now())
    xc.atomic_json(receipt, record)
    return record


# ---------------------------------------------------------------- probe (common 3, doc 6.4)

def probe_pool(size=PROBE_USERS):
    """Users with an order before the probe anchor, the first ``size`` in query order."""
    con = history(PROBE_ANCHOR, 'probe', xc.THREADS['probe'])
    try:
        con.execute('CREATE TEMP TABLE known AS SELECT DISTINCT user_id FROM orders')
        return _query_order(con, 'known', size)
    finally:
        con.close()


def _r(value, digits=4):
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value):
        return None
    rounded = round(value, digits)
    return int(rounded) if rounded.is_integer() else rounded


def probe_stats(A, users, base=None, threads=xc.THREADS['probe']):
    """Label-free aggregates of the history before A for stats.json (doc 6.4); no ids, no time range."""
    A = _date(A)
    if base is None:
        path = xc.config_path(DATASET, 'base')
        base = xc.read_base(path) if path.exists() else initial_base()
    policy = _policy(base)
    a = _ts(A)
    con = history(A, 'probe', threads)
    try:
        def window(days):
            return f'ts >= {a} - INTERVAL {days} DAY'
        windows = {}
        for label, condition in (('last_14_days', window(14)), ('last_28_days', window(28)),
                                 ('last_90_days', window(90)), ('all_history', 'true')):
            lines, products = con.execute(f'SELECT count(*), count(DISTINCT product_id) FROM lines WHERE {condition}'
                                          ).fetchone()
            orders, users_n = con.execute(f'SELECT count(*), count(DISTINCT user_id) FROM orders WHERE {condition}'
                                          ).fetchone()
            windows[label] = dict(lines=int(lines), orders=int(orders), users=int(users_n), products=int(products))
        r = con.execute(f'''SELECT count(*), avg(n), quantile_cont(n, [0.1, 0.25, 0.5, 0.75, 0.9, 0.99]), max(n),
            avg(CASE WHEN n >= 2 THEN 1.0 ELSE 0.0 END) FROM (SELECT user_id, count(*) AS n FROM orders
            WHERE {window(90)} GROUP BY 1)''').fetchone()
        qs = ('p10', 'p25', 'p50', 'p75', 'p90', 'p99')
        per_user = dict(users=int(r[0]), mean=_r(r[1]), **{q: _r(v) for q, v in zip(qs, r[2] or [None]*6)},
                        max=None if r[3] is None else int(r[3]))
        repeat_share = _r(r[4])
        r = con.execute('''SELECT avg(n), quantile_cont(n, [0.1, 0.25, 0.5, 0.75, 0.9, 0.99]), max(n) FROM (
            SELECT order_id, count(DISTINCT product_id) AS n FROM lines GROUP BY 1)''').fetchone()
        basket = dict(mean=_r(r[0]), **{q: _r(v) for q, v in zip(qs, r[1] or [None]*6)},
                      max=None if r[2] is None else int(r[2]))
        r = con.execute('''SELECT min(price), quantile_cont(price, [0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99]), max(price)
            FROM lines''').fetchone()
        pq = ('p01', 'p10', 'p25', 'p50', 'p75', 'p90', 'p99')
        price = dict(min=_r(r[0]), **{q: _r(v) for q, v in zip(pq, r[1] or [None]*7)}, max=_r(r[2]))
        platforms = con.execute('SELECT platform, count(*) FROM orders GROUP BY 1 ORDER BY 1').fetchall()
        total = sum(n for _, n in platforms) or 1
        retailers = con.execute('SELECT count(DISTINCT retailer) FROM orders').fetchone()[0]
        top_r = con.execute(f'''SELECT retailer, count(*) AS n FROM orders WHERE {window(28)} GROUP BY 1
            ORDER BY n DESC, retailer LIMIT 10''').fetchall()
        cities = con.execute('SELECT count(DISTINCT city_name) FROM orders').fetchone()[0]
        cats = con.execute('SELECT count(DISTINCT master_category_id) FROM lines').fetchone()[0]
        top_c = con.execute(f'''SELECT l.master_category_id, c.name, count(*) AS n FROM lines l
            LEFT JOIN st.categories c ON c.id = l.master_category_id
            WHERE {window(28)} AND l.master_category_id IS NOT NULL GROUP BY 1, 2
            ORDER BY n DESC, l.master_category_id LIMIT 10''').fetchall()
        null_cat, null_brand = con.execute('''SELECT avg(CASE WHEN master_category_id IS NULL THEN 1.0 ELSE 0.0 END),
            avg(CASE WHEN brand_name IS NULL THEN 1.0 ELSE 0.0 END) FROM lines''').fetchone()
        _anchor_tables(con, A, policy['window_days'])
        users = sorted({int(u) for u in users})
        _register_users(con, 'cu', users)
        _user_tables(con, A)
        _candidates(con, policy)
        n_users, a_n, b_n, c_n = con.execute('''SELECT count(DISTINCT user_id), count(*) FILTER (WHERE src = 1),
            count(*) FILTER (WHERE src = 2), count(*) FILTER (WHERE src = 3) FROM c_cand''').fetchone()
    finally:
        con.close()
    denominator = n_users or 1
    stats = dict(
        windows=windows,
        orders_per_user_last_90_days=per_user,
        users_with_2_or_more_orders_last_90_days_share=repeat_share,
        distinct_products_per_order=basket,
        line_price=price,
        platform_share_of_orders={str(p): _r(n/total) for p, n in platforms},
        retailers=dict(count=int(retailers), top_by_orders_last_28_days=[[str(c), int(n)] for c, n in top_r]),
        cities=dict(count=int(cities)),
        categories=dict(count=int(cats),
                        top_by_lines_last_28_days=[[int(i), None if nm is None else str(nm), int(n)]
                                                   for i, nm, n in top_c],
                        null_category_line_share=_r(null_cat), null_brand_line_share=_r(null_brand)),
        candidates=dict(users=int(n_users), per_user_mean=dict(repeat=_r(a_n/denominator),
                                                               pop_retailer=_r(b_n/denominator),
                                                               global_=_r(c_n/denominator))))
    stats['candidates']['per_user_mean']['global'] = stats['candidates']['per_user_mean'].pop('global_')
    text = json.dumps(stats, ensure_ascii=False)
    xc.require(not re.search(r'[0-9]{9,}', text), 'stats.json would carry an id-shaped number')
    return stats


def coverage_sources():
    """Source-rank columns behind the H&M coverage fields: (a) -> recent, (b) and (c) -> global.

    The exact entering source of each candidate is ``sources.parquet`` of the collection.
    """
    return {'recent': ['repeat_rank'], 'global': ['popr_rank', 'glob_rank']}


# ---------------------------------------------------------------- prompt template (common 3, doc 6.5)

PROMPT_TEMPLATE = """You are a feature engineer for a ranking model. Reply with JSON only.

TASK
Orders of a grocery delivery service. Every anchor A is a midnight. A query is a user with at least one order
before A and at least one order in [A, A + {W} days). The target of a query is the set of distinct products of the
user's first order in that window (earliest ts, then smallest order_id); products the user bought before count too.
The label of a (user, product) candidate pair is whether the product is in the target. The metric is MAP@{K}:
AP@{K} = (1 / min({K}, M)) * sum over positions k = 1..{K} of rel_k * P@k, where M is the number of target products
(targets outside the candidates included), rel_k is 1 when the product at position k is a target, and P@k is the
number of targets among the first k positions divided by k; MAP@{K} is the mean AP@{K} over all queries.

CANDIDATES (policy {policy_name})
{candidates}

TRAINING
CatBoost Logloss, {trees} trees, depth {depth}, learning rate {learning_rate}, L2 {l2_leaf_reg}, {border_count}
borders, no tuning. Training anchors are {W} days apart; each contributes at most {N} queries: all positive pairs
plus {negatives} hash-sampled negatives per query, with inverse-inclusion weights. Candidates are ranked by the raw
model value, ties by product_id.

FEATURES ALREADY IN THE MODEL: the base (name: formula; missing). A window of w days is [A - w days, A).
{features}
Columns of earlier proposals with status valid are also in the model.

TABLES (DuckDB; a query sees only these five)
{tables}
orders: one row per order placed in the last {agent_days} days before A, [A - {agent_days} days, A), that has at
  least one product line; retailer and city_name are anonymised codes. Earlier orders are not visible to queries
  (the base features above use the whole history before A).
lines: every product line of those orders with the order's user_id and ts; a product can appear on several lines
  of one order (duplicate lines are kept).
order_id and line_item_id are shifted to the start of the window (their first value there is 0) and carry no
  absolute meaning; use them to tell orders and lines apart and to break ties of equal ts.
categories: the category tree; lines.master_category_id refers to categories.id.
cand(user_id BIGINT, product_id BIGINT): the candidate pairs of the current batch, keys only
users(user_id BIGINT): the distinct users of cand
There is no user table and no product attribute table.
Id columns (user_id, product_id, store_id, master_category_id, order_id, line_item_id, retailer, city_name) are
  labels: do not use their numeric value or order as a feature, only equality and joins.

QUERY RULES
- Exactly one SELECT or WITH statement; ';' only at the very end; no comments (-- or /* */).
- Write the anchor only as TIMESTAMP '{{A}}', literally with the braces, e.g.
  ts >= TIMESTAMP '{{A}}' - INTERVAL 28 DAY. No other {{...}} placeholders, no date or time literals
  ('YYYY-MM-DD...', DATE '...', TIMESTAMP '...' other than the anchor); intervals only as INTERVAL n DAY, unquoted.
- Times. A time value is the column ts of orders or lines, or a column of a WITH query or subquery that
  selects one; its min, max, first, last, arg_max/arg_min result, lag, lead, first_value or last_value;
  CAST(... AS DATE); date_trunc('day' | 'hour' | 'minute' | 'second' | 'week', ...); or such a value +/-
  INTERVAL n DAY. The anchor is TIMESTAMP '{{A}}' +/- INTERVAL n DAY. Nothing else is a time value: struct
  fields, values of other tables and anything built from text or numbers are not. A time value may only be:
  compared (=, <>, <, <=, >, >=, BETWEEN, IN, IS DISTINCT FROM) with another time value or the anchor;
  subtracted from another time value or the anchor (the difference is an interval, free to use, e.g.
  epoch(TIMESTAMP '{{A}}' - max(ts)) / 86400); passed with another time value or the anchor to date_diff or
  date_sub with 'week', 'day', 'hour', 'minute' or 'second'; reduced to a periodic part by date_part with dow,
  isodow, day (of the month), hour, minute or second (or dayofweek(), day(), hour() and the like); counted;
  used in ORDER BY, GROUP BY or PARTITION BY. A default of lag or lead must be a time value or the anchor
  (lead(ts, 1, TIMESTAMP '{{A}}')); for a numeric default wrap the result instead, e.g.
  COALESCE(date_diff('day', lag(ts) OVER (PARTITION BY user_id ORDER BY ts, order_id), ts), -1). The anchor
  itself has no parts: date_part, dayofweek() and the like of TIMESTAMP '{{A}}' are errors. A scalar subquery
  that returns a time value must name it ts or *_ts: (SELECT max(ts) AS last_ts FROM ...). All dates lie within
  one year, so month, quarter, week of the year and day of the year are absolute dates and are errors
  (date_part, month(), week(), dayofyear(), date_trunc('month' | 'quarter' | 'year', ...),
  date_diff('month', ...)). Anything else is an error too: epoch(ts), year, julian, strftime,
  CAST(ts AS VARCHAR), arithmetic on ts other than +/- INTERVAL n DAY,
  comparing ts with anything but a time value or the anchor, and any cast whose type contains DATE, TIME,
  TIMESTAMP or INTERVAL (STRUCT(x TIMESTAMP), lists and maps included), except ts to DATE or TIMESTAMP. A time
  value selected in a WITH query or subquery must be named ts or end in _ts, and only time values may carry
  such names; no WITH RECURSIVE, no column aliases in WITH name(...) or AS t(...), no table used as a value
  (SELECT o FROM orders o), no COLUMNS(...), no * RENAME, no positional #n, no $; every column must exist;
  column names have at most two parts (alias.column, not main.orders.ts). No lambdas (x -> ..., lambda x: ...,
  [y FOR y IN ...]) and no table functions in FROM (range, generate_series, unnest and the like); struct keys,
  STRUCT field names and named arguments may not be ts or *_ts. In a subquery whose FROM has users, cand,
  categories, VALUES or a subquery with unnamed columns, write the outer ts as alias.ts, with an alias not used
  in that FROM.
- Forbidden whole words, in any case: transactions, customers, frame, label, labels, target, targets, hm_*,
  _hm_*; read_*, parquet_*, csv, json*, glob, getenv, query, query_table, duckdb_*, information_schema,
  pg_catalog, sqlite_master, pragma*; attach, detach, copy, export, import, install, load, set, reset, use,
  call, create, drop, insert, update, delete, alter; random, setseed, uuid, gen_random_uuid, now, today,
  current_*, get_current_*, transaction_timestamp, localtimestamp, sample, tablesample, current_setting,
  sniff_*, checkpoint, force_checkpoint, which_secret; tab_*, sample_submission, product_name, propert*,
  profile, profiles, bdate, gender (also inside names joined by _); make_*, strptime, strftime, to_timestamp,
  to_date, to_days and the other to_<unit> interval functions, epoch_*, julian, yearweek, ago; the functions
  error(), strptime() and regexp_*(). Tables are named by plain names only (no quoted paths, no schemas).
- An item-level query must not mention cand or users: its values do not depend on the batch and are cached.

OUTPUT OF A QUERY
- level "pair": key columns user_id, product_id (pairs of cand); level "user": user_id (of users); level "item":
  product_id (of the products in lines). Keys are BIGINT, never NULL and unique. A key outside its set is an
  error, not a silent filter, so keep queries narrow.
- 1 to 3 value columns named by ^ag_[a-z][a-z0-9_]{{1,38}}$, unique among the accepted columns and different from
  every feature name above; integer, DECIMAL, FLOAT, DOUBLE or BOOLEAN. VARCHAR, DATE and TIMESTAMP values are
  errors: turn times into days before TIMESTAMP '{{A}}'. No other columns.
- Values are cast to DOUBLE and left-joined to the batch keys of the level. No row, NULL, a non-finite value or
  a float32 overflow mean "no data": NaN in the model, which CatBoost treats as the minimum. Put your own
  defaults with COALESCE.
- Batch invariance: a value depends only on orders, lines, categories and its own key; cand and users only
  filter. A window PARTITION BY user_id over cand is allowed (all {candidates_per_user} candidates of a user are
  always in one batch); aggregates over cand across users are not. Windows need a full tie-break
  (..., product_id). Violations are caught mechanically.
- Limits on the probe: timeout {timeout_pair_user} s for pair and user queries, {timeout_item} s for item queries;
  at most 20 million output rows. Budget of the whole set on the probe: valid pair and user proposals together
  at most {budget_pair_user} s, valid item proposals at most {budget_item} s; a proposal that does not fit into
  what is left gets status budget.

VALIDITY
A proposal is accepted or rejected as a whole. It is invalid on an SQL error, a broken rule or a timeout; when
a column has fewer than 2 distinct non-NULL values or fewer than 100 non-NULL rows; when a column has
|Spearman rho| >= 0.999 with a base feature, an accepted column or another column of the same proposal; or when
batch invariance fails.

PROBE STATISTICS (history before the probe anchor only)
{stats}

WARNING
""" + WARNING + """

EARLIER ATTEMPTS IN THIS RUN (validity and coverage on the probe; effects on labels are not shown)
{history}
Probe time budget left (rounded down to 10 s): pair+user about {budget_pair_user_left} s of {budget_pair_user} s;
item about {budget_item_left} s of {budget_item} s.

REQUEST
This is round {round} of {rounds}. Propose {proposals} new features that are likely to improve the ranking beyond
the base and the accepted columns and that differ from earlier attempts. Answer with a JSON list only:
[{{"name": "short_snake_case", "idea": "one sentence", "level": "pair|user|item", "sql": "SELECT ..."}}]
"""


def _number_text(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'null'
    if isinstance(value, (int, float)):
        return json.dumps(value)
    return ' '.join(str(value).split())


def _stats_lines(value, depth=0):
    """Indented plain text of stats.json in its own key order; numbers exactly as JSON writes them."""
    pad, lines = '  '*depth, []

    def inline(item):
        if isinstance(item, list):
            return '[' + ', '.join(inline(x) for x in item) + ']'
        if isinstance(item, dict):
            return '{' + ', '.join(f'{k}: {inline(v)}' for k, v in item.items()) + '}'
        return _number_text(item)

    def simple(item):
        if isinstance(item, dict):
            return all(not isinstance(v, (dict, list)) for v in item.values())
        if isinstance(item, list):
            return all(not isinstance(v, dict) for v in item)
        return True
    if isinstance(value, dict):
        for key, item in value.items():
            if simple(item):
                lines.append(f'{pad}{key}: {inline(item)}')
            else:
                lines.append(f'{pad}{key}:')
                lines.extend(_stats_lines(item, depth+1))
    else:
        lines.append(pad + inline(value))
    return lines


def _tens(seconds):
    return int(max(float(seconds), 0.0) // 10 * 10)


def prompt_substitutions(stats, base, history, round_index, budget):
    """Slot values of PROMPT_TEMPLATE.

    ``history`` is the feedback text rendered by xfer_agent; ``budget`` the probe
    seconds left, ``pair_user_seconds`` and ``item_seconds``. Formatter outputs here:
    ``round`` and the two ``*_left`` slots.
    """
    xc.require(isinstance(stats, dict) and stats, 'stats.json must be a non-empty object')
    xc.require(type(round_index) is int and round_index >= 1, 'round_index is a positive integer')
    xc.require(isinstance(budget, dict) and set(budget) == set(PROBE_BUDGET), 'budget needs pair_user_seconds and '
               'item_seconds')
    policy = _policy(base)
    cand = base['candidates']
    features = [f"- {f['name']}: {f['formula']}; missing: {f['missing']}" for f in base['features']]
    features.append('categorical: ' + (', '.join(base['categorical']) or '(none)'))
    tables = [f"{name}({', '.join(f'{c} {t}' for c, t in schema)})" for name, schema in VIEW_SCHEMA.items()]
    subs = {key: _number_text(value) for key, value in PROMPT_CONSTANTS.items()}
    subs.update(policy_name=str(cand.get('name')), candidates='\n'.join(cand.get('text') or []),
                candidates_per_user=str(policy['per_query']), features='\n'.join(features), tables='\n'.join(tables),
                stats='\n'.join(_stats_lines(stats)),
                history=(history.strip() if isinstance(history, str) and history.strip() else '(none yet)'),
                round=str(round_index), budget_pair_user_left=str(_tens(budget['pair_user_seconds'])),
                budget_item_left=str(_tens(budget['item_seconds'])))
    return subs


def render_prompt(stats, base, history, round_index, budget):
    return PROMPT_TEMPLATE.format(**prompt_substitutions(stats, base, history, round_index, budget))


def prompt_digest():
    return xc.canonical_digest(dict(template=PROMPT_TEMPLATE, constants=PROMPT_CONSTANTS))


# ---------------------------------------------------------------- CLI

def _handle(argv):
    xc.isolated()
    parser = argparse.ArgumentParser(prog='xfer_sber.py')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('load')
    p.add_argument('--raw', default=None)
    p.add_argument('--threads', type=int, default=xc.THREADS['collect'])
    p.add_argument('--memory', default='16GB')
    p = sub.add_parser('collect')
    p.add_argument('--role', required=True, choices=xc.ROLES)
    p.add_argument('--anchor', required=True)
    p.add_argument('--base', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--users-file', default=None)
    p.add_argument('--threads', type=int, default=xc.THREADS['collect'])
    args = parser.parse_args(argv)
    if args.command == 'load':
        report = load(args.raw or xc.raw_dir(DATASET), xc.output_dir(DATASET, 'load'), args.threads, args.memory)
        return dict(command='load', status=report['status'], seconds=report['seconds'],
                    events=report['facts']['events'])
    users = _read_users_file(args.users_file) if args.users_file else None
    manifest = collect(args.anchor, args.role, xc.read_base(args.base), Path(args.output), users=users,
                       threads=args.threads)
    return dict(command='collect', role=manifest['role'], anchor=manifest['anchor'], counts=manifest['counts'],
                output=str(Path(args.output).resolve()))


def main(argv=None):
    return xc.run_cli(_handle, argv)


if __name__ == '__main__':
    sys.exit(main())
