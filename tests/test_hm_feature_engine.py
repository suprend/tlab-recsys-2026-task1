"""Synthetic SQL/scalar witnesses; no production sources, labels or model fits."""
from datetime import date, datetime, timedelta
import hashlib
import json
import math
import unittest

from scripts import hm_feature_engine as engine


ANCHOR = date(2020, 9, 9)
FIELDS = ("product_type_no", "colour_group_code", "department_no", "index_code", "garment_group_no")
METADATA = {
    "0001": ("T", "red", "D", "I", "G"),
    "0002": ("T", "blue", "E", "J", "G"),
    "0003": ("S", "red", "D", "I", "H"),
    "0004": (None, None, None, None, None),
    "0005": ("T", "red", "D", "I", "G"),
}


def fixture_events():
    # Duplicate rows represent multiple purchased units, not duplicate labels.
    specs = [
        (1, "u1", "0001", 2.0), (1, "u1", "0001", 2.0),
        (7, "u1", "0002", 4.0), (28, "u1", "0003", 1.0),
        (90, "u1", "0004", 0.0), (91, "u1", "0002", 999.0),
        (0, "u1", "0002", 999.0), (-1, "u1", "0001", 999.0),
        (3, "outside_cohort", "0001", 6.0),
        (40, "outside_cohort", "0002", 8.0),
        (29, "u2", "0003", 0.0), (90, "u2", "0002", None),
        (1, "u2", "0099", 0.0),
    ]
    return [(ANCHOR - timedelta(days=ago), user, item, price, "2")
            for ago, user, item, price in specs]


def scalar_oracle(events, metadata, candidates, anchor):
    """List-based implementation independent of SQL builder and program dispatch.

    The dimension/window/operator grid is declared literally here, rather than
    imported from the engine. Every emitted field is checked against this result.
    """
    history = [event for event in events if anchor-timedelta(days=90) <= event[0] < anchor]
    dims = ("product_type_no", "colour_group_code", "department_no", "garment_group_no", "index_code")
    dim_index = {field: i for i, field in enumerate(FIELDS)}
    aliases = {
        ("product_type_no", 28, "count"): "affinity_type28",
        ("colour_group_code", 28, "count"): "affinity_colour28",
        ("department_no", 28, "count"): "affinity_department28",
        ("product_type_no", 28, "share"): "affinity_type_share28",
        ("colour_group_code", 28, "share"): "affinity_colour_share28",
        ("department_no", 28, "share"): "affinity_department_share28",
        ("product_type_no", 90, "recency"): "affinity_type_recency90",
    }

    def within(rows, days):
        return [row for row in rows if row[0] >= anchor-timedelta(days=days)]

    def mean_price(rows):
        prices = [row[3] for row in rows if row[3] is not None]
        return sum(prices)/len(prices) if prices else None

    def recency(rows):
        return (anchor-max(row[0] for row in rows)).days if rows else 91

    weekly_buyers = {}
    for row in within(history, 7):
        weekly_buyers.setdefault(row[2], set()).add(row[1])
    ranked_global = sorted(weekly_buyers, key=lambda item: (-len(weekly_buyers[item]), item))[:100]
    output = {}
    for user, item in sorted(candidates):
        uh = [row for row in history if row[1] == user]
        ih = [row for row in history if row[2] == item]
        uih = [row for row in uh if row[2] == item]
        values = {"customer_id": user, "article_id": item}
        for days in (7, 28, 90):
            values[f"u_tx{days}"] = len(within(uh, days))
            values[f"i_buyers{days}"] = len({row[1] for row in within(ih, days)})
            values[f"ui_tx{days}"] = len(within(uih, days))
        values.update(u_recency=recency(uh), i_recency=recency(ih), ui_recency=recency(uih))
        ip, up = mean_price(within(ih, 28)), mean_price(within(uh, 28))
        values["item_price28"], values["user_price28"] = ip if ip is not None else 0, up if up is not None else 0
        values["item_price28_missing"], values["user_price28_missing"] = int(ip is None), int(up is None)
        valid = ip is not None and up is not None and ip > 0 and up > 0 and math.isfinite(ip) and math.isfinite(up)
        values["price_compat28_valid"] = int(valid)
        values["price_compat28"] = abs(math.log(ip/up)) if valid else 0
        values["repeat_share28"] = values["ui_tx28"]/values["u_tx28"] if values["u_tx28"] else 0
        values["demand7to28"] = 4*values["i_buyers7"]/values["i_buyers28"] if values["i_buyers28"] else 0
        values["global_rank"] = ranked_global.index(item)+1 if item in ranked_global else 101
        latest = {}
        for row in uh:
            latest[row[2]] = max(latest.get(row[2], row[0]), row[0])
        ranked_recent = sorted(latest, key=lambda a: (-latest[a].toordinal(), a))[:20]
        values["user_recent_rank"] = ranked_recent.index(item)+1 if item in ranked_recent else 21
        for dimension in dims:
            position = dim_index[dimension]
            candidate_value = metadata.get(item, (None,)*5)[position]
            values[dimension] = candidate_value if candidate_value is not None else "__MISSING__"
            matching = [row for row in uh if candidate_value is not None
                        and metadata.get(row[2], (None,)*5)[position] == candidate_value]
            for days in (7, 28, 90):
                rows = within(matching, days)
                total = len(within(uh, days))
                results = {"count": len(rows), "share": len(rows)/total if total else 0,
                           "distinct_items": len({row[2] for row in rows}), "recency": recency(rows)}
                for operation, value in results.items():
                    name = aliases.get((dimension, days, operation), f"auto_{dimension}_{operation}{days}")
                    values[name] = value
        output[(user, item)] = values
    return output


class RegistryTests(unittest.TestCase):
    def test_generated_schema_and_semantic_dedup_are_fixed_before_data(self):
        manifest = engine.feature_manifest()
        registry = engine.feature_registry()
        sets = manifest["feature_sets"]
        self.assertEqual(len(sets["manual_pilot"]), 23)
        self.assertEqual(len(sets["strong_manual"]), 34)
        self.assertEqual(len(sets["generated"]), 53)
        self.assertEqual(len(sets["strong_plus_generated"]), 87)
        self.assertEqual(len({definition.name for definition in registry}), len(registry))
        self.assertEqual(len({definition.semantic_key for definition in registry}), len(registry))
        self.assertTrue(set(sets["strong_manual"]).isdisjoint(sets["generated"]))
        self.assertEqual({definition.name for definition in registry}, set(sets["strong_plus_generated"]))
        self.assertEqual(len(manifest["generated_aliases"]), 7)
        self.assertNotIn("auto_product_type_no_count28", sets["generated"])
        self.assertIn("auto_department_no_distinct_items28", sets["generated"])

    def test_digest_is_json_stable_and_detects_semantic_changes(self):
        one, two = engine.feature_manifest(), engine.feature_manifest()
        digest = one.pop("digest")
        self.assertEqual(digest, two["digest"])
        self.assertEqual(digest, hashlib.sha256(json.dumps(one, sort_keys=True, separators=(",", ":"),
                                                         ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest())
        one["policy"]["history"] = "changed window"
        changed = hashlib.sha256(json.dumps(one, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        self.assertNotEqual(digest, changed)

    def test_unknown_capabilities_and_labels_are_rejected(self):
        for kwargs in (
            dict(operation="label"), dict(operation="count", dimension="age", window_days=28),
            dict(operation="count", dimension="index_code", window_days=30),
            dict(operation="count", dimension=None, window_days=28),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                engine.FeatureDef("candidate_feature", "generated", **kwargs)


class SqlTests(unittest.TestCase):
    def setUp(self):
        import duckdb
        self.con = duckdb.connect(":memory:")
        self.con.execute("CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR,price DOUBLE,sales_channel_id VARCHAR)")
        self.con.execute("CREATE TABLE articles(article_id VARCHAR,"+",".join(f"{field} VARCHAR" for field in FIELDS)+")")
        self.con.executemany("INSERT INTO articles VALUES(?,?,?,?,?,?)", [(item, *attrs) for item, attrs in METADATA.items()])
        self.events = fixture_events()
        self.con.executemany("INSERT INTO transactions VALUES(?,?,?,?,?)", self.events)
        self.candidates = [("u1", item) for item in METADATA] + [("u1", "0099"), ("u2", "0002"), ("u2", "0099"), ("cold", "0001")]
        self.con.execute("CREATE TEMP TABLE hm_candidates(customer_id VARCHAR,article_id VARCHAR)")
        self.con.executemany("INSERT INTO hm_candidates VALUES(?,?)", list(reversed(self.candidates)))

    def tearDown(self):
        self.con.close()

    def assert_frame_matches_oracle(self, result, events=None, metadata=None, candidates=None):
        oracle = scalar_oracle(self.events if events is None else events,
                               METADATA if metadata is None else metadata,
                               self.candidates if candidates is None else candidates, ANCHOR)
        self.assertEqual(list(result.frame.columns), ["customer_id", "article_id"] + result.feature_sets["strong_plus_generated"])
        self.assertEqual(list(zip(result.frame.customer_id, result.frame.article_id)), sorted(oracle))
        for actual in result.frame.to_dict("records"):
            expected = oracle[(actual["customer_id"], actual["article_id"])]
            self.assertEqual(set(actual), set(expected))
            for name, value in expected.items():
                with self.subTest(pair=(actual["customer_id"], actual["article_id"]), name=name):
                    if isinstance(value, str):
                        self.assertEqual(actual[name], value)
                    else:
                        self.assertAlmostEqual(actual[name], value, places=12)

    def test_every_family_all_windows_all_columns_match_independent_scalar_oracle(self):
        result = engine.build_features(self.con, ANCHOR)
        self.assert_frame_matches_oracle(result)
        self.assertEqual(result.digest, engine.feature_manifest()["digest"])
        self.assertEqual(result.registry, engine.feature_registry())

    def test_literal_counts_duplicates_boundaries_and_fullpopulation_stats(self):
        result = engine.build_features(self.con, "2020-09-09")
        row = result.frame.set_index(["customer_id", "article_id"]).loc[("u1", "0001")]
        expected = {"u_tx7": 3, "u_tx28": 4, "u_tx90": 5, "ui_tx7": 2,
                    "i_buyers7": 2, "i_buyers28": 2, "i_buyers90": 2,
                    "affinity_type28": 3, "affinity_type_share28": 3/4,
                    "affinity_colour28": 3, "affinity_department28": 3,
                    "affinity_type_recency90": 1, "repeat_share28": 1/2,
                    "demand7to28": 4, "item_price28": 10/3, "user_price28": 9/4,
                    "auto_product_type_no_distinct_items7": 2,
                    "auto_product_type_no_count90": 3,
                    "auto_colour_group_code_count90": 3,
                    "price_compat28_valid": 1, "item_price28_missing": 0}
        for name, value in expected.items():
            with self.subTest(name=name):
                self.assertAlmostEqual(row[name], value, places=12)
        # June11, the 90-day boundary, is retained. A user cannot match a NULL
        # category to another NULL category merely through the display sentinel.
        missing = result.frame.set_index(["customer_id", "article_id"]).loc[("u1", "0004")]
        self.assertEqual(missing.ui_tx90, 1)
        self.assertEqual(missing.ui_recency, 90)
        self.assertEqual(missing.auto_product_type_no_count90, 0)
        self.assertEqual(missing.affinity_type_recency90, 91)

    def test_future_and_expired_rows_cannot_change_any_feature(self):
        before = engine.build_features(self.con, ANCHOR).frame
        self.con.executemany("INSERT INTO transactions VALUES(?,?,?,?,?)", [
            (ANCHOR, "u1", "0001", 123456, "1"),
            (ANCHOR+timedelta(days=10), "u1", "0001", 98765, "1"),
            (ANCHOR-timedelta(days=91), "u1", "0001", 22222, "1"),
        ])
        after = engine.build_features(self.con, ANCHOR).frame
        self.assertTrue(before.equals(after))

    def test_missing_history_item_metadata_and_zero_prices_are_explicit(self):
        result = engine.build_features(self.con, ANCHOR)
        rows = result.frame.set_index(["customer_id", "article_id"])
        cold = rows.loc[("cold", "0001")]
        self.assertEqual(cold.u_tx90, 0)
        self.assertEqual(cold.u_recency, 91)
        self.assertEqual(cold.user_recent_rank, 21)
        self.assertEqual(cold.i_buyers7, 2)
        self.assertEqual(cold.user_price28_missing, 1)
        self.assertEqual(cold.price_compat28_valid, 0)
        self.assertEqual(cold.price_compat28, 0)
        unknown = rows.loc[("u2", "0099")]
        self.assertEqual(unknown.product_type_no, "__MISSING__")
        self.assertEqual(unknown.affinity_type28, 0)
        self.assertEqual(unknown.ui_tx7, 1)
        self.assertEqual(unknown.item_price28_missing, 0)  # observed zero, not absent
        self.assertEqual(unknown.user_price28_missing, 0)
        self.assertEqual(unknown.price_compat28_valid, 0)
        no_price = rows.loc[("u2", "0002")]
        self.assertEqual(no_price.item_price28_missing, 0)  # u1's 7-day purchase
        no_item = rows.loc[("u1", "0005")]
        self.assertEqual(no_item.item_price28_missing, 1)
        self.assertEqual(no_item.affinity_type28, 3)  # semantic match without item exposure

    def test_empty_candidates_and_entirely_empty_history_preserve_typed_schema(self):
        self.con.execute("DELETE FROM hm_candidates")
        empty = engine.build_features(self.con, ANCHOR)
        self.assertEqual(len(empty.frame), 0)
        self.assertEqual(len(empty.frame.columns), 89)
        self.con.execute("INSERT INTO hm_candidates VALUES('new','0001')")
        self.con.execute("DELETE FROM transactions")
        result = engine.build_features(self.con, ANCHOR)
        self.assert_frame_matches_oracle(result, events=[], candidates=[("new", "0001")])

    def test_bad_candidate_keys_and_duplicate_metadata_are_rejected(self):
        self.con.execute("INSERT INTO hm_candidates VALUES('u1','0001')")
        with self.assertRaisesRegex(ValueError, "exactly one row"):
            engine.build_features(self.con, ANCHOR)
        self.con.execute("DELETE FROM hm_candidates")
        self.con.execute("INSERT INTO hm_candidates VALUES(NULL,'0001')")
        with self.assertRaisesRegex(ValueError, "non-null"):
            engine.build_features(self.con, ANCHOR)
        self.con.execute("DELETE FROM hm_candidates")
        self.con.execute("INSERT INTO articles SELECT * FROM articles LIMIT 1")
        with self.assertRaisesRegex(ValueError, "unique"):
            engine.build_features(self.con, ANCHOR)

    def test_numeric_keys_and_sql_expressions_are_rejected_before_coercion(self):
        self.con.execute("CREATE TEMP TABLE numeric_candidates(customer_id VARCHAR,article_id BIGINT)")
        with self.assertRaisesRegex(ValueError, "VARCHAR"):
            engine.build_features(self.con, ANCHOR, "numeric_candidates")
        for name in ("hm_candidates; DROP TABLE articles", "hm_f_history", "schema.hm_candidates"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                engine.build_features(None, ANCHOR, name)
        with self.assertRaisesRegex(ValueError, "time component"):
            engine.build_features(None, datetime(2020, 9, 9))

    def test_rank_caps_ties_leading_zeros_and_scalar_agreement(self):
        self.con.execute("DELETE FROM transactions")
        self.con.execute("DELETE FROM hm_candidates")
        items = [f"{i:04d}" for i in range(1, 106)]
        metadata = dict(METADATA)
        for item in items:
            metadata.setdefault(item, ("T", "red", "D", "I", "G"))
        self.con.execute("DELETE FROM articles")
        self.con.executemany("INSERT INTO articles VALUES(?,?,?,?,?,?)", [(item, *attrs) for item, attrs in metadata.items()])
        events = [(ANCHOR-timedelta(days=1), "u", item, 1.0, "1") for item in items]
        self.con.executemany("INSERT INTO transactions VALUES(?,?,?,?,?)", events)
        candidates = [("u", item) for item in ("0001", "0020", "0021", "0100", "0101", "0105")]
        self.con.executemany("INSERT INTO hm_candidates VALUES(?,?)", candidates)
        result = engine.build_features(self.con, ANCHOR)
        self.assert_frame_matches_oracle(result, events=events, metadata=metadata, candidates=candidates)
        rows = result.frame.set_index("article_id")
        self.assertEqual(rows.loc["0100", "global_rank"], 100)
        self.assertEqual(rows.loc["0101", "global_rank"], 101)
        self.assertEqual(rows.loc["0105", "global_rank"], 101)
        self.assertEqual(rows.loc["0020", "user_recent_rank"], 20)
        self.assertEqual(rows.loc["0021", "user_recent_rank"], 21)
        self.assertEqual(rows.loc["0001", "user_recent_rank"], 1)

    def test_no_source_mutations_or_retrieval_temp_clobber(self):
        self.con.execute("CREATE TEMP TABLE hm_r_history AS SELECT 777 AS marker")
        before = self.con.execute("SELECT * FROM transactions ORDER BY ALL").fetchall()
        articles = self.con.execute("SELECT * FROM articles ORDER BY ALL").fetchall()
        candidates = self.con.execute("SELECT * FROM hm_candidates ORDER BY ALL").fetchall()
        engine.build_features(self.con, ANCHOR)
        self.assertEqual(self.con.execute("SELECT * FROM transactions ORDER BY ALL").fetchall(), before)
        self.assertEqual(self.con.execute("SELECT * FROM articles ORDER BY ALL").fetchall(), articles)
        self.assertEqual(self.con.execute("SELECT * FROM hm_candidates ORDER BY ALL").fetchall(), candidates)
        self.assertEqual(self.con.execute("SELECT * FROM hm_r_history").fetchall(), [(777,)])


if __name__ == "__main__":
    unittest.main()
