# Архитектура: адаптированная слоистая архитектура

## Обзор

Сервис развёртывается как один асинхронный процесс и имеет небольшой набор чётко
разделённых обязанностей: принимает Telegram-апдейты, читает уведомления из Redis Stream
и вызывает внутренний backend API. Для такого размера и уровня доменной сложности
подходит слоистая архитектура, адаптированная к пакетам текущего приложения, а не к
абстрактным папкам `controllers/` и `services/`.

`app.py` служит composition root: он создаёт конкретные зависимости и управляет их
жизненным циклом. Входной слой находится в `bot/`; процесс доставки и его контракты — в
`notifications/`; конкретные интеграции с Telegram, Redis и backend API расположены на
внешней границе. Это позволяет тестировать процесс доставки с небольшими fake-объектами,
не поднимая Telegram, Redis или HTTP-сервер.

## Обоснование решения

- **Тип проекта:** отдельный Telegram-сервис с одним процессом доставки уведомлений.
- **Стек:** Python, aiogram 3, Redis Streams, httpx, pydantic-settings и OpenAPI-клиент.
- **Ключевой фактор:** нужны понятные границы интеграций и надёжная асинхронная обработка,
  но выделение микросервисов или строгих bounded contexts добавило бы лишнюю сложность.

## Структура каталогов

```text
src/viatradetgbot/
├── __main__.py                     # запуск: настройки, logging, asyncio
├── app.py                           # composition root и lifecycle
├── config.py                        # конфигурация из окружения
├── logging_config.py                # общая настройка логирования
├── bot/                             # входной Telegram-слой
│   ├── handlers/                    # команды и обработка ошибок
│   ├── middlewares/                 # logging и throttling
│   ├── bot.py                       # Dispatcher и polling
│   ├── telegram_links.py            # входной контракт привязки аккаунта
│   └── notification_delivery.py     # исходящий Telegram-адаптер
├── notifications/                   # application-слой доставки
│   ├── consumer.py                  # оркестрация обработки Stream-сообщения
│   ├── handlers.py                  # логика типа уведомления reminder
│   ├── models.py                    # схема сообщения и payload
│   ├── contracts.py                 # порты Redis, доставки и настроек
│   ├── store.py                     # Redis-операции для consumer-а
│   └── redis_client.py              # адаптер типов redis-py
├── integrations/
│   └── backend_api.py               # HTTP-адаптер внутреннего backend API
├── backend_api/gen/                 # генерируемый OpenAPI-клиент; не редактировать
└── scripts/
    └── generate_backend_api.py      # перегенерация клиента из OpenAPI
```

## Правила зависимостей

```text
__main__ → app (composition root)
app → bot / notifications / integrations / Redis-клиент
bot.handlers → контракты application-слоя
notifications.consumer → Protocol-контракты и обработчики уведомлений
notifications.store → RedisNotificationClient (Protocol) → redis.asyncio
integrations.backend_api → OpenAPI-клиент → httpx
bot.notification_delivery → aiogram Bot
```

- ✅ Обработчики `bot/` могут зависеть от контрактов (`TelegramAccountLinker`) и получать
  их от Dispatcher через DI aiogram.
- ✅ `NotificationConsumer` может зависеть только от `NotificationStoreProtocol`,
  `NotificationDelivery` и `NotificationHandler`, переданных в конструктор.
- ✅ Concrete adapters могут зависеть от библиотек и сгенерированного клиента.
- ❌ Обработчики Telegram не должны создавать `BackendApi`, Redis-клиент или bot session.
- ❌ `notifications/` не должен импортировать aiogram или конкретный `BackendApi` ради
  вызова их методов: добавляйте либо расширяйте контракт.
- ❌ Не редактируйте файлы `backend_api/gen/`; источником изменений является
  `swagger-tgbot.yaml`.

## Взаимодействие слоёв

1. `__main__.py` создаёт `Settings`, настраивает logging и открывает `App` как
   асинхронный контекстный менеджер.
2. `App` создаёт Redis- и HTTP-адаптеры, Telegram-бота, `NotificationStore` и
   `NotificationConsumer`, затем запускает consumer отдельной задачей.
3. Aiogram передаёт `TelegramAccountLinker` в `/start`-обработчик; обработчик валидирует
   контекст чата, вызывает контракт и отображает пользователю результат.
4. Consumer валидирует Stream-сообщение, берёт блокировку, выполняет дедупликацию,
   доставляет уведомление, подтверждает его в backend API и только затем делает `ack`.
5. Ошибки схемы и постоянный отказ Telegram попадают в dead-letter stream; временные
   ошибки внешней инфраструктуры логируются и оставляют сообщение доступным для повтора.

## Ключевые принципы

1. **Тонкие входные обработчики.** Обработчики команд и middleware решают только задачи
   Telegram: проверяют входные данные, вызывают контракт и формируют ответ.
2. **Инверсия зависимостей на границах.** Для Redis, доставки и backend-подтверждения
   определяйте `Protocol`, а конкретную реализацию подключайте в `App`.
3. **Надёжность важнее скорости ack.** Нельзя подтверждать Stream-сообщение до успешного
   подтверждения доставки в backend API.
4. **Безопасные observability-данные.** Логируйте идентификаторы операций, но не токены
   привязки, пароли или заголовки авторизации.
5. **Контракт прежде реализации.** Изменения HTTP- и Stream-форматов начинаются со
   спецификаций; сгенерированный API-клиент обновляется командой генерации.

## Примеры кода

### Входной обработчик зависит от контракта

```python
class TelegramAccountLinker(Protocol):
    async def link_telegram(self, token: str, telegram_id: str) -> TelegramLinkResult: ...


@router.message(CommandStart())
async def handle_start_command(
    message: Message,
    command: CommandObject,
    account_linker: TelegramAccountLinker,
) -> None:
    if not command.args:
        await message.answer("Откройте бота по ссылке из ViaTrade для привязки аккаунта.")
        return

    result = await account_linker.link_telegram(command.args, str(message.chat.id))
    await message.answer(result.user_message)
```

### Consumer зависит от порта доставки

```python
class NotificationDelivery(Protocol):
    async def send_text(self, chat_id: str, text: str) -> None: ...


class ReminderNotificationHandler:
    async def deliver(
        self, notification: NotificationEnvelope, delivery: NotificationDelivery
    ) -> None:
        payload = self._parse_payload(notification)
        await delivery.send_text(notification.chat_id, f"Напоминание:\n{payload.text}")
```

## Организация существующего кода

- **Новые возможности:** следуют правилам этого документа; новые интеграции получают
  контракт и конкретный адаптер, а wiring остаётся в `App`.
- **Существующий код:** сохраняет текущие пакеты и имена. Не рефакторируйте несвязанные
  модули только ради переименования каталогов.
- **Совместимость:** при расширении старого кода сначала добавляйте чистую границу через
  `Protocol` или небольшую функцию-адаптер, затем подключайте её в composition root.

## Антипаттерны

- ❌ Создавать HTTP-, Redis- или Telegram-клиенты внутри handlers или consumer-а.
- ❌ Подтверждать Redis Stream-сообщение до вызова backend API или игнорировать pending
  сообщения consumer group.
- ❌ Поглощать `asyncio.CancelledError`, забывать освобождать lock в `finally` или
  обрабатывать постоянный отказ Telegram как бесконечную повторную попытку.
- ❌ Вручную менять OpenAPI-клиент либо логировать токен `/start` и секреты конфигурации.
