# 📈 Web UI Update — Sprint 2 (Charts & Live PnL)

**Дата:** 2026-03-28  
**Версия:** 3.3.0 (charts & live PnL)  
**Статус:** ✅ Готово к деплою

---

## 📋 Обзор изменений

Улучшения веб-интерфейса для визуализации рынков и отслеживания активных сигналов:
- **График цен** (Lightweight Charts) с выбором пары и таймфрейма
- **Активные сигналы** с реальным PnL и прогрессом до TP/SL
- **API** для рыночных данных и активных сигналов

---

## 🗂️ Новые файлы

| Файл | Описание |
|------|----------|
| `web/routes/active_signals.py` | API для активных сигналов с PnL |
| `web/routes/market_data.py` | API для свечей и цен (Lightweight Charts) |

---

## 🎯 Новые возможности

### 1. График цен (Lightweight Charts)

**URL:** `/dashboard` (новая секция)

**Функции:**
- 📊 Японские свечи (15m, 1h, 4h, 1d)
- 🔄 Выбор пары (BTC/ETH/SOL/BNB)
- 📈 Интерактивный график (zoom, crosshair)
- 🎨 Адаптивный дизайн

**API:**
```
GET /market/candles?symbol=BTCUSDT&interval=15m&limit=200
```

**Ответ:**
```json
[
  {
    "time": 1711627200,
    "open": 71234.50,
    "high": 71456.00,
    "low": 71100.00,
    "close": 71345.00,
    "volume": 1234.56
  }
]
```

---

### 2. Активные сигналы (Live PnL)

**URL:** `/dashboard` (новая секция)

**Функции:**
- 📍 Карточки активных сигналов
- 💰 PnL в реальном времени (% и $)
- 📊 Прогресс до TP (progress bar)
- 🛑 Дистанция до SL
- 🔄 Авто-обновление каждые 10 сек

**Карточка сигнала:**
```
┌─────────────────────────────────┐
│ BTCUSDT              LONG 🟢    │
├─────────────────────────────────┤
│ Entry:    71234.50              │
│ Current:  71456.00              │
│ PnL:      +0.31% ✅             │
│ RR:       2.4                   │
├─────────────────────────────────┤
│ Progress to TP: [████░░] 65%   │
├─────────────────────────────────┤
│ SL: 70800.00   TP: 72000.00    │
└─────────────────────────────────┘
```

**API:**
```
GET /signals/active
```

**Ответ:**
```json
[
  {
    "signal_id": "abc123...",
    "pair": "BTCUSDT",
    "direction": "LONG",
    "entry_price": 71234.50,
    "stop_loss": 70800.00,
    "take_profit": 72000.00,
    "current_price": 71456.00,
    "pnl_pct": 0.31,
    "progress_to_tp": 0.65,
    "distance_to_sl": 0.61,
    "rr_ratio": 2.4,
    "status": "sent"
  }
]
```

---

## 🚀 Деплой

### Локально

```powershell
# 1. Проверка синтаксиса
python -m py_compile web/app.py web/routes/active_signals.py web/routes/market_data.py

# 2. Запустить бота
python main.py --dry-run --log-level=INFO

# 3. Открыть dashboard
# http://localhost:8001/dashboard
```

### VPS

```bash
# 1. Загрузить файлы
scp -P 2222 web/app.py root@148.222.186.16:/opt/crypto-bot/web/
scp -P 2222 web/routes/active_signals.py web/routes/market_data.py root@148.222.186.16:/opt/crypto-bot/web/routes/
scp -P 2222 web/static/dashboard.html root@148.222.186.16:/opt/crypto-bot/web/static/

# 2. Перезапустить бота
ssh -p 2222 root@148.222.186.16
cd /opt/crypto-bot
systemctl restart crypto-bot

# 3. Проверить логи
journalctl -u crypto-bot -f --no-pager
```

---

## 📊 API Endpoints

### Market Data

| Endpoint | Описание |
|----------|----------|
| `GET /market/candles?symbol=BTCUSDT&interval=15m` | Свечи для графика |
| `GET /market/price?symbol=BTCUSDT` | Текущая цена |
| `GET /market/funding?symbol=BTCUSDT` | Funding rate |

### Active Signals

| Endpoint | Описание |
|----------|----------|
| `GET /signals/active` | Все активные сигналы |
| `GET /signals/active?pair=BTCUSDT` | Активные сигналы по паре |

---

## ⚠️ Возможные проблемы

### 1. График не загружается

**Причина:** Lightweight Charts CDN недоступен  
**Решение:** Проверить интернет-соединение или скачать библиотеку локально

```bash
# Скачать локально
curl -o web/static/lightweight-charts.js \
  https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js
```

Обновить `dashboard.html`:
```html
<script src="lightweight-charts.js"></script>
```

### 2. PnL не обновляется

**Причина:** API /market/price недоступен  
**Решение:** Проверить логи на наличие ошибок Binance API

```bash
journalctl -u crypto-bot -f | grep "market/price"
```

### 3. Нет активных сигналов

**Причина:** Нет открытых сигналов в БД  
**Решение:** Это нормально в выходные. Проверить в понедельник.

```sql
SELECT COUNT(*) FROM signals WHERE status IN ('sent', 'partial_tp1');
```

---

## ✅ Чек-лист успешного деплоя

- [ ] Файлы загружены на VPS
- [ ] Бот перезапущен: `systemctl restart crypto-bot`
- [ ] График загружается: `http://148.222.186.16:8001/dashboard`
- [ ] Выбор пары и таймфрейма работает
- [ ] Активные сигналы отображаются (когда есть)
- [ ] PnL обновляется каждые 10 сек
- [ ] Прогресс до TP отображается корректно

---

## 📈 Следующие шаги (Sprint 3)

**План улучшений:**
1. Тёмная тема
2. Мобильная версия (адаптивность)
3. Browser notifications
4. Отметки сигналов на графике

**Время:** 2-3 часа

---

**Готово!** 🎉

Теперь веб-интерфейс отображает графики цен и активные сигналы с реальным PnL!
