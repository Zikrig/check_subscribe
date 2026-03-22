from app.services.storage import mutate_store


async def get_or_assign_promo(user_id: int) -> str | None:
    def _fn(data) -> str | None:
        promos = data["promos"]
        for code, uid in promos.items():
            if uid == user_id:
                return code
        for code, uid in promos.items():
            if uid is None:
                promos[code] = user_id
                c = data.setdefault("counters", {})
                c["promos_issued"] = c.get("promos_issued", 0) + 1
                return code
        return None

    return await mutate_store(_fn)
