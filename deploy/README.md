# 🚀 VPS Deployment Guide

## 📋 Quick Start

### **1. На локальном компьютере:**

```powershell
# Откройте PowerShell от имени администратора
cd d:\bot_final\deploy

# Отредактируйте upload-to-vps.ps1
notepad upload-to-vps.ps1

# Введите ваши данные:
$VPS_IP = "ваш_ip"
$VPS_USER = "root"

# Запустите загрузку
.\upload-to-vps.ps1
```

### **2. На VPS:**

```bash
# Подключитесь к VPS
ssh root@your-vps-ip

# Запустите развёртывание
sudo bash /tmp/crypto-bot-source/deploy/deploy.sh

# Настройте .env
nano /opt/crypto-bot/.env

# Перезапустите бота
systemctl restart crypto-bot

# Проверьте статус
systemctl status crypto-bot
```

### **3. Настройте SSL (опционально):**

```bash
# Если у вас есть домен
certbot --nginx -d your-domain.com
```

---

## 📁 Файлы для развёртывания

| Файл | Назначение |
|------|------------|
| `deploy.sh` | Скрипт развёртывания на VPS |
| `upload-to-vps.ps1` | Загрузка файлов на VPS |
| `docker-compose-vps.yml` | Docker Compose для VPS |
| `nginx.conf` | Конфигурация Nginx |

---

## 🔧 Альтернативные способы

### **A. Через Git:**

```bash
# На VPS
cd /opt
git clone https://github.com/your-username/crypto-bot.git
cd crypto-bot
sudo bash deploy/deploy.sh
```

### **B. Через Docker:**

```bash
# На VPS
cd /opt/crypto-bot
sudo docker-compose -f deploy/docker-compose-vps.yml up -d
```

### **C. Вручную (WinSCP/FileZilla):**

1. Откройте WinSCP или FileZilla
2. Подключитесь к VPS
3. Загрузите файлы в `/opt/crypto-bot`
4. На VPS:
   ```bash
   cd /opt/crypto-bot
   sudo bash deploy/deploy.sh
   ```

---

## ✅ Проверка

```bash
# Проверка бота
curl http://localhost:8001/health

# Проверка Dashboard
curl http://localhost:8001/dashboard

# Проверка Nginx
systemctl status nginx

# Логи
tail -f /opt/crypto-bot/logs/bot.log
```

---

## 🆘 Troubleshooting

### **Бот не запускается:**
```bash
journalctl -u crypto-bot -n 50
```

### **Порт 8001 занят:**
```bash
netstat -tlnp | grep 8001
kill -9 <PID>
systemctl restart crypto-bot
```

### **Nginx ошибка:**
```bash
nginx -t
systemctl restart nginx
```

---

## 📞 Команды управления

```bash
# Статус
systemctl status crypto-bot

# Перезапуск
systemctl restart crypto-bot

# Остановка
systemctl stop crypto-bot

# Запуск
systemctl start crypto-bot

# Логи
journalctl -u crypto-bot -f
tail -f /opt/crypto-bot/logs/bot.log
```

---

## 🎉 Готово!

**Ваш бот работает на VPS!**

**Доступ:**
- Dashboard: `http://your-vps-ip/dashboard`
- API: `http://your-vps-ip/health`
- Telegram: @Akoffice_bot
