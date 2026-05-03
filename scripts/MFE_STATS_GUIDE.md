# 🎯 MFE/MAE Statistics Collection

**Цель:** Собрать статистику по реальному движению цены (MFE/MAE) для оптимизации TP1 и SL.

---

## 📋 Что делает скрипт

`scripts/collect_mfe_stats.py` анализирует исторические сигналы и вычисляет:

1. **Avg MFE** — среднее максимальное движение в профит
2. **Avg MAE** — среднее максимальное движение против позиции
3. **Median MFE** — медианное MFE (более стабильная метрика)
4. **P75 MFE** — 75-й перцентиль (реалистичная цель для TP2)
5. **Рекомендации** для config/settings.py

---

## 🚀 Использование

### 1. Запустить сбор статистики

```bash
# На VPS
cd /opt/crypto-bot

# Проанализировать последние 100 сигналов
/opt/crypto-bot/venv/bin/python scripts/collect_mfe_stats.py --limit 100

# Проанализировать только BTCUSDT
/opt/crypto-bot/venv/bin/python scripts/collect_mfe_stats.py --pair BTCUSDT --limit 50

# Сохранить результаты в JSON
/opt/crypto-bot/venv/bin/python scripts/collect_mfe_stats.py --limit 100 --output results/mfe_stats.json
```

### 2. Интерпретировать результаты

**Пример вывода:**

```
======================================================================
MFE/MAE STATISTICS & RECOMMENDATIONS
======================================================================

Total signals analyzed: 45
Pairs analyzed: 4

┌─────────────────────────────────────────────────────────────────┐
│ PER-PAIR STATISTICS                                           │
├─────────────────────────────────────────────────────────────────┤

│ BTCUSDT  (15 signals)
│   Avg MFE:      0.92%
│   Avg MAE:      0.48%
│   MFE/MAE:      1.92
│   Median MFE:   0.85%
│   P75 MFE:      1.05%
│   P90 MFE:      1.25%
│
│   → Recommended TP1:  0.68%
│   → Recommended TP2:  1.16%
│   → Recommended SL:   0.58%

│ ETHUSDT  (12 signals)
│   Avg MFE:      1.15%
│   Avg MAE:      0.52%
│   MFE/MAE:      2.21
│   Median MFE:   1.02%
│   P75 MFE:      1.28%
│   P90 MFE:      1.45%
│
│   → Recommended TP1:  0.82%
│   → Recommended TP2:  1.41%
│   → Recommended SL:   0.62%

┌─────────────────────────────────────────────────────────────────┐
│ OVERALL RECOMMENDATIONS (config/settings.py)                  │
├─────────────────────────────────────────────────────────────────┤
│
│ # TP1: Fixed distance based on MFE (not SL-dependent)
│ quiet_tp1_pct = 0.0068  # 0.68%
│ normal_tp1_pct = 0.0088  # 0.88%
│
│ # TP2: Realistic target
│ quiet_tp_max_pct = 0.0116  # 1.16%
│ normal_tp_max_pct = 0.0151  # 1.51%
│
│ # SL: Wide enough to avoid noise
│ quiet_sl_atr_mult = 0.8  # 0.8×ATR
│ normal_sl_atr_mult = 0.6  # 0.6×ATR
│
│ # Timeout: More time for TP
│ quiet_timeout_candles = 40  # 10 hours
│ normal_timeout_candles = 30  # 7.5 hours
│
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Как читать результаты

### Ключевые метрики

| Метрика | Что означает | Как использовать |
|---------|--------------|------------------|
| **Median MFE** | Типичное движение в профит | База для TP1 |
| **P75 MFE** | Реалистичная цель для 75% сделок | База для TP2 |
| **P90 MFE** | Оптимистичная цель | Максимальный TP |
| **Avg MAE** | Типичный шум против позиции | Минимальный SL |
| **MFE/MAE** | Качество входа | > 1.5 = хорошо |

### Формулы рекомендаций

```python
# TP1: 80% от медианного MFE (чтобы попадать в 80% случаев)
tp1_pct = median_mfe * 0.8

# TP2: 110% от P75 MFE (реалистичная цель)
tp2_pct = p75_mfe * 1.1

# SL: 120% от максимального MAE (защита от шума)
sl_pct = max_mae * 1.2
```

---

## 🎯 План сбора статистики

### Этап 1: Сейчас (15 сигналов)

```bash
# Запустить анализ
/opt/crypto-bot/venv/bin/python scripts/collect_mfe_stats.py --limit 15 --output results/mfe_stats_15.json
```

**Ожидаемо:**
- 15 сигналов (3 ETH + 12 BTC)
- Предварительные рекомендации
- Низкая достоверность

---

### Этап 2: Через 1 неделю (30-40 сигналов)

```bash
/opt/crypto-bot/venv/bin/python scripts/collect_mfe_stats.py --limit 40 --output results/mfe_stats_40.json
```

**Ожидаемо:**
- 30-40 сигналов
- Статистика по всем 4 парам
- Средняя достоверность

---

### Этап 3: Через 2 недели (50-70 сигналов)

```bash
/opt/crypto-bot/venv/bin/python scripts/collect_mfe_stats.py --limit 70 --output results/mfe_stats_70.json
```

**Ожидаемо:**
- 50-70 сигналов
- Стабильные метрики по парам
- Высокая достоверность
- **Готово к применению настроек!**

---

## 🔧 Применение настроек

**После сбора 50+ сигналов:**

1. **Запустить анализ:**
   ```bash
   /opt/crypto-bot/venv/bin/python scripts/collect_mfe_stats.py --limit 70
   ```

2. **Скопировать рекомендации** из вывода

3. **Обновить config/settings.py:**
   ```python
   # ── Risk Management (на основе MFE статистики) ──────────────
   quiet_tp1_pct = 0.0068        # Из рекомендаций
   normal_tp1_pct = 0.0088
   quiet_tp_max_pct = 0.0116
   normal_tp_max_pct = 0.0151
   quiet_sl_atr_mult = 0.8
   normal_sl_atr_mult = 0.6
   quiet_timeout_candles = 40
   normal_timeout_candles = 30
   ```

4. **Перезапустить бота:**
   ```bash
   systemctl restart crypto-bot
   ```

5. **Запустить replay для проверки:**
   ```bash
   /opt/crypto-bot/venv/bin/python scripts/replay_sweep.py --limit 100
   ```

---

## 📈 Ожидаемые улучшения

| Метрика | До оптимизации | После оптимизации |
|---------|----------------|-------------------|
| **TP1 hit rate** | 33% | 50-60% ✅ |
| **Full TP rate** | 0% | 10-15% ✅ |
| **Timeout rate** | 67% | 25-35% ✅ |
| **SL hit rate** | 25% | 20-25% ✅ |
| **Expectancy** | 0.23% | 0.6-0.8% ✅ |
| **Profit Factor** | 1.98 | 2.2-2.5 ✅ |

---

## ✅ Чек-лист

- [ ] Скрипт создан: `scripts/collect_mfe_stats.py`
- [ ] Запустить через 1 неделю (30+ сигналов)
- [ ] Запустить через 2 недели (50+ сигналов)
- [ ] Применить рекомендации к config/settings.py
- [ ] Перезапустить бота
- [ ] Проверить через replay_sweep.py

---

**Готово!** 🎉

Теперь у тебя есть инструмент для точной настройки TP1/TP2/SL на основе реальных данных!
