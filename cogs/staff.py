
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite

from config import ROLES, CHANNELS, INFRACTION_TYPES, DATABASE_PATH
from embeds import (
    make_embed,
    section,
    success_embed,
    error_embed,
    warning_embed,
    audit_embed,
)


class Staff(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def has_hr_access(self, member):
        allowed = {
            ROLES["hr"],
            ROLES["shr"],
            ROLES["management"],
            ROLES["developer"],
            ROLES["founder"],
        }
        return member.guild_permissions.administrator or any(
            role.id in allowed for role in member.roles
        )

    def has_senior_access(self, member):
        allowed = {
            ROLES["shr"],
            ROLES["developer"],
            ROLES["founder"],
        }
        return member.guild_permissions.administrator or any(
            role.id in allowed for role in member.roles
        )

    def can_manage_member(self, actor, target):
        if actor.id == target.id:
            return False

        if actor.guild_permissions.administrator:
            return True

        return target.top_role < actor.top_role

    async def record_action(self, guild_id, user_id, actor_id, action, details):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                """
                INSERT INTO staff_history
                (guild_id, user_id, actor_id, action, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, actor_id, action, details),
            )
            await db.commit()

    async def log_action(self, guild, title, actor, target, details, status="success"):
        channel = guild.get_channel(CHANNELS["bot_logs"])

        if channel is None:
            return

        embed = audit_embed(
            title=f"STAFF MANAGEMENT | {title}",
            actor=actor,
            target=target,
            details=details,
            category="Staff Management",
            status=status,
        )

        try:
            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            return

    async def record_infraction(self, interaction, member, infraction_type, reason):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                """
                INSERT INTO infractions
                (guild_id, user_id, moderator_id, infraction_type, reason)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    interaction.guild_id,
                    member.id,
                    interaction.user.id,
                    infraction_type,
                    reason,
                ),
            )
            await db.commit()

        await self.record_action(
            interaction.guild_id,
            member.id,
            interaction.user.id,
            infraction_type,
            reason,
        )

        await self.log_action(
            interaction.guild,
            f"Infraction Issued: {infraction_type}",
            interaction.user,
            member,
            reason,
            status="warning",
        )

    @app_commands.command(
        name="infract",
        description="Issue and record a staff infraction.",
    )
    @app_commands.describe(
        member="The member receiving the infraction",
        infraction_type="The type of infraction",
        reason="The reason for the action",
    )
    @app_commands.choices(
        infraction_type=[
            app_commands.Choice(name=item, value=item)
            for item in INFRACTION_TYPES
        ]
    )
    async def infract(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        infraction_type: app_commands.Choice[str],
        reason: str,
    ):
        actor = interaction.user

        if not self.has_hr_access(actor):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "HR permissions or higher are required to issue infractions.",
                ),
                ephemeral=True,
            )
            return

        if not self.can_manage_member(actor, member):
            await interaction.response.send_message(
                embed=error_embed(
                    "Action Not Permitted",
                    "You cannot issue an infraction to yourself or a member "
                    "with an equal or higher top role.",
                ),
                ephemeral=True,
            )
            return

        reason = reason.strip()

        if not reason:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Reason Required",
                    "Provide a valid reason before recording the infraction.",
                ),
                ephemeral=True,
            )
            return

        await self.record_infraction(
            interaction,
            member,
            infraction_type.value,
            reason,
        )

        embed = success_embed(
            "Infraction Recorded",
            "The infraction has been saved to the staff records.",
            actor=actor,
            target=member,
            category=infraction_type.value,
        )
        section(embed, "Reason", reason)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="promote",
        description="Promote a member by assigning a role.",
    )
    @app_commands.describe(
        member="The member to promote",
        role="The role to assign",
        reason="Reason for the promotion",
    )
    async def promote(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        reason: str,
    ):
        actor = interaction.user
        guild = interaction.guild

        if not self.has_hr_access(actor):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "HR permissions or higher are required to promote members.",
                ),
                ephemeral=True,
            )
            return

        if not self.can_manage_member(actor, member):
            await interaction.response.send_message(
                embed=error_embed(
                    "Action Not Permitted",
                    "You cannot promote yourself or a member with an equal "
                    "or higher top role.",
                ),
                ephemeral=True,
            )
            return

        if role.is_default() or role.managed or role >= actor.top_role:
            await interaction.response.send_message(
                embed=error_embed(
                    "Role Hierarchy Restriction",
                    "The selected role is protected or is not below your highest role.",
                ),
                ephemeral=True,
            )
            return

        bot_member = guild.me

        if bot_member is None or role >= bot_member.top_role:
            await interaction.response.send_message(
                embed=error_embed(
                    "Bot Role Restriction",
                    "Move the bot's highest role above the role you want to assign.",
                ),
                ephemeral=True,
            )
            return

        if role in member.roles:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Role Already Assigned",
                    f"{member.mention} already has the selected role.",
                ),
                ephemeral=True,
            )
            return

        reason = reason.strip()

        if not reason:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Reason Required",
                    "Provide a reason for the promotion.",
                ),
                ephemeral=True,
            )
            return

        try:
            await member.add_roles(
                role,
                reason=f"Promotion by {actor} ({actor.id}): {reason}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed(
                    "Role Assignment Failed",
                    "I cannot assign that role. Check my Manage Roles permission "
                    "and role hierarchy.",
                ),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed(
                    "Role Assignment Failed",
                    "Discord could not complete the role assignment. Try again later.",
                ),
                ephemeral=True,
            )
            return

        details = f"Assigned role: {role.name} ({role.id}). Reason: {reason}"

        await self.record_action(
            interaction.guild_id,
            member.id,
            actor.id,
            "Promotion",
            details,
        )

        await self.log_action(
            guild,
            "Promotion",
            actor,
            member,
            details,
        )

        embed = success_embed(
            "Promotion Completed",
            f"{member.mention} has been assigned {role.mention}.",
            actor=actor,
            target=member,
            category="Promotion",
        )
        section(embed, "Reason", reason)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="demote",
        description="Remove a role from a member.",
    )
    @app_commands.describe(
        member="The member to demote",
        role="The role to remove",
        reason="Reason for the demotion",
    )
    async def demote(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        reason: str,
    ):
        actor = interaction.user
        guild = interaction.guild

        if not self.has_hr_access(actor):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "HR permissions or higher are required to demote members.",
                ),
                ephemeral=True,
            )
            return

        if not self.can_manage_member(actor, member):
            await interaction.response.send_message(
                embed=error_embed(
                    "Action Not Permitted",
                    "You cannot demote yourself or a member with an equal "
                    "or higher top role.",
                ),
                ephemeral=True,
            )
            return

        if role.is_default() or role.managed or role >= actor.top_role:
            await interaction.response.send_message(
                embed=error_embed(
                    "Role Hierarchy Restriction",
                    "The selected role is protected or is not below your highest role.",
                ),
                ephemeral=True,
            )
            return

        if role not in member.roles:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Role Not Found",
                    f"{member.mention} does not have the selected role.",
                ),
                ephemeral=True,
            )
            return

        reason = reason.strip()

        if not reason:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Reason Required",
                    "Provide a reason for the demotion.",
                ),
                ephemeral=True,
            )
            return

        try:
            await member.remove_roles(
                role,
                reason=f"Demotion by {actor} ({actor.id}): {reason}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed(
                    "Role Removal Failed",
                    "I cannot remove that role. Check my Manage Roles permission "
                    "and role hierarchy.",
                ),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed(
                    "Role Removal Failed",
                    "Discord could not complete the role removal. Try again later.",
                ),
                ephemeral=True,
            )
            return

        details = f"Removed role: {role.name} ({role.id}). Reason: {reason}"

        await self.record_action(
            interaction.guild_id,
            member.id,
            actor.id,
            "Demotion",
            details,
        )

        await self.log_action(
            guild,
            "Demotion",
            actor,
            member,
            details,
        )

        embed = success_embed(
            "Demotion Completed",
            f"{role.mention} has been removed from {member.mention}.",
            actor=actor,
            target=member,
            category="Demotion",
        )
        section(embed, "Reason", reason)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="staffhistory",
        description="View a member's staff action history.",
    )
    async def staffhistory(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        if not self.has_hr_access(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "HR permissions or higher are required to view staff history.",
                ),
                ephemeral=True,
            )
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT action, details, actor_id, created_at
                FROM staff_history
                WHERE guild_id = ? AND user_id = ?
                ORDER BY id DESC
                LIMIT 10
                """,
                (interaction.guild_id, member.id),
            )
            records = await cursor.fetchall()

            cursor = await db.execute(
                """
                SELECT infraction_type, reason, moderator_id, created_at
                FROM infractions
                WHERE guild_id = ? AND user_id = ?
                ORDER BY id DESC
                LIMIT 10
                """,
                (interaction.guild_id, member.id),
            )
            infractions = await cursor.fetchall()

        embed = make_embed(
            "STAFF RECORD | HISTORY",
            f"Reviewing the latest staff records for {member.mention}.",
            status="info",
            target=member,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        history_text = "\n".join(
            f"**{action}** | {details}\nBy: <@{actor}> | {created}"
            for action, details, actor, created in records
        )

        infraction_text = "\n".join(
            f"**{kind}** | {reason}\nBy: <@{moderator}> | {created}"
            for kind, reason, moderator, created in infractions
        )

        section(
            embed,
            "Recent Staff Actions",
            history_text or "No staff actions have been recorded.",
        )
        section(
            embed,
            "Recent Infractions",
            infraction_text or "No infractions have been recorded.",
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="staffinfo",
        description="View a member's staff record.",
    )
    async def staffinfo(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        if not self.has_hr_access(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "HR permissions or higher are required to view staff records.",
                ),
                ephemeral=True,
            )
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM infractions
                WHERE guild_id = ? AND user_id = ?
                """,
                (interaction.guild_id, member.id),
            )
            infraction_count = (await cursor.fetchone())[0]

            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM staff_history
                WHERE guild_id = ? AND user_id = ?
                """,
                (interaction.guild_id, member.id),
            )
            action_count = (await cursor.fetchone())[0]

        staff_roles = [
            role.mention
            for role in reversed(member.roles)
            if role.id in ROLES.values()
        ]

        embed = make_embed(
            "STAFF RECORD | MEMBER PROFILE",
            f"Staff information for {member.mention}.",
            status="info",
            target=member,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        section(
            embed,
            "Configured Staff Roles",
            ", ".join(staff_roles) if staff_roles else "No configured staff roles.",
        )
        section(embed, "Recorded Infractions", str(infraction_count), inline=True)
        section(embed, "Staff Actions", str(action_count), inline=True)
        section(
            embed,
            "Joined Server",
            discord.utils.format_dt(member.joined_at, style="D")
            if member.joined_at else "Unknown",
            inline=True,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="stafflist",
        description="List current members with configured staff roles.",
    )
    async def stafflist(self, interaction: discord.Interaction):
        if not self.has_hr_access(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "HR permissions or higher are required to view the staff list.",
                ),
                ephemeral=True,
            )
            return

        staff_members = [
            member
            for member in interaction.guild.members
            if any(role.id in ROLES.values() for role in member.roles)
        ]

        staff_members.sort(
            key=lambda member: (
                -member.top_role.position,
                member.display_name.lower(),
            )
        )

        lines = [
            f"{member.mention} | {member.top_role.mention}"
            for member in staff_members[:40]
        ]

        embed = make_embed(
            "STAFF DIRECTORY | ATLANTA ROLEPLAY",
            "\n".join(lines) if lines else "No configured staff members were found.",
            status="info",
        )
        section(
            embed,
            "Directory Summary",
            f"Showing up to 40 members. Total matching members: {len(staff_members)}.",
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Staff(bot))
