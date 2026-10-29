
import discord
import aiosqlite
import io
import re
from datetime import datetime, timezone
from discord import app_commands
from discord.ext import commands

from config import CHANNELS, ROLES, DATABASE_PATH
from embeds import (
    make_embed,
    section,
    success_embed,
    error_embed,
    warning_embed,
    audit_embed,
    ticket_embed,
    ticket_panel_embed,
)


CATEGORY_LABELS = {
    "General Support": "General Support",
    "Internal Affairs": "Internal Affairs",
    "Management": "Management Support",
    "Partnerships": "Partnership / Affiliation Support",
}

TICKET_STAFF = {
    "General Support": ("staff", "hr", "shr", "developer", "founder"),
    "Internal Affairs": ("hr", "shr", "developer", "founder"),
    "Management": ("management", "shr", "developer", "founder"),
    "Partnerships": ("partnership_support", "shr", "developer", "founder"),
}

ADMIN_ROLES = ("shr", "developer", "founder")
HR_ROLES = ("hr", "shr", "developer", "founder")
OPEN_STATUSES = ("Open", "Claimed")


def role_ids(role_names):
    return {
        int(ROLES[name])
        for name in role_names
        if name in ROLES and ROLES[name]
    }


def member_has_role(member, role_names):
    allowed = role_ids(role_names)
    return any(role.id in allowed for role in member.roles)


def is_ticket_admin(member):
    return member_has_role(member, ADMIN_ROLES)


def is_hr_or_above(member):
    return member_has_role(member, HR_ROLES)


def is_authorized_for_ticket(member, ticket_type):
    return (
        member.guild_permissions.administrator
        or is_ticket_admin(member)
        or member_has_role(member, TICKET_STAFF.get(ticket_type, ()))
    )


def ticket_reference(ticket_id):
    return f"ACR-{ticket_id:04d}"


def safe_channel_name(member, ticket_type):
    prefix = {
        "General Support": "support",
        "Internal Affairs": "internal-affairs",
        "Management": "management",
        "Partnerships": "partnerships",
    }.get(ticket_type, "ticket")

    username = re.sub(r"[^a-z0-9-]", "-", member.name.lower())
    username = re.sub(r"-+", "-", username).strip("-")[:35] or "member"

    return f"{prefix}-{username}"[:95]


async def get_ticket(channel_id):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tickets WHERE channel_id = ?",
            (channel_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_ticket_status(channel_id, status, claimed_by=None):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if claimed_by is None:
            await db.execute(
                "UPDATE tickets SET status = ? WHERE channel_id = ?",
                (status, channel_id),
            )
        else:
            await db.execute(
                "UPDATE tickets SET status = ?, claimed_by = ? "
                "WHERE channel_id = ?",
                (status, claimed_by, channel_id),
            )
        await db.commit()


async def get_log_channel(guild):
    channel_id = CHANNELS.get("ticket_logs")
    channel = guild.get_channel(channel_id) if channel_id else None

    if isinstance(channel, discord.TextChannel):
        return channel

    return None


class TicketReasonModal(discord.ui.Modal):
    def __init__(self, system, ticket_type):
        super().__init__(title="Submit Support Request")
        self.system = system
        self.ticket_type = ticket_type

        self.reason = discord.ui.TextInput(
            label="Describe your request",
            placeholder="Explain the issue and include relevant details.",
            style=discord.TextStyle.paragraph,
            min_length=10,
            max_length=1000,
            required=True,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        await self.system.create_ticket(
            interaction,
            self.ticket_type,
            str(self.reason.value).strip(),
        )


class TicketPanelSelect(discord.ui.Select):
    def __init__(self, system):
        self.system = system

        options = [
            discord.SelectOption(
                label="General Support",
                description="General questions and assistance",
                value="General Support",
            ),
            discord.SelectOption(
                label="Internal Affairs",
                description="Confidential staff conduct reports",
                value="Internal Affairs",
            ),
            discord.SelectOption(
                label="Management Support",
                description="Management-level requests and appeals",
                value="Management",
            ),
            discord.SelectOption(
                label="Partnership / Affiliation Support",
                description="Partnership enquiries and proposals",
                value="Partnerships",
            ),
        ]

        super().__init__(
            placeholder="Open a Ticket • Select a Category",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="acr_ticket_panel_select",
        )

    async def callback(self, interaction):
        await interaction.response.send_modal(
            TicketReasonModal(self.system, self.values[0])
        )


class TicketPanelView(discord.ui.View):
    def __init__(self, system):
        super().__init__(timeout=None)
        self.add_item(TicketPanelSelect(system))


class TicketControls(discord.ui.View):
    def __init__(self, system):
        super().__init__(timeout=None)
        self.system = system

    @discord.ui.button(
        label="Claim Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="acr_ticket_claim",
    )
    async def claim_button(self, interaction, button):
        await self.system.claim_ticket(interaction)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="acr_ticket_close",
    )
    async def close_button(self, interaction, button):
        record = await get_ticket(interaction.channel_id)

        if not record:
            await interaction.response.send_message(
                embed=error_embed(
                    "Ticket Not Found",
                    "This channel is not registered as a ticket.",
                ),
                ephemeral=True,
            )
            return

        if record["status"] not in OPEN_STATUSES:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Ticket Already Closed",
                    "This ticket is not currently open.",
                ),
                ephemeral=True,
            )
            return

        member = interaction.user

        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                embed=error_embed(
                    "Server Only",
                    "This action must be performed inside the Discord server.",
                ),
                ephemeral=True,
            )
            return

        if member.id != record["opener_id"] and not is_authorized_for_ticket(
            member, record["ticket_type"]
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Access Restricted",
                    "You are not authorized to close this ticket.",
                ),
                ephemeral=True,
            )
            return

        if (
            record["claimed_by"]
            and member.id != record["opener_id"]
            and member.id != record["claimed_by"]
            and not is_ticket_admin(member)
            and not member.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Ticket Assigned to Another Staff Member",
                    "Only the assigned staff member or authorized senior staff "
                    "can close this claimed ticket.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=warning_embed(
                "Confirm Ticket Closure",
                "Are you sure you want to close this ticket? A transcript "
                "will be generated and sent to the ticket log channel.",
                category=CATEGORY_LABELS.get(
                    record["ticket_type"], record["ticket_type"]
                ),
            ),
            view=CloseConfirmation(self.system),
            ephemeral=True,
        )


class CloseConfirmation(discord.ui.View):
    def __init__(self, system):
        super().__init__(timeout=60)
        self.system = system

    @discord.ui.button(
        label="Confirm Closure",
        style=discord.ButtonStyle.danger,
    )
    async def confirm(self, interaction, button):
        await self.system.close_ticket(interaction)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(self, interaction, button):
        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            embed=info_embed_for_cancel(),
            view=self,
        )


def info_embed_for_cancel():
    return success_embed(
        "Closure Cancelled",
        "The ticket remains open. No closure was performed.",
    )


class TicketRating(discord.ui.View):
    def __init__(self, ticket_id, guild_id):
        super().__init__(timeout=300)
        self.ticket_id = ticket_id
        self.guild_id = guild_id

        for rating in range(1, 6):
            button = discord.ui.Button(
                label=str(rating),
                style=discord.ButtonStyle.secondary,
                custom_id=f"acr_rating_{ticket_id}_{rating}",
            )

            async def callback(interaction, score=rating):
                await self.save_rating(interaction, score)

            button.callback = callback
            self.add_item(button)

    async def save_rating(self, interaction, rating):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_ratings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticket_id, user_id)
                )
                """
            )

            try:
                await db.execute(
                    """
                    INSERT INTO ticket_ratings
                    (ticket_id, guild_id, user_id, rating)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        self.ticket_id,
                        self.guild_id,
                        interaction.user.id,
                        rating,
                    ),
                )
                await db.commit()
            except aiosqlite.IntegrityError:
                await interaction.response.send_message(
                    embed=warning_embed(
                        "Rating Already Submitted",
                        "You have already submitted a rating for this ticket.",
                    ),
                    ephemeral=True,
                )
                return

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            embed=success_embed(
                "Feedback Received",
                f"Thank you. Your support rating of **{rating}/5** "
                "has been recorded.",
                reference=ticket_reference(self.ticket_id),
            ),
            view=self,
        )


class TicketSystem:
    def __init__(self, bot):
        self.bot = bot

    async def log(self, guild, embed, file=None):
        channel = await get_log_channel(guild)

        if not channel:
            return

        try:
            await channel.send(embed=embed, file=file)
        except discord.HTTPException:
            pass

    async def create_ticket(self, interaction, ticket_type, reason):
        guild = interaction.guild
        opener = interaction.user

        if guild is None or not isinstance(opener, discord.Member):
            await interaction.followup.send(
                embed=error_embed(
                    "Server Only",
                    "Tickets can only be opened inside the Discord server.",
                ),
                ephemeral=True,
            )
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                """
                SELECT channel_id FROM tickets
                WHERE guild_id = ? AND opener_id = ? AND status IN (?, ?)
                """,
                (guild.id, opener.id, "Open", "Claimed"),
            )
            existing = await cursor.fetchone()

        if existing:
            existing_channel = guild.get_channel(existing[0])
            destination = (
                existing_channel.mention
                if existing_channel
                else "your existing ticket channel"
            )

            await interaction.followup.send(
                embed=warning_embed(
                    "Existing Ticket Found",
                    f"You already have an open ticket: {destination}. "
                    "Please continue using that ticket.",
                ),
                ephemeral=True,
            )
            return

        category_id = CHANNELS.get("ticket_category")
        category = guild.get_channel(category_id) if category_id else None

        if category is not None and not isinstance(
            category, discord.CategoryChannel
        ):
            category = None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            )
        }

        overwrites[opener] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
        )

        bot_member = guild.me
        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True,
            )

        for role_name in TICKET_STAFF.get(ticket_type, ()):
            configured_id = ROLES.get(role_name)
            role = guild.get_role(int(configured_id)) if configured_id else None

            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                )

        try:
            channel = await guild.create_text_channel(
                name=safe_channel_name(opener, ticket_type),
                category=category,
                overwrites=overwrites,
                topic=(
                    f"Atlanta Roleplay ticket | {ticket_type} | "
                    f"Opened by {opener.id}"
                ),
                reason=f"Support ticket opened by {opener} ({opener.id})",
            )
        except discord.HTTPException:
            await interaction.followup.send(
                embed=error_embed(
                    "Ticket Creation Failed",
                    "The bot could not create your ticket channel. "
                    "Please contact server management.",
                ),
                ephemeral=True,
            )
            return

        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO tickets
                    (guild_id, channel_id, opener_id, ticket_type, status, reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild.id,
                        channel.id,
                        opener.id,
                        ticket_type,
                        "Open",
                        reason,
                    ),
                )
                await db.commit()
                ticket_id = cursor.lastrowid
        except Exception:
            await channel.delete(
                reason="Ticket database registration failed"
            )
            await interaction.followup.send(
                embed=error_embed(
                    "Ticket Registration Failed",
                    "The ticket could not be registered. Please try again.",
                ),
                ephemeral=True,
            )
            raise

        embed = ticket_embed(
            ticket_number=ticket_id,
            ticket_type=CATEGORY_LABELS.get(ticket_type, ticket_type),
            opener=opener,
            reason=reason,
            status="Open",
        )

        await channel.send(
            content=opener.mention,
            embed=embed,
            view=TicketControls(self),
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
            ),
        )

        await self.log(
            guild,
            audit_embed(
                title="Ticket Created",
                actor=opener,
                target=opener,
                reason=reason,
                reference=ticket_reference(ticket_id),
                category=CATEGORY_LABELS.get(ticket_type, ticket_type),
                status="info",
            ),
        )

        await interaction.followup.send(
            embed=success_embed(
                "Ticket Created Successfully",
                f"Your private support ticket is ready: {channel.mention}",
                reference=ticket_reference(ticket_id),
                category=CATEGORY_LABELS.get(ticket_type, ticket_type),
            ),
            ephemeral=True,
        )

    async def update_ticket_embed(self, channel, record, include_controls=True):
        guild = channel.guild
        opener = guild.get_member(record["opener_id"])
        if opener is None:
            opener = discord.Object(id=record["opener_id"])

        claimant = (
            guild.get_member(record["claimed_by"])
            if record["claimed_by"]
            else None
        )

        embed = ticket_embed(
            ticket_number=record["id"],
            ticket_type=CATEGORY_LABELS.get(
                record["ticket_type"], record["ticket_type"]
            ),
            opener=opener,
            reason=record["reason"],
            status=record["status"],
            claimed_by=claimant,
        )

        async for message in channel.history(limit=50, oldest_first=True):
            if message.author.id != self.bot.user.id:
                continue

            if message.embeds and message.embeds[0].title:
                if message.embeds[0].title.startswith("SUPPORT SERVICES"):
                    await message.edit(
                        embed=embed,
                        view=TicketControls(self) if include_controls else None,
                    )
                    return

    async def claim_ticket(self, interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed(
                    "Server Only",
                    "This action must be performed inside the Discord server.",
                ),
                ephemeral=True,
            )
            return

        channel = interaction.channel
        record = await get_ticket(interaction.channel_id)

        if not record or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed(
                    "Ticket Not Found",
                    "This channel is not registered as a ticket.",
                ),
                ephemeral=True,
            )
            return

        if record["status"] not in OPEN_STATUSES:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Ticket Unavailable",
                    "Only open tickets can be claimed.",
                ),
                ephemeral=True,
            )
            return

        if not is_authorized_for_ticket(
            interaction.user, record["ticket_type"]
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Access Restricted",
                    "You do not have permission to claim this ticket category.",
                ),
                ephemeral=True,
            )
            return

        if record["claimed_by"] and record["claimed_by"] != interaction.user.id:
            if not is_ticket_admin(interaction.user):
                await interaction.response.send_message(
                    embed=warning_embed(
                        "Already Assigned",
                        "This ticket has already been claimed by another staff member.",
                    ),
                    ephemeral=True,
                )
                return

        await interaction.response.defer(ephemeral=True, thinking=True)

        await update_ticket_status(
            channel.id,
            "Claimed",
            interaction.user.id,
        )

        senior_ids = role_ids(ADMIN_ROLES)
        opener_id = record["opener_id"]

        for target, old_overwrite in list(channel.overwrites.items()):
            overwrite = old_overwrite.copy()

            if isinstance(target, discord.Role):
                if target.id in role_ids(TICKET_STAFF.get(record["ticket_type"], ())):
                    overwrite.view_channel = True
                    overwrite.read_message_history = True
                    overwrite.send_messages = target.id in senior_ids
                    await channel.set_permissions(target, overwrite=overwrite)

            elif isinstance(target, discord.Member):
                if target.id == opener_id or target.id == interaction.user.id:
                    overwrite.view_channel = True
                    overwrite.read_message_history = True
                    overwrite.send_messages = True
                    await channel.set_permissions(target, overwrite=overwrite)
                elif target.id == self.bot.user.id:
                    overwrite.view_channel = True
                    overwrite.send_messages = True
                    await channel.set_permissions(target, overwrite=overwrite)
                elif member_has_role(target, ADMIN_ROLES):
                    overwrite.view_channel = True
                    overwrite.send_messages = True
                    await channel.set_permissions(target, overwrite=overwrite)
                else:
                    overwrite.view_channel = True
                    overwrite.read_message_history = True
                    overwrite.send_messages = False
                    await channel.set_permissions(target, overwrite=overwrite)

        record["claimed_by"] = interaction.user.id
        record["status"] = "Claimed"

        await self.update_ticket_embed(channel, record)

        await channel.send(
            embed=success_embed(
                "Ticket Assigned",
                f"This ticket has been assigned to {interaction.user.mention}. "
                "Please keep all replies relevant to the request.",
                actor=interaction.user,
                reference=ticket_reference(record["id"]),
                category=CATEGORY_LABELS.get(
                    record["ticket_type"], record["ticket_type"]
                ),
            )
        )

        await self.log(
            interaction.guild,
            audit_embed(
                title="Ticket Claimed",
                actor=interaction.user,
                target=interaction.user,
                reference=ticket_reference(record["id"]),
                category=CATEGORY_LABELS.get(
                    record["ticket_type"], record["ticket_type"]
                ),
                status="success",
            ),
        )

        await interaction.followup.send(
            embed=success_embed(
                "Ticket Claimed",
                f"You are now assigned to {channel.mention}.",
                reference=ticket_reference(record["id"]),
            ),
            ephemeral=True,
        )

    async def close_ticket(self, interaction):
        channel = interaction.channel
        record = await get_ticket(interaction.channel_id)

        if not record or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed(
                    "Ticket Not Found",
                    "This channel is not registered as a ticket.",
                ),
                ephemeral=True,
            )
            return

        if record["status"] not in OPEN_STATUSES:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Ticket Already Closed",
                    "This ticket has already been closed.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        transcript_lines = [
            f"ATLANTA ROLEPLAY | TICKET TRANSCRIPT",
            f"Reference: {ticket_reference(record['id'])}",
            f"Category: {CATEGORY_LABELS.get(record['ticket_type'], record['ticket_type'])}",
            f"Opened by: {record['opener_id']}",
            f"Reason: {record['reason']}",
            f"Status before closure: {record['status']}",
            f"Claimed by: {record['claimed_by'] or 'Unassigned'}",
            "",
            "=" * 72,
            "",
        ]

        async for message in channel.history(limit=1000, oldest_first=True):
            created = message.created_at.astimezone(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
            author = f"{message.author} ({message.author.id})"
            content = message.content or ""

            if message.embeds:
                embed_titles = [
                    item.title for item in message.embeds if item.title
                ]
                if embed_titles:
                    content += f" [Embed: {'; '.join(embed_titles)}]"

            if message.attachments:
                content += " [Attachments: " + ", ".join(
                    attachment.url for attachment in message.attachments
                ) + "]"

            transcript_lines.append(
                f"[{created}] {author}\n{content}\n"
            )

        transcript_data = "\n".join(transcript_lines).encode(
            "utf-8", errors="replace"
        )

        transcript_file = discord.File(
            io.BytesIO(transcript_data),
            filename=f"{ticket_reference(record['id'])}-transcript.txt",
        )

        await update_ticket_status(channel.id, "Closed")

        for target, old_overwrite in list(channel.overwrites.items()):
            overwrite = old_overwrite.copy()

            if isinstance(target, discord.Role):
                if target.id in role_ids(
                    TICKET_STAFF.get(record["ticket_type"], ())
                ):
                    overwrite.view_channel = True
                    overwrite.read_message_history = True
                    overwrite.send_messages = False
                    await channel.set_permissions(target, overwrite=overwrite)

            elif isinstance(target, discord.Member):
                overwrite.view_channel = True
                overwrite.read_message_history = True
                overwrite.send_messages = False
                await channel.set_permissions(target, overwrite=overwrite)

        closed_embed = make_embed(
            title="SUPPORT SERVICES | TICKET CLOSED",
            description=(
                "This ticket has been closed. The transcript has been "
                "submitted to the designated ticket log channel."
            ),
            status="neutral",
            reference=ticket_reference(record["id"]),
            category=CATEGORY_LABELS.get(
                record["ticket_type"], record["ticket_type"]
            ),
        )
        section(closed_embed, "Original Request", record["reason"])
        section(
            closed_embed,
            "Closed By",
            f"{interaction.user.mention}\n`{interaction.user.id}`",
        )

        await channel.send(embed=closed_embed, view=None)

        log_embed = audit_embed(
            title="Ticket Closed",
            actor=interaction.user,
            reference=ticket_reference(record["id"]),
            category=CATEGORY_LABELS.get(
                record["ticket_type"], record["ticket_type"]
            ),
            reason=record["reason"],
            status="neutral",
        )

        await self.log(interaction.guild, log_embed, file=transcript_file)

        opener = interaction.guild.get_member(record["opener_id"])

        if opener:
            rating_embed = make_embed(
                title="SUPPORT FEEDBACK | RATE YOUR EXPERIENCE",
                description=(
                    "Your ticket has been closed. If you have a moment, "
                    "please rate your support experience below. Your feedback "
                    "helps us improve the quality of our support services."
                ),
                status="info",
                reference=ticket_reference(record["id"]),
            )
            section(
                rating_embed,
                "Rating Scale",
                "1 = Very poor\n2 = Poor\n3 = Satisfactory\n"
                "4 = Good\n5 = Excellent",
            )

            try:
                await opener.send(
                    embed=rating_embed,
                    view=TicketRating(record["id"], interaction.guild_id),
                )
            except discord.HTTPException:
                pass

        await interaction.followup.send(
            embed=success_embed(
                "Ticket Closed",
                "The ticket has been closed and the transcript process completed.",
                reference=ticket_reference(record["id"]),
            ),
            ephemeral=True,
        )


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.system = TicketSystem(bot)

    async def cog_load(self):
        self.bot.add_view(TicketPanelView(self.system))
        self.bot.add_view(TicketControls(self.system))

    @app_commands.command(
        name="ticketpanel",
        description="Post the official support ticket panel.",
    )
    @app_commands.guild_only()
    async def ticketpanel(self, interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed(
                    "Server Only",
                    "This command must be used inside the Discord server.",
                ),
                ephemeral=True,
            )
            return

        if not (
            is_ticket_admin(interaction.user)
            or interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Access Restricted",
                    "Only authorized senior staff can publish the ticket panel.",
                ),
                ephemeral=True,
            )
            return

        target_id = CHANNELS.get("support")
        target = interaction.guild.get_channel(target_id) if target_id else None

        if not isinstance(target, discord.TextChannel):
            target = interaction.channel

        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed(
                    "Channel Unavailable",
                    "The configured support channel could not be found.",
                ),
                ephemeral=True,
            )
            return

        await target.send(
            embed=ticket_panel_embed(),
            view=TicketPanelView(self.system),
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Ticket Panel Published",
                f"The official support panel has been posted in {target.mention}.",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="ticketadd",
        description="Give a member access to the current ticket.",
    )
    @app_commands.describe(member="Member to add to this ticket")
    @app_commands.guild_only()
    async def ticketadd(self, interaction, member: discord.Member):
        record = await get_ticket(interaction.channel_id)

        if not record or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed(
                    "Ticket Not Found",
                    "Use this command inside a registered ticket channel.",
                ),
                ephemeral=True,
            )
            return

        if not is_hr_or_above(interaction.user) and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=error_embed(
                    "Access Restricted",
                    "Only HR or authorized senior staff can manage ticket access.",
                ),
                ephemeral=True,
            )
            return

        if record["status"] not in OPEN_STATUSES:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Ticket Closed",
                    "Reopen the ticket before changing its access.",
                ),
                ephemeral=True,
            )
            return

        if member.id == record["opener_id"]:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Access Already Granted",
                    "The ticket owner already has access to this ticket.",
                ),
                ephemeral=True,
            )
            return

        can_speak = (
            not record["claimed_by"]
            or member.id == record["claimed_by"]
            or member_has_role(member, ADMIN_ROLES)
        )

        await interaction.channel.set_permissions(
            member,
            view_channel=True,
            read_message_history=True,
            send_messages=can_speak,
            attach_files=can_speak,
            embed_links=can_speak,
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Ticket Access Updated",
                f"{member.mention} has been added to this ticket.",
                actor=interaction.user,
                target=member,
                reference=ticket_reference(record["id"]),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="ticketremove",
        description="Remove a member's access to the current ticket.",
    )
    @app_commands.describe(member="Member to remove from this ticket")
    @app_commands.guild_only()
    async def ticketremove(self, interaction, member: discord.Member):
        record = await get_ticket(interaction.channel_id)

        if not record or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed(
                    "Ticket Not Found",
                    "Use this command inside a registered ticket channel.",
                ),
                ephemeral=True,
            )
            return

        if not is_hr_or_above(interaction.user) and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=error_embed(
                    "Access Restricted",
                    "Only HR or authorized senior staff can manage ticket access.",
                ),
                ephemeral=True,
            )
            return

        if member.id == record["opener_id"]:
            await interaction.response.send_message(
                embed=error_embed(
                    "Action Not Allowed",
                    "The ticket owner cannot be removed from their own ticket.",
                ),
                ephemeral=True,
            )
            return

        await interaction.channel.set_permissions(member, overwrite=None)

        await interaction.response.send_message(
            embed=success_embed(
                "Ticket Access Removed",
                f"{member.mention}'s individual ticket access has been removed.",
                actor=interaction.user,
                target=member,
                reference=ticket_reference(record["id"]),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="ticketreopen",
        description="Reopen a closed ticket.",
    )
    @app_commands.describe(reason="Reason for reopening the ticket")
    @app_commands.guild_only()
    async def ticketreopen(self, interaction, reason: str):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed(
                    "Server Only",
                    "This command must be used inside the Discord server.",
                ),
                ephemeral=True,
            )
            return

        if not (
            is_ticket_admin(interaction.user)
            or interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Access Restricted",
                    "Only authorized senior staff can reopen closed tickets.",
                ),
                ephemeral=True,
            )
            return

        channel = interaction.channel
        record = await get_ticket(interaction.channel_id)

        if not record or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed(
                    "Ticket Not Found",
                    "Use this command inside a registered ticket channel.",
                ),
                ephemeral=True,
            )
            return

        if record["status"] in OPEN_STATUSES:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Ticket Already Open",
                    "This ticket is already open.",
                ),
                ephemeral=True,
            )
            return

        opener = interaction.guild.get_member(record["opener_id"])

        if opener:
            await channel.set_permissions(
                opener,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            )

        senior_ids = role_ids(ADMIN_ROLES)
        assigned_id = record["claimed_by"]

        for role_name in TICKET_STAFF.get(record["ticket_type"], ()):
            configured_id = ROLES.get(role_name)
            role = (
                interaction.guild.get_role(int(configured_id))
                if configured_id
                else None
            )

            if role:
                can_speak = role.id in senior_ids or not assigned_id
                await channel.set_permissions(
                    role,
                    view_channel=True,
                    send_messages=can_speak,
                    read_message_history=True,
                    attach_files=can_speak,
                    embed_links=can_speak,
                )

        if assigned_id:
            claimant = interaction.guild.get_member(assigned_id)
            if claimant:
                await channel.set_permissions(
                    claimant,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                )

        await update_ticket_status(channel.id, "Claimed" if assigned_id else "Open")

        record["status"] = "Claimed" if assigned_id else "Open"
        await self.system.update_ticket_embed(channel, record)

        await channel.send(
            embed=success_embed(
                "Ticket Reopened",
                f"This ticket has been reopened by {interaction.user.mention}.\n\n"
                f"**Reason:** {reason}",
                actor=interaction.user,
                reference=ticket_reference(record["id"]),
            ),
            view=TicketControls(self.system),
        )

        await self.system.log(
            interaction.guild,
            audit_embed(
                title="Ticket Reopened",
                actor=interaction.user,
                reference=ticket_reference(record["id"]),
                category=CATEGORY_LABELS.get(
                    record["ticket_type"], record["ticket_type"]
                ),
                reason=reason,
                status="success",
            ),
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Ticket Reopened",
                f"{channel.mention} is now available again.",
                reference=ticket_reference(record["id"]),
            ),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Tickets(bot))
