import os
import json
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import aiosqlite
import asyncio
import aiohttp

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
POKEMON_TRAINER_ROLE_ID = int(os.getenv("POKEMON_TRAINER_ROLE_ID", "0"))
POKEMON_HUNTER_ROLE_ID = int(os.getenv("POKEMON_HUNTER_ROLE_ID", "0"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0"))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID", "0"))
ANNOUNCEMENTS_CHANNEL_ID = int(os.getenv("ANNOUNCEMENTS_CHANNEL_ID", "0"))
GENERAL_CHAT_CHANNEL_ID = int(os.getenv("GENERAL_CHAT_CHANNEL_ID", "0"))
OPEN_HUNTING_CHANNEL_ID = int(os.getenv("OPEN_HUNTING_CHANNEL_ID", "0"))
PULLS_CHANNEL_ID = int(os.getenv("PULLS_CHANNEL_ID", "0"))
SUCCESS_CHANNEL_ID = int(os.getenv("SUCCESS_CHANNEL_ID", "0"))
MEE6_SILVER_ROLE_ID = int(os.getenv("MEE6_SILVER_ROLE_ID", "0"))

DB_PATH = "data/pokehunt.db"

with open("config.json", "r") as f:
    CONFIG = json.load(f)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
scan_in_progress = False


# ─── Database ────────────────────────────────────────────────────────────────

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS pings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                store TEXT,
                mention_type TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS whitelist (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        for key, value in CONFIG.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )
        await db.commit()


async def get_setting(key):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else CONFIG.get(key)


async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )
        await db.commit()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def days_ago_iso(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def is_admin_or_mod(member):
    return any(r.id in (ADMIN_ROLE_ID, MOD_ROLE_ID) for r in member.roles)


async def count_in_window(table, user_id, window_days):
    cutoff = days_ago_iso(window_days)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE user_id = ? AND timestamp >= ?",
            (user_id, cutoff)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def count_total(table, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


def extract_store_from_channel(channel_name):
    return channel_name


def parse_mentioned_stores(message):
    store_mentions = []
    for role in message.role_mentions:
        name_lower = role.name.lower()
        if name_lower in ("location", "oos"):
            for channel in CONFIG.get("store_channels", []):
                if message.channel.name == channel or message.channel.name in CONFIG.get("store_channels", []):
                    store_mentions.append({
                        "role_type": name_lower,
                        "channel": message.channel.name,
                        "store": message.channel.name
                    })
                    break
            if not store_mentions:
                store_mentions.append({
                    "role_type": name_lower,
                    "channel": message.channel.name,
                    "store": message.channel.name
                })
    return store_mentions


def extract_store_from_text(message):
    store_mentions = []
    content_lower = message.content.lower()
    store_list = CONFIG.get("store_channels", [])
    role_names = [r.name.lower() for r in message.role_mentions]

    has_location_ping = "location" in role_names
    has_oos_ping = "oos" in role_names

    if not has_location_ping and not has_oos_ping:
        return store_mentions

    for store in store_list:
        if store in content_lower or store.replace("-", " ") in content_lower:
            store_mentions.append({
                "role_type": "location" if has_location_ping else "oos",
                "channel": message.channel.name,
                "store": store
            })

    if not store_mentions and message.channel.name in store_list:
        store_mentions.append({
            "role_type": "location" if has_location_ping else "oos",
            "channel": message.channel.name,
            "store": message.channel.name
        })

    return store_mentions


async def log_ping(user_id, channel_id, store, mention_type):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO pings (user_id, channel_id, store, mention_type, timestamp) VALUES (?, ?, ?, ?, ?)",
            (user_id, channel_id, store, mention_type, now_iso())
        )
        await db.commit()


async def log_media(user_id, channel_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO media (user_id, channel_id, timestamp) VALUES (?, ?, ?)",
            (user_id, channel_id, now_iso())
        )
        await db.commit()


async def log_chat(user_id, channel_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO chat (user_id, channel_id, timestamp) VALUES (?, ?, ?)",
            (user_id, channel_id, now_iso())
        )
        await db.commit()


# ─── Access Engine ───────────────────────────────────────────────────────────

async def check_access(user_id, guild):
    member = guild.get_member(user_id)
    if not member:
        return

    hunter_role = guild.get_role(POKEMON_HUNTER_ROLE_ID)
    if not hunter_role:
        return

    if hunter_role in member.roles:
        whitelist_cutoff = days_ago_iso(9999)
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id FROM whitelist WHERE user_id = ?", (user_id,)
            )
            if await cursor.fetchone():
                return

        window = int(await get_setting("maintenance_window_days"))
        pings = await count_in_window("pings", user_id, window)
        media_count = await count_in_window("media", user_id, window)
        chat_count = await count_in_window("chat", user_id, int(await get_setting("chat_window_days")))

        min_pings = int(await get_setting("pings_to_maintain"))
        min_media = int(await get_setting("media_to_maintain"))
        min_chat = int(await get_setting("chat_to_maintain"))

        if pings >= min_pings or media_count >= min_media or chat_count >= min_chat:
            return

        await member.remove_roles(hunter_role, reason="Failed activity maintenance")
        channel = guild.get_channel(ANNOUNCEMENTS_CHANNEL_ID)
        if channel:
            try:
                await channel.send(
                    f"⚠️ {member.mention} has lost the **Pokemon Hunter** role due to inactivity. "
                    f"You need to keep posting pings, sharing hits in #pulls, or chatting to maintain access."
                )
            except discord.Forbidden:
                pass
    else:
        total_pings = await count_total("pings", user_id)
        required = int(await get_setting("pings_to_gain"))
        if total_pings >= required:
            await member.add_roles(hunter_role, reason="Reached ping threshold")
            channel = guild.get_channel(ANNOUNCEMENTS_CHANNEL_ID)
            if channel:
                try:
                    await channel.send(
                        f"🎉 {member.mention} has earned the **Pokemon Hunter** role! "
                        f"You now have access to all store channels."
                    )
                except discord.Forbidden:
                    pass


# ─── Events ──────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Guild: {bot.guilds[0].name if bot.guilds else 'No guild'}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")
    if not daily_maintenance.is_running():
        daily_maintenance.start()


@bot.event
async def on_member_join(member):
    if MEE6_SILVER_ROLE_ID:
        silver_role = member.guild.get_role(MEE6_SILVER_ROLE_ID)
        hunter_role = member.guild.get_role(POKEMON_HUNTER_ROLE_ID)
        if silver_role and hunter_role and silver_role in member.roles:
            try:
                await member.add_roles(hunter_role, reason="MEE6 Silver+ head start")
                channel = member.guild.get_channel(ANNOUNCEMENTS_CHANNEL_ID)
                if channel:
                    await channel.send(
                        f"🌟 Welcome {member.mention}! You have the MEE6 Silver role, "
                        f"so you've been granted **Pokemon Hunter** access right away."
                    )
            except discord.Forbidden:
                pass

    trainer_role = member.guild.get_role(POKEMON_TRAINER_ROLE_ID)
    if trainer_role:
        try:
            await member.add_roles(trainer_role, reason="Auto-assign Trainer on join")
        except discord.Forbidden:
            pass


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if not message.guild:
        return

    await bot.process_commands(message)

    channel_id = message.channel.id
    user_id = message.author.id

    store_channels = CONFIG.get("store_channels", [])
    media_channels = CONFIG.get("media_channels", [])
    chat_channels = CONFIG.get("chat_channels", [])

    channel_name = message.channel.name

    if channel_name in store_channels or channel_name in media_channels or channel_name in chat_channels:
        store_mentions = extract_store_from_text(message)
        if store_mentions:
            for mention in store_mentions:
                await log_ping(user_id, channel_id, mention["store"], mention["role_type"])
            await check_access(user_id, message.guild)

    if channel_name in media_channels:
        if message.attachments:
            for _ in message.attachments:
                await log_media(user_id, channel_id)
            await check_access(user_id, message.guild)

    if channel_name in chat_channels:
        await log_chat(user_id, channel_id)


# ─── Maintenance Task ────────────────────────────────────────────────────────

@tasks.loop(hours=24)
async def daily_maintenance():
    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT user_id FROM pings")
        rows = await cursor.fetchall()
        for (user_id,) in rows:
            await check_access(user_id, guild)


@daily_maintenance.before_loop
async def before_daily_maintenance():
    await bot.wait_until_ready()
    hour = int(await get_setting("daily_maintenance_hour"))
    minute = int(await get_setting("daily_maintenance_minute"))
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())


# ─── User Commands ───────────────────────────────────────────────────────────

@bot.command(name="pings")
async def pings_cmd(ctx, member: discord.Member = None):
    target = member or ctx.author
    window = int(await get_setting("maintenance_window_days"))
    count = await count_in_window("pings", target.id, window)
    embed = discord.Embed(
        title="Ping Count",
        description=f"**{target.display_name}** has **{count}** pings in the last {window} days.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)


@bot.command(name="pingtotal")
async def pingtotal_cmd(ctx, member: discord.Member = None):
    target = member or ctx.author
    total = await count_total("pings", target.id)
    embed = discord.Embed(
        title="Total Pings",
        description=f"**{target.display_name}** has **{total}** total lifetime pings.",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)


@bot.command(name="pingleaderboard")
async def pingleaderboard_cmd(ctx):
    limit = int(await get_setting("ping_leaderboard_size"))
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, COUNT(*) as cnt FROM pings GROUP BY user_id ORDER BY cnt DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()

    if not rows:
        await ctx.send("No pings recorded yet.")
        return

    embed = discord.Embed(title="Ping Leaderboard", color=discord.Color.gold())
    description = ""
    medals = ["🥇", "🥈", "🥉"]
    for i, (user_id, count) in enumerate(rows):
        prefix = medals[i] if i < 3 else f"**{i+1}.**"
        description += f"{prefix} <@{user_id}> — {count} pings\n"
    embed.description = description
    await ctx.send(embed=embed)


@bot.command(name="mylevel")
async def mylevel_cmd(ctx):
    user = ctx.author
    total = await count_total("pings", user.id)
    window = int(await get_setting("maintenance_window_days"))
    recent = await count_in_window("pings", user.id, window)
    media_count = await count_in_window("media", user.id, window)
    chat_count = await count_in_window("chat", user.id, int(await get_setting("chat_window_days")))
    hunter_role = ctx.guild.get_role(POKEMON_HUNTER_ROLE_ID)
    has_hunter = hunter_role in user.roles if hunter_role else False

    embed = discord.Embed(title=f"Your Activity — {user.display_name}", color=discord.Color.purple())
    embed.add_field(name="Total Pings", value=str(total), inline=True)
    embed.add_field(name=f"Pings ({window}d)", value=str(recent), inline=True)
    embed.add_field(name="Media Posts", value=str(media_count), inline=True)
    embed.add_field(name="Chat Messages", value=str(chat_count), inline=True)
    embed.add_field(name="Pokemon Hunter", value="✅ Yes" if has_hunter else "❌ No", inline=True)

    status = "✅ Maintaining" if has_hunter else "⏳ Not yet"
    embed.add_field(name="Status", value=status, inline=True)
    await ctx.send(embed=embed)


# ─── Admin Commands ──────────────────────────────────────────────────────────

@bot.command(name="whitelist")
@commands.has_role(ADMIN_ROLE_ID)
async def whitelist_cmd(ctx, action: str = None, member: discord.Member = None):
    if action not in ("add", "remove") or not member:
        await ctx.send("Usage: `!whitelist add/remove @user`")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        if action == "add":
            await db.execute(
                "INSERT OR REPLACE INTO whitelist (user_id, added_by, timestamp) VALUES (?, ?, ?)",
                (member.id, ctx.author.id, now_iso())
            )
            hunter_role = ctx.guild.get_role(POKEMON_HUNTER_ROLE_ID)
            if hunter_role and hunter_role not in member.roles:
                await member.add_roles(hunter_role, reason="Whitelisted by admin")
            await ctx.send(f"✅ {member.mention} has been whitelisted (permanent Hunter access).")
        else:
            await db.execute("DELETE FROM whitelist WHERE user_id = ?", (member.id,))
            await ctx.send(f"✅ {member.mention} has been removed from the whitelist.")
        await db.commit()


@bot.command(name="resetpings")
@commands.has_role(ADMIN_ROLE_ID)
async def resetpings_cmd(ctx, member: discord.Member = None):
    if not member:
        await ctx.send("Usage: `!resetpings @user`")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pings WHERE user_id = ?", (member.id,))
        await db.commit()
    await ctx.send(f"✅ All pings cleared for {member.mention}.")


@bot.command(name="resetallpings")
@commands.has_role(ADMIN_ROLE_ID)
async def resetallpings_cmd(ctx):
    confirm_msg = await ctx.send("⚠️ Are you sure? Type `!confirm` in the next 30 seconds to proceed.")

    def check(m):
        return m.author.id == ctx.author.id and m.content.lower() == "!confirm"

    try:
        await bot.wait_for("message", check=check, timeout=30)
    except asyncio.TimeoutError:
        await confirm_msg.edit(content="❌ Reset cancelled (timed out).")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pings")
        await db.commit()
    await ctx.send("✅ All ping history has been cleared.")


@bot.command(name="settings")
@commands.has_role(ADMIN_ROLE_ID)
async def settings_cmd(ctx):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT key, value FROM settings ORDER BY key")
        rows = await cursor.fetchall()

    embed = discord.Embed(title="Bot Settings", color=discord.Color.orange())
    for key, value in rows:
        embed.add_field(name=key, value=f"`{value}`", inline=True)
    await ctx.send(embed=embed)


@bot.command(name="set")
@commands.has_role(ADMIN_ROLE_ID)
async def set_cmd(ctx, key: str = None, value: str = None):
    if not key or not value:
        await ctx.send("Usage: `!set <key> <value>`\nUse `!settings` to see available keys.")
        return

    valid_keys = list(CONFIG.keys())
    if key not in valid_keys:
        await ctx.send(f"❌ Unknown setting `{key}`. Valid keys: {', '.join(valid_keys)}")
        return

    await set_setting(key, value)
    CONFIG[key] = value
    await ctx.send(f"✅ Setting `{key}` updated to `{value}`.")


@bot.command(name="sync")
@commands.has_role(ADMIN_ROLE_ID)
async def sync_cmd(ctx):
    await ctx.send("🔄 Running access check on all members...")
    guild = ctx.guild
    count = 0
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT user_id FROM pings")
        rows = await cursor.fetchall()
        for (user_id,) in rows:
            member = guild.get_member(user_id)
            if member:
                await check_access(user_id, guild)
                count += 1
    await ctx.send(f"✅ Access check complete. Processed {count} members.")


@bot.command(name="mee6sync")
@commands.has_role(ADMIN_ROLE_ID)
async def mee6sync_cmd(ctx):
    if not MEE6_SILVER_ROLE_ID:
        await ctx.send("❌ MEE6 Silver Role ID not configured in .env")
        return

    await ctx.send("🔄 Syncing MEE6 Silver+ members...")
    guild = ctx.guild
    silver_role = guild.get_role(MEE6_SILVER_ROLE_ID)
    hunter_role = guild.get_role(POKEMON_HUNTER_ROLE_ID)
    if not silver_role or not hunter_role:
        await ctx.send("❌ Could not find Silver or Hunter role.")
        return

    count = 0
    for member in guild.members:
        if silver_role in member.roles and hunter_role not in member.roles:
            try:
                await member.add_roles(hunter_role, reason="MEE6 sync")
                count += 1
            except discord.Forbidden:
                pass
    await ctx.send(f"✅ Sync complete. Granted Hunter role to {count} MEE6 Silver+ members.")


@bot.command(name="mee6import")
@commands.has_role(ADMIN_ROLE_ID)
async def mee6import_cmd(ctx, level_threshold: int = None):
    """Import MEE6 level data via API and grant Hunter to members at or above threshold.
    Usage: !mee6import [level_threshold]
    Example: !mee6import 10  (grants Hunter to everyone level 10+)
    If no threshold given, uses the mee6_level_threshold setting from config."""
    guild = ctx.guild
    hunter_role = guild.get_role(POKEMON_HUNTER_ROLE_ID)
    if not hunter_role:
        await ctx.send("❌ Could not find Pokemon Hunter role. Check POKEMON_HUNTER_ROLE_ID in .env")
        return

    if level_threshold is None:
        level_threshold = int(await get_setting("mee6_level_threshold"))

    await ctx.send(f"🔄 Fetching MEE6 level data (granting Hunter to level {level_threshold}+)...")

    mee6_levels = {}
    page = 0
    limit = 1000

    async with aiohttp.ClientSession() as session:
        while True:
            url = f"https://mee6.xyz/api/plugins/levels/leaderboard/{guild.id}?page={page}"
            async with session.get(url) as resp:
                if resp.status == 429:
                    await ctx.send("⏳ Rate limited by MEE6 API, waiting 10 seconds...")
                    await asyncio.sleep(10)
                    continue
                if resp.status != 200:
                    await ctx.send(
                        f"❌ MEE6 API returned status {resp.status}. "
                        f"Make sure the leaderboard is set to **public** in MEE6 dashboard → Levels → "
                        f"'Make my server's leaderboard public'"
                    )
                    return
                data = await resp.json()

            members = data.get("members", [])
            if not members:
                break

            for m in members:
                user_id = int(m.get("id", 0))
                xp = m.get("xp", 0)
                level = m.get("level", 0)
                mee6_levels[user_id] = {"xp": xp, "level": level}

            if len(members) < limit:
                break
            page += 1
            await asyncio.sleep(1)

    if not mee6_levels:
        await ctx.send("❌ No MEE6 data found. Is MEE6 Levels plugin enabled in this server?")
        return

    granted = 0
    skipped = 0
    not_in_server = 0
    below_threshold = 0
    level_breakdown = {}

    for user_id, data in mee6_levels.items():
        lvl = data["level"]
        level_breakdown[lvl] = level_breakdown.get(lvl, 0) + 1

        member = guild.get_member(user_id)
        if not member:
            not_in_server += 1
            continue

        if hunter_role in member.roles:
            skipped += 1
            continue

        if lvl >= level_threshold:
            try:
                await member.add_roles(hunter_role, reason=f"MEE6 import: Level {lvl}")
                granted += 1
            except discord.Forbidden:
                pass
        else:
            below_threshold += 1

    top_levels = sorted(level_breakdown.items(), reverse=True)[:10]
    top_display = ", ".join([f"Lvl {lvl}: {count}" for lvl, count in top_levels])

    summary = (
        f"✅ MEE6 import complete! (threshold: level {level_threshold})\n"
        f"• **{granted}** members granted Hunter role\n"
        f"• **{skipped}** already had Hunter\n"
        f"• **{below_threshold}** below level {level_threshold}\n"
        f"• **{not_in_server}** MEE6 members not in server\n"
        f"• **{len(mee6_levels)}** total MEE6 members processed\n"
        f"• Top levels: {top_display}"
    )
    await ctx.send(summary)


@bot.command(name="mee6scan")
@commands.has_role(ADMIN_ROLE_ID)
async def mee6scan_cmd(ctx, level_threshold: int = None):
    """Scan message history for MEE6 level-up messages and grant Hunter to members at or above threshold.
    Usage: !mee6scan [level_threshold]
    Example: !mee6scan 10  (grants Hunter to everyone who reached level 10+)"""
    guild = ctx.guild
    hunter_role = guild.get_role(POKEMON_HUNTER_ROLE_ID)
    if not hunter_role:
        await ctx.send("❌ Could not find Pokemon Hunter role.")
        return

    global scan_in_progress
    if scan_in_progress:
        await ctx.send("❌ A scan is already running. Wait for it to finish.")
        return
    scan_in_progress = True

    if level_threshold is None:
        level_threshold = int(await get_setting("mee6_level_threshold"))

    await ctx.send(f"🔄 Scanning message history for MEE6 level-up messages (threshold: level {level_threshold})...")

    mee6_users = {}
    scanned_channels = 0
    total_messages = 0
    level_ups_found = 0
    progress_msg = await ctx.send("📡 Starting scan...")
    last_update = 0

    mee6_keywords = ["reached level", "level up", "just reached", "is now level", "has reached level", "leveled up"]

    channels_to_scan = [ch for ch in guild.text_channels]
    total_channels = len(channels_to_scan)

    for channel in channels_to_scan:
        try:
            permissions = channel.permissions_for(guild.me)
            if not permissions.read_message_history:
                continue
        except discord.Forbidden:
            continue

        scanned_channels += 1

        if scanned_channels - last_update >= 3 or scanned_channels == total_channels:
            try:
                await progress_msg.edit(
                    content=f"📡 Scanning... Channel **{scanned_channels}/{total_channels}** | "
                            f"Messages: {total_messages:,} | Level-ups found: {level_ups_found} | "
                            f"Users: {len(mee6_users)}"
                )
                last_update = scanned_channels
            except discord.Forbidden:
                pass

        try:
            async for message in channel.history(limit=5000, oldest_first=False):
                total_messages += 1

                if message.author.bot is not True:
                    continue

                if message.author.id != 159962941502783488:
                    continue

                content_lower = message.content.lower()
                is_level_up = any(kw in content_lower for kw in mee6_keywords)

                if not is_level_up:
                    continue

                level_ups_found += 1

                import re
                level_match = re.search(r'level\s+(\d+)', content_lower)
                if not level_match:
                    continue

                level = int(level_match.group(1))

                if message.mentions:
                    for user in message.mentions:
                        if user.bot:
                            continue
                        if user.id in mee6_users:
                            mee6_users[user.id] = max(mee6_users[user.id], level)
                        else:
                            mee6_users[user.id] = level

        except discord.Forbidden:
            continue
        except Exception as e:
            continue

    try:
        await progress_msg.edit(content=f"✅ Scan complete! Processing results...")
    except discord.Forbidden:
        pass

    if not mee6_users:
        await ctx.send(
            f"❌ No MEE6 level-up messages found.\n"
            f"• Scanned {scanned_channels} channels, {total_messages} messages\n"
            f"• Make sure MEE6 is posting level-up messages in your server"
        )
        scan_in_progress = False
        return

    granted = 0
    skipped = 0
    below_threshold = 0
    not_in_server = 0
    level_breakdown = {}

    for user_id, level in mee6_users.items():
        level_breakdown[level] = level_breakdown.get(level, 0) + 1

        member = guild.get_member(user_id)
        if not member:
            not_in_server += 1
            continue

        if hunter_role in member.roles:
            skipped += 1
            continue

        if level >= level_threshold:
            try:
                await member.add_roles(hunter_role, reason=f"MEE6 scan: Level {level}")
                granted += 1
            except discord.Forbidden:
                pass
        else:
            below_threshold += 1

    top_levels = sorted(level_breakdown.items(), reverse=True)[:10]
    top_display = ", ".join([f"Lvl {lvl}: {count}" for lvl, count in top_levels])

    summary = (
        f"✅ MEE6 scan complete! (threshold: level {level_threshold})\n"
        f"• Scanned **{scanned_channels}** channels, **{total_messages}** messages\n"
        f"• Found **{level_ups_found}** level-up messages\n"
        f"• **{granted}** members granted Hunter role\n"
        f"• **{skipped}** already had Hunter\n"
        f"• **{below_threshold}** below level {level_threshold}\n"
        f"• **{not_in_server}** members not in server\n"
        f"• **{len(mee6_users)}** unique users found\n"
        f"• Top levels: {top_display}"
    )
    await ctx.send(summary)
    scan_in_progress = False

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ You don't have permission to use that command.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Member not found.")
    else:
        await ctx.send(f"❌ Error: {error}")


# ─── Run ─────────────────────────────────────────────────────────────────────

async def main():
    await init_db()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
