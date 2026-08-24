# AGENTS.md

> Поддерживайте этот файл актуальным при существенном изменении структуры проекта.

## Обзор проекта

ViaTrade Telegram Bot — Python-сервис для привязки Telegram-аккаунтов ViaTrade и
доставки напоминаний из Redis Stream через внутренний backend API. Назначение,
ограничения и требования описаны в `.ai-factory/DESCRIPTION.md`.

## Технологический стек

- **Язык:** Python 3.14.7+.
- **Сборка и зависимости:** uv, `uv_build`.
- **Telegram:** aiogram 3.
- **Очередь и идемпотентность:** Redis Streams, consumer groups и `redis.asyncio`.
- **HTTP и конфигурация:** httpx, pydantic-settings.
- **Контракт backend API:** OpenAPI 3.0, `openapi-python-client`.
- **База данных и ORM:** не используются.

## Структура проекта

```text
.
├── .agents/                         # локальные навыки и инструкции для агентов
├── .ai-factory/                     # контекст, правила и архитектура AI Factory
├── docs/
│   └── notification-stream.asyncapi.yaml # AsyncAPI-контракт Redis Stream
├── src/
│   └── viatradetgbot/
│       ├── __main__.py              # консольная точка входа
│       ├── app.py                   # composition root и lifecycle приложения
│       ├── config.py                # типизированные настройки из .env
│       ├── logging_config.py        # настройка стандартного logging
│       ├── backend_api/gen/         # автогенерируемый клиент OpenAPI
│       ├── bot/                     # aiogram: lifecycle, команды, middleware и доставка
│       │   ├── handlers/            # /start и обработчики ошибок
│       │   ├── middlewares/         # логирование и throttling обновлений
│       │   ├── bot.py               # настройка Dispatcher и polling
│       │   └── notification_delivery.py # Telegram-адаптер доставки
│       ├── integrations/
│       │   └── backend_api.py       # адаптер внутреннего backend API
│       ├── notifications/           # Redis Stream consumer и доставка уведомлений
│       │   ├── contracts.py         # Protocol-контракты Redis и доставки
│       │   ├── consumer.py          # обработка, recovery и ack сообщений
│       │   ├── handlers.py          # обработчики типов уведомлений
│       │   ├── models.py            # Pydantic-модели stream-сообщений
│       │   ├── redis_client.py      # типизированный адаптер redis-py
│       │   └── store.py             # Redis Streams, дедупликация и DLQ
│       └── scripts/
│           └── generate_backend_api.py # генерация OpenAPI-клиента
├── tests/                           # асинхронные unit-тесты
├── swagger-tgbot.yaml               # OpenAPI-спецификация backend API
├── .env.example                     # безопасный шаблон окружения
├── README.md                        # запуск и контракты сервиса
├── pyproject.toml                   # зависимости, Ruff и консольные команды
└── uv.lock                          # lock-файл зависимостей uv
```

## Ключевые точки входа

| Файл | Назначение |
|---|---|
| `src/viatradetgbot/__main__.py` | Загружает настройки, настраивает логирование и запускает приложение. |
| `src/viatradetgbot/app.py` | Собирает адаптеры, запускает consumer Redis Stream и управляет закрытием ресурсов. |
| `src/viatradetgbot/bot/bot.py` | Создаёт aiogram-бота, Dispatcher, middleware и обработчики. |
| `src/viatradetgbot/scripts/generate_backend_api.py` | Генерирует клиент backend API из `swagger-tgbot.yaml`. |
| `pyproject.toml` | Описывает пакет, версию Python, зависимости и команды `viatradetgbot` и `generate-api`. |

## Документация и контракты

| Документ | Путь | Описание |
|---|---|---|
| README | `README.md` | Запуск сервиса, поток доставки и порядок генерации API-клиента. |
| Шаблон окружения | `.env.example` | Переменные окружения без реальных секретов. |
| OpenAPI-спецификация | `swagger-tgbot.yaml` | Контракт внутреннего backend API. |
| AsyncAPI-спецификация | `docs/notification-stream.asyncapi.yaml` | Формат сообщений Redis Stream для уведомлений. |
| Описание проекта | `.ai-factory/DESCRIPTION.md` | Цель, стек и нефункциональные требования. |

## Файлы контекста AI

| Файл | Назначение |
|---|---|
| `AGENTS.md` | Карта структуры и правила работы с проектом. |
| `.ai-factory/DESCRIPTION.md` | Краткая спецификация проекта. |
| `.ai-factory/ARCHITECTURE.md` | Практические правила адаптированной слоистой архитектуры. |
| `.ai-factory/rules/base.md` | Автоматически выявленные соглашения кода. |

## Правила для агентов

- Выполняйте составные команды Git отдельными шагами, чтобы каждый шаг можно было проверить.
  - Неправильно: `git checkout master && git pull`.
  - Правильно: сначала `git checkout master`, затем, после настройки `origin`, `git pull origin master`.
- Не добавляйте токены, пароли и другие секреты в исходный код или репозиторий.
- Не редактируйте `src/viatradetgbot/backend_api/gen/` вручную: обновляйте
  `swagger-tgbot.yaml` и запускайте `uv run generate-api`.
- После изменения Python-кода или конфигурации Ruff выполняйте `uv run ruff check --fix`
  и повторяйте проверку до чистого результата.
