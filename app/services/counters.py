from app.services.storage import mutate_store, read_store


async def increment_counter(name: str = "promos_issued"):
    def _fn(data):
        c = data.setdefault("counters", {})
        c[name] = c.get(name, 0) + 1
        return c[name]

    return await mutate_store(_fn)


async def get_counter(name: str = "promos_issued"):
    data = await read_store()
    return data.get("counters", {}).get(name, 0)


async def reset_counter(name: str = "promos_issued"):
    def _fn(data):
        data.setdefault("counters", {})[name] = 0
        return 0

    return await mutate_store(_fn)
