import asyncio
import gspread
from sqlalchemy import select
from app.services.db import SessionLocal, Promo
from app.config import settings

gc = gspread.service_account(filename="creds.json")

async def update_table():
    sh = gc.open_by_key(settings.SHEET_ID).sheet1
    data = sh.get_all_records()  # читаем текущие значения

    # Сначала добавляем/удаляем промокоды в БД
    async with SessionLocal() as session:
        for row in data:
            row = {k.lower(): v for k, v in row.items()}  # нормализуем ключи
            add_code = str(row.get("добавление") or "").strip()
            if add_code:
                promo = await session.get(Promo, add_code)
                if not promo:
                    session.add(Promo(code=add_code))

            remove_code = str(row.get("удаление") or "").strip()
            if remove_code:
                promo = await session.get(Promo, remove_code)
                if promo:
                    await session.delete(promo)
        await session.commit()

        # Берём активные и занятые промокоды
        result_active = await session.execute(select(Promo).where(Promo.user_id.is_(None)))
        active_codes = [p.code for p in result_active.scalars().all()]

        result_taken = await session.execute(select(Promo).where(Promo.user_id.is_not(None)))
        taken = result_taken.scalars().all()
        taken_rows = [[p.code, p.user_id] for p in taken]

    # Подготавливаем новые данные для листа
    header = ["Добавление", "Удаление", "Активные", "Готовые", "ID пользователя"]
    n = max(len(active_codes), len(taken_rows))
    add_col = [""] * n
    remove_col = [""] * n
    active_col = active_codes + [""] * (n - len(active_codes))
    ready_col = [row[0] for row in taken_rows] + [""] * (n - len(taken_rows))
    user_col = [row[1] for row in taken_rows] + [""] * (n - len(taken_rows))

    rows = list(zip(add_col, remove_col, active_col, ready_col, user_col))

    # Очищаем лист и вставляем новую таблицу
    sh.clear()
    sh.append_row(header)
    if rows:
        sh.append_rows(rows)


async def periodic_update():
    while True:
        await update_table()
        await asyncio.sleep(600)
