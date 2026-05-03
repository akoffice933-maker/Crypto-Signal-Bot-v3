# 🔄 Multi-Pair Update — Changelog

**Дата:** 2026-03-28  
**Версия:** 3.1.0 (multi-pair support)  
**Статус:** ✅ Готово к деплою

---

## 📋 Обзор изменений

Добавлена поддержка 4 торговых пар для сбора сигналов и бэктестов:
- **BTCUSDT** (основная)
- **ETHUSDT** (добавлена)
- **SOLUSDT** (добавлена)
- **BNBUSDT** (добавлена)

---

## 🗂️ Изменённые файлы

### 1. Конфигурация

| Файл | Изменения |
|------|-----------|
| `.env` | Добавлено: `SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT` |
| `.env.example` | Добавлено: `SYMBOLS=...` (шаблон) |
| `config/settings.py` | Добавлено: `symbols: list` + property `symbol` для обратной совместимости |

### 2. Pipeline анализа

| Файл | Изменения |
|------|-----------|
| `engine/pipeline.py` | - Добавлен `asyncio` импорт<br>- `run_pipeline()` теперь циклически обходит все пары<br>- Новая функция `_analyze_single_pair()` для анализа одной пары<br>- Rate limit: 2 сек задержки между парами |

### 3. База данных

| Файл | Изменения |
|------|-----------|
| `database/schema.sql` | Добавлены индексы:<br>- `idx_signals_pair`<br>- `idx_cycle_pair` |
| `database/db.py` | - `get_signals_for_export()` теперь принимает `pair` параметр |
| `scripts/apply_indexes.py` | Новый скрипт для применения индексов |

### 4. Web API

| Файл | Изменения |
|------|-----------|
| `web/routes/signals.py` | - `list_signals()`: добавлен фильтр `pair`<br>- `stats()`: добавлен фильтр `pair` + поле в ответе<br>- `export_csv()`: добавлен фильтр `pair` + имя файла с парой |

### 5. Стратегии

| Файл | Изменения |
|------|-----------|
| `strategies/sweep_reversal.py` | - `_make_signal_id()`: добавлен `pair` параметр<br>- `signal_to_dict()`: использует `settings.symbol` |
| `strategies/breakout.py` | - `_make_signal_id()`: добавлен `pair` параметр<br>- `signal_to_dict()`: использует `settings.symbol` |

### 6. Документация

| Файл | Изменения |
|------|-----------|
| `.qwen/PROJECT_CONTEXT.md` | Обновлён для multi-pair |
| `.qwen/instructions.md` | Обновлён для multi-pair |

---

## 🎯 Ключевые изменения

### 1. Конфигурация пар

**До:**
```python
# config/settings.py
symbol: str = "BTCUSDT"
```

**После:**
```python
# config/settings.py
symbols: list = field(default_factory=lambda: os.getenv("SYMBOLS", "BTCUSDT").split(","))

@property
def symbol(self) -> str:
    return self.symbols[0] if self.symbols else "BTCUSDT"
```

### 2. Pipeline цикл

**До:**
```python
async def run_pipeline(...):
    # Анализ только BTCUSDT
    signal = await analyze_pair("BTCUSDT", ...)
```

**После:**
```python
async def run_pipeline(...):
    for symbol in settings.symbols:
        signal = await _analyze_single_pair(symbol, ...)
        await asyncio.sleep(2)  # Rate limit
```

### 3. Signal ID (уникальность по парам)

**До:**
```python
def _make_signal_id(direction: str, entry: float) -> str:
    raw = f"{direction}{entry:.2f}{now}"
```

**После:**
```python
def _make_signal_id(pair: str, direction: str, entry: float) -> str:
    raw = f"{pair}{direction}{entry:.2f}{now}"
```

---

## 📊 Ожидаемые результаты

| Метрика | До (1 пара) | После (4 пары) |
|---------|-------------|----------------|
| Сигналы/неделю | 2-5 | 8-20 |
| Сделки для бэктеста | 10-20/мес | 40-80/мес |
| Время сбора статистики | 4-6 недель | 1-2 недели |
| Надёжность оптимизации | Низкая | Средняя/Высокая |

---

## 🚀 Деплой

### Локально

```powershell
# 1. Проверка синтаксиса
python -m py_compile config/settings.py engine/pipeline.py

# 2. Тесты
python -m pytest tests/test_signal_replay.py -v

# 3. Dry-run
python main.py --dry-run --log-level=INFO
```

### VPS

```bash
# 1. Загрузить файлы
scp -P 2222 .env root@148.222.186.16:/opt/crypto-bot/
scp -P 2222 config/settings.py root@148.222.186.16:/opt/crypto-bot/config/
scp -P 2222 engine/pipeline.py root@148.222.186.16:/opt/crypto-bot/engine/
scp -P 2222 database/db.py root@148.222.186.16:/opt/crypto-bot/database/
scp -P 2222 web/routes/signals.py root@148.222.186.16:/opt/crypto-bot/web/routes/
scp -P 2222 strategies/*.py root@148.222.186.16:/opt/crypto-bot/strategies/

# 2. Применить индексы БД
ssh -p 2222 root@148.222.186.16
cd /opt/crypto-bot
python scripts/apply_indexes.py

# 3. Перезапустить бота
systemctl restart crypto-bot

# 4. Проверить логи
journalctl -u crypto-bot -f --no-pager

# 5. Проверить сигналы по парам
sqlite3 data/signals.db "SELECT pair, COUNT(*) FROM signals GROUP BY pair;"
```

---

## ⚠️ Возможные проблемы

### 1. Rate limit Binance

**Симптом:** Ошибки 429 Too Many Requests  
**Решение:** Увеличить задержку в `engine/pipeline.py`:
```python
await asyncio.sleep(3)  # вместо 2
```

### 2. Старые сигналы без pair

**Симптом:** Ошибки при чтении старых сигналов  
**Решение:** В `database/schema.sql` уже стоит `DEFAULT 'BTCUSDT'`

### 3. Дубликаты signal_id

**Симптом:** Конфликты при вставке сигналов  
**Решение:** `_make_signal_id()` теперь включает `pair`

---

## 📈 Мониторинг после деплоя

### Через 1 час

```bash
# Проверить количество циклов по парам
sqlite3 data/signals.db "SELECT pair, COUNT(*) FROM cycle_summary WHERE created_at > datetime('now','-1 hour') GROUP BY pair;"

# Проверить ошибки
journalctl -u crypto-bot --since "1 hour ago" | grep -i error
```

### Через 24 часа

```bash
# Статистика сигналов по парам
sqlite3 data/signals.db "SELECT pair, direction, strategy, COUNT(*) FROM signals WHERE created_at > datetime('now','-24 hours') GROUP BY pair, direction, strategy;"

# Проверить Web API
curl http://localhost:8001/signals/stats?pair=ETHUSDT
```

### Через 1 неделю

```bash
# Сравнение сигналов по парам
sqlite3 data/signals.db "SELECT pair, COUNT(*), AVG(confidence_score), AVG(rr_ratio) FROM signals WHERE created_at > datetime('now','-7 days') GROUP BY pair;"
```

---

## ✅ Чек-лист успешного деплоя

- [ ] `.env` обновлён: `SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT`
- [ ] Индексы БД применены: `python scripts/apply_indexes.py`
- [ ] Бот перезапущен: `systemctl restart crypto-bot`
- [ ] В логах видно анализ 4 пар каждые 15 минут
- [ ] Web API возвращает сигналы с фильтром по паре
- [ ] Telegram сообщения содержат `pair` в заголовке

---

**Готово!** 🎉

Теперь бот анализирует 4 пары и собирает в 4× больше данных для бэктестов.
