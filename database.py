import aiosqlite
from config import DATABASE_PATH

async def initialize_database():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS infractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                infraction_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS staff_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                actor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS loa_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                host_id INTEGER NOT NULL,
                session_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS session_attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                attendance_status TEXT NOT NULL,
                UNIQUE(session_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS roblox_links (
                guild_id INTEGER NOT NULL,
                discord_id INTEGER NOT NULL,
                roblox_id TEXT NOT NULL,
                roblox_username TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, discord_id),
                UNIQUE(guild_id, roblox_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL UNIQUE,
                opener_id INTEGER NOT NULL,
                ticket_type TEXT NOT NULL,
                claimed_by INTEGER,
                status TEXT NOT NULL DEFAULT 'Open',
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()