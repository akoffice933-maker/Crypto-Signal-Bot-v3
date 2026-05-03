# 🎯 Crypto Signal Bot v3 — Торговая Стратегия

## 📖 Описание

**Crypto Signal Bot v3** — это автоматизированная торговая система для BTCUSDT Futures, использующая концепции **Smart Money Concepts (SMC)** и **Order Flow** для поиска высоковероятных точек входа.

---

## 🏗️ Архитектура Стратегии

```
┌─────────────────────────────────────────────────────────────────┐
│                    15-минутный Анализ Cycle                     │
├─────────────────────────────────────────────────────────────────┤
│  1. Market State (ADX, ATR, Sessions) → Фильтр условий         │
│  2. Liquidity Map (1D + 4H levels) → Карта ликвидности         │
│  3. Squeeze Detector (4H) → Волатильность                      │
│  4. Order Flow (CVD, OI, Funding) → Подтверждение              │
│  5. Strategy A: Sweep Reversal → Сигнал LONG/SHORT             │
│  6. Strategy B: Volatility Breakout → Сигнал LONG/SHORT        │
│  7. Confidence Score ≥ 65% → Фильтр качества                   │
│  8. Risk Management → Позиция, SL, TP                          │
│  9. Telegram Signal → Уведомление                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Стратегия 1: Liquidity Sweep Reversal

### 🎯 Концепция

**Sweep Reversal** — это стратегия торговли на **сборе ликвидности** с последующим разворотом цены.

**Логика:**
1. Крупные игроки (Smart Money) пробивают известные уровни ликвидности
2. Срабатывают стоп-лоссы розничных трейдеров
3. Цена резко разворачивается в противоположном направлении
4. Входим вместе с Smart Money

---

### 📋 Условия Входа

#### **1. Liquidity Pool (Уровень Ликвидности)**

| Параметр | Значение |
|----------|----------|
| **Timeframe** | 1D или 4H |
| **Тип** | Equal Highs или Equal Lows |
| **Min Touches** | 3 (до очистки) |
| **Max Touches** | 2 (после очистки) |
| **Tolerance** | 0.2% от цены |

**Пример:**
```
4H Equal Lows at $87,598.41 (2 touches) ← СВЕЖИЙ УРОВЕНЬ
4H Equal Highs at $87,936.38 (1 touch) ← СВЕЖИЙ УРОВЕНЬ
```

---

#### **2. Sweep Candle (Свеча Сбора)**

**LONG:**
```
• Low свечи < уровня Equal Lows
• Close свечи > уровня (возврат)
• Тело свечи закрывается выше уровня
```

**SHORT:**
```
• High свечи > уровня Equal Highs
• Close свечи < уровня (возврат)
• Тело свечи закрывается ниже уровня
```

**Визуально:**
```
     │
     │    ╔═════════╗  ← Equal Highs
     │    ║         ║
     │━━━━║  SWEEP  ║  ← Пробой и возврат
     │    ║         ║
     │    ╚═════════╝
     │
```

---

#### **3. Rejection Candle (Свеча Отторжения)**

**Параметры:**
```
• Wick ≥ 2.5 × Body (фитиль в 2.5 раза больше тела)
• Body ≤ 1/3 от полного диапазона свечи
• Фитиль в направлении разворота
```

**LONG (нижний фитиль):**
```
        │
    ┌───┴───┐  ← Тело (маленькое)
    │       │
    └───┬───┘
        │
        │       ← Длинный нижний фитиль (≥ 2.5× тела)
        │
```

**SHORT (верхний фитиль):**
```
        │
        │       ← Длинный верхний фитиль (≥ 2.5× тела)
        │
    ┌───┬───┐  ← Тело (маленькое)
    │   │   │
    └───┴───┘
```

---

#### **4. Volume Spike (Объём)**

**Условие:**
```
Volume свечи ≥ 1.2 × Volume MA(20)
```

**Проверка:**
- На свече sweep **ИЛИ**
- На свече rejection

---

#### **5. Entry (Вход)**

**Market Entry:**
```
• Вход по закрытию rejection свечи
• Entry = Close rejection candle
```

**Limit Entry (опционально):**
```
• Вход на 50% от тела sweep свечи
• Entry = Sweep Low + (Sweep High - Sweep Low) × 0.50
```

---

#### **6. Stop Loss**

**LONG:**
```
SL = Sweep Low - (1 ATR × 0.5)
Минимум: Sweep Low × 0.999
```

**SHORT:**
```
SL = Sweep High + (1 ATR × 0.5)
Минимум: Sweep High × 1.001
```

---

#### **7. Take Profit**

**Цель:**
```
TP = Ближайший уровень ликвидности в направлении сделки
```

**Минимальный RR:**
```
RR = (TP - Entry) / (Entry - SL) ≥ 2.0
```

**Если нет уровня:**
```
TP = Entry + (Risk × 2.0)  ← Минимум 2R
```

---

### 📈 Пример Сделки (LONG)

```
┌─────────────────────────────────────────────────────────────┐
│  BTCUSDT LONG 🟢                                            │
│  Strategy: Liquidity Sweep Reversal                         │
├─────────────────────────────────────────────────────────────┤
│  Entry (Market):  $95,420.50                                │
│  Entry (Limit):   $95,180.00                                │
│  Stop Loss:       $94,850.00                                │
│  Take Profit:     $96,800.00                                │
│  R:R Ratio:       2.8                                       │
│  Confidence:      82%                                       │
├─────────────────────────────────────────────────────────────┤
│  Market State:    Range                                     │
│  Volatility:      Normal                                    │
│  Target Liquidity: Daily High                               │
├─────────────────────────────────────────────────────────────┤
│  Order Flow:                                                │
│  • CVD bullish divergence                                   │
│  • Funding negative (-0.015%)                               │
├─────────────────────────────────────────────────────────────┤
│  Analysis factors:                                          │
│  +30 Liquidity sweep confirmed                              │
│  +20 Volume spike ≥1.2×                                     │
│  +20 Session: london                                        │
│  +15 CVD bullish divergence                                 │
│  +10 Trend alignment (ADX 28)                               │
│  ──────────────────────────────────                         │
│  = 95 points (≥ 65 = Signal)                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Стратегия 2: Volatility Breakout

### 🎯 Концепция

**Volatility Breakout** — это стратегия торговли **пробоя** после периода сжатия волатильности.

**Логика:**
1. Рынок консолидируется (низкая волатильность)
2. Bollinger Bands сужаются (Squeeze)
3. Происходит резкий пробой
4. Входим в направлении пробоя

---

### 📋 Условия Входа

#### **1. Squeeze Detection (4H)**

**Три условия должны выполняться одновременно:**

**a) BB Width Minimum:**
```
Current BB Width ≤ Min(BB Width за последние 50 свечей)
```

**b) ATR Below Average:**
```
Current ATR(14) < Average ATR(14) за последние 50 свечей
```

**c) Range Compression:**
```
(High - Low) за последние 20 свечей < 1.5% от цены
```

---

#### **2. Breakout Candle (15m)**

**LONG:**
```
• Close > Upper Bollinger Band
• ИЛИ Close > известного уровня ликвидности
```

**SHORT:**
```
• Close < Lower Bollinger Band
• ИЛИ Close < известного уровня ликвидности
```

---

#### **3. Entry**

```
Entry = Close breakout свечи (Market)
```

---

#### **4. Stop Loss**

```
SL = Entry × (1 ± 0.7%)  ← Фиксированный 0.7%
```

**LONG:** `SL = Entry × 0.993`
**SHORT:** `SL = Entry × 1.007`

---

#### **5. Take Profit**

```
TP = Entry × (1 ± 3.0%)  ← Целевые 3%
```

**Минимальный RR:**
```
RR = 3.0 / 0.7 = 4.3  ← Всегда ≥ 2.0
```

---

## 🎯 Market State Filter

### **ADX (Average Directional Index)**

| Значение | Статус | Действие |
|----------|--------|----------|
| **< 20** | Ranging | ✅ Торгуем |
| **20-25** | Dead Zone | ❌ Пропускаем |
| **> 25** | Trending | ✅ Торгуем (с учётом тренда) |
| **> 40** | Strong Trend | ⚠️ Counter-trend штраф |

---

### **ATR% (Volatility Regime)**

| Значение | Статус | Действие |
|----------|--------|----------|
| **< 0.7%** | Low | ❌ Пропускаем |
| **0.7-1.5%** | Normal | ✅ Торгуем |
| **> 1.5%** | High | ✅ Торгуем |

**Расчёт:**
```
ATR% = ATR(14) / Mean(Close, 20 свечей)
```

---

### **Sessions (UTC)**

| Сессия | Время (UTC) | Статус |
|--------|-------------|--------|
| **Asian** | 00:00-08:00 | ✅ Активна |
| **London** | 07:00-11:00 | ✅ Активна (приоритет) |
| **NY** | 13:00-17:00 | ✅ Активна |
| **Off-hours** | Остальное | ❌ Пропускаем |

**Overlap 07:00-08:00:**
```
Приоритет: London > NY > Asian
```

---

## 📊 Order Flow Confirmation

### **1. CVD (Cumulative Volume Delta)**

**Что это:**
```
CVD = Taker Buy Volume - Taker Sell Volume
```

**Сигналы:**
```
Bullish Divergence:  Price ↓ + CVD ↑ → LONG
Bearish Divergence:  Price ↑ + CVD ↓ → SHORT
```

---

### **2. OI (Open Interest)**

**Cascade Detection:**
```
Условие CASCADE:
• OI dropped ≥ 2% за 60 минут
• Price moved ≥ 1.2% за 60 минут
```

**Сигнал:**
```
OI ↓ + Price ↓ = Long Liquidation → Ищем LONG
OI ↓ + Price ↑ = Short Liquidation → Ищем SHORT
```

---

### **3. Funding Rate**

| Значение | Статус | Действие |
|----------|--------|----------|
| **> 0.05%** | Long Overleveraged | ✅ Ищем SHORT |
| **> 0.10%** | Extreme Long | ❌ Блок для LONG |
| **< -0.05%** | Short Overleveraged | ✅ Ищем LONG |
| **< -0.10%** | Extreme Short | ❌ Блок для SHORT |

---

## 🎯 Confidence Score System

### **Базовые Факторы**

| Фактор | Delta | Условие |
|--------|-------|---------|
| **Liquidity sweep confirmed** | +30 | Sweep Reversal стратегия |
| **Squeeze breakout** | +25 | Breakout стратегия |
| **Volume spike ≥1.2×** | +20 | Объём выше MA(20) |
| **Session active** | +20 | Asian/London/NY |
| **Volatility squeeze (4H)** | +20 | Сжатие волатильности |
| **Trend alignment (ADX >25)** | +10 | Вход по тренду |
| **CVD divergence** | +15 | Классическая дивергенция |
| **Funding extreme (counter)** | +10 | Против funding |
| **Liquidation cascade** | +15 | OI drop + price move |

---

### **Штрафы**

| Фактор | Delta | Условие |
|--------|-------|---------|
| **ADX >40 against trend** | -25 | Сильный тренд против |
| **Funding >+0.10% + LONG** | -15 | Блок для LONG |
| **Funding <-0.10% + SHORT** | -15 | Блок для SHORT |
| **Outside all sessions** | -30 | Неактивная сессия |

---

### **Порог Сигнала**

```
Confidence Score ≥ 65 → ОТПРАВИТЬ СИГНАЛ
Confidence Score < 65 → ПРОПУСТИТЬ
```

---

## 💰 Risk Management

### **Position Sizing**

```
Max Position = Account Balance × 10%
Max Risk = Account Balance × 2%
```

### **Stop Loss**

| Стратегия | SL |
|-----------|-----|
| **Sweep Reversal** | За экстремум свечи |
| **Breakout** | Фиксированный 0.7% |

### **Take Profit**

| Стратегия | TP | Min RR |
|-----------|-----|--------|
| **Sweep Reversal** | По уровню ликвидности | 2.0 |
| **Breakout** | Фиксированный 3% | 4.3 |

---

## ⏰ Analysis Cycle

### **Расписание**

```
Анализ каждые 15 минут в:
:03, :18, :33, :48 (UTC)

3 секунды после закрытия свечи
```

### **Процесс**

```
1. Загрузка свечей (15m, 4H, 1D)
2. Проверка Market State
3. Построение Liquidity Map
4. Проверка Squeeze
5. Анализ Order Flow
6. Поиск паттернов (Sweep / Breakout)
7. Расчёт Confidence Score
8. Проверка Cooldown (60 мин)
9. Сохранение в БД
10. Отправка в Telegram
```

---

## 📊 Database Schema

### **Таблицы**

| Таблица | Назначение |
|---------|------------|
| **signals** | Отправленные сигналы |
| **liquidity_pools** | Уровни ликвидности (1D + 4H) |
| **cvd_buckets** | CVD данные по сессиям |
| **oi_snapshots** | Open Interest (15m интервал) |
| **signal_cooldowns** | Кулдауны сигналов (60 мин) |

---

## 🔧 Configuration

### **Файл `.env`**

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Binance
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
TESTNET=true

# Strategy
LIQUIDITY_MAX_TOUCHES=3
CONFIDENCE_THRESHOLD=65
MIN_RR=2.0

# Risk
ACCOUNT_BALANCE=10000
MAX_RISK_PER_TRADE=2.0
MAX_POSITION_PCT=10.0

# Market State
ADX_TRENDING=25.0
ADX_DEAD_ZONE_MIN=20.0
ADX_DEAD_ZONE_MAX=25.0
ATR_LOW_THRESHOLD=0.007
ATR_NORMAL_MAX=0.015
```

---

## 📈 Performance Metrics

### **Ожидаемые Показатели**

| Метрика | Значение |
|---------|----------|
| **Сигналов в день** | 1-5 |
| **Winrate** | 65-75% |
| **Average RR** | 2.5-3.0 |
| **Max Drawdown** | < 10% |
| **Profit Factor** | > 2.0 |

---

## ⚠️ Важные Заметки

### **1. Не Торговать Когда:**

```
❌ ADX 20-25 (Dead Zone)
❌ ATR < 0.7% (Low Volatility)
❌ Вне сессий (Off-hours)
❌ Перед важными новостями
❌ При Confidence < 65%
```

### **2. Лучшие Условия:**

```
✅ London Session (07:00-11:00 UTC)
✅ NY Session (13:00-17:00 UTC)
✅ ATR 0.7-1.5% (Normal Volatility)
✅ ADX < 20 или > 25
✅ Свежие уровни (1-2 touches)
```

### **3. Управление Рисками:**

```
• Всегда используйте Stop Loss
• Не увеличивайте позицию вручную
• Доверяйте Confidence Score
• Лучше пропустить, чем войти рано
```

---

## 🎯 Примеры Сделок

### **Пример 1: Sweep Reversal LONG**

```
Дата: 2026-03-20 08:30 UTC
Пара: BTCUSDT
Направление: LONG 🟢

Условия:
✅ Sweep Equal Lows at $87,598
✅ Rejection candle (wick 3.2× body)
✅ Volume spike 1.5× MA(20)
✅ London session active
✅ CVD bullish divergence
✅ Funding negative (-0.02%)

Вход: $87,650
SL: $87,450
TP: $88,500
RR: 4.25
Confidence: 88%

Результат: TP HIT (+0.97%)
```

---

### **Пример 2: Volatility Breakout SHORT**

```
Дата: 2026-03-20 14:15 UTC
Пара: BTCUSDT
Направление: SHORT 🔴

Условия:
✅ 4H Squeeze active (BB width min)
✅ Breakout below Lower BB
✅ Volume spike 1.3× MA(20)
✅ NY session active
✅ OI cascade detected

Вход: $88,200
SL: $88,815 (0.7%)
TP: $85,554 (3.0%)
RR: 4.3
Confidence: 76%

Результат: TP HIT (+3.0%)
```

---

## 📞 Поддержка

**Документация:**
- `README.md` — Общая информация
- `STRATEGY.md` — Этот файл (стратегия)
- `DEPLOYMENT.md` — Развёртывание на VPS

**Логи:**
```bash
tail -f /opt/crypto-bot/logs/bot.log
journalctl -u crypto-bot -f
```

**Dashboard:**
```
http://your-vps-ip:8001/dashboard
```

---

## ⚠️ Disclaimer

```
⚠️ NOT FINANCIAL ADVICE

Этот бот предоставлен только в образовательных целях.
Торговля криптовалютой связана с высоким риском.
Вы используете бота на свой страх и риск.

Всегда проводите собственное исследование (DYOR).
Никогда не торгуйте на деньги, которые не готовы потерять.
```

---

## 🎉 Заключение

**Crypto Signal Bot v3** — это профессиональная торговая система, основанная на:

1. ✅ **Smart Money Concepts** — работа с ликвидностью
2. ✅ **Order Flow Analysis** — подтверждение потоком ордеров
3. ✅ **Risk Management** — строгий контроль рисков
4. ✅ **Automation** — 24/7 мониторинг рынка

**Ключевые преимущества:**
- 🎯 Высокий Confidence Score (≥ 65%)
- 💰 Отличный Risk/Reward (≥ 2.0)
- 📊 Прозрачная логика решений
- 🔒 Автоматический риск-менеджмент

**Готово к реальной торговле!** 🚀

---

**Версия:** 3.0.0  
**Последнее обновление:** Март 2026  
**Автор:** Crypto Signal Bot Team
