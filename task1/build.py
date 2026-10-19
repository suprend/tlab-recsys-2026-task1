"""Build per-day ranking tables for the new-item target: queries, labels, candidates and features.

Protocol (docs/task1-baseline-features.md). Anchor t = 00:00 UTC. Queries are users active in
[t-48h, t) with at least one target. A target is the user's first cart or purchase, in [t, t+24h),
of a product the user never touched before t (history starts 2019-10-01). Candidates come from four
sources and exclude every product the user touched before t:
  1. the 100 products with most distinct cart/purchase users in [t-7d, t);
  2. the top 30 of each of the user's 3 heaviest categories (decayed weight over [t-14d, t));
  3. the top 20 of each of the user's 2 heaviest brands;
  4. the 10 strongest session co-view neighbours (n_ab >= 2, [t-14d, t)) of the user's 10 latest views.
Source ranks are taken before the exclusion of touched products.

Every feature reads only schema `fs`: `hist` (events strictly before t), `pf` (pair_first as of t)
and the item tables; `labels` and `queries` read `src` in [t, t+24h) only to choose who is ranked and
what is correct. task1.leakcheck verifies this by pointing `fs` at a database cut at t.

Splits (by anchor day): train 2019-10-15..11-07, val 11-08..11-13, test 11-18..11-28. Days 11-14..11-17
are not anchors: a sale (views x3) and 11-15 has no purchase events at all. Cart logging changes level
on 10-28 (~33k -> ~18k a day) and on 11-08 (-> ~70k); purchases stay at 21-25k.

Run: .venv/bin/python -m task1.build --start 2019-10-15 --end 2019-11-28
"""
import argparse
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'data/processed/rees46.duckdb'
OUT = ROOT / 'artifacts/task1/v2/days'


FS_TABLES = ['events', 'pair_first', 'item_static', 'item_brand_day']


def connect(threads=10, features_db=None):
    """`src` serves labels and queries; `fs` serves features. They are the same database unless the
    leak test (task1.leakcheck) passes a features_db that holds only events before the anchor."""
    con = duckdb.connect()
    con.execute(f"SET threads={threads}; SET memory_limit='20GB'")
    con.execute(f"ATTACH '{DB}' AS src (READ_ONLY)")
    if features_db:
        con.execute(f"ATTACH '{features_db}' AS fs (READ_ONLY)")
    else:
        con.execute('CREATE SCHEMA fs')
        for t in FS_TABLES:
            con.execute(f'CREATE VIEW fs.{t} AS SELECT * FROM src.{t}')
    return con


def sql(text, t):
    """Substitute the anchor: {T} timestamp literal, {D} date literal."""
    return text.replace('{T}', f"TIMESTAMP '{t}'").replace('{D}', f"DATE '{t[:10]}'")


ANCHOR = """
CREATE OR REPLACE TEMP VIEW hist AS SELECT * FROM fs.events WHERE event_time < {T};
CREATE OR REPLACE TEMP TABLE w AS SELECT * FROM hist WHERE event_time >= {T} - INTERVAL 14 DAY;
CREATE OR REPLACE TEMP VIEW pf AS
  SELECT user_id, product_id, first_ts, CASE WHEN first_cp_ts < {T} THEN first_cp_ts END first_cp_ts
  FROM fs.pair_first WHERE first_ts < {T};
CREATE OR REPLACE TEMP TABLE labels AS
  SELECT p.user_id, p.product_id,
    EXISTS (SELECT 1 FROM src.events e WHERE e.user_id = p.user_id AND e.product_id = p.product_id
            AND e.event_type = 'purchase' AND e.event_time >= {T} AND e.event_time < {T} + INTERVAL 24 HOUR)::INT is_purchase
  FROM src.pair_first p
  WHERE p.first_ts >= {T} AND p.first_cp_ts >= {T} AND p.first_cp_ts < {T} + INTERVAL 24 HOUR
    AND p.user_id IN (SELECT DISTINCT user_id FROM w WHERE event_time >= {T} - INTERVAL 48 HOUR);
CREATE OR REPLACE TEMP TABLE queries AS
  SELECT user_id, count(*) n_targets, sum(is_purchase)::INT n_targets_purchase FROM labels GROUP BY 1
  ORDER BY hash(user_id, 2026) {LIMIT};
CREATE OR REPLACE TEMP TABLE uev AS SELECT * FROM w SEMI JOIN queries USING(user_id);
CREATE OR REPLACE TEMP TABLE touched AS SELECT user_id, product_id FROM pf SEMI JOIN queries USING(user_id);
CREATE OR REPLACE TEMP TABLE ibrand AS
  SELECT product_id, arg_max(brand, d) brand FROM fs.item_brand_day WHERE d < {D} GROUP BY 1;
CREATE OR REPLACE TEMP TABLE iattr AS
  SELECT s.product_id, s.category_id cat, s.l1, b.brand FROM fs.item_static s LEFT JOIN ibrand b USING(product_id);

-- item counters over the 14-day window (all products, all users)
CREATE OR REPLACE TEMP TABLE it AS SELECT product_id,
  count(DISTINCT user_id) FILTER (event_type IN ('cart','purchase') AND event_time >= {T} - INTERVAL 7 DAY) a7,
  count(DISTINCT user_id) FILTER (event_type IN ('cart','purchase') AND event_time >= {T} - INTERVAL 1 DAY) a1,
  count(DISTINCT user_id) FILTER (event_type IN ('cart','purchase')) a14,
  count(DISTINCT user_id) FILTER (event_type = 'view' AND event_time >= {T} - INTERVAL 1 DAY) v1,
  count(DISTINCT user_id) FILTER (event_type = 'view' AND event_time >= {T} - INTERVAL 7 DAY) v7,
  count(DISTINCT user_id) FILTER (event_type = 'view') v14,
  count(DISTINCT user_id) FILTER (event_type = 'purchase') b14,
  count(DISTINCT user_id) FILTER (event_type = 'cart' AND event_time >= {T} - INTERVAL 7 DAY) c7,
  max(event_time) FILTER (event_type = 'view') last_view,
  bool_or(event_time >= {T} - INTERVAL 7 DAY) seen7, bool_or(event_time < {T} - INTERVAL 7 DAY) seen_prev7
  FROM w GROUP BY 1;

-- candidate sources
CREATE OR REPLACE TEMP TABLE pop AS SELECT product_id, row_number() OVER (ORDER BY a7 DESC, product_id) pop_rank
  FROM it WHERE a7 > 0 QUALIFY pop_rank <= 100;
CREATE OR REPLACE TEMP TABLE uw AS SELECT e.user_id, e.product_id, e.event_type, e.event_time, e.price, e.user_session,
  a.cat, a.l1, a.brand,
  (CASE e.event_type WHEN 'view' THEN 1 WHEN 'cart' THEN 3 ELSE 10 END) * pow(0.5, epoch({T} - e.event_time) / 86400) wt
  FROM uev e JOIN iattr a USING(product_id);
CREATE OR REPLACE TEMP TABLE utot AS SELECT user_id, sum(wt) tot FROM uw GROUP BY 1;
CREATE OR REPLACE TEMP TABLE ucw AS SELECT user_id, cat, round(sum(wt), 9) w, max(event_time) last_ts,
  max(event_time) FILTER (event_type IN ('cart','purchase')) last_cp_ts,
  max(event_time) FILTER (event_type = 'purchase') last_purchase_ts,
  count(DISTINCT event_time::DATE) active_days,
  count(*) FILTER (event_type = 'view' AND event_time >= {T} - INTERVAL 7 DAY) n_view_7d
  FROM uw GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE ubw AS SELECT user_id, brand, round(sum(wt), 9) w, max(event_time) last_ts
  FROM uw WHERE brand IS NOT NULL GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE catpop AS SELECT a.cat, it.product_id,
  row_number() OVER (PARTITION BY a.cat ORDER BY it.a7 DESC, it.product_id) cat_rank
  FROM it JOIN iattr a USING(product_id) WHERE it.a7 > 0 QUALIFY cat_rank <= 30;
CREATE OR REPLACE TEMP TABLE brandpop AS SELECT a.brand, it.product_id,
  row_number() OVER (PARTITION BY a.brand ORDER BY it.a7 DESC, it.product_id) brand_rank
  FROM it JOIN iattr a USING(product_id) WHERE it.a7 > 0 AND a.brand IS NOT NULL QUALIFY brand_rank <= 20;
CREATE OR REPLACE TEMP TABLE rv AS SELECT user_id, product_id, max(event_time) last_ts,
  arg_max(price, (event_time, price)) price_seen,
  row_number() OVER (PARTITION BY user_id ORDER BY max(event_time) DESC, product_id) k
  FROM uev WHERE event_type = 'view' GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE sv AS SELECT DISTINCT user_session s, product_id FROM w
  WHERE event_type = 'view' AND user_session IS NOT NULL;
CREATE OR REPLACE TEMP TABLE ns AS SELECT product_id, count(*) n FROM sv GROUP BY 1;
-- nb: full neighbour list of recent items with ranks; cor: links (n_ab >= 2) used by source 4 and cf_cv_*
CREATE OR REPLACE TEMP TABLE nb AS
  WITH s2 AS (SELECT sv.* FROM sv JOIN (SELECT s FROM sv GROUP BY s HAVING count(*) BETWEEN 2 AND 50) USING(s))
  SELECT x.product_id a, y.product_id b, count(*) n_ab,
    row_number() OVER (PARTITION BY x.product_id ORDER BY count(*) DESC, y.product_id) rk
  FROM s2 x JOIN s2 y ON x.s = y.s AND x.product_id <> y.product_id
  WHERE x.product_id IN (SELECT product_id FROM rv WHERE k <= 10)
  GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE cor AS SELECT * FROM nb WHERE n_ab >= 2;
CREATE OR REPLACE TEMP TABLE candidates AS
  WITH s AS (
    SELECT q.user_id, p.product_id, p.pop_rank, NULL::BIGINT cat_rank, NULL::BIGINT brand_rank, 0 src4 FROM queries q CROSS JOIN pop p
    UNION ALL
    SELECT c.user_id, cp.product_id, NULL, cp.cat_rank, NULL, 0 FROM
      (SELECT user_id, cat FROM ucw QUALIFY row_number() OVER (PARTITION BY user_id ORDER BY w DESC, cat) <= 3) c
      JOIN catpop cp USING(cat)
    UNION ALL
    SELECT b.user_id, bp.product_id, NULL, NULL, bp.brand_rank, 0 FROM
      (SELECT user_id, brand FROM ubw QUALIFY row_number() OVER (PARTITION BY user_id ORDER BY w DESC, brand) <= 2) b
      JOIN brandpop bp USING(brand)
    UNION ALL
    SELECT r.user_id, c.b, NULL, NULL, NULL, 1 FROM rv r JOIN cor c ON c.a = r.product_id AND c.rk <= 10 WHERE r.k <= 10)
  SELECT user_id, product_id, min(pop_rank) pop_rank, min(cat_rank) cat_rank, min(brand_rank) brand_rank, max(src4) src4
  FROM s WHERE NOT EXISTS (SELECT 1 FROM touched x WHERE x.user_id = s.user_id AND x.product_id = s.product_id)
  GROUP BY 1, 2;
"""

FEATURES = """
-- global normalisers (all products, all users of the window)
CREATE OR REPLACE TEMP TABLE acq_all AS SELECT user_id, product_id, first_ts, first_cp_ts FROM pf
  WHERE first_ts >= {T} - INTERVAL 14 DAY AND first_cp_ts IS NOT NULL AND first_ts::DATE = first_cp_ts::DATE;
CREATE OR REPLACE TEMP TABLE iacq AS SELECT p.product_id, count(*) new_users,
  count(*) FILTER (p.first_cp_ts IS NOT NULL AND p.first_ts::DATE = p.first_cp_ts::DATE) acq,
  count(*) FILTER (p.first_cp_ts IS NOT NULL AND p.first_ts::DATE = p.first_cp_ts::DATE AND p.first_ts >= {T} - INTERVAL 1 DAY) acq1,
  count(*) FILTER (p.first_cp_ts IS NOT NULL AND p.first_ts::DATE = p.first_cp_ts::DATE AND p.first_ts >= {T} - INTERVAL 7 DAY) acq7
  FROM pf p WHERE p.first_ts >= {T} - INTERVAL 14 DAY GROUP BY 1;
CREATE OR REPLACE TEMP TABLE gnorm AS SELECT
  (SELECT sum(a7) FROM it) sum_a7,
  (SELECT sum(b14) / sum(v14) FROM it) p_buy,
  (SELECT sum(c7) / sum(v7) FROM it) p_cart,
  (SELECT sum(acq) / sum(new_users) FROM iacq) p_acq_rate,
  (SELECT sum(coalesce(i.acq, 0)) / sum(t.a14) FROM it t LEFT JOIN iacq i USING(product_id) WHERE t.a14 > 0) p_acq_share,
  (SELECT count(DISTINCT user_id) FROM w WHERE event_type = 'view') n_viewers;

-- item price as of t: last positive price of any event; dynamics from daily medians of view prices
CREATE OR REPLACE TEMP TABLE ilast AS SELECT product_id, arg_max(price, (event_time, price)) p_last FROM w
  WHERE price > 0 GROUP BY 1;
CREATE OR REPLACE TEMP TABLE dprice AS SELECT product_id, event_time::DATE d, median(price) p FROM w
  WHERE event_type = 'view' AND price > 0 GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE iprice AS SELECT product_id, arg_max(p, d) p_last, max(p) p_max, count(*) n_days,
  median(p) FILTER (d >= {D} - 7) p_med7, count(*) FILTER (d >= {D} - 7) n_days7
  FROM dprice GROUP BY 1;
CREATE OR REPLACE TEMP TABLE ipct AS SELECT i.product_id, i.p_last,
  CASE WHEN count(*) OVER (PARTITION BY a.cat) >= 5 THEN percent_rank() OVER (PARTITION BY a.cat ORDER BY i.p_last) END pct
  FROM ilast i JOIN iattr a USING(product_id);
CREATE OR REPLACE TEMP TABLE irep AS SELECT product_id, count(*) buyers, count(*) FILTER (nd >= 2) rep FROM
  (SELECT user_id, product_id, count(DISTINCT event_time::DATE) nd FROM w WHERE event_type = 'purchase' GROUP BY 1, 2) GROUP BY 1;

-- category and brand counters
CREATE OR REPLACE TEMP TABLE wa AS SELECT w.user_id, w.event_type, w.event_time, w.product_id, a.cat, a.brand
  FROM w JOIN iattr a USING(product_id);
CREATE OR REPLACE TEMP TABLE ct AS SELECT cat,
  count(DISTINCT user_id) FILTER (event_type IN ('cart','purchase') AND event_time >= {T} - INTERVAL 7 DAY) a7,
  count(DISTINCT user_id) FILTER (event_type = 'view' AND event_time >= {T} - INTERVAL 1 DAY) v1,
  count(DISTINCT user_id) FILTER (event_type = 'view' AND event_time >= {T} - INTERVAL 7 DAY) v7,
  count(DISTINCT user_id) FILTER (event_type = 'view') v14,
  count(DISTINCT user_id) FILTER (event_type = 'purchase') b14
  FROM wa GROUP BY 1;
CREATE OR REPLACE TEMP TABLE cnorm AS SELECT sum(b14) / sum(v14) p_buy FROM ct;
CREATE OR REPLACE TEMP TABLE csum AS SELECT a.cat, sum(it.a7) a7 FROM it JOIN iattr a USING(product_id) GROUP BY 1;
CREATE OR REPLACE TEMP TABLE cmulti AS SELECT cat, count(*) FILTER (np >= 2) / count(*) multi FROM
  (SELECT user_id, cat, count(DISTINCT product_id) np FROM wa WHERE event_type = 'purchase' GROUP BY 1, 2) GROUP BY 1;
CREATE OR REPLACE TEMP TABLE bt AS SELECT brand,
  count(DISTINCT user_id) FILTER (event_type IN ('cart','purchase') AND event_time >= {T} - INTERVAL 7 DAY) a7
  FROM wa WHERE brand IS NOT NULL GROUP BY 1;
CREATE OR REPLACE TEMP TABLE cbt AS SELECT cat, brand,
  count(DISTINCT user_id) FILTER (event_type IN ('cart','purchase') AND event_time >= {T} - INTERVAL 7 DAY) a7
  FROM wa WHERE brand IS NOT NULL GROUP BY 1, 2;

-- user-level
CREATE OR REPLACE TEMP TABLE ls AS SELECT user_id, arg_max(user_session, (event_time, user_session)) s FROM uev
  WHERE event_time >= {T} - INTERVAL 48 HOUR AND user_session IS NOT NULL GROUP BY 1;
CREATE OR REPLACE TEMP TABLE lsev AS SELECT u.* FROM uw u JOIN ls ON ls.user_id = u.user_id AND ls.s = u.user_session;
CREATE OR REPLACE TEMP TABLE ufirst AS SELECT user_id, count(*) n_new,
  count(*) FILTER (first_cp_ts IS NOT NULL AND first_ts::DATE = first_cp_ts::DATE) n_acq
  FROM pf WHERE first_ts >= {T} - INTERVAL 14 DAY AND user_id IN (SELECT user_id FROM queries) GROUP BY 1;
CREATE OR REPLACE TEMP TABLE ubfirst AS SELECT user_id, brand, min(event_time) first_ts FROM wa
  WHERE brand IS NOT NULL GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE bexp AS SELECT q.user_id, (b.first_ts >= q.first_ts)::INT novel
  FROM acq_all q JOIN iattr a USING(product_id) JOIN ubfirst b ON b.user_id = q.user_id AND b.brand = a.brand;
CREATE OR REPLACE TEMP TABLE uf AS
WITH v AS (SELECT user_id,
    count(*) FILTER (event_type = 'view' AND event_time >= {T} - INTERVAL 7 DAY) views7,
    count(DISTINCT user_session) FILTER (event_time >= {T} - INTERVAL 7 DAY) sess7,
    count(DISTINCT product_id) FILTER (event_type = 'view' AND event_time >= {T} - INTERVAL 7 DAY) items7,
    max(event_time) FILTER (event_type IN ('cart','purchase')) last_cp,
    max(event_time) FILTER (event_type = 'view' AND event_time >= {T} - INTERVAL 48 HOUR) last_view,
    median(ln(CASE WHEN price > 0 THEN price END)) FILTER (event_type = 'view' AND event_time >= {T} - INTERVAL 7 DAY) lp_med,
    count(DISTINCT event_time::DATE) FILTER (event_time >= {T} - INTERVAL 7 DAY) days7,
    min(event_time) first_ev,
    bool_or(event_time::DATE = {D} - 7) same_wd
  FROM uev GROUP BY 1),
topc AS (SELECT user_id, max(n_view_7d) top FROM ucw GROUP BY 1),
r AS (SELECT rv.user_id,
    median(ln(1 + coalesce(it.a7, 0))) FILTER (rv.k <= 50) pop_taste,
    avg(ipct.pct) FILTER (rv.k <= 20) tier
  FROM rv LEFT JOIN it USING(product_id) LEFT JOIN ipct USING(product_id) GROUP BY 1),
l AS (SELECT user_id, count(*) FILTER (event_type = 'view') ls_views,
    CASE WHEN bool_or(event_type = 'purchase') THEN 2 WHEN bool_or(event_type = 'cart') THEN 1 ELSE 0 END ls_outcome
  FROM lsev GROUP BY 1),
hhi AS (SELECT user_id, sum(pow(w / s, 2)) hhi FROM (SELECT user_id, w, sum(w) OVER (PARTITION BY user_id) s FROM ubw) GROUP BY 1),
bx AS (SELECT user_id, count(*) n, sum(novel) novel FROM bexp GROUP BY 1),
g AS (SELECT avg(novel) g FROM bexp)
SELECT q.user_id,
  ln(1 + coalesce(v.views7, 0)) u_views_7d_log,
  topc.top / nullif(v.views7, 0) u_top_category_share_7d,
  epoch({T} - v.last_cp) / 3600 u_hours_since_last_cp,
  coalesce(uf1.n_acq, 0) / (coalesce(uf1.n_new, 0) + 5.0) u_new_item_cp_rate_14d,
  v.lp_med u_log_price_med_view_7d,
  r.pop_taste u_pop_taste_14d,
  epoch({T} - v.last_view) / 3600 u_hours_since_last_view,
  v.views7 / nullif(v.sess7, 0) u_views_per_session_7d,
  v.items7 / nullif(v.views7, 0) u_items_per_view_7d,
  coalesce(l.ls_outcome, 0) u_ls_outcome,
  ln(1 + coalesce(l.ls_views, 0)) u_ls_views_log,
  coalesce(v.days7, 0) u_active_days_7d,
  r.tier u_price_tier,
  least(7, epoch({T} - v.first_ev) / 86400) u_first_seen_days_cap7,
  coalesce(v.same_wd, false)::INT u_active_same_weekday_last_week,
  hhi.hhi u_brand_hhi_14d,
  (bx.novel + 3 * g.g) / (bx.n + 3) u_brand_explore_rate_14d
FROM queries q LEFT JOIN v USING(user_id) LEFT JOIN topc USING(user_id) LEFT JOIN ufirst uf1 USING(user_id)
LEFT JOIN r USING(user_id) LEFT JOIN l USING(user_id) LEFT JOIN hhi USING(user_id) LEFT JOIN bx USING(user_id) CROSS JOIN g;

-- item-level, for candidate products only
CREATE OR REPLACE TEMP TABLE items AS SELECT DISTINCT product_id FROM candidates;
CREATE OR REPLACE TEMP TABLE itf AS SELECT i.product_id,
  CASE WHEN it.product_id IS NOT NULL THEN ln(1 + 1e6 * it.a7 / g.sum_a7) END i_actor_share_7d,
  (coalesce(it.a1, 0) + 3) / (coalesce(it.a7, 0) / 7.0 + 3) i_trend_actor_1v7,
  (coalesce(it.v1, 0) + 5) / (coalesce(it.v7, 0) / 7.0 + 5) i_trend_view_1v7,
  ((coalesce(ac.acq, 0) + 10 * g.p_acq_share) / (coalesce(it.a14, 0) + 10)) / g.p_acq_share i_acq_share_lift_14d,
  ln(pc.p_last) i_log_price,
  pc.pct i_price_pct_in_cat,
  it.a7 / nullif(cs.a7, 0) i_cat_actor_share_7d,
  ((coalesce(it.b14, 0) + 50 * g.p_buy) / (coalesce(it.v14, 0) + 50)) / g.p_buy i_buy_lift_14d,
  ((coalesce(ac.acq, 0) + 50 * g.p_acq_rate) / (coalesce(ac.new_users, 0) + 50)) / g.p_acq_rate i_acq_rate_lift_14d,
  ((coalesce(it.c7, 0) + 50 * g.p_cart) / (coalesce(it.v7, 0) + 50)) / g.p_cart i_cart_lift_7d,
  ((coalesce(ct.b14, 0) + 200 * cn.p_buy) / (coalesce(ct.v14, 0) + 200)) / cn.p_buy i_cat_buy_lift_14d,
  CASE WHEN a.brand IS NOT NULL THEN ln(1 + 1e6 * coalesce(bt.a7, 0) / (SELECT sum(a7) FROM bt)) END i_brand_actor_share_7d,
  CASE WHEN a.brand IS NOT NULL THEN coalesce(cbt.a7, 0) / nullif(ct.a7, 0) END i_brand_share_in_cat_7d,
  CASE WHEN ip.n_days7 >= 3 THEN greatest(-0.5, least(0.5, ip.p_last / ip.p_med7 - 1)) END i_price_change_7d,
  CASE WHEN ip.n_days >= 3 THEN ip.p_last / ip.p_max - 1 END i_price_from_max_14d,
  CASE WHEN it.product_id IS NOT NULL THEN (it.seen7 AND NOT it.seen_prev7)::INT END i_is_fresh_item_7d,
  coalesce(a.l1, 'none') i_cat_l1,
  epoch({T} - it.last_view) / 3600 i_hours_since_last_view,
  (coalesce(ct.v1, 0) + 20) / (coalesce(ct.v7, 0) / 7.0 + 20) i_cat_trend_view_1v7,
  (coalesce(ac.acq1, 0) + 2) / (coalesce(ac.acq7, 0) / 7.0 + 2) i_acq_trend_1v7,
  (coalesce(ir.rep, 0) + 20 * (SELECT sum(rep) / sum(buyers) FROM irep)) / (coalesce(ir.buyers, 0) + 20)
    / (SELECT sum(rep) / sum(buyers) FROM irep) * CASE WHEN ir.buyers > 0 THEN 1 END i_repeat_buyer_share_14d,
  cm.multi i_cat_multi_buy_14d
FROM items i CROSS JOIN gnorm g CROSS JOIN cnorm cn LEFT JOIN it USING(product_id) LEFT JOIN iattr a USING(product_id)
LEFT JOIN iacq ac USING(product_id) LEFT JOIN ipct pc USING(product_id) LEFT JOIN iprice ip USING(product_id)
LEFT JOIN ct ON ct.cat = a.cat LEFT JOIN csum cs ON cs.cat = a.cat LEFT JOIN bt ON bt.brand = a.brand LEFT JOIN cbt ON cbt.cat = a.cat AND cbt.brand = a.brand
LEFT JOIN irep ir USING(product_id) LEFT JOIN cmulti cm ON cm.cat = a.cat;

-- user x category / brand profiles
CREATE OR REPLACE TEMP TABLE ucr AS SELECT ucw.*, ucw.w / utot.tot cshare,
  dense_rank() OVER (PARTITION BY user_id ORDER BY ucw.w DESC, cat) rank_in_user
  FROM ucw JOIN utot USING(user_id);
CREATE OR REPLACE TEMP TABLE ucb AS SELECT user_id, cat, brand, sum(wt) w FROM uw WHERE brand IS NOT NULL GROUP BY ALL;
CREATE OR REPLACE TEMP TABLE ul1 AS SELECT user_id, l1, sum(wt) w FROM uw WHERE l1 IS NOT NULL GROUP BY ALL;
CREATE OR REPLACE TEMP TABLE rva AS SELECT rv.*, a.cat, a.brand, pc.pct FROM rv JOIN iattr a USING(product_id)
  LEFT JOIN ipct pc USING(product_id);
CREATE OR REPLACE TEMP TABLE rvc AS SELECT user_id, cat,
  count(*) FILTER (last_ts >= {T} - INTERVAL 7 DAY) distinct_viewed_7d,
  min(k) FILTER (k <= 50) first_pos, sum(pow(0.8, k - 1)) FILTER (k <= 20) decay20
  FROM rva GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE rvb AS SELECT user_id, brand, sum(pow(0.8, k - 1)) FILTER (k <= 20) decay20
  FROM rva WHERE brand IS NOT NULL GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE lsc AS SELECT user_id, cat, count(DISTINCT product_id) FILTER (event_type = 'view') items,
  max((event_type IN ('cart','purchase'))::INT) cp FROM lsev GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE jc AS SELECT k.user_id, k.product_id,
  ln(pc.p_last) - median(ln(r.price_seen)) ratio_med,
  min(abs(ln(pc.p_last / r.price_seen))) dist_min,
  CASE WHEN count(*) >= 2 THEN (ln(pc.p_last) BETWEEN min(ln(r.price_seen)) AND max(ln(r.price_seen)))::INT END in_range
  FROM candidates k JOIN iattr a USING(product_id) JOIN ipct pc USING(product_id)
  JOIN rva r ON r.user_id = k.user_id AND r.cat = a.cat AND r.k <= 50 AND r.price_seen > 0
  WHERE pc.p_last > 0 GROUP BY k.user_id, k.product_id, pc.p_last;

-- transitions to acquisitions: up to 20 latest views of other products in the 3 days before the first cp
CREATE OR REPLACE TEMP TABLE prior AS SELECT q.user_id, q.product_id b, v.product_id a
  FROM acq_all q JOIN w v ON v.user_id = q.user_id AND v.event_type = 'view' AND v.product_id <> q.product_id
    AND v.event_time < q.first_cp_ts AND v.event_time >= q.first_cp_ts - INTERVAL 3 DAY
  GROUP BY q.user_id, q.product_id, v.product_id
  QUALIFY row_number() OVER (PARTITION BY q.user_id, q.product_id ORDER BY max(v.event_time) DESC, v.product_id) <= 20;
CREATE OR REPLACE TEMP TABLE tr AS SELECT a, b, count(DISTINCT user_id) n FROM prior
  WHERE a IN (SELECT product_id FROM rv WHERE k <= 10) GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE trc AS SELECT aa.cat ca, ab.cat cb, count(DISTINCT p.user_id) n FROM prior p
  JOIN iattr aa ON aa.product_id = p.a JOIN iattr ab ON ab.product_id = p.b WHERE aa.cat <> ab.cat GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE nca AS SELECT a.cat, count(DISTINCT q.user_id) n FROM acq_all q JOIN iattr a USING(product_id) GROUP BY 1;
CREATE OR REPLACE TEMP TABLE ncp AS SELECT product_id, count(DISTINCT user_id) n FROM acq_all GROUP BY 1;

-- candidate x recent items
CREATE OR REPLACE TEMP TABLE kr AS SELECT k.user_id, k.product_id, r.product_id a, r.k, r.last_ts, r.cat cat_a, ab.cat cat_b,
  CASE WHEN c.n_ab >= 2 THEN c.n_ab END n_ab, c.rk, na.n n_a, nb.n n_b, tr.n ntr, it.v14 nv_a, coalesce(ncp.n, 0) nc_b
  FROM candidates k JOIN rva r ON r.user_id = k.user_id AND r.k <= 10 JOIN iattr ab ON ab.product_id = k.product_id
  LEFT JOIN nb c ON c.a = r.product_id AND c.b = k.product_id
  LEFT JOIN ns na ON na.product_id = r.product_id LEFT JOIN ns nb ON nb.product_id = k.product_id
  LEFT JOIN tr ON tr.a = r.product_id AND tr.b = k.product_id
  LEFT JOIN it ON it.product_id = r.product_id LEFT JOIN ncp ON ncp.product_id = k.product_id;
CREATE OR REPLACE TEMP TABLE cff AS SELECT user_id, product_id,
  coalesce(max(n_ab / sqrt(n_a * n_b)), 0) cf_cv_cos_max,
  coalesce(max(n_ab / sqrt(n_a * n_b)) FILTER (k = 1), 0) cf_cv_cos_last,
  coalesce(sum(n_ab / (n_a + 5) * exp(-epoch({T} - last_ts) / 86400)), 0) cf_cv_cond_tdecay,
  coalesce(sum(ntr / (nv_a + 10) * exp(-epoch({T} - last_ts) / 86400)), 0) cf_tr_p_tdecay,
  min(rk) cf_src4_best_rank,
  coalesce(max(n_ab / sqrt(n_a * n_b)) FILTER (cat_a = cat_b), 0) cf_cv_cos_same_cat_max,
  coalesce(max(ntr / (nv_a + 10)) FILTER (cat_a <> cat_b), 0) cf_tr_p_diff_cat_max,
  max(ln(((ntr + 1) / (nv_a + 10)) / ((nc_b + 1) / (SELECT n_viewers FROM gnorm)))) FILTER (ntr >= 1) cf_tr_lift_max
  FROM kr GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE ctl AS SELECT k.user_id, k.product_id,
  max(ln(((t.n + 1) / (cv.v14 + 10)) / ((coalesce(nca.n, 0) + 1) / (SELECT n_viewers FROM gnorm)))) uc_trans_lift_max
  FROM candidates k JOIN iattr ab ON ab.product_id = k.product_id
  JOIN (SELECT DISTINCT user_id, cat FROM rva WHERE k <= 10) r ON r.user_id = k.user_id AND r.cat <> ab.cat
  JOIN trc t ON t.ca = r.cat AND t.cb = ab.cat JOIN ct cv ON cv.cat = r.cat LEFT JOIN nca ON nca.cat = ab.cat
  GROUP BY 1, 2;
"""

FINAL = """
SELECT {D} AS anchor, k.user_id, k.product_id,
  (l.user_id IS NOT NULL)::INT AS label, coalesce(l.is_purchase, 0) label_purchase, q.n_targets, q.n_targets_purchase,
  -- s_: candidate source
  k.pop_rank s_pop_rank, k.cat_rank s_cat_rank, k.brand_rank s_brand_rank,
  (k.pop_rank IS NOT NULL)::INT + (k.cat_rank IS NOT NULL)::INT + (k.brand_rank IS NOT NULL)::INT + k.src4 s_n_sources,
  -- u_: user
  u.* EXCLUDE (user_id),
  -- i_: item
  i.* EXCLUDE (product_id),
  -- uc_: candidate category in the user's history
  coalesce(c.cshare, 0) uc_share_hl1d,
  epoch({T} - c.last_ts) / 3600 uc_last_h,
  coalesce(rc.distinct_viewed_7d, 0) uc_distinct_viewed_7d,
  rc.first_pos uc_first_pos,
  coalesce(lc.items, 0) uc_ls_items,
  epoch({T} - c.last_cp_ts) / 3600 uc_last_cp_h,
  c.rank_in_user uc_rank_in_user,
  coalesce(c.active_days, 0) uc_active_days_14d,
  epoch({T} - c.last_purchase_ts) / 3600 uc_last_purchase_h,
  coalesce(rc.decay20, 0) uc_decay20,
  coalesce(lc.cp, 0) uc_ls_cp,
  CASE WHEN a.l1 IS NOT NULL THEN coalesce(l1.w, 0) / ut.tot END uc_l1_share_hl1d,
  ctl.uc_trans_lift_max,
  -- ub_: candidate brand in the user's history
  CASE WHEN a.brand IS NOT NULL THEN coalesce(b.w, 0) / ut.tot END ub_share_hl1d,
  CASE WHEN a.brand IS NOT NULL AND c.w IS NOT NULL THEN coalesce(cb.w, 0) / c.w END ub_share_in_cat,
  epoch({T} - b.last_ts) / 3600 ub_last_h,
  CASE WHEN a.brand IS NOT NULL THEN coalesce(b.w, 0) END ub_weight_hl1d,
  CASE WHEN a.brand IS NOT NULL THEN coalesce(rb.decay20, 0) END ub_decay20,
  -- up_/ui_: price and popularity relative to the user
  i.i_log_price - u.u_log_price_med_view_7d up_logprice_vs_user,
  abs(i.i_price_pct_in_cat - u.u_price_tier) up_tier_absdiff,
  jc.ratio_med up_cat_logratio_med,
  jc.dist_min up_cat_logdist_min,
  i.i_price_pct_in_cat - u.u_price_tier up_tier_diff,
  jc.in_range up_cat_in_range,
  ln(1 + coalesce(it.a7, 0)) - u.u_pop_taste_14d ui_pop_gap,
  -- cf_: item-item from the user's 10 latest views (NULL when the user has no views)
  f.cf_cv_cos_max, f.cf_cv_cos_last, f.cf_cv_cond_tdecay, f.cf_tr_p_tdecay, f.cf_src4_best_rank,
  f.cf_cv_cos_same_cat_max, f.cf_tr_p_diff_cat_max, f.cf_tr_lift_max
FROM candidates k
JOIN queries q USING(user_id)
LEFT JOIN labels l USING(user_id, product_id)
LEFT JOIN uf u USING(user_id)
LEFT JOIN itf i USING(product_id)
LEFT JOIN it USING(product_id)
LEFT JOIN iattr a USING(product_id)
LEFT JOIN utot ut USING(user_id)
LEFT JOIN ucr c ON c.user_id = k.user_id AND c.cat = a.cat
LEFT JOIN rvc rc ON rc.user_id = k.user_id AND rc.cat = a.cat
LEFT JOIN lsc lc ON lc.user_id = k.user_id AND lc.cat = a.cat
LEFT JOIN ul1 l1 ON l1.user_id = k.user_id AND l1.l1 = a.l1
LEFT JOIN ubw b ON b.user_id = k.user_id AND b.brand = a.brand
LEFT JOIN ucb cb ON cb.user_id = k.user_id AND cb.cat = a.cat AND cb.brand = a.brand
LEFT JOIN rvb rb ON rb.user_id = k.user_id AND rb.brand = a.brand
LEFT JOIN jc ON jc.user_id = k.user_id AND jc.product_id = k.product_id
LEFT JOIN ctl ON ctl.user_id = k.user_id AND ctl.product_id = k.product_id
LEFT JOIN cff f ON f.user_id = k.user_id AND f.product_id = k.product_id
ORDER BY k.user_id, k.product_id
"""


def set_anchor(con, t, max_queries=None):
    """Create temp tables for anchor t: hist, queries, labels, candidates and their inputs."""
    con.execute(sql(ANCHOR, t).replace('{LIMIT}', f'LIMIT {max_queries}' if max_queries else ''))


def build_day(con, day, max_queries=None, out=OUT):
    t = datetime.combine(day, datetime.min.time()).isoformat(sep=' ')
    t0 = time.time()
    set_anchor(con, t, max_queries)
    t1 = time.time()
    con.execute(sql(FEATURES, t))
    t2 = time.time()
    path = out / f'{day.isoformat()}.parquet'
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({sql(FINAL, t)}) TO '{path}' (FORMAT PARQUET)")
    s = con.execute(f"""SELECT count(DISTINCT user_id), count(*), sum(label), sum(label_purchase),
        (SELECT sum(n_targets) FROM queries), (SELECT sum(n_targets_purchase) FROM queries),
        count(*) FILTER (s_pop_rank IS NOT NULL), count(*) FILTER (s_cat_rank IS NOT NULL),
        count(*) FILTER (s_brand_rank IS NOT NULL), (SELECT count(*) FROM candidates WHERE src4 = 1)
        FROM read_parquet('{path}')""").fetchone()
    return dict(day=day.isoformat(), queries=s[0], pairs=s[1], hits=s[2], targets=s[4],
                recall=round(s[2] / s[4], 3), recall_purchase=round(s[3] / max(s[5], 1), 3),
                rows_by_source=dict(pop=s[6], cat=s[7], brand=s[8], coview=s[9]),
                seconds=dict(anchor=round(t1 - t0, 1), features=round(t2 - t1, 1), write=round(time.time() - t2, 1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True, type=date.fromisoformat)
    ap.add_argument('--end', required=True, type=date.fromisoformat, help='inclusive')
    ap.add_argument('--max-queries', type=int, help='cap of queries per day (default: all)')
    ap.add_argument('--out', type=Path, default=OUT)
    ap.add_argument('--threads', type=int, default=10)
    args = ap.parse_args()
    con = connect(args.threads)
    day = args.start
    while day <= args.end:
        print(build_day(con, day, args.max_queries, args.out), flush=True)
        day += timedelta(days=1)


if __name__ == '__main__':
    main()
