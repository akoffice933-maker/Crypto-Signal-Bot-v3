# Execution RR Model

## Назначение

Этот файл фиксирует текущую логику расчета:

- `Stop Loss`
- `Take Profit`
- `RR`
- различий между `entry_market` и `entry_limit`
- выбора основной базы исполнения через `execution_basis`

Актуально для текущей версии стратегии после внедрения dual `RR`:

- `rr_market`
- `rr_limit`
- `rr_ratio` по выбранной базе исполнения


## 1. Основная идея

В системе теперь существуют две отдельные метрики `RR`:

- `rr_market` — RR, рассчитанный от `entry_market`
- `rr_limit` — RR, рассчитанный от `entry_limit`

Основной `RR`, который используется в сигнале и в фильтрации стратегии:

- `rr_ratio = rr_limit`, если `settings.execution_basis == "limit"`
- `rr_ratio = rr_market`, если `settings.execution_basis == "market"`

Текущее значение по умолчанию в коде:

- `execution_basis = "limit"`

Источник:

- [settings.py](/d:/bot_final/config/settings.py)


## 2. Sweep Reversal: как считается SL

Файл:

- [sweep_reversal.py](/d:/bot_final/strategies/sweep_reversal.py)

### LONG

Для `LONG` стоп ставится структурно:

- за минимум `sweep`-свечи
- с небольшим буфером

Текущая логика:

```python
stop_loss = float(sweep_c["low"]) - float(rej_c["close"] - rej_c["open"]) * 0.5
stop_loss = min(stop_loss, float(sweep_c["low"]) * 0.999)
```

### SHORT

Для `SHORT` стоп ставится выше максимума `sweep`-свечи:

```python
stop_loss = float(sweep_c["high"]) * 1.001
```

То есть для `Sweep Reversal` стоп остается структурным, а не фиксированным процентным.


## 3. Sweep Reversal: как считается TP

### Основной сценарий

Стратегия пытается найти ближайший валидный уровень ликвидности по направлению сделки:

```python
target = select_target_level(all_levels, current_price, direction)
```

Если target найден:

- `take_profit = target.price`

### Fallback

Если target не найден, TP строится по минимальному RR режима:

```python
risk = abs(rr_entry - stop_loss)
take_profit = rr_entry + risk * rr_min      # LONG
take_profit = rr_entry - risk * rr_min      # SHORT
```

Где:

- `rr_entry = entry_limit`, если база исполнения `limit`
- `rr_entry = entry_market`, если база исполнения `market`

### TP cap

После этого TP ограничивается максимумом `10%` от выбранной базы входа:

```python
max_take_profit = rr_entry * (1 + 0.10)   # LONG
max_take_profit = rr_entry * (1 - 0.10)   # SHORT
```


## 4. Формулы RR

### LONG

```text
risk   = entry - stop_loss
reward = take_profit - entry
RR     = reward / risk
```

### SHORT

```text
risk   = stop_loss - entry
reward = entry - take_profit
RR     = reward / risk
```

В коде это вынесено в helper:

```python
_calculate_rr(direction, entry, stop_loss, take_profit)
```


## 5. Почему теперь RR может отличаться для market и limit

Если `entry_limit` отличается от `entry_market`, то:

- меняется расстояние до `SL`
- меняется расстояние до `TP`
- значит меняется и итоговый `RR`

Это особенно важно для `Sweep Reversal`, где:

- `entry_market` — закрытие rejection candle
- `entry_limit` — лимитный вход по телу sweep candle

Раньше стратегия фильтровала сигнал по `RR`, рассчитанному только от `entry_market`.
Теперь это исправлено: используется честный `RR` по выбранной базе исполнения.


## 6. Пример на последнем SHORT сигнале

Сигнал:

- `Entry (Market): 71692.90`
- `Entry (Limit): 71645.30`
- `Stop Loss: 72003.83`
- `Take Profit: 70357.42`

### RR от market

```text
risk   = 72003.83 - 71692.90 = 310.93
reward = 71692.90 - 70357.42 = 1335.48
RR     = 1335.48 / 310.93 ≈ 4.29
```

### RR от limit

```text
risk   = 72003.83 - 71645.30 = 358.53
reward = 71645.30 - 70357.42 = 1287.88
RR     = 1287.88 / 358.53 ≈ 3.59
```

### Практический вывод

Для этого сигнала:

- `rr_market` выше
- `rr_limit` ниже

Если `execution_basis = "limit"`, то:

- основной рабочий RR должен быть `~3.59`
- именно он должен использоваться в фильтрации и в Telegram


## 7. Что сохраняется в сигнале

После обновления сигнал содержит:

- `entry_market`
- `entry_limit`
- `rr_market`
- `rr_limit`
- `rr_ratio`
- `execution_basis`

Для `Sweep Reversal`:

- `rr_market` и `rr_limit` заполнены оба

Для `Breakout`:

- `execution_basis = "market"`
- `rr_market` заполнен
- `rr_limit = null`


## 8. Что показывается в Telegram

Теперь уведомление показывает:

```text
RR: 3.6 (limit)
```

или

```text
RR: 2.1 (market)
```

Это убирает путаницу, по какой именно модели исполнения рассчитан сигнал.


## 9. Текущий статус логики

### Sweep Reversal

- `SL` — структурный
- `TP` — liquidity target, затем fallback, затем cap
- `RR` — по выбранной базе исполнения

### Breakout

- `SL` — adaptive ATR-based
- `TP` — фиксированный диапазон
- `execution_basis` пока остается `market`


## 10. Следующий логичный шаг

После выравнивания `Entry -> RR -> TP` можно безопасно внедрять:

- `TP1 / TP2`
- partial take profit
- trailing stop
- более точный risk sizing

Без этой унификации дальнейшее управление позицией было бы менее прозрачным.
