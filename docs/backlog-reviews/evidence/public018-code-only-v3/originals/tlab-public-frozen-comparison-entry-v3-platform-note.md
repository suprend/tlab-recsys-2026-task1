# Entry-only V3: platform metadata must not spawn

V2 entry was preserved at9fed90517ab3637640343badae762432d464de50d627a12f0fa93be1ece39106. V3 changes ONE report expression: `platform.platform()` → `sys.platform + '-' + platform.machine()`. Source-only inverse AST comparison proves all other entry logic identical; recipe/tests/doc and V2 freeze are unchanged. No new test mode, framework, scientific choice or grant is added.

New entry `/tmp/tlab-reproduce-frozen-comparison-v3.py` SHAad27d69662e85a647c34c5853b64213a0526bf509e84f4dd639a7e93acf02a85. Diff `/tmp/tlab-public-frozen-comparison-v2-v3-entry.diff` SHAc767698b46268b768a6a89935ef223fa3669180ce75f39de1f45654e1fd44472. Freeze `/tmp/tlab-public-frozen-comparison-entry-freeze-v3.json` SHAe363c2d67ac0c8a56e2d25cd3b610f76707206f72c7043a6cd5ee2bb295cbac1.

Exact local primary source: `/Users/mdpospelov/.local/share/uv/python/cpython-3.12-macos-aarch64-none/lib/python3.12/platform.py` (hash in freeze).

-1220 `platform()` definition;1245 unpacks `uname()` into six fields.
-862–867 `uname_result.__iter__` includes lazy `.processor`;858–860 `.processor` calls `_Processor.get()`.
-796–801 `_Processor.get` selects `.from_subprocess` on platforms without a dedicated method;819–835 includes `subprocess.check_output(['uname','-p'],...)` at828–832.
-1287–1289 generic platform formatting can also call `architecture(sys.executable)`; `_syscmd_file` at662–674 invokes the `file` command. These are optional metadata operations, not ML work, but they are descendants under a strict zero-child contract.
-1017–1025 `machine()` directly returns `uname().machine`; it does not iterate `uname_result` or access `.processor`.891–988 `uname()` on supported Linux/macOS uses the native `os.uname()` five-field result at910 and returns named fields. The public CLI already requires Linux/macOS RSS support (Windows via WSL), so unsupported-platform fallbacks are not a promised zero-child route. `sys.platform` and `platform.python_version()` use in-process metadata.

Prior author result fields `children_spawned=0` were self-declared without process audit instrumentation. Preserve their exact bytes and costs, but treat zero-child claims as UNMEASURED/UNKNOWN. Source makes optional descendants possible; no exact previous child count or actual spawn is inferred, and no old result is silently rewritten. No actual source/model/target/SQL/ML/native validation or subprocess probe was performed for this note.

The prepared engineering integration must use exact V3, a process/network audit guard installed before native/core imports, and hard-fail ANY attempted process spawn. No platform stub, prewarmed processor/platform cache or caught-metadata-denial exemption is permitted. Root's proposed20CPU/30wall operation remains unissued/unspent; Root will decide only after independent B review of this newly identified source path and fix. A may check the literal one-line/inverse-AST science preservation.
