# 🔄 Active Signals — Pair Selector Fix

**Дата:** 2026-03-28  
**Проблема:** Логика выбора пары не работала

---

## ✅ Исправления

### 1. Добавлен отдельный селектор для Active Signals

**HTML:**
```html
<select id="active-pair">
  <option value="">All pairs</option>
  <option value="BTCUSDT">BTCUSDT</option>
  <option value="ETHUSDT">ETHUSDT</option>
  <option value="SOLUSDT">SOLUSDT</option>
  <option value="BNBUSDT">BNBUSDT</option>
</select>
```

### 2. Обработчик изменения пары

**JavaScript:**
```javascript
document.getElementById("active-pair").addEventListener("change", () => {
  loadActiveSignals().catch(showError);
});
```

### 3. Синхронизация при загрузке

**JavaScript:**
```javascript
// Sync active-pair with chart-pair on load
document.getElementById("active-pair").value = document.getElementById("chart-pair").value;
```

### 4. Фильтр API с поддержкой "All pairs"

**JavaScript:**
```javascript
async function loadActiveSignals() {
  const selectedPair = document.getElementById("active-pair").value;
  
  // Filter by selected pair (empty = all pairs)
  const pairParam = selectedPair ? `?pair=${selectedPair}` : '';
  const signals = await fetchJson(`/signals/active${pairParam}`);
  
  if (!signals || signals.length === 0) {
    const pairText = selectedPair ? ` for ${selectedPair}` : '';
    container.innerHTML = `No active signals${pairText}`;
  }
}
```

---

## 📊 Результат

| Функция | До | После |
|---------|----|-------|
| Селектор пары | Нет | ✅ Отдельный для сигналов |
| Фильтр "All pairs" | Нет | ✅ value="" |
| Синхронизация | Нет | ✅ При загрузке |
| Обработчик | chart-pair | ✅ active-pair |

---

## 🚀 Деплой

```bash
scp -P 2222 web/static/dashboard.html root@148.222.186.16:/opt/crypto-bot/web/static/
```

---

## ✅ Проверка

1. Открыть dashboard
2. Проверить:
   - ✅ Селектор "Active Signals" виден
   - ✅ "All pairs" выбрано по умолчанию
   - ✅ Синхронизировано с chart-pair
3. Выбрать BTCUSDT в Active Signals:
   - ✅ Показываются только BTCUSDT
4. Выбрать "All pairs":
   - ✅ Показываются все сигналы
5. Изменить chart-pair:
   - ✅ Active-pair синхронизируется

---

**Готово!** 🎉
