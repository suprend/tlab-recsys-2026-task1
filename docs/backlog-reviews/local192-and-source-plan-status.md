# Локальные исправления приняты; подготовлены source и два producer plan

Датированный SOURCE-срез: 2026-10-17 00:59:13 UTC. Этот отчёт описывает проверенные результаты; установка самого нового документального пакета ещё не выполнялась.

Семь исправлений pipeline и их регрессии локально установлены в `13ce92d650a59794d1a503063c23e9fc9529bcbc`. [Root acceptance](evidence/local192-followup/originals/tlab-root-LOCAL192-final-actual-acceptance-v1.json) и [независимый actual review](evidence/local192-followup/originals/tlab-LOCAL192-independent-actual-review-v1.md) подтвердили exact192, обычную staged whitespace проверку с exit0 и CLEAN. Полное tree содержит 3312 записей: 20 M / 172 A, остальные 3120 прежних записей неизменны. Ранее приняты 89 уникальных targeted synthetic методов; во время установки тесты повторно не выполнялись.

Это не новый native/full-raw повтор и не доказательство качества модели. Исторический final CI разницы B/W пересекает ноль; adaptive 1189/403 остаётся exploratory. Приняты 14 из 19 задач, TLAB-014 continuous, TLAB-010–013 optional/deferred. Exact476 опубликован ранее; новые локальные коммиты не получили разрешения на push.

[Source-plan V1](evidence/local192-followup/originals/tlab-root-post-audit-source-plan-wrapper-failure-v1.json) остаётся FAILED: внешний `time -lp` сообщил sysctl error, outer exit1; прямой owner exit не был независимо зафиксирован. Child exit0/reaped не заменяет отсутствующую owner proof. Fits 0; allowance закрыто без повторного использования.

[Отдельный V2](evidence/local192-followup/originals/tlab-root-post-audit-source-plan-actual-pass-v2.json) завершился direct owner/child exit0/reaped. [Независимая artifact review](evidence/local192-followup/originals/tlab-native-post-audit-source-plan-independent-actual-review-v2.md) и [Root acceptance](evidence/local192-followup/originals/tlab-root-post-audit-source-plan-final-artifact-acceptance-v2.json) приняли synthetic typed9 source с 10 вымышленными строками и два producer plan. Проверены 28 файлов и 21 current-code pin. Reviewer выполнил одну разрешённую read-only проверку synthetic DB: exact rows/types, SHA до/после одинаков, WAL отсутствует. Этот документ не повторяет SQL и не копирует DB.

Dispatch-to-known-terminal upper bound V2 — 0.777 s; child CPU — 0.486607 s. Owner 0.55154 s является prefix, не final whole CPU. V1 не стал успешным задним числом; namespaces и allowances раздельные, повторное использование закрытых allowances не разрешено. Genuine approvals ещё не выданы; QYC/F/Prepared/native в новом scope **UNRUN**. Исправленный обычный native CLI end-to-end и callback-abort остаются UNRUN; нового native grant нет.

Волны [085](../research-lab/brainstorm-wave085-synthesis.md) и [086](../research-lab/brainstorm-wave086-synthesis.md) приняты как SOURCE refinements без admissions. Для 086 три независимых FIRST предшествовали отдельной критике. Следующий исходный срок — 01:30 UTC / 04:30 МСК 17 октября; сетка 45 минут и исходный deadline не сброшены.

[Publication map](evidence/local192-followup/publication.json) связывает точные безопасные оригиналы с архивными назначениями. Приватные controllers, issuers, consumed markers, human approvals, policy/skill bodies, DB и модели исключены; исходные path/hash references сохранены как metadata. Ранние pending/failure формулировки в raw originals относятся к своим датам и не переписаны.
