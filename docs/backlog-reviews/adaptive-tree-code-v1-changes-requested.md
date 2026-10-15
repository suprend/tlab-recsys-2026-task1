# Адаптивное обучение V1: исправление проверки output path

Root прочитал две независимые wholeCODE проверки. Correctness review B не нашёл supportedP1/P2 в своём scope. Resource/lifecycle reviewer нашёл один P2: producer сначала resolve() пути output теряет исходный literal namespace; dangling symlink может перенаправить once-output и допустить платные fits до последующего отказа verifier. Это source-only finding; actual alias fixture/fit не запускались.

Автор ExecutionScopeAudit готовит узкую V2 проверку literal exists/is_symlink до resolve и один stdlib regression; SourceImportReview обновляет только два связанных SHA. V1 producer/request/verifier не приняты и не устанавливаются. Прежний synthetic06f5 PASS остаётся доказательством selector semantics, а не разрешением native обучения.

Отдельный thinV6transport review не нашёл supportedfinding: восемь прямых/обратных transformations exact, proposal approved=false/unissued. Это не wholeproducer acceptance и не runtime proof. Proposed4200CPU/3600wall/12GiB и subdivision producer3500/2700/verifier600/800/tails100/100 остаются prospective; native feasibility неизвестна.

Следующий путь: V2 закрывает P2 → те же reviewers делают focused recheck → Root принимает source и устанавливает только в свой TMPclone → Root отдельно решает bounded2-fit runtime. Canonical publisher пишет только project/Git/docs; sharedclone ему не передан. Нет новых теоретических prerequisites.

[Девять точных review/ledger/freeze originals](evidence/adaptive-tree-code-v1-changes-requested/publication.json). Original015/018 done14/19, accepted report/DOC/publicfixed300 неизменны; новая2400-dependent-check ветвь exploratory/unrun/ungranted.
