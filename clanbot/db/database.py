import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "bot.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS clans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                deviz TEXT DEFAULT '',
                avatar_file_id TEXT DEFAULT NULL,
                al INTEGER DEFAULT 100,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                max_win_streak INTEGER DEFAULT 0,
                current_win_streak INTEGER DEFAULT 0,
                best_multiplier REAL DEFAULT 1.0,
                best_multiplier_user_id INTEGER DEFAULT NULL,
                best_multiplier_username TEXT DEFAULT '',
                creator_id INTEGER NOT NULL,
                war_id INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS clan_members (
                user_id INTEGER NOT NULL,
                clan_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                joined_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id)
            );

            CREATE TABLE IF NOT EXISTS wars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT DEFAULT (datetime('now')),
                ended_at TEXT DEFAULT NULL,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS duels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                war_id INTEGER NOT NULL,
                clan1_id INTEGER NOT NULL,
                clan2_id INTEGER NOT NULL,
                player1_id INTEGER DEFAULT NULL,
                player2_id INTEGER DEFAULT NULL,
                player1_done INTEGER DEFAULT 0,
                player2_done INTEGER DEFAULT 0,
                scheduled_at TEXT DEFAULT (datetime('now')),
                completed_at TEXT DEFAULT NULL,
                status TEXT DEFAULT 'pending',
                chat_id INTEGER NOT NULL,
                message_id INTEGER DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS duel_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                duel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                clan_id INTEGER NOT NULL,
                mines INTEGER DEFAULT 1,
                field TEXT DEFAULT NULL,
                opened TEXT DEFAULT '[]',
                current_multiplier REAL DEFAULT 1.0,
                step INTEGER DEFAULT 0,
                status TEXT DEFAULT 'choosing_mines',
                message_id INTEGER DEFAULT NULL,
                chat_id INTEGER DEFAULT NULL,
                started_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS duel_queue (
                clan_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                attempts_left INTEGER DEFAULT 1,
                PRIMARY KEY (clan_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS war_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                war_id INTEGER NOT NULL,
                clan_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                duel_id INTEGER NOT NULL,
                result TEXT NOT NULL,
                multiplier REAL DEFAULT 1.0,
                al_before INTEGER,
                al_after INTEGER,
                played_at TEXT DEFAULT (datetime('now'))
            );
        """)
        # Создаём первую войну если нет
        async with db.execute("SELECT id FROM wars WHERE is_active=1") as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute("INSERT INTO wars (is_active) VALUES (1)")
        await db.commit()


async def get_db():
    return aiosqlite.connect(DB_PATH)
