import asyncio
import secrets
import time

import aiohttp
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from config import DATABASE_PATH
from embeds import make_embed, section, success_embed, error_embed, info_embed


VERIFICATION_EXPIRY_SECONDS = 900
ROBLOX_PROFILE_URL = "https://www.roblox.com/users/{}/profile"


class Roblox(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending_verifications = {}

    async def fetch_roblox_user(self, username):
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {
            "usernames": [username],
            "excludeBannedUsers": True,
        }

        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Roblox username API returned HTTP {response.status}"
                    )

                data = await response.json()

        users = data.get("data", [])
        return users[0] if users else None

    async def fetch_roblox_description(self, roblox_id):
        url = f"https://users.roblox.com/v1/users/{roblox_id}"
        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Roblox profile API returned HTTP {response.status}"
                    )

                data = await response.json()

        return data.get("description", "")

    def get_pending_verification(self, guild_id, user_id):
        key = (guild_id, user_id)
        pending = self.pending_verifications.get(key)

        if not pending:
            return None

        if time.time() >= pending["expires_at"]:
            self.pending_verifications.pop(key, None)
            return None

        return pending

    @app_commands.command(
        name="robloxlink",
        description="Begin linking your Roblox account.",
    )
    @app_commands.guild_only()
    @app_commands.describe(username="Your Roblox username")
    async def robloxlink(
        self,
        interaction: discord.Interaction,
        username: str,
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            user = await self.fetch_roblox_user(username)
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError):
            await interaction.followup.send(
                embed=error_embed(
                    "Roblox Service Unavailable",
                    "Roblox could not be reached right now. Please try again shortly.",
                ),
                ephemeral=True,
            )
            return

        if not user:
            await interaction.followup.send(
                embed=error_embed(
                    "Roblox Account Not Found",
                    "I couldn't find that Roblox username. Check the spelling and try again.",
                ),
                ephemeral=True,
            )
            return

        code = "ACR-" + secrets.token_hex(4).upper()
        key = (interaction.guild_id, interaction.user.id)

        self.pending_verifications[key] = {
            "roblox_id": str(user["id"]),
            "username": user["name"],
            "code": code,
            "expires_at": time.time() + VERIFICATION_EXPIRY_SECONDS,
        }

        embed = make_embed(
            title="ROBLOX ACCOUNT VERIFICATION",
            description=(
                f"**Roblox account:** [{user['name']}]"
                f"({ROBLOX_PROFILE_URL.format(user['id'])})\n\n"
                "To verify ownership of this account:\n"
                "1. Open your Roblox profile.\n"
                "2. Add the verification code below to your profile description.\n"
                "3. Run `/robloxverify` in this server.\n"
                "4. Once verification succeeds, you may remove the code."
            ),
            status="info",
            actor=interaction.user,
        )

        section(embed, "Verification Code", f"`{code}`")
        section(embed, "Expires In", "15 minutes")
        section(
            embed,
            "Security Notice",
            "Only add the code to the Roblox account you own. "
            "Never share your Discord password or Roblox password.",
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="robloxverify",
        description="Verify ownership of your Roblox account.",
    )
    @app_commands.guild_only()
    async def robloxverify(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        key = (interaction.guild_id, interaction.user.id)
        pending = self.get_pending_verification(
            interaction.guild_id,
            interaction.user.id,
        )

        if not pending:
            await interaction.followup.send(
                embed=error_embed(
                    "Verification Not Found",
                    "You don't have an active verification code. Run `/robloxlink` to begin again. "
                    "Verification codes expire after 15 minutes.",
                ),
                ephemeral=True,
            )
            return

        try:
            description = await self.fetch_roblox_description(
                pending["roblox_id"]
            )
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError):
            await interaction.followup.send(
                embed=error_embed(
                    "Roblox Service Unavailable",
                    "Roblox could not be reached right now. Your verification code is still available. "
                    "Please try again shortly.",
                ),
                ephemeral=True,
            )
            return

        if pending["code"] not in description:
            await interaction.followup.send(
                embed=error_embed(
                    "Verification Code Not Found",
                    "The code was not found in the selected Roblox profile description. "
                    "Make sure it matches exactly, then run `/robloxverify` again.",
                ),
                ephemeral=True,
            )
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT discord_id
                FROM roblox_links
                WHERE guild_id = ? AND roblox_id = ?
                """,
                (interaction.guild_id, pending["roblox_id"]),
            )
            existing = await cursor.fetchone()

            if existing and existing[0] != interaction.user.id:
                await interaction.followup.send(
                    embed=error_embed(
                        "Roblox Account Already Linked",
                        "That Roblox account is already linked to another Discord member in this server.",
                    ),
                    ephemeral=True,
                )
                return

            try:
                await db.execute(
                    """
                    INSERT INTO roblox_links
                    (guild_id, discord_id, roblox_id, roblox_username, verified)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(guild_id, discord_id)
                    DO UPDATE SET
                        roblox_id = excluded.roblox_id,
                        roblox_username = excluded.roblox_username,
                        verified = 1
                    """,
                    (
                        interaction.guild_id,
                        interaction.user.id,
                        pending["roblox_id"],
                        pending["username"],
                    ),
                )
                await db.commit()
            except aiosqlite.IntegrityError:
                await interaction.followup.send(
                    embed=error_embed(
                        "Account Link Conflict",
                        "This Roblox account could not be linked because it is already associated with another Discord member.",
                    ),
                    ephemeral=True,
                )
                return

        self.pending_verifications.pop(key, None)

        embed = success_embed(
            "ROBLOX ACCOUNT VERIFIED",
            "Your Roblox account has been successfully linked to your Discord account.",
            actor=interaction.user,
            category="Roblox Verification",
        )

        section(
            embed,
            "Roblox Username",
            f"[{pending['username']}]"
            f"({ROBLOX_PROFILE_URL.format(pending['roblox_id'])})",
        )
        section(embed, "Roblox User ID", f"`{pending['roblox_id']}`")
        section(embed, "Verification Status", "Verified")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="robloxinfo",
        description="View a member's verified Roblox account.",
    )
    @app_commands.guild_only()
    @app_commands.describe(member="Member to look up, or yourself")
    async def robloxinfo(
        self,
        interaction: discord.Interaction,
        member: discord.Member = None,
    ):
        target = member or interaction.user

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT roblox_id, roblox_username, verified
                FROM roblox_links
                WHERE guild_id = ? AND discord_id = ?
                """,
                (interaction.guild_id, target.id),
            )
            record = await cursor.fetchone()

        if not record or not record[2]:
            await interaction.response.send_message(
                embed=info_embed(
                    "NO VERIFIED ROBLOX ACCOUNT",
                    f"{target.mention} doesn't have a verified Roblox account linked.",
                    actor=interaction.user,
                    target=target,
                ),
                ephemeral=True,
            )
            return

        roblox_id, username, _ = record

        embed = make_embed(
            title="LINKED ROBLOX ACCOUNT",
            description="A verified Roblox account is linked to this Discord member.",
            status="info",
            actor=interaction.user,
            target=target,
            category="Roblox Account",
        )

        section(
            embed,
            "Roblox Username",
            f"[{username}]({ROBLOX_PROFILE_URL.format(roblox_id)})",
        )
        section(embed, "Roblox User ID", f"`{roblox_id}`")
        section(embed, "Verification Status", "Verified")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="robloxunlink",
        description="Remove your linked Roblox account.",
    )
    @app_commands.guild_only()
    async def robloxunlink(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                DELETE FROM roblox_links
                WHERE guild_id = ? AND discord_id = ?
                """,
                (interaction.guild_id, interaction.user.id),
            )
            await db.commit()
            removed = cursor.rowcount > 0

        self.pending_verifications.pop(
            (interaction.guild_id, interaction.user.id),
            None,
        )

        if not removed:
            await interaction.response.send_message(
                embed=info_embed(
                    "NO LINKED ACCOUNT",
                    "You don't currently have a linked Roblox account to remove.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "ROBLOX ACCOUNT UNLINKED",
                "Your Roblox account link has been removed from this server.",
                actor=interaction.user,
                category="Roblox Account",
            ),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Roblox(bot))