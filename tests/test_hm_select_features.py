"""Program selection tests use opaque fake artifacts and a nontraining model stub."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import hm_feature_engine as engine
from scripts import hm_select_features as selector


class FakeModel:
    """No fit, predictions, validation Pool or native saved model is available."""
    def __init__(self, names, categorical, scores, trees=150):
        self.feature_names_ = list(names)
        self.categorical = set(categorical)
        self.scores = scores
        self.tree_count_ = trees
        self.calls = []

    def load_model(self, path):
        self.calls.append(("load_model", path))

    def get_cat_feature_indices(self):
        return [i for i, name in enumerate(self.feature_names_) if name in self.categorical]

    def get_feature_importance(self, *, type, thread_count):
        self.calls.append(("importance", type, thread_count))
        return [self.scores.get(name, 0.0) for name in self.feature_names_]


class PoolTests(unittest.TestCase):
    def test_pilot58_and_strong53_reinclude_only_nonselected_manual_aggregate_aliases(self):
        manifest = engine.feature_manifest()
        pilot = selector.enumerate_pool(manifest["feature_sets"]["manual_pilot"])
        strong = selector.enumerate_pool(manifest["feature_sets"]["strong_manual"])
        pnames, snames = {entry["name"] for entry in pilot}, {entry["name"] for entry in strong}
        self.assertEqual(len(pilot), 58)
        self.assertEqual(len(strong), 53)
        self.assertEqual(pnames - snames, {"affinity_type_share28", "affinity_colour_share28", "affinity_department28",
                                          "affinity_department_share28", "affinity_type_recency90"})
        self.assertNotIn("affinity_type28", pnames)
        self.assertNotIn("affinity_colour28", pnames)
        self.assertNotIn("repeat_share28", pnames)
        self.assertNotIn("demand7to28", pnames)
        self.assertNotIn("price_compat28", pnames)

    def test_randoms_preserve_M_and_match_declared_numpy_draws_exactly(self):
        import numpy as np
        manual = engine.feature_manifest()["feature_sets"]["manual_pilot"]
        pool = [entry["name"] for entry in selector.enumerate_pool(manual)]
        result = selector.random_bundles(manual, list(reversed(pool)))
        self.assertEqual(result, selector.random_bundles(manual, pool))
        self.assertEqual(set(result), {"101", "102", "103"})
        for seed in (101, 102, 103):
            expected = sorted(str(name) for name in np.random.default_rng(seed).choice(sorted(pool), 12, replace=False))
            self.assertEqual(result[str(seed)], manual + expected)
            self.assertEqual(len(set(result[str(seed)][len(manual):])), 12)
            self.assertTrue(set(manual).isdisjoint(expected))

    def test_zero_or_undersized_generated_pool_rejected(self):
        manifest = engine.feature_manifest()
        aggregate_names = [definition["name"] for definition in manifest["registry"] if definition["operation"] in selector.OPERATIONS]
        with self.assertRaisesRegex(ValueError, "Fewer than 12"):
            selector.enumerate_pool(aggregate_names)
        with self.assertRaisesRegex(ValueError, "at least12"):
            selector.random_bundles(["manual"], [f"p{i}" for i in range(11)])
        with self.assertRaises(ValueError):
            selector.random_bundles(["p0"], [f"p{i}" for i in range(12)])

    def test_importance_alignment_and_ties_are_by_actual_model_names(self):
        pool = [f"p{i:02d}" for i in range(14)]
        names = ["manual"] + list(reversed(pool))
        scores = [9999] + [1 if name not in ("p13", "p12") else 2 for name in reversed(pool)]
        chosen, ranking = selector.choose_by_importance(pool, names, scores)
        self.assertEqual(chosen, ["p12", "p13"] + pool[:10])
        self.assertEqual(ranking[-2:], [{"name": "p10", "importance": 1.0}, {"name": "p11", "importance": 1.0}])
        self.assertNotIn("manual", chosen)

    def test_invalid_model_importance_vectors_and_names_are_rejected(self):
        names = [f"p{i}" for i in range(12)]
        for scores in ([0]*11, [0]*11+[float("nan")], [0]*11+[float("inf")], [0]*11+[-1]):
            with self.subTest(scores=scores), self.assertRaises(ValueError):
                selector.choose_by_importance(names, names, scores)
        with self.assertRaises(ValueError):
            selector.choose_by_importance(names, names[:-1]+[names[0]], [0]*12)
        with self.assertRaises(ValueError):
            selector.choose_by_importance(names, names, [0]*12, width=11)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        # Historical fixture witnesses retain the original two-thread contract.
        self.config = deepcopy(selector._campaign())
        self.config.pop("post_manual_execution", None)
        campaign_patch = patch.object(selector, "_campaign", return_value=self.config)
        campaign_patch.start()
        self.addCleanup(campaign_patch.stop)
        self.tmp = tempfile.TemporaryDirectory(prefix="hm-selection-unit-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = self.root / "collection"
        self.manual = self.root / "manual"
        self.study = self.root / "study"
        self.all = self.root / "all"
        self.selected = self.root / "selected"
        self.code = selector._code_identity()
        self.manifest = engine.feature_manifest()
        self.manual_names = self.manifest["feature_sets"]["manual_pilot"]
        self._write_cache()
        self._write_fit(self.manual, self.manual_names)

    def write_json(self, path, value):
        Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")

    def _write_cache(self):
        self.cache.mkdir()
        for name in selector.CACHE_FILES:
            (self.cache/name).write_bytes(f"opaque synthetic {name}; not a real parquet or production row".encode())
        files = {name: selector._sha(self.cache/name) for name in selector.CACHE_FILES}
        report = dict(format="hm-experiment-collection-v1", status="completed", anchor="2020-09-02",
                      cohort_seed=2026, policy="C0-Q120", requested_users=20000,
                      files=files, qcy_identity=selector._digest({name: files[name] for name in ("users.parquet", "targets.parquet")}),
                      candidate_identity=selector._digest("synthetic C"), database=dict(sha256=selector._digest("synthetic source"), bytes=1),
                      features=dict(registry=[dict(entry, kind="categorical" if entry["dtype"] == "string" else "numeric")
                                              for entry in self.manifest["registry"]],
                                    feature_sets=self.manifest["feature_sets"], digest=self.manifest["digest"]),
                      code={name: self.code[name] for name in ("hm_experiment.py", "hm_retrieval.py", "hm_feature_engine.py", "hm_baseline.py")})
        self.write_json(self.cache/"manifest.json", report)

    def _write_fit(self, directory, names, changes=None, reverse_order=False):
        directory.mkdir()
        for name in selector.FIT_FILES:
            (directory/name).write_bytes(f"opaque synthetic {name}; not a model or predictions".encode())
        categorical = [name for name in names if name in engine.CATEGORICAL_FEATURES]
        numeric = [name for name in names if name not in engine.CATEGORICAL_FEATURES]
        if reverse_order:
            numeric.reverse()
            categorical.reverse()
        cache = selector._read_json(self.cache/"manifest.json")
        inputs = [dict(anchor=anchor, manifest_sha256=selector._digest(f"manifest {anchor}"),
                       qcy_identity=selector._digest(f"qcy {anchor}"), candidate_identity=selector._digest(f"c {anchor}"))
                  for anchor in ("2020-08-12", "2020-08-19", "2020-08-26")]
        inputs.append(dict(anchor=cache["anchor"], manifest_sha256=selector._sha(self.cache/"manifest.json"),
                           qcy_identity=cache["qcy_identity"], candidate_identity=cache["candidate_identity"]))
        report = dict(format="hm-experiment-fit-v1", status="completed", fit_count=1, actual_trees=150,
                      selection=selector.FIT_SELECTION, training_user_limit=5000, negative_sample=20,
                      sampling_seed=2026, features=dict(numeric=numeric, categorical=categorical,
                                                        contract_digest=self.manifest["digest"]),
                      inputs=inputs, runtime={"environment": "synthetic unit test"},
                      code={name: self.code[name] for name in ("hm_experiment.py", "hm_baseline.py")},
                      hyperparameters=dict(iterations=150, depth=6, learning_rate=0.05, l2_leaf_reg=10,
                                           loss_function="Logloss", random_seed=2026, thread_count=2,
                                           task_type="CPU", verbose=False, allow_writing_files=False),
                      validation_metrics={"poison": "not a numeric result; must never guide selection"},
                      files={name: selector._sha(directory/name) for name in selector.FIT_FILES})
        if changes:
            report.update(deepcopy(changes))
        self._finish_report(directory, report)
        return report

    def _finish_report(self, directory, report):
        report["fit_identity"] = selector._digest(dict(inputs=report["inputs"], features=report["features"],
            hyperparameters=report["hyperparameters"], train_users=report["training_user_limit"],
            negative_sample=report["negative_sample"], sampling_seed=report["sampling_seed"],
            code=report["code"], runtime=report["runtime"]))
        self.write_json(directory/"report.json", report)

    def prepare_and_all(self, reverse_order=False):
        prepared = selector.prepare_study(self.manual, self.cache, self.study)
        report = self._write_fit(self.all, prepared["plan"]["names"]["all_names.json"], reverse_order=reverse_order)
        return prepared, report

    def fake(self, prepared, report, scores=None):
        names = report["features"]["numeric"] + report["features"]["categorical"]
        pool = [entry["name"] for entry in prepared["plan"]["pool"]]
        if scores is None:
            scores = {name: float(i+1) for i, name in enumerate(pool)}
            scores.update({name: 99999 for name in prepared["plan"]["manual_names"]})
        return FakeModel(names, report["features"]["categorical"], scores)

    def test_prepare_persists_before_model_access_and_keeps_every_manual_input(self):
        with patch.object(FakeModel, "load_model", side_effect=AssertionError("prepare loaded model")):
            result = selector.prepare_study(self.manual, self.cache, self.study)
        self.assertEqual(result["status"], "prepared")
        self.assertEqual(len(result["plan"]["pool"]), 58)
        self.assertEqual(len(result["plan"]["names"]["all_names.json"]), 81)
        self.assertEqual(set(result["files"]), set(selector.NAME_FILES))
        self.assertEqual(selector.read_study(self.study), result)
        for filename, names in result["plan"]["names"].items():
            self.assertEqual(names[:23], self.manual_names)
            self.assertEqual(selector._read_json(self.study/filename), names)
        with self.assertRaises(FileExistsError):
            selector.prepare_study(self.manual, self.cache, self.study)

    def test_four_thread_amendment_requires_fresh_M_and_preserves_frozen_recipe(self):
        self.config["post_manual_execution"] = dict(threads=4, manual_features="strong_manual", iterations=500, depth=8, seed=2026)
        strong = self.root/"strong"
        report = self._write_fit(strong, self.manifest["feature_sets"]["strong_manual"])
        report["hyperparameters"].update(iterations=500,depth=8)
        report["actual_trees"]=500
        report["training_user_limit"]=20000
        self._finish_report(strong, report)
        with self.assertRaisesRegex(ValueError,"hyperparameters"):
            selector.prepare_study(strong,self.cache,self.study)
        self.assertFalse(self.study.exists())
        fresh = self.root/"fresh-M4"
        fresh_params=dict(report["hyperparameters"],thread_count=4)
        self._write_fit(fresh,self.manifest["feature_sets"]["strong_manual"],
            changes=dict(hyperparameters=fresh_params,actual_trees=500,training_user_limit=20000,
                         runtime={"threads":4,"environment":"fresh synthetic reference"}))
        result=selector.prepare_study(fresh,self.cache,self.study)
        self.assertEqual(result["plan"]["manual_set"],"strong_manual")
        self.assertEqual(result["plan"]["recipe"]["hyperparameters"]["thread_count"],4)
        self.assertEqual(self.config["manual_tuning"]["fixed"]["thread_count"],2)
        self.assertEqual(result["plan"]["manual_fit"]["path"],fresh.resolve().as_posix())
        with self.assertRaisesRegex(ValueError,"frozen winning"):
            selector.prepare_study(self.manual,self.cache,self.root/"wrong-recipe")

    def test_strong_manual_preparation_has53_pool_and_never_injects_manual_transforms(self):
        strong = self.root/"strong"
        self._write_fit(strong, self.manifest["feature_sets"]["strong_manual"])
        result = selector.prepare_study(strong, self.cache, self.study)
        self.assertEqual(result["plan"]["manual_set"], "strong_manual")
        self.assertEqual(len(result["plan"]["pool"]), 53)
        self.assertEqual(len(result["plan"]["names"]["all_names.json"]), 87)

    def test_select_uses_name_aligned_trainingPVC_with_exact_thread_limit_and_no_data(self):
        prepared, report = self.prepare_and_all(reverse_order=True)
        model = self.fake(prepared, report)
        selected = selector.select_study(self.study, self.all, self.selected, model_factory=lambda: model)
        pool = [entry["name"] for entry in prepared["plan"]["pool"]]
        expected = list(reversed(pool[-12:]))
        self.assertEqual(selected["selected_programs"], expected)
        self.assertEqual(selected["names"], self.manual_names+expected)
        self.assertEqual(model.calls[1], ("importance", "PredictionValuesChange", 2))
        self.assertEqual(selected["protocol"]["importance_data"], None)
        self.assertEqual(selector._read_json(self.selected/"selected_names.json"), self.manual_names+expected)
        self.assertEqual(len(selected["pool_ranking"]), 58)
        self.assertEqual(selected["files"]["selected_names.json"], selector._sha(self.selected/"selected_names.json"))
        with self.assertRaises(FileExistsError):
            selector.select_study(self.study, self.all, self.selected, model_factory=lambda: model)

    def test_tiedPVC_uses_feature_name_tie_break_despite_model_and_report_reorder(self):
        prepared, report = self.prepare_and_all(reverse_order=True)
        model = self.fake(prepared, report, scores={name: 7 for name in prepared["plan"]["names"]["all_names.json"]})
        result = selector.select_study(self.study, self.all, self.selected, model_factory=lambda: model)
        self.assertEqual(result["selected_programs"], sorted(entry["name"] for entry in prepared["plan"]["pool"])[:12])

    def test_validation_metrics_values_have_no_effect_on_name_selection(self):
        prepared, report = self.prepare_and_all()
        first = selector.select_study(self.study, self.all, self.selected, model_factory=lambda: self.fake(prepared, report))
        # This is an alternate all-fit report with the same recipe/model bytes,
        # but arbitrary misleading validation figures. It cannot change PVC order.
        report["validation_metrics"] = {"map_at_12_conditional": 1e100, "choose": "wrong_program"}
        self._finish_report(self.all, report)
        second = selector.select_study(self.study, self.all, self.root/"selected2", model_factory=lambda: self.fake(prepared, report))
        self.assertEqual(first["selected_programs"], second["selected_programs"])

    def test_changed_study_names_inputs_model_and_source_are_detected_before_load(self):
        prepared, report = self.prepare_and_all()
        name_path = self.study/"random101_names.json"
        original = name_path.read_bytes()
        name_path.write_bytes(original+b" ")
        with self.assertRaisesRegex(ValueError, "byte identity"):
            selector.select_study(self.study, self.all, self.selected, model_factory=lambda: self.fail("loaded model"))
        name_path.write_bytes(original)
        model_path = self.all/"model.cbm"
        original_model = model_path.read_bytes()
        model_path.write_bytes(b"tampered model")
        with self.assertRaisesRegex(ValueError, "byte identity"):
            selector.select_study(self.study, self.all, self.selected, model_factory=lambda: self.fail("loaded model"))
        model_path.write_bytes(original_model)
        changed = dict(self.code, **{"hm_feature_engine.py": selector._digest("changed engine")})
        with patch.object(selector, "_code_identity", return_value=changed), self.assertRaisesRegex(ValueError, "source code"):
            selector.select_study(self.study, self.all, self.selected, model_factory=lambda: self.fail("loaded model"))
        (self.cache/"frame.parquet").write_bytes(b"tampered validation bytes")
        with self.assertRaisesRegex(ValueError, "byte identity"):
            selector.select_study(self.study, self.all, self.selected, model_factory=lambda: self.fail("loaded model"))

    def test_mismatched_all_training_policy_and_inputs_fail_before_model_load(self):
        prepared, report = self.prepare_and_all()
        for key, value in (("negative_sample", 0), ("training_user_limit", 20000)):
            changed = deepcopy(report)
            changed[key] = value
            self._finish_report(self.all, changed)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "preserve manual"):
                selector.select_study(self.study, self.all, self.selected, model_factory=lambda: self.fail("loaded model"))
        changed = deepcopy(report)
        changed["inputs"][-1]["candidate_identity"] = selector._digest("different C")
        self._finish_report(self.all, changed)
        with self.assertRaisesRegex(ValueError, "preserve manual"):
            selector.select_study(self.study, self.all, self.selected, model_factory=lambda: self.fail("loaded model"))

    def test_historical_wrapper_drift_allowed_but_feature_engine_drift_rejected(self):
        prepared, report = self.prepare_and_all()
        changed = dict(self.code, **{"hm_experiment.py": selector._digest("later final CLI wrapper"),
                                     "hm_retrieval.py": selector._digest("later retrieval wrapper")})
        with patch.object(selector, "_code_identity", return_value=changed):
            self.assertEqual(selector.read_study(self.study), prepared)
            result = selector.select_study(self.study, self.all, self.selected,
                                           model_factory=lambda: self.fake(prepared, report))
        self.assertEqual(len(result["selected_programs"]), 12)
        changed["hm_feature_engine.py"] = selector._digest("different aggregate formulas")
        with patch.object(selector, "_code_identity", return_value=changed), self.assertRaisesRegex(ValueError, "feature source code"):
            selector.read_study(self.study)

    def test_all_fit_producer_version_must_match_manual_fit_even_if_latest_wrapper_differs(self):
        prepared, report = self.prepare_and_all()
        report["code"]["hm_experiment.py"] = selector._digest("different all-fit producer")
        self._finish_report(self.all, report)
        with self.assertRaisesRegex(ValueError, "preserve manual"):
            selector.select_study(self.study, self.all, self.selected, model_factory=lambda: self.fail("loaded model"))

    def test_mismatched_all_feature_set_model_names_trees_and_types_are_rejected(self):
        prepared, report = self.prepare_and_all()
        changed = deepcopy(report)
        changed["features"]["numeric"] = changed["features"]["numeric"][:-1]
        self._finish_report(self.all, changed)
        with self.assertRaisesRegex(ValueError, "exactly M"):
            selector.select_study(self.study, self.all, self.selected, model_factory=lambda: self.fail("loaded model"))
        self._finish_report(self.all, report)
        for mutate in (lambda model: model.feature_names_.reverse(),
                       lambda model: setattr(model, "tree_count_", 149),
                       lambda model: setattr(model, "categorical", set())):
            model = self.fake(prepared, report)
            mutate(model)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                selector.select_study(self.study, self.all, self.selected, model_factory=lambda: model)

    def test_incomplete_or_nonfixed_manual_fit_and_wrong_selection_anchor_are_rejected(self):
        report = selector._read_json(self.manual/"report.json")
        for changes in ({"status": "failed"}, {"fit_count": 2}, {"actual_trees": 149}):
            changed = deepcopy(report)
            changed.update(changes)
            self._finish_report(self.manual, changed)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                selector.prepare_study(self.manual, self.cache, self.study)
        self._finish_report(self.manual, report)
        cache = selector._read_json(self.cache/"manifest.json")
        cache["anchor"] = "2020-09-09"
        self.write_json(self.cache/"manifest.json", cache)
        with self.assertRaisesRegex(ValueError, "selection collection"):
            selector.prepare_study(self.manual, self.cache, self.study)

    def test_report_identity_and_manifest_feature_contract_tampering_is_rejected(self):
        report = selector._read_json(self.manual/"report.json")
        report["hyperparameters"]["depth"] = 8
        self.write_json(self.manual/"report.json", report)  # deliberately do not recompute fit identity
        with self.assertRaisesRegex(ValueError, "recipe identity"):
            selector.prepare_study(self.manual, self.cache, self.study)
        cache = selector._read_json(self.cache/"manifest.json")
        cache["features"]["registry"][0]["formula"] = "future outcome"
        self.write_json(self.cache/"manifest.json", cache)
        with self.assertRaisesRegex(ValueError, "registry/manifest"):
            selector.prepare_study(self.manual, self.cache, self.study)


if __name__ == "__main__":
    unittest.main()
