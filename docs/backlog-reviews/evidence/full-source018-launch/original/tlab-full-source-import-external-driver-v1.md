# Full-source018 external driver V1 — source proposal, no execution authority

The fixed TMP driver calls the already accepted V6 `supervise()` exactly once. It binds the prepared project Python3.12 environment, requires its own `-I -B`, and builds only:

```
/Users/mdpospelov/tlab-recsys-2026/.venv/bin/python -I -B /Users/mdpospelov/tlab-recsys-2026/scripts/run_source_import.py --request /Users/mdpospelov/tlab-recsys-2026/artifacts/reproduction/requests/oct2019-full-018-20261015-once.json --expected-request-sha 17edb3954caed6cd409765e870ef8ec547bfc407e30f0e47f5d1df92f553219c
```

This is a documented bound command, **not a command to run now**. The staged request is still absent. The driver is not a smoke check; an actual invocation can consume its fixed TMP namespace and the inner owner's original project claim. Root must separately approve exact current source/request/operation and authenticate the driver's entry bytes before launch.

`ENTRY_MONOTONIC` is captured immediately after importing only `time`. Fixed global7200CPU/10800wall/8GiB sampled limits include this original entry/preparation plus the supervised owner. The accepted inner request ceilings are unchanged; outer overhead may stop it earlier. The driver verifies bounded raw request/owner/kernel/lock/project bytes, refuses existing fixed outputs or original inner output/claim, compiles the exact raw V6 SHA snapshot without a bytecode loader, then uses its generic call. Preparation reads no archive, DB, model or source table.

Fixed exclusive TMP files:

- `/tmp/tlab-full-source018-20261015-once-owner.stdout-stderr.log`: V6's combined owner stdout/stderr, opened exclusively by V6.
- `/tmp/tlab-full-source018-20261015-once-process-receipt.json`: original returned supervisor report or original exception cleanup evidence, retained verbatim as nested JSON; no changed scope/status/reap/unknown/exit flags.
- `/tmp/tlab-full-source018-20261015-once-driver.stdout.json`: normal process return still pending external owner-output and full-exit acceptance.
- `/tmp/tlab-full-source018-20261015-once-driver.error.json`: driver failure, no automatic retry; original fixed outputs remain untouched.

An already occupied namespace produces console failure without creating mixed new receipts. A new preflight failure records no supervision attempt. A supervisor exception retains its attached cleanup evidence, including known reaping/exit or unknown nested work. A returned failure stays a driver failure. The V6 report's historical `synthetic_harness_process_supervision` scope and `worker_ledger_verified=False` are deliberately preserved; this driver does not claim that the imported real source or inner worker ledger was independently accepted.

Root later wraps the fresh driver with `/usr/bin/time -l` and independently accepts the complete driver exit and inner owner/worker ledger. V6's output serialization/driver exit tail is not measured by the driver itself; the external observer must cover it and reject overall cap violations. Sampled RSS is not a hard allocation guarantee. No new containment framework or claim about unseen/orphan processes is added.

Actual limited checks: initial11 pure/mocked methods PASS0.007s; after adding the previously uncovered full preflight cases,14 methods PASS0.010s. These are unittest-reported body times, not external whole-lifetime receipts. Tests mock the supervisor call and process/resource observations, exercise full fixed preflight mutations, preserve failure/reap/unknown states, verify same-snapshot raw compilation, and inspect the actual pinned V6 function's AST signature without importing/instantiating its backend. No supervisor/owner/process/native/SQL/archive/fit operation ran. No project/request/claim/output staging occurred. The four current accepted code/config fingerprints, original proposal and V6 match exact expected hashes. Git status was clean and proposed project request/output/claim absent at09:16:27UTC.

Independent review is pending. Exact source/test/dependency pins and all restrictions are in the neighboring freeze JSON. Neither this document nor that freeze issues a grant.
