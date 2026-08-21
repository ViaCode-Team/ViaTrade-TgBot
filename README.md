# ViaTrade Telegram Bot

Сервис получает уведомления ViaTrade из Redis Stream и доставляет их через Telegram.

## Запуск

1. Скопируйте `.env.example` в `.env` и заполните секреты.
2. Выполните `uv sync`.
3. Запустите `uv run viatradetgbot`.

Бот использует Redis DB `1`, stream `telegram:notifications` и Consumer Group
`viatrade-telegram-bot`. Сообщение подтверждается только после успешной доставки в Telegram.
