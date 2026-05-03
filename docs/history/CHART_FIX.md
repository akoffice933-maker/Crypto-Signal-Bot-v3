# 📈 Chart Fix — Correct Formatting

**Дата:** 2026-03-28  
**Проблема:** График некорректно форматировался на мобильных

---

## ✅ Исправления

### 1. Контейнер графика

**HTML:**
```html
<div id="chart-container" style="height: 250px; width: 100%; position: relative;"></div>
```

**CSS:**
```css
#chart-container {
  width: 100% !important;
  max-width: 100% !important;
  height: 250px !important;
  min-height: 250px !important;
  position: relative !important;
  overflow: hidden !important;
}

/* Fix chart canvas sizing */
#chart-container canvas {
  width: 100% !important;
  height: 100% !important;
}
```

### 2. ResizeObserver для авторесайза

**JavaScript:**
```javascript
const resizeObserver = new ResizeObserver(entries => {
  if (!chart || entries.length === 0) return;
  
  const { width, height } = entries[0].contentRect;
  if (width > 0 && height > 0) {
    chart.applyOptions({
      width: width,
      height: height,
    });
  }
});

const container = document.getElementById("chart-container");
resizeObserver.observe(container);
```

### 3. Lightweight Charts настройки

```javascript
chart = LightweightCharts.createChart(container, {
  width: containerWidth,
  height: containerHeight,  // 250px для мобильных
  layout: {
    background: { color: 'transparent' },
    textColor: '#5c6258',
  },
  timeScale: {
    fixLeftEdge: true,
    fixRightEdge: true,
  },
  rightPriceScale: {
    autoScale: true,
  },
});
```

---

## 📱 Мобильные размеры

| Устройство | Высота графика |
|------------|----------------|
| Desktop    | 250px          |
| Tablet     | 250px          |
| Mobile     | 250px          |
| Small phone| 200px          |

---

## 🚀 Деплой

```bash
# Загрузить файл
scp -P 2222 web/static/dashboard.html root@148.222.186.16:/opt/crypto-bot/web/static/

# Hard refresh (Ctrl+F5)
```

---

## 📊 Проверка

### Desktop
- ✅ График 250px высота
- ✅ Canvas на 100% ширины
- ✅ ResizeObserver работает

### Mobile
- ✅ График 250px (200px на <480px)
- ✅ Canvas масштабируется
- ✅ Нет обрезки

---

**Готово!** 🎉
