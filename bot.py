import discord
import asyncio
import io
import json
import os
import re
import random
import qrcode
from PIL import Image
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View
from typing import Optional
from functools import partial

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# =========================
# KEEP ALIVE
# =========================
@tasks.loop(hours=1)
async def keep_alive():
    print("Bot is alive and running!")

# =========================
# ON READY
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    keep_alive.start()
    print(f'Bot is ready. Logged in as {bot.user}')

# =========================
# CORE COPY HELPERS
# =========================
async def copy_message(source_channel, target_channel, message_mapping, message):
    try:
        reference_message = None
        if message.reference and message.reference.resolved:
            referenced_id = message.reference.resolved.id
            if referenced_id in message_mapping:
                reference_message = message_mapping[referenced_id]

        if message.content and not message.thread:
            sent_message = await target_channel.send(message.content, reference=reference_message)
            message_mapping[message.id] = sent_message

        if message.embeds and not message.thread:
            for embed in message.embeds:
                sent_message = await target_channel.send(embed=embed, reference=reference_message)
                message_mapping[message.id] = sent_message
                await asyncio.sleep(1)

        if message.attachments:
            is_voice_message = any(
                getattr(a, 'is_voice_message', lambda: False)()
                for a in message.attachments
            )
            if is_voice_message:
                for attachment in message.attachments:
                    file = await attachment.to_file()
                    sent_message = await target_channel.send(
                        files=[file],
                        reference=reference_message,
                        flags=discord.MessageFlags(voice=True) if attachment.is_voice_message() else discord.MessageFlags()
                    )
                    message_mapping[message.id] = sent_message
            else:
                files = [await attachment.to_file() for attachment in message.attachments]
                sent_message = await target_channel.send(files=files, reference=reference_message)
                message_mapping[message.id] = sent_message

        if message.thread:
            source_thread = message.thread
            target_thread = await target_channel.create_thread(
                name=source_thread.name,
                type=source_thread.type
            )
            message_mapping[source_thread.id] = target_thread
            await copy_messages_and_threads(source_thread, target_thread, message_mapping, in_thread=True)

        await asyncio.sleep(1)
    except Exception as e:
        print(f'Error copying message: {e}')


async def copy_messages_and_threads(source_channel, target_channel, message_mapping, in_thread=False):
    messages = [message async for message in source_channel.history(limit=None, oldest_first=True)]
    for message in messages:
        await copy_message(source_channel, target_channel, message_mapping, message)


async def add_stt_button(channel):
    async for first_message in channel.history(limit=1, oldest_first=True):
        button = Button(label="Click to Scroll to Top", style=discord.ButtonStyle.link, url=first_message.jump_url)
        view = View()
        view.add_item(button)
        await channel.send(view=view)
        break


async def resolve_channel(interaction, channel_picker, channel_id):
    if channel_picker:
        return channel_picker
    if channel_id:
        try:
            return await interaction.client.fetch_channel(int(channel_id))
        except Exception:
            return None
    return None


async def resolve_category(interaction, category_picker, category_id):
    if category_picker:
        return category_picker
    if category_id:
        try:
            ch = await interaction.client.fetch_channel(int(category_id))
            if isinstance(ch, discord.CategoryChannel):
                return ch
        except Exception:
            return None
    return None


# =========================
# /copy_channel
# =========================
@bot.tree.command(name="copy_channel", description="Copy all messages from one channel to another.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    source="Source channel to copy from",
    source_id="Source channel ID (alternative to picker)",
    target="Target channel to copy into (defaults to current channel)",
    target_id="Target channel ID (alternative to picker)"
)
async def copy_channel(
    interaction: discord.Interaction,
    source: Optional[discord.TextChannel] = None,
    source_id: Optional[str] = None,
    target: Optional[discord.TextChannel] = None,
    target_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    src = await resolve_channel(interaction, source, source_id)
    tgt = await resolve_channel(interaction, target, target_id) or interaction.channel

    if not src:
        await interaction.followup.send("Could not find source channel.", ephemeral=True)
        return

    message_mapping = {}
    await copy_messages_and_threads(src, tgt, message_mapping)
    await add_stt_button(tgt)
    await interaction.followup.send("Channel copied successfully.", ephemeral=True)


# =========================
# /copy_category
# =========================
@bot.tree.command(name="copy_category", description="Copy all channels from one category to another.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    source="Source category",
    source_id="Source category ID (alternative to picker)",
    target="Target category",
    target_id="Target category ID (alternative to picker)"
)
async def copy_category(
    interaction: discord.Interaction,
    source: Optional[discord.CategoryChannel] = None,
    source_id: Optional[str] = None,
    target: Optional[discord.CategoryChannel] = None,
    target_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    src = await resolve_category(interaction, source, source_id)
    tgt = await resolve_category(interaction, target, target_id)

    if not src or not isinstance(src, discord.CategoryChannel):
        await interaction.followup.send("Could not find source category.", ephemeral=True)
        return
    if not tgt or not isinstance(tgt, discord.CategoryChannel):
        await interaction.followup.send("Could not find target category.", ephemeral=True)
        return

    for ch in src.channels:
        if isinstance(ch, discord.TextChannel):
            new_channel = await tgt.create_text_channel(ch.name)
            message_mapping = {}
            await copy_messages_and_threads(ch, new_channel, message_mapping)
            await add_stt_button(new_channel)
        elif isinstance(ch, discord.VoiceChannel):
            await tgt.create_voice_channel(ch.name)

    await interaction.followup.send("Category copied successfully.", ephemeral=True)


# =========================
# /copy_forum
# =========================
@bot.tree.command(name="copy_forum", description="Copy all threads from one forum channel to another.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    source="Source forum channel",
    source_id="Source forum channel ID (alternative to picker)",
    target="Target forum channel",
    target_id="Target forum channel ID (alternative to picker)"
)
async def copy_forum(
    interaction: discord.Interaction,
    source: Optional[discord.ForumChannel] = None,
    source_id: Optional[str] = None,
    target: Optional[discord.ForumChannel] = None,
    target_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    src = await resolve_channel(interaction, source, source_id)
    tgt = await resolve_channel(interaction, target, target_id)

    if not isinstance(src, discord.ForumChannel) or not isinstance(tgt, discord.ForumChannel):
        await interaction.followup.send("Both channels must be forum channels.", ephemeral=True)
        return

    active_threads = src.threads
    archived_threads = [t async for t in src.archived_threads(limit=None)]
    all_threads = active_threads + archived_threads
    sorted_threads = sorted(all_threads, key=lambda t: t.created_at)

    for thread in sorted_threads:
        all_messages = [m async for m in thread.history(limit=None, oldest_first=True)]
        first_msg = all_messages[0] if all_messages else None
        first_content = first_msg.content if first_msg and first_msg.content else '.'

        files = []
        if first_msg and first_msg.attachments:
            files = [await a.to_file() for a in first_msg.attachments]

        new_thread_obj = await tgt.create_thread(
            name=thread.name,
            content=first_content,
            auto_archive_duration=thread.auto_archive_duration,
            files=files
        )
        new_thread = new_thread_obj.thread

        message_mapping = {}
        for message in all_messages[1:]:
            await copy_message(thread, new_thread, message_mapping, message)

        thread_messages = [m async for m in new_thread.history(limit=None, oldest_first=True)]
        if len(thread_messages) >= 2:
            second_message = thread_messages[1]
            button = Button(label="Click to Scroll to Top", style=discord.ButtonStyle.link, url=second_message.jump_url)
            view = View()
            view.add_item(button)
            await new_thread.send(view=view)

        await asyncio.sleep(1)

    await interaction.followup.send("Forum copied successfully.", ephemeral=True)


# =========================
# /duplicate_channel
# =========================
@bot.tree.command(name="duplicate_channel", description="Duplicate the current channel in the same category.")
@app_commands.checks.has_permissions(administrator=True)
async def duplicate_channel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    source_channel = interaction.channel
    category = source_channel.category

    if category is None:
        await interaction.followup.send("This channel is not in a category.", ephemeral=True)
        return

    new_channel = await category.create_text_channel(source_channel.name)
    message_mapping = {}
    await copy_messages_and_threads(source_channel, new_channel, message_mapping)
    await add_stt_button(new_channel)
    await interaction.followup.send("Channel duplicated successfully.", ephemeral=True)


# =========================
# /repost_channel
# =========================
@bot.tree.command(name="repost_channel", description="Repost all messages in the current channel (moves them to the bottom).")
@app_commands.checks.has_permissions(administrator=True)
async def repost_channel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.channel
    message_mapping = {}
    await copy_messages_and_threads(channel, channel, message_mapping)

    original_ids = set(message_mapping.keys())
    async for message in channel.history(limit=None, oldest_first=True):
        if message.id in original_ids:
            await message.delete()

    await add_stt_button(channel)
    await interaction.followup.send("Channel reposted successfully.", ephemeral=True)


# =========================
# /send_message
# =========================
@bot.tree.command(name="send_message", description="Send a plain text message to a channel.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    text="The message content to send",
    channel="Target channel (defaults to current channel)",
    channel_id="Target channel ID (alternative to picker)"
)
async def send_message(
    interaction: discord.Interaction,
    text: str,
    channel: Optional[discord.TextChannel] = None,
    channel_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    ch = await resolve_channel(interaction, channel, channel_id) or interaction.channel
    await ch.send(text)
    await interaction.followup.send("Message sent.", ephemeral=True)


# =========================
# /embed
# =========================
@bot.tree.command(name="embed", description="Send an embed message.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    text="The embed description text",
    image_url="Optional image URL to display in the embed",
    channel="Target channel (defaults to current channel)",
    channel_id="Target channel ID (alternative to picker)"
)
async def send_embed(
    interaction: discord.Interaction,
    text: str,
    image_url: Optional[str] = None,
    channel: Optional[discord.TextChannel] = None,
    channel_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    ch = await resolve_channel(interaction, channel, channel_id) or interaction.channel
    embed = discord.Embed(description=text, color=0x3498DB)
    if image_url:
        embed.set_image(url=image_url)
    await ch.send(embed=embed)
    await interaction.followup.send("Embed sent.", ephemeral=True)


# =========================
# /edit_message
# =========================
@bot.tree.command(name="edit_message", description="Edit a message sent by the bot.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    message_id="The ID of the message to edit",
    new_content="The new text content",
    channel="Channel where the message is (defaults to current channel)",
    channel_id="Channel ID (alternative to picker)"
)
async def edit_message(
    interaction: discord.Interaction,
    message_id: str,
    new_content: str,
    channel: Optional[discord.TextChannel] = None,
    channel_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    ch = await resolve_channel(interaction, channel, channel_id) or interaction.channel
    try:
        message = await ch.fetch_message(int(message_id))
        if message.author == bot.user:
            await message.edit(content=new_content)
            await interaction.followup.send("Message edited.", ephemeral=True)
        else:
            await interaction.followup.send("Cannot edit messages not sent by the bot.", ephemeral=True)
    except discord.NotFound:
        await interaction.followup.send("Message not found.", ephemeral=True)


# =========================
# /edit_embed
# =========================
@bot.tree.command(name="edit_embed", description="Edit an existing embed message.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    message_id="The ID of the embed message to edit",
    text="New description text (leave empty to keep current)",
    image_url="New image URL (use 'remove' to clear the image)",
    channel="Channel where the message is (defaults to current channel)",
    channel_id="Channel ID (alternative to picker)"
)
async def edit_embed(
    interaction: discord.Interaction,
    message_id: str,
    text: Optional[str] = None,
    image_url: Optional[str] = None,
    channel: Optional[discord.TextChannel] = None,
    channel_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    ch = await resolve_channel(interaction, channel, channel_id) or interaction.channel
    try:
        message = await ch.fetch_message(int(message_id))
        if not message.embeds:
            await interaction.followup.send("This message has no embed.", ephemeral=True)
            return
        embed = message.embeds[0].copy()
        if text:
            embed.description = text
        if image_url == "remove":
            embed.set_image(url=None)
        elif image_url:
            embed.set_image(url=image_url)
        await message.edit(embed=embed)
        await interaction.followup.send("Embed edited.", ephemeral=True)
    except discord.NotFound:
        await interaction.followup.send("Message not found.", ephemeral=True)


# =========================
# /webhook
# =========================
@bot.tree.command(name="webhook", description="Send a rich webhook-style embed with full options.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    title="Embed title",
    description="Embed description/body text",
    field1_name="Field 1 name",
    field1_value="Field 1 value",
    field2_name="Field 2 name",
    field2_value="Field 2 value",
    field3_name="Field 3 name",
    field3_value="Field 3 value",
    image="Upload an image (re-uploaded to avoid expiry)",
    image_url="Or provide an image URL instead",
    footer="Footer text",
    color="Hex color code e.g. 3498DB",
    channel="Target channel (defaults to current channel)",
    channel_id="Target channel ID (alternative to picker)"
)
async def webhook(
    interaction: discord.Interaction,
    title: Optional[str] = None,
    description: Optional[str] = None,
    field1_name: Optional[str] = None,
    field1_value: Optional[str] = None,
    field2_name: Optional[str] = None,
    field2_value: Optional[str] = None,
    field3_name: Optional[str] = None,
    field3_value: Optional[str] = None,
    image: Optional[discord.Attachment] = None,
    image_url: Optional[str] = None,
    footer: Optional[str] = None,
    color: Optional[str] = None,
    channel: Optional[discord.TextChannel] = None,
    channel_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    ch = await resolve_channel(interaction, channel, channel_id) or interaction.channel

    try:
        embed_color = int((color or "3498DB").lstrip('#'), 16)
    except Exception:
        embed_color = 0x3498DB

    embed = discord.Embed(title=title, description=description, color=embed_color)

    if field1_name and field1_value:
        embed.add_field(name=field1_name, value=field1_value, inline=False)
    if field2_name and field2_value:
        embed.add_field(name=field2_name, value=field2_value, inline=False)
    if field3_name and field3_value:
        embed.add_field(name=field3_name, value=field3_value, inline=False)

    if footer:
        embed.set_footer(text=footer)

    file = None
    if image:
        image_data = await image.read()
        file = discord.File(io.BytesIO(image_data), filename=image.filename)
        embed.set_image(url=f"attachment://{image.filename}")
    elif image_url:
        embed.set_image(url=image_url)

    if file:
        await ch.send(embed=embed, file=file)
    else:
        await ch.send(embed=embed)

    await interaction.followup.send("Webhook embed sent.", ephemeral=True)


# =========================
# /delete_channel
# =========================
@bot.tree.command(name="delete_channel", description="Purge all messages in a channel.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    channel="Channel to purge (defaults to current channel)",
    channel_id="Channel ID (alternative to picker)"
)
async def delete_channel(
    interaction: discord.Interaction,
    channel: Optional[discord.TextChannel] = None,
    channel_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    ch = await resolve_channel(interaction, channel, channel_id) or interaction.channel
    await ch.purge(limit=None)
    await interaction.followup.send("Channel purged.", ephemeral=True)


# =========================
# /delete_category
# =========================
@bot.tree.command(name="delete_category", description="Purge all messages in every channel in a category.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    category="Category to purge (defaults to current channel's category)",
    category_id="Category ID (alternative to picker)"
)
async def delete_category(
    interaction: discord.Interaction,
    category: Optional[discord.CategoryChannel] = None,
    category_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    cat = await resolve_category(interaction, category, category_id) or interaction.channel.category

    if not cat:
        await interaction.followup.send("Could not find category.", ephemeral=True)
        return

    for ch in cat.text_channels:
        await ch.purge(limit=None)
        await asyncio.sleep(1)

    await interaction.followup.send("Category purged.", ephemeral=True)


# =========================
# /audit
# =========================
@bot.tree.command(name="audit", description="Analyze a channel or category and show a detailed report.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    channel="Channel to audit (defaults to current channel)",
    category="Audit all channels in a category instead",
    user="Filter by a specific user",
    hours="Only look at messages from the last N hours",
    spam_text="Check how many times a specific phrase appears"
)
async def audit(
    interaction: discord.Interaction,
    channel: Optional[discord.TextChannel] = None,
    category: Optional[discord.CategoryChannel] = None,
    user: Optional[discord.Member] = None,
    hours: Optional[int] = None,
    spam_text: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)

    since = None
    if hours:
        since = discord.utils.utcnow() - discord.timedelta(hours=hours)

    if category:
        targets = category.text_channels
    elif channel:
        targets = [channel]
    else:
        targets = [interaction.channel]

    total_msgs = 0
    bots = 0
    humans = 0
    user_counts = {}
    content_stats = {"text": 0, "images": 0, "links": 0}
    spam_hits = 0

    for ch in targets:
        async for m in ch.history(limit=None, after=since):
            if user and m.author != user:
                continue
            total_msgs += 1
            if m.author.bot:
                bots += 1
            else:
                humans += 1
                user_counts[m.author] = user_counts.get(m.author, 0) + 1
            if m.attachments:
                content_stats["images"] += 1
            elif "http" in m.content:
                content_stats["links"] += 1
            else:
                content_stats["text"] += 1
            if spam_text and spam_text in m.content:
                spam_hits += 1

    top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    embed = discord.Embed(title="📊 Audit Report", color=0x3498DB)
    scope = category.name if category else targets[0].mention
    embed.add_field(name="Scope", value=scope, inline=False)
    if user:
        embed.add_field(name="User Filter", value=user.mention, inline=False)
    embed.add_field(name="Total Messages", value=str(total_msgs), inline=True)
    embed.add_field(name="Humans / Bots", value=f"{humans} / {bots}", inline=True)
    embed.add_field(
        name="Content Breakdown",
        value=f"📝 Text: {content_stats['text']}\n🖼 Images: {content_stats['images']}\n🔗 Links: {content_stats['links']}",
        inline=False
    )
    embed.add_field(
        name="Top Users",
        value="\n".join(f"{u.mention}: {c}" for u, c in top_users) or "None",
        inline=False
    )
    if spam_text:
        embed.add_field(name=f"Spam: '{spam_text}'", value=f"Found **{spam_hits}** times", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)


# =========================
# /stt_button
# =========================
@bot.tree.command(name="stt_button", description="Add a scroll-to-top button in the current channel.")
@app_commands.checks.has_permissions(administrator=True)
async def stt_button(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await add_stt_button(interaction.channel)
    await interaction.followup.send("Scroll to top button added.", ephemeral=True)


# =========================
# /stt_button_category
# =========================
@bot.tree.command(name="stt_button_category", description="Add a scroll-to-top button in every channel in the current category.")
@app_commands.checks.has_permissions(administrator=True)
async def stt_button_category(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    category = interaction.channel.category
    if not category:
        await interaction.followup.send("This channel is not in a category.", ephemeral=True)
        return
    for ch in category.channels:
        if isinstance(ch, discord.TextChannel):
            await add_stt_button(ch)
    await interaction.followup.send("Scroll to top buttons added to all channels.", ephemeral=True)


# =========================
# /poll
# =========================
@bot.tree.command(name="poll", description="Create a reaction-based poll.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    question="The poll question",
    option1="Option 1",
    option2="Option 2",
    option3="Option 3",
    option4="Option 4",
    option5="Option 5",
    option6="Option 6",
    option7="Option 7",
    channel="Target channel (defaults to current channel)",
    channel_id="Target channel ID (alternative to picker)"
)
async def poll(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str,
    option3: Optional[str] = None,
    option4: Optional[str] = None,
    option5: Optional[str] = None,
    option6: Optional[str] = None,
    option7: Optional[str] = None,
    channel: Optional[discord.TextChannel] = None,
    channel_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    ch = await resolve_channel(interaction, channel, channel_id) or interaction.channel
    options = [o for o in [option1, option2, option3, option4, option5, option6, option7] if o]
    emoji_numbers = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣']
    embed = discord.Embed(description=f"**{question}**", color=0x3498DB)
    for idx, option in enumerate(options):
        embed.add_field(name=f"{emoji_numbers[idx]} {option}", value="\u200b", inline=False)
    poll_message = await ch.send(embed=embed)
    for i in range(len(options)):
        await poll_message.add_reaction(emoji_numbers[i])
    await interaction.followup.send("Poll created.", ephemeral=True)


# =========================
# /custom_button
# =========================
@bot.tree.command(name="custom_button", description="Create a standalone clickable button in the current channel.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    label="The button label text",
    style="Button color style",
    link_url="URL to open when clicked",
    target_channel="Discord channel to link to (alternative to URL)"
)
@app_commands.choices(style=[
    app_commands.Choice(name="Primary (Blue)", value="primary"),
    app_commands.Choice(name="Secondary (Grey)", value="secondary"),
    app_commands.Choice(name="Success (Green)", value="success"),
    app_commands.Choice(name="Danger (Red)", value="danger"),
    app_commands.Choice(name="Link", value="link"),
])
async def custom_button(
    interaction: discord.Interaction,
    label: str,
    style: app_commands.Choice[str],
    link_url: Optional[str] = None,
    target_channel: Optional[discord.TextChannel] = None
):
    await interaction.response.defer(ephemeral=True)
    style_map = {
        "primary": discord.ButtonStyle.primary,
        "secondary": discord.ButtonStyle.secondary,
        "success": discord.ButtonStyle.success,
        "danger": discord.ButtonStyle.danger,
        "link": discord.ButtonStyle.link,
    }
    url = link_url or (
        f"https://discord.com/channels/{interaction.guild.id}/{target_channel.id}"
        if target_channel else None
    )
    if not url:
        await interaction.followup.send("You must provide either a link URL or a target channel.", ephemeral=True)
        return
    button = Button(label=label, style=style_map[style.value], url=url)
    view = View()
    view.add_item(button)
    await interaction.channel.send(view=view)
    await interaction.followup.send("Button created.", ephemeral=True)


# =========================
# /qr_code
# =========================
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
COLOR_MAP = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "blue": (0, 0, 255), "green": (0, 128, 0), "yellow": (255, 255, 0),
    "orange": (255, 165, 0), "purple": (128, 0, 128), "pink": (255, 105, 180),
    "cyan": (0, 255, 255), "gray": (128, 128, 128), "brown": (139, 69, 19),
}
COLOR_CHOICES = [app_commands.Choice(name=name, value=name) for name in COLOR_MAP]

def parse_hex(s):
    s = (s or "").strip()
    if not s or not HEX_RE.match(s):
        return None
    return tuple(int(s[i:i+2], 16) for i in (1, 3, 5))

def make_qr_image(data, fg_rgb, bg_rgb, logo_bytes=None):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fg_rgb, back_color=bg_rgb).convert("RGBA")
    if logo_bytes:
        logo_img = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
        target = img.size[0] // 4
        logo_img.thumbnail((target, target))
        x = (img.size[0] - logo_img.size[0]) // 2
        y = (img.size[1] - logo_img.size[1]) // 2
        img.paste(logo_img, (x, y), logo_img)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

@bot.tree.command(name="qr_code", description="Generate a customized QR code.")
@app_commands.describe(
    data="The link or text to encode",
    foreground="Foreground color",
    background="Background color",
    foreground_hex="Override foreground with hex e.g. #ff0000",
    background_hex="Override background with hex e.g. #ffffff",
    logo="Optional logo image to place in the center"
)
@app_commands.choices(foreground=COLOR_CHOICES, background=COLOR_CHOICES)
async def qr_code(
    interaction: discord.Interaction,
    data: str,
    foreground: app_commands.Choice[str],
    background: app_commands.Choice[str],
    foreground_hex: Optional[str] = None,
    background_hex: Optional[str] = None,
    logo: Optional[discord.Attachment] = None
):
    await interaction.response.defer()
    fg_rgb = COLOR_MAP[foreground.value]
    bg_rgb = COLOR_MAP[background.value]
    if foreground_hex:
        override = parse_hex(foreground_hex)
        if not override:
            await interaction.followup.send("Invalid foreground hex. Use format #ff0000", ephemeral=True)
            return
        fg_rgb = override
    if background_hex:
        override = parse_hex(background_hex)
        if not override:
            await interaction.followup.send("Invalid background hex. Use format #ffffff", ephemeral=True)
            return
        bg_rgb = override
    logo_bytes = None
    if logo:
        if not (logo.content_type or "").startswith("image/"):
            await interaction.followup.send("Logo must be an image file.", ephemeral=True)
            return
        logo_bytes = await logo.read()
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(None, partial(make_qr_image, data, fg_rgb, bg_rgb, logo_bytes))
    await interaction.followup.send(file=discord.File(buf, filename="qr.png"))


# =========================
# TIC-TAC-TOE
# =========================
class TicTacToeGame:
    def __init__(self, player1, player2=None):
        self.player1 = player1
        self.player2 = player2
        self.board = [""] * 9
        self.current = player1
        self.scores = {str(player1.id): 0, "bot" if not player2 else str(player2.id): 0}
        self.round = 1

    def is_vs_bot(self):
        return self.player2 is None

    def current_symbol(self):
        return "❌" if self.current == self.player1 else "⭕"

    def check_winner(self):
        wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        for a, b, c in wins:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        return None

    def is_draw(self):
        return "" not in self.board and not self.check_winner()

    def bot_move(self):
        for i in range(9):
            if self.board[i] == "":
                self.board[i] = "⭕"
                if self.check_winner():
                    return
                self.board[i] = ""
        for i in range(9):
            if self.board[i] == "":
                self.board[i] = "❌"
                if self.check_winner():
                    self.board[i] = "⭕"
                    return
                self.board[i] = ""
        if self.board[4] == "":
            self.board[4] = "⭕"
            return
        for i in [0, 2, 6, 8]:
            if self.board[i] == "":
                self.board[i] = "⭕"
                return
        for i in range(9):
            if self.board[i] == "":
                self.board[i] = "⭕"
                return

    def reset_board(self):
        self.board = [""] * 9
        self.round += 1
        self.current = self.player1


class TicTacToeView(discord.ui.View):
    def __init__(self, game: TicTacToeGame):
        super().__init__(timeout=300)
        self.game = game
        self.build_buttons()

    def build_buttons(self):
        self.clear_items()
        for i in range(9):
            label = self.game.board[i] if self.game.board[i] else "⬜"
            disabled = self.game.board[i] != ""
            btn = discord.ui.Button(label=label, row=i // 3, disabled=disabled)
            btn.callback = self.make_callback(i)
            self.add_item(btn)

    def make_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            game = self.game
            if interaction.user != game.current:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
            if game.board[idx] != "":
                await interaction.response.send_message("That cell is already taken!", ephemeral=True)
                return

            game.board[idx] = game.current_symbol()
            winner_symbol = game.check_winner()

            if winner_symbol:
                is_p1_win = winner_symbol == "❌"
                winner = game.player1 if is_p1_win else (game.player2 or "Bot")
                w_key = str(game.player1.id) if is_p1_win else ("bot" if game.is_vs_bot() else str(game.player2.id))
                game.scores[w_key] = game.scores.get(w_key, 0) + 1
                self.build_buttons()
                self.disable_all()
                name = "Bot 🤖" if winner == "Bot" else winner.mention
                await interaction.response.edit_message(
                    content=f"🏆 {name} wins! Round {game.round}\n{self.score_text()}",
                    view=self.add_play_again_buttons()
                )
                return

            if game.is_draw():
                self.build_buttons()
                self.disable_all()
                await interaction.response.edit_message(
                    content=f"It's a draw! Round {game.round}\n{self.score_text()}",
                    view=self.add_play_again_buttons()
                )
                return

            game.current = game.player2 if game.current == game.player1 else game.player1

            if game.is_vs_bot() and game.current != game.player1:
                game.bot_move()
                winner_symbol = game.check_winner()
                if winner_symbol:
                    game.scores["bot"] = game.scores.get("bot", 0) + 1
                    self.build_buttons()
                    self.disable_all()
                    await interaction.response.edit_message(
                        content=f"🤖 Bot wins! Round {game.round}\n{self.score_text()}",
                        view=self.add_play_again_buttons()
                    )
                    return
                if game.is_draw():
                    self.build_buttons()
                    self.disable_all()
                    await interaction.response.edit_message(
                        content=f"It's a draw! Round {game.round}\n{self.score_text()}",
                        view=self.add_play_again_buttons()
                    )
                    return
                game.current = game.player1

            self.build_buttons()
            p2_name = "Bot 🤖" if game.is_vs_bot() else game.player2.mention
            turn = game.player1.mention if game.current == game.player1 else p2_name
            await interaction.response.edit_message(
                content=f"Turn: {turn}\n{self.score_text()}",
                view=self
            )
        return callback

    def disable_all(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    def score_text(self):
        game = self.game
        p2_name = "Bot" if game.is_vs_bot() else game.player2.display_name
        p1_score = game.scores.get(str(game.player1.id), 0)
        p2_key = "bot" if game.is_vs_bot() else str(game.player2.id)
        p2_score = game.scores.get(p2_key, 0)
        return f"📊 {game.player1.display_name}: {p1_score} | {p2_name}: {p2_score}"

    def add_play_again_buttons(self):
        again_btn = discord.ui.Button(label="Play Again", style=discord.ButtonStyle.success, row=3)
        stop_btn = discord.ui.Button(label="Stop", style=discord.ButtonStyle.danger, row=3)

        async def play_again(interaction: discord.Interaction):
            if interaction.user not in [self.game.player1, self.game.player2]:
                await interaction.response.send_message("You're not in this game.", ephemeral=True)
                return
            self.game.reset_board()
            self.build_buttons()
            p2_name = "Bot 🤖" if self.game.is_vs_bot() else self.game.player2.mention
            await interaction.response.edit_message(
                content=f"Round {self.game.round}! {self.game.player1.mention} ❌ vs {p2_name} ⭕\nTurn: {self.game.player1.mention}\n{self.score_text()}",
                view=self
            )

        async def stop_game(interaction: discord.Interaction):
            if interaction.user not in [self.game.player1, self.game.player2]:
                await interaction.response.send_message("You're not in this game.", ephemeral=True)
                return
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(
                content=f"Game over!\n{self.score_text()}",
                view=self
            )

        again_btn.callback = play_again
        stop_btn.callback = stop_game
        self.add_item(again_btn)
        self.add_item(stop_btn)
        return self


@bot.tree.command(name="tictactoe", description="Play Tic-Tac-Toe against another user or the bot.")
@app_commands.describe(opponent="The user to play against (leave empty to play against the bot)")
async def tictactoe(interaction: discord.Interaction, opponent: Optional[discord.Member] = None):
    if opponent and opponent.bot and opponent != bot.user:
        await interaction.response.send_message("You can't challenge that bot.", ephemeral=True)
        return
    player2 = None if (not opponent or opponent.bot) else opponent
    game = TicTacToeGame(interaction.user, player2)
    view = TicTacToeView(game)
    p2_name = "Bot 🤖" if not player2 else player2.mention
    await interaction.response.send_message(
        content=f"Round 1! {interaction.user.mention} ❌ vs {p2_name} ⭕\nTurn: {interaction.user.mention}\n{view.score_text()}",
        view=view
    )


# =========================
# SUDOKU
# =========================
def generate_sudoku():
    base = 3
    side = base * base

    def pattern(r, c):
        return (base * (r % base) + r // base + c) % side

    def shuffle(s):
        return random.sample(s, len(s))

    rBase = range(base)
    rows = [g * base + r for g in shuffle(rBase) for r in shuffle(rBase)]
    cols = [g * base + c for g in shuffle(rBase) for c in shuffle(rBase)]
    nums = shuffle(range(1, side + 1))
    board = [[nums[pattern(r, c)] for c in cols] for r in rows]

    squares = side * side
    empties = squares * 5 // 9
    for p in random.sample(range(squares), empties):
        board[p // side][p % side] = 0

    return board


def board_to_str(board, user_fills=None, selected=None):
    if user_fills is None:
        user_fills = {}
    lines = []
    for r in range(9):
        if r % 3 == 0 and r != 0:
            lines.append("──────────────────────")
        row_parts = []
        for c in range(9):
            if c % 3 == 0 and c != 0:
                row_parts.append("│")
            val = board[r][c]
            pos = (r, c)
            if val != 0:
                row_parts.append(f"**{val}**")
            elif pos in user_fills:
                row_parts.append(f"`{user_fills[pos]}`" if selected == pos else f"__{user_fills[pos]}__")
            else:
                row_parts.append("`·`" if selected == pos else "·")
        lines.append(" ".join(row_parts))
    return "\n".join(lines)


def solve_board(board):
    board = [row[:] for row in board]

    def valid(r, c, num):
        if num in board[r]:
            return False
        if num in [board[i][c] for i in range(9)]:
            return False
        br, bc = 3 * (r // 3), 3 * (c // 3)
        for i in range(br, br + 3):
            for j in range(bc, bc + 3):
                if board[i][j] == num:
                    return False
        return True

    def solve(b):
        empty = next(((r, c) for r in range(9) for c in range(9) if b[r][c] == 0), None)
        if not empty:
            return True
        r, c = empty
        for num in range(1, 10):
            if valid(r, c, num):
                b[r][c] = num
                if solve(b):
                    return True
                b[r][c] = 0
        return False

    solve(board)
    return board


class SudokuView(discord.ui.View):
    def __init__(self, player, board):
        super().__init__(timeout=3600)
        self.player = player
        self.board = board
        self.solution = solve_board(board)
        self.user_fills = {}
        self.selected = None
        self.build_controls()

    def build_controls(self):
        self.clear_items()

        row_select = discord.ui.Select(
            placeholder="① Select Row (1-9)",
            options=[discord.SelectOption(label=f"Row {i+1}", value=str(i)) for i in range(9)],
            row=0
        )
        row_select.callback = self.select_row
        self.add_item(row_select)

        col_select = discord.ui.Select(
            placeholder="② Select Column (1-9)",
            options=[discord.SelectOption(label=f"Column {i+1}", value=str(i)) for i in range(9)],
            row=1
        )
        col_select.callback = self.select_col
        self.add_item(col_select)

        num_select = discord.ui.Select(
            placeholder="③ Select Number to place",
            options=[discord.SelectOption(label=str(i), value=str(i)) for i in range(1, 10)],
            row=2
        )
        num_select.callback = self.select_number
        self.add_item(num_select)

        clear_btn = discord.ui.Button(label="Clear Cell", style=discord.ButtonStyle.secondary, row=3)
        clear_btn.callback = self.clear_cell
        self.add_item(clear_btn)

        check_btn = discord.ui.Button(label="Check Progress", style=discord.ButtonStyle.primary, row=3)
        check_btn.callback = self.check_progress
        self.add_item(check_btn)

        reveal_btn = discord.ui.Button(label="Reveal Solution", style=discord.ButtonStyle.danger, row=3)
        reveal_btn.callback = self.reveal_solution
        self.add_item(reveal_btn)

    async def select_row(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        r = int(interaction.data["values"][0])
        c = self.selected[1] if self.selected else 0
        self.selected = (r, c)
        await interaction.response.edit_message(content=self.render(), view=self)

    async def select_col(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        r = self.selected[0] if self.selected else 0
        c = int(interaction.data["values"][0])
        self.selected = (r, c)
        await interaction.response.edit_message(content=self.render(), view=self)

    async def select_number(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        if not self.selected:
            await interaction.response.send_message("Select a row and column first.", ephemeral=True)
            return
        r, c = self.selected
        if self.board[r][c] != 0:
            await interaction.response.send_message("That cell is pre-filled and cannot be changed.", ephemeral=True)
            return
        num = int(interaction.data["values"][0])
        self.user_fills[self.selected] = num
        if self.is_complete():
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(
                content=self.render() + "\n\n🎉 **Congratulations! You solved it!**",
                view=self
            )
            return
        await interaction.response.edit_message(content=self.render(), view=self)

    async def clear_cell(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        if self.selected and self.selected in self.user_fills:
            del self.user_fills[self.selected]
        await interaction.response.edit_message(content=self.render(), view=self)

    async def check_progress(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        correct = sum(1 for (r, c), v in self.user_fills.items() if self.solution[r][c] == v)
        wrong = len(self.user_fills) - correct
        empty = sum(1 for r in range(9) for c in range(9) if self.board[r][c] == 0 and (r, c) not in self.user_fills)
        await interaction.response.send_message(
            f"✅ Correct: {correct} | ❌ Wrong: {wrong} | ⬜ Empty: {empty}",
            ephemeral=True
        )

    async def reveal_solution(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="**Solution:**\n" + board_to_str(self.solution),
            view=self
        )

    def is_complete(self):
        for r in range(9):
            for c in range(9):
                if self.board[r][c] == 0:
                    if self.user_fills.get((r, c)) != self.solution[r][c]:
                        return False
        return True

    def render(self):
        header = f"🧩 **Sudoku** — {self.player.display_name}\n"
        if self.selected:
            header += f"Selected: Row {self.selected[0]+1}, Column {self.selected[1]+1}\n"
        return header + "\n" + board_to_str(self.board, self.user_fills, self.selected)


@bot.tree.command(name="sudoku", description="Start a solo playable Sudoku game.")
async def sudoku(interaction: discord.Interaction):
    await interaction.response.defer()
    board = generate_sudoku()
    view = SudokuView(interaction.user, board)
    await interaction.followup.send(content=view.render(), view=view)


# =========================
# PERSISTENT STORAGE
# =========================
STORAGE_FILE = "bot_data.json"

def load_data():
    if not os.path.exists(STORAGE_FILE):
        return {"archive_category": None, "welcome_templates": {}}
    with open(STORAGE_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(STORAGE_FILE, "w") as f:
        json.dump(data, f, indent=4)


# =========================
# /set_archive_category
# =========================
@bot.tree.command(name="set_archive_category", description="Set the category where archived channels will be moved to.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    category="The category to use as the archive",
    category_id="Category ID (alternative to picker)"
)
async def set_archive_category(
    interaction: discord.Interaction,
    category: Optional[discord.CategoryChannel] = None,
    category_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    cat = await resolve_category(interaction, category, category_id)

    if not cat:
        await interaction.followup.send("Could not find that category.", ephemeral=True)
        return

    data = load_data()
    data["archive_category"] = cat.id
    save_data(data)
    await interaction.followup.send(f"Archive category set to **{cat.name}**.", ephemeral=True)


# =========================
# /archive_channel
# =========================
@bot.tree.command(name="archive_channel", description="Move a channel to the archive category and lock it.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    channel="Channel to archive (defaults to current channel)",
    channel_id="Channel ID (alternative to picker)"
)
async def archive_channel(
    interaction: discord.Interaction,
    channel: Optional[discord.TextChannel] = None,
    channel_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)

    data = load_data()
    archive_cat_id = data.get("archive_category")

    if not archive_cat_id:
        await interaction.followup.send("No archive category set. Use `/set_archive_category` first.", ephemeral=True)
        return

    archive_cat = interaction.guild.get_channel(archive_cat_id)
    if not archive_cat or not isinstance(archive_cat, discord.CategoryChannel):
        await interaction.followup.send("Archive category not found. Please set it again with `/set_archive_category`.", ephemeral=True)
        return

    ch = await resolve_channel(interaction, channel, channel_id) or interaction.channel

    # Move to archive category
    await ch.edit(category=archive_cat)

    # Lock the channel — deny Send Messages for everyone
    overwrite = ch.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await ch.set_permissions(interaction.guild.default_role, overwrite=overwrite)

    # Rename with archive prefix if not already there
    if not ch.name.startswith("📦"):
        await ch.edit(name=f"📦{ch.name}")

    await interaction.followup.send(f"Channel archived successfully.", ephemeral=True)


# =========================
# /set_welcome
# =========================
@bot.tree.command(name="set_welcome", description="Save a welcome message template.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    name="A short name for this template (e.g. 'new member', 'vip', 'returning')",
    message="The welcome message. Use {user} for mention, {channel} for a channel mention (e.g. <#channel_id>)",
    delete="Set to True to delete an existing template by this name instead of saving"
)
async def set_welcome(
    interaction: discord.Interaction,
    name: str,
    message: Optional[str] = None,
    delete: Optional[bool] = False
):
    await interaction.response.defer(ephemeral=True)

    data = load_data()
    if "welcome_templates" not in data:
        data["welcome_templates"] = {}

    if delete:
        if name in data["welcome_templates"]:
            del data["welcome_templates"][name]
            save_data(data)
            await interaction.followup.send(f"Template **{name}** deleted.", ephemeral=True)
        else:
            await interaction.followup.send(f"No template named **{name}** found.", ephemeral=True)
        return

    if not message:
        await interaction.followup.send("You must provide a message when saving a template.", ephemeral=True)
        return

    data["welcome_templates"][name] = message
    save_data(data)
    await interaction.followup.send(
        f"Template **{name}** saved.\nPreview: {message}",
        ephemeral=True
    )


# =========================
# /welcome
# =========================
ALLOWED_ROLES = {"Moderator", "Admin", "Verifier"}

def has_allowed_role():
    async def predicate(interaction: discord.Interaction):
        user_roles = {role.name for role in interaction.user.roles}
        if user_roles & ALLOWED_ROLES or interaction.user.guild_permissions.administrator:
            return True
        raise app_commands.CheckFailure("You need to be a Moderator, Admin, or Verifier to use this command.")
    return app_commands.check(predicate)

@bot.tree.command(name="welcome", description="Welcome a user using a saved template.")
@has_allowed_role()
@app_commands.describe(
    user="The user to welcome",
    template="The name of the saved welcome template to use"
)
async def welcome(
    interaction: discord.Interaction,
    user: discord.Member,
    template: str
):
    await interaction.response.defer(ephemeral=False)

    data = load_data()
    templates = data.get("welcome_templates", {})

    if template not in templates:
        await interaction.followup.send(
            f"No template named **{template}** found. Use `/set_welcome` to create one.",
            ephemeral=True
        )
        return

    message = templates[template].replace("{user}", user.mention).replace("\\n", "\n")
    await interaction.followup.send(message)


@welcome.autocomplete("template")
async def welcome_template_autocomplete(interaction: discord.Interaction, current: str):
    data = load_data()
    templates = data.get("welcome_templates", {})
    return [
        app_commands.Choice(name=name, value=name)
        for name in templates
        if current.lower() in name.lower()
    ]

@set_welcome.autocomplete("name")
async def set_welcome_name_autocomplete(interaction: discord.Interaction, current: str):
    data = load_data()
    templates = data.get("welcome_templates", {})
    return [
        app_commands.Choice(name=name, value=name)
        for name in templates
        if current.lower() in name.lower()
    ]


# =========================
# ERROR HANDLING
# =========================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        try:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
        except Exception:
            await interaction.followup.send("You need administrator permissions to use this command.", ephemeral=True)
    else:
        print(f"Command error: {error}")
        try:
            await interaction.response.send_message("An error occurred.", ephemeral=True)
        except Exception:
            pass


# =========================
# RUN
# =========================
async def run_bot():
    while True:
        try:
            await bot.start(TOKEN)
        except Exception as e:
            print(f'Bot crashed due to {e}. Restarting...')
            await asyncio.sleep(5)

if __name__ == '__main__':
    if not TOKEN:
        raise RuntimeError(
            "DISCORD_BOT_TOKEN is not set. See README.md and .env.example for setup instructions."
        )
    asyncio.run(run_bot())
