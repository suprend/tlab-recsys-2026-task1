# Волна 064 и SIDE064: представление, доступность и интерпретация

Основные три FIRST и два SIDE-FIRST прошли разные независимые скептические ревью. Root принял только optional-уточнения. [Основные оригиналы](archives/wave064/publication.json) и [SIDE-оригиналы](archives/side064/publication.json) сохранены побайтно.

**A — прежняя граница 019/014.** Полная кривая, глобальный максимум и самый ранний префикс в полосе 1e−12 должны сохранять positive fullY, включая off-C и empty-C; zero-Y учитывается отдельно. Принятый native eight-tree helper имел плоскую кривую и не различает все nonflat-ошибки. Tiny nonflat CLI и callback-abort остаются UNRUN; если будущий пример плоский, вывод ограничивается inconclusive без повторов. Нового базового gate нет.

**B — детерминированные представления, 013/014/016.** Преобразование B41 может облегчить разбиения ограниченному learner, не добавляя информации; XOR-пример доказывает возможность для stumps, не CatBoost convergence или REES46 gain. Нужно различать исходные counts и уже float32-encoded B41. Будущий M/G с одинаковыми колонками проверяет parity и общую пользу представления, не превосходство автоматизации.

Критическое ограничение: текущая grammar не поддерживает предложенные difference/product/denominator-plus-one, а whitelist helper и CLI **не поддерживают** border_count/input_borders и замораживание общих borders. Схема 3 arms × 2 depths × 2 border settings = 12 новых fit attempts — лишь будущий дизайн после отдельной реализации/ревью и бюджета, не готовая CLI-команда. Каждое обучение выбирает собственный префикс на общей development validation; все повторные обращения exploratory и оплачиваются. Operands, units, missingness и три физические колонки ещё требуют фиксации.

**C — event time и синтетическая availability, 022/040/036/043.** Шесть придуманных событий аналитически дают event-time Q={g,u,v}, C_u={p,r}, availability Q={g,u}, C_u={p}. Значение X(u,r)=1/0 относится только к отдельно заданной fixed-C проекции. Синтетические L=24h и trusted watermark дают зрелость в t+48h, не гарантируют её в t+24h. Это не измерение REES46 lag или completeness; источник не содержит arrival clock. Toy UNRUN; качество не проверялось.

**SIDE: nonflat oracle, 014/019.** Только три вручную описанных дерева дают условную кривую `(0.5,1,1)/(3*(1+1/log2(3)))` и earliest maximum 2. JSON не построен и не загружен; installed lock, native metadata/routing и lifecycle feasibility не доказаны. Loaded model не проходит fresh-unfitted контракт helper. Возможный zero-fit тест не доказывает fit/callback/CLI и всё равно требует native ресурсов; он UNRUN.

**SIDE: calibration, target04/L01/L06/round072.** Вес 1/|Cq| задаёт D*: равномерный mature nonempty-C query, затем кандидат. Идеальный weighted-BCE posterior покупки в окне не доказывает калибровку конечной regularized/ranking-selected модели. Без impressions нет CTR, dislike или causal трактовки. Диагностика UNRUN; свежие дни и достаточная поддержка не установлены.

Новых механизмов, ID, grants, admissions или gates нет; закрытые бюджеты не переоткрыты. Исторический next09:00 сохранён в оригиналах. По последнему сообщению Root 065 отправлена в 09:00, следующая исходная точка — 09:45 UTC / 12:45 МСК. Пакет вне публикации b286 и не задерживает её.
