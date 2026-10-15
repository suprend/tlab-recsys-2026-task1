# Initial model-parameter observer failure

The first independent observer stopped before prediction, because CBM-loaded floating metadata has fewer decimal places than in-memory get_all_params. No producer/model/claim changes or refits followed. Initial3.335586CPU seconds are charged, not reset.

```text
Traceback (most recent call last):
  File "tlab-verify009-model.py", line 111, in <module>
    assert model.tree_count_==50 and model.feature_names_==names+cat_names and params==R['actual_model_parameters']
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError

```

Loaded learning_rate .05000000075 versus .05000000074505806, bayesian_matrix_reg .1000000015 versus .10000000149011612. Narrow float-only rtol1e−8/atol1e−12 observer regression accepts these two deltas and rejects material float/int/bool/string drift. Eight pure checks are in the aggregate evidence. Exact output predictions remain checked at absolute1e−12.
