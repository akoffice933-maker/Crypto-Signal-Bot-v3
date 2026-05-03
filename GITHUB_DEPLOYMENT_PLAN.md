# План деплоя проекта на GitHub

## Цель
Развернуть Crypto Signal Bot v3 на GitHub под аккаунтом `akoffice933-maker` с лицензией, сделав его полностью готовым продуктом.

## Шаги выполнения

### 1. Подготовка проекта к публикации
- [ ] Создать `.gitignore` для исключения конфиденциальных данных и временных файлов
- [ ] Проверить и обновить `.env.example` с placeholder-ами
- [ ] Удалить реальные API ключи из `.env` (не коммитить)
- [ ] Очистить временные файлы и директории
- [ ] Проверить наличие других конфиденциальных данных

### 2. Создание необходимых файлов
- [ ] **README.md** - основная документация проекта
- [ ] **LICENSE** - лицензионный файл (MIT рекомендовано)
- [ ] **requirements.txt** - зависимости Python (уже есть)
- [ ] **setup.py** или **pyproject.toml** - для установки как пакета
- [ ] **CONTRIBUTING.md** - руководство для контрибьюторов
- [ ] **CHANGELOG.md** - история изменений

### 3. Очистка проекта
- [ ] Удалить временные файлы: `web_server_stdin.tmp`, `bot_final.zip`
- [ ] Очистить логи: `logs/`
- [ ] Очистить результаты: `results/`
- [ ] Очистить тестовые временные файлы: `tests/_tmp_*/`
- [ ] Проверить базы данных: `data/*.db`, `data/*.db-*`

### 4. Настройка git
- [ ] Инициализировать git репозиторий: `git init`
- [ ] Настроить ветки: `main`, `develop`
- [ ] Создать первоначальный коммит
- [ ] Добавить remote: `git remote add origin https://github.com/akoffice933-maker/crypto-signal-bot-v3.git`

### 5. Создание репозитория на GitHub
- [ ] Создать новый репозиторий на GitHub под именем `crypto-signal-bot-v3`
- [ ] Настроить visibility (public/private)
- [ ] Настроить ветку по умолчанию (main)
- [ ] Настроить .gitignore, license, README при создании

### 6. Загрузка проекта
- [ ] Запушить код: `git push -u origin main`
- [ ] Создать тег первого релиза: `v1.0.0`
- [ ] Настроить GitHub Actions для CI/CD (опционально)

### 7. Документация
- [ ] Обновить README.md с:
  - Описанием проекта
  - Быстрым стартом
  - Конфигурацией
  - Примером использования
  - Лицензией
- [ ] Создать документацию по API (если есть)
- [ ] Добавить примеры конфигурации

### 8. Проверка
- [ ] Проверить что проект запускается с чистого окружения
- [ ] Проверить установку: `pip install -r requirements.txt`
- [ ] Проверить запуск: `python main.py --help`
- [ ] Проверить тесты: `pytest tests/`

## Файлы для исключения из git (.gitignore)

```
# Конфиденциальные данные
.env
.env.local

# Логи
logs/
*.log

# Базы данных
*.db
*.db-shm
*.db-wal
data/signals.db

# Временные файлы
__pycache__/
*.pyc
.pytest_cache/
tests/_tmp_*/

# IDE
.vscode/
.idea/

# Системные
.DS_Store
Thumbs.db

# Архивы
*.zip
```

## Лицензия

Рекомендуемые лицензии:
1. **MIT** - простая, разрешительная
2. **Apache 2.0** - с патентной защитой
3. **GPL v3** - копилефт

Для торгового бота рекомендуется MIT или Apache 2.0.

## Структура репозитория

```
crypto-signal-bot-v3/
├── README.md
├── LICENSE
├── requirements.txt
├── setup.py
├── .gitignore
├── .env.example
├── main.py
├── config/
├── engine/
├── strategies/
├── database/
├── data/
├── telegram/
├── web/
├── tests/
├── scripts/
└── deploy/
```

## Команды для выполнения

```bash
# 1. Подготовка
rm -f web_server_stdin.tmp bot_final.zip
rm -rf logs/* results/* tests/_tmp_*/

# 2. Создание файлов
touch .gitignore LICENSE README.md

# 3. Git инициализация
git init
git add .
git commit -m "Initial commit: Crypto Signal Bot v3"

# 4. Связь с GitHub
git remote add origin https://github.com/akoffice933-maker/crypto-signal-bot-v3.git
git push -u origin main
```

## Временная шкала

1. **День 1**: Подготовка проекта и создание файлов
2. **День 2**: Очистка и настройка git
3. **День 3**: Создание репозитория и загрузка
4. **День 4**: Документация и проверка

## Риски и решения

1. **Конфиденциальные данные в истории коммитов** - использовать `git filter-branch` или `BFG Repo-Cleaner`
2. **Большой размер репозитория** - исключить бинарные файлы, использовать git LFS
3. **Зависимости от внешних API** - предоставить mock данные для тестов
4. **Сложность настройки** - создать подробную документацию и скрипты установки