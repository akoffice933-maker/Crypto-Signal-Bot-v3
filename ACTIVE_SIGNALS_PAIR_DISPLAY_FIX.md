# ✅ Active Signals — Pair Display Fix

**Дата:** 2026-03-28  
**Проблема:** При смене пары сигналы не обновлялись корректно

---

## ✅ Исправления

### 1. Всегда пересоздавать grid

**До:**
```javascript
let grid = container.querySelector(".active-signals-grid");
if (!grid) {
  container.innerHTML = '<div class="active-signals-grid"></div>';
}
grid.innerHTML = '';  // Старые карточки могли остаться
```

**После:**
```javascript
// Always recreate grid to ensure clean render
container.innerHTML = '<div class="active-signals-grid"></div>';
const grid = container.querySelector(".active-signals-grid");
// Все старые карточки удалены
```

### 2. Очищать контейнер при "No signals"

**До:**
```javascript
if (!signals || signals.length === 0) {
  if (!container.querySelector('.active-signals-grid')) {
    // Не очищало если grid существовал
  }
}
```

**После:**
```javascript
if (!signals || signals.length === 0) {
  // Clear container and show "no signals" message
  const pairText = selectedPair ? ` for ${selectedPair}` : '';
  container.innerHTML = `<div class="loading">No active signals${pairText}</div>`;
  return;
}
```

### 3. Фильтр по паре работает

**JavaScript:**
```javascript
const selectedPair = document.getElementById("active-pair").value;
const pairParam = selectedPair ? `?pair=${selectedPair}` : '';
const signals = await fetchJson(`/signals/active${pairParam}`);
```

**API (Python):**
```python
@router.get("/active")
async def active_signals(pair: Optional[str] = None):
    if pair:
        pair_filter = " AND pair=?"
        params.append(pair.upper())
```

---

## 📊 Результат

| Действие | До | После |
|----------|----|-------|
| Смена пары | Старые сигналы | ✅ Только выбранная пара |
| Нет сигналов | Grid оставался | ✅ "No signals for BTC" |
| All pairs | Работало | ✅ Работает |
| BTC → ETH | BTC оставался | ✅ Только ETH |

---

## 🚀 Деплой

```bash
scp -P 2222 web/static/dashboard.html root@148.222.186.16:/opt/crypto-bot/web/static/
```

---

## ✅ Проверка

1. **Открыть dashboard**
2. **Выбрать BTCUSDT** в Active Signals:
   - ✅ Показываются только BTCUSDT
3. **Выбрать ETHUSDT**:
   - ✅ BTCUSDT исчезли
   - ✅ Показываются только ETHUSDT
4. **Выбрать "All pairs"**:
   - ✅ Показываются все сигналы
5. **Выбрать пару без сигналов**:
   - ✅ "No active signals for SOLUSDT"

---

**Готово!** 🎉
