# Signal Replay & Parameter Sweep

Инструменты для валидации сигналов и подбора оптимальных параметров exit-модели.

---

## 📁 Файлы

| Файл | Описание |
|------|----------|
| `scripts/signal_replay.py` | Replay отдельных сигналов на исторических данных |
| `scripts/replay_sweep.py` | Batch parameter sweep (10-20 конфигураций за прогон) |
| `tests/test_signal_replay.py` | Тесты для signal_replay |
| `tests/test_replay_sweep.py` | Тесты для success criteria |

---

## 🚀 signal_replay.py

Запускает replay сигналов из `signals.db` с настраиваемыми параметрами exits.

### Базовое использование

```bash
# Replay последних 50 сигналов
python scripts/signal_replay.py --limit 50

# Replay одного сигнала по ID
python scripts/signal_replay.py --signal-id 85325a8415d6fc4a

# Replay для конкретной пары
python scripts/signal_replay.py --pair BTCUSDT

# С кастомными параметрами
python scripts/signal_replay.py --limit 100 --tp-model capped --tp-max-pct 1.0 --sl-mult 0.8
```

### Параметры

| Параметр | Описание | Default |
|----------|----------|---------|
| `--db` | Путь к signals.db | `data/signals.db` |
| `--limit` | Лимит сигналов | all |
| `--signal-id` | Replay один сигнал | — |
| `--pair` | Фильтр по паре | all |
| `--out` | Путь к CSV | `results/signal_replay_<ts>.csv` |
| `--tp-model` | Модель TP: `liquidity`, `capped`, `reduced_multiple` | `liquidity` |
| `--tp-max-pct` | Макс. TP % для capped модели | — |
| `--sl-mult` | Множитель SL (ATR) | 0.5 |
| `--tp1-mult` | Множитель TP1 (R) | 2.0 |
| `--max-candles-hold` | Timeout в свечах | 20 |

### Выходные данные

**CSV:** `results/signal_replay_<timestamp>.csv`

| Поле | Описание |
|------|----------|
| `signal_id`, `pair`, `direction` | Информация о сигнале |
| `entry_market`, `entry_limit`, `fill_price` | Цены входа |
| `stop_loss`, `take_profit`, `tp1_price` | Уровни exits |
| `tp1_hit`, `tp1_hit_time`, `tp1_hit_price` | Достижение TP1 |
| `exit_type_detail` | Тип выхода: `sl`, `tp2`, `timeout`, `partial_tp1_*` |
| `pnl_pct`, `rr_achieved` | Результат сделки |
| `mfe_pct`, `mae_pct`, `mfe_mae_ratio` | Excursion метрики |
| `timeout_pnl_pct` | PnL при timeout |

**DB:** Таблица `signal_replay_results` в том же SQLite.

---

## 🔬 replay_sweep.py

Batch parameter sweep для сравнения 10-20 конфигураций exit-модели.

### Базовое использование

```bash
# Запустить все конфигурации (14 конфигов)
python scripts/replay_sweep.py --limit 100

# Запустить только эксперимент A (timeout sweep)
python scripts/replay_sweep.py --experiment A --limit 100

# Запустить для конкретной пары
python scripts/replay_sweep.py --pair BTCUSDT
```

### Конфигурации (CONFIG_GRID)

| Группа | Конфиги | Параметры |
|--------|---------|-----------|
| **A** | A1-A4 | Timeout: 20, 30, 40, 60 свечей |
| **B** | B1-B4 | TP cap: 0.8%, 1.0%, 1.2%, 1.5% (capped model) |
| **C** | C1-C3 | SL mult: 0.7, 0.8, 1.0 |
| **D** | D1-D3 | Комбинированные: timeout+TP+SL |

### Success Criteria

| Приоритет | Критерий | Порог |
|-----------|----------|-------|
| **P0** | Expectancy | > 0.5% |
| **P0** | Profit Factor | > 1.5 |
| **P1** | SL rate | < 40% |
| **P2** | MFE/MAE ratio | > 1.5 |

**Verdict:**
- ✅ **PASS** — все критерии выполнены
- ⚠️ **PARTIAL** — 1 проблема (только P0 Expectancy или PF)
- ❌ **FAIL** — 2+ проблемы

### Выходные данные

| Файл | Описание |
|------|----------|
| `results/replay_comparison_<ts>.csv` | Сводная таблица всех конфигураций |
| `results/replay_summary_<ts>.json` | Полные метрики в JSON |

### Формат comparison CSV

```
Config   Exp  Timeout TP Model     TP Max   SL    Exp%     PF   SL%   TO%   TP1%  MFE/MAE  Verdict
------------------------------------------------------------------------------------------------
A1       A         20 liquidity       —    0.50    0.08   1.03  56.0  44.0   0.0     1.20       ❌
B2       B         20 capped         1.0    0.50    0.45   1.35  45.0  30.0  25.0     1.60       ⚠️
D1       D         40 capped         1.0    0.80    0.72   1.82  32.0  28.0  33.0     2.10       ✅
```

---

## 📊 Метрики

### Excursion (MFE/MAE)

| Метрика | Формула | Интерпретация |
|---------|---------|---------------|
| **MFE** | `(max_price - entry) / entry * 100` (LONG) | Макс. движение в профит |
| **MAE** | `(entry - min_price) / entry * 100` (LONG) | Макс. движение против |
| **MFE/MAE** | `avg(MFE) / avg(MAE)` | Качество тайминга входа |

### Exit Quality

| Метрика | Формула | Цель |
|---------|---------|------|
| **Expectancy** | `avg(pnl_pct)` | > 0.5% |
| **Profit Factor** | `sum(profit) / abs(sum(loss))` | > 1.5 |
| **SL rate** | `sl_hits / validated` | < 40% |
| **Timeout rate** | `timeout_hits / validated` | < 40% |
| **Full TP rate** | `tp_hits / validated` | > 20% |
| **TP1 hit rate** | `tp1_hits / validated` | > 50% |
| **Timeout PnL median** | `median(pnl on timeout)` | > 0 |

---

## 🔧 Добавление новых конфигураций

Откройте `scripts/replay_sweep.py` и добавьте в `CONFIG_GRID`:

```python
{
    "experiment": "E",
    "config_label": "E1",
    "timeout_candles": 50,
    "tp_model": "reduced_multiple",
    "tp_max_pct": None,
    "sl_mult": 0.9,
    "tp1_mult": 2.5,
    "reduced_rr_mult": 3.5,
},
```

Затем запустите:
```bash
python scripts/replay_sweep.py --experiment E
```

---

## 🧪 Тесты

```bash
# Тесты signal_replay
python tests/test_signal_replay.py

# Тесты success criteria
python tests/test_replay_sweep.py
```

---

## 📝 Примеры использования

### 1. Базовый replay

```bash
python scripts/signal_replay.py --limit 50
```

### 2. Тест capped модели

```bash
python scripts/signal_replay.py --limit 100 --tp-model capped --tp-max-pct 1.0
```

### 3. Полный sweep

```bash
python scripts/replay_sweep.py --limit 200
```

### 4. Сравнение timeout

```bash
python scripts/replay_sweep.py --experiment A --limit 100
```

### 5. Поиск лучшей конфигурации

После запуска sweep откройте `results/replay_comparison_<ts>.csv` и отфильтруйте по:
- `verdict = ✅`
- Максимальному `expectancy`

---

## 🎯 Интерпретация результатов

### Хорошая конфигурация

- ✅ Expectancy > 0.5%
- ✅ Profit Factor > 1.5
- ✅ SL rate < 40%
- ✅ MFE/MAE > 1.5
- ✅ Timeout PnL median > 0

### Проблемы и решения

| Проблема | Причина | Решение |
|----------|---------|---------|
| Высокий SL rate (>50%) | SL слишком узкий | Увеличить `sl_mult` до 0.7-1.0 |
| Высокий timeout rate (>50%) | TP слишком далёкий | Использовать `capped` модель |
| Низкий MFE/MAE (<1.2) | Плохой тайминг входа | Пересмотреть entry логику |
| Отрицательный timeout PnL | Timeout слишком долгий | Уменьшить `timeout_candles` |

---

## 📚 Связанная документация

- [`EXECUTION_RR_MODEL.md`](../EXECUTION_RR_MODEL.md) — Модель управления сделками
- [`STRATEGY.md`](../STRATEGY.md) — Описание торговой стратегии
- [`TZ_OPTIMAL_STRATEGY_V5.md`](../TZ_OPTIMAL_STRATEGY_V5.md) — ТЗ на оптимальную стратегию
