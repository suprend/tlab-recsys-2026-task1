# Автоматизация: пример генерации определений без данных

В подготовленном locked environment из корня проекта можно вызвать существующий API. Он читает только два committed JSON, создаёт definitions и физические зависимости; SQL, приватные данные, модели, fit и approvals не используются. Эта проверка действительно исполнена15October2026, exit0. Она не повторяет исторические четыре обучения016 и не воспроизводит их метрики.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import json
from pathlib import Path
from scripts.feature_programs import generate_pool,allocate_slots,registry_for_slot
contract=json.loads(Path('configs/features/automation-pool.json').read_text());base=json.loads(Path('configs/features/manual-18.json').read_text())
pool=generate_pool(contract,base);allocation=allocate_slots(pool)
for bundle in pool['identity']['bundles']:
 if bundle['bundle_id'] in ('L02','L06'):
  print(json.dumps(dict(bundle=bundle['bundle_id'],generated_definitions=bundle['programs'],physical_delta=bundle['physical_delta'],model_width=len(bundle['model_feature_order'])),indent=2))
print(json.dumps(allocation['identity']['slots'],indent=2));registry=registry_for_slot(pool,allocation,'I2')
print('I2 additional core definitions:',len(registry['features'])-len(base['features']));print('execution_approved:',allocation['identity']['execution_approved'])
PY
```

Observed: L02 порождает три count24h core definitions; L06 — два core definitions и автоматический BOOLEAN missing flag. Каждый блок добавляет три физических поля, model width44=B41+3. Allocation даёт I1/L02, I2/L06, R1/L01, R2/L05; `execution_approved=false` и `native_fits_started=0` относятся к этой construction-only демонстрации. Историческое исполнение четырёх моделей отдельно описано в [отчёте](../progress-report.md). Ограниченная human-bounded генерация не заявляет discovery произвольных схем, superiority guided search, speedup или измеренную экономию труда.

## Original demonstration evidence

Script SHA256 649428dbb5f1023dc0a70c7c3572668dc163d609b8ab5b8c7cc3e9bae3ec6ec7, output SHA256 d7645b9d7d5329cea52b5ff667b96924abc6846bc07b3a4bab5715bbdb973b38. Полный stdout содержит только generated names/types/definitions, slot identities и permission=false; приватных keys/данных нет.
