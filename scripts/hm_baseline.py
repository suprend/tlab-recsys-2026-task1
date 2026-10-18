"""Fixed, bounded H&M pilot; local aggregate reports, never the final period.

Input is the typed DuckDB made by hm_eda.py. All history is strictly before
each anchor. Training labels end before validation; validation labels end
2020-09-16 exclusively. This command has no final evaluation or tuning path.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

TRAIN_ANCHORS = ("2020-08-12", "2020-08-19", "2020-08-26", "2020-09-02")
VALIDATION_ANCHOR = "2020-09-09"
FINAL_START = date(2020, 9, 16)
NUMERIC_FEATURES = [
    "u_tx7", "u_tx28", "u_tx90", "i_buyers7", "i_buyers28", "i_buyers90",
    "ui_tx7", "ui_tx28", "ui_tx90", "u_recency", "i_recency", "ui_recency",
    "item_price28", "user_price28", "affinity_type28", "affinity_colour28",
    "global_rank", "user_recent_rank",
]
CATEGORICAL_FEATURES = [
    "product_type_no", "colour_group_code", "department_no", "index_code",
    "garment_group_no",
]
HYPERPARAMETERS = dict(
    iterations=150, depth=6, learning_rate=0.05, l2_leaf_reg=10,
    loss_function="Logloss", random_seed=2026, thread_count=2,
    task_type="CPU", verbose=False, allow_writing_files=False,
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cohort_key(customer: str, seed: int) -> str:
    return hashlib.sha256(f"{customer}:{seed}".encode("utf-8")).hexdigest()


def select_eligible_users(events, anchor: date, limit: int, seed: int = 2026):
    """Small pure oracle for the SQL's history-only cohort definition."""
    eligible = {u for day, u, _ in events
                if anchor - timedelta(days=90) <= day < anchor}
    return sorted(eligible, key=lambda u: (cohort_key(u, seed), u))[:limit]


def average_precision(predictions, truth, k=12):
    truth = set(truth)
    if not truth:
        return 0.0
    hits, total, seen = 0, 0.0, set()
    for rank, article in enumerate(predictions[:k], 1):
        if article in truth and article not in seen:
            hits += 1
            total += hits / rank
        seen.add(article)
    return total / min(k, len(truth))


def summarize_predictions(predictions, targets, candidates, k=12):
    """All truth survives, including purchases absent from the candidate set."""
    ap, recall, oracle, covered, positive = [], [], [], 0, 0
    hits_total, targets_total = 0, 0
    for user, truth in targets.items():
        truth = set(truth)
        if not truth:
            continue
        positive += 1
        pred = predictions.get(user, [])[:k]
        hits = len(set(pred) & truth)
        available = len(set(candidates.get(user, [])) & truth)
        ap.append(average_precision(pred, truth, k))
        recall.append(hits / len(truth))
        oracle.append(min(available, k) / min(len(truth), k))
        covered += int(available > 0)
        hits_total += available
        targets_total += len(truth)
    n = len(targets)
    mean = lambda values: sum(values) / len(values) if values else None
    return {
        "queries": n, "positive_queries": positive, "empty_target_queries": n - positive,
        "map_at_12_conditional": mean(ap), "recall_at_12_conditional": mean(recall),
        "map_at_12_all_queries_empty_zero": sum(ap) / n if n else None,
        "recall_at_12_all_queries_empty_zero": sum(recall) / n if n else None,
        "candidate_query_coverage_conditional": covered / positive if positive else None,
        "candidate_target_coverage_micro": hits_total / targets_total if targets_total else None,
        "oracle_map_at_12_conditional": mean(oracle),
        "distinct_query_target_pairs": targets_total,
    }


@dataclass
class Collection:
    numeric: object
    categorical: object
    labels: object
    weights: object
    users: object
    articles: object
    targets: dict
    population: dict


def build_collection(connection, anchor: str, user_limit: int, seed=2026):
    """Only temporary relations are written; source tables remain read-only."""
    import numpy as np

    cutoff = date.fromisoformat(anchor)
    if cutoff + timedelta(days=7) > FINAL_START:
        raise ValueError("Anchor would inspect the reserved final period")
    if user_limit < 1:
        raise ValueError("user_limit must be positive")
    for table in ("hm_history", "hm_users", "hm_global", "hm_recent", "hm_candidates"):
        connection.execute(f"DROP TABLE IF EXISTS temp.{table}")
    connection.execute("""
        CREATE TEMP TABLE hm_history AS SELECT * FROM transactions
        WHERE t_dat >= ?::DATE - INTERVAL '90 days' AND t_dat < ?::DATE
    """, [anchor, anchor])
    eligible = connection.execute("SELECT count(DISTINCT customer_id) FROM hm_history").fetchone()[0]
    connection.execute("""
        CREATE TEMP TABLE hm_users AS SELECT DISTINCT customer_id FROM hm_history
        ORDER BY sha256(customer_id || ':' || ?), customer_id LIMIT ?
    """, [str(seed), user_limit])
    connection.execute("""
        CREATE TEMP TABLE hm_global AS
        SELECT article_id, row_number() OVER (ORDER BY count(DISTINCT customer_id) DESC,
          article_id) AS global_rank FROM hm_history
        WHERE t_dat >= ?::DATE - INTERVAL '7 days'
        GROUP BY article_id ORDER BY global_rank LIMIT 100
    """, [anchor])
    connection.execute("""
        CREATE TEMP TABLE hm_recent AS SELECT * FROM (
          SELECT h.customer_id, h.article_id, row_number() OVER (
            PARTITION BY h.customer_id ORDER BY max(t_dat) DESC, h.article_id) AS user_recent_rank
          FROM hm_history h JOIN hm_users u USING(customer_id)
          GROUP BY h.customer_id, h.article_id) WHERE user_recent_rank <= 20
    """)
    connection.execute("""
        CREATE TEMP TABLE hm_candidates AS
        SELECT u.customer_id, g.article_id FROM hm_users u CROSS JOIN hm_global g
        UNION SELECT customer_id, article_id FROM hm_recent
    """)
    if connection.execute("SELECT count(*) FROM hm_global").fetchone()[0] < 12:
        raise ValueError("Fewer than 12 global articles; fixed candidate protocol cannot fill top12")
    cats = ", ".join(f"coalesce(a.{name}, '__MISSING__') AS {name}" for name in CATEGORICAL_FEATURES)
    # Aggregates for item/global statistics use all available users, not only the cohort.
    query = f"""
      WITH ua AS (
        SELECT h.customer_id,
          count(*) FILTER(WHERE t_dat >= DATE '{anchor}' - INTERVAL '7 days') u_tx7,
          count(*) FILTER(WHERE t_dat >= DATE '{anchor}' - INTERVAL '28 days') u_tx28,
          count(*) u_tx90, date_diff('day',max(t_dat),DATE '{anchor}') u_recency,
          avg(price) FILTER(WHERE t_dat >= DATE '{anchor}' - INTERVAL '28 days') user_price28
        FROM hm_history h JOIN hm_users USING(customer_id) GROUP BY h.customer_id
      ), ia AS (
        SELECT article_id,
          count(DISTINCT customer_id) FILTER(WHERE t_dat >= DATE '{anchor}' - INTERVAL '7 days') i_buyers7,
          count(DISTINCT customer_id) FILTER(WHERE t_dat >= DATE '{anchor}' - INTERVAL '28 days') i_buyers28,
          count(DISTINCT customer_id) i_buyers90,
          date_diff('day',max(t_dat),DATE '{anchor}') i_recency,
          avg(price) FILTER(WHERE t_dat >= DATE '{anchor}' - INTERVAL '28 days') item_price28
        FROM hm_history GROUP BY article_id
      ), uia AS (
        SELECT h.customer_id, h.article_id,
          count(*) FILTER(WHERE t_dat >= DATE '{anchor}' - INTERVAL '7 days') ui_tx7,
          count(*) FILTER(WHERE t_dat >= DATE '{anchor}' - INTERVAL '28 days') ui_tx28,
          count(*) ui_tx90, date_diff('day',max(t_dat),DATE '{anchor}') ui_recency
        FROM hm_history h JOIN hm_users USING(customer_id) GROUP BY h.customer_id,h.article_id
      ), affinity_type AS (
        SELECT h.customer_id, a.product_type_no, count(*) affinity_type28
        FROM hm_history h JOIN hm_users USING(customer_id) JOIN articles a USING(article_id)
        WHERE h.t_dat >= DATE '{anchor}' - INTERVAL '28 days'
        GROUP BY h.customer_id,a.product_type_no
      ), affinity_colour AS (
        SELECT h.customer_id, a.colour_group_code, count(*) affinity_colour28
        FROM hm_history h JOIN hm_users USING(customer_id) JOIN articles a USING(article_id)
        WHERE h.t_dat >= DATE '{anchor}' - INTERVAL '28 days'
        GROUP BY h.customer_id,a.colour_group_code
      )
      SELECT c.customer_id,c.article_id,
        ua.u_tx7,ua.u_tx28,ua.u_tx90,
        coalesce(ia.i_buyers7,0) i_buyers7,coalesce(ia.i_buyers28,0) i_buyers28,
        coalesce(ia.i_buyers90,0) i_buyers90,
        coalesce(uia.ui_tx7,0) ui_tx7,coalesce(uia.ui_tx28,0) ui_tx28,
        coalesce(uia.ui_tx90,0) ui_tx90,ua.u_recency,
        coalesce(ia.i_recency,91) i_recency,coalesce(uia.ui_recency,91) ui_recency,
        coalesce(ia.item_price28,0) item_price28,coalesce(ua.user_price28,0) user_price28,
        coalesce(atp.affinity_type28,0) affinity_type28,
        coalesce(aco.affinity_colour28,0) affinity_colour28,
        coalesce(g.global_rank,101) global_rank,coalesce(r.user_recent_rank,21) user_recent_rank,
        {cats}
      FROM hm_candidates c JOIN ua USING(customer_id)
      LEFT JOIN ia USING(article_id) LEFT JOIN uia USING(customer_id,article_id)
      LEFT JOIN articles a USING(article_id) LEFT JOIN hm_global g USING(article_id)
      LEFT JOIN hm_recent r USING(customer_id,article_id)
      LEFT JOIN affinity_type atp ON c.customer_id=atp.customer_id AND a.product_type_no=atp.product_type_no
      LEFT JOIN affinity_colour aco ON c.customer_id=aco.customer_id AND a.colour_group_code=aco.colour_group_code
      ORDER BY c.customer_id,c.article_id
    """
    frame = connection.execute(query).fetch_df()
    targets = {row[0]: set() for row in connection.execute("SELECT customer_id FROM hm_users").fetchall()}
    for user, article in connection.execute("""
        SELECT DISTINCT t.customer_id,t.article_id FROM transactions t JOIN hm_users USING(customer_id)
        WHERE t.t_dat >= ?::DATE AND t.t_dat < ?::DATE + INTERVAL '7 days'
    """, [anchor, anchor]).fetchall():
        targets[user].add(article)
    users = frame["customer_id"].to_numpy()
    articles = frame["article_id"].to_numpy()
    labels = np.fromiter((int(a in targets[u]) for u, a in zip(users, articles)), dtype=np.int8)
    per_user_counts = frame.groupby("customer_id")["article_id"].transform("count").to_numpy()
    weights = (1.0 / per_user_counts).astype(np.float32)
    numeric = frame[NUMERIC_FEATURES].to_numpy(dtype=np.float32)
    categorical = frame[CATEGORICAL_FEATURES].to_numpy(dtype=object)
    population = dict(anchor=anchor, horizon_days=7, eligible_history_users=eligible,
                      selected_users=len(targets), requested_users=user_limit,
                      candidate_rows=len(frame), positive_candidate_rows=int(labels.sum()),
                      positive_queries=sum(bool(y) for y in targets.values()),
                      target_pairs=sum(map(len, targets.values())),
                      history_rows=connection.execute("SELECT count(*) FROM hm_history").fetchone()[0])
    return Collection(numeric,categorical,labels,weights,users,articles,targets,population)


def rank_collection(collection, scores=None, heuristic=None):
    """Ties always resolve by the complete string article ID."""
    import numpy as np
    if heuristic:
        global_rank = collection.numeric[:, NUMERIC_FEATURES.index("global_rank")]
        recent_rank = collection.numeric[:, NUMERIC_FEATURES.index("user_recent_rank")]
        scores = -(recent_rank * 1000 + global_rank) if heuristic == "recency" else -(global_rank * 1000 + recent_rank)
    scores = np.asarray(scores)
    if len(scores) != len(collection.users) or not np.isfinite(scores).all():
        raise ValueError("Invalid prediction count or nonfinite scores")
    order = np.lexsort((collection.articles, -scores, collection.users))
    predictions, candidates = {}, {}
    for index in order:
        user, article = collection.users[index], collection.articles[index]
        candidates.setdefault(user, []).append(article)
        top = predictions.setdefault(user, [])
        if len(top) < 12:
            top.append(article)
    return summarize_predictions(predictions,collection.targets,candidates)


def write_report(output: Path, report):
    (output / "report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n")
    lines = ["# H&M initial fixed pilot", "", f"Status: **{report['status']}**", "",
             "Validation: 2020-09-09 inclusive to 2020-09-16 exclusive. No final-period evaluation.", "",
             "```json", json.dumps(report,indent=2,ensure_ascii=False), "```", ""]
    (output / "report.md").write_text("\n".join(lines),encoding="utf-8",newline="\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--train-users",type=int,default=5000)
    parser.add_argument("--validation-users",type=int,default=20000)
    parser.add_argument("--wall-seconds",type=int,default=1800)
    args = parser.parse_args(argv)
    if min(args.train_users,args.validation_users,args.wall_seconds) < 1:
        parser.error("Population and wall limits must be positive")
    args.output.mkdir(parents=True,exist_ok=False)
    start = time.monotonic()
    report = dict(status="running", protocol=dict(train_anchors=list(TRAIN_ANCHORS),
        validation_anchor=VALIDATION_ANCHOR,horizon_days=7,reserved_final_start=FINAL_START.isoformat(),
        cohort="SHA256(customer_id + ':' + 2026), history activity in prior90d; before labels",
        candidates="top100 articles by distinct buyers7d UNION last20 distinct user articles90d; ties article_id ASC",
        candidate_policy="no target injection, no seen-item filtering; fullY retained",
        features=NUMERIC_FEATURES+CATEGORICAL_FEATURES,
        article_snapshot_assumption="semantic article attributes treated as static; historical availability assumed",
        customer_snapshot="excluded",sample_weights="1 / candidate count per query",
        hyperparameters=HYPERPARAMETERS,selection="fixed150 trees; no eval_set, early stopping or hyperparameter search"),
        caveats=["Single seed, single validation week, sampled users; no claim of automated-feature benefit.",
                 "MAP conditional on future purchasers; all-query empty-target-zero result also reported.",
                 "Kaggle public/private leaderboard populations and dates differ; scores are not comparable.",
                 "Candidate coverage limits achievable ranking; repeated transactions retained as events.",
                 "Wall checks occur between stages and CatBoost iterations; external process limit is recommended."])
    connection = None
    try:
        import duckdb
        import numpy as np
        from catboost import CatBoostClassifier, FeaturesData, Pool

        def check_wall():
            if time.monotonic() - start > args.wall_seconds:
                raise TimeoutError("Pilot exceeded declared wall limit")

        report["source"] = dict(database=args.database.resolve().as_posix(),
                                  sha256=file_sha256(args.database),
                                  bytes=args.database.stat().st_size)
        report["runtime"] = dict(python=sys.version,platform=platform.platform(),
            packages={name:importlib.metadata.version(name) for name in ("duckdb","numpy","catboost","pandas")},
            script_sha256=file_sha256(Path(__file__)),wall_limit_seconds=args.wall_seconds)
        revision = subprocess.run(["git","rev-parse","HEAD"],cwd=Path(__file__).resolve().parent,
                                  capture_output=True,text=True,check=False)
        report["runtime"]["git_revision"] = revision.stdout.strip() if revision.returncode == 0 else None
        connection = duckdb.connect(str(args.database.resolve()),read_only=True)
        connection.execute("SET threads=2")
        connection.execute("SET memory_limit='4GB'")
        duplicate_articles = connection.execute("SELECT count(*)-count(DISTINCT article_id) FROM articles").fetchone()[0]
        if duplicate_articles:
            raise ValueError("articles must contain exactly one row per article ID")
        training = []
        report["training_populations"] = []
        for anchor in TRAIN_ANCHORS:
            check_wall()
            part = build_collection(connection,anchor,args.train_users)
            report["training_populations"].append(part.population)
            training.append((part.numeric,part.categorical,part.labels,part.weights))
            del part
            write_report(args.output,report)
        check_wall()
        numeric = np.concatenate([p[0] for p in training])
        categorical = np.concatenate([p[1] for p in training])
        labels = np.concatenate([p[2] for p in training])
        weights = np.concatenate([p[3] for p in training])
        del training
        if len(np.unique(labels)) != 2:
            raise ValueError("Training candidate labels need both classes")
        pool = Pool(FeaturesData(num_feature_data=numeric,cat_feature_data=categorical,
                    num_feature_names=NUMERIC_FEATURES,cat_feature_names=CATEGORICAL_FEATURES),
                    label=labels,weight=weights)
        class WallCallback:
            def after_iteration(self, info):
                return time.monotonic() - start <= args.wall_seconds
        model = CatBoostClassifier(**HYPERPARAMETERS)
        model.fit(pool,callbacks=[WallCallback()])
        check_wall()
        if model.tree_count_ != HYPERPARAMETERS["iterations"]:
            raise RuntimeError("Fixed-tree fit incomplete")
        model.save_model(str(args.output / "manual.cbm"))
        del pool,numeric,categorical,labels,weights
        validation = build_collection(connection,VALIDATION_ANCHOR,args.validation_users)
        report["validation_population"] = validation.population
        check_wall()
        val_pool = Pool(FeaturesData(num_feature_data=validation.numeric,
                        cat_feature_data=validation.categorical,num_feature_names=NUMERIC_FEATURES,
                        cat_feature_names=CATEGORICAL_FEATURES))
        scores = model.predict_proba(val_pool)[:,1]
        report["validation_metrics"] = {
            "manual_catboost":rank_collection(validation,scores=scores),
            "recency":rank_collection(validation,heuristic="recency"),
            "popularity":rank_collection(validation,heuristic="popularity"),
        }
        check_wall()
        report["status"] = "completed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = {"type":type(exc).__name__,"message":str(exc)}
    finally:
        if connection is not None:
            connection.close()
        report["elapsed_seconds"] = round(time.monotonic()-start,3)
        write_report(args.output,report)
    print(json.dumps({"status":report["status"],"report":(args.output/"report.json").resolve().as_posix()}))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
