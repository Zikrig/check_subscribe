# Бот для мессенджера MAX

## Документация платформы

- Подготовка и настройка бота: [dev.max.ru — чат-боты](https://dev.max.ru/docs/chatbots/bots-coding/prepare)
- Официальная библиотека (JS/TS): [@maxhub/max-bot-api](https://www.npmjs.com/package/@maxhub/max-bot-api)
- HTTP API: [dev.max.ru/docs-api](https://dev.max.ru/docs-api)

## Этот проект (Python)

Используется библиотека **[maxapi](https://pypi.org/project/maxapi/)** (сообщество; примеры в [документации maxapi](https://love-apples.github.io/maxapi/)).

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `MAX_BOT_TOKEN` или `BOT_TOKEN` | Токен бота из кабинета MAX |
| `CHANNELS` | Начальные каналы только **до первого появления** `store.json`: `chat_id:username,...`. Дальше список хранится в JSON и правится через `/channels`; переменная для уже созданного файла не подмешивается. |
| `ADMINS` | ID администраторов в MAX (через запятую) |
| `DATA_JSON_PATH` | Путь к JSON-хранилищу (локально по умолчанию `data/store.json`). В `docker-compose` данные лежат в томе `bot_data` → `/app/data/store.json`, пересборка образа их не стирает |
| Остальное | Google Sheets (`SHEET_ID`), `creds.json` для таблицы — как раньше |

## Проверка подписок

Бот вызывает API `GET /chats/{chat_id}/members` (в `maxapi`: `bot.get_chat_member(chat_id, user_id)`).  
Чтобы проверка работала, бот должен иметь права в соответствующих каналах/чатах (см. заметки в документации MAX про права бота).

## Запуск

```bash
pip install -r requirements.txt
# задайте MAX_BOT_TOKEN и .env
python bot.py
```

В Docker образе используется Python 3.11 (как в `Dockerfile`).

### Данные в Docker

Каталог `/app/data` смонтирован отдельным томом `bot_data`, файл `store.json` в нём **не** совпадает с `./data/store.json` на хосте (том перекрывает bind-монтирование проекта). Бэкап: `docker volume inspect` / экспорт тома.
