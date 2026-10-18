"""Label-free H&M feature programs and bounded historical SQL aggregates.

The public registry is generated without a connection or data. ``build_features``
reads transactions/articles and a caller-owned candidate relation, writes only
TEMP hm_f_* relations, and returns features; it never reads outcomes or fits a
model. The caller owns population, candidate selection and evaluation policy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import re


DIMENSIONS = (
    "product_type_no", "colour_group_code", "department_no",
    "garment_group_no", "index_code",
)
WINDOWS = (7, 28, 90)
OPERATIONS = ("count", "share", "recency", "distinct_items")
CATEGORICAL_FEATURES = (
    "product_type_no", "colour_group_code", "department_no", "index_code",
    "garment_group_no",
)
PILOT_NUMERIC_FEATURES = (
    "u_tx7", "u_tx28", "u_tx90", "i_buyers7", "i_buyers28", "i_buyers90",
    "ui_tx7", "ui_tx28", "ui_tx90", "u_recency", "i_recency", "ui_recency",
    "item_price28", "user_price28", "affinity_type28", "affinity_colour28",
    "global_rank", "user_recent_rank",
)
STRONG_ADDITIONS = (
    "affinity_type_share28", "affinity_colour_share28", "affinity_department28",
    "affinity_department_share28", "repeat_share28", "demand7to28",
    "price_compat28", "price_compat28_valid", "affinity_type_recency90",
    "item_price28_missing", "user_price28_missing",
)


@dataclass(frozen=True)
class FeatureDef:
    """A finite feature program; no arbitrary SQL or label expression is accepted."""

    name: str
    group: str
    operation: str
    dimension: str | None = None
    window_days: int | None = None
    formula: str = ""
    missing: str = "zero"
    dtype: str = "float64"

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.name):
            raise ValueError("Feature name must be an SQL identifier")
        if self.group not in ("manual_pilot", "strong_addition", "generated"):
            raise ValueError("Unknown feature group")
        if self.operation not in OPERATIONS + ("manual", "categorical"):
            raise ValueError("Unknown operation")
        if self.dimension is not None and self.dimension not in DIMENSIONS:
            raise ValueError("Unsupported semantic dimension")
        if self.window_days is not None and self.window_days not in WINDOWS:
            raise ValueError("Unsupported historical window")
        if self.operation in OPERATIONS and (self.dimension is None or self.window_days is None):
            raise ValueError("Aggregate programs need a semantic dimension and window")

    @property
    def semantic_key(self):
        if self.operation in OPERATIONS:
            return ("user_attribute", self.dimension, self.window_days, self.operation)
        return ("explicit", self.name)


_ALIASES = {
    ("product_type_no", 28, "count"): "affinity_type28",
    ("colour_group_code", 28, "count"): "affinity_colour28",
    ("department_no", 28, "count"): "affinity_department28",
    ("product_type_no", 28, "share"): "affinity_type_share28",
    ("colour_group_code", 28, "share"): "affinity_colour_share28",
    ("department_no", 28, "share"): "affinity_department_share28",
    ("product_type_no", 90, "recency"): "affinity_type_recency90",
}


def _aggregate_def(name, group, dimension, window, operation):
    formulas = {
        "count": "transaction rows for user with attribute equal to candidate attribute",
        "share": "matching transaction rows / all user transaction rows in the same window",
        "recency": "days from latest matching transaction in the window to cutoff",
        "distinct_items": "distinct matching article_id values in the window",
    }
    return FeatureDef(name, group, operation, dimension, window, formulas[operation],
                      "91 when no matching transaction" if operation == "recency" else "zero")


def feature_registry():
    """Return immutable definitions, including manual/generated semantic dedup."""
    alias_by_name = {name: key for key, name in _ALIASES.items()}
    formulas = {
        **{f"u_tx{w}": f"all user transaction rows in prior {w} days" for w in WINDOWS},
        **{f"i_buyers{w}": f"distinct historical buyers of item in prior {w} days, full population" for w in WINDOWS},
        **{f"ui_tx{w}": f"user-item transaction rows in prior {w} days" for w in WINDOWS},
        "u_recency": "days since latest user transaction in prior90d; absent=91",
        "i_recency": "days since latest item transaction in prior90d; absent=91",
        "ui_recency": "days since latest user-item transaction in prior90d; absent=91",
        "item_price28": "mean price over full-population item transaction rows in prior28d; absent=0",
        "user_price28": "mean price over user transaction rows in prior28d; absent=0",
        "global_rank": "buyers7d descending, article_id ascending; only top100 retained; absent=101",
        "user_recent_rank": "latest user-item date descending, article_id ascending; only top20 retained; absent=21",
        "repeat_share28": "ui_tx28 / u_tx28; zero denominator=0",
        "demand7to28": "(i_buyers7 / 7) / (i_buyers28 / 28); zero denominator=0",
        "price_compat28": "abs(ln(item_price28)-ln(user_price28)); invalid=0",
        "price_compat28_valid": "1 iff both raw historical mean prices are finite and strictly positive",
        "item_price28_missing": "1 iff raw historical item mean price is NULL (zero is observed)",
        "user_price28_missing": "1 iff raw historical user mean price is NULL (zero is observed)",
    }
    definitions = []
    for group, names in (("manual_pilot", PILOT_NUMERIC_FEATURES),
                         ("strong_addition", STRONG_ADDITIONS)):
        for name in names:
            if name in alias_by_name:
                dimension, window, operation = alias_by_name[name]
                definitions.append(_aggregate_def(name, group, dimension, window, operation))
            else:
                missing = "explicit in formula"
                definitions.append(FeatureDef(name, group, "manual", formula=formulas[name], missing=missing))
    for name in CATEGORICAL_FEATURES:
        definitions.append(FeatureDef(name, "manual_pilot", "categorical", dimension=name,
                                     formula="undated article semantic snapshot", missing="__MISSING__", dtype="string"))
    seen = {definition.semantic_key for definition in definitions}
    for dimension in DIMENSIONS:
        for window in WINDOWS:
            for operation in OPERATIONS:
                name = f"auto_{dimension}_{operation}{window}"
                definition = _aggregate_def(name, "generated", dimension, window, operation)
                if definition.semantic_key not in seen:
                    definitions.append(definition)
                    seen.add(definition.semantic_key)
    return tuple(definitions)


def feature_manifest():
    """Stable manifest/digest; constructing this never touches data or labels."""
    registry = feature_registry()
    pilot = list(PILOT_NUMERIC_FEATURES + CATEGORICAL_FEATURES)
    strong = list(PILOT_NUMERIC_FEATURES + STRONG_ADDITIONS + CATEGORICAL_FEATURES)
    generated = [definition.name for definition in registry if definition.group == "generated"]
    payload = {
        "format": "hm-typed-features-v1",
        "source_schema": {
            "transactions": {"t_dat": "DATE", "customer_id": "VARCHAR", "article_id": "VARCHAR", "price": "numeric"},
            "articles": {"article_id": "VARCHAR", **dict.fromkeys(DIMENSIONS, "VARCHAR")},
            "candidates": {"customer_id": "VARCHAR", "article_id": "VARCHAR"},
        },
        "policy": {
            "history": "[cutoff-90days, cutoff); all smaller windows also left inclusive/right exclusive",
            "duplicates": "transaction rows retained; distinct_items distincts only article_id",
            "items": "full historical population, not restricted to candidate users",
            "dimensions": "raw NULL does not match; categorical NULL rendered as __MISSING__ only at output",
            "snapshot_assumption": "article semantic metadata treated as static; historical versions/availability unknown",
            "customer_snapshots": "not used",
            "labels": "not accepted or read; eligibility/selection/final protection owned by caller",
            "empty_history": "counts=0, recency=91, rank caps101/21; candidates preserved",
        },
        "registry": [asdict(definition) for definition in registry],
        "generated_aliases": [
            {"dimension": d, "window_days": w, "operation": op, "manual_name": name}
            for (d, w, op), name in sorted(_ALIASES.items())
        ],
        "feature_sets": {
            "manual_pilot": pilot,
            "strong_manual": strong,
            "generated": generated,
            "strong_plus_generated": strong + generated,
        },
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return {**payload, "digest": hashlib.sha256(serialized.encode("utf-8")).hexdigest()}


@dataclass(frozen=True)
class FeatureResult:
    frame: object
    feature_sets: dict
    registry: tuple[FeatureDef, ...]
    digest: str
    manifest: dict


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("Relation must be a simple SQL identifier")
    if value.lower().startswith("hm_f_"):
        raise ValueError("Candidate relation must not use the engine-owned hm_f_ prefix")
    return '"' + value + '"'


def _require_schema(con, table, required):
    fields = {row[0]: row[1].upper() for row in con.execute(f"DESCRIBE {table}").fetchall()}
    if not required <= fields.keys():
        raise ValueError("Required source columns are missing")
    for key in ("customer_id", "article_id"):
        if key in required and fields[key] != "VARCHAR":
            raise ValueError("Entity keys must have VARCHAR type; numeric IDs lose leading zeros")


def build_features(con, anchor, candidates_table="hm_candidates"):
    """Compute all predeclared features for exactly the caller's unique C pairs.

    ``transactions`` contains DATE t_dat, VARCHAR IDs and numeric price;
    ``articles`` contains unique VARCHAR article_id and the five VARCHAR semantic
    dimensions. Candidate IDs must be non-null VARCHARs with unique pairs.
    Only TEMP hm_f_* tables are replaced. No future label relation is referenced.
    Metadata records absent for a candidate are allowed and never fabricated.
    """
    if isinstance(anchor, date) and type(anchor) is not date:
        raise ValueError("Anchor must be a date, without a time component")
    cutoff = anchor if isinstance(anchor, date) else date.fromisoformat(anchor)
    anchor = cutoff.isoformat()
    candidates = _identifier(candidates_table)
    _require_schema(con, candidates, {"customer_id", "article_id"})
    _require_schema(con, "transactions", {"t_dat", "customer_id", "article_id", "price"})
    _require_schema(con, "articles", {"article_id", *DIMENSIONS})
    # Explicit metadata types avoid implicit coercions that merge semantic codes.
    article_types = {row[0]: row[1].upper() for row in con.execute("DESCRIBE articles").fetchall()}
    if any(article_types[dimension] != "VARCHAR" for dimension in DIMENSIONS):
        raise ValueError("Article semantic dimensions must have VARCHAR type")
    invalid = con.execute(f"SELECT count(*) FROM {candidates} WHERE customer_id IS NULL OR article_id IS NULL").fetchone()[0]
    duplicate = con.execute(f"SELECT count(*) FROM (SELECT customer_id,article_id FROM {candidates} GROUP BY 1,2 HAVING count(*)>1)").fetchone()[0]
    if invalid or duplicate:
        raise ValueError("Candidates need non-null keys and exactly one row per pair")
    if con.execute("SELECT count(*) FROM (SELECT article_id FROM articles GROUP BY 1 HAVING count(*)>1)").fetchone()[0]:
        raise ValueError("Article metadata IDs must be unique")
    con.execute("""CREATE OR REPLACE TEMP TABLE hm_f_history AS
        SELECT t_dat,customer_id,article_id,price FROM transactions
        WHERE t_dat >= ?::DATE-INTERVAL '90 days' AND t_dat < ?::DATE""", [anchor, anchor])
    con.execute(f"CREATE OR REPLACE TEMP TABLE hm_f_users AS SELECT DISTINCT customer_id FROM {candidates}")

    user_exprs = [f"count(*) FILTER(WHERE t_dat >= DATE '{anchor}'-INTERVAL '{w} days') AS u_tx{w}" for w in WINDOWS]
    con.execute(f"""CREATE OR REPLACE TEMP TABLE hm_f_ua AS SELECT h.customer_id,
        {','.join(user_exprs)}, date_diff('day',max(t_dat),DATE '{anchor}') AS u_recency,
        avg(price) FILTER(WHERE t_dat >= DATE '{anchor}'-INTERVAL '28 days') AS user_price28
        FROM hm_f_history h JOIN hm_f_users u USING(customer_id) GROUP BY h.customer_id""")
    item_exprs = [f"count(DISTINCT customer_id) FILTER(WHERE t_dat >= DATE '{anchor}'-INTERVAL '{w} days') AS i_buyers{w}" for w in WINDOWS]
    con.execute(f"""CREATE OR REPLACE TEMP TABLE hm_f_ia AS SELECT article_id,
        {','.join(item_exprs)}, date_diff('day',max(t_dat),DATE '{anchor}') AS i_recency,
        avg(price) FILTER(WHERE t_dat >= DATE '{anchor}'-INTERVAL '28 days') AS item_price28
        FROM hm_f_history GROUP BY article_id""")
    pair_exprs = [f"count(*) FILTER(WHERE t_dat >= DATE '{anchor}'-INTERVAL '{w} days') AS ui_tx{w}" for w in WINDOWS]
    con.execute(f"""CREATE OR REPLACE TEMP TABLE hm_f_uia AS SELECT h.customer_id,h.article_id,
        {','.join(pair_exprs)}, date_diff('day',max(t_dat),DATE '{anchor}') AS ui_recency
        FROM hm_f_history h JOIN hm_f_users u USING(customer_id) GROUP BY h.customer_id,h.article_id""")
    con.execute("""CREATE OR REPLACE TEMP TABLE hm_f_global AS SELECT article_id,
        row_number() OVER(ORDER BY i_buyers7 DESC,article_id) AS global_rank
        FROM hm_f_ia WHERE i_buyers7>0 QUALIFY global_rank<=100""")
    con.execute("""CREATE OR REPLACE TEMP TABLE hm_f_recent AS SELECT customer_id,article_id,
        row_number() OVER(PARTITION BY customer_id ORDER BY ui_recency,article_id) AS user_recent_rank
        FROM hm_f_uia QUALIFY user_recent_rank<=20""")

    for index, dimension in enumerate(DIMENSIONS):
        expressions = []
        for window in WINDOWS:
            condition = f"t_dat >= DATE '{anchor}'-INTERVAL '{window} days'"
            expressions += [
                f"count(*) FILTER(WHERE {condition}) AS n{window}",
                f"count(DISTINCT h.article_id) FILTER(WHERE {condition}) AS d{window}",
                f"date_diff('day',max(t_dat) FILTER(WHERE {condition}),DATE '{anchor}') AS r{window}",
            ]
        con.execute(f"""CREATE OR REPLACE TEMP TABLE hm_f_dim{index} AS
            SELECT h.customer_id,a.{dimension} AS dimension_value,{','.join(expressions)}
            FROM hm_f_history h JOIN hm_f_users u USING(customer_id)
            JOIN articles a USING(article_id) WHERE a.{dimension} IS NOT NULL
            GROUP BY h.customer_id,a.{dimension}""")

    expressions = {}
    for name in PILOT_NUMERIC_FEATURES:
        if name in ("global_rank", "user_recent_rank"):
            alias, fallback = ("g", 101) if name == "global_rank" else ("r", 21)
        elif name.startswith("ui_"):
            alias, fallback = "uia", 91 if name.endswith("recency") else 0
        elif name.startswith("u_") or name == "user_price28":
            alias, fallback = "ua", 91 if name.endswith("recency") else 0
        else:
            alias, fallback = "ia", 91 if name.endswith("recency") else 0
        if not name.startswith("affinity_"):
            expressions[name] = f"coalesce({alias}.{name},{fallback})"
    for definition in feature_registry():
        if definition.operation in OPERATIONS:
            dim = f"d{DIMENSIONS.index(definition.dimension)}"
            window = definition.window_days
            if definition.operation == "count":
                expression = f"coalesce({dim}.n{window},0)"
            elif definition.operation == "distinct_items":
                expression = f"coalesce({dim}.d{window},0)"
            elif definition.operation == "recency":
                expression = f"coalesce({dim}.r{window},91)"
            else:
                expression = f"coalesce({dim}.n{window}::DOUBLE/nullif(ua.u_tx{window},0),0)"
            expressions[definition.name] = expression
    valid_price = "(ia.item_price28>0 AND ua.user_price28>0 AND isfinite(ia.item_price28) AND isfinite(ua.user_price28))"
    expressions.update({
        "repeat_share28": "coalesce(uia.ui_tx28::DOUBLE/nullif(ua.u_tx28,0),0)",
        "demand7to28": "coalesce(4.0*ia.i_buyers7/nullif(ia.i_buyers28,0),0)",
        "price_compat28": f"CASE WHEN {valid_price} THEN abs(ln(ia.item_price28)-ln(ua.user_price28)) ELSE 0 END",
        "price_compat28_valid": f"CASE WHEN {valid_price} THEN 1 ELSE 0 END",
        "item_price28_missing": "CASE WHEN ia.item_price28 IS NULL THEN 1 ELSE 0 END",
        "user_price28_missing": "CASE WHEN ua.user_price28 IS NULL THEN 1 ELSE 0 END",
    })
    for name in CATEGORICAL_FEATURES:
        expressions[name] = f"coalesce(a.{name},'__MISSING__')"
    manifest = feature_manifest()
    ordered = manifest["feature_sets"]["strong_plus_generated"]
    selected = ",".join(f'{expressions[name]} AS "{name}"' for name in ordered)
    dimension_joins = "\n".join(
        f"LEFT JOIN hm_f_dim{i} d{i} ON c.customer_id=d{i}.customer_id AND a.{dimension}=d{i}.dimension_value"
        for i, dimension in enumerate(DIMENSIONS))
    frame = con.execute(f"""SELECT c.customer_id,c.article_id,{selected}
        FROM {candidates} c LEFT JOIN hm_f_ua ua USING(customer_id)
        LEFT JOIN hm_f_ia ia USING(article_id)
        LEFT JOIN hm_f_uia uia USING(customer_id,article_id)
        LEFT JOIN articles a USING(article_id)
        LEFT JOIN hm_f_global g USING(article_id)
        LEFT JOIN hm_f_recent r USING(customer_id,article_id)
        {dimension_joins} ORDER BY c.customer_id,c.article_id""").fetch_df()
    return FeatureResult(frame, manifest["feature_sets"], feature_registry(), manifest["digest"], manifest)
