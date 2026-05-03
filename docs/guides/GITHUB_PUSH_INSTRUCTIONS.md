# Инструкция по загрузке проекта на GitHub

Проект подготовлен к публикации. Выполнен первоначальный коммит. Теперь необходимо создать репозиторий на GitHub и загрузить код.

## Вариант 1: Создание репозитория через веб-интерфейс GitHub

1. Откройте https://github.com и войдите в аккаунт `akoffice933-maker`.
2. Нажмите кнопку **New repository** (зелёная кнопка в левом верхнем углу).
3. Заполните поля:
   - **Repository name**: `crypto-bot` (или другое название)
   - **Description**: `Crypto Signal Bot v3 - торговый бот для Binance Futures с алгоритмическим анализом ликвидности`
   - Выберите **Public** (или Private, если хотите закрытый репозиторий)
   - **Initialize this repository with**: НЕ добавляйте README, .gitignore или license — проект уже содержит эти файлы.
4. Нажмите **Create repository**.

После создания GitHub покажет инструкции для push существующего репозитория. Выполните следующие команды в терминале в папке проекта (`d:/bot_final`):

```bash
git remote add origin https://github.com/akoffice933-maker/crypto-bot.git
git branch -M master
git push -u origin master
```

Если репозиторий уже был добавлен ранее (уже есть remote origin), обновите URL:

```bash
git remote set-url origin https://github.com/akoffice933-maker/crypto-bot.git
git push -u origin master
```

## Вариант 2: Создание репозитория через GitHub CLI (если установлен)

Установите GitHub CLI (https://cli.github.com), затем выполните:

```bash
gh auth login
gh repo create crypto-bot --description "Crypto Signal Bot v3" --public --source=. --remote=origin --push
```

Эта команда создаст репозиторий, добавит remote и выполнит push.

## Вариант 3: Использование API с токеном (для автоматизации)

Если у вас есть персональный токен GitHub с правами `repo`, можно создать репозиторий с помощью curl:

```bash
curl -X POST -H "Authorization: token YOUR_GITHUB_TOKEN" \
  -d '{"name":"crypto-bot","description":"Crypto Signal Bot v3","private":false}' \
  https://api.github.com/user/repos
```

Затем выполните push как в варианте 1.

## После успешного push

1. Убедитесь, что код загружен: откройте https://github.com/akoffice933-maker/crypto-bot
2. Проверьте, что все файлы присутствуют, отсутствуют конфиденциальные данные (.env, базы данных, логи).
3. Настройте ветку по умолчанию (master) и при необходимости добавьте теги.

## Дополнительные шаги

- **Добавление тега версии**: если хотите отметить текущее состояние как релиз, выполните:
  ```bash
  git tag -a v1.0.0 -m "Initial release"
  git push origin v1.0.0
  ```
- **Настройка GitHub Actions**: в проекте уже есть базовый `.github/workflows`? Если нет, можно добавить CI/CD для автоматического тестирования.

## Проблемы и решения

- **Ошибка аутентификации**: если git запрашивает логин/пароль, используйте персональный токен доступа (PAT) вместо пароля. Или настройте SSH-ключи.
- **Репо уже существует**: если репозиторий с таким именем уже есть, измените имя или удалите старый репозиторий.
- **Большой размер файлов**: проект не содержит больших бинарных файлов, но если есть, убедитесь, что они в .gitignore.

После успешной загрузки проект будет полностью готовым продуктом с лицензией MIT и документацией.