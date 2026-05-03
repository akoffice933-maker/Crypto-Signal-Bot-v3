# Crypto Signal Bot v3

Async trading bot for cryptocurrency futures signal generation with Binance market data, SQLite persistence, Telegram delivery, backtesting, and a FastAPI web interface.

## Features

- **15-minute analysis pipeline** with async scheduler
- **Dual trading strategies**:
  - `sweep_reversal`: liquidity sweep with rejection confirmation
  - `breakout`: 4H squeeze breakout using Bollinger expansion
- **Multi-pair support**: Analyze multiple trading pairs simultaneously
- **SQLite storage** for signals, cooldowns, liquidity pools, and OI snapshots
- **Telegram notifications** with formatted trade plans
- **FastAPI web interface** with endpoints: `/health`, `/signals`, `/signals/stats`, `/signals/liquidity`, `/metrics`, `/dashboard`
- **CSV export** and Google Sheets sync via webhook
- **Backtesting utilities** and comprehensive test suite
- **Weekend trading support** (configurable)
- **Dual-mode operation**: NORMAL/QUIET/BLOCKED based on market volatility

## Quick Start

### Prerequisites
- Python 3.9+
- Binance API key (with futures trading enabled)
- Telegram Bot Token

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/akoffice933-maker/crypto-signal-bot-v3.git
   cd crypto-signal-bot-v3
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

5. **Run the bot**
   ```bash
   python main.py --log-level=INFO
   ```

### Docker Installation
```bash
cp .env.example .env
docker-compose up --build
```

## Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
# Binance API
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
TESTNET=true  # Use testnet for development

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Trading Settings
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT
ACCOUNT_BALANCE=10000

# Application
LOG_LEVEL=INFO
API_KEY=your_api_key_for_web_interface
DEV_MODE=false
```

### Trading Settings

Key parameters in `config/settings.py`:
- `quiet_atr_min`: Minimum ATR% for trading (default: 0.12%)
- `normal_confidence_threshold`: Confidence threshold for NORMAL mode (default: 65)
- `quiet_confidence_threshold`: Confidence threshold for QUIET mode (default: 70)
- `quiet_breakout_min_adx`: Minimum ADX for breakout in QUIET mode (default: 30)

## Project Structure

```
crypto-signal-bot-v3/
├── main.py                 # Entry point
├── config/                 # Configuration
├── engine/                 # Core analysis engine
│   ├── pipeline.py         # Main analysis pipeline
│   ├── confidence.py       # Confidence scoring
│   ├── liquidity_map.py    # Liquidity level detection
│   └── indicators.py       # Technical indicators
├── strategies/             # Trading strategies
│   ├── sweep_reversal.py   # Sweep reversal strategy
│   └── breakout.py         # Breakout strategy
├── database/               # Database layer
├── data/                   # Market data clients
├── telegram/               # Telegram integration
├── web/                    # FastAPI web interface
├── tests/                  # Test suite
├── scripts/                # Utility scripts
└── deploy/                 # Deployment scripts
```

## Usage

### Running the Bot

```bash
# Normal mode
python main.py --log-level=INFO

# Dry run (no Telegram messages)
python main.py --dry-run --log-level=DEBUG

# Test mode
python main.py --testnet --log-level=INFO
```

### Web Interface

After starting the bot, access the web interface at `http://localhost:8000`:

- Dashboard: `http://localhost:8000/dashboard`
- Signals API: `http://localhost:8000/signals/api`
- Health check: `http://localhost:8000/health`
- Metrics: `http://localhost:8000/metrics`

### Telegram Commands

- `/start` - Bot status and mode
- `/active` - Show active signals
- `/pairs` - Show trading pairs and statistics
- `/export` - Export signals to CSV
- `/replay` - Replay recent signals

## Development

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test module
pytest tests/test_pipeline.py -v

# Run with coverage
pytest --cov=engine tests/
```

### Code Style

The project uses flake8 for code style checking:

```bash
flake8 .
```

### Adding New Strategies

1. Create a new strategy file in `strategies/`
2. Implement the strategy logic
3. Add strategy detection to `engine/pipeline.py`
4. Add tests in `tests/`

## Deployment

### VPS Deployment

See `deploy/` directory for deployment scripts:

```bash
# Linux/Mac
./deploy/deploy.sh

# Windows PowerShell
.\deploy\deploy.ps1
```

### Systemd Service

A systemd service file is provided in `deploy/crypto-bot.service`:

```bash
sudo cp deploy/crypto-bot.service /etc/systemd/system/
sudo systemctl enable crypto-bot
sudo systemctl start crypto-bot
```

## Monitoring

### Logs

```bash
# View bot logs
tail -f logs/bot.log

# Systemd logs
journalctl -u crypto-bot -f
```

### Metrics

Prometheus metrics are available at `http://localhost:8000/metrics`

### Health Checks

```bash
curl http://localhost:8000/health
```

## Troubleshooting

### Common Issues

1. **No signals generated**
   - Check market volatility (ATR%)
   - Verify Binance API connectivity
   - Check if market is in dead zone (ADX 15-25)

2. **Telegram messages not sending**
   - Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
   - Check bot has permission to send messages
   - Check rate limiting

3. **Database errors**
   - Verify write permissions for `data/` directory
   - Check SQLite file is not corrupted

### Debug Mode

Run with debug logging for detailed information:

```bash
python main.py --log-level=DEBUG
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This software is for educational and research purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred while using this bot. Cryptocurrency trading carries significant risk, and you should only trade with money you can afford to lose.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Support

For issues and questions, please open an issue on GitHub.
