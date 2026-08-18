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

## Copyright and use

Copyright (c) 2026 Muneer Mahmoud. All rights reserved.

This project is proprietary. Viewing the source on GitHub does not grant permission to use, copy, modify, distribute, sublicense, sell, or otherwise exploit it. See the [proprietary copyright notice](LICENSE). Third-party materials remain subject to their respective owners' rights and license terms.
