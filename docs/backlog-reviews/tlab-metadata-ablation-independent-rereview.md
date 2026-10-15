# metadata_ablation narrow rereview — ACCEPT CODE ONLY

2026-10-15. Новый exact freeze принят в узком code/fault scope: первоначальный P1 terminal-decision mismatch закрыт. Это **не** execution approval, actual matrix/Pool/model acceptance или самостоятельная проверка176/114-pin real receipts. Ни actualfull009 outputs, ни реальные008 scores/models, ни raw source не открывались.0native Pool/fit,0actual matrices/scans/approval writes. Existing policy/budget не расширены.

| Файл | SHA256 до/после |
|---|---|
| scripts/metadata_ablation.py | 35733f2f9ae7991072baff197d839681a8021b3f3ba54850da8c170818ff047a |
| tests/test_metadata_ablation.py | 066595311975b5d5876d96e083011798577068add7a99758f8ffdf0681d51dbf |
| docs/experiments/metadata-ablation.md | 96008b1c1cd9d24b6713672028d54db086831ea169dcc9911160f8b812d414bb |

Shared `metadata_price_collection.py` остался59565643f58a3b34bb716c6cc071d7e1802d79aaf0b707e1537459b0a5377afa. Fix локален: `AblationAudit` классифицирует body failure до shared seal, а terminal exception после shared seal — через best-effort corrected failed receipt. Resource→base41/no replacement, прочая integrity/API→STOP; оба решения явно retain=false. Первичный exception не заменяется secondary writer error.

## Независимые5narrow cases — PASS

Helper повторно использует **собственные** исходные runtime mutants и synthetic fixture plumbing через selected AST definitions; первоначальные helper/results не исполняются целиком и не переписываются. Matrices/Pool/fit/acceptance planning mocked; tiny real scoring/evaluation используется только для lifecycle outcome. Это не quality evidence.

1. Healthy retained outcome: complete_produced_unreviewed, retain=true, mocked fit1, четыре chunk-loader calls. Как прежде, ни один loader не вызван до существующего global claim.
2. **Исходный terminal manifest MemoryError:** теперь durable failed report имеет base41/retain=false; проброшен исходный MemoryError; consumed claim сохранён.
3. **Исходный final-complete-report OSError:** durable report и existing known-failed marker имеют STOP/retain=false; исходный OSError сохранён. Противоречивого failed+retain=true больше нет.
4. Terminal MemoryError плюс **новый secondary failure исправляющего policy writer**: наружу выходит исходный MemoryError, corrected failed marker сохраняет base41/retain=false и secondary error evidence. Claim не теряется.
5. **Body primary ValueError плюс terminal secondary MemoryError:** сохранена identity первичного exception, report error_type=ValueError/STOP/retain=false; secondary terminal evidence сохранено. Resource secondary не переименовывает integrity primary в fallback.

После первых четырёх trajectories собственная проверка повторно вызывает consume_claim с другим runID/output directory: FileExistsError, байты первого claim неизменны. Нового model.fit/подготовки второго массива нет. Это direct global-claim no-retry evidence; изменённый proposal не получает refill.

16author tests/fullsuite не повторялись: scope требует только новые meaningful regressions, первоначальные13 уже reproduced. CPU/wall/RSS hard-cap guarantees не добавлены. Локальный failure-persistence tail остаётся явно вне shared final-receipt snapshot и обязан измеряться external parent process ledger; недоступный filesystem может препятствовать durable rewrite, но failed status/knownfailed marker запрещает promotion. Fixed count writer attempts и preservation primary не обещают отмену блокирующего OS write.

Raw `tlab-metadata-ablation-rereview-faults.py` и `tlab-metadata-ablation-rereview-results.json`:5PASS,1.226175wall/1.225858CPU/peakRSS136462336bytes. Internal timer после imports; эти числа не выданы за fresh-process total. No new native fitting.

Первоначальные immutable evidence SHA совпали с precheck:

- review: ecbbdd1fd72b1c5d23394ee7effd2217bfde4bb178f62051305b94291cf233bf;
- helper: bcd690167c2107e97da3a41497f88ea47bb4a89726cf3a1f5ea88c4210d7119e;
- results:43babc13761229ae832013101a2a41af1d9d1b1e33ce5d4e167f81d37ac1c769.

Actual control/full-export binding, exact6000 BASEONLY/mixed-prefix equivalence, full4000 score/fullY replay, actual TRAIN4096/noCTR/effective parameters и external exact execution approval остаются обязательными gates будущего запуска. Этот verdict закрывает только frozen code defect и не авторизует новый fit самостоятельно.
