# Crypto Signal Bot v3/v4 Hybrid — Полное Описание Стратегии

## 1. Назначение

Данная стратегия представляет собой алгоритмическую intraday-систему для `BTCUSDT Futures`, ориентированную на поиск высоковероятных точек входа после многоступенчатой фильтрации рыночных условий.

Система не торгует постоянно. Ее логика построена вокруг идеи селективности:

- сначала отсекаются неблагоприятные режимы рынка;
- затем строится карта ликвидности;
- далее оцениваются волатильность, order flow и подтверждающие факторы;
- только после этого стратегия допускает вход.

Стратегия реализована в коде и работает циклами каждые `15 минут`.


## 2. Торгуемый инструмент и частота работы

- Инструмент: `BTCUSDT`
- Рынок: Binance Futures
- Основной рабочий таймфрейм: `15m`
- Контекстные таймфреймы: `4h` и `1d`
- Периодичность анализа: каждые `15 минут`

Привязка к коду:

- `symbol`
- `analysis_interval_minutes`
- `liquidity_timeframes`


## 3. Архитектурная идея

Стратегия сочетает 4 группы сигналов:

1. Режим рынка
2. Ликвидность
3. Order flow
4. Price action / breakout behavior

В коде это реализовано как последовательный pipeline:

1. Загрузка свечей `15m / 4h / 1d`
2. Расчет состояния рынка: `ADX`, `ATR%`, торговая сессия, operating mode
3. Hard-block фильтрация
4. Построение liquidity map
5. Проверка `4h squeeze`
6. Оценка order flow: funding, OI, CVD
7. Поиск `Sweep Reversal`
8. Поиск `Volatility Breakout`
9. Фильтрация по `confidence score`
10. Проверка cooldown
11. Сохранение сигнала и отправка в Telegram


## 4. Источники данных

Система использует следующие данные:

- OHLCV свечи `15m`, `4h`, `1d`
- Funding rate
- Open interest
- CVD divergence из WebSocket order flow
- Состояние squeeze на `4h`

Практически это означает, что стратегия сочетает price action, старшие уровни ликвидности и derivatives context.


## 5. Торговые сессии

В стратегии зафиксированы UTC-сессии:

- `asian`: `00:00-08:00`
- `london`: `07:00-11:00`
- `ny`: `13:00-17:00`

При пересечении приоритет у `london`, затем `ny`, затем `asian`.

Вне сессий новые сигналы не формируются.

Привязка к коду:

- `sessions`
- `get_session(hour_utc)`


## 6. Рыночные режимы: BLOCKED / QUIET / NORMAL

Одно из ключевых свойств стратегии — работа в разных режимах волатильности.

### 6.1. Основа классификации

Режим определяется через `ATR%`:

- `BLOCKED`: `ATR% < 0.20%`
- `QUIET`: `0.20% <= ATR% < 0.60%`
- `NORMAL`: `ATR% >= 0.60%`

В коде это соответствует:

- `quiet_atr_min = 0.0020`
- `quiet_atr_max = 0.0060`
- `atr_normal_max = 0.015`
- `adx_trending_threshold = 25.0`
- `adx_dead_zone_min = 21.0`
- `adx_dead_zone_max = 24.0`

Дополнительно используется `ADX`:

- `trending`: `ADX > 25`
- `dead_zone`: `21 <= ADX <= 24`
- `ranging`: все остальное

### 6.2. Практический смысл режимов

`BLOCKED`

- рынок слишком тихий;
- стратегия не торгует;
- цикл останавливается до стратегий.

`QUIET`

- рынок торгуемый, но менее импульсный;
- стратегия работает осторожнее;
- breakout отключен;
- требования к уровням строже;
- порог confidence мягче, но структура сигнала должна быть качественной.

`NORMAL`

- рынок допускает полный набор логики;
- активны обе стратегии: sweep и breakout;
- допускаются более агрессивные импульсные сценарии.


## 7. Hard Blocks: когда стратегия вообще не торгует

До запуска стратегий система применяет набор жестких фильтров.

### 7.1. Weekend Block

В субботу и воскресенье стратегия не торгует.

Причина:

- качество ликвидности в выходные хуже;
- выше риск ложных движений;
- ниже воспроизводимость сигналов.

### 7.2. Off-hours

Если текущий UTC-час не попадает ни в одну из торговых сессий, цикл останавливается.

### 7.3. Dead Zone по ADX

Если `ADX` попадает в диапазон неопределенности `21-24`, рынок считается нежелательным для входа.

Параметры:

- `adx_dead_zone_min`
- `adx_dead_zone_max`

### 7.4. Слишком низкая волатильность

Если `ATR%` ниже минимального порога для торговли, цикл блокируется.

Параметры:

- `quiet_atr_min`
- `quiet_atr_max`

### 7.5. Quiet session allowlist

В `QUIET` режиме возможна дополнительная фильтрация по разрешенным сессиям. В текущей конфигурации разрешены:

- `asian`
- `london`
- `ny`

То есть сейчас `QUIET` не ограничен по сессиям, но архитектура фильтра в коде предусмотрена.

Параметр:

- `quiet_allowed_sessions`


## 8. Liquidity Map

После прохождения hard blocks стратегия строит карту ликвидности на таймфреймах `1d` и `4h`.

### 8.1. Что считается уровнем ликвидности

Стратегия ищет:

- `equal_highs`
- `equal_lows`

Это кластеры экстремумов, где цена несколько раз касалась примерно одной зоны.

### 8.2. Базовые параметры

- lookback: `90 дней`
- minimum touches: `2`
- tolerance: `0.3%`

Параметры:

- `liquidity_lookback_days`
- `liquidity_touch_min`
- `liquidity_tolerance_pct`
- `liquidity_min_distance_pct`
- `liquidity_timeframes`

### 8.3. Оценка уровня

Для каждого уровня рассчитываются:

- `touch_count`
- `strength`
- `distance_pct`
- `mitigated`
- `freshness_score`
- `level_score`

Поля структуры `LiquidityLevel`:

- `touch_count`
- `strength`
- `distance_pct`
- `mitigated`
- `freshness_score`
- `level_score`

### 8.4. Freshness / Quality Logic

Уровни не хранятся бесконечно между циклами. Они пересчитываются заново на каждом цикле.

Однако внутри цикла уровни ранжируются по качеству:

- меньшее число касаний обычно означает более "свежий" уровень;
- слишком многократно протестированные уровни штрафуются;
- `1d` уровни получают больший вес, чем `4h`.

### 8.5. Фильтрация по уровню в режимах

Минимальный `level_score`:

- `NORMAL`: `>= 5`
- `QUIET`: `>= 7`

Это означает, что в тихом рынке стратегия требует более качественной ликвидности, чем в обычном режиме.

Важно: это отдельный pre-filter внутри `Sweep Reversal`, а не только косвенное влияние через confidence. После этого `freshness_score` дополнительно влияет уже на confidence как бонус/штраф.

Параметры:

- `normal_level_score_min`
- `quiet_level_score_min`


## 9. Order Flow Layer

После карты ликвидности подключается слой order flow.

В текущей реализации используются:

- `funding rate`
- `open interest change`
- `liquidation cascade`
- `CVD divergence`

Параметры:

- `oi_drop_threshold_pct`
- `oi_price_move_pct`
- `oi_lookback_minutes`
- `funding_extreme_threshold`
- `funding_block_threshold`

### 9.1. Funding

Funding используется как фактор качества:

- экстремальный funding против направления сделки может давать бонус;
- слишком экстремальный funding в сторону сделки может давать штраф или блокировать confidence.

### 9.2. OI Cascade

Если наблюдается достаточное падение OI на фоне движения цены, это трактуется как liquidation-driven move и добавляет confidence.

### 9.3. CVD Divergence

Если divergence совпадает с направлением сигнала:

- bullish divergence поддерживает LONG;
- bearish divergence поддерживает SHORT.


## 10. Strategy A: Sweep Reversal

Это основная стратегия текущей системы.

### 10.1. Идея

Стратегия ищет ложный прокол уровня ликвидности с возвратом цены обратно и свечным подтверждением разворота.

### 10.2. Логика LONG

Для LONG требуется:

- уровень типа `equal_lows`;
- sweep candle пробивает уровень вниз;
- sweep candle закрывается обратно выше уровня;
- rejection candle показывает сильный нижний фитиль;
- рассчитывается stop loss под экстремум sweep;
- take profit берется по ближайшему валидному уровню ликвидности в сторону движения.

### 10.3. Логика SHORT

Для SHORT требуется:

- уровень типа `equal_highs`;
- sweep candle пробивает уровень вверх;
- sweep candle возвращается под уровень;
- rejection candle показывает сильный верхний фитиль;
- stop loss ставится за sweep high;
- target берется ниже по ликвидности.

### 10.4. Свечные требования

Rejection candle:

- в `NORMAL`: `wick >= 2.5 x body`
- в `QUIET`: `wick >= 2.0 x body`
- `body <= 1/3 range`

Параметры:

- `rejection_wick_ratio`
- `quiet_rejection_wick_ratio`
- `rejection_body_range_max`

### 10.5. Volume logic

Volume spike рассчитывается по отношению к `MA20`:

- `NORMAL`: `>= 1.2x`
- `QUIET`: `>= 1.05x`

Дополнительно в pipeline действует правило:

- если у sweep-сигнала нет volume spike и confidence ниже `75`, сигнал отбрасывается как `MANDATORY FAIL`

Параметры:

- `normal_volume_spike_multiplier`
- `quiet_volume_spike_multiplier`
- `volume_spike_multiplier` — legacy/global fallback

### 10.6. RR logic

Минимальный RR:

- `NORMAL`: `>= 2.0`
- `QUIET`: `>= 1.3`

Если целевой уровень ликвидности не найден, используется fallback target по минимальному RR.

Параметры:

- `normal_min_rr`
- `quiet_min_rr`
- `min_rr` — legacy/global fallback

### 10.7. TP cap

Если target получается слишком далеким, стратегия ограничивает take profit максимумом `10%` от entry.

### 10.8. Роль стратегии

`Sweep Reversal` — основная стратегия для:

- QUIET режима
- ranging/trending откатных разворотов
- сценариев с явным сбором ликвидности


## 11. Strategy B: Volatility Breakout

Это вспомогательная стратегия, которая работает только в определенных условиях.

### 11.1. Когда активна

Breakout запускается только если:

- `operating_mode == NORMAL`
- `squeeze_active == True`
- `sweep` не дал сигнала

То есть breakout — не первая стратегия, а вторая ветка после sweep.

### 11.2. Логика сигнала

Система проверяет:

- breakout выше верхней полосы Bollinger -> `LONG`
- breakout ниже нижней полосы Bollinger -> `SHORT`

### 11.3. Entry

- entry = close breakout-candle

### 11.4. Stop Loss

Ранее breakout использовал фиксированный стоп `0.7%`.

В текущей реализации используется adaptive ATR-based stop:

`sl_pct = clamp(ATR% x 1.5, min=0.5%, max=1.2%)`

Режимы логируются как:

- `adaptive_min_clamp`
- `adaptive_raw`
- `adaptive_max_clamp`
- `fixed_fallback` если ATR недоступен

Параметры:

- `breakout_sl_pct` — fallback
- `breakout_sl_atr_mult`
- `breakout_sl_min_pct`
- `breakout_sl_max_pct`
- `breakout_sl_quiet_atr_mult`
- `breakout_sl_normal_atr_mult`

### 11.5. Take Profit

TP пока фиксирован по целевому диапазону:

- `2%-4%`
- в коде используется среднее значение диапазона, то есть около `3%`

Параметры:

- `breakout_tp_min`
- `breakout_tp_max`

### 11.6. RR logic

RR рассчитывается уже после adaptive SL. Если после пересчета RR ниже режима, сигнал не проходит.

### 11.7. Роль стратегии

Breakout ориентирован на:

- expansion after squeeze
- высоковолатильные импульсные сценарии
- продолжение движения в `NORMAL` режиме


## 12. Confidence Score

После нахождения кандидата стратегия не отправляет сигнал автоматически. Она рассчитывает `confidence score`.

### 12.1. Базовые факторы

Для `Sweep Reversal`:

- `+30` Liquidity sweep confirmed

Для `Breakout`:

- `+25` Squeeze breakout

### 12.2. Дополнительные факторы

- `+20` Volume spike
- `+20` Active session
- `+20` 4h squeeze
- `+10` Trend alignment
- `+15` CVD divergence
- `+10` funding counter-direction
- `+15` liquidation cascade

### 12.3. Freshness contribution

Уровень влияет на confidence:

- `Fresh level` -> `+10`
- `Moderate level` -> `+5`
- `Stale level` -> `-10`

### 12.4. Штрафы

- `-15` funding blocks signal
- `-25` сильный counter-trend при `ADX > 40`
- `-30` outside sessions

### 12.5. Порог

Confidence thresholds:

- `NORMAL`: `>= 70`
- `QUIET`: `>= 60`

Это берется из:

- `normal_confidence_threshold = 70`
- `quiet_confidence_threshold = 60`
- `confidence_threshold` — legacy/global value, уже не основной для live-pipeline

Если кандидат не проходит порог, pipeline пишет explicit:

- `CONFIDENCE FAIL (Sweep)`
- `CONFIDENCE FAIL (Breakout)`

с breakdown причин.


## 13. Система принятия решения

Полный decision flow выглядит так:

1. Проверка weekend
2. Проверка сессии
3. Проверка `ATR%`
4. Проверка `ADX dead zone`
5. Построение liquidity map
6. Проверка squeeze
7. Сбор funding/OI/CVD
8. Поиск `Sweep Reversal`
9. Если sweep нет, поиск `Breakout`
10. Проверка confidence
11. Проверка cooldown
12. Отправка сигнала


## 14. Cooldown и исполнение

Даже валидный сигнал не отправляется повторно бесконтрольно.

В системе есть cooldown:

- `60 минут` на идентификатор сигнала

Параметр и реализация:

- cooldown ставится через `db.set_cooldown(..., minutes=60)`
- проверяется через `db.is_on_cooldown(...)`

После прохождения:

- сигнал сохраняется в БД;
- выставляется cooldown;
- при наличии notifier отправляется в Telegram.


## 15. Что сохраняется в сигнале

Сигнал включает:

- strategy
- direction
- session
- entry market
- stop loss
- take profit
- rr ratio
- confidence score
- confidence breakdown
- market state
- volatility regime
- atr_pct
- adx_value
- order flow context

Это делает сигнал интерпретируемым и пригодным для последующего аудита.


## 16. Сильные стороны стратегии

### 16.1. Селективность

Стратегия не пытается торговать каждый цикл. Она отсекает рыночные условия до входа, что снижает churn.

### 16.2. Гибкость по режиму волатильности

Разделение на `BLOCKED / QUIET / NORMAL` делает поведение более адаптивным.

### 16.3. Комбинация price action и derivatives context

Ликвидность, свечные паттерны, funding, OI, CVD и squeeze не используются изолированно; они комбинируются в единый фильтр качества.

### 16.4. Объяснимость

Система умеет объяснить:

- почему сигнал был заблокирован;
- почему кандидат не прошел confidence;
- почему цикл завершился без сделки.

Это критично для аудита и мониторинга.


## 17. Ограничения текущей реализации

Стратегия уже рабочая, но у нее есть ограничения.

### 17.1. Один инструмент

Система сейчас работает только по `BTCUSDT`.

### 17.2. Risk layer еще базовый

Есть stop loss, take profit и cooldown, но нет полноценного position limit manager и завершенного portfolio-level risk engine.

Связанные параметры:

- `account_balance`
- `max_risk_per_trade_pct`
- `max_position_pct`

### 17.3. Backtest не полностью равен live

Backtester стал ближе к live по core filters, но это не полный live parity:

- упрощен data context;
- не все live-компоненты полностью воспроизводятся;
- order flow и execution context не идентичны продовой среде.

### 17.4. Breakout менее зрелый, чем sweep

На текущий момент `Sweep Reversal` — более зрелая и центральная стратегия системы.
`Breakout` — полезная вторая ветка, но не основа всей архитектуры.


## 18. Для кого подходит стратегия

Стратегия подходит для:

- private capital / founder capital
- controlled pilot live deployment
- signal service с ручной или полуавтоматической валидацией

Для внешнего инвесторского капитала стратегия требует:

- длинной live-статистики;
- подтвержденного winrate и expectancy;
- отчета по drawdown;
- стабильного execution layer;
- полного risk framework.


## 19. Итоговая позиция

Это не "мем-бот" и не примитивный индикаторный скрипт.

Это селективная BTC intraday strategy, которая:

- понимает рыночный режим;
- работает с ликвидностью старших таймфреймов;
- использует order flow как подтверждение;
- разделяет reversal и breakout сценарии;
- фильтрует сделки по quality score;
- объясняет свои решения через логи и breakdown.

На текущем этапе стратегия уже является рабочим signal engine.
Как инвестпродукт она находится на стадии сильного prototype / early live system, а не финального institutional-grade решения.


## 20. Короткое investor summary

`Crypto Signal Bot` — это алгоритмическая intraday-стратегия для BTC futures, которая ищет либо разворот после сбора ликвидности, либо продолжение движения после сжатия волатильности. Система не торгует постоянно: она сначала определяет, пригоден ли рынок для сделки, затем строит карту ликвидности, проверяет контекст деривативов и только после этого принимает решение. Основной акцент сделан на селективность, объяснимость и контроль качества сигнала, а не на максимальное количество входов.


## 21. Сводка параметров из settings.py

Ниже перечислены основные параметры, которые прямо управляют стратегией:

### 21.1. Общие

- `symbol`
- `analysis_interval_minutes`
- `confidence_threshold`
- `min_rr`
- `target_move_min_pct`
- `target_move_max_pct`

### 21.2. Режимы рынка

- `quiet_atr_min`
- `quiet_atr_max`
- `normal_confidence_threshold`
- `quiet_confidence_threshold`
- `normal_volume_spike_multiplier`
- `quiet_volume_spike_multiplier`
- `normal_min_rr`
- `quiet_min_rr`
- `quiet_allowed_sessions`
- `normal_level_score_min`
- `quiet_level_score_min`

### 21.3. ADX / ATR

- `adx_trending_threshold`
- `adx_dead_zone_min`
- `adx_dead_zone_max`
- `atr_low_threshold`
- `atr_normal_max`
- `atr_lookback_candles`

### 21.4. Liquidity

- `liquidity_lookback_days`
- `liquidity_touch_min`
- `liquidity_tolerance_pct`
- `liquidity_min_distance_pct`
- `liquidity_timeframes`

### 21.5. Squeeze

- `squeeze_tf`
- `squeeze_lookback`
- `squeeze_range_max_pct`
- `squeeze_range_candles`

### 21.6. Order Flow

- `oi_drop_threshold_pct`
- `oi_price_move_pct`
- `oi_lookback_minutes`
- `funding_extreme_threshold`
- `funding_block_threshold`

### 21.7. Sweep Reversal

- `sweep_tolerance_pct`
- `rejection_wick_ratio`
- `quiet_rejection_wick_ratio`
- `rejection_body_range_max`
- `volume_spike_multiplier`
- `limit_entry_pct`

### 21.8. Breakout

- `breakout_sl_pct`
- `breakout_tp_min`
- `breakout_tp_max`
- `breakout_sl_atr_mult`
- `breakout_sl_min_pct`
- `breakout_sl_max_pct`
- `breakout_sl_quiet_atr_mult`
- `breakout_sl_normal_atr_mult`

### 21.9. Risk

- `account_balance`
- `max_risk_per_trade_pct`
- `max_position_pct`


## 22. Рекомендации по развитию стратегии

Ниже приведен практический roadmap развития стратегии, если цель — поднять систему от сильного prototype / early live stage к более зрелому investor-grade продукту.

### 22.1. P1 — критично для качества стратегии

Это наиболее важные направления, которые стоит реализовывать в первую очередь.

#### 1. Полноценный backtest / live parity

Главная задача — сделать так, чтобы бэктест воспроизводил live-логику максимально близко:

- те же фильтры;
- те же режимы рынка;
- ту же логику confidence;
- сопоставимые сигналы на одной и той же истории.

Практический минимум:

- `12-18 месяцев` истории;
- обязательно включить периоды разного рынка, включая `2022`, `2024`, `2025`;
- отдельная валидация по сильным трендам, флэту и event-driven volatility.

Почему это приоритет №1:

- без этого трудно честно оценить edge;
- невозможно уверенно калибровать risk layer;
- любые улучшения в сигнале будут выглядеть лучше или хуже только из-за рассинхрона среды.

#### 2. Улучшение risk layer

Сейчас система уже имеет базовые risk-параметры, но для следующего уровня зрелости нужны:

- dynamic position sizing по ATR / volatility regime;
- daily loss limit;
- weekly loss limit;
- exposure caps;
- ограничение максимального одновременного directional exposure.

Это позволит:

- снизить риск серии убытков;
- избежать избыточного риска в нестабильные периоды;
- сделать equity curve более управляемой.

#### 3. Усиление защиты от false sweep в сильном тренде

Сейчас в стратегии уже есть penalty для counter-trend сигналов при `ADX > 40`, но это можно усилить.

Потенциальные направления:

- усиленный штраф в confidence;
- обязательный volume / order flow confirmation в таких случаях;
- отдельный hard block для weakest counter-trend setups при экстремальном ADX.

Почему это важно:

- именно в сильных трендах ложные reversal-сценарии дают один из самых опасных классов ошибок;
- стратегия уже знает об этом риске, но пока реагирует на него умеренно.


### 22.2. P2 — улучшение управления прибылью

После стабилизации parity и risk layer логично развивать управление уже открытой позицией.

#### 4. Partial scaling out

Один из практичных вариантов:

- закрывать `50%` позиции на `1.5R`;
- остаток держать до liquidity target.

Преимущества:

- быстрее фиксируется часть результата;
- снижается психологическая и статистическая нагрузка от полного отката сделки;
- растет устойчивость стратегии на неоднородных импульсах.

#### 5. Trailing stop

Trailing stop можно использовать:

- либо после прохождения `1R`;
- либо только после partial take-profit;
- либо только для breakout-сценариев.

Важно:

- внедрять trailing нужно только после нормального parity и статистики;
- иначе легко получить красивую, но ложную оптимизацию на истории.


### 22.3. P3 — масштабирование стратегии

После стабилизации BTC-модели можно думать о расширении.

#### 6. Мульти-инструментальность

Стратегию можно тестировать на нескольких ликвидных инструментах:

- `ETHUSDT`
- `SOLUSDT`
- другие высоколиквидные perpetual futures

Цель:

- снизить зависимость от одного рынка;
- проверить переносимость edge;
- построить basket-level signal engine.

Важно:

- масштабировать стоит только после подтверждения edge на `BTCUSDT`;
- иначе масштабируется не преимущество, а шум.


### 22.4. P4 — фильтр макро-событий

Это полезный, но не первоочередной слой.

#### 7. Optional news / volatility event filter

Можно добавить отдельный optional filter для крупных макро-событий:

- `FOMC`
- `CPI`
- `NFP`
- другие запланированные volatility events

Варианты реализации:

- hard block за `N` минут до/после события;
- отдельный режим снижения риска;
- отключение только breakout-ветки в event window.

Почему это не P1:

- сама по себе стратегия уже фильтрует рынок через ATR, ADX, session и confidence;
- news-filter полезен, но не заменяет фундаментальную доработку parity и risk layer.


### 22.5. Предлагаемый порядок внедрения

Оптимальный порядок выглядит так:

1. `P1`: backtest/live parity
2. `P1`: risk limits и position/risk layer
3. `P1`: усиление anti-false-sweep логики при `ADX > 40`
4. `P2`: partial scaling out
5. `P2`: trailing stop
6. `P3`: multi-asset expansion
7. `P4`: optional macro-event filter


### 22.6. Целевое состояние стратегии после roadmap

Если roadmap будет реализован последовательно, стратегия должна перейти из статуса:

- `working selective signal engine`

в статус:

- `validated systematic trading framework`

То есть система станет:

- более воспроизводимой;
- более устойчивой к смене режима рынка;
- лучше управляемой по риску;
- более пригодной для внешнего капитала и investor reporting.
