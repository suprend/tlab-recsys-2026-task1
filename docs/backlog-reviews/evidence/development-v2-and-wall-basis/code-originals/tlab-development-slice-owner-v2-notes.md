# V2 source-only typed9 repair

V1 source, tests, notes and freeze remain byte-exact and immutable. V1 is not granted for runtime: its fixed consumer schema used price DOUBLE, while the exact accepted importer evidence declares DECIMAL(12,2). That would reject the accepted source before reaching the reviewed core.

V2 owner differs from V1 by exactly one literal replacement: `('price', 'DOUBLE')` becomes `('price', 'DECIMAL(12,2)')`. No other owner code, request vocabulary, resource handling, authority boundary, core or runtime behavior was changed.

The new regression reads only the2509-byte accepted kernel JSON at SHA08343988dc77c388abc7378ae99fba207b69672c2870bf5759c906f98edc22ff. It generates the complete schema from the evidence's schema rows and cross-checks independent profile fields/types. The consumer receives those rows through a mocked DESCRIBE result: frozenV1 must reject with its exact schema error before the core call; V2 must pass schema admission and reach the patched reviewed-core boundary. Neither branch opens a DB or executes native code. No owner constant is used to build the oracle.

All21 pure/mock tests pass with30CPU/60wall fences. The final log reports0.03492wall/0.03399CPU seconds, native calls0, actual DB/model/Parquet/NPZ opens0 and children0. Literal combined core+V2 source compiles and has no protected core global collisions or midfile future import. The immutable core remains SHA cc5a5779199636c2336b2bc0edcb8b31ff496d2e6edf78ed48bfd5f8f3982e8f.

This repairs only the confirmed type mismatch. Independent Root review, narrow handoff adoption, sole-publisher integration, exact original request/environment/V6 dispatch and separately authorized bounded runtime remain outstanding. Mandatory all-keyed parity and complete external exit/reap/tail/output acceptance still share the same future stage cap. No runtime authority or actual output acceptance was issued.
