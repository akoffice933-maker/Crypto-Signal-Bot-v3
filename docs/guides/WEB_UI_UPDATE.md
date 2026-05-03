# 🎨 Web UI Update — Changelog (Sprint 1)

**Дата:** 2026-03-28  
**Версия:** 3.2.0 (multi-pair dashboard)  
**Статус:** ✅ Готово к деплою

---

## 📋 Обзор изменений

Улучшения веб-интерфейса для поддержки мульти-пар (BTC/ETH/SOL/BNB):
- Селектор пар на dashboard
- Фильтр таблицы сигналов по паре
- Страница результатов Replay Sweep
- API для статистики по парам

---

## 🗂️ Изменённые файлы

### 1. Новые файлы

| Файл | Описание |
|------|----------|
| `web/routes/replay.py` | API для replay результатов |
| `web/static/replay.html` | Страница просмотра sweep comparison |

### 2. Обновлённые файлы

| Файл | Изменения |
|------|-----------|
| `web/app.py` | Добавлен `replay_router` |
| `web/routes/signals.py` | Добавлен endpoint `/stats/by-pair` |
| `web/static/dashboard.html` | Селектор пар, фильтр таблицы, ссылка на Replay |

---

## 🎯 Новые возможности

### 1. Мульти-пар Dashboard

**Селектор пар:**
- Фильтр для таблицы сигналов
- 4 пары: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT
- Опция "All pairs"

**Новая колонка в таблице:**
- Pair — отображение пары сигнала
- Жирный шрифт для наглядности

---

### 2. API /signals/stats/by-pair

**Endpoint:** `GET /signals/stats/by-pair`

**Ответ:**
```json
{
  "BTCUSDT": {
    "total": 15,
    "longs": 8,
    "shorts": 7,
    "avg_confidence": 75.3,
    "avg_rr": 2.4,
    "tp_hits": 5,
    "sl_hits": 4,
    "winrate_pct": 55.6,
    "signals_24h": 2
  },
  "ETHUSDT": {...},
  "SOLUSDT": {...},
  "BNBUSDT": {...}
}
```

---

### 3. Страница Replay (/replay)

**Функции:**
- Просмотр результатов parameter sweep
- Таблица сравнения конфигураций
- Фильтр по экспериментам (A/B/C/D)
- Сводка: passing/partial/failing конфиги
- Экспорт в CSV

**Метрики в таблице:**
- Config ID, Experiment, Timeout, TP Model, TP Max, SL
- Signals, Validated
- Expectancy %, Profit Factor
- SL %, Timeout %, TP1 Hit %
- MFE/MAE ratio
- Verdict (✅/⚠️/❌)

---

## 🚀 Деплой

### Локально

```powershell
# 1. Проверка синтаксиса
python -m py_compile web/app.py web/routes/signals.py web/routes/replay.py

# 2. Запустить бота
python main.py --dry-run --log-level=INFO

# 3. Открыть dashboard
# http://localhost:8001/dashboard
# http://localhost:8001/replay
```

### VPS

```bash
# 1. Загрузить файлы
scp -P 2222 web/app.py web/routes/signals.py web/routes/replay.py web/static/dashboard.html web/static/replay.html root@148.222.186.16:/opt/crypto-bot/web/
scp -P 2222 web/routes/replay.py root@148.222.186.16:/opt/crypto-bot/web/routes/
scp -P 2222 web/static/replay.html root@148.222.186.16:/opt/crypto-bot/web/static/

# 2. Перезапустить бота
ssh -p 2222 root@148.222.186.16
cd /opt/crypto-bot
systemctl restart crypto-bot

# 3. Проверить логи
journalctl -u crypto-bot -f --no-pager
```

---

## 📊 Скриншоты изменений

### Dashboard (обновления)

**До:**
- Нет селектора пар
- Нет колонки Pair в таблице
- Нет ссылки на Replay

**После:**
- ✅ Селектор пар (All/BTC/ETH/SOL/BNB)
- ✅ Колонка Pair в таблице сигналов
- ✅ Ссылка "Replay" в навигации

---

### Replay страница (новая)

**URL:** `/replay`

**Элементы:**
- Toolbar с фильтром экспериментов
- Summary cards (Total/Passing/Partial/Failing/Best Expectancy)
- Таблица результатов (15 колонок)
- Кнопка Export CSV

---

## ⚠️ Возможные проблемы

### 1. 404 на /replay

**Причина:** Файл replay.html не загружен  
**Решение:**
```bash
scp -P 2222 web/static/replay.html root@148.222.186.16:/opt/crypto-bot/web/static/
```

### 2. Пустая таблица Replay

**Причина:** Нет файлов `results/replay_comparison_*.csv`  
**Решение:**
```bash
# Запустить parameter sweep
python scripts/replay_sweep.py --limit 100
```

### 3. Фильтр пар не работает

**Причина:** Старый кэш браузера  
**Решение:** Hard refresh (Ctrl+F5) или очистить кэш

---

## ✅ Чек-лист успешного деплоя

- [ ] Файлы загружены на VPS
- [ ] Бот перезапущен: `systemctl restart crypto-bot`
- [ ] Dashboard открывается: `http://148.222.186.16:8001/dashboard`
- [ ] Селектор пар виден и работает
- [ ] Колонка Pair в таблице отображается
- [ ] Страница Replay открывается: `http://148.222.186.16:8001/replay`
- [ ] API `/signals/stats/by-pair` возвращает данные

---

## 📈 Следующие шаги (Sprint 2)

**План улучшений:**
1. Графики (Lightweight Charts)
2. Active signals с PnL в реальном времени
3. Улучшенная статистика (heatmap, win rate by pair)

**Время:** 3-4 часа

---

**Готово!** 🎉

Теперь веб-интерфейс поддерживает мульти-пар мониторинг и replay результаты.
