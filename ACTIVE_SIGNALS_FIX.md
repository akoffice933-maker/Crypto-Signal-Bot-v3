# ⚡ Active Signals — No Flicker Fix

**Дата:** 2026-03-28  
**Проблема:** Сигналы пропадали и появлялись снова при обновлении

---

## ✅ Исправления

### 1. Не очищать контейнер перед загрузкой

**До:**
```javascript
container.innerHTML = '<div class="loading">Loading...</div>';
// Сигналы пропали!
```

**После:**
```javascript
// Добавить индикатор "Updating..." поверх существующих
const loadingIndicator = container.querySelector('.loading-indicator');
if (!loadingIndicator) {
  const tempLoading = document.createElement('div');
  tempLoading.className = 'loading loading-indicator';
  tempLoading.textContent = 'Updating...';
  container.appendChild(tempLoading);
}
```

### 2. Сохранять предыдущие данные при ошибке

**До:**
```javascript
} catch (e) {
  sig.current_price = null;  // Потеряли данные!
  sig.pnl_pct = null;
}
```

**После:**
```javascript
} catch (e) {
  // Keep previous price if fetch fails
  sig.current_price = sig.current_price || null;
  sig.pnl_pct = sig.pnl_pct || null;
}
```

### 3. Не очищать при ошибке загрузки

**До:**
```javascript
} catch (error) {
  container.innerHTML = `<div class="error">Error...</div>`;
  // Всё пропало!
}
```

**После:**
```javascript
} catch (error) {
  console.error("Active signals load error:", error);
  // Don't clear on error - preserve existing content
  const loadingEl = container.querySelector('.loading-indicator');
  if (loadingEl) loadingEl.textContent = '⚠️ Update failed';
  setTimeout(() => {
    const el = container.querySelector('.loading-indicator');
    if (el) el.remove();
  }, 2000);
}
```

### 4. Обновлять grid, а не container

**До:**
```javascript
function renderActiveSignals(signals) {
  container.innerHTML = '<div class="active-signals-grid"></div>';
  // Всё содержимое удалено!
}
```

**После:**
```javascript
function renderActiveSignals(signals) {
  let grid = container.querySelector(".active-signals-grid");
  
  // Create grid if not exists
  if (!grid) {
    container.innerHTML = '<div class="active-signals-grid"></div>';
    grid = container.querySelector(".active-signals-grid");
  }

  // Clear grid only (not container)
  grid.innerHTML = '';
  // ... render cards
}
```

### 5. Увеличить интервал обновления

**До:** 10 секунд  
**После:** 15 секунд

```javascript
setInterval(() => loadActiveSignals().catch(console.error), 15000);
```

---

## 📊 Результат

| Ситуация | До | После |
|----------|----|-------|
| Обновление | Мигание | Плавное |
| Ошибка API | Пустой контейнер | Сохранение данных |
| Нет сигналов | Мигание "No signals" | Стабильно |
| Интервал | 10 сек | 15 сек |

---

## 🚀 Деплой

```bash
scp -P 2222 web/static/dashboard.html root@148.222.186.16:/opt/crypto-bot/web/static/
```

---

## ✅ Проверка

1. Открыть dashboard
2. Подождать 15 секунд
3. Проверить:
   - ✅ Сигналы не пропадают
   - ✅ Индикатор "Updating..." появляется
   - ✅ PnL обновляется плавно
   - ✅ При ошибке данные сохраняются

---

**Готово!** 🎉
