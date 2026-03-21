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
| `CHANNELS` | Список каналов: `chat_id:username,...` — **ID чатов каналов в MAX** (не Telegram). Укажите ссылки на каналы в БД (`link`) или задайте корректный URL в настройках. |
| `ADMINS` | ID администраторов в MAX (через запятую) |
| Остальные | Как раньше: Postgres (`POSTGRES_*`), Google Sheets (`SHEET_ID`), и т.д. |

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
