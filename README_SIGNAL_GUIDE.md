# README Signal Guide

## Назначение

Этот файл нужен для быстрого понимания:

- когда бот считает рынок пригодным для торговли;
- в какие часы по Москве реально ждать сигналы;
- как читать логи;
- какие команды использовать для быстрого мониторинга.

## Когда рынок становится `tradeable=True`

Бот считает рынок пригодным для торговли только если одновременно выполняются все 3 условия:

1. Есть активная торговая сессия
2. Волатильность не низкая
3. Рынок не находится в `dead_zone`

Итоговая логика:

```python
tradeable = market_state != "dead_zone" and vol != "low" and session is not None
```

## Условия подробно

### 1. Активная торговая сессия

Нужно, чтобы `session` была не `None`.

Сессии в UTC:

- `asian`: `00:00–08:00 UTC`
- `london`: `07:00–11:00 UTC`
- `ny`: `13:00–17:00 UTC`

### 2. Волатильность не низкая

ATR% не должен попадать в `low`.

- `low`: `< 0.7%`
- `normal`: `0.7%–1.5%`
- `high`: `> 1.5%`

Для торговли нужно:

- `ATR% >= 0.7%`

### 3. Рынок не в `dead_zone`

Состояние рынка определяется по ADX:

- `dead_zone`: `20–25` -> торговля запрещена
- `trending`: `> 25`
- `ranging`: `< 20`

Для торговли нужно:

- `ADX` не в диапазоне `20–25`

## Что это значит на практике

Рынок станет `tradeable=True`, если:

- сейчас идет одна из торговых сессий;
- `ATR% >= 0.7%`;
- `ADX` не в диапазоне `20–25`.

Если в логах видно:

- `ranging` -> это нормально;
- `vol=low` -> уже блокирует торговлю;
- `session=None` -> тоже блокирует торговлю.

Значит бот не ошибся: сейчас рынок действительно не проходит фильтры.

## Когда ждать сигналы по Москве

Бот работает по UTC, но для Москвы (`UTC+3`) полезно ориентироваться на такие интервалы:

- `03:00–11:00 МСК` — Asian session
- `10:00–14:00 МСК` — London session
- `16:00–20:00 МСК` — New York session

### Самые полезные окна

- `10:00–14:00 МСК`
- `16:00–20:00 МСК`
- `10:00–11:00 МСК` — переход Asian/London

### Когда почти нет смысла ждать

- `11:00–16:00 МСК` — между London и NY, часто `session=None`
- `20:00–03:00 МСК` — вне заданных сессий
- `03:00–08:00 МСК` — формально сессия есть, но волатильность часто слабая

### Короткий вывод

- главный фокус: `10:00–14:00` и `16:00–20:00 МСК`
- лучший шанс на сигналы: `16:00–20:00 МСК`
- вне этих окон бот часто будет писать `Not tradeable`

## Как быстро читать логи

Смотри в первую очередь на строки:

- `MarketContext(...)`
- `Not tradeable: ...`
- `Liquidity map: ...`
- `Sweep signal: ...`
- `Breakout signal: ...`
- `Signal: ...`

## Как отличать состояния по логам

### 1. Сигнала не будет

Если видишь:

- `session=None`
- `vol=low`
- `market_state=dead_zone`
- после этого есть строка `Not tradeable: ...`

Примеры:

```text
Not tradeable: ranging, vol=low, session=None
Not tradeable: dead_zone, vol=normal, session=london
```

Это значит:

- pipeline отфильтровал рынок еще до стратегий;
- в этом цикле сигнала не будет.

### 2. Рынок почти готов

Если видишь:

- `session=london` или `session=ny`
- `vol=normal` или `vol=high`
- `market_state=ranging` или `market_state=trending`
- строки `Not tradeable` нет

И потом есть:

- `Liquidity map: ... levels`

Но нет:

- `Sweep signal: ...`
- `Breakout signal: ...`

Это значит:

- рынок уже проходит базовые фильтры;
- но конкретного сетапа для входа пока нет.

### 3. Сигнал возможен прямо сейчас

Если лог идет так:

- `MarketContext(... tradeable=True)`
- `Liquidity map: ...`
- затем:
  - `Sweep signal: ...`
  - или `Breakout signal: ...`

А потом появляется:

- `Signal: LONG sweep_reversal ...`
- или `Signal: SHORT breakout ...`

Это значит:

- сигнал действительно сформирован;
- фильтры пройдены;
- confidence прошел порог.

## Быстрая шпаргалка

- Есть `Not tradeable` -> сигнала в этом цикле не будет
- Нет `Not tradeable`, но нет `Sweep signal` / `Breakout signal` -> рынок нормальный, входа пока нет
- Есть `Sweep signal` / `Breakout signal` и потом `Signal:` -> сигнал найден

## Команды для поиска по логу

### Ключевые состояния цикла

```powershell
Select-String -Path logs\bot.log -Pattern "MarketContext|Not tradeable|Liquidity map|Sweep signal|Breakout signal|Signal:"
```

Что это дает:

- `MarketContext` — базовое состояние рынка
- `Not tradeable` — сигналов в этом цикле точно не будет
- `Liquidity map` — рынок прошел базовые фильтры
- `Sweep signal` / `Breakout signal` — стратегия нашла кандидата
- `Signal:` — финальный подтвержденный сигнал

### Только финальные сигналы

```powershell
Select-String -Path logs\bot.log -Pattern "Signal:"
```

### Только причины, почему бот молчит

```powershell
Select-String -Path logs\bot.log -Pattern "Not tradeable"
```

### Только почти боевые циклы

```powershell
Select-String -Path logs\bot.log -Pattern "MarketContext|Liquidity map|Sweep signal|Breakout signal|Signal:"
```

### Live-просмотр лога

```powershell
Get-Content logs\bot.log -Wait
```

### Live-фильтр только по важному

```powershell
Get-Content logs\bot.log -Wait | Select-String "MarketContext|Not tradeable|Sweep signal|Breakout signal|Signal:"
```

## Практическое использование

Если бот запущен так:

```powershell
python main.py --dry-run --log-level=INFO
```

то дальше логика такая:

- в неудачное время бот будет писать `Not tradeable`;
- в хорошие часы рынок начнет проходить дальше по pipeline;
- при появлении сетапа сначала появится кандидат стратегии;
- потом появится финальный `Signal: ...`.

## Что запускать

Если цель — ждать сигналы:

```powershell
python main.py --dry-run --log-level=INFO
```

Если цель — только открыть web-интерфейс:

```powershell
python scripts\run_web_local.py
```

Важно:

- `main.py` запускает анализ, scheduler, WebSocket и API;
- `run_web_local.py` запускает только web/API без генерации сигналов.
