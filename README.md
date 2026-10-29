# Atlanta Roleplay Management Bot

A Discord management bot for Atlanta Roleplay, built with `discord.py` and SQLite.

## Included systems

- Staff promotions, demotions, infractions, and staff records
- Session voting, session start/end announcements, attendance, and history
- Leave-of-absence requests and reviews
- Kick, ban, and timeout commands
- Roblox account linking and verification
- Private support tickets, ticket actions, transcripts, and ratings
- Member/server information, help, and management announcements
- Shared embed styling for command responses and management logs

## Requirements

- Python 3.10 or newer recommended
- A Discord application and bot token
- The bot invited to the server with the permissions required by the features you use

## Setup on macOS

1. Open this folder in VS Code.
2. Create your private environment file by copying `.env.example` to `.env`.
3. Open `.env` and set `DISCORD_TOKEN` to your bot's token. Keep this file private.
4. Open the VS Code terminal in this folder and run:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python3 -m pip install -r requirements.txt
   python3 -m compileall .
   python3 main.py
   ```

5. Keep the terminal open while the bot is running. Use `Ctrl+C` to stop it.

## Configuration

- `GUILD_ID` is set to the Atlanta Roleplay server ID in `.env.example`.
- The Session Management role ID is configured in `config.py` as `1538727238353289297`.
- Session announcements ping only that configured role. The role must exist in the server, and the bot must have permission to send messages in the announcement channel.
- Management actions and session audit records are sent to the configured `bot_logs` channel.
- Ticket transcripts and ticket audit records use the configured `ticket_logs` channel.
- Session announcements are posted in the channel where the session command is run.

## Security and data

- Never share `.env` or post your bot token in chats, screenshots, repositories, or support requests.
- `.env`, local databases, virtual environments, Python caches, and editor-specific files are excluded from the project archive.
- If your token was included in a shared ZIP or repository, reset it in the Discord Developer Portal and update your local `.env` file.
- The local SQLite database is created automatically when the bot starts. Back up your existing `atlanta_roleplay.db` before replacing or moving project files if you need to preserve records.

## Notes

Slash commands are synced to the configured server at startup. Role hierarchy and channel permissions still apply: the bot's highest role must be above any role it assigns, and the bot needs the appropriate moderation, channel, and message permissions.
