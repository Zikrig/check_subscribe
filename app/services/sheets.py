import asyncio
import gspread

from app.config import settings
from app.services.storage import mutate_store

gc = gspread.service_account(filename="creds.json")


async def update_table():
    sh = gc.open_by_key(settings.SHEET_ID).sheet1
    data = sh.get_all_records()

    def _sync_promos(store):
        for row in data:
            row = {k.lower(): v for k, v in row.items()}
            add_code = str(row.get("добавление") or "").strip()
            if add_code:
                if add_code not in store["promos"]:
                    store["promos"][add_code] = None

            remove_code = str(row.get("удаление") or "").strip()
            if remove_code and remove_code in store["promos"]:
                del store["promos"][remove_code]

        active_codes = [c for c, uid in store["promos"].items() if uid is None]
        taken_rows = [[c, uid] for c, uid in store["promos"].items() if uid is not None]
        return active_codes, taken_rows

    active_codes, taken_rows = await mutate_store(_sync_promos)

    header = ["Добавление", "Удаление", "Активные", "Готовые", "ID пользователя"]
    n = max(len(active_codes), len(taken_rows))
    add_col = [""] * n
    remove_col = [""] * n
    active_col = active_codes + [""] * (n - len(active_codes))
    ready_col = [row[0] for row in taken_rows] + [""] * (n - len(taken_rows))
    user_col = [row[1] for row in taken_rows] + [""] * (n - len(taken_rows))

    rows = list(zip(add_col, remove_col, active_col, ready_col, user_col))

    sh.clear()
    sh.append_row(header)
    if rows:
        sh.append_rows(rows)


async def periodic_update():
    while True:
        await update_table()
        await asyncio.sleep(600)
