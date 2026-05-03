# SWEEP_5M_AND_TRADE_MANAGER.md
## Интеграция sweep_trigger_5m + trade_manager в pipeline

### Что добавлено

| Файл | Назначение |
|---|---|
| `engine/sweep_trigger_5m.py` | WebSocket подписка на 5M свечи, event-driven детект sweep |
| `engine/trade_manager.py` | Расчёт SL/TP, трекинг позиций, Telegram-алерты |
| `tests/test_sweep_trigger_and_trade_manager.py` | 30 unit-тестов |

---

### 1. Интеграция sweep_trigger_5m в main.py

```python
# main.py — в функции init()
from engine.sweep_trigger_5m import SweepTrigger5m

sweep_trigger: SweepTrigger5m = None

async def init():
    global db, client, ws, notifier, sweep_trigger
    # ... существующий код ...

    # Создать триггер для всех пар из настроек
    sweep_trigger = SweepTrigger5m(symbols=settings.symbols)
    await sweep_trigger.start()  # неблокирующий запуск в фоне
    logger.info("SweepTrigger5m started")
```

```python
# main.py — в функции shutdown()
if sweep_trigger:
    await _await_shutdown_step("SweepTrigger5m", sweep_trigger.stop())
```

---

### 2. Интеграция sweep_trigger_5m в pipeline.py

В `run_pipeline()` после построения liquidity map передать уровни в триггер:

```python
# engine/pipeline.py — после liquidity_map.build()
from engine.sweep_trigger_5m import SweepTrigger5m

async def run_pipeline(client, db, ws, notifier, sweep_trigger=None):
    # ... существующий код строит liquidity_map ...

    # Обновить уровни для real-time детектирования на 5M
    if sweep_trigger:
        level_prices = [lv.price for lv in liquidity_map.levels]
        sweep_trigger.update_levels(symbol, level_prices)

    # Получить уже обнаруженные sweep-события от 5M стрима
    if sweep_trigger:
        pending_sweeps = await sweep_trigger.drain()
        for sweep_event in pending_sweeps:
            # Добавить confidence_bonus к сигналу если направление совпадает
            logger.info(
                f"5M sweep event: {sweep_event.symbol} "
                f"{sweep_event.direction} +{sweep_event.confidence_bonus} pts"
            )
            # Передать в confidence scoring как дополнительный контекст
```

**Важно:** sweep_trigger передаётся как параметр в `run_pipeline()` — не как глобальная переменная. Это сохраняет существующий принцип явной передачи зависимостей.

---

### 3. Интеграция trade_manager в main.py

```python
# main.py
from engine.trade_manager import TradeManager

trade_manager: TradeManager = None

async def init():
    global trade_manager
    # ... после создания notifier ...
    trade_manager = TradeManager(notifier=notifier, expiry_hours=4)
    logger.info("TradeManager initialized")
```

---

### 4. Использование trade_manager в analysis_cycle

```python
# main.py — analysis_cycle()
async def analysis_cycle():
    sig = await run_pipeline(
        client=client,
        db=db,
        ws=ws,
        notifier=notifier if not _dry_run else None,
        sweep_trigger=sweep_trigger,
    )

    if sig:
        # Открыть трекинг сделки
        atr = sig.get("atr", 0)  # pipeline должен возвращать ATR в сигнале
        if atr > 0 and trade_manager:
            managed = trade_manager.open_trade(sig, current_atr=atr)
            if notifier and not _dry_run:
                await notifier.send_text(managed.to_telegram_open())

    # Тикнуть менеджер по текущей цене (используем последнюю закрытую 15M свечу)
    # Это даёт проверку SL/TP каждые 15 минут
    # Для более частой проверки — вызывать tick() из 5M WebSocket callback
    if trade_manager and sig:
        symbol = sig.get("symbol", settings.symbols[0])
        # Получить текущую цену из клиента или из последней свечи
        # price_data = await client.get_ticker(symbol)
        # await trade_manager.tick(symbol, price_data.high, price_data.low, price_data.close)
```

---

### 5. Добавить ATR в возвращаемый сигнал pipeline.py

Для корректного расчёта SL/TP нужен ATR в словаре сигнала. Минимальное изменение:

```python
# engine/pipeline.py — при формировании signal dict
signal = {
    "symbol": symbol,
    "direction": direction,
    "strategy": strategy,
    "entry_market": entry_price,
    "swept_level": swept_level,  # для sweep_reversal
    "confidence_score": confidence,
    "atr": current_atr,          # ← добавить это поле
    # ... остальные поля ...
}
```

---

### 6. Telegram команда /trades

Добавить в `telegram/bot.py`:

```python
@router.message(Command("trades"))
async def cmd_trades(message: Message):
    """Показать активные трекируемые сделки."""
    active = trade_manager.get_active_trades()
    if not active:
        await message.answer("Нет активных сделок.")
        return

    lines = [f"📊 Активных сделок: {len(active)}\n"]
    for t in active:
        lvl = t.levels
        lines.append(
            f"{'🟢' if t.direction.value == 'LONG' else '🔴'} "
            f"*{t.symbol}* {t.strategy}\n"
            f"  Entry `{lvl.entry}` SL `{lvl.sl}` TP1 `{lvl.tp1}` TP2 `{lvl.tp2}`\n"
            f"  TP1 {'✅' if t.tp1_triggered else '⏳'} | "
            f"Expires: {t.expires_at.strftime('%H:%M UTC')}\n"
        )
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("tradestats"))
async def cmd_trade_stats(message: Message):
    """Статистика по закрытым сделкам."""
    stats = trade_manager.get_stats()
    if stats["total"] == 0:
        await message.answer("Нет закрытых сделок.")
        return

    text = (
        f"📈 *Статистика сделок*\n\n"
        f"Всего: `{stats['total']}`\n"
        f"Полных побед (TP2): `{stats['wins_full']}`\n"
        f"Частичных (TP1): `{stats['wins_partial']}`\n"
        f"Убытков (SL): `{stats['losses']}`\n"
        f"Истекло: `{stats['expired']}`\n"
        f"Win rate: `{stats['win_rate_pct']}%`\n"
        f"Средний RR: `{stats['avg_rr']}`"
    )
    await message.answer(text, parse_mode="Markdown")
```

---

### 7. Запуск тестов

```bash
# Только новые тесты
pytest tests/test_sweep_trigger_and_trade_manager.py -v

# Все тесты вместе
pytest tests/ -v

# С coverage
pytest tests/ --cov=engine --cov-report=term-missing
```

---

### Что НЕ изменяется

- Сигнальная природа бота сохранена: реальные ордера не выставляются
- Структура `run_pipeline()` — только добавляется параметр `sweep_trigger=None`
- База данных — trade_manager хранит состояние **в памяти** (не в SQLite)
- Все существующие тесты продолжают работать без изменений

### Что добавляется пользователю

| Было | Стало |
|---|---|
| Сигнал раз в 15 минут | Sweep детектируется в течение ≤5 минут |
| Один Telegram-алерт на вход | Алерты: открытие → TP1 → TP2/SL/истечение |
| Нет статистики исходов | `/tradestats` показывает win rate, avg RR |
| SL/TP только в тексте сигнала | Трекинг: автоматическое уведомление при достижении |
