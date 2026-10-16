# New-training tree-selection entrypoint audit

At HEAD b7607b427a3dd1cd2e88696bb65053a6a122de3e, validation selection is implemented for the NEW adaptive study, not automatically for every callable trainer. No second current, non-frozen development workflow silently fixing300 was verified.

The reusable [select_best_tree](/Users/mdpospelov/tlab-recsys-2026/scripts/adaptive_tree_selection.py:63) accepts an already fitted model. It scores every trained prefix and returns the validation argmax; it neither fits nor shrinks the model. The study explicitly calls it [after each model's fit](/Users/mdpospelov/tlab-recsys-2026/scripts/adaptive_tree_selection.py:230), then [shrinks a copy](/Users/mdpospelov/tlab-recsys-2026/scripts/adaptive_tree_selection.py:243). Its [CLI](/Users/mdpospelov/tlab-recsys-2026/scripts/adaptive_tree_selection.py:304) is a closed accepted-export/report-bound two-fit study, not a general fresh-data trainer; [documentation](/Users/mdpospelov/tlab-recsys-2026/docs/experiments/adaptive-tree-selection.md:17) says so.

Other executable training routes preserve historical contracts:

- [Smoke fitting](/Users/mdpospelov/tlab-recsys-2026/scripts/train_baselines.py:362) uses configured iterations, with default50 and explicit cpu_smoke role; [its owner](/Users/mdpospelov/tlab-recsys-2026/scripts/train_baselines.py:542) predicts after fitting without calling the selector. This parameterized legacy API can consume a new fit approval, so it must not be described as the general adaptive default.
- [Strong019](/Users/mdpospelov/tlab-recsys-2026/scripts/strong_baseline.py:56) trains300 but actually evaluates50/150/300 [validation prefixes](/Users/mdpospelov/tlab-recsys-2026/scripts/strong_baseline.py:382). Calling it wholly unselected fixed300 would be inaccurate.
- [Feature-program016](/Users/mdpospelov/tlab-recsys-2026/scripts/feature_program_experiment.py:77) deliberately inherits trained_iterations/scoring_prefix; [prediction](/Users/mdpospelov/tlab-recsys-2026/scripts/feature_program_experiment.py:441) uses that prefix rather than reselecting per arm.
- Metadata009 and [public frozen reproduction](/Users/mdpospelov/tlab-recsys-2026/scripts/reproduce_frozen_comparison.py:559) intentionally retain fixed historical recipes. They are not evidence that future development should fix300.

Smallest future integration: one explicit development-fit helper requiring train AND validation, with max_iterations as a ceiling, that fits once, calls the existing selector, copies/shrinks, and records trained ceiling versus selected count/curve. Route future non-frozen baseline/manual/program-arm callers through it; missing validation must fail rather than silently choose the ceiling. Keep historical entrypoints/contracts explicit and unchanged. No selector algorithm, historical reselection or new experiment is needed to define this seam.

Nineteen source/metadata pins are unchanged. Source-only audit; no native imports, artifacts/data/models/Y, tests/fixtures/jobs/polls/helpers, publisher contact, Git/project writes or budget/runtime grant. Pending publication question remains untouched.
