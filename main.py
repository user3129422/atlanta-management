import logging

import discord
from discord.ext import commands

from config import DISCORD_TOKEN, GUILD_ID
from database import initialize_database


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("atlanta_roleplay")

EXTENSIONS = [
    "cogs.utility",
    "cogs.moderation",
    "cogs.staff",
    "cogs.sessions",
    "cogs.leave_of_absence",
    "cogs.roblox",
    "cogs.tickets",
]


intents = discord.Intents.default()
intents.members = True
intents.message_content = True


class AtlantaBot(commands.Bot):
    async def setup_hook(self):
        logger.info("Initializing database...")
        await initialize_database()
        logger.info("Database initialized.")

        for extension in EXTENSIONS:
            await self.load_extension(extension)
            logger.info("Loaded extension: %s", extension)

        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)

        synced_commands = await self.tree.sync(guild=guild)

        logger.info(
            "Synced %s slash commands to guild %s.",
            len(synced_commands),
            GUILD_ID,
        )

    async def on_ready(self):
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        logger.info("Connected to %s server(s).", len(self.guilds))

    async def on_guild_join(self, guild):
        logger.info("Joined server: %s (ID: %s)", guild.name, guild.id)


if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing from your .env file. "
        "Add your bot token locally and never share it."
    )

if GUILD_ID <= 0:
    raise RuntimeError("GUILD_ID must be a valid positive Discord server ID.")


bot = AtlantaBot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN, log_handler=None)
