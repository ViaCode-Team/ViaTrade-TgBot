# ViaTrade Telegram Bot

Сервис привязывает Telegram-аккаунты ViaTrade и доставляет напоминания через
автогенерируемый клиент API из `swagger-tgbot.yaml`.

## Запуск

1. Скопируйте `.env.example` в `.env` и заполните секреты.
2. Выполните `uv sync`.
3. Запустите `uv run viatradetgbot`.

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
каждая запись Stream содержит единственное поле `message`, значение которого — JSON
уведомления. Бот использует `chatId` из уведомления как идентификатор Telegram-чата;
`userId` передаётся backend при подтверждении доставки. Изменить API-клиент после
обновления HTTP-контракта можно командой `uv run generate-api`.
