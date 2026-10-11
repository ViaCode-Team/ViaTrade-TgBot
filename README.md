# ViaTrade Telegram Bot

Сервис привязывает Telegram-аккаунты ViaTrade и доставляет напоминания через
автогенерируемый клиент API из `swagger-tgbot.yaml`.

## Запуск

1. Скопируйте `.env.example` в `.env` и заполните секреты.
2. Выполните `uv sync`.
3. Запустите `uv run viatradetgbot`.

Для локального ASP.NET Core backend с самоподписанным HTTPS-сертификатом
экспортируйте публичный сертификат в PEM (PowerShell):

```powershell
New-Item -ItemType Directory -Path .certs -Force
dotnet dev-certs https --export-path "$PWD/.certs/backend-localhost.pem" --format PEM
```

Добавьте в `.env` строку `BACKEND_CA_BUNDLE=.certs/backend-localhost.pem`.
Проверка сертификата и имени сервера остаётся включённой. Без этой настройки
используется стандартное доверие HTTPX. Для собственного центра сертификации укажите
путь к его PEM bundle; отсутствующий или некорректный файл приводит к ошибке при запуске.
После замены сертификата backend повторите экспорт. Каталог `.certs/` исключён из Git.

Повторные сообщения из одного чата ограничиваются интервалом
`TELEGRAM_MESSAGE_RATE_LIMIT_SECONDS` (по умолчанию — 1 секунда).

Backend добавляет готовые к отправке напоминания в Redis Stream. Бот читает их через
Redis consumer group с блокирующим ожиданием новых записей, поэтому не выполняет
периодических запросов к backend. После успешной отправки в Telegram бот подтверждает
доставку через `PUT /api/v1/internal/tgbot/reminders/{reminderId}/delivery` и
подтверждает запись в Stream. Неподтверждённые сообщения возвращаются в обработку после
тайм-аута периодической задачей APScheduler, а сообщения с некорректным форматом
переносятся в `<NOTIFICATION_STREAM>:dead-letter`. Dishka создаёт зависимости уровня
приложения и внедряет контракт backend API прямо в aiogram-обработчик `/start`.

Формат сообщений определяет [AsyncAPI-контракт](docs/notification-stream.asyncapi.yaml):
backend публикует поля `notification_id`, `type`, `user_id`, `chat_id`, `payload`
и `created_at`, где `payload` — JSON. Этот формат без версии обрабатывается как
версия схемы 1. Также поддерживается единственное поле `message` с JSON уведомления
и явным `schemaVersion: 1`. Тикер инструмента передаётся в поле `instrumentTicker`.
Бот использует `chat_id` / `chatId` как идентификатор Telegram-чата;
`userId` передаётся backend при подтверждении доставки. Изменить API-клиент после
обновления HTTP-контракта можно командой `uv run generate-api`.
