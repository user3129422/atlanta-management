import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from datetime import date

from config import ROLES, CHANNELS, DATABASE_PATH
from embeds import (
    make_embed,
    section,
    success_embed,
    error_embed,
    warning_embed,
    audit_embed,
)


class LeaveOfAbsence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def can_review(self, member):
        allowed = {
            ROLES["hr"],
            ROLES["shr"],
            ROLES["developer"],
            ROLES["founder"],
        }

        return member.guild_permissions.administrator or any(
            role.id in allowed for role in member.roles
        )

    async def log_loa(
        self,
        guild,
        title,
        actor,
        request_id,
        member_id,
        details,
        status="info",
    ):
        channel = guild.get_channel(CHANNELS["bot_logs"])

        if channel is None:
            return

        embed = audit_embed(
            title=f"LEAVE OF ABSENCE | {title}",
            actor=actor,
            target=guild.get_member(member_id),
            reference=f"LOA-{request_id:04d}",
            category="Leave of Absence",
            details=details,
            status=status,
        )

        try:
            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            return

    @app_commands.command(
        name="loa",
        description="Submit a leave of absence request.",
    )
    @app_commands.describe(
        start_date="Leave start date in YYYY-MM-DD format",
        end_date="Leave end date in YYYY-MM-DD format",
        reason="Reason for your leave request",
    )
    async def loa(
        self,
        interaction: discord.Interaction,
        start_date: str,
        end_date: str,
        reason: str,
    ):
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Date",
                    "Both dates must use YYYY-MM-DD format, for example "
                    "`2026-11-01`.",
                ),
                ephemeral=True,
            )
            return

        if end < start:
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Date Range",
                    "The end date cannot be earlier than the start date.",
                ),
                ephemeral=True,
            )
            return

        if start < date.today():
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Start Date",
                    "The leave start date cannot be in the past.",
                ),
                ephemeral=True,
            )
            return

        reason = reason.strip()

        if not reason:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Reason Required",
                    "Provide a reason before submitting your LOA request.",
                ),
                ephemeral=True,
            )
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT id
                FROM loa_requests
                WHERE guild_id = ?
                  AND user_id = ?
                  AND status IN ('Pending', 'Approved')
                LIMIT 1
                """,
                (interaction.guild_id, interaction.user.id),
            )

            existing = await cursor.fetchone()

            if existing:
                await interaction.response.send_message(
                    embed=warning_embed(
                        "Existing LOA Request",
                        f"You already have a pending or approved request: "
                        f"**#{existing[0]}**.",
                    ),
                    ephemeral=True,
                )
                return

            cursor = await db.execute(
                """
                INSERT INTO loa_requests
                (guild_id, user_id, reason, start_date, end_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    interaction.guild_id,
                    interaction.user.id,
                    reason,
                    start.isoformat(),
                    end.isoformat(),
                ),
            )

            request_id = cursor.lastrowid
            await db.commit()

        embed = make_embed(
            "LEAVE OF ABSENCE | REQUEST SUBMITTED",
            "Your leave request has been registered and is awaiting review.",
            status="info",
            actor=interaction.user,
            reference=f"LOA-{request_id:04d}",
            category="Leave of Absence",
        )

        section(embed, "Start Date", start.isoformat(), inline=True)
        section(embed, "End Date", end.isoformat(), inline=True)
        section(embed, "Current Status", "Pending Review", inline=True)
        section(embed, "Reason", reason)
        section(
            embed,
            "Next Steps",
            "An authorized HR team member will review your request. "
            "You can check its status using `/loainfo`.",
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

        await self.log_loa(
            interaction.guild,
            "Request Submitted",
            interaction.user,
            request_id,
            interaction.user.id,
            (
                f"Start date: {start.isoformat()}\n"
                f"End date: {end.isoformat()}\n"
                f"Reason: {reason}"
            ),
            status="info",
        )

    @app_commands.command(
        name="loaapprove",
        description="Approve a pending LOA request.",
    )
    async def loaapprove(
        self,
        interaction: discord.Interaction,
        request_id: app_commands.Range[int, 1, 2147483647],
    ):
        if not self.can_review(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "HR permissions or higher are required to review LOA requests.",
                ),
                ephemeral=True,
            )
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT user_id, start_date, end_date, reason
                FROM loa_requests
                WHERE id = ?
                  AND guild_id = ?
                  AND status = 'Pending'
                """,
                (request_id, interaction.guild_id),
            )

            request = await cursor.fetchone()

            if not request:
                await interaction.response.send_message(
                    embed=warning_embed(
                        "Request Not Found",
                        "No pending LOA request with that ID was found.",
                    ),
                    ephemeral=True,
                )
                return

            cursor = await db.execute(
                """
                UPDATE loa_requests
                SET status = 'Approved'
                WHERE id = ?
                  AND guild_id = ?
                  AND status = 'Pending'
                """,
                (request_id, interaction.guild_id),
            )

            if cursor.rowcount == 0:
                await interaction.response.send_message(
                    embed=warning_embed(
                        "Request Already Reviewed",
                        "This request is no longer pending.",
                    ),
                    ephemeral=True,
                )
                return

            await db.commit()

        user_id, start_date, end_date, reason = request

        embed = success_embed(
            "LOA Request Approved",
            f"Request **#{request_id}** has been approved.",
            actor=interaction.user,
            reference=f"LOA-{request_id:04d}",
            category="Leave of Absence",
        )

        section(embed, "Member", f"<@{user_id}>")
        section(embed, "Approved Dates", f"{start_date} to {end_date}")
        section(embed, "Original Reason", reason)

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

        await self.log_loa(
            interaction.guild,
            "Request Approved",
            interaction.user,
            request_id,
            user_id,
            (
                f"Dates: {start_date} to {end_date}\n"
                f"Original reason: {reason}"
            ),
            status="success",
        )

    @app_commands.command(
        name="loadeny",
        description="Deny a pending LOA request.",
    )
    @app_commands.describe(
        reason="Reason for denying the request",
    )
    async def loadeny(
        self,
        interaction: discord.Interaction,
        request_id: app_commands.Range[int, 1, 2147483647],
        reason: str,
    ):
        if not self.can_review(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "HR permissions or higher are required to review LOA requests.",
                ),
                ephemeral=True,
            )
            return

        reason = reason.strip()

        if not reason:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Reason Required",
                    "Provide a reason for denying the request.",
                ),
                ephemeral=True,
            )
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT user_id, start_date, end_date
                FROM loa_requests
                WHERE id = ?
                  AND guild_id = ?
                  AND status = 'Pending'
                """,
                (request_id, interaction.guild_id),
            )

            request = await cursor.fetchone()

            if not request:
                await interaction.response.send_message(
                    embed=warning_embed(
                        "Request Not Found",
                        "No pending LOA request with that ID was found.",
                    ),
                    ephemeral=True,
                )
                return

            cursor = await db.execute(
                """
                UPDATE loa_requests
                SET status = 'Denied'
                WHERE id = ?
                  AND guild_id = ?
                  AND status = 'Pending'
                """,
                (request_id, interaction.guild_id),
            )

            if cursor.rowcount == 0:
                await interaction.response.send_message(
                    embed=warning_embed(
                        "Request Already Reviewed",
                        "This request is no longer pending.",
                    ),
                    ephemeral=True,
                )
                return

            await db.commit()

        user_id, start_date, end_date = request

        embed = warning_embed(
            "LOA Request Denied",
            f"Request **#{request_id}** has been denied.",
            actor=interaction.user,
            reference=f"LOA-{request_id:04d}",
            category="Leave of Absence",
        )

        section(embed, "Member", f"<@{user_id}>")
        section(embed, "Requested Dates", f"{start_date} to {end_date}")
        section(embed, "Decision Reason", reason)

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

        await self.log_loa(
            interaction.guild,
            "Request Denied",
            interaction.user,
            request_id,
            user_id,
            (
                f"Requested dates: {start_date} to {end_date}\n"
                f"Decision reason: {reason}"
            ),
            status="warning",
        )

    @app_commands.command(
        name="loaend",
        description="End an approved LOA.",
    )
    @app_commands.describe(
        request_id="The approved LOA request ID",
    )
    async def loaend(
        self,
        interaction: discord.Interaction,
        request_id: app_commands.Range[int, 1, 2147483647],
    ):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT user_id, start_date, end_date
                FROM loa_requests
                WHERE id = ?
                  AND guild_id = ?
                  AND status = 'Approved'
                """,
                (request_id, interaction.guild_id),
            )

            request = await cursor.fetchone()

            if not request:
                await interaction.response.send_message(
                    embed=warning_embed(
                        "Approved Request Not Found",
                        "No approved LOA request with that ID was found.",
                    ),
                    ephemeral=True,
                )
                return

            user_id, start_date, end_date = request

            if (
                user_id != interaction.user.id
                and not self.can_review(interaction.user)
            ):
                await interaction.response.send_message(
                    embed=error_embed(
                        "Permission Denied",
                        "Only the requesting member or authorized HR staff "
                        "can end this LOA.",
                    ),
                    ephemeral=True,
                )
                return

            cursor = await db.execute(
                """
                UPDATE loa_requests
                SET status = 'Ended'
                WHERE id = ?
                  AND guild_id = ?
                  AND status = 'Approved'
                """,
                (request_id, interaction.guild_id),
            )

            if cursor.rowcount == 0:
                await interaction.response.send_message(
                    embed=warning_embed(
                        "Request Already Updated",
                        "This LOA is no longer approved.",
                    ),
                    ephemeral=True,
                )
                return

            await db.commit()

        embed = success_embed(
            "Leave of Absence Ended",
            f"LOA request **#{request_id}** has been marked as ended.",
            actor=interaction.user,
            reference=f"LOA-{request_id:04d}",
            category="Leave of Absence",
        )

        section(embed, "Member", f"<@{user_id}>")
        section(embed, "Approved Dates", f"{start_date} to {end_date}")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

        await self.log_loa(
            interaction.guild,
            "Request Ended",
            interaction.user,
            request_id,
            user_id,
            f"Approved dates: {start_date} to {end_date}",
            status="success",
        )

    @app_commands.command(
        name="loainfo",
        description="View the status of an LOA request.",
    )
    async def loainfo(
        self,
        interaction: discord.Interaction,
        request_id: app_commands.Range[int, 1, 2147483647],
    ):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT user_id, reason, start_date, end_date, status, created_at
                FROM loa_requests
                WHERE id = ? AND guild_id = ?
                """,
                (request_id, interaction.guild_id),
            )

            request = await cursor.fetchone()

        if not request:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Request Not Found",
                    "No LOA request with that ID was found in this server.",
                ),
                ephemeral=True,
            )
            return

        user_id, reason, start_date, end_date, status, created_at = request

        if (
            user_id != interaction.user.id
            and not self.can_review(interaction.user)
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "You can only view your own LOA requests.",
                ),
                ephemeral=True,
            )
            return

        status_style = {
            "Approved": "success",
            "Denied": "warning",
            "Ended": "neutral",
            "Pending": "info",
        }.get(status, "info")

        embed = make_embed(
            "LEAVE OF ABSENCE | REQUEST DETAILS",
            f"Details for LOA request **#{request_id}**.",
            status=status_style,
            reference=f"LOA-{request_id:04d}",
            category="Leave of Absence",
        )

        section(embed, "Member", f"<@{user_id}>")
        section(embed, "Start Date", start_date, inline=True)
        section(embed, "End Date", end_date, inline=True)
        section(embed, "Current Status", status, inline=True)
        section(embed, "Submitted", created_at)
        section(embed, "Reason", reason)

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(LeaveOfAbsence(bot))