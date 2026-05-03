# Примеры конфигурации Crypto Signal Bot v3

В этом документе приведены примеры конфигурации для различных сценариев развёртывания бота.

## Базовый .env файл

Создайте файл `.env` в корне проекта на основе `.env.example`:

```env
# Telegram Bot (обязательно)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_CHANNEL_LINK=https://t.me/your_channel

# Binance API (обязательно)
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret

# Режим тестовой сети (рекомендуется для начала)
TESTNET=true

# Путь к базе данных
DB_PATH=data/signals.db

# Уровень логирования
LOG_LEVEL=INFO

# Баланс счёта для расчёта позиции (в USDT)
ACCOUNT_BALANCE=10000

# Список торговых пар (через запятую)
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT

# API ключ для доступа к веб-интерфейсу
# Сгенерируйте безопасный ключ: python -c "import secrets; print(secrets.token_urlsafe(32))"
API_KEY=dev_local_key_12345

# Режим разработки (отключает проверку API ключа)
DEV_MODE=true
```

## Конфигурация для продакшена (VPS)

Для работы на реальной бирже измените следующие параметры:

```env
TESTNET=false
DEV_MODE=false
API_KEY=strong_production_key_here_generate_with_secrets
LOG_LEVEL=WARNING
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,ADAUSDT,XRPUSDT
```

## Конфигурация для Docker

При использовании Docker Compose переменные окружения передаются через `docker-compose.yml`. Пример `docker-compose.yml`:

```yaml
version: '3.8'
services:
  crypto-bot:
    build: .
    container_name: crypto-bot
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    ports:
      - "8000:8000"
```

Соответствующий `.env` файл должен быть в той же директории.

## Конфигурация для systemd (VPS)

Файл сервиса `deploy/crypto-bot.service` уже содержит базовые настройки. Для адаптации под ваше окружение отредактируйте:

```ini
[Unit]
Description=Crypto Signal Bot v3
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/crypto-bot
EnvironmentFile=/home/ubuntu/crypto-bot/.env
ExecStart=/usr/bin/python3 /home/ubuntu/crypto-bot/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Убедитесь, что путь к `.env` правильный.

## Настройки торговли (config/settings.py)

Основные торговые параметры находятся в `config/settings.py`. Вы можете изменить их, отредактировав файл или через переменные окружения (не все поддерживаются).

Ключевые параметры:

```python
quiet_atr_min = 0.0012          # Минимальный ATR для режима QUIET (0.12%)
normal_atr_min = 0.0018         # Минимальный ATR для режима NORMAL (0.18%)
adx_threshold = 30.0            # Порог ADX для определения тренда
confidence_threshold = 60       # Минимальный уровень уверенности для сигнала
cooldown_minutes = 60           # Количество минут между сигналами на одну пару
```

Чтобы изменить эти параметры без редактирования кода, создайте файл `config/local_settings.py` (если поддерживается) или модифицируйте `config/settings.py` напрямую.

## Пример для мульти-таймфрейм анализа

Бот использует таймфреймы 1D и 4H для анализа ликвидности. Вы можете добавить другие таймфреймы, изменив код в `engine/liquidity_map.py` и `engine/pipeline.py`.

## Конфигурация веб-интерфейса

Веб-интерфейс работает на порту 8000. Для изменения порта отредактируйте `web/app.py` или установите переменную окружения `PORT`.

```env
PORT=8080
```

## Безопасность

1. **Никогда не коммитьте `.env` файл** — он уже в `.gitignore`.
2. Используйте разные API ключи для тестовой и основной сети.
3. Регулярно обновляйте `API_KEY` в продакшене.
4. Ограничьте доступ к веб-интерфейсу с помощью брандмауэра или nginx.

## Переменные окружения для расширенной настройки

| Переменная | Описание | Значение по умолчанию |
|------------|----------|----------------------|
| `TELEGRAM_BOT_TOKEN` | Токен бота Telegram | (обязательно) |
| `TELEGRAM_CHAT_ID` | ID чата для уведомлений | (обязательно) |
| `BINANCE_API_KEY` | API ключ Binance | (обязательно) |
| `BINANCE_API_SECRET` | Секрет Binance | (обязательно) |
| `TESTNET` | Использовать тестовую сеть Binance | `true` |
| `DB_PATH` | Путь к SQLite базе данных | `data/signals.db` |
| `LOG_LEVEL` | Уровень логирования (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `ACCOUNT_BALANCE` | Баланс счёта в USDT | `10000` |
| `SYMBOLS` | Список торговых пар | `BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT` |
| `API_KEY` | Ключ аутентификации веб-API | `dev_local_key_12345` |
| `DEV_MODE` | Режим разработки (отключает аутентификацию) | `false` |
| `PORT` | Порт веб-сервера | `8000` |
| `HOST` | Хост веб-сервера | `0.0.0.0` |

## Проверка конфигурации

После настройки `.env` запустите бота в тестовом режиме:

```bash
python main.py --dry-run
```

Убедитесь, что бот подключается к Binance, загружает свечи и начинает анализ без ошибок.

## Дополнительные ресурсы

- [README.md](README.md) — основная документация
- [DEPLOYMENT.md](DEPLOYMENT.md) — руководство по развёртыванию
- [GITHUB_PUSH_INSTRUCTIONS.md](GITHUB_PUSH_INSTRUCTIONS.md) — инструкция по загрузке на GitHub