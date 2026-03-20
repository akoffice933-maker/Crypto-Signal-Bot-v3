# Crypto Signal Bot v3

Async bot for BTCUSDT futures signal generation with Binance market data, SQLite persistence, Telegram delivery, backtesting, and a small FastAPI surface for health, signals, and Prometheus metrics.

Practical monitoring and signal-waiting guide: [README_SIGNAL_GUIDE.md](D:/bot_final/README_SIGNAL_GUIDE.md)

## Features

- 15-minute analysis pipeline with async scheduler
- Two trading strategies:
  - `sweep_reversal`: liquidity sweep with rejection confirmation
  - `breakout`: 4H squeeze breakout using Bollinger expansion
- SQLite storage for signals, cooldowns, liquidity pools, and OI snapshots
- Telegram notifications with formatted trade plans
- FastAPI endpoints: `/health`, `/signals`, `/signals/stats`, `/signals/liquidity`, `/metrics`, `/dashboard`
- CSV export and Google Sheets sync via webhook
- Critical error alerts and Telegram flood protection
- Backtesting utilities and local test suite

## Installation

### Local Python

1. Create and activate a virtual environment.
2. Install dependencies.
3. Copy `.env.example` to `.env` and fill required values.
4. Start the bot.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py --log-level=INFO
```

For startup validation, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are required unless you run in dry-run mode:

```powershell
python main.py --dry-run --log-level=DEBUG
```

### Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

The container exposes the API on `http://localhost:8000`.

## Configuration

Environment variables from `.env`:

```env
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
TESTNET=true
DB_PATH=data/signals.db
LOG_LEVEL=INFO
ACCOUNT_BALANCE=10000
GOOGLE_SHEETS_WEBHOOK_URL=
GOOGLE_SHEETS_TIMEOUT_SECONDS=10
TELEGRAM_MAX_MESSAGES_PER_MINUTE=20
TELEGRAM_MIN_INTERVAL_SECONDS=1.2
```

Important runtime notes:

- `--testnet` forces testnet URLs at startup.
- `--dry-run` skips Telegram validation and message sending.
- API and bot run in the same process; `/health` and `/metrics` stay available while the scheduler runs.
- Google Sheets sync uses `GOOGLE_SHEETS_WEBHOOK_URL` or a URL passed from the dashboard/API.
- Telegram sending is protected by local throttling using `TELEGRAM_MAX_MESSAGES_PER_MINUTE` and `TELEGRAM_MIN_INTERVAL_SECONDS`.

## Strategies

### 1. Liquidity Sweep Reversal

Looks for equal highs/lows on `1d` and `4h`, then waits for:

- a sweep through the liquidity level
- a close back inside the level
- a rejection candle with strong wick/body ratio
- optional order-flow confirmation via CVD, funding, and OI cascade

Typical use case: fade a failed breakout after liquidity is taken.

### 2. Volatility Breakout

Activates only when a 4H squeeze is detected and the latest 15m candle breaks outside Bollinger Bands. This strategy targets momentum continuation with fixed stop distance and a wider take-profit band.

Typical use case: trade expansion after prolonged compression.

## API

- `GET /health` returns component status plus 24h metrics
- `GET /signals/` lists recent stored signals
- `GET /signals/stats` returns 30-day aggregate stats
- `GET /signals/liquidity?current_price=60000` lists active liquidity pools
- `GET /signals/export.csv?limit=500` downloads recent signals as CSV
- `POST /signals/export/google-sheets` pushes signals to an Apps Script webhook
- `GET /metrics` exposes Prometheus-compatible gauges:
  - `crypto_signal_signals_24h`
  - `crypto_signal_winrate_24h`
  - `crypto_signal_avg_drawdown_pct_24h`
- `GET /dashboard` opens the built-in web interface

### Google Sheets Webhook Payload

The Google Sheets sync endpoint sends JSON in the shape:

```json
{
  "columns": ["signal_id", "created_at", "..."],
  "rows": [
    {"signal_id": "abc123", "strategy": "sweep_reversal", "status": "sent"}
  ]
}
```

The intended target is a deployed Google Apps Script web app that accepts POST requests and appends rows into a sheet.

## Example Signals

### Sweep Reversal

```text
BTCUSDT LONG 🟢

Strategy: Liquidity Sweep Reversal
Entry (Market): 60012.50
Entry (Limit):  59940.00
Stop Loss:     59780.00
Take Profit:   60650.00
RR:            2.8
Confidence:    82%

Market State: Range
Volatility:   Normal
Target Liquidity: Daily High

Order Flow:
• CVD bullish divergence
• Funding negative (-0.020%)

Analysis factors:
+30 Liquidity sweep confirmed
+20 Volume spike ≥1.2×
+20 Session: london
+15 CVD bullish divergence

🔑 `a1b2c3d4`
```

### Breakout

```text
BTCUSDT SHORT 🔴

Strategy: Volatility Breakout
Entry (Market): 60540.00
Stop Loss:     60963.78
Take Profit:   58723.80
RR:            4.3
Confidence:    76%

Market State: Range
Volatility:   High
Target Liquidity: —

Order Flow:
• Volatility squeeze active (4H)
• CVD bearish divergence

Analysis factors:
+25 Squeeze breakout
+20 Volume spike ≥1.2×
+20 Session: ny
+20 Volatility squeeze (4h)

🔑 `deadbeef`
```

## Testing

Run the full pytest suite:

```powershell
python -m pytest -q
```

Run the custom console runner:

```powershell
python tests\run_all.py
```

## Project Layout

```text
config/       runtime settings
data/         Binance REST and WebSocket clients
database/     SQLite schema and access layer
engine/       indicators, market state, confidence, pipeline
strategies/   signal generation logic
telegram/     message formatting and delivery
web/          FastAPI app and routes
backtesting/  offline evaluation tools
tests/        unit and integration tests
```
