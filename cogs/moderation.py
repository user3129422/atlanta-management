import datetime

import discord
from discord import app_commands
from discord.ext import commands

from config import ROLES, CHANNELS
from embeds import audit_embed, success_embed, error_embed, warning_embed


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def can_moderate(self, member):
        allowed_roles = {
            ROLES["hr"],
            ROLES["shr"],
            ROLES["management"],
            ROLES["developer"],
            ROLES["founder"],
        }

        return (
            member.guild_permissions.administrator
            or any(role.id in allowed_roles for role in member.roles)
        )

    def can_target(self, moderator, target):
        if moderator.id == target.id:
            return False

        if moderator.guild.owner_id == target.id:
            return False

        if moderator.id != moderator.guild.owner_id:
            if target.top_role >= moderator.top_role:
                return False

        return True

    async def log_action(
        self,
        guild,
        title,
        moderator,
        target,
        reason,
        status="warning",
        category="Moderation",
    ):
        channel = guild.get_channel(CHANNELS["bot_logs"])

        if channel is None:
            return

        embed = audit_embed(
            title=title,
            actor=moderator,
            target=target,
            reason=reason,
            category=category,
            status=status,
        )

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def send_permission_error(self, interaction):
        await interaction.response.send_message(
            embed=error_embed(
                "ACCESS DENIED",
                "You do not have permission to use this moderation command.",
            ),
            ephemeral=True,
        )

    async def send_target_error(self, interaction):
        await interaction.response.send_message(
            embed=error_embed(
                "ACTION NOT PERMITTED",
                "You cannot moderate yourself, the server owner, or a member "
                "whose highest role is equal to or higher than yours.",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="kick",
        description="Remove a member from the server.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        member="Member to remove",
        reason="Reason for the kick",
    )
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ):
        moderator = interaction.user

        if not self.can_moderate(moderator):
            await self.send_permission_error(interaction)
            return

        if not self.can_target(moderator, member):
            await self.send_target_error(interaction)
            return

        if not interaction.guild.me.guild_permissions.kick_members:
            await interaction.response.send_message(
                embed=error_embed(
                    "BOT PERMISSION MISSING",
                    "I need the **Kick Members** permission to perform this action.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await member.kick(reason=f"{moderator} ({moderator.id}): {reason}")

            await self.log_action(
                interaction.guild,
                "MEMBER KICKED",
                moderator,
                member,
                reason,
            )

            await interaction.followup.send(
                embed=success_embed(
                    "MEMBER KICKED",
                    f"{member.mention} has been removed from the server.",
                    actor=moderator,
                    target=member,
                    category="Kick",
                ),
                ephemeral=True,
            )

        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed(
                    "KICK FAILED",
                    "Discord denied the action. Check my permissions and role hierarchy.",
                ),
                ephemeral=True,
            )
        except discord.HTTPException:
            await interaction.followup.send(
                embed=error_embed(
                    "KICK FAILED",
                    "Discord encountered an error while processing this action.",
                ),
                ephemeral=True,
            )

    @app_commands.command(
        name="ban",
        description="Ban a member from the server.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        member="Member to ban",
        reason="Reason for the ban",
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ):
        moderator = interaction.user

        if not self.can_moderate(moderator):
            await self.send_permission_error(interaction)
            return

        if not self.can_target(moderator, member):
            await self.send_target_error(interaction)
            return

        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message(
                embed=error_embed(
                    "BOT PERMISSION MISSING",
                    "I need the **Ban Members** permission to perform this action.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await member.ban(reason=f"{moderator} ({moderator.id}): {reason}")

            await self.log_action(
                interaction.guild,
                "MEMBER BANNED",
                moderator,
                member,
                reason,
            )

            await interaction.followup.send(
                embed=success_embed(
                    "MEMBER BANNED",
                    f"{member.mention} has been banned from the server.",
                    actor=moderator,
                    target=member,
                    category="Ban",
                ),
                ephemeral=True,
            )

        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed(
                    "BAN FAILED",
                    "Discord denied the action. Check my permissions and role hierarchy.",
                ),
                ephemeral=True,
            )
        except discord.HTTPException:
            await interaction.followup.send(
                embed=error_embed(
                    "BAN FAILED",
                    "Discord encountered an error while processing this action.",
                ),
                ephemeral=True,
            )

    @app_commands.command(
        name="timeout",
        description="Timeout a member for a specified number of minutes.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        member="Member to timeout",
        minutes="Duration from 1 to 10080 minutes",
        reason="Reason for the timeout",
    )
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 10080],
        reason: str,
    ):
        moderator = interaction.user

        if not self.can_moderate(moderator):
            await self.send_permission_error(interaction)
            return

        if not self.can_target(moderator, member):
            await self.send_target_error(interaction)
            return

        if not interaction.guild.me.guild_permissions.moderate_members:
            await interaction.response.send_message(
                embed=error_embed(
                    "BOT PERMISSION MISSING",
                    "I need the **Moderate Members** permission to perform this action.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)

            await member.timeout(
                until,
                reason=f"{moderator} ({moderator.id}): {reason}",
            )

            await self.log_action(
                interaction.guild,
                "MEMBER TIMED OUT",
                moderator,
                member,
                f"{reason}\nDuration: {minutes} minutes",
            )

            await interaction.followup.send(
                embed=success_embed(
                    "MEMBER TIMED OUT",
                    f"{member.mention} has been timed out for **{minutes} minutes**.",
                    actor=moderator,
                    target=member,
                    category="Timeout",
                ),
                ephemeral=True,
            )

        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed(
                    "TIMEOUT FAILED",
                    "Discord denied the action. Check my permissions and role hierarchy.",
                ),
                ephemeral=True,
            )
        except discord.HTTPException:
            await interaction.followup.send(
                embed=error_embed(
                    "TIMEOUT FAILED",
                    "Discord encountered an error while processing this action.",
                ),
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(Moderation(bot))