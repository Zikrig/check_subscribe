from app.services.storage import read_store


async def get_replic(name: str) -> str:
    data = await read_store()
    replics = data.get("replics", {})
    if name in replics:
        return replics[name]

    default_replics = {
        "start_message": "Привет! Подпишись на наши каналы:",
        "success_message": "Все подписки выполнены!",
        "not_subbed_message": "Похоже, ты ещё не подписан на все каналы. Проверь и нажми кнопку снова.",
        "promo_followup_message": "",
        "promo_followup_link_button_text": "Перейти",
        "bot_started_description": "",
    }
    return default_replics.get(name, "")
