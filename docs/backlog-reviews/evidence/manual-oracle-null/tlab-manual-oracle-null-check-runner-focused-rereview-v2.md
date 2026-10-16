# Focused NULL-regression runner rereview V2

P2 closed in the inspected source. No new supported P1/P2 in this narrow delta.

At `/tmp/tlab-manual-oracle-null-check-once-v2.py:75–85`, TimeoutExpired is caught before normal terminal handling. The runner attempts to persist TIMEOUT, timeout_seconds, exact command and available partial stdout/stderr; byte outputs are decoded safely for JSON. A receipt-writing exception is attached as a note, followed by bare rethrow of the original timeout. GREEN cannot start after a RED timeout. No retry is introduced.

The supplied diff matches the actual V1/V2 bytes. Normalizing output/request paths and replacing only the new timeout block restores exact V1 source. Child execution, RED failure classification,13-method GREEN scope, input pins apart from runner rebinding,10CPU/20wall per-child limits and observed-only RSS are unchanged. V1 source/request pins remain intact. V2 source/request/diff freshly match583b583a…/ccb9dd03…/51cbd19f…; AST parse passes.

Static inspection only: no timeout injection, imports, execution, tests/native/SQL/fixtures/helpers/canonical/Git/network/coordinator actions. RED/GREEN remain predicted, not observed. This closes the source finding and issues no runtime grant.
