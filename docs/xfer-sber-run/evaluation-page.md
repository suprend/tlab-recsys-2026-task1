# Снимок раздела Evaluation, test-recsys

- Источник: https://www.kaggle.com/competitions/test-recsys/overview/evaluation
- Снят 21.10.2026 из встроенного браузера (текст страницы), раздел Evaluation дословно — в [evaluation-page.txt](evaluation-page.txt).
- SHA-256 файла: `3c770f31071f79f888aa34e1ccb3250d9da4418d5396f52e74bd2dd9ba959849`
- Метрика: MAP@50; знаменатель AP — min(K, M), где M — длина цели. Предсказание короче M считается ошибочным в недостающей части. Формат: `Id,Predicted`, 50 товаров через пробел.
- Оговорка: формула p@k на странице записана через K, а не через k; реализация в `xfer_sber.metric` следует стандартному AP@K (precision на позиции k) и знаменателю min(K, M). Совпадение с лидербордом проверяется только описательно.
