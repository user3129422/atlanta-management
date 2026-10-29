import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite

from config import ROLES, CHANNELS, DATABASE_PATH, SESSION_MANAGEMENT_ROLE_ID
from embeds import (
    make_embed,
    section,
    success_embed,
    error_embed,
    warning_embed,
    audit_embed,
)


class SessionVote(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=3600)
        self.votes = {}

    async def update_vote(self, interaction, response):
        await interaction.response.defer(ephemeral=True)

        self.votes[interaction.user.id] = response

        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0].copy()

            attend_count = sum(
                value == "Attend" for value in self.votes.values()
            )
            decline_count = sum(
                value == "Cannot Attend" for value in self.votes.values()
            )

            summary = (
                f"**Planning to Attend:** {attend_count}\n"
                f"**Cannot Attend:** {decline_count}\n"
                f"**Total Responses:** {len(self.votes)}"
            )

            field_index = next(
                (
                    index
                    for index, field in enumerate(embed.fields)
                    if field.name == "Vote Summary"
                ),
                None,
            )

            if field_index is None:
                embed.add_field(
                    name="Vote Summary",
                    value=summary,
                    inline=False,
                )
            else:
                embed.set_field_at(
                    field_index,
                    name="Vote Summary",
                    value=summary,
                    inline=False,
                )

            await interaction.message.edit(embed=embed, view=self)

        await interaction.followup.send(
            embed=success_embed(
                "Response Recorded",
                f"Your response has been recorded as **{response}**. "
                "You can change it by selecting either button again.",
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Attend",
        style=discord.ButtonStyle.success,
        custom_id="acr_session_attend",
    )
    async def attend(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await self.update_vote(interaction, "Attend")

    @discord.ui.button(
        label="Cannot Attend",
        style=discord.ButtonStyle.secondary,
        custom_id="acr_session_decline",
    )
    async def decline(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await self.update_vote(interaction, "Cannot Attend")


class Sessions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def can_host(self, member):
        allowed = {
            SESSION_MANAGEMENT_ROLE_ID,
            ROLES["hr"],
            ROLES["shr"],
            ROLES["management"],
            ROLES["developer"],
            ROLES["founder"],
        }

        return member.guild_permissions.administrator or any(
            role.id in allowed for role in member.roles
        )

    async def publish_session_announcement(self, channel, embed):
        role = channel.guild.get_role(SESSION_MANAGEMENT_ROLE_ID)
        content = role.mention if role else f"<@&{SESSION_MANAGEMENT_ROLE_ID}>"
        allowed_mentions = discord.AllowedMentions(
            roles=[role] if role else False,
            users=False,
            everyone=False,
            replied_user=False,
        )
        await channel.send(
            content=content,
            embed=embed,
            allowed_mentions=allowed_mentions,
        )

    async def get_log_channel(self, guild):
        channel = guild.get_channel(CHANNELS["bot_logs"])
        return channel if isinstance(channel, discord.TextChannel) else None

    async def log_session(
        self,
        guild,
        title,
        actor,
        session_id,
        session_type,
        details,
        status="info",
    ):
        channel = await self.get_log_channel(guild)

        if channel is None:
            return

        embed = audit_embed(
            title=f"SESSION MANAGEMENT | {title}",
            actor=actor,
            reference=f"SESSION-{session_id:04d}",
            category=session_type,
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
        name="sessionvote",
        description="Create a session attendance vote.",
    )
    @app_commands.describe(
        session_type="Choose the type of session",
        time="When the session will begin",
        notes="Optional additional information",
    )
    @app_commands.choices(
        session_type=[
            app_commands.Choice(name="Regular Session", value="Regular"),
            app_commands.Choice(name="Training", value="Training"),
            app_commands.Choice(name="Patrol", value="Patrol"),
            app_commands.Choice(name="Special Event", value="Special Event"),
        ]
    )
    async def sessionvote(
        self,
        interaction: discord.Interaction,
        session_type: app_commands.Choice[str],
        time: str,
        notes: str = "No additional information.",
    ):
        if not self.can_host(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "You do not have permission to create session votes.",
                ),
                ephemeral=True,
            )
            return

        embed = make_embed(
            "SESSION MANAGEMENT | ATTENDANCE POLL",
            "Staff attendance poll for Atlanta Roleplay.",
            status="info",
            actor=interaction.user,
            category=session_type.value,
        )

        section(embed, "Scheduled Time", time)
        section(embed, "Additional Information", notes)
        section(
            embed,
            "How to Respond",
            "Select **Attend** if you plan to participate, or "
            "**Cannot Attend** if you are unavailable. You can change "
            "your response while the poll remains active.",
        )
        section(
            embed,
            "Vote Summary",
            "**Planning to Attend:** 0\n"
            "**Cannot Attend:** 0\n"
            "**Total Responses:** 0",
        )

        await interaction.response.defer(ephemeral=True)

        await interaction.channel.send(
            content=(
                interaction.guild.get_role(SESSION_MANAGEMENT_ROLE_ID).mention
                if interaction.guild.get_role(SESSION_MANAGEMENT_ROLE_ID)
                else f"<@&{SESSION_MANAGEMENT_ROLE_ID}>"
            ),
            embed=embed,
            view=SessionVote(),
            allowed_mentions=discord.AllowedMentions(
                roles=[interaction.guild.get_role(SESSION_MANAGEMENT_ROLE_ID)]
                if interaction.guild.get_role(SESSION_MANAGEMENT_ROLE_ID)
                else False,
                users=False,
                everyone=False,
            ),
        )

        await interaction.followup.send(
            embed=success_embed(
                "Session Poll Published",
                "The attendance poll has been posted successfully.",
                actor=interaction.user,
                category=session_type.value,
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="sessionstart",
        description="Start a session.",
    )
    @app_commands.describe(
        session_type="Choose the type of session",
        notes="Optional session information",
    )
    @app_commands.choices(
        session_type=[
            app_commands.Choice(name="Regular Session", value="Regular"),
            app_commands.Choice(name="Low Session", value="Low"),
            app_commands.Choice(name="Full Session", value="Full"),
            app_commands.Choice(name="Training", value="Training"),
            app_commands.Choice(name="Patrol", value="Patrol"),
        ]
    )
    async def sessionstart(
        self,
        interaction: discord.Interaction,
        session_type: app_commands.Choice[str],
        notes: str = "No additional information.",
    ):
        if not self.can_host(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "You do not have permission to start sessions.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT id FROM sessions
                WHERE guild_id = ? AND status = 'Active'
                LIMIT 1
                """,
                (interaction.guild_id,),
            )
            active = await cursor.fetchone()

            if active:
                await interaction.followup.send(
                    embed=warning_embed(
                        "Session Already Active",
                        f"Session **#{active[0]}** is already active. "
                        "End it before starting another session.",
                    ),
                    ephemeral=True,
                )
                return

            cursor = await db.execute(
                """
                INSERT INTO sessions (guild_id, host_id, session_type)
                VALUES (?, ?, ?)
                """,
                (
                    interaction.guild_id,
                    interaction.user.id,
                    session_type.value,
                ),
            )

            session_id = cursor.lastrowid
            await db.commit()

        embed = make_embed(
            "SESSION MANAGEMENT | SESSION STARTED",
            "An official Atlanta Roleplay session is now active.",
            status="success",
            actor=interaction.user,
            reference=f"SESSION-{session_id:04d}",
            category=session_type.value,
        )

        section(embed, "Session Host", interaction.user.mention)
        section(embed, "Session Information", notes)
        section(embed, "Current Status", "Active", inline=True)

        await self.publish_session_announcement(interaction.channel, embed)

        await interaction.followup.send(
            embed=success_embed(
                "Session Started",
                f"Session **#{session_id}** has been created and recorded.",
                actor=interaction.user,
                reference=f"SESSION-{session_id:04d}",
                category=session_type.value,
            ),
            ephemeral=True,
        )

        await self.log_session(
            interaction.guild,
            "Session Started",
            interaction.user,
            session_id,
            session_type.value,
            notes,
            status="success",
        )

    @app_commands.command(
        name="sessionend",
        description="End the active session.",
    )
    @app_commands.describe(
        summary="Optional summary of the session",
    )
    async def sessionend(
        self,
        interaction: discord.Interaction,
        summary: str = "No summary provided.",
    ):
        if not self.can_host(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "You do not have permission to end sessions.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT id, host_id, session_type
                FROM sessions
                WHERE guild_id = ? AND status = 'Active'
                ORDER BY id DESC
                LIMIT 1
                """,
                (interaction.guild_id,),
            )

            session = await cursor.fetchone()

            if not session:
                await interaction.followup.send(
                    embed=warning_embed(
                        "No Active Session",
                        "There is currently no active session to end.",
                    ),
                    ephemeral=True,
                )
                return

            session_id, host_id, session_type = session

            await db.execute(
                """
                UPDATE sessions
                SET status = 'Ended', ended_at = CURRENT_TIMESTAMP
                WHERE id = ? AND guild_id = ?
                """,
                (session_id, interaction.guild_id),
            )

            cursor = await db.execute(
                """
                SELECT
                    SUM(CASE WHEN attendance_status = 'Present' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN attendance_status = 'Absent' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN attendance_status = 'Late' THEN 1 ELSE 0 END)
                FROM session_attendance
                WHERE session_id = ?
                """,
                (session_id,),
            )

            attendance = await cursor.fetchone()
            await db.commit()

        present_count = attendance[0] or 0
        absent_count = attendance[1] or 0
        late_count = attendance[2] or 0

        embed = make_embed(
            "SESSION MANAGEMENT | SESSION ENDED",
            "The session has been closed and its recorded attendance "
            "has been summarized.",
            status="warning",
            actor=interaction.user,
            reference=f"SESSION-{session_id:04d}",
            category=session_type,
        )

        section(embed, "Session Host", f"<@{host_id}>")
        section(embed, "Ended By", interaction.user.mention)
        section(
            embed,
            "Attendance Summary",
            f"Present: **{present_count}**\n"
            f"Absent: **{absent_count}**\n"
            f"Late: **{late_count}**",
        )
        section(embed, "Session Summary", summary)
        section(embed, "Final Status", "Ended", inline=True)

        await self.publish_session_announcement(interaction.channel, embed)

        await interaction.followup.send(
            embed=success_embed(
                "Session Ended",
                f"Session **#{session_id}** has been closed successfully.",
                actor=interaction.user,
                reference=f"SESSION-{session_id:04d}",
                category=session_type,
            ),
            ephemeral=True,
        )

        await self.log_session(
            interaction.guild,
            "Session Ended",
            interaction.user,
            session_id,
            session_type,
            (
                f"Present: {present_count}; "
                f"Absent: {absent_count}; "
                f"Late: {late_count}. Summary: {summary}"
            ),
            status="warning",
        )

    @app_commands.command(
        name="sessionlow",
        description="Announce a low session.",
    )
    async def sessionlow(
        self,
        interaction: discord.Interaction,
        notes: str = "Join if available.",
    ):
        await self.announce_session_type(
            interaction,
            "Low Session",
            notes,
        )

    @app_commands.command(
        name="sessionfull",
        description="Announce a full session.",
    )
    async def sessionfull(
        self,
        interaction: discord.Interaction,
        notes: str = "The session is full.",
    ):
        await self.announce_session_type(
            interaction,
            "Full Session",
            notes,
        )

    async def announce_session_type(
        self,
        interaction,
        session_type,
        notes,
    ):
        if not self.can_host(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "You do not have permission to announce session status.",
                ),
                ephemeral=True,
            )
            return

        embed = make_embed(
            f"SESSION MANAGEMENT | {session_type.upper()}",
            notes,
            status="info",
            actor=interaction.user,
            category=session_type,
        )

        await interaction.response.defer(ephemeral=True)
        await self.publish_session_announcement(interaction.channel, embed)

        await interaction.followup.send(
            embed=success_embed(
                "Session Announcement Published",
                f"The **{session_type}** announcement has been posted.",
                actor=interaction.user,
                category=session_type,
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="attendance",
        description="Record a member's session attendance.",
    )
    @app_commands.describe(
        member="The member whose attendance to record",
        status="Attendance status",
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(name="Present", value="Present"),
            app_commands.Choice(name="Absent", value="Absent"),
            app_commands.Choice(name="Late", value="Late"),
        ]
    )
    async def attendance(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        status: app_commands.Choice[str],
    ):
        if not self.can_host(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "You do not have permission to record attendance.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT id, session_type
                FROM sessions
                WHERE guild_id = ? AND status = 'Active'
                ORDER BY id DESC
                LIMIT 1
                """,
                (interaction.guild_id,),
            )

            session = await cursor.fetchone()

            if not session:
                await interaction.followup.send(
                    embed=warning_embed(
                        "No Active Session",
                        "Start a session before recording attendance.",
                    ),
                    ephemeral=True,
                )
                return

            session_id, session_type = session

            await db.execute(
                """
                INSERT INTO session_attendance
                (session_id, user_id, attendance_status)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id, user_id)
                DO UPDATE SET attendance_status = excluded.attendance_status
                """,
                (session_id, member.id, status.value),
            )

            await db.commit()

        embed = success_embed(
            "Attendance Recorded",
            f"Attendance for {member.mention} has been recorded.",
            actor=interaction.user,
            target=member,
            reference=f"SESSION-{session_id:04d}",
            category=session_type,
        )

        section(embed, "Attendance Status", status.value, inline=True)

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

        await self.log_session(
            interaction.guild,
            "Attendance Updated",
            interaction.user,
            session_id,
            session_type,
            f"{member} ({member.id}) recorded as {status.value}.",
            status="success",
        )

    @app_commands.command(
        name="sessionhistory",
        description="View recent session records.",
    )
    async def sessionhistory(self, interaction: discord.Interaction):
        if not self.can_host(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "You do not have permission to view session history.",
                ),
                ephemeral=True,
            )
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT id, host_id, session_type, status, created_at, ended_at
                FROM sessions
                WHERE guild_id = ?
                ORDER BY id DESC
                LIMIT 10
                """,
                (interaction.guild_id,),
            )

            records = await cursor.fetchall()

        embed = make_embed(
            "SESSION MANAGEMENT | HISTORY",
            "The ten most recent recorded sessions.",
            status="info",
        )

        if records:
            for sid, host, kind, state, started, ended in records:
                value = (
                    f"**Host:** <@{host}>\n"
                    f"**Status:** {state}\n"
                    f"**Started:** {started}\n"
                    f"**Ended:** {ended or 'Still active'}"
                )

                section(
                    embed,
                    f"Session #{sid} | {kind}",
                    value,
                )
        else:
            section(embed, "Session Records", "No sessions have been recorded.")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="sessionstats",
        description="View recorded attendance for a member.",
    )
    async def sessionstats(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        if not self.can_host(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission Denied",
                    "You do not have permission to view session statistics.",
                ),
                ephemeral=True,
            )
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT sa.attendance_status, COUNT(*)
                FROM session_attendance sa
                JOIN sessions s ON s.id = sa.session_id
                WHERE s.guild_id = ? AND sa.user_id = ?
                GROUP BY sa.attendance_status
                """,
                (interaction.guild_id, member.id),
            )

            rows = await cursor.fetchall()

        stats = {
            status: count
            for status, count in rows
        }

        embed = make_embed(
            "SESSION MANAGEMENT | ATTENDANCE RECORD",
            f"Recorded session attendance for {member.mention}.",
            status="info",
            target=member,
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        section(
            embed,
            "Present",
            str(stats.get("Present", 0)),
            inline=True,
        )
        section(
            embed,
            "Absent",
            str(stats.get("Absent", 0)),
            inline=True,
        )
        section(
            embed,
            "Late",
            str(stats.get("Late", 0)),
            inline=True,
        )

        total = sum(stats.values())

        section(
            embed,
            "Total Recorded Sessions",
            str(total),
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Sessions(bot))