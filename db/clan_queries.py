import aiosqlite
from db.database import DB_PATH


async def create_clan(name: str, deviz: str, avatar_file_id: str | None, creator_id: int, war_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute(
                "INSERT INTO clans (name, deviz, avatar_file_id, creator_id, war_id, al) VALUES (?, ?, ?, ?, ?, 100)",
                (name, deviz, avatar_file_id, creator_id, war_id)
            )
            await db.commit()
            return cur.lastrowid
        except aiosqlite.IntegrityError:
            return None


async def get_clan_by_id(clan_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM clans WHERE id=?", (clan_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_clan_by_name(name: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM clans WHERE name=?", (name,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_clans(war_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM clans WHERE war_id=? ORDER BY al DESC", (war_id,)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_user_clan(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT c.* FROM clans c
            JOIN clan_members m ON c.id = m.clan_id
            WHERE m.user_id = ?
        """, (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_clan_members(clan_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM clan_members WHERE clan_id=? ORDER BY joined_at",
            (clan_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def join_clan(user_id: int, clan_id: int, username: str, full_name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем не состоит ли уже в другом клане
        async with db.execute("SELECT clan_id FROM clan_members WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        if row:
            return False
        await db.execute(
            "INSERT INTO clan_members (user_id, clan_id, username, full_name) VALUES (?, ?, ?, ?)",
            (user_id, clan_id, username, full_name)
        )
        await db.commit()
        return True


async def leave_clan(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM clan_members WHERE user_id=?", (user_id,))
        await db.commit()


async def kick_member(clan_id: int, target_user_id: int, requester_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT creator_id FROM clans WHERE id=?", (clan_id,)) as cur:
            clan = await cur.fetchone()
        if not clan or clan[0] != requester_id:
            return False
        await db.execute("DELETE FROM clan_members WHERE user_id=? AND clan_id=?", (target_user_id, clan_id))
        await db.commit()
        return True


async def transfer_leadership(clan_id: int, new_leader_id: int, requester_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT creator_id FROM clans WHERE id=?", (clan_id,)) as cur:
            clan = await cur.fetchone()
        if not clan or clan[0] != requester_id:
            return False
        # Новый лидер должен быть в клане
        async with db.execute("SELECT 1 FROM clan_members WHERE user_id=? AND clan_id=?", (new_leader_id, clan_id)) as cur:
            member = await cur.fetchone()
        if not member:
            return False
        await db.execute("UPDATE clans SET creator_id=? WHERE id=?", (new_leader_id, clan_id))
        await db.commit()
        return True


async def update_clan_al(clan_id: int, new_al: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE clans SET al=? WHERE id=?", (new_al, clan_id))
        await db.commit()


async def update_clan_stats_win(clan_id: int, multiplier: float, user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT wins, current_win_streak, max_win_streak, best_multiplier FROM clans WHERE id=?",
            (clan_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return
        wins, streak, max_streak, best_mult = row
        new_streak = streak + 1
        new_max_streak = max(max_streak, new_streak)
        update_best = multiplier > best_mult
        await db.execute("""
            UPDATE clans SET
                wins = wins + 1,
                current_win_streak = ?,
                max_win_streak = ?,
                best_multiplier = CASE WHEN ? > best_multiplier THEN ? ELSE best_multiplier END,
                best_multiplier_user_id = CASE WHEN ? > best_multiplier THEN ? ELSE best_multiplier_user_id END,
                best_multiplier_username = CASE WHEN ? > best_multiplier THEN ? ELSE best_multiplier_username END
            WHERE id=?
        """, (new_streak, new_max_streak,
              multiplier, multiplier,
              multiplier, user_id,
              multiplier, username,
              clan_id))
        await db.commit()


async def update_clan_stats_loss(clan_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE clans SET losses=losses+1, current_win_streak=0 WHERE id=?",
            (clan_id,)
        )
        await db.commit()


async def get_active_war() -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM wars WHERE is_active=1 LIMIT 1") as cur:
            row = await cur.fetchone()
            return dict(row) if row else None
            async def delete_clan(clan_id: int, creator_id: int) -> bool:
    """
    Удаляет клан и всех его участников.
    Возвращает True если удаление прошло успешно.
    Работает только если creator_id совпадает с создателем клана.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Сначала исключаем всех участников
        await db.execute(
            "DELETE FROM clan_members WHERE clan_id = ?",
            (clan_id,)
        )
        # Удаляем сам клан (только если это действительно создатель)
        cursor = await db.execute(
            "DELETE FROM clans WHERE id = ? AND creator_id = ?",
            (clan_id, creator_id)
        )
        await db.commit()
        return cursor.rowcount > 0

