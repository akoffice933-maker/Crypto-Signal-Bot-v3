# ⚡ Crypto Bot — Quick Start

## 🚀 Локальный запуск (5 минут)

```powershell
# 1. Клонировать/открыть проект
cd d:\bot_final

# 2. Активировать venv
.venv\Scripts\Activate.ps1

# 3. Установить зависимости (если нужно)
pip install -r requirements.txt

# 4. Проверить .env
cat .env | grep -E "API_KEY|DEV_MODE"
# Должно быть: DEV_MODE=true

# 5. Запустить бота
python main.py --dry-run --log-level=INFO

# 6. Открыть веб-интерфейс
# http://localhost:8001/dashboard
```

---

## 📦 Деплой на VPS (10 минут)

```powershell
# 1. Загрузить файлы
scp -P 2222 .env root@148.222.186.16:/opt/crypto-bot/
scp -rP 2222 scripts/ root@148.222.186.16:/opt/crypto-bot/scripts/

# 2. Подключиться к VPS
ssh -p 2222 root@148.222.186.16

# 3. Перезапустить бота
cd /opt/crypto-bot
systemctl restart crypto-bot

# 4. Проверить логи
journalctl -u crypto-bot -f --no-pager

# 5. Открыть веб-интерфейс
# http://148.222.186.16:8001/dashboard
```

---

## 🧪 Запуск тестов

```powershell
# Все тесты
python -m pytest -q

# Тесты replay
python tests/test_signal_replay.py
python tests/test_replay_sweep.py

# С выводом
python -m pytest -v
```

---

## 📊 Replay сигналов

```powershell
# Replay последних 50 сигналов
python scripts/signal_replay.py --limit 50

# Parameter sweep (14 конфигураций)
python scripts/replay_sweep.py --limit 100

# Только experiment A (timeout)
python scripts/replay_sweep.py --experiment A

# Результаты в results/
```

---

## 🔍 Проверка статуса

```powershell
# Локально
curl http://localhost:8001/health

# На VPS
ssh -p 2222 root@148.222.186.16 "curl http://localhost:8001/health"

# Telegram
/start
/status
```

---

## 📁 Структура (кратко)

```
d:\bot_final\
├── config/settings.py     # Настройки
├── engine/pipeline.py     # Главный цикл
├── strategies/            # Стратегии
├── web/                   # FastAPI сервер
├── scripts/               # Утилиты (replay, sweep)
├── tests/                 # Тесты
└── data/signals.db        # SQLite БД
```

---

## 🎯 Основные команды

| Команда | Описание |
|---------|----------|
| `python main.py` | Запуск бота |
| `python main.py --dry-run` | Без Telegram |
| `python main.py --testnet` | Testnet режим |
| `python -m pytest` | Запуск тестов |
| `python scripts/signal_replay.py` | Replay сигналов |
| `python scripts/replay_sweep.py` | Parameter sweep |
| `systemctl restart crypto-bot` | Перезапуск на VPS |

---

## 🔑 Переменные .env (минимум)

```env
TELEGRAM_BOT_TOKEN=...
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
TESTNET=false
DB_PATH=data/signals.db
API_KEY=dev_local_key_12345
DEV_MODE=true
```

---

## 📚 Документация

- **Полные правила:** `PROJECT_RULES.md`
- **Replay guide:** `scripts/REPLAY_GUIDE.md`
- **Стратегия:** `STRATEGY.md`
- **Деплой:** `DEPLOYMENT.md`

---

**Версия:** 3.0.0  
**Обновлено:** 2026-03-27
