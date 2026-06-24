import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot

from config import DUEL_INTERVAL_HOURS, WAR_DURATION_DAYS, STARTING_AL
from db.clan_queries import get_all_clans, get_clan_by_id, get_active_war, update_clan_al
from db.duel_queries import create_duel, add_to_queue
from game.matchmaking import get_next_duel_pair
from handlers.duel import announce_duel

import aiosqlite
from db.database import DB_PATH

logger = logging.getLogger(__name__)

# ID группового чата — бот сам запомнит когда получит первое сообщение из группы
GROUP_CHAT_ID = None


async def save_group_chat(chat_id: int):
    global GROUP_CHAT_ID
    GROUP_CHAT_ID = chat_id


async def war_scheduler(bot: Bot):
    """Основной планировщик — запускается в фоне."""
    logger.info("Планировщик запущен")
    while True:
        try:
            await _tick(bot)
        except Exception as e:
            logger.error(f"Ошибка планировщика: {e}")
       await asyncio.sleep(60)  # Проверяем каждую минуту


async def _tick(bot: Bot):
    global GROUP_CHAT_ID
    if not GROUP_CHAT_ID:
        return

    war = await get_active_war()
    if not war:
        return

    # Проверяем не закончилась ли война
    started = datetime.fromisoformat(war["started_at"])
    if datetime.now() - started > timedelta(days=WAR_DURATION_DAYS):
        await _end_war(bot, war)
        return

    # Проверяем время последней дуэли
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT scheduled_at FROM duels
            WHERE war_id=?
            ORDER BY id DESC LIMIT 1
        """, (war["id"],)) as cur:
            row = await cur.fetchone()

    if row:
        last_duel_time = datetime.fromisoformat(row[0])
        if datetime.now() - last_duel_time < timedelta(hours=DUEL_INTERVAL_HOURS):
            return  # Ещё рано

    # Подбираем пару
    result = await get_next_duel_pair(war["id"])
    if not result:
        logger.info("Нет пары для дуэли")
        return

    clan1, clan2, player1_id, player2_id = result

    # Создаём дуэль в БД
    duel_id = await create_duel(war["id"], clan1["id"], clan2["id"], player1_id, player2_id, GROUP_CHAT_ID)

    # Анонсируем
    await announce_duel(bot, GROUP_CHAT_ID, duel_id, clan1, clan2, player1_id, player2_id)

    logger.info(f"Дуэль #{duel_id} анонсирована: {clan1['name']} vs {clan2['name']}")


async def _end_war(bot: Bot, war: dict):
    """Завершает войну и объявляет победителя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE wars SET is_active=0, ended_at=datetime('now') WHERE id=?", (war["id"],))
        await db.commit()

    if not GROUP_CHAT_ID:
        return

    clans = await get_all_clans(war["id"])
    if not clans:
        return

    sorted_clans = sorted(clans, key=lambda c: c["al"], reverse=True)
    winner = sorted_clans[0]

    medals = ["🥇", "🥈", "🥉"]
    lines = [
        "🏁 <b>ВОЙНА КЛАНОВ ЗАВЕРШЕНА!</b>\n",
        f"👑 Победитель: <b>{winner['name']}</b> с {winner['al']} Al!\n",
        "📊 <b>Итоговая таблица:</b>"
    ]
    for i, c in enumerate(sorted_clans):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} {c['name']} — {c['al']} Al")

    await bot.send_message(GROUP_CHAT_ID, "\n".join(lines), parse_mode="HTML")

    # Сбрасываем Al для новой войны
    async with aiosqlite.connect(DB_PATH) as db:
        new_war_cur = await db.execute("INSERT INTO wars (is_active) VALUES (1)")
        new_war_id = new_war_cur.lastrowid
        await db.execute(f"UPDATE clans SET al={STARTING_AL}, war_id=?, current_win_streak=0 WHERE 1=1", (new_war_id,))
        await db.commit()

    await bot.send_message(
        GROUP_CHAT_ID,
        f"🔄 <b>Новая война кланов началась!</b>\nВсе кланы стартуют с {STARTING_AL} Al.\nУдачи всем! ⚔️",
        parse_mode="HTML"
    )
