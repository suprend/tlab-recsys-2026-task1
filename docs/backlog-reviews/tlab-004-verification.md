# TLAB-004: независимое prereview synthetic retrieval

15 октября 2026. **Verdict: accept pending final guard/provenance. Material retrieval findings: 0. Production acceptance не выдана.** Проверены фактические [candidate_pilot.py](../../scripts/candidate_pilot.py), [tests](../../tests/test_candidate_pilot.py), accepted [protocol_manifest.py](../../scripts/protocol_manifest.py), текущий [TLAB-004](../backlog.md) и provisional clock configs. Deadline guard в начале review изменялся Root; окончательное принятие executor/frozen run provenance остаётся отдельным gate.

## Scope и actual tests

Оба retrieval-файла — untracked additions. Проверен полный actual text; пустой обычный Git diff не использован как доказательство отсутствия изменений. Никакие source DB, raw data или real candidate pilots reviewer не открывал и не запускал. Код, repo/Git/dependencies не изменялись.

После priority rereview TLAB-003 выполнена только разрешённая scoped suite:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_candidate_pilot.py -v
Ran 14 tests in 0.254s
OK; exit 0
```

Тесты работают с отдельной in-memory synthetic events/Q/Y и не тренируют модели. На последнем чтении hashes actual files:

```text
scripts/candidate_pilot.py  c6044b683acafb3d7a90d2310037e65c46699d98b640e46cb1a45f4f4314fa70
tests/test_candidate_pilot.py  b50a36f51a600def574f6ec7033d732f2ba439498a55e7787671f65a701432c5
```

Hash фиксирует просмотренную версию, не объявляет guard замороженным и не заменяет final provenance check.

## Подтверждённая retrieval-семантика

**Глобальный past-only и grain.** Для каждого фактического anchor счётчики фильтруются `[t−W,t)`. Популярность — distinct purchase users per product, не число purchase rows; дубли одного покупателя не увеличивают support. Recent — distinct products выбранных event types конкретного query-user, latest event time, независимо от числа повторов. Product/user NULL не создают кандидатов/support. Глобальные покупки других пользователей в секунде t исключены тем же predicate.

**Quotas/ties/dedup.** Popular top-N упорядочен по buyer count DESC, затем product_id ASC; recent — latest time DESC, затем product_id ASC. Numeric ID здесь только deterministic tie-break, не модельная ordinal feature. Union сохраняет оба source flags/ranks, dedup по `(query_id,product_id)`, overlap не вызывает refill. Пустой popularity оставляет recent-only, пустые источники — пустой C. Купленные раньше товары не удаляются. Исполнитель явно отклоняет меньший union cap без объявленной truncation policy; в v1 итоговый max_unique равен сумме quotas. Undersized pool — допустимый результат, не повод вставлять positives.

**Независимость Y.** `create_candidates` вообще не читает labels: это подтверждено тестом с удалённой label table. Coverage joins выполняются после создания/каталоговой проверки C. Future events и перестановка peers сохраняют fixed-query candidates. Cold future target остаётся в полном Y, не получает candidate row. Генератор не реализует ItemCF и не заявляет сравнения popularity220 против union200+20; это отдельная HYP-004 ветвь.

**Universe.** `verify_catalog` независимо читает necessary source prefix для candidate products, затем требует first_seen<конкретного query anchor. Подмена U набором из labels отсутствует. Тест с вручную внедрённым future candidate отвергается. U остаётся observed-catalog proxy; ни stock, ни impressions из этой проверки не следуют.

**Q/Y integrity и denominators.** Проверяются уникальные непустые query IDs, уникальные user-day, declared pilot bounds/UTC midnights, nonnull maturity и sample budgets. Y проверяется на duplicates, orphan/null product/flags и labels для censored queries. Retrieved target с catalog_seen_before=False отвергается. Coverage строится LEFT JOIN от всех Q: empty C, mature empty Y и censored сохраняются, censored counts не превращаются в zero-negative. Recall использует полный Y, включая cold/nonretrieved targets; positive-query macro и pooled counts различимы. Hand fixture даёт 7 candidate pairs без refill, 4 targets/3 retrieved и macro Recall=((2/3)+1)/2. Informative ranking queries требуют retrieved positive и отрицательного candidate.

## Meaningful tests и границы доказательства

Python set/count oracle независим от production SQL/helpers и использует буквальные half-open predicates. Дополнительно есть goldens по raw duplicates/distinct buyers, source overlap/ties, нижней границе, ранее купленному товару, cold target, empty sources, no labels, mismatched Q/labels и censoring. Основные acceptance-пути TLAB-004 покрыты. Oracle использует одинаковые 7d окна fixture; произвольные допустимые window/event-type варианты не исчерпывающе перебраны. Это ограничение coverage, не найденное расхождение SQL с manifest.

Validator **не доказывает** полноту supplied Y, sampling provenance, истинность всех catalog/pair flags или происхождение complete artifacts. Например, невозможную комбинацию pair_seen_before=True/catalog_seen_before=False для nonretrieved label данный layer отдельно не отвергает. В принятом pipeline эти свойства принадлежат проверенному producer TLAB-003; считать generic artifact validator полной повторной проверкой source нельзя. Добавление простой invariant-проверки возможно как hardening, но material defect корректных upstream inputs этим review не установлен.

## Оставшийся gate

Production остаётся blocked до acceptance TLAB-003 нового execution evidence. До запуска/принятия TLAB-004 нужны frozen candidate executor, actual hashes accepted anchor run/report/Q/Y/source и проверка их соответствия consumed files. Candidate run сейчас fingerprint-ит фактические входные artifacts и проверяет source DB digest; свежий hash фиксирует прочитанный файл, но сам по себе не доказывает, что это именно ранее принятый output producer. Достаточна явная сверка accepted run IDs/artifact fingerprints, новый framework не требуется.

Deadline/cooperative resource handling, полный run failure path и новые production artifacts не приняты настоящим retrieval review. После final freeze их проверять отдельно; прошлый one-shot interrupt finding нельзя закрывать только чтением похожего кода. До тех пор корректная synthetic retrieval логика не равна измеренному coverage/cost или разрешению production pilot.


## Final guard, execution и независимый source reconciliation — coordinator, 15 октября 2026

Actual final executor использует принятый persistent RunDeadline: fingerprint preparation проверяется до/после, ledger и RSS guard проверяют stages, exports и before-complete. Guard кооперативный, не OS hard kill; read/timer gaps не разрешают complete после expiry. Original synthetic retrieval review выше сохранён.

Coordinator проверил actual candidate manifest через validator, matching complete report/run/protocol, все14complete stages, фактические source/code/uv.lock/input hashes и pins независимого accepted003 Q/Y. Candidate identity42be82b3e4eda60c3c202e72de381172f1d979efe4c6c5a970d41d1adc5e26f3 потребляет anchor687afe24b689c0996344892808306685f39afdf56a5dad5aa521c3094ec0305d.

Read-only source oracle отдельно агрегировал distinct purchase users и last user-item event на каждом UTC anchor; Python sorting/dictionaries/sets реконструировали expected top200, recent20 и no-refill union. Потоково проверены **все1 226268 candidate rows**: membership, оба flags/ranks, full popularity count и last time совпали; ожидаемые размеры union также совпали. Source recent20 содержит34181пар втрёхднях. Source DB открыт read-only,threads2/memory2GB; ни user×catalog, ни labels в retrieval oracle нет. Первый ad-hoc ATTACH сparameter вызвал ParserError; исправлен только временный reviewer adapter, итог exit0, production artifacts не менялись.

Независимый full-Y LEFT JOIN проверил каждый saved per-query target/hit/popular/recent counter:0mismatches. Итог121Y,92retrieved,50popular,70recent,71/73repeat и21/48new-pair; positive-query macroRecall0.7836538461538461,84informativequeries. Uniqueness C=1 226268/1 226268. Actual output parquet/report fingerprints сверены и закреплены локальным ignored acceptance manifest для downstream.

**TLAB004 accepted.** Runtime1.476s/RSS666189824bytes/enginepeakspill0 относятся к этому provisional Bsample; это не доказательство final model quality или оптимальных quotas. HYP004popularity220 не исполнялась, protocolv1 cap200 сохранён.005/007 могут использовать именно этот fixedC/fullY после собственных code/synthetic/resource gates.
