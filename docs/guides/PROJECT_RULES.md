# 📘 Crypto Signal Bot v3 — Project Rules

**Версия:** 3.0.0  
**Последнее обновление:** 2026-03-27  
**Статус:** Production (testnet/live)

---

## 📁 1. Структура проекта

```
d:\bot_final\
├── config/              # КОНФИГУРАЦИЯ
│   ├── settings.py      # Настройки из .env, параметры стратегий
│   └── __init__.py
│
├── data/                # БИРЖЕВЫЕ ДАННЫЕ
│   ├── binance_client.py    # REST API Binance Futures
│   └── orderflow_ws.py      # WebSocket (CVD, OI)
│
├── database/            # БАЗА ДАННЫХ
│   ├── schema.sql       # Схема SQLite (7 таблиц)
│   └── db.py            # Асинхронный доступ
│
├── engine/              # ЯДРО АНАЛИТИКИ
│   ├── pipeline.py          # Главный 15-мин цикл анализа
│   ├── market_state.py      # ADX, ATR → режим рынка
│   ├── liquidity_map.py     # Уровни ликвидности 1D/4H
│   ├── confidence.py        # Расчёт confidence score
│   ├── squeeze.py           # Squeeze detector (4H BB)
│   ├── orderflow.py         # OI cascade, funding
│   ├── indicators.py        # Тех. индикаторы
│   └── candle_loader.py     # Загрузка свечей
│
├── strategies/          # ТОРГОВЫЕ СТРАТЕГИИ
│   ├── sweep_reversal.py    # Стратегия 1: пробой ликвидности
│   └── breakout.py          # Стратегия 2: волатильный прорыв
│
├── telegram/            # TELEGRAM
│   ├── bot.py               # Aiogram бот
│   └── formatter.py         # Форматирование сообщений
│
├── web/                 # FASTAPI СЕРВЕР
│   ├── app.py               # Основное приложение
│   ├── middleware.py        # Auth middleware
│   ├── dependencies.py      # DI (db, client)
│   └── routes/
│       ├── health.py        # /health, /metrics
│       ├── signals.py       # /signals/*
│       ├── ui.py            # /dashboard
│       ├── logs.py          # /logs
│       ├── settings.py      # /settings
│       ├── backtest.py      # /backtest
│       └── downloads.py     # /downloads/*
│
├── backtesting/         # БЭКТЕСТИНГ
│   ├── backtester.py        # Движок бэктестирования
│   └── config.py            # Настройки бэктеста
│
├── scripts/             # УТИЛИТЫ
│   ├── signal_replay.py     # Replay сигналов на истории
│   ├── replay_sweep.py      # Parameter sweep (MFE/MAE)
│   └── REPLAY_GUIDE.md      # Документация replay
│
├── tests/               # ТЕСТЫ
│   ├── test_*.py            # Юнит-тесты
│   └── run_all.py           # Runner всех тестов
│
├── results/             # РЕЗУЛЬТАТЫ
│   ├── signal_replay_*.csv  # Экспорты replay
│   └── replay_comparison_*.csv  # Сравнение конфигураций
│
├── logs/                # ЛОГИ
│   └── bot.log
│
├── data/                # ДАННЫЕ (SQLite)
│   ├── signals.db         # Сигналы, циклы, метрики
│   └── orderflow.db       # OI, CVD snapshots
│
├── .env                 # ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (НЕ в git!)
├── .env.example         # Шаблон .env
├── main.py              # ТОЧКА ВХОДА
├── requirements.txt     # ЗАВИСИМОСТИ
├── Dockerfile           # Docker образ
└── docker-compose.yml   # Docker Compose
```

---

## ⚙️ 2. Конфигурация

### .env (обязательные переменные)

```env
# Telegram
TELEGRAM_BOT_TOKEN=8749354405:AAF...
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_CHANNEL_LINK=https://t.me/your_channel

# Binance
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
TESTNET=false                    # true для testnet, false для live

# База данных и логирование
DB_PATH=data/signals.db
LOG_LEVEL=INFO

# Торговые настройки
ACCOUNT_BALANCE=10000
EXECUTION_BASIS=limit            # market или limit

# API Security (для веб-интерфейса)
API_KEY=dev_local_key_12345      # Ключ для API
DEV_MODE=true                    # true для локальной разработки
```

### config/settings.py (ключевые параметры)

| Параметр | Значение | Описание |
|----------|----------|----------|
| `confidence_threshold` | 70 | Мин. уверенность для сигнала |
| `min_rr` | 2.0 | Мин. риск/прибыль |
| `quiet_atr_min` | 0.20% | Нижняя граница QUIET режима |
| `quiet_atr_max` | 0.60% | Верхняя граница QUIET режима |
| `adx_trending_threshold` | 25 | ADX > 25 = тренд |
| `volume_spike_multiplier` | 1.2 | Объем ≥ 1.2× MA20 = спайк |
| `max_leverage` | 10.0 | Макс. плечо |
| `max_risk_per_trade_pct` | 2.0 | Риск на сделку (%) |
| `tp1_size_pct` | 0.3-0.5 | Размер TP1 (30-50%) |
| `sl_atr_multiplier` | 0.5 | SL = 0.5×ATR |
| `max_candles_hold` | 20 | Timeout в свечах (15m) |

---

## 🚀 3. Команды для разработки

### Локальный запуск (Windows)

```powershell
# 1. Создание виртуального окружения
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Установка зависимостей
pip install -r requirements.txt

# 3. Копирование .env
Copy-Item .env.example .env

# 4. Запуск в dry-run режиме (без Telegram)
python main.py --dry-run --log-level=DEBUG

# 5. Запуск в testnet режиме
python main.py --testnet --log-level=INFO

# 6. Запуск веб-сервера отдельно
python -m uvicorn web.app:app --host 0.0.0.0 --port 8001 --reload
```

### Docker

```powershell
# 1. Копирование .env
Copy-Item .env.example .env

# 2. Сборка и запуск
docker compose up --build

# 3. Просмотр логов
docker compose logs -f bot

# 4. Остановка
docker compose down
```

### Тесты

```powershell
# Запуск всех тестов
python -m pytest -q

# Запуск через runner
python tests\run_all.py

# Конкретный тест
python -m pytest tests/test_signal_replay.py -v

# Тесты replay sweep
python tests\test_replay_sweep.py
```

### Деплой на VPS

```powershell
# 1. Загрузка файлов на VPS (148.222.186.16:2222)
scp -P 2222 .env root@148.222.186.16:/opt/crypto-bot/
scp -rP 2222 scripts/ root@148.222.186.16:/opt/crypto-bot/scripts/
scp -rP 2222 tests/ root@148.222.186.16:/opt/crypto-bot/tests/

# 2. Подключение к VPS
ssh -p 2222 root@148.222.186.16

# 3. Перезапуск бота
cd /opt/crypto-bot
systemctl restart crypto-bot

# 4. Проверка логов
journalctl -u crypto-bot -f --no-pager
```

---

## 📊 4. База данных (SQLite)

### Таблица: signals

**Отправленные сигналы**

| Поле | Тип | Описание |
|------|-----|----------|
| `signal_id` | TEXT | Уникальный ID |
| `strategy` | TEXT | sweep_reversal / breakout |
| `direction` | TEXT | LONG / SHORT |
| `session` | TEXT | asian / london / ny |
| `entry_market` | REAL | Рыночная цена входа |
| `entry_limit` | REAL | Лимитная цена входа |
| `stop_loss` | REAL | Уровень стоп-лосса |
| `take_profit` | REAL | Уровень тейк-профита |
| `tp1_price` | REAL | TP1 (частичная фиксация) |
| `tp1_rr` | REAL | RR для TP1 |
| `tp1_size_pct` | REAL | Размер TP1 (%) |
| `final_tp_size_pct` | REAL | Размер финального TP (%) |
| `rr_ratio` | REAL | Общий RR |
| `execution_basis` | TEXT | market / limit |
| `confidence_score` | INTEGER | 0-100 |
| `confidence_breakdown` | TEXT | JSON с факторами |
| `market_state` | TEXT | ranging / trending |
| `volatility_regime` | TEXT | blocked / quiet / normal |
| `adx_value` | REAL | ADX значение |
| `atr_pct` | REAL | ATR% |
| `status` | TEXT | sent / closed / cancelled |
| `result_pnl_pct` | REAL | Итоговый PnL% |
| `closed_at` | TEXT | Время закрытия |

### Таблица: cycle_summary

**Результаты каждого 15-мин цикла**

| Поле | Тип | Описание |
|------|-----|----------|
| `cycle_id` | TEXT | Уникальный ID цикла |
| `analysis_time_utc` | TEXT | Время анализа |
| `session` | TEXT | asian / london / ny / off-hours |
| `market_state` | TEXT | ranging / trending |
| `operating_mode` | TEXT | normal / quiet / blocked |
| `tradeable` | INTEGER | 0/1 |
| `liquidity_levels_found` | INTEGER | Найдено уровней |
| `liquidity_levels_eligible` | INTEGER | Подходящих уровней |
| `squeeze_active` | INTEGER | 0/1 |
| `funding_rate` | REAL | Funding rate |
| `oi_change_pct` | REAL | Изменение OI% |
| `sweep_candidate` | INTEGER | 0/1 |
| `breakout_candidate` | INTEGER | 0/1 |
| `confidence_score` | INTEGER | 0-100 |
| `confidence_threshold` | INTEGER | Порог для сигнала |
| `final_status` | TEXT | signal / no_signal / skip / error |
| `final_reason` | TEXT | Причина решения |
| `blocker_reason` | TEXT | Причина блокировки |

### Таблица: liquidity_pools

**Уровни ликвидности**

| Поле | Тип | Описание |
|------|-----|----------|
| `timeframe` | TEXT | 1d / 4h |
| `pool_type` | TEXT | equal_highs / equal_lows / swing_high / swing_low |
| `price` | REAL | Цена уровня |
| `touch_count` | INTEGER | Количество касаний |
| `strength` | TEXT | strong / moderate / weak |
| `is_active` | INTEGER | 0/1 |
| `mitigated` | INTEGER | 0/1 (пробит ли) |

### Другие таблицы

- `oi_snapshots` — снимки Open Interest (15 мин, 14 дней)
- `cvd_buckets` — CVD дельты по сессиям
- `signal_cooldowns` — дедупликация сигналов (60 мин)
- `system_logs` — логи системы
- `signal_replay_results` — результаты replay (добавляется после replay)

---

## 🔄 5. Пайплайн обработки сигналов

### Цикл анализа (каждые 15 минут)

```
┌─────────────────────────────────────────────────────────┐
│  1. Загрузка свечей (15m, 4h, 1d)                       │
│     • Binance Futures API                               │
│     • OHLCV + volume                                    │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  2. Market State (engine/market_state.py)               │
│     • ADX: trending (>25) / dead_zone (20-25) / ranging │
│     • ATR%: blocked (<0.2%) / quiet (0.2-0.6%) / normal │
│     • Session: asian / london / ny / off-hours          │
│     → SKIP если: dead_zone ИЛИ blocked ИЛИ off-hours    │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  3. Liquidity Map (engine/liquidity_map.py)             │
│     • equal_highs / equal_lows (1D + 4H)                │
│     • touch_count, strength, freshness                  │
│     • Фильтр: только активные уровни                    │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  4. Squeeze Detector (engine/squeeze.py)                │
│     • Bollinger Bands сжатие (4H)                       │
│     • BB width < MA20(BB width) × 0.7                   │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  5. Order Flow (engine/orderflow.py)                    │
│     • Funding rate (Binance)                            │
│     • OI cascade (падение OI + движение цены)           │
│     • CVD divergence (из WebSocket)                     │
└─────────────────────────────────────────────────────────┘
                           ↓
         ┌───────────────┴───────────────┐
         ↓                               ↓
┌─────────────────────┐         ┌─────────────────────┐
│  6A. Sweep Reversal │         │  6B. Breakout       │
│  (приоритет)        │         │  (только NORMAL +   │
│  • Пробой уровня    │         │   squeeze active)   │
│  • Rejection candle │         │  • Прорыв BB        │
│  • Wick ≥ 2.5×body  │         │  • SL: 1.5×ATR      │
│  • Volume spike     │         │  • TP: 2-4%         │
└─────────────────────┘         └─────────────────────┘
         ↓                               ↓
         └───────────────┬───────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  7. Confidence Score (engine/confidence.py)             │
│     ≥ 70 для сигнала                                    │
│     +30 Liquidity sweep confirmed                       │
│     +20 Volume spike ≥ 1.2× MA20                        │
│     +20 Session active (london/ny)                      │
│     +20 Squeeze active                                  │
│     +15 CVD divergence                                  │
│     +15 Liquidation cascade                             │
│     +10 Trend alignment (ADX > 25)                      │
│     -15 Counter-trend trade                             │
│     -25 Extreme funding (>0.10%)                        │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  8. Cooldown check (database/db.py)                     │
│     • Проверка: был ли сигнал за 60 мин                 │
│     • same_pair + same_direction                        │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  9. Save to DB + Telegram notification                  │
│     • INSERT INTO signals                               │
│     • notifier.send()                                   │
└─────────────────────────────────────────────────────────┘
```

### Режимы работы (Operating Modes)

| Режим | ATR% | Стратегии | Сессии | Confidence | Min RR | TP1 |
|-------|------|-----------|--------|------------|--------|-----|
| **BLOCKED** | < 0.20% | ❌ Все отключены | — | — | — | — |
| **QUIET** | 0.20–0.60% | Sweep only | Все | ≥ 60 | 1.3 | 2.0R |
| **NORMAL** | ≥ 0.60% | Sweep + Breakout | Все | ≥ 70 | 2.0 | 2.0-2.5R |

### Детали стратегий

#### Sweep Reversal (приоритет)

```python
# Точка входа
- Пробой liquidity уровня
- Rejection candle (wick ≥ 2.5× body)
- Volume spike ≥ 1.2× MA20

# Exit модель
- SL: 0.5×ATR от entry
- TP1: 2.0R (30-50% позиции)
- TP2: ближайший liquidity level (50-70%)
- Timeout: 20 свечей (5 часов)
```

#### Breakout (только NORMAL + squeeze)

```python
# Точка входа
- Прорыв Bollinger Bands (4H)
- Volume confirmation
- ADX > 20 (тренд)

# Exit модель
- SL: 1.5×ATR
- TP: 2-4% (фиксированный)
- Timeout: 30 свечей
```

---

## 🎯 6. Exit-модель (Replay & MFE/MAE)

### Параметры exit

| Параметр | Значение | Описание |
|----------|----------|----------|
| `tp1_multiplier` | 2.0 | TP1 = 2.0×R |
| `tp1_size_pct` | 0.3-0.5 | 30-50% позиции |
| `sl_atr_multiplier` | 0.5 | SL = 0.5×ATR |
| `max_candles_hold` | 20 | Timeout = 20 свечей |
| `tp_model` | liquidity | liquidity / capped / reduced_multiple |
| `tp_max_pct_quiet` | 1.5% | Макс. TP в QUIET режиме |

### Replay сигналов

```powershell
# Replay последних 50 сигналов
python scripts/signal_replay.py --limit 50

# Replay с кастомными параметрами
python scripts/signal_replay.py --tp-model capped --tp-max-pct 1.0 --sl-mult 0.8

# Parameter sweep (14 конфигураций)
python scripts/replay_sweep.py --limit 100

# Только эксперимент A (timeout)
python scripts/replay_sweep.py --experiment A
```

### Метрики MFE/MAE

| Метрика | Формула | Цель |
|---------|---------|------|
| **MFE** | `(max_price - entry) / entry × 100` (LONG) | > 2.0R |
| **MAE** | `(entry - min_price) / entry × 100` (LONG) | < SL |
| **MFE/MAE** | `avg(MFE) / avg(MAE)` | > 1.5 |
| **TP1 hit rate** | `tp1_hits / validated` | > 50% |
| **Timeout PnL median** | `median(pnl on timeout)` | > 0 |

### Success Criteria (для sweep)

| Приоритет | Критерий | Порог |
|-----------|----------|-------|
| **P0** | Expectancy | > 0.5% |
| **P0** | Profit Factor | > 1.5 |
| **P1** | SL rate | < 40% |
| **P2** | MFE/MAE ratio | > 1.5 |

**Verdict:** ✅ PASS / ⚠️ PARTIAL / ❌ FAIL

---

## 🌐 7. Веб-интерфейс (FastAPI)

### Эндпоинты

| Endpoint | Метод | Описание | Auth |
|----------|-------|----------|------|
| `/health` | GET | Статус компонентов | ❌ |
| `/metrics` | GET | Prometheus метрики | ❌ |
| `/dashboard` | GET | Веб-интерфейс | ✅ |
| `/signals/` | GET | Последние сигналы | ✅ |
| `/signals/stats` | GET | Статистика 24h | ✅ |
| `/signals/export.csv` | GET | Экспорт в CSV | ✅ |
| `/logs` | GET | Логи бота | ✅ |
| `/settings` | GET/POST | Настройки бота | ✅ |
| `/backtest` | GET/POST | Бэктестинг | ✅ |
| `/downloads/*` | GET | Скачивание файлов | ❌ |

### Auth middleware

```python
# Заголовок для API
X-API-Key: dev_local_key_12345

# Или DEV_MODE=true в .env (отключает auth для локальной разработки)
```

### URL для доступа

- **Локально:** http://localhost:8001/dashboard
- **VPS:** http://148.222.186.16:8001/dashboard

---

## 📝 8. Стили кода

### Именование

```python
# Переменные и функции: snake_case
def calculate_mfe_mae(candles, entry_price, direction):
    mfe_pct = ...
    return mfe_pct, mae_pct

# Классы: PascalCase
class ReplayConfig:
    pass

# Константы: UPPER_CASE
DEFAULT_DB_PATH = Path("data/signals.db")
INTERVAL_MS_15M = 900_000

# Приватные методы: _prefix
def _normalize_num(value):
    return None if value is None else float(value)
```

### Типизация

```python
# Обязательно указывать типы
def replay_signal(
    signal_row: sqlite3.Row,
    future_df: pd.DataFrame,
    cfg: ReplayConfig
) -> dict[str, Any]:
    ...

# Union types
tp_max_pct: float | None = None

# TypedDict для сложных структур
from typing import TypedDict

class SignalDict(TypedDict):
    signal_id: str
    strategy: str
    direction: str
```

### Документирование

```python
def calculate_mfe_mae(candles: pd.DataFrame, entry_price: float, direction: str) -> tuple[float | None, float | None]:
    """
    Расчёт MFE (Maximum Favorable Excursion) и MAE (Maximum Adverse Excursion).

    Args:
        candles: DataFrame с OHLC за период сделки
        entry_price: Цена входа
        direction: LONG или SHORT

    Returns:
        (mfe_pct, mae_pct) или (None, None) если нет данных
    """
    ...
```

---

## 🧪 9. Тестирование

### Структура тестов

```
tests/
├── test_signal_replay.py      # Тесты replay
├── test_replay_sweep.py       # Тесты success criteria
├── test_backtester_execution.py
├── test_confidence.py
├── test_integration.py
└── run_all.py                 # Runner
```

### Запуск тестов

```powershell
# Все тесты
python -m pytest -q

# С выводом
python -m pytest -v

# Конкретный файл
python -m pytest tests/test_signal_replay.py -v

# С coverage
python -m pytest --cov=engine --cov-report=html
```

### Написание тестов

```python
def test_replay_limit_signal_tp1_then_final_tp():
    future = pd.DataFrame([...])
    result = replay_signal(_signal_row(), future, ReplayConfig())
    
    assert result["validation_status"] == "validated"
    assert result["tp1_hit"] == 1
    assert result["final_tp_hit"] == 1
```

---

## 🔧 10. Полезные скрипты

### signal_replay.py

```powershell
# Replay последних 50 сигналов
python scripts/signal_replay.py --limit 50

# Replay одного сигнала по ID
python scripts/signal_replay.py --signal-id 85325a8415d6fc4a

# С кастомными параметрами
python scripts/signal_replay.py --tp-model capped --tp-max-pct 1.0 --sl-mult 0.8
```

### replay_sweep.py

```powershell
# Полный sweep (14 конфигураций)
python scripts/replay_sweep.py --limit 100

# Только эксперимент A (timeout)
python scripts/replay_sweep.py --experiment A

# Вывод сравнения таблицей
# (автоматически после запуска)
```

### Экспорт данных

```powershell
# Экспорт сигналов в CSV
curl http://localhost:8001/signals/export.csv -o signals.csv

# Через веб-интерфейс
# /dashboard → Export → CSV
```

---

## 📚 11. Документация в проекте

| Файл | Описание |
|------|----------|
| `README.md` | Основная документация |
| `README_SIGNAL_GUIDE.md` | Мониторинг сигналов |
| `EXECUTION_RR_MODEL.md` | Модель RR и exits |
| `STRATEGY.md` | Описание стратегий |
| `STRATEGY_FULL_DESCRIPTION.md` | Полное описание стратегий |
| `TZ_OPTIMAL_STRATEGY_V5.md` | ТЗ на стратегию v5 |
| `DEPLOYMENT.md` | Деплой на VPS |
| `TELEGRAM_CHANNEL_GUIDE.md` | Telegram канал |
| `scripts/REPLAY_GUIDE.md` | Replay и parameter sweep |
| `PROJECT_RULES.md` | **Этот файл** |

---

## 🚨 12. Чек-лист перед деплоем

### Локально

- [ ] `.env` скопирован и настроен
- [ ] `DEV_MODE=true` для разработки
- [ ] Тесты проходят: `python -m pytest -q`
- [ ] `python main.py --dry-run` работает

### VPS

- [ ] Файлы загружены: `scp -P 2222 ...`
- [ ] `.env` обновлён на сервере
- [ ] `TESTNET=false` для live
- [ ] `systemctl restart crypto-bot`
- [ ] `journalctl -u crypto-bot -f` — ошибок нет
- [ ] Веб-интерфейс доступен: `http://148.222.186.16:8001/dashboard`
- [ ] Telegram бот отвечает: `/start`, `/status`

---

## 🆘 13. Troubleshooting

### Ошибка: "API_KEY not configured"

**Решение:**
```env
# В .env
API_KEY=dev_local_key_12345
DEV_MODE=true
```

### Ошибка: "Unit bot_final.service not found"

**Решение:**
```bash
# Правильное имя сервиса
systemctl restart crypto-bot
```

### Ошибка: "No module named 'xxx'"

**Решение:**
```powershell
# Переустановить зависимости
pip install -r requirements.txt --upgrade
```

### Бот не отправляет сигналы

**Проверка:**
```powershell
# 1. Проверить логи
journalctl -u crypto-bot -f

# 2. Проверить TELEGRAM_BOT_TOKEN
cat .env | grep TELEGRAM

# 3. Проверить статус бота
curl http://localhost:8001/health
```

### Веб-интерфейс не открывается

**Проверка:**
```bash
# 1. Проверить процесс
netstat -tlnp | grep python

# 2. Порт 8001 должен быть открыт
# 3. Проверить firewall
ufw status
```

---

## 📞 14. Контакты и поддержка

- **Telegram канал:** https://t.me/+urBYFrzObzU3Y2Ey
- **VPS:** 148.222.186.16:2222 (root)
- **Локальная разработка:** d:\bot_final

---

**Версия документа:** 1.0  
**Дата создания:** 2026-03-27  
**Автор:** Development Team
