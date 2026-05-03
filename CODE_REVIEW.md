# Code Review — Crypto Signal Bot v3

**Дата:** 2026-05-01  
**Ревьюер:** Автоматическое ревью (Roo)  
**Python:** 3.14.2  
**Тестов:** 110 (108 passed, **2 failed**)  
**Flake8:** 316 замечаний  

---

## 1. Тесты

### ✅ Результат: 108/110 (98.2%)

| Файл | Passed | Failed |
|------|--------|--------|
| test_backtester_execution | 2 | 0 |
| test_breakout | 6 | 0 |
| test_confidence | 11 | 0 |
| test_cycle_summary | 8 | 0 |
| test_database_oi | 1 | 0 |
| test_dual_mode | 7 | 0 |
| test_exports_and_notifier | 11 | **1** |
| test_integration | 3 | **1** |
| test_liquidity_map | 5 | 0 |
| test_market_state | 5 | 0 |
| test_no_lookahead | 3 | 0 |
| test_replay_sweep | 3 | 0 |
| test_runtime_and_routes | 5 | 0 |
| test_signal_replay | 3 | 0 |
| test_sweep_pattern | 16 | 0 |

### ❌ Упавшие тесты

#### 1. `test_telegram_start_text_contains_mode_and_chat_id`
**Файл:** `tests/test_exports_and_notifier.py:140`  
**Причина:** Тест ожидает строки `"Bot is online"`, `"Signals chat: \`2017851817\`"` и `/status - show notifier status`, но реальный текст бота содержит другие строки (русский язык, другой формат).

```
AssertionError: assert 'Bot is online' in '🤖 **Crypto Signal Bot v3.4**\n\nMode: `testnet`\nPairs: ...'
```

**Вывод:** Тест устарел — `_build_start_text()` был переписан (добавлены русские команды, изменён формат), а тест не обновлён.

**Исправление:** Обновить тест под актуальный формат сообщения.

---

#### 2. `test_signals_endpoints_return_seeded_data`
**Файл:** `tests/test_integration.py:123`  
**Причина:** `response.json()` бросает `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` — ответ пустой. Эндпоинт `/signals/?limit=5` возвращает пустое тело.

**Вывод:** Вероятно, проблема в инициализации тестовой БД или в том, что `get_db()` dependency не подменяется корректно в тестовом клиенте.

**Исправление:** Проверить `integration_client()` — убедиться, что `set_db()` вызывается до запроса и dependency override работает.

---

### ⚠️ Предупреждения тестов (8 штук)

```
database/db.py:406: DeprecationWarning: datetime.datetime.utcnow() is deprecated
```

Используется `datetime.utcnow()` в двух местах (`is_on_cooldown`, `set_cooldown`). В Python 3.12+ это deprecated.

---

## 2. Качество кода (Flake8)

**Итого: 316 замечаний** по всему проекту.

### Критические (функциональные)

| Код | Кол-во | Описание | Файлы |
|-----|--------|----------|-------|
| `F401` | 14 | Неиспользуемые импорты | `engine/confidence.py`, `engine/indicators.py`, `engine/liquidity_map.py`, `web/routes/market_data.py`, `web/routes/replay.py` |
| `F541` | 18 | f-строки без плейсхолдеров | `engine/logger.py` (10+) |
| `F841` | 3 | Переменная присвоена, но не используется | `engine/liquidity_map.py:47` — `tf_weight` |
| `F824` | 10 | `global` объявлен, но переменная не присваивается | `main.py`, `web/routes/backtest_api.py` |

### Детали критических проблем

#### `F841` — мёртвый код в `engine/liquidity_map.py:47`
```python
tf_weight = TF_WEIGHT.get(self.timeframe, 1.0)  # присваивается, но не используется!
touches_bonus = min(self.touch_count, 10)
```
`tf_weight` вычисляется, но в формуле `level_score` не применяется. Это либо баг (вес таймфрейма должен влиять на score), либо мёртвый код.

#### `F541` — пустые f-строки в `engine/logger.py`
```python
logger.info(f"")   # строки 79, 89, 100, 107, 117, 233, 240, 263
```
Следует заменить на `logger.info("")`.

#### `F401` — неиспользуемые импорты
```python
# engine/confidence.py:23
from typing import Tuple  # не используется

# engine/indicators.py:8
import numpy as np  # не используется

# engine/liquidity_map.py:15
from typing import Dict  # не используется
```

### Стилевые (некритические)

| Код | Кол-во | Описание |
|-----|--------|----------|
| `W293` | 124 | Пробелы в пустых строках |
| `E221` | 79 | Выравнивание операторов пробелами |
| `E231` | 22 | Нет пробела после `:` или `,` |
| `E501` | 15 | Строки длиннее 120 символов |
| `W291` | 12 | Trailing whitespace |
| `E702` | 4 | Несколько операторов на одной строке (`;`) |

#### `E702` в `web/routes/signals.py:42-47`
```python
q += " AND direction=?"; params.append(direction.upper())  # плохо
q += " AND strategy=?"; params.append(strategy)
```
Следует разбить на отдельные строки.

---

## 3. Архитектурные замечания

### 🔴 Высокий приоритет

#### 3.1 Мутация глобального состояния в `engine/pipeline.py:150`
```python
settings.symbols[0] = symbol   # временная мутация!
# ... анализ ...
settings.symbols[0] = original_symbol  # восстановление
```
Это **thread-unsafe** и хрупкий паттерн. При исключении до `finally` (хотя `finally` есть) или при параллельном запуске — состояние может быть повреждено. Правильное решение: передавать `symbol` явным параметром во все функции, которые читают `settings.symbol`.

#### 3.2 `datetime.utcnow()` deprecated — `database/db.py:402,406`
```python
return datetime.fromisoformat(row[0]) > datetime.utcnow()   # строка 402
until = (datetime.utcnow() + timedelta(minutes=minutes)).isoformat()  # строка 406
```
Заменить на `datetime.now(timezone.utc)`.

#### 3.3 Прямые SQL-запросы в Telegram-хендлерах — `telegram/bot.py`
```python
rows = await db._fetch("""SELECT ... FROM signals ...""")
```
Хендлеры `/active`, `/pairs`, `/export` напрямую вызывают `db._fetch()` (приватный метод). Логика должна быть в `Database` или в отдельном сервисном слое.

### 🟡 Средний приоритет

#### 3.4 `tf_weight` не используется в формуле `level_score`
В [`engine/liquidity_map.py:47`](engine/liquidity_map.py:47) переменная `tf_weight` вычисляется, но не применяется в расчёте `level_score`. Если вес таймфрейма (1D > 4H) должен влиять на оценку уровня — это баг. Если нет — мёртвый код.

#### 3.5 `run_pipeline()` возвращает только последний сигнал
```python
return all_signals[-1] if all_signals else None
```
При анализе нескольких пар возвращается только последний сигнал. Вызывающий код в `main.py` логирует только его. Остальные сигналы теряются для логирования на верхнем уровне (хотя в БД они сохраняются).

#### 3.6 `CORS allow_origins=["*"]` в `web/app.py:40`
```python
allow_origins=["*"]
```
Для production следует ограничить список разрешённых origins.

#### 3.7 Отсутствие `pytest.ini` / `pyproject.toml` с настройками asyncio
Тесты используют `asyncio_mode=STRICT` (из `pytest-asyncio`), но конфигурация не зафиксирована в файле проекта. Это может вызвать проблемы при обновлении `pytest-asyncio`.

### 🟢 Низкий приоритет

#### 3.8 Дублирование логики создания `Database` в Telegram-хендлерах
Каждый хендлер создаёт новый `Database()`, подключается и закрывает. Лучше использовать единственный экземпляр из `main.py`.

#### 3.9 Комментарий `# Legacy support` в `config/settings.py:27`
Свойство `symbol` помечено как legacy, но активно используется в `pipeline.py` (`_make_cycle_id`, логирование). Следует либо убрать пометку, либо полностью перейти на `symbols[0]`.

---

## 4. Зависимости

### `requirements.txt` — минимальный, без pin версий
```
aiohttp>=3.9.0
pandas>=2.1.0
...
```
Нет верхних ограничений версий. Это нормально для разработки, но для production рекомендуется `pip freeze > requirements-lock.txt`.

### Конфликты в системе (не влияют на проект)
```
statbet-bot 0.1.0 требует pandas<3.0.0, установлен pandas 3.0.1
statbet-bot 0.1.0 требует asyncpg<0.31.0, установлен asyncpg 0.31.0
```
Это конфликты **другого проекта** (`statbet-bot`) в системе Python, не данного бота. На работу проекта не влияют.

### Отсутствующие dev-зависимости
В `requirements.txt` нет `pytest`, `pytest-asyncio`, `httpx`, `flake8`. Рекомендуется добавить `requirements-dev.txt`.

---

## 5. Безопасность

| Проблема | Файл | Серьёзность |
|----------|------|-------------|
| `CORS allow_origins=["*"]` | `web/app.py:40` | Средняя |
| SQL через `db._fetch()` напрямую в хендлерах | `telegram/bot.py` | Низкая (параметризованные запросы используются) |
| `.env` в корне проекта | `.env` | Низкая (должен быть в `.gitignore`) |

---

## 6. Итоговая оценка

| Категория | Оценка | Комментарий |
|-----------|--------|-------------|
| Покрытие тестами | ⭐⭐⭐⭐☆ | 98.2%, 2 теста устарели |
| Качество кода | ⭐⭐⭐☆☆ | 316 flake8 замечаний, есть мёртвый код |
| Архитектура | ⭐⭐⭐⭐☆ | Чёткое разделение слоёв, есть точечные проблемы |
| Безопасность | ⭐⭐⭐☆☆ | CORS открыт, прямые SQL в хендлерах |
| Документация | ⭐⭐⭐⭐☆ | Хорошие docstring и комментарии в ключевых модулях |

---

## 7. Приоритетный план исправлений

### Срочно (до следующего деплоя)
1. **Исправить `datetime.utcnow()`** в [`database/db.py:402,406`](database/db.py:402) → `datetime.now(timezone.utc)`
2. **Исправить упавший тест** `test_telegram_start_text_contains_mode_and_chat_id` — обновить ожидаемые строки
3. **Исправить упавший тест** `test_signals_endpoints_return_seeded_data` — проверить dependency override

### Важно (в ближайшем спринте)
4. **Убрать мутацию `settings.symbols[0]`** в [`engine/pipeline.py:150`](engine/pipeline.py:150) — передавать `symbol` параметром
5. **Разобраться с `tf_weight`** в [`engine/liquidity_map.py:47`](engine/liquidity_map.py:47) — баг или мёртвый код?
6. **Убрать неиспользуемые импорты** (`F401`) — `numpy`, `Tuple`, `Dict`, `json`, `os`
7. **Убрать пустые f-строки** в [`engine/logger.py`](engine/logger.py) (`F541`)

### Желательно (технический долг)
8. Добавить `requirements-dev.txt` с dev-зависимостями
9. Вынести SQL из Telegram-хендлеров в методы `Database`
10. Ограничить `CORS allow_origins` в production
11. Убрать trailing whitespace (`W293`, `W291`) — 136 мест
