"""Metric and temporal-protocol regression checks; no native model training."""
from datetime import date, timedelta
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hm_baseline.py"
SPEC = importlib.util.spec_from_file_location("hm_baseline_tested", SCRIPT)
hm = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hm
SPEC.loader.exec_module(hm)


class MetricTests(unittest.TestCase):
    def test_ap_denominator_includes_offcandidate_truth(self):
        self.assertAlmostEqual(hm.average_precision(["01"], {"01", "outside"}), 0.5)

    def test_duplicate_prediction_never_gains_a_second_hit(self):
        self.assertAlmostEqual(hm.average_precision(["01", "01", "02"], {"01", "02"}), (1+2/3)/2)

    def test_empty_and_uncovered_queries_count_correctly(self):
        report = hm.summarize_predictions(
            {"hit":["01"], "miss":["02"], "empty":["01"]},
            {"hit":{"01","outside"}, "miss":{"outside"}, "empty":set()},
            {"hit":["01"], "miss":["02"], "empty":["01"]})
        self.assertEqual(report["positive_queries"], 2)
        self.assertEqual(report["empty_target_queries"], 1)
        self.assertAlmostEqual(report["map_at_12_conditional"], 0.25)
        self.assertAlmostEqual(report["map_at_12_all_queries_empty_zero"], 1/6)
        self.assertAlmostEqual(report["candidate_target_coverage_micro"], 1/3)
        self.assertAlmostEqual(report["oracle_map_at_12_conditional"], 0.25)

    def test_ap_cutoff_denominator(self):
        truth = {str(i) for i in range(20)}
        self.assertEqual(hm.average_precision(list(truth)[:12], truth), 1.0)

    def test_cohort_never_depends_on_future_purchase(self):
        anchor = date(2020, 9, 9)
        events = [(anchor-timedelta(days=1),u,"01") for u in ("a","b","c")]
        future = [(anchor,u,"02") for u in ("a","future_only")]
        before = hm.select_eligible_users(events,anchor,2)
        self.assertEqual(before, hm.select_eligible_users(events+future,anchor,2))
        self.assertNotIn("future_only",hm.select_eligible_users(events+future,anchor,20))


class DatabaseProtocolTests(unittest.TestCase):
    def setUp(self):
        import duckdb
        self.con = duckdb.connect(":memory:")
        self.con.execute("CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR,price DOUBLE,sales_channel_id VARCHAR)")
        fields = ",".join(f"{field} VARCHAR" for field in hm.CATEGORICAL_FEATURES)
        self.con.execute(f"CREATE TABLE articles(article_id VARCHAR,{fields})")
        articles = [f"{i:010d}" for i in range(15)]
        self.con.executemany("INSERT INTO articles VALUES (?,?,?,?,?,?)",[(a,"type","colour","dept","index","garment") for a in articles])
        rows = [("2020-09-08","u",a,0.1,"2") for a in articles[:13]]
        rows += [("2020-09-09","u",articles[13],0.2,"2"),
                 ("2020-09-16","u",articles[14],0.3,"2"),
                 ("2020-09-10","future_only",articles[0],0.1,"2")]
        self.con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?)",rows)

    def tearDown(self):
        self.con.close()

    def test_sql_cohort_targets_candidates_and_features_are_temporal(self):
        data = hm.build_collection(self.con,"2020-09-09",20)
        self.assertEqual(set(data.targets),{"u"})
        self.assertEqual(data.targets["u"],{"0000000013"})
        self.assertNotIn("0000000013",set(data.articles))
        self.assertNotIn("0000000014",set(data.articles))
        self.assertEqual(int(data.labels.sum()),0)
        self.assertTrue((data.numeric[:,hm.NUMERIC_FEATURES.index("u_tx7")] == 13).all())
        self.assertTrue((data.numeric[:,hm.NUMERIC_FEATURES.index("u_recency")] == 1).all())
        self.assertAlmostEqual(float(data.weights.sum()),1.0,places=6)
        result = hm.rank_collection(data,scores=[0.0]*len(data.articles))
        self.assertEqual(result["map_at_12_conditional"],0.0)
        self.assertEqual(result["oracle_map_at_12_conditional"],0.0)

    def test_equal_scores_are_broken_by_string_article_id(self):
        data = hm.build_collection(self.con,"2020-09-09",20)
        data.targets["u"] = {"0000000000"}
        result = hm.rank_collection(data,scores=[0.0]*len(data.articles))
        self.assertEqual(result["map_at_12_conditional"],1.0)
        # The last lexicographic item must be outside the top12 at equal scores.
        data.targets["u"] = {"0000000012"}
        self.assertEqual(hm.rank_collection(data,scores=[0.0]*len(data.articles))["map_at_12_conditional"],0.0)

    def test_sql_cohort_agrees_with_sha256_oracle(self):
        self.con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?)",
            [("2020-09-08",u,"0000000000",0.1,"2") for u in ("a","b","c")])
        data = hm.build_collection(self.con,"2020-09-09",2)
        events = [(date(2020,9,8),u,"0000000000") for u in ("u","a","b","c")]
        self.assertEqual(set(data.targets),set(hm.select_eligible_users(events,date(2020,9,9),2)))

    def test_reserved_final_period_is_rejected_before_reading(self):
        with self.assertRaisesRegex(ValueError,"reserved final"):
            hm.build_collection(self.con,"2020-09-10",20)

    def test_features_are_accepted_by_native_catboost_pool_without_training(self):
        from catboost import FeaturesData, Pool
        data = hm.build_collection(self.con,"2020-09-09",20)
        pool = Pool(FeaturesData(num_feature_data=data.numeric,
                    cat_feature_data=data.categorical,
                    num_feature_names=hm.NUMERIC_FEATURES,
                    cat_feature_names=hm.CATEGORICAL_FEATURES),
                    label=data.labels,weight=data.weights)
        self.assertEqual(pool.num_row(),13)
        self.assertEqual(pool.num_col(),23)

    def test_past_window_boundary_is_inclusive_and_anchor_exclusive(self):
        self.con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?)",[
            ("2020-06-11","boundary","0000000000",0.1,"2"),
            ("2020-06-10","expired","0000000000",0.1,"2")])
        data=hm.build_collection(self.con,"2020-09-09",20)
        self.assertIn("boundary",data.targets)
        self.assertNotIn("expired",data.targets)


if __name__ == "__main__":
    unittest.main()
