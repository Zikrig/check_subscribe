import logging

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

MAX_API_URL = "https://platform-api.max.ru"


async def is_user_subscribed(chat_id: int, user_id: int) -> bool:
    url = f"{MAX_API_URL}/chats/{chat_id}/members"
    params = {"user_ids": str(user_id)}
    headers = {"Authorization": settings.BOT_TOKEN}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        "Subscription check failed: chat_id=%s user_id=%s status=%s body=%s",
                        chat_id,
                        user_id,
                        resp.status,
                        body[:200],
                    )
                    return False

                data = await resp.json()
                members = data.get("members") or []
                return len(members) > 0
    except Exception:
        logger.exception(
            "Subscription check error: chat_id=%s user_id=%s",
            chat_id,
            user_id,
        )
        return False
