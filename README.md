# Discord Organizer Bot

A practical, all-in-one Discord bot for organizing server content, administering channels, creating polished messages, and adding lightweight community utilities. It combines message and channel migration tools with moderation-oriented workflows, reusable welcome templates, interactive polls, QR-code generation, and built-in games—all through Discord slash commands.

## Highlights

- **Server organization:** copy channels, categories, forum threads, messages, embeds, attachments, and supported reply relationships.
- **Content management:** duplicate or repost channels, purge channel/category messages, edit bot-authored messages and embeds, and add scroll-to-top buttons.
- **Archiving workflow:** configure an archive category, move channels into it, lock them, and apply an archive prefix.
- **Server insights:** audit channels or categories to summarize activity and content.
- **Rich community tools:** publish embeds, custom link buttons, reaction polls, and customized QR codes.
- **Reusable onboarding:** save named welcome templates and send them with role-based access control.
- **Interactive games:** play Tic-Tac-Toe against another member or the bot, plus solo Sudoku.
- **Discord-native UX:** slash commands, channel/category pickers, autocomplete, buttons, selects, ephemeral confirmations, and permission checks.
- **Lightweight persistence:** stores archive settings and welcome templates locally in `bot_data.json`.

## Technology

- Python 3.10+
- [discord.py](https://discordpy.readthedocs.io/) with application commands and UI components
- [Pillow](https://python-pillow.org/) and [qrcode](https://pypi.org/project/qrcode/) for QR-code image generation

## Setup

1. Clone the repository and enter its directory.
2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. In the [Discord Developer Portal](https://discord.com/developers/applications), create an application and bot. Enable the **Message Content** and **Server Members** privileged gateway intents used by this project.
5. Invite the bot to your server with the `bot` and `applications.commands` scopes. Grant only the permissions needed for the commands you plan to use; organization and cleanup commands generally require elevated channel-management permissions.
6. Copy `.env.example` to `.env`, replace the placeholder with your token, and load it into your shell before starting the bot:

   ```powershell
   # PowerShell
   $env:DISCORD_BOT_TOKEN = (Get-Content .env | Select-String '^DISCORD_BOT_TOKEN=').Line.Split('=', 2)[1]
   python bot.py
   ```

   ```bash
   # macOS/Linux
   set -a; source .env; set +a
   python bot.py
   ```

> `.env` is intentionally ignored by Git. Never commit or share a real Discord bot token.

## Usage

Start the bot with `python bot.py`. Once it connects, application commands are synchronized automatically. Type `/` in a server channel to browse the available commands.

Key command groups include:

| Area | Commands |
| --- | --- |
| Copy and organize | `/copy_channel`, `/copy_category`, `/copy_forum`, `/duplicate_channel`, `/repost_channel` |
| Manage content | `/send_message`, `/embed`, `/edit_message`, `/edit_embed`, `/webhook`, `/delete_channel`, `/delete_category` |
| Navigation and review | `/audit`, `/stt_button`, `/stt_button_category` |
| Community tools | `/poll`, `/custom_button`, `/qr_code`, `/set_welcome`, `/welcome` |
| Archiving | `/set_archive_category`, `/archive_channel` |
| Games | `/tictactoe`, `/sudoku` |

Administrative commands enforce Discord permission checks where implemented. Always test destructive commands in a private test server before using them on important content.

## Project Structure

```text
Discord-Organizer-Bot/
├── bot.py              # Bot commands, UI components, and runtime entry point
├── requirements.txt    # Python dependencies
├── .env.example        # Safe configuration template
├── .gitignore          # Secrets, caches, local state, and editor exclusions
├── LICENSE             # MIT License
└── README.md            # Project documentation
```

`bot_data.json` is created at runtime and is intentionally not committed because it contains server-specific configuration and welcome-message content.

## Screenshots / Demo

No screenshots are bundled. For a portfolio demo, consider adding screenshots captured in a dedicated test server with member names, server IDs, invite links, and other private information removed.

## Important Notes

- Copying or reposting a large message history can take time because the bot intentionally pauses between operations and is subject to Discord rate limits.
- Discord API constraints mean copied content may not preserve every aspect of the original message exactly (for example, original authorship and some thread or message metadata).
- Purge, repost, archive, and copy operations can materially alter server content. Use least-privilege permissions and test first.
- Local JSON persistence is suitable for a single bot process. Multi-instance deployment would require shared storage and concurrency controls.
- The bot synchronizes commands globally at startup; Discord may take time to show newly registered global commands.

## License

Licensed under the [MIT License](LICENSE).
