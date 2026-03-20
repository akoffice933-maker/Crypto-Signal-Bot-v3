# 🚀 Crypto Signal Bot v3 — Инструкция по развёртыванию

## 📋 Требования

**Минимальные:**
- CPU: 2 cores
- RAM: 2 GB
- Disk: 10 GB
- OS: Linux (Ubuntu 20.04+) или Windows Server
- Python: 3.11+

**Рекомендуемые:**
- CPU: 4 cores
- RAM: 4 GB
- Disk: 20 GB SSD
- Docker: 20.10+

---

## 📦 Вариант 1: Развёртывание через Docker (рекомендуется)

### **Шаг 1: Подготовка сервера**

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Проверка
docker --version
docker-compose --version
```

### **Шаг 2: Загрузка файлов проекта**

```bash
# Создание директории
sudo mkdir -p /opt/crypto-bot
sudo chown $USER:$USER /opt/crypto-bot

# Загрузка файлов (через git или scp)
git clone <your-repo-url> /opt/crypto-bot
# ИЛИ
scp -r ./bot_final/* user@server:/opt/crypto-bot/
```

### **Шаг 3: Настройка окружения**

```bash
cd /opt/crypto-bot

# Копирование примера
cp .env.example .env

# Редактирование .env
nano .env
```

**Заполните `.env`:**
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
TESTNET=false
DB_PATH=data/signals.db
LOG_LEVEL=INFO
ACCOUNT_BALANCE=10000
```

### **Шаг 4: Запуск бота**

```bash
cd /opt/crypto-bot

# Сборка и запуск
docker-compose up -d --build

# Проверка статуса
docker-compose ps
docker-compose logs -f
```

### **Шаг 5: Настройка автозапуска**

```bash
# Включение автозапуска
sudo systemctl enable docker
sudo systemctl restart docker

# Проверка
docker-compose ps
```

---

## 📦 Вариант 2: Развёртывание через Python (без Docker)

### **Шаг 1: Подготовка сервера**

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python 3.11+
sudo apt install -y python3.11 python3.11-venv python3-pip

# Проверка
python3 --version
pip3 --version
```

### **Шаг 2: Загрузка проекта**

```bash
# Создание директории
sudo mkdir -p /opt/crypto-bot
sudo chown $USER:$USER /opt/crypto-bot
cd /opt/crypto-bot

# Загрузка файлов
git clone <your-repo-url> .
# ИЛИ
# Загрузите файлы через SCP/FTP
```

### **Шаг 3: Создание виртуального окружения**

```bash
# Создание venv
python3 -m venv venv

# Активация
source venv/bin/activate

# Обновление pip
pip install --upgrade pip
```

### **Шаг 4: Установка зависимостей**

```bash
pip install -r requirements.txt
```

### **Шаг 5: Настройка окружения**

```bash
# Копирование .env
cp .env.example .env

# Редактирование
nano .env
```

**Заполните `.env`:**
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
TESTNET=false
DB_PATH=data/signals.db
LOG_LEVEL=INFO
ACCOUNT_BALANCE=10000
```

### **Шаг 6: Создание systemd сервиса**

```bash
sudo nano /etc/systemd/system/crypto-bot.service
```

**Содержимое файла:**
```ini
[Unit]
Description=Crypto Signal Bot v3
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/crypto-bot
Environment="PATH=/opt/crypto-bot/venv/bin"
ExecStart=/opt/crypto-bot/venv/bin/python main.py --log-level=INFO
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### **Шаг 7: Запуск сервиса**

```bash
# Перезагрузка systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable crypto-bot

# Запуск
sudo systemctl start crypto-bot

# Проверка статуса
sudo systemctl status crypto-bot

# Просмотр логов
sudo journalctl -u crypto-bot -f
```

---

## 🔧 Настройка брандмауэра

### **UFW (Ubuntu)**

```bash
# Установка
sudo apt install -y ufw

# Разрешение SSH
sudo ufw allow 22/tcp

# Разрешение API (опционально)
sudo ufw allow 8001/tcp

# Включение
sudo ufw enable
sudo ufw status
```

### **iptables**

```bash
# Разрешение портов
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8001 -j ACCEPT
```

---

## 🌐 Настройка Nginx (опционально, для доступа к API)

### **Шаг 1: Установка Nginx**

```bash
sudo apt install -y nginx
```

### **Шаг 2: Конфигурация**

```bash
sudo nano /etc/nginx/sites-available/crypto-bot
```

**Содержимое:**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### **Шаг 3: Активация**

```bash
# Создание симлинка
sudo ln -s /etc/nginx/sites-available/crypto-bot /etc/nginx/sites-enabled/

# Проверка конфигурации
sudo nginx -t

# Перезапуск Nginx
sudo systemctl restart nginx
```

### **Шаг 4: SSL (Let's Encrypt)**

```bash
# Установка Certbot
sudo apt install -y certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d your-domain.com

# Автообновление
sudo certbot renew --dry-run
```

---

## 📊 Мониторинг

### **Проверка статуса**

```bash
# Docker
docker-compose ps
docker-compose logs -f

# Systemd
sudo systemctl status crypto-bot
sudo journalctl -u crypto-bot -f

# Процессы
ps aux | grep python
netstat -tlnp | grep 8001
```

### **Логи**

```bash
# Просмотр логов бота
tail -f /opt/crypto-bot/logs/bot.log

# Docker логи
docker-compose logs -f bot
```

### **Метрики**

```bash
# Проверка API
curl http://localhost:8001/health

# Prometheus метрики
curl http://localhost:8001/metrics
```

---

## 🔄 Обновление

### **Docker**

```bash
cd /opt/crypto-bot

# Загрузка изменений
git pull

# Пересборка и перезапуск
docker-compose down
docker-compose up -d --build

# Проверка
docker-compose logs -f
```

### **Python**

```bash
cd /opt/crypto-bot

# Активация venv
source venv/bin/activate

# Загрузка изменений
git pull

# Обновление зависимостей
pip install -r requirements.txt --upgrade

# Перезапуск сервиса
sudo systemctl restart crypto-bot

# Проверка
sudo systemctl status crypto-bot
```

---

## 🛡️ Безопасность

### **1. Настройка .env**

```bash
# Установка правильных прав
chmod 600 /opt/crypto-bot/.env
chown root:root /opt/crypto-bot/.env
```

### **2. Ограничение доступа к API**

```nginx
# В nginx конфигурации
location / {
    allow 192.168.1.0/24;  # Разрешить только локальную сеть
    deny all;
    proxy_pass http://localhost:8001;
}
```

### **3. Fail2Ban**

```bash
# Установка
sudo apt install -y fail2ban

# Настройка
sudo nano /etc/fail2ban/jail.local
```

```ini
[sshd]
enabled = true
bantime = 3600
maxretry = 5
```

---

## 🆘 Troubleshooting

### **Бот не запускается**

```bash
# Проверка логов
sudo journalctl -u crypto-bot -n 50

# Проверка .env
cat /opt/crypto-bot/.env

# Проверка портов
netstat -tlnp | grep 8001
```

### **API недоступно**

```bash
# Проверка firewall
sudo ufw status

# Проверка Nginx
sudo nginx -t
sudo systemctl status nginx

# Проверка бота
curl http://localhost:8001/health
```

### **Telegram не работает**

```bash
# Проверка токена
grep TELEGRAM_BOT_TOKEN /opt/crypto-bot/.env

# Проверка связи с Telegram
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

### **Бэктест не работает**

```bash
# Проверка памяти
free -h

# Проверка диска
df -h

# Проверка логов
tail -f /opt/crypto-bot/logs/bot.log | grep -i backtest
```

---

## 📞 Поддержка

**Логи для отладки:**
```bash
# Полные логи
sudo journalctl -u crypto-bot --since today > bot_logs.txt

# Логи бота
tail -1000 /opt/crypto-bot/logs/bot.log > bot_app_logs.txt
```

**Контакты:**
- GitHub Issues: <your-repo>/issues
- Telegram: <your-support-channel>

---

## ✅ Чек-лист после развёртывания

- [ ] Бот запущен (`systemctl status crypto-bot`)
- [ ] API доступно (`curl http://localhost:8001/health`)
- [ ] Telegram работает (отправьте `/start` боту)
- [ ] Dashboard открывается (http://your-domain.com/dashboard)
- [ ] Логи пишутся (`tail -f logs/bot.log`)
- [ ] Автозапуск настроен (`systemctl is-enabled crypto-bot`)
- [ ] Брандмауэр настроен (`ufw status`)
- [ ] SSL сертификат установлен (если используется домен)

---

## 🎉 Готово!

Бот успешно развёрнут и готов к работе!

**Полезные команды:**

```bash
# Перезапуск
sudo systemctl restart crypto-bot

# Остановка
sudo systemctl stop crypto-bot

# Логи в реальном времени
sudo journalctl -u crypto-bot -f

# Статистика
curl http://localhost:8001/metrics
```
