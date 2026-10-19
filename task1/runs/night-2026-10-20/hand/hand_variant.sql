-- A.2: variants of a model the user compared. Over the user's 20 latest viewed products (14d) of the same
-- category and brand as the product: min |log price difference| (only pairs within 0.5 are enumerated,
-- farther ones stay NULL) and the number of viewed products within 0.1
WITH w AS (SELECT * FROM hist WHERE event_time >= TIMESTAMP '{t}' - INTERVAL 14 DAY AND price > 0),
ip AS (SELECT product_id, arg_max(category_id, (event_time, category_id)) cat, arg_max(brand, (event_time, brand)) brand,
         ln(arg_max(price, (event_time, price))) lp FROM w GROUP BY 1),
rv AS (SELECT user_id, product_id, row_number() OVER (PARTITION BY user_id ORDER BY max(event_time) DESC, product_id) k
       FROM w WHERE event_type = 'view' AND user_id IN (SELECT user_id FROM active_users) GROUP BY 1, 2),
ucb AS (SELECT rv.user_id, ip.cat, ip.brand, ip.lp FROM rv JOIN ip USING(product_id) WHERE rv.k <= 20 AND ip.brand IS NOT NULL)
SELECT u.user_id, p.product_id, min(abs(p.lp - u.lp))::DOUBLE f_x_variant_logdist_min,
       count(*) FILTER (abs(p.lp - u.lp) < 0.1)::DOUBLE f_x_variant_siblings
FROM ucb u JOIN ip p ON p.cat = u.cat AND p.brand = u.brand AND abs(p.lp - u.lp) < 0.5
GROUP BY 1, 2
