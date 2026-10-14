"""Bounded user-history EDA for the typed October ``events`` table.

All query results are aggregates. No user or product identifiers are exported.
The source event grain is retained unless a metric explicitly says otherwise.
"""

from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from time import perf_counter


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _query(connection, label, sql):
    started = perf_counter()
    print(f"[users] {label}: started", flush=True)
    cursor = connection.execute(sql)
    columns = [entry[0] for entry in cursor.description]
    result = [_json_value(dict(zip(columns, row))) for row in cursor.fetchall()]
    print(f"[users] {label}: {perf_counter() - started:.1f}s", flush=True)
    return result


def _execute(connection, label, sql):
    started = perf_counter()
    print(f"[users] {label}: started", flush=True)
    connection.execute(sql)
    print(f"[users] {label}: {perf_counter() - started:.1f}s", flush=True)


def run(connection, output_dir) -> dict:
    """Compute user, warm-history and view-to-purchase aggregate diagnostics.

    Assumes second-resolution UTC TIMESTAMP event_time. Strictly prior means
    event_time < prediction time; all same-second events are excluded.
    October is left/right censored: first-seen is only first seen in this file.
    This function writes one JSON artifact after every stage succeeds.
    """
    result = {
        "definitions": {
            "time_zone": "UTC",
            "user_population": "Rows with non-null user_id; counts include raw duplicate rows.",
            "observed_span": "last_seen - first_seen within October, not retention or lifetime.",
            "warm": "Entity has an event strictly before the reference timestamp in this file.",
            "cutoff_windows": "[cutoff, cutoff + 7 days), known iff first_seen < cutoff.",
            "cutoff_pairs": "Distinct user-product pairs with >=1 purchase row in that window.",
            "purchase_keys": "Distinct (user_id, product_id, event_time), not orders; order IDs absent.",
            "delay": "Seconds from nearest strictly earlier view of same user-product to purchase key.",
            "unmatched_delay": "No strictly earlier matching view observed in October; not proof of no exposure.",
            "delay_scope": "Across sessions; no horizon restriction; may match a view before an earlier purchase.",
            "same_second": "Same-second views/events do not qualify as earlier history.",
            "quantile_probabilities": [0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99],
        }
    }
    _execute(connection, "user summaries", """
        CREATE OR REPLACE TEMP TABLE _eda_users AS
        SELECT user_id, COUNT(*) AS n_events,
               COUNT(*) FILTER (WHERE event_type = 'view') AS n_views,
               COUNT(*) FILTER (WHERE event_type = 'cart') AS n_carts,
               COUNT(*) FILTER (WHERE event_type = 'purchase') AS n_purchases,
               COUNT(DISTINCT CAST(event_time AS DATE)) AS active_days,
               MIN(event_time) AS first_seen, MAX(event_time) AS last_seen,
               EPOCH(MAX(event_time) - MIN(event_time)) / 86400.0 AS observed_span_days
        FROM events WHERE user_id IS NOT NULL GROUP BY user_id
    """)
    result["user_summary"] = _query(connection, "user distributions", """
        SELECT COUNT(*) AS users, SUM(n_events) AS events_with_user,
               COUNT(*) FILTER (WHERE n_events = 1) AS users_one_event,
               COUNT(*) FILTER (WHERE active_days >= 2) AS users_two_or_more_active_days,
               COUNT(*) FILTER (WHERE active_days >= 7) AS users_seven_or_more_active_days,
               COUNT(*) FILTER (WHERE observed_span_days >= 1) AS users_span_at_least_one_day,
               COUNT(*) FILTER (WHERE observed_span_days >= 7) AS users_span_at_least_seven_days,
               COUNT(*) FILTER (WHERE n_purchases > 0) AS users_with_purchase,
               COUNT(*) FILTER (WHERE n_purchases > 1) AS users_with_multiple_purchase_rows,
               quantile_cont(n_events, [0.1,0.25,0.5,0.75,0.9,0.95,0.99]) AS event_quantiles,
               quantile_cont(active_days, [0.1,0.25,0.5,0.75,0.9,0.95,0.99]) AS active_day_quantiles,
               quantile_cont(observed_span_days, [0.1,0.25,0.5,0.75,0.9,0.95,0.99]) AS span_day_quantiles,
               quantile_cont(n_purchases, [0.1,0.25,0.5,0.75,0.9,0.95,0.99]) AS purchase_row_quantiles
        FROM _eda_users
    """)[0]
    result["user_event_bins"] = _query(connection, "event bins", """
        SELECT CASE WHEN n_events=1 THEN '01: 1' WHEN n_events<=5 THEN '02: 2-5'
                    WHEN n_events<=10 THEN '03: 6-10' WHEN n_events<=50 THEN '04: 11-50'
                    WHEN n_events<=100 THEN '05: 51-100' ELSE '06: 101+' END AS event_bin,
               COUNT(*) AS users, SUM(n_events) AS event_rows, SUM(n_purchases) AS purchase_rows
        FROM _eda_users GROUP BY event_bin ORDER BY event_bin
    """)
    result["daily_users"] = _query(connection, "daily returning users", """
        WITH days AS (
            SELECT DISTINCT user_id, CAST(event_time AS DATE) AS day
            FROM events WHERE user_id IS NOT NULL AND event_time IS NOT NULL
        )
        SELECT day, COUNT(*) AS active_users,
               COUNT(*) FILTER (WHERE CAST(u.first_seen AS DATE)=day) AS first_seen_users,
               COUNT(*) FILTER (WHERE CAST(u.first_seen AS DATE)<day) AS returning_observed_users
        FROM days JOIN _eda_users u USING(user_id) GROUP BY day ORDER BY day
    """)
    _execute(connection, "item first-seen", """
        CREATE OR REPLACE TEMP TABLE _eda_items AS
        SELECT product_id, MIN(event_time) AS first_seen
        FROM events WHERE product_id IS NOT NULL GROUP BY product_id
    """)
    result["warm_purchase_rows"] = _query(connection, "purchase warm entities", """
        SELECT COUNT(*) AS purchase_rows,
               COUNT(*) FILTER (WHERE u.first_seen < p.event_time) AS warm_user_rows,
               COUNT(*) FILTER (WHERE i.first_seen < p.event_time) AS warm_item_rows,
               COUNT(*) FILTER (WHERE u.first_seen < p.event_time AND i.first_seen < p.event_time) AS both_warm_rows,
               COUNT(*) FILTER (WHERE p.user_id IS NULL OR p.product_id IS NULL OR p.event_time IS NULL) AS missing_key_rows
        FROM events p LEFT JOIN _eda_users u USING(user_id)
                      LEFT JOIN _eda_items i USING(product_id)
        WHERE p.event_type='purchase'
    """)[0]
    result["pre_purchase_user_history"] = _query(connection, "strict prior user history", """
        WITH times AS (
            SELECT user_id, event_time, COUNT(*) AS n_events,
                   COUNT(*) FILTER (WHERE event_type='purchase') AS n_purchases
            FROM events WHERE user_id IS NOT NULL AND event_time IS NOT NULL
            GROUP BY user_id, event_time
        ), history AS (
            SELECT *, COALESCE(SUM(n_events) OVER (
                PARTITION BY user_id ORDER BY event_time
                RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL '1 second' PRECEDING
            ),0) AS prior_events
            FROM times
        )
        SELECT CASE WHEN prior_events=0 THEN '01: 0' WHEN prior_events<=5 THEN '02: 1-5'
                    WHEN prior_events<=10 THEN '03: 6-10' WHEN prior_events<=50 THEN '04: 11-50'
                    WHEN prior_events<=100 THEN '05: 51-100' ELSE '06: 101+' END AS prior_event_bin,
               SUM(n_purchases) AS purchase_rows, COUNT(*) AS user_purchase_timestamps
        FROM history WHERE n_purchases>0 GROUP BY prior_event_bin ORDER BY prior_event_bin
    """)
    result["cutoff_purchase_coverage"] = _query(connection, "weekly warm coverage", """
        WITH cutoffs(cutoff) AS (VALUES (TIMESTAMP '2019-10-08 00:00:00'),
                                      (TIMESTAMP '2019-10-15 00:00:00'),
                                      (TIMESTAMP '2019-10-22 00:00:00')),
        purchases AS (
            SELECT user_id, product_id, event_time, COUNT(*) AS raw_rows
            FROM events WHERE event_type='purchase'
              AND user_id IS NOT NULL AND product_id IS NOT NULL AND event_time IS NOT NULL
            GROUP BY user_id, product_id, event_time
        ), flagged AS (
            SELECT c.cutoff, p.*, u.first_seen<c.cutoff AS known_user,
                   i.first_seen<c.cutoff AS known_item
            FROM cutoffs c JOIN purchases p
              ON p.event_time>=c.cutoff AND p.event_time<c.cutoff+INTERVAL '7 days'
            JOIN _eda_users u USING(user_id) JOIN _eda_items i USING(product_id)
        )
        SELECT cutoff, known_user, known_item, SUM(raw_rows) AS raw_purchase_rows,
               COUNT(*) AS distinct_purchase_keys,
               COUNT(DISTINCT (user_id, product_id)) AS distinct_purchased_pairs,
               COUNT(DISTINCT user_id) AS distinct_purchasing_users
        FROM flagged GROUP BY cutoff, known_user, known_item
        ORDER BY cutoff, known_user, known_item
    """)
    result["view_to_purchase_delay"] = _query(connection, "nearest earlier view delays", """
        WITH purchases AS (
            SELECT user_id, product_id, event_time, COUNT(*) AS raw_rows
            FROM events WHERE event_type='purchase'
              AND user_id IS NOT NULL AND product_id IS NOT NULL AND event_time IS NOT NULL
            GROUP BY user_id, product_id, event_time
        ), views AS (
            SELECT user_id, product_id, event_time FROM events WHERE event_type='view'
              AND user_id IS NOT NULL AND product_id IS NOT NULL AND event_time IS NOT NULL
        ), matched AS (
            SELECT p.raw_rows, p.event_time, v.event_time AS view_time,
                   EPOCH(p.event_time-v.event_time) AS delay_seconds
            FROM purchases p ASOF LEFT JOIN views v
              ON p.user_id=v.user_id AND p.product_id=v.product_id AND p.event_time>v.event_time
        )
        SELECT COUNT(*) AS purchase_keys, SUM(raw_rows) AS raw_purchase_rows,
               COUNT(view_time) AS matched_purchase_keys,
               COUNT(*) FILTER (WHERE view_time IS NULL) AS unmatched_purchase_keys,
               SUM(raw_rows) FILTER (WHERE view_time IS NOT NULL) AS matched_raw_purchase_rows,
               AVG(delay_seconds) AS mean_delay_seconds_matched_keys,
               quantile_cont(delay_seconds,[0.1,0.25,0.5,0.75,0.9,0.95,0.99]) AS delay_seconds_quantiles_matched_keys,
               COUNT(*) FILTER (WHERE delay_seconds<=3600) AS matched_within_one_hour,
               COUNT(*) FILTER (WHERE delay_seconds<=86400) AS matched_within_one_day,
               COUNT(*) FILTER (WHERE delay_seconds<=604800) AS matched_within_seven_days
        FROM matched
    """)[0]
    _execute(connection, "release summaries", "DROP TABLE _eda_users; DROP TABLE _eda_items;")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "users.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return result
