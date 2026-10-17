# HYP-061: конечная проверка поиска кандидатов по совместным просмотрам

Root принял результат **17 октября 2026, 10:40 UTC**: на фиксированных 100 запросах без Y независимо совпали три полных графа и все 100 полных выходных артефактов. Это подтверждение объявленного вычисления; качество рекомендаций не измерялось. [Решение Root](evidence/covis-candidate-discovery/tlab-root-hyp061-q100-final-actual-acceptance-v1.json), [безопасный агрегат](evidence/covis-candidate-discovery/tlab-root-hyp061-q100-public-aggregate-v1.json).

Графы используют различные пары пользователь–товар за строго прошлые семь суток для 8, 9 и 10 октября. Профиль с более чем 32 товарами исключается целиком. Перед расчётом поддержек и норм из графа вычитается пользователь запроса. Count и cosine используют один полный найденный домен; C0 исключается до top20. Новые кандидаты добавляются к P180∪R20 без скрытого заполнения квоты.

| Наблюдение | Результат |
|---|---:|
| Запросы по трём датам | 25 / 41 / 34 |
| Непустой / пустой источник | 63 / 37 |
| Разные count/cosine top20-наборы | 54 |
| Размер итогового C / нового источника | 180–220 / 0–20 |
| Посещения рёбер профилей | 203225 |
| Полный домен до C0 / ячейки арифметики Root | 9516 / 19032 |

[Независимый SQL-oracle V3](evidence/covis-candidate-discovery/tlab-hyp061-independent-correctness-actual-v3.md) заново построил три полных графа и сравнил целиком структуры, поддержки, нормы, порядок суммирования, ранги, tie-breaks и дедупликацию. Он не импортировал producer. Root перепроверил 159 новых metadata refs и 123 прежних. Проверка относится к этим окнам и этой принятой processed DB: это не новый raw import, формульный oracle исходных событий, доказательство serving-доступности или общего отсутствия утечек.

| Измерение producer, original 9904→77dfb7, exit0/reaped | Значение |
|---|---:|
| CPU завершённого child | 26.061709 с |
| Elapsed wrapper до финального хвоста | 24.913533 с |
| Наблюдённый максимум RSS child | 1181286400 B |
| Сохранено после завершения | 1920126 B, 105 файлов |

[Resource review](evidence/covis-candidate-discovery/tlab-hyp061-independent-resources-actual-v1.md) сохраняет ограничения: точного полного CPU/wall wrapper нет; sampled child RSS не является жёстким суммарным RSS. Финальный spill/cache равен нулю, transient peak не установлен. Physical I/O UNKNOWN; прежний экран 32 GiB **не пройден**. Только операционные пороги числа непустых/различающихся источников выполнены.

История сохранена: Source V1 P2 о потере вторичных ошибок и замечание о сканировании posting закрыты V2; первая synthetic-попытка имела ошибочный expected-домен, production не менялся, затем 20 PASS. [Первый log](evidence/covis-candidate-discovery/SourceV2/synthetic-attempt1.txt) и [финальный log](evidence/covis-candidate-discovery/SourceV2/synthetic-attempt2.txt) сохранены. Две actual harness-неудачи ps/WAL остаются [INCOMPLETE](evidence/covis-candidate-discovery/tlab-hyp061-independent-correctness-actual-v1.md), не дефектами discovery. V3 verifier 29548/eab004→b41f30 завершён exit0/reaped; суммарные samples 13.624467 CPU / 12.109406 wall не включают точный весь хвост. P3 об этом ограничении сохранён в [Source-review V3](evidence/covis-candidate-discovery/tlab-hyp061-independent-correctness-v3-source-review-v1.md).

Y, fits, загрузки моделей и predictions — 0. Выводов о качестве нет; прежний frozen final и negative seed2027 неизменны. План 6000 — SOURCE-only под независимым ревью, runtime UNRUN и не допущен. Волна 101 — отдельные необязательные уточнения, не основание продвигать этот пилот дальше.
