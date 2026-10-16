# Portable six-file bundle: independent correctness review v1

Замечаний по корректности и требованиям в проверенной переносимой части не найдено. Это статическое заключение; portable layout не запускался.

Проверены ровно шесть кандидатов из Root snapshot `1f9d6968…5981` и author manifest `89f50da2…82a0`. Production `development_training.py` и `itemcf_projection.py` побайтно совпадают с ранее рассмотренными версиями `3d6052c0…17d8` и `74bb5671…335f`. Контекстный `train_baselines.py` не является седьмым кандидатом.

В `tests/test_development_training.py:11–26,74–95` и `tests/test_itemcf_projection.py:11–22` пути выводятся из расположения установленного test-файла. Загрузчики ограничивают чтение 128 KiB и компилируют именно полученные raw bytes, без повторного открытия через import loader/pyc. Development module зарегистрирован для dataclass; его вызов выполняется внутри подстановок fake Prepared/backend/selector. Из `train_baselines.py` извлекается только существующий callback AST. ItemCF implementation использует stdlib; тестовая загрузка не требует native backend.

Независимое AST-сопоставление подтвердило сохранение всех 22 test methods: 6+4 development и 10+2 ItemCF. Сохранены четыре fake fixture classes, `run_fit`, `project`, independent `reference` и `compare`, включая assertions. Test classes напрямую наследуют `unittest.TestCase`; наследованного повторного discovery нет. Структура неизменённых oracle loops задаёт 1024+256 сравнений, но эти сравнения здесь не выполнялись.

Все первоначальные и добавленные source/context pins, shared copies и собственные byte copies проверены повторно и неизменны. Выполнены только чтение, SHA, AST-сопоставление и syntax compilation без исполнения.

Пределы: не проверялись native compatibility, данные, модели, новая ML-тренировка, фактический unittest discovery/runtime или установка. Предыдущее unit-acceptance отделено от ещё UNRUN portable layout. Future caller adoption, chronology, persistence и cost остаются внешними обязательствами; исторические training routes не меняются. Заключение не является runtime grant или разрешением публикации.
