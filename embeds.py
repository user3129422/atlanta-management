
import discord
from datetime import datetime, timezone

BRAND = "ATLANTA ROLEPLAY"
FOOTER = "ATLANTA ROLEPLAY  •  MANAGEMENT SYSTEMS"

COLORS = {
    "success": discord.Color.from_rgb(47, 125, 79),
    "error": discord.Color.from_rgb(160, 52, 52),
    "warning": discord.Color.from_rgb(185, 125, 43),
    "info": discord.Color.from_rgb(47, 58, 74),
    "neutral": discord.Color.from_rgb(65, 72, 82),
}


def make_embed(
    title,
    description=None,
    status="info",
    reference=None,
    actor=None,
    target=None,
    category=None,
):
    embed = discord.Embed(
        title=title,
        description=description,
        color=COLORS.get(status.lower(), COLORS["info"]),
        timestamp=datetime.now(timezone.utc),
    )

    embed.set_author(name=BRAND)

    if category:
        embed.add_field(
            name="CATEGORY",
            value=str(category)[:1024],
            inline=True,
        )

    if reference:
        embed.add_field(
            name="REFERENCE",
            value=f"`{reference}`",
            inline=True,
        )

    if actor:
        embed.add_field(
            name="ACTIONED BY",
            value=f"{actor.mention}\n`{actor.id}`",
            inline=True,
        )

    if target:
        embed.add_field(
            name="MEMBER",
            value=f"{target.mention}\n`{target.id}`",
            inline=True,
        )

    embed.set_footer(text=FOOTER)
    return embed


def section(embed, title, value, inline=False):
    text_value = str(value).strip() if value is not None else ""

    if not text_value:
        text_value = "Not provided."

    # Discord embed field values have a 1,024-character limit.
    if len(text_value) > 1024:
        text_value = text_value[:1009].rstrip() + "… [truncated]"

    embed.add_field(
        name=str(title).strip().upper()[:256] or "DETAILS",
        value=text_value,
        inline=inline,
    )
    return embed


def success_embed(title, description=None, **kwargs):
    return make_embed(
        title,
        description,
        status="success",
        **kwargs,
    )


def error_embed(title, description=None, **kwargs):
    return make_embed(
        title,
        description,
        status="error",
        **kwargs,
    )


def warning_embed(title, description=None, **kwargs):
    return make_embed(
        title,
        description,
        status="warning",
        **kwargs,
    )


def info_embed(title, description=None, **kwargs):
    return make_embed(
        title,
        description,
        status="info",
        **kwargs,
    )


def audit_embed(
    title,
    actor,
    target=None,
    reason=None,
    reference=None,
    category=None,
    details=None,
    status="info",
):
    embed = make_embed(
        title=title,
        description="This action has been recorded by the management system.",
        status=status,
        reference=reference,
        actor=actor,
        target=target,
        category=category,
    )

    if reason:
        section(embed, "Reason", reason)

    if details:
        section(embed, "Additional Details", details)

    return embed


def ticket_embed(
    ticket_number,
    ticket_type,
    opener,
    reason,
    status="Open",
    claimed_by=None,
):
    embed = make_embed(
        title=f"SUPPORT SERVICES | {ticket_type.upper()}",
        description=(
            "Your request has been registered with Atlanta Roleplay Support.\n\n"
            "Please keep messages relevant to this request and provide any "
            "information needed to review it."
        ),
        status="info",
        reference=f"ACR-{ticket_number:04d}",
        target=opener,
        category=ticket_type,
    )

    section(embed, "Current Status", status, inline=True)
    section(
        embed,
        "Assigned Staff",
        claimed_by.mention if claimed_by else "Awaiting assignment",
        inline=True,
    )
    section(embed, "Request Summary", reason)

    section(
        embed,
        "Support Process",
        "01  Request received\n"
        "02  Authorized staff review\n"
        "03  Additional information collected if needed\n"
        "04  Resolution and closure",
    )

    section(
        embed,
        "Privacy and Security",
        "Channel access is controlled by ticket category and staff permissions. "
        "Never share passwords, authentication codes, or private account credentials.",
    )

    return embed


def action_embed(
    title,
    description,
    actor,
    target=None,
    reason=None,
    reference=None,
    category=None,
    status="success",
):
    embed = make_embed(
        title=title,
        description=description,
        status=status,
        reference=reference,
        actor=actor,
        target=target,
        category=category,
    )

    if reason:
        section(embed, "Reason", reason)

    return embed


def ticket_panel_embed():
    embed = make_embed(
        title="ATLANTA ROLEPLAY | SUPPORT CENTER",
        description=(
            "Welcome to the official support center.\n\n"
            "Select the category that best matches your request. A private "
            "ticket will be created for your case and made available to the "
            "appropriate support team."
        ),
        status="info",
    )

    section(
        embed,
        "01 | General Support",
        "For general questions, community assistance, technical issues, "
        "or help with server procedures.",
    )

    section(
        embed,
        "02 | Internal Affairs",
        "For confidential staff reports, conduct concerns, or matters "
        "requiring Internal Affairs review.",
    )

    section(
        embed,
        "03 | Management Support",
        "For management-level concerns, appeals, or matters requiring "
        "review by the Management team.",
    )

    section(
        embed,
        "04 | Partnership / Affiliation Support",
        "For partnership enquiries, affiliation proposals, and existing "
        "partnership matters.",
    )

    section(
        embed,
        "What Happens Next?",
        "1. Select a category from the dropdown below.\n"
        "2. Provide a clear reason for your request.\n"
        "3. The appropriate team will review your ticket.\n"
        "4. Follow staff instructions and wait for a response.",
    )

    section(
        embed,
        "Community Expectations",
        "Provide accurate information, remain respectful, and do not open "
        "duplicate tickets for the same issue. Ticket access is restricted "
        "according to category and staff permissions.",
    )

    return embed
