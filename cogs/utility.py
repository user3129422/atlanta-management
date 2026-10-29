import discord
from discord import app_commands
from discord.ext import commands

from config import ROLES
from embeds import make_embed, section, success_embed, error_embed, info_embed


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="info",
        description="View information about a server member.",
    )
    @app_commands.guild_only()
    @app_commands.describe(member="The member to look up")
    async def info(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        roles = [
            role.mention
            for role in reversed(member.roles)
            if role != interaction.guild.default_role
        ]

        embed = make_embed(
            title="MEMBER INFORMATION",
            description=f"Information for {member.mention}.",
            status="info",
            actor=interaction.user,
            target=member,
            category="Member Lookup",
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        section(embed, "Username", str(member), inline=True)
        section(embed, "User ID", str(member.id), inline=True)
        section(
            embed,
            "Account Created",
            discord.utils.format_dt(member.created_at, style="F"),
        )
        section(
            embed,
            "Joined Server",
            discord.utils.format_dt(member.joined_at, style="F")
            if member.joined_at
            else "Unknown",
        )
        section(embed, "Roles", ", ".join(roles) if roles else "No roles")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="serverinfo",
        description="View information about this server.",
    )
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild

        embed = make_embed(
            title="SERVER INFORMATION",
            description=f"Information for **{guild.name}**.",
            status="info",
            actor=interaction.user,
            category="Server Overview",
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        section(embed, "Server ID", str(guild.id), inline=True)
        section(
            embed,
            "Members",
            str(guild.member_count or "Unknown"),
            inline=True,
        )
        section(
            embed,
            "Created",
            discord.utils.format_dt(guild.created_at, style="F"),
        )
        section(embed, "Text Channels", str(len(guild.text_channels)), inline=True)
        section(embed, "Voice Channels", str(len(guild.voice_channels)), inline=True)
        section(embed, "Categories", str(len(guild.categories)), inline=True)

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="announce",
        description="Post an announcement in a selected channel.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        channel="Where to post the announcement",
        message="Announcement content",
    )
    async def announce(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str,
    ):
        if not self.has_management_access(interaction.user):
            await interaction.response.send_message(
                embed=error_embed(
                    "ACCESS DENIED",
                    "You do not have permission to use the announcement command.",
                ),
                ephemeral=True,
            )
            return

        bot_member = interaction.guild.get_member(self.bot.user.id)
        if bot_member is None or not channel.permissions_for(bot_member).send_messages or not channel.permissions_for(bot_member).embed_links:
            await interaction.response.send_message(
                embed=error_embed(
                    "MISSING CHANNEL PERMISSIONS",
                    f"I cannot send messages in {channel.mention}.",
                ),
                ephemeral=True,
            )
            return

        embed = make_embed(
            title="ATLANTA ROLEPLAY | ANNOUNCEMENT",
            description=message,
            status="info",
            actor=interaction.user,
            category="Official Announcement",
        )

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed(
                    "ANNOUNCEMENT FAILED",
                    "Discord denied permission to post in that channel.",
                ),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed(
                    "ANNOUNCEMENT FAILED",
                    "Discord encountered an error while posting the announcement.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "ANNOUNCEMENT POSTED",
                f"Your announcement was posted in {channel.mention}.",
                actor=interaction.user,
                category="Announcement",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="help",
        description="View the bot's command categories.",
    )
    @app_commands.guild_only()
    async def help(self, interaction: discord.Interaction):
        embed = make_embed(
            title="ATLANTA ROLEPLAY | BOT COMMANDS",
            description=(
                "Use `/` to browse available commands. "
                "Your available commands depend on your server permissions."
            ),
            status="info",
            category="Command Guide",
        )

        section(
            embed,
            "STAFF MANAGEMENT",
            "Promotions, demotions, infractions, staff history, and staff records.",
        )
        section(
            embed,
            "SESSIONS",
            "Session voting, hosting, attendance, and session history.",
        )
        section(
            embed,
            "LEAVE OF ABSENCE",
            "Submit, review, approve, deny, and end leave requests.",
        )
        section(
            embed,
            "SUPPORT TICKETS",
            "Open support tickets, claim cases, manage access, and review transcripts.",
        )
        section(
            embed,
            "ROBLOX",
            "Link, verify, view, and unlink Roblox accounts.",
        )
        section(
            embed,
            "MODERATION",
            "Kick, ban, and timeout members, subject to role permissions.",
        )
        section(
            embed,
            "UTILITY",
            "View member information, inspect server details, and post announcements.",
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    def has_management_access(self, member):
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


async def setup(bot):
    await bot.add_cog(Utility(bot))