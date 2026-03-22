"""
Подтверждение callback (POST /answers) без повторной отправки старых attachments.

MAX API отклоняет тело без полей `message` и `notification` (proto.payload).
`event.answer()` в maxapi подставляет старые attachments — затирает свежий message.edit.
Поэтому: message=None + минимальное notification (некоторые версии API отвергают пустое тело и «невидимые» символы).
"""

SILENT_NOTIFICATION = " "


async def send_callback_ack(bot, callback_id: str, *, notification: str | None = None) -> None:
    await bot.send_callback(
        callback_id=callback_id,
        message=None,
        notification=notification if notification is not None else SILENT_NOTIFICATION,
    )
