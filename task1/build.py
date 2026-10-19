"""Build per-day ranking tables: queries, candidates, labels and manual features.

Protocol (same as the earlier study): at each day t 00:00 UTC we rank purchases of the
next 24 hours for users active in [t-48h, t). Candidates are the 200 items with the most
distinct buyers in [t-7d, t) plus the user's 20 most recent distinct items in [t-7d, t).
Every feature reads only the view `hist` = events strictly before t.

Only queries with at least one purchase in the horizon are kept: NDCG/Recall are averaged
over such queries anyway, and queries without purchases carry no ranking signal.
"""
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'data/processed/october.duckdb'
OUT = ROOT / 'artifacts/task1/days'


def connect(threads=8):
    con = duckdb.connect()
    con.execute(f"SET threads={threads}")
    con.execute(f"ATTACH '{DB}' AS src (READ_ONLY)")
    return con


def set_anchor(con, t, max_queries=None, seed=2026):
    """Create temp tables for anchor t: hist, queries, labels, candidates."""
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW hist AS
        SELECT * FROM src.events WHERE event_time < TIMESTAMP '{t}';
        CREATE OR REPLACE TEMP TABLE labels AS
        SELECT DISTINCT user_id, product_id FROM src.events
        WHERE event_type='purchase' AND event_time >= TIMESTAMP '{t}'
          AND event_time < TIMESTAMP '{t}' + INTERVAL 24 HOUR;
        CREATE OR REPLACE TEMP TABLE queries AS
        WITH active AS (
            SELECT DISTINCT user_id FROM hist WHERE event_time >= TIMESTAMP '{t}' - INTERVAL 48 HOUR),
        buyers AS (SELECT user_id, count(*) n_targets FROM labels GROUP BY user_id)
        SELECT a.user_id, b.n_targets FROM active a JOIN buyers b USING(user_id)
        ORDER BY hash(a.user_id, {seed}) {'LIMIT ' + str(max_queries) if max_queries else ''};
        CREATE OR REPLACE TEMP TABLE popular AS
        SELECT product_id, count(DISTINCT user_id) AS pop_buyers_7d,
               row_number() OVER (ORDER BY count(DISTINCT user_id) DESC, product_id) AS pop_rank
        FROM hist WHERE event_type='purchase' AND event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY
        GROUP BY product_id QUALIFY pop_rank <= 200;
        CREATE OR REPLACE TEMP TABLE recent AS
        SELECT user_id, product_id,
               row_number() OVER (PARTITION BY user_id ORDER BY max(event_time) DESC, product_id) AS rec_rank
        FROM hist SEMI JOIN queries USING(user_id)
        WHERE event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY
        GROUP BY user_id, product_id QUALIFY rec_rank <= 20;
        CREATE OR REPLACE TEMP TABLE candidates AS
        SELECT coalesce(p.user_id, r.user_id) user_id, coalesce(p.product_id, r.product_id) product_id,
               p.pop_rank, p.pop_buyers_7d, r.rec_rank
        FROM (SELECT q.user_id, pp.* FROM queries q CROSS JOIN popular pp) p
        FULL OUTER JOIN recent r USING(user_id, product_id);
    """)


MANUAL_SQL = """
WITH
u AS (
    SELECT user_id,
        count(*) FILTER (event_type='view') AS user_view_7d,
        count(*) FILTER (event_type='cart') AS user_cart_7d,
        count(*) FILTER (event_type='purchase') AS user_purchase_7d,
        count(DISTINCT product_id) FILTER (event_type='view') AS user_distinct_viewed_items_7d
    FROM hist SEMI JOIN queries USING(user_id)
    WHERE event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY GROUP BY user_id),
pair AS (
    SELECT user_id, product_id,
        count(*) FILTER (event_type='view' AND event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY) AS pair_view_7d,
        count(*) FILTER (event_type='cart' AND event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY) AS pair_cart_7d,
        count(*) FILTER (event_type='purchase' AND event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY) AS pair_purchase_7d,
        max(event_time) FILTER (event_type='view') AS last_view,
        max(event_time) FILTER (event_type='purchase') AS last_purchase,
        max(event_time) AS last_any
    FROM hist SEMI JOIN candidates USING(user_id, product_id) GROUP BY user_id, product_id),
items AS (SELECT DISTINCT product_id FROM candidates),
i AS (
    SELECT product_id,
        count(*) FILTER (event_type='view' AND event_time >= TIMESTAMP '{t}' - INTERVAL 24 HOUR) AS item_view_24h,
        count(*) FILTER (event_type='purchase' AND event_time >= TIMESTAMP '{t}' - INTERVAL 24 HOUR) AS item_purchase_24h,
        count(DISTINCT user_id) FILTER (event_type='view' AND event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY) AS item_distinct_viewers_7d,
        count(*) FILTER (event_type='view' AND event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY) AS item_view_7d,
        arg_max(category_id, event_time) AS cat
    FROM hist SEMI JOIN items USING(product_id) GROUP BY product_id),
ic AS (
    SELECT e.product_id, count(*) AS item_category_view_7d
    FROM hist e JOIN i ON e.product_id=i.product_id AND e.category_id=i.cat
    WHERE e.event_type='view' AND e.event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY GROUP BY e.product_id),
c AS (
    SELECT category_id AS cat, count(*) AS category_view_7d FROM hist
    WHERE event_type='view' AND event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY
      AND category_id IN (SELECT cat FROM i) GROUP BY category_id),
uc AS (
    SELECT user_id, category_id AS cat,
        count(*) FILTER (event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY) AS user_category_view_7d,
        max(event_time) AS last_cat_view
    FROM hist SEMI JOIN queries USING(user_id) WHERE event_type='view' GROUP BY user_id, category_id)
SELECT DATE '{day}' AS anchor, k.user_id, k.product_id,
    (l.user_id IS NOT NULL)::INT AS label, q.n_targets,
    (k.pop_rank IS NOT NULL)::INT AS f_from_popular, k.pop_rank AS f_pop_rank, k.pop_buyers_7d AS f_pop_buyers_7d,
    (k.rec_rank IS NOT NULL)::INT AS f_from_recent, k.rec_rank AS f_rec_rank,
    coalesce(u.user_view_7d,0) f_user_view_7d, coalesce(u.user_cart_7d,0) f_user_cart_7d,
    coalesce(u.user_purchase_7d,0) f_user_purchase_7d,
    coalesce(u.user_distinct_viewed_items_7d,0) f_user_distinct_viewed_items_7d,
    coalesce(pair.pair_view_7d,0) f_pair_view_7d, coalesce(pair.pair_cart_7d,0) f_pair_cart_7d,
    coalesce(pair.pair_purchase_7d,0) f_pair_purchase_7d,
    epoch(TIMESTAMP '{t}' - pair.last_view) f_pair_view_recency_s,
    epoch(TIMESTAMP '{t}' - pair.last_purchase) f_pair_purchase_recency_s,
    epoch(TIMESTAMP '{t}' - pair.last_any) f_pair_any_recency_s,
    coalesce(i.item_view_24h,0) f_item_view_24h, coalesce(i.item_purchase_24h,0) f_item_purchase_24h,
    coalesce(i.item_distinct_viewers_7d,0) f_item_distinct_viewers_7d,
    coalesce(uc.user_category_view_7d,0) f_user_category_view_7d,
    coalesce(uc.user_category_view_7d,0) / nullif(u.user_view_7d,0) f_user_category_view_share_7d,
    epoch(TIMESTAMP '{t}' - uc.last_cat_view) f_user_category_view_recency_s,
    coalesce(ic.item_category_view_7d,0) f_item_category_view_7d,
    c.category_view_7d f_category_view_7d,
    ic.item_category_view_7d / nullif(c.category_view_7d,0) f_item_category_view_share_7d
FROM candidates k
JOIN queries q USING(user_id)
LEFT JOIN labels l USING(user_id, product_id)
LEFT JOIN u USING(user_id)
LEFT JOIN pair USING(user_id, product_id)
LEFT JOIN i USING(product_id)
LEFT JOIN ic USING(product_id)
LEFT JOIN c ON c.cat=i.cat
LEFT JOIN uc ON uc.user_id=k.user_id AND uc.cat=i.cat
"""


def build_day(con, day, max_queries=None, out=OUT):
    t = datetime.combine(day, datetime.min.time()).isoformat(sep=' ')
    set_anchor(con, t, max_queries)
    path = out / f'{day.isoformat()}.parquet'
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({MANUAL_SQL.format(t=t, day=day.isoformat())}) TO '{path}' (FORMAT PARQUET)")
    stats = con.execute(f"""SELECT count(DISTINCT user_id), count(*), sum(label),
        (SELECT sum(n_targets) FROM queries) FROM read_parquet('{path}')""").fetchone()
    return dict(day=day.isoformat(), queries=stats[0], pairs=stats[1], hits=stats[2], targets=stats[3])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True, type=date.fromisoformat)
    ap.add_argument('--end', required=True, type=date.fromisoformat, help='inclusive')
    ap.add_argument('--max-queries', type=int, help='cap of purchasing users per day (default: all)')
    ap.add_argument('--threads', type=int, default=8)
    args = ap.parse_args()
    con = connect(args.threads)
    day = args.start
    while day <= args.end:
        s = build_day(con, day, args.max_queries)
        print(s, f"candidate recall {s['hits'] / s['targets']:.3f}", flush=True)
        day += timedelta(days=1)


if __name__ == '__main__':
    main()
