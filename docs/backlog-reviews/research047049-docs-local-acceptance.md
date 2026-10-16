# Локальный срез исследований047–049: проверки и пределы

Независимые semantic и provenance reviews приняли исходные57 документов; отдельное review приняло более читаемый progress V2. Архивы сверены с оригиналами, существующие четыре документа — с исходными версиями. Единственная очередь и14/19 сохранены; frozen report/history/recipe/lock не меняются.

[Semantic review](evidence/research047049-docs/semantic-review.md), [provenance review](evidence/research047049-docs/provenance-review.md), [progress V2 review](evidence/research047049-docs/progress-v2-review.md).

Четыре legacy-пояснения progress совпадают с намерением ссылок report и имеют уникальные именованные HTML anchors. Bundled marked построил HTML; статический parser проверил четыре ссылки и нужные абзацы. [Структурная проверка](evidence/research047049-docs/anchor-structure.json) подтверждает только эту область.

Фактическая браузерная навигация НЕ подтверждена: Playwright завершился до запуска браузера из-за отсутствующего executable; [исходная ошибка](evidence/research047049-docs/render-failure.json) сохранена. Встроенный браузер затем отклонилfile:// по URL security policy; обход не выполнялся. Источник синтаксиса именованных anchors: [GitHub Docs](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#custom-anchors).

NULL-oracle patch уже локально установлен и подтверждён13 GREEN-методами после ожидаемых двух RED-ошибок. Этот результат не является native fit/serialization helper или новым экспериментом качества. Новых ML fits, чтения реального датасета, stage/commit/push здесь нет. Точная установка документации проверяется отдельной Root-квитанцией; это source/code acceptance, не заявление об отправке на GitHub.
