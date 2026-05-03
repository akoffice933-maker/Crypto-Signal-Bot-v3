# 🔄 Active Signals — Pair Sync Fix

**Дата:** 2026-03-28  
**Проблема:** При смене пары на графике, активные сигналы не фильтровались

---

## ✅ Исправления

### 1. Синхронизация при смене пары

**JavaScript:**
```javascript
document.getElementById("chart-pair").addEventListener("change", () => {
  loadChart().catch(showError);
  loadActiveSignals().catch(showError);  // Refresh signals when pair changes
});
```

### 2. Фильтр по выбранной паре

**JavaScript:**
```javascript
async function loadActiveSignals() {
  const selectedPair = document.getElementById("chart-pair").value;
  
  // Filter by selected pair
  const signals = await fetchJson(`/signals/active?pair=${selectedPair}`);
  
  if (!signals || signals.length === 0) {
    container.innerHTML = `No active signals for ${selectedPair}`;
  }
}
```

### 3. API уже поддерживает фильтр

**Python (active_signals.py):**
```python
@router.get("/active")
async def active_signals(
    pair: Optional[str] = None,  # ✅ Уже есть!
    db: Database = Depends(get_db),
):
    pair_filter = ""
    if pair:
        pair_filter = " AND pair=?"
        params.append(pair.upper())
    
    rows = await db._fetch(f"""
        SELECT ... FROM signals
        WHERE status IN ('sent', 'partial_tp1')
        {pair_filter}
        ORDER BY created_at DESC
    """)
```

---

## 📊 Результат

| Действие | До | После |
|----------|----|-------|
| Смена пары | График меняется, сигналы нет | Меняются и график, и сигналы |
| Фильтр | Нет | API фильтр по паре |
| Сообщение | "No active signals" | "No active signals for BTCUSDT" |

---

## 🚀 Деплой

```bash
scp -P 2222 web/static/dashboard.html root@148.222.186.16:/opt/crypto-bot/web/static/
```

---

## ✅ Проверка

1. Открыть dashboard
2. Выбрать BTCUSDT на графике
3. Проверить:
   - ✅ График BTCUSDT загрузился
   - ✅ Active signals показывают только BTCUSDT
4. Выбрать ETHUSDT
5. Проверить:
   - ✅ График ETHUSDT загрузился
   - ✅ Active signals показывают только ETHUSDT
   - ✅ Сообщение "No active signals for ETHUSDT" если нет сигналов

---

**Готово!** 🎉
