# Full-source018 driver V2 — narrow interface repair, still no execution grant

Root found that V1's absolute `--request` value was rejected by the actual accepted source owner's `main → run_owner → consume → read_json → local` boundary. No real owner was launched. V1 source/tests/freeze/description remain unchanged.

V2 changes exactly one source expression: the CLI value is `REQUEST.relative_to(PROJECT).as_posix()`, yielding `artifacts/reproduction/requests/oct2019-full-018-20261015-once.json`. The absolute fixed REQUEST path and its exact original SHA remain unchanged for metadata/hash checks. The owner runs with cwd PROJECT. Supervisor V6,7200CPU/10800wall/8GiB sampled limits, exclusive outputs, all original failure/reap/unknown flags, no retry and pending external acceptance remain unchanged.

A new pure interface regression compiles only the actual pinned owner's `need`/`local` AST functions; it does not import owner code or launch the owner. The V1 *actual command* fails with `ValueError: Normalized project-relative path required` in the preserved RED log. The V2 actual command passes `local(..., existing=False)` in the GREEN log. Filesystem observations are mocked, so no request or claim is staged. The author suite also retains V1 as a negative consumer-interface test and V2 as a positive one, rather than merely asserting a mirrored command list.

Actual checks:16 pure/mocked methods PASS0.020s; terminal author-test call exit0. V2 interface probe terminal exit0. The RED log records the original unhandled ValueError; its first tool wrapper printed only redirected output and did not retain a separate exit-code metadata object. No owner/supervisor/backend/archive/SQL/native operation, project write, request staging, claim, grant or refill occurred. Exact V1 pins and fixed absent paths are rechecked in the V2 freeze.

Independent rereview is assigned to `/root/six_role_harness`; code remains pending that review and Root's concrete launch decision. Nothing here grants execution.
