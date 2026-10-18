"""Freeze generated H&M programs/random controls, then select by training PVC.

Prepare reads completed fit/cache metadata and byte hashes, never row content or
scores. Select loads only the frozen M+all model and requests training-derived
PredictionValuesChange without any validation Pool. No stage fits a model.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re

from scripts import hm_feature_engine as engine


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "configs/datasets/hm-campaign.json"
WIDTH = 12
RANDOM_SEEDS = (101, 102, 103)
OPERATIONS = frozenset(("count", "share", "recency", "distinct_items"))
FIT_FILES = ("model.cbm", "query-metrics.parquet", "predictions-top12.parquet")
CACHE_FILES = ("frame.parquet", "users.parquet", "targets.parquet")
CODE_FILES = ("hm_select_features.py", "hm_feature_engine.py", "hm_experiment.py",
              "hm_baseline.py", "hm_retrieval.py")
NAME_FILES = ("M_names.json", "all_names.json", "random101_names.json",
              "random102_names.json", "random103_names.json")
HEX_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
FIT_SELECTION = "One fixed-tree fit; no eval_set, early stopping or parameter search"


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _read_json(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON property")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("Nonfinite JSON constant")

    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)


def _write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _require_digest(value):
    if not isinstance(value, str) or not HEX_DIGEST.fullmatch(value):
        raise ValueError("A full lowercase SHA256 identity is required")
    return value


def _require_names(names):
    if (not isinstance(names, list) or not names or not all(isinstance(name, str) for name in names)
            or len(set(names)) != len(names)):
        raise ValueError("Nonempty unique feature-name list required")
    return names


def _code_identity():
    return {name: _sha(ROOT / "scripts" / name) for name in CODE_FILES}


def _campaign():
    config = _read_json(CAMPAIGN)
    automatic = config["automation"]
    if (automatic["bundle_size"] != WIDTH
            or automatic["schema_dimensions"] != list(engine.DIMENSIONS)
            or automatic["windows"] != list(engine.WINDOWS)
            or set(automatic["operations"]) != OPERATIONS
            or len(automatic["operations"]) != len(OPERATIONS)
            or automatic["random_bundles"]["count"] != 3
            or automatic["random_bundles"]["seeds"] != list(RANDOM_SEEDS)
            or automatic["model_seed"] != 2026):
        raise ValueError("Campaign automation differs from this reviewed finite protocol")
    if config["selection"] != {"anchor": "2020-09-02",
                              "train_anchors": ["2020-08-12", "2020-08-19", "2020-08-26"]}:
        raise ValueError("Only the predeclared selection phase is supported")
    return config


def enumerate_pool(manual_names, manifest=None):
    """Return all aggregate programs not semantically present in exact M.

    A pilot M excludes only its two aggregate counts, so five nonselected strong
    aliases re-enter the pool. Nonaggregate strong transforms are never invented
    by this grammar. Expected sizes are 58 (pilot M) and 53 (strong M).
    """
    manual_names = _require_names(list(manual_names))
    manifest = engine.feature_manifest() if manifest is None else manifest
    registry = manifest["registry"]
    by_name = {definition["name"]: definition for definition in registry}
    if len(by_name) != len(registry) or not set(manual_names) <= set(by_name):
        raise ValueError("M must contain unique registered names")

    def semantic_key(definition):
        if definition["operation"] in OPERATIONS:
            return (definition["dimension"], definition["window_days"], definition["operation"])
        return ("explicit", definition["name"])

    manual_keys = {semantic_key(by_name[name]) for name in manual_names}
    aggregates = [definition for definition in registry if definition["operation"] in OPERATIONS]
    if len(aggregates) != 60 or len({semantic_key(definition) for definition in aggregates}) != 60:
        raise ValueError("Exactly 60 unique frozen aggregate programs are required")
    pool = sorted((definition for definition in aggregates if semantic_key(definition) not in manual_keys),
                  key=lambda definition: definition["name"])
    if len(pool) < WIDTH:
        raise ValueError("Fewer than 12 novel aggregate programs; replan before fitting")
    return pool


def random_bundles(manual_names, pool_names):
    """Three fixed draws; preserve M, sample without replacement, never pick best."""
    import numpy as np
    manual_names = _require_names(list(manual_names))
    pool_names = sorted(_require_names(list(pool_names)))
    if set(manual_names) & set(pool_names) or len(pool_names) < WIDTH:
        raise ValueError("Pool must be novel to M and contain at least12 programs")
    result = {}
    for seed in RANDOM_SEEDS:
        chosen = sorted(str(name) for name in np.random.default_rng(seed).choice(pool_names, WIDTH, replace=False))
        result[str(seed)] = manual_names + chosen
    return result


def _verify_files(directory, declared, names):
    if not isinstance(declared, dict) or set(declared) != set(names):
        raise ValueError("Artifact file inventory differs from the expected fixed inventory")
    for name in names:
        if _sha(directory / name) != _require_digest(declared[name]):
            raise ValueError("Artifact byte identity changed")


def _collection(directory, code):
    path = directory / "manifest.json"
    report = _read_json(path)
    if report.get("format") != "hm-experiment-collection-v1" or report.get("status") != "completed":
        raise ValueError("Completed development collection required")
    if report.get("cohort_seed") != 2026 or report.get("policy") not in ("C0-Q120", "C1-Q120"):
        raise ValueError("Collection cohort/retrieval policy mismatch")
    producer = report.get("code")
    if not isinstance(producer, dict) or set(producer) != {"hm_experiment.py", "hm_retrieval.py", "hm_feature_engine.py", "hm_baseline.py"}:
        raise ValueError("Collection producer code inventory is incomplete")
    for value in producer.values():
        _require_digest(value)
    if producer["hm_feature_engine.py"] != code["hm_feature_engine.py"]:
        raise ValueError("Collection feature source code differs from the frozen implementation")
    _verify_files(directory, report["files"], CACHE_FILES)
    if report["qcy_identity"] != _digest({name: report["files"][name] for name in ("users.parquet", "targets.parquet")}):
        raise ValueError("Collection Q/Y identity is inconsistent")
    _require_digest(report["candidate_identity"])
    current = engine.feature_manifest()
    expected_registry = [dict(definition, kind="categorical" if definition["dtype"] == "string" else "numeric")
                         for definition in current["registry"]]
    expected = {"registry": expected_registry, "feature_sets": current["feature_sets"], "digest": current["digest"]}
    if report.get("features") != expected:
        raise ValueError("Collection feature registry/manifest differs from frozen generator")
    _require_digest(report["database"]["sha256"])
    return report, dict(anchor=report["anchor"], manifest_sha256=_sha(path),
                        qcy_identity=report["qcy_identity"], candidate_identity=report["candidate_identity"])


def _fit(directory):
    path = directory / "report.json"
    # validation_metrics is deliberately never indexed, inspected or used.
    report = _read_json(path)
    if report.get("format") != "hm-experiment-fit-v1" or report.get("status") != "completed" or report.get("fit_count") != 1:
        raise ValueError("Exactly one completed fit is required")
    parameters = report["hyperparameters"]
    if report.get("actual_trees") != parameters["iterations"] or report.get("selection") != FIT_SELECTION:
        raise ValueError("Fit must have the full fixed-tree training policy")
    producer = report.get("code")
    if not isinstance(producer, dict) or set(producer) != {"hm_experiment.py", "hm_baseline.py"}:
        raise ValueError("Fit producer code inventory is incomplete")
    for value in producer.values():
        _require_digest(value)
    _verify_files(directory, report["files"], FIT_FILES)
    features = report["features"]
    numeric = _require_names(features["numeric"])
    categorical = _require_names(features["categorical"])
    names = numeric + categorical
    _require_names(names)
    kinds = {definition["name"]: definition["dtype"] for definition in engine.feature_manifest()["registry"]}
    if not set(names) <= set(kinds) or any(kinds[name] == "string" for name in numeric) or any(kinds[name] != "string" for name in categorical):
        raise ValueError("Fit feature names/types differ from registered programs")
    if features["contract_digest"] != engine.feature_manifest()["digest"]:
        raise ValueError("Fit feature contract differs from the frozen generator")
    inputs = report["inputs"]
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("Ordered training/validation input identities required")
    for identity in inputs:
        if set(identity) != {"anchor", "manifest_sha256", "qcy_identity", "candidate_identity"}:
            raise ValueError("Unexpected input identity schema")
        for key in ("manifest_sha256", "qcy_identity", "candidate_identity"):
            _require_digest(identity[key])
    recipe = dict(inputs=inputs, hyperparameters=parameters, training_user_limit=report["training_user_limit"],
                  negative_sample=report["negative_sample"], sampling_seed=report["sampling_seed"],
                  selection=report["selection"], runtime=report["runtime"], code=report["code"])
    identity = _digest(dict(inputs=inputs, features=features, hyperparameters=parameters,
                            train_users=report["training_user_limit"], negative_sample=report["negative_sample"],
                            sampling_seed=report["sampling_seed"], code=report["code"], runtime=report["runtime"]))
    if report.get("fit_identity") != identity:
        raise ValueError("Fit recipe identity is inconsistent")
    return report, names, recipe


def _prepare_plan(manual_fit_dir, validation_collection_dir):
    manual_fit_dir = Path(manual_fit_dir).resolve()
    validation_collection_dir = Path(validation_collection_dir).resolve()
    config = _campaign()
    code = _code_identity()
    cache, validation_identity = _collection(validation_collection_dir, code)
    manual, names, recipe = _fit(manual_fit_dir)
    if cache["anchor"] != config["selection"]["anchor"] or recipe["inputs"][-1] != validation_identity:
        raise ValueError("Manual fit must use exactly the supplied selection collection")
    if [identity["anchor"] for identity in recipe["inputs"][:-1]] != config["selection"]["train_anchors"]:
        raise ValueError("Manual fit training anchors differ from selection protocol")
    if recipe["negative_sample"] not in (0, 20) or recipe["sampling_seed"] != 2026:
        raise ValueError("Unrecognized training sampling policy")
    limit = recipe["training_user_limit"]
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("Training user limit must be positive or None")
    manifest = engine.feature_manifest()
    matches = [key for key in ("manual_pilot", "strong_manual") if set(names) == set(manifest["feature_sets"][key])]
    if len(matches) != 1:
        raise ValueError("M must be exactly one declared manual feature set")
    manual_set = matches[0]
    params = recipe["hyperparameters"]
    task_type = params.get("task_type")
    if task_type not in ("CPU", "GPU"):
        raise ValueError("Manual backend must be CPU or GPU")
    active_backend = config.get("execution", {}).get("task_type")
    if active_backend is not None and active_backend != task_type:
        raise ValueError("Manual backend differs from the active campaign backend")
    tuning = config["manual_tuning_gpu" if task_type == "GPU" else "manual_tuning"]
    candidate = [entry for entry in tuning["candidate_configs"]
                 if entry["features"] == manual_set and entry["iterations"] == params["iterations"] and entry["depth"] == params["depth"]]
    fixed = tuning["fixed"]
    amendment = config.get("post_manual_gpu_execution" if task_type == "GPU" else "post_manual_execution")
    if task_type == "GPU" and amendment is None:
        raise ValueError("Freeze GPU winner in post_manual_gpu_execution before preparing generated programs")
    model_threads = fixed["thread_count"]
    if amendment is not None:
        model_threads = amendment["threads"]
        if type(model_threads) is not int or model_threads != 4:
            raise ValueError("Post-manual execution requires the declared four-thread reference")
        if (manual_set != amendment["manual_features"] or params["iterations"] != amendment["iterations"]
                or params["depth"] != amendment["depth"] or params["random_seed"] != amendment["seed"]):
            raise ValueError("Post-manual execution must preserve the frozen winning manual recipe")
        if limit != 20000 or recipe["negative_sample"] != 20:
            raise ValueError("Post-manual reference must retain the frozen 20000-user sampled training policy")
    expected_params = dict(iterations=params["iterations"], depth=params["depth"],
                           learning_rate=fixed["learning_rate"], l2_leaf_reg=fixed["l2_leaf_reg"],
                           loss_function=fixed["loss_function"], random_seed=fixed["seed"],
                           thread_count=model_threads, task_type=task_type, verbose=False, allow_writing_files=False)
    if task_type == "GPU":
        if fixed.get("task_type", "GPU") != "GPU":
            raise ValueError("GPU manual tuning must declare the GPU backend")
        expected_params.update({name: fixed[name] for name in ("devices", "gpu_ram_part", "pinned_memory_size",
            "bootstrap_type", "bagging_temperature", "border_count", "boosting_type")})
    if len(candidate) != 1 or params != expected_params:
        raise ValueError("M hyperparameters differ from the declared manual candidates")
    pool = enumerate_pool(names, manifest)
    pool_names = [definition["name"] for definition in pool]
    random = random_bundles(names, pool_names)
    names_by_file = {"M_names.json": names, "all_names.json": names + pool_names,
                     **{f"random{seed}_names.json": random[str(seed)] for seed in RANDOM_SEEDS}}
    plan = {
        "format": "hm-generated-program-selection-plan-v1",
        "manual_fit": {"path": manual_fit_dir.as_posix(), "report_sha256": _sha(manual_fit_dir / "report.json"),
                       "files": manual["files"], "fit_identity": manual["fit_identity"]},
        "validation_collection": {"path": validation_collection_dir.as_posix(), "identity": validation_identity,
                                  "files": cache["files"], "database": cache["database"], "policy": cache["policy"]},
        "recipe": recipe,
        "manual_set": manual_set,
        "manual_names": names,
        "manual_input_digest": _digest(manual["features"]),
        "feature_contract_digest": manifest["digest"],
        "pool": pool,
        "pool_digest": _digest(pool),
        "names": names_by_file,
        "protocol": {"width": WIDTH, "random_seeds": list(RANDOM_SEEDS),
                     "random_sampler": "numpy.default_rng(seed).choice(sorted_pool,12,replace=False); sorted chosen",
                     "selector": "PredictionValuesChange; top12 pool by importance DESC,name ASC",
                     "importance_data": None, "importance_thread_count": 2,
                     "score_use": "No validation metrics, targets or validation Pool used for choosing names",
                     "campaign_sha256": _sha(CAMPAIGN)},
        "runtime": {name: importlib.metadata.version(name) for name in ("numpy", "catboost")},
        # Historical producer versions are pinned, not compared to a later
        # wrapper: adding a final CLI flag cannot change an existing cache/model.
        "producer_code": {"collection": cache["code"], "manual_fit": manual["code"]},
        "code": {name: code[name] for name in ("hm_select_features.py", "hm_feature_engine.py")},
    }
    return plan


def prepare_study(manual_fit_dir, validation_collection_dir, output):
    """Freeze M, all aggregate programs and three random controls before all-fit."""
    plan = _prepare_plan(manual_fit_dir, validation_collection_dir)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    for name, names in plan["names"].items():
        _write_json(output / name, names)
    manifest = {"format": "hm-feature-selection-study-v1", "status": "prepared", "plan": plan,
                "plan_digest": _digest(plan), "files": {name: _sha(output / name) for name in NAME_FILES}}
    _write_json(output / "manifest.json", manifest)
    return manifest


def read_study(study_dir):
    """Recheck all frozen names, current sources and original artifact identities."""
    study_dir = Path(study_dir).resolve()
    manifest = _read_json(study_dir / "manifest.json")
    if manifest.get("format") != "hm-feature-selection-study-v1" or manifest.get("status") != "prepared":
        raise ValueError("Prepared feature study required")
    plan = manifest["plan"]
    if manifest["plan_digest"] != _digest(plan):
        raise ValueError("Study plan digest changed")
    _verify_files(study_dir, manifest["files"], NAME_FILES)
    for name in NAME_FILES:
        if _read_json(study_dir / name) != plan["names"][name]:
            raise ValueError("Study feature names differ from the frozen plan")
    expected = _prepare_plan(plan["manual_fit"]["path"], plan["validation_collection"]["path"])
    if plan != expected:
        raise ValueError("Study source, inputs, protocol or runtime changed")
    return manifest


def choose_by_importance(pool_names, model_names, importances, width=WIDTH):
    """Pure name-aligned PVC order; never index importances by a sorted feature list."""
    pool_names = _require_names(list(pool_names))
    model_names = _require_names(list(model_names))
    if width != WIDTH or len(pool_names) < width or not set(pool_names) <= set(model_names):
        raise ValueError("Selector needs12 available pool programs and registered model names")
    scores = list(importances)
    if len(scores) != len(model_names):
        raise ValueError("Importance vector length differs from model input order")
    if not all(math.isfinite(float(score)) and float(score) >= 0 for score in scores):
        raise ValueError("PredictionValuesChange must contain finite nonnegative importances")
    by_name = {name: float(score) for name, score in zip(model_names, scores)}
    ranked = sorted(pool_names, key=lambda name: (-by_name[name], name))
    return ranked[:width], [{"name": name, "importance": by_name[name]} for name in ranked]


def select_study(study_dir, all_fit_dir, output, *, model_factory=None):
    """Load a frozen M+all model; select exactly12 programs without validation data."""
    study_dir, all_fit_dir, output = map(lambda path: Path(path).resolve(), (study_dir, all_fit_dir, output))
    if output.exists():
        raise FileExistsError("Selection output must be a new directory")
    study = read_study(study_dir)
    plan = study["plan"]
    report, all_names, recipe = _fit(all_fit_dir)
    if recipe != plan["recipe"]:
        raise ValueError("M+all must preserve manual hyperparameters, training policy and input identities")
    expected_names = plan["names"]["all_names.json"]
    if set(all_names) != set(expected_names):
        raise ValueError("M+all model input set must be exactly M plus the entire generated pool")
    report_hash = _sha(all_fit_dir / "report.json")
    if model_factory is None:
        from catboost import CatBoostClassifier
        model_factory = CatBoostClassifier
    model = model_factory()
    model.load_model(str(all_fit_dir / "model.cbm"))
    model_names = list(model.feature_names_)
    if model_names != all_names or model.tree_count_ != report["actual_trees"]:
        raise ValueError("Loaded model inputs/trees differ from its frozen report")
    expected_cats = {name for name in report["features"]["categorical"]}
    if {model_names[index] for index in model.get_cat_feature_indices()} != expected_cats:
        raise ValueError("Loaded model categorical inputs differ from its report")
    # Explicit training-only importance; never pass validation rows or a Pool.
    importance = model.get_feature_importance(type="PredictionValuesChange", thread_count=2)
    pool_names = [definition["name"] for definition in plan["pool"]]
    selected, ranking = choose_by_importance(pool_names, model_names, importance)
    if _sha(all_fit_dir / "report.json") != report_hash or _sha(all_fit_dir / "model.cbm") != report["files"]["model.cbm"]:
        raise ValueError("M+all report/model changed during selection")
    names = plan["manual_names"] + selected
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "selected_names.json", names)
    selection = {"format": "hm-generated-program-selection-v1", "status": "selected",
                 "study": {"path": study_dir.as_posix(), "manifest_sha256": _sha(study_dir / "manifest.json"),
                           "plan_digest": study["plan_digest"]},
                 "all_fit": {"path": all_fit_dir.as_posix(), "report_sha256": report_hash,
                             "model_sha256": report["files"]["model.cbm"], "fit_identity": report["fit_identity"]},
                 "manual_names": plan["manual_names"], "selected_programs": selected,
                 "names": names, "pool_ranking": ranking, "importance_model_order": model_names,
                 "protocol": plan["protocol"], "pool_digest": plan["pool_digest"],
                 "feature_contract_digest": plan["feature_contract_digest"], "code": plan["code"],
                 "files": {"selected_names.json": _sha(output / "selected_names.json")}}
    selection["selection_digest"] = _digest(selection)
    _write_json(output / "manifest.json", selection)
    return selection


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--manual-fit", type=Path, required=True)
    prepare.add_argument("--validation-collection", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    select = sub.add_parser("select")
    select.add_argument("--study", type=Path, required=True)
    select.add_argument("--all-fit", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            report = prepare_study(args.manual_fit, args.validation_collection, args.output)
        else:
            report = select_study(args.study, args.all_fit, args.output)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "output": args.output.as_posix()}))
        return 1
    print(json.dumps({"status": report["status"], "output": args.output.resolve().as_posix()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
