# Данные для обучения подготовлены и проверены

Срез 2026-10-17 02:04:47 UTC. Для вымышленного случая приняты две матрицы: по три строки и 41 признаку. Независимо сверены все 246 сериализованных значений: 228 конечных чисел и 18 NULL на местах ожидаемых NaN. Проверены порядок признаков, группы, метки, веса и полный набор целевых товаров, включая цели вне кандидатов и запрос без кандидатов.

[Root acceptance](evidence/post-audit-Prepared/originals/tlab-root-post-audit-Prepared-final-artifact-acceptance-v1.json) и [независимый отчёт](evidence/post-audit-Prepared/originals/tlab-native-post-audit-Prepared-independent-actual-review-v1.md) сохраняют точные доказательства. Все 120 входных файлов остались неизменны; проверены 55 закреплённых имён и значений для CLI. Типы, размеры и объём матриц подтверждены исполненными проверками в закреплённом исходном коде. **Независимый reviewer проверил сериализованные значения, а не напрямую heap или in-memory dtype.**

**Полный исправленный native CLI и callback-abort остаются UNRUN.** Prepared-проверка не загружала ML runtime, не выполняла fit и не запускала полный CLI. Следующий нативный запуск не входит в эту приёмку; нового native grant она не даёт. Ограничение доказательств — десять вымышленных событий, без утверждения качества, CV или общей свободы от leakage.

Прежний [документальный checkpoint принят локально](evidence/post-audit-Prepared/originals/tlab-root-LOCAL38-final-actual-acceptance-v1.json). Ранее опубликованы код и документы семи исправлений. Этот новый Prepared пакет пока является SOURCE-предложением. Исторический Mac repeat, 89 синтетических методов и exploratory 1189/403 сохраняют прежний смысл. Финальный NDCG B = 0.459825 / W = 0.464947; 95% интервал разницы пересекает ноль, надёжный выигрыш не установлен. Приняты 14 из 19 исходных задач; TLAB-014 продолжается, TLAB-010–013 отложены как необязательные опыты.

Сохранены побайтно четыре безопасных оригинала: две Root-приёмки, peer report и [peer freeze](evidence/post-audit-Prepared/originals/tlab-native-post-audit-Prepared-independent-actual-review-v1-freeze.json). Raw pins содержит полные X-матрицы и не включён. Его точная ссылка:

```json
{"original_path":"/tmp/tlab-native-post-audit-Prepared-independent-actual-review-v1-pins.json","sha256":"2db19d8bbaab436a998e58e569e27ed92e8071ab5c06e60bd8d7d76454d38d6e","bytes":86580,"body_copied":false,"withheld_fields":["/actual_serialized_Prepared/train/x","/actual_serialized_Prepared/selection/x"]}
```

Сохранённый freeze связывает withheld original pins, а не bundled body или производный файл. RawX/result/oracle/DB/Parquet/models и private worker/owner/issuer/consumed/policy/grant/human bodies исключены; ссылки на них остаются metadata-only. Полный прежний текст четырёх текущих документов сохраняется; ранний B41 UNRUN относится к прежним датам.
