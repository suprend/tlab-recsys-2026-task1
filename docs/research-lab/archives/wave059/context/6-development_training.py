"""Explicit new-development fit seam; historical trainers are separate contracts."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class DevelopmentFit:
    full_model: object
    selected_model: object
    trained_ceiling: int
    selected_trees: int
    validation_curve: tuple
    validation_support: dict
    training_accounting: dict


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def fit_development(model, train, validation, *, max_iterations, check):
    """Fit one fresh numeric CPU Logloss classifier, then select/shrink a copy.

    Trusted caller owns prepared-data lineage and whole-operation supervision.
    The supplied unfitted full model is fitted once and never itself shrunk.
    No eval_set, native OD, init_model, fit kwargs, refit or ceiling fallback.
    """
    _require(train is not None and validation is not None, 'Train and validation are required')
    _require(type(max_iterations) is int and max_iterations > 0, 'Explicit positive tree ceiling required')
    _require(callable(check), 'Caller-owned whole-operation guard required')
    check()
    from catboost import CatBoostClassifier, Pool
    from scripts import train_baselines as b
    from scripts.adaptive_tree_selection import select_best_tree
    _require(type(model) is CatBoostClassifier and not model.is_fitted(), 'Fresh exact CatBoostClassifier required')
    params = model.get_params()
    allowed = {'iterations','depth','learning_rate','l2_leaf_reg','random_seed','task_type','thread_count',
               'loss_function','use_best_model','allow_writing_files','verbose','boosting_type','bootstrap_type',
               'random_strength','boost_from_average','leaf_estimation_method','leaf_estimation_iterations',
               'leaf_estimation_backtracking'}
    _require(type(params) is dict and set(params) <= allowed, 'Unsupported constructor option or native stopping/alias')
    _require(type(params.get('iterations')) is int and params['iterations'] == max_iterations
             and params.get('loss_function') == 'Logloss' and params.get('task_type') == 'CPU'
             and type(params.get('thread_count')) is int and params['thread_count'] == 2
             and params.get('use_best_model') is False and params.get('allow_writing_files') is False,
             'Explicit CPU/Logloss/two-thread/ceiling/no-native-selection parameters required')
    for data in (train, validation):
        _require(type(data) is b.Prepared and bool(data.queries), 'Nonempty trusted Prepared query population required')
        _require(data.x.dtype.name == 'float32' and data.group.dtype.name == 'int32'
                 and data.items.dtype.name == 'int64' and data.y.dtype.name == 'int8', 'Numeric prepared dtypes required')
    _require(train.feature_names == validation.feature_names and bool(train.feature_names)
             and len(train.feature_names) == len(set(train.feature_names)), 'Matching ordered numeric features required')
    _, positive, negative, _, weights, accounting = b.group_accounting(train)
    _, _, _, _, _, validation_accounting = b.group_accounting(validation)
    _require(len(train.group) > 0 and sum(positive) > 0 and sum(negative) > 0, 'Nonempty binary training support required')
    _require(validation_accounting['positive_fullY_queries'] > 0, 'Validation needs positive full targets before fitting')
    check()
    pool = Pool(train.x, label=train.y, weight=weights, feature_names=train.feature_names, thread_count=2)
    callback = b._BudgetCallback(check)
    check()
    try:
        model.fit(pool, callbacks=[callback])
    except BaseException as error:
        if callback.failure is not None and callback.failure is not error:
            try: callback.failure.add_note('Native fit also raised '+type(error).__name__)
            except BaseException: pass
            raise callback.failure from error
        raise
    if callback.failure is not None:
        raise callback.failure
    check()
    _require(model.is_fitted() and type(model.tree_count_) is int and model.tree_count_ == max_iterations
             and model.feature_names_ == train.feature_names, 'Fit must complete the entire declared tree range')
    _require(model.get_cat_feature_indices() == model.get_text_feature_indices()
             == model.get_embedding_feature_indices() == [], 'Only numeric CPU models are supported')
    best, curve, support = select_best_tree(model, validation, maximum=max_iterations, check=check)
    _require(type(best) is int and 1 <= best <= max_iterations and len(curve) == max_iterations
             and all(type(v) is float and math.isfinite(v) for v in curve), 'Complete selector result required')
    _require(support['fullY_positive_queries'] == validation_accounting['positive_fullY_queries'], 'Every positive validation query required')
    check()
    selected = model.copy()
    _require(type(selected) is CatBoostClassifier and selected is not model, 'Independent native model copy required')
    selected.shrink(best, ntree_start=0)
    _require(type(selected.tree_count_) is int and selected.tree_count_ == best
             and model.tree_count_ == max_iterations and selected.feature_names_ == model.feature_names_ == train.feature_names,
             'Selected copy must preserve the complete original model')
    check()
    return DevelopmentFit(model, selected, max_iterations, best, tuple(curve),
                          dict(support, informative_candidate_groups=validation_accounting['informative_groups']),
                          dict(accounting))
