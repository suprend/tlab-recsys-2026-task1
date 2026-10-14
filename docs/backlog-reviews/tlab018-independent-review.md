# TLAB-018: independent code/fault review

15 октября 2026. **CHANGES_REQUESTED, code-only.** Resource-seal исправление принято по независимым faults; найден отдельный блокирующий пробел механической lineage. Реальные accepted017 collections не читались, source scans/fits/regeneration/acceptance writes не выполнялись. Все изменяемые fixtures находились во временных каталогах; три reviewed repo-файла остались неизменными.

Проверенная freeze: `scripts/verify_development.py` SHA256 `9d0e30c61def76206f150054566399433357e401c22a0a7a9f870e5ba7282bb6`; tests `5373fe2d99e0cca215f2b34df1cbd2bbf6809a38f97e36fb8ebdd7a7b2988c5d`; workflow `4398525b95544e5c7ac320af61e7df6d60becfb73246031279a4db855fc53507`. Все три digest сверены до и после проверки. Это verdict именно данной версии, не acceptance следующего исправления или разрешение real execution.

## P1: scope shard approval не гарантирует Q/C inputs F

В `_lineage`, строки232–235 проверяют структуру/approved/version approval; строки267–269 определяют допустимые F inputs через его произвольный `fingerprints`. После чтения manifests отсутствует проверка, что approval обязательно содержит actual anchor/candidate artifacts и их необходимые code/source inputs. Поэтому равенство F inputs этому approval не доказывает обещанное потребление конкретных Q/C.

Независимый reproducer создал полноценный маленький bundle через unchanged017 producer, затем удалил из первого shard approval hashes **actual queries.parquet и candidates.parquet**. Те же два input keys удалены из F manifest. Заново рассчитаны F identity/run_id, dependent reports, child seals, state и верхние external expectation pins. Содержимое Q/Y/C/F и source не менялось. Результат — **verified**, все QYC/F stages пройдены. Верхний approval по-прежнему закрепляет сами outputs через seals; это не восстанавливает утраченное утверждение о inputs конкретного F run.

Это содержательный provenance gap, а не найденная ошибка числовых данных: independent source comparison действительно проходит. Но такой F identity не соответствует pinned producer contract. В `scripts/heuristic_baselines.py:206` функция `verify_accepted_inputs`, используемая manual_features, требует accepted Q/C artifact fingerprints; отсутствующие pins там отвергаются до materialization. Verifier объявляет mechanical child lineage корректной для bundle, который этот producer path принять не мог бы. Свежие hashes не должны легализовать такую структуру.

Минимальное исправление — самостоятельно построить обязательный upstream pin map из проверенных anchor/candidate manifests, seals, source и code; потребовать его наличия с exact values в shard approval. Если выбран exact14-pin policy, сравнить весь map. Если прежний producer намеренно разрешает дополнительные approved inputs, явно сохранить этот контракт, но обязательные Q/Y/C, upstream manifests/reports/code/source не могут исчезнуть. Затем проверить точный F input map как это mandatory/allowed approval плюс registry, approval-file hash и единственная selection definition. Regression должен свежо reseal всю цепочку, а не остановиться на старом digest mismatch.

Reproducer: `tlab018-independent-lineage-faults.py`; evidence: `tlab018-independent-lineage-fault-results.json`. Авторский rewrite_output не использовался.

## P2: upstream IDs child reports не сверяются

Строка243 связывает только собственный report.run_id с manifest/seal. Независимые свежо resealed faults поменяли отдельно candidate report `anchor_run_id`, feature report `anchor_run_id` и feature report `candidate_run_id` на другой64hex ID. Все три получили **verified**. Manifest inputs и feature selection сохраняют истинную связь, поэтому это слабее P1; однако report provenance противоречит обещанному проверяемому lineage. Проверить candidate report anchor ID и оба feature report upstream IDs относительно actual am/cm. Это маленькое дополнение того же mechanical gate, без source scans и нового framework.

## Что выдержало проверку

Read-only code review подтверждает exact identity→execution source/registry/code/physical phase binding, строгую manual18 registry, phase/shard cover, pinned child code/input sets, final rehash всех ожиданий. Common JSON/protocol validators не вычисляют expected values. Q/Y/C строятся собственными SQL relations до label conditioning: strict past eligibility/bottom SHA, полный24h Y с multiplicity/cold diagnostics, distinct-buyer popularity, recent ties, union/no-refill. Bidirectional EXCEPT ALL ловит не только counts.

F проверяет полный C rowset/retrieval fields и query keys, schema/order/types, ranges/missing flags. Python formula oracle читает source rows, не вызывает producer category/counter/compiler helpers; latest global all-user bucket сохраняет known+NULL ambiguity, category numerators исторические, denominator вне C, recency/ages используют весь наблюдаемый prefix. Но metadata и18 values проверяются только на deterministic sample. Объявленный sampled scope честен; малые fixtures с8F rows не доказывают exhaustive реальные F. Zero-Y, empty-C и полностью пустой upstream failure различены; последний не превращён в фиктивный положительный pass.

Собственные freshly resealed faults независимо поймали потерю fullY, изменённые Q diagnostics/recent timestamp, coverage, age и category denominator. После fake close wall+700/CPU+700/RSS536870913 возвращается failed; close error и недоступный counter сохраняют partial evidence. Совмещённые primary error и close failure оставляют primary gate первым, cleanup error — secondary; отсутствующая RSS остаётся null. Таким образом прежний cleanup P1 закрыт, реальных sleep/allocations за пределами cap не было.

Независимый CLI byte/inventory snapshot до/после default запуска совпал; traversal/symlink escape rejected. Попытка DELETE в **synthetic** attached source получила engine read-only error, после чего обычная проверка прошла. Никакой реальный source write не предпринимался. Optional evidence и regeneration не трактуются как review approval.

## Actual evidence и следующий gate

Авторские25 scoped tests воспроизведены: PASS12,147s. Отдельно выполнен21 собственный synthetic case в трёх invocations: общий измеренный wall6,177442s, processCPU6,784151s, maximum process peakRSS142262272bytes,0fits. В21case входят четыре неожиданных verified lineage faults; их нельзя считать passed checks. Авторский suite CPU отдельно не измерялся и в эти числа не включён.

Основной helper/evidence: `tlab018-independent-faults.py`, `tlab018-independent-fault-results.json`; safety: `tlab018-independent-safety.py`, `tlab018-independent-safety-results.json`. Tiny producer fixture используется только для получения входного bundle; собственные mutations/resealing/fault assertions независимы от test_verify_development.py. После адресного fix нужны новая exact freeze и повтор этих четырёх lineage faults плюс healthy/resource cases. Real execution, clean-environment installation, fresh-source regeneration,009 support и acceptance-writing остаются отдельными scopes.
