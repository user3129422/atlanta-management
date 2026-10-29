
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("GUILD_ID", "1538727238290251886"))
ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY", "").strip()

ROLES = {
    "staff": 1538727238399303727,
    "partnership_support": 1538727238399303726,
    "hr": 1538727238441369670,
    "shr": 1538727238441369677,
    "management": 1538727238441369679,
    "developer": 1538727238458155043,
    "founder": 1538727238483050664,
}

SESSION_MANAGEMENT_ROLE_ID = 1538727238353289297

CHANNELS = {
    "ticket_test": 1553403546462986320,
    "support": 1538727239850659909,
    "ticket_category": 1540217389717786727,
    "ticket_logs": 1538727243465883746,
    "bot_logs": 1540428815866667098,
}

DATABASE_PATH = "atlanta_roleplay.db"

INFRACTION_TYPES = [
    "Warn",
    "Strike",
    "Final Warning",
    "Suspension",
    "Demotion",
    "Blacklist",
    "Termination",
    "Other",
]

TICKET_TYPES = [
    "General Support",
    "Internal Affairs",
    "Management",
    "Partnerships",
]

if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing. Add your bot token to the .env file."
    )
