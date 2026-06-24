import aiosqlite
import json
from db.database import DB_PATH


async def create_duel(war_id: int, clan1_id: int, clan2_id: int,
                      player1_id: int, player2_id: int, chat_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO duels (war_id, clan1_id, clan2_id, player1_id, player2_id, chat_id, status)
            VALUES (?, ?, ?, ?, ?, ?, 'announced')
        """, (war_id, clan1_id, clan2_id, player1_id, player2_id, chat_id))
        await db.commit()
        return cur.lastrowid


async def get_duel(duel_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM duels WHERE id=?", (duel_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_active_duel_for_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM duels
            WHERE (player1_id=? OR player2_id=?)
            AND status IN ('announced', 'in_progress')
            ORDER BY id DESC LIMIT 1
        """, (user_id, user_id)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def set_duel_message(duel_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE duels SET message_id=? WHERE id=?", (message_id, duel_id))
        await db.commit()


async def mark_player_done(duel_id: int, player_num: int):
    col = f"player{player_num}_done"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE duels SET {col}=1 WHERE id=?", (duel_id,))
        # Проверяем оба готовы
        async with db.execute("SELECT player1_done, player2_done FROM duels WHERE id=?", (duel_id,)) as cur:
            row = await cur.fetchone()
        if row and row[0] == 1 and row[1] == 1:
            await db.execute("UPDATE duels SET status='completed', completed_at=datetime('now') WHERE id=?", (duel_id,))
        await db.commit()


async def set_duel_status(duel_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE duels SET status=? WHERE id=?", (status, duel_id))
        await db.commit()


# === СЕССИИ ИГРЫ ===

async def create_session(duel_id: int, user_id: int, clan_id: int, chat_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO duel_sessions (duel_id, user_id, clan_id, chat_id, status)
            VALUES (?, ?, ?, ?, 'choosing_mines')
        """, (duel_id, user_id, clan_id, chat_id))
        await db.commit()
        return cur.lastrowid


async def get_session(session_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM duel_sessions WHERE id=?", (session_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_active_session_for_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM duel_sessions
            WHERE user_id=? AND status NOT IN ('done', 'lost')
            ORDER BY id DESC LIMIT 1
        """, (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_session(session_id: int, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [session_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE duel_sessions SET {sets} WHERE id=?", vals)
        await db.commit()


# === ОЧЕРЕДЬ ===

async def get_queue(clan_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM duel_queue WHERE clan_id=? ORDER BY rowid",
            (clan_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def add_to_queue(clan_id: int, user_id: int, attempts: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO duel_queue (clan_id, user_id, attempts_left)
            VALUES (?, ?, ?)
            ON CONFLICT(clan_id, user_id) DO UPDATE SET attempts_left = attempts_left + ?
        """, (clan_id, user_id, attempts, attempts))
        await db.commit()


async def decrement_attempts(clan_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE duel_queue SET attempts_left = attempts_left - 1
            WHERE clan_id=? AND user_id=?
        """, (clan_id, user_id))
        await db.execute("""
            DELETE FROM duel_queue WHERE clan_id=? AND user_id=? AND attempts_left <= 0
        """, (clan_id, user_id))
        await db.commit()


async def get_next_player(clan_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT dq.*, cm.username, cm.full_name
            FROM duel_queue dq
            JOIN clan_members cm ON cm.user_id = dq.user_id
            WHERE dq.clan_id=? AND dq.attempts_left > 0
            ORDER BY dq.rowid LIMIT 1
        """, (clan_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None
