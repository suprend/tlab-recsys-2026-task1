-- A.6: regime-invariant item counters: the product's share of the day's cart users and of purchase users,
-- last day and last 7 days (each normalised by that window's total), and their ratio
WITH w AS (SELECT * FROM hist WHERE event_time >= TIMESTAMP '{t}' - INTERVAL 7 DAY AND event_type IN ('cart', 'purchase')),
c AS (SELECT product_id,
        count(DISTINCT user_id) FILTER (event_type = 'cart' AND event_time >= TIMESTAMP '{t}' - INTERVAL 1 DAY) c1,
        count(DISTINCT user_id) FILTER (event_type = 'purchase' AND event_time >= TIMESTAMP '{t}' - INTERVAL 1 DAY) p1,
        count(DISTINCT user_id) FILTER (event_type = 'cart') c7,
        count(DISTINCT user_id) FILTER (event_type = 'purchase') p7 FROM w GROUP BY 1),
g AS (SELECT sum(c1) c1, sum(p1) p1, sum(c7) c7, sum(p7) p7 FROM c)
SELECT product_id, ln(1 + 1e6 * c.c1 / g.c1) f_x_cart_share_1d, ln(1 + 1e6 * c.p1 / g.p1) f_x_buy_share_1d,
       ln((1e6 * c.c7 / g.c7 + 1) / (1e6 * c.p7 / g.p7 + 1)) f_x_cart_vs_buy_share_7d
FROM c CROSS JOIN g
