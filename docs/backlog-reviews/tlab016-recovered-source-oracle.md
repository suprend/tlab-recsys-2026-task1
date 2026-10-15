# Независимый oracle восстановленного источника016

Принятый entry: `tests/oracles/feature_program_recovery_audit.py`, SHA256 `a3a485a0b0d899150c91eac3706e75e9e3d0fceb798ef5d48c84063bdc8891d6`. Admission `47cc4495cbf24bd033316ca9a667382f66a1ab8cd718843d057c52d13bfeeec2`; owner `9100471dc98cfc68ee558ad1dadaafbf1a862ffcd53bca9f239cffb10c068c55`. Полный новый lifetime и все30 export hashes закреплены внешней attestation; исходный failed producer `b3e05d85d97afc26d8cbda8627d3bfffc46ad6a037d03beb1c0c6d5d807ef84f` не изменён.

Oracle независимо вычисляет значения12 выбранных столбцов из исходных событий и сверяет все6 134 207пар. Полный домен Q/C доказывается дневными bags, accepted Q/F bindings, disjoint anchors и суммами; общего57-column CTAS нет. Все45 старых полей сохранены. Ноль расхождений на73 610 484 новых значениях, noY/noMLfit/no regeneration. Source, temporal peers и повторения сохраняют строгий past contract. Отдельный issuer SHA связывает context с реально выданной allowance.

[Production oracle](../../tests/oracles/feature_program_recovery_audit.py), [admission](../../scripts/feature_program_source_recovery.py), [owner](../../scripts/run_feature_source_recovery.py), [агрегаты](tlab016-recovered-source-aggregate.json).
