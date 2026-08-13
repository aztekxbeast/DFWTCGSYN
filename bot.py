import os
import re
import json
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from collections import defaultdict
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
ANNOUNCEMENTS_CHANNEL_ID = int(os.getenv("ANNOUNCEMENTS_CHANNEL_ID", "1502087476305461349"))
GETROLES_CHANNEL_ID = int(os.getenv("GETROLES_CHANNEL_ID", "1502144792358817933"))
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

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
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
                timestamp TEXT NOT NULL,
                message_content TEXT,
                location TEXT,
                message_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                image_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS chat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                message_content TEXT
            );
            CREATE TABLE IF NOT EXISTS flagged_pings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ping_id INTEGER NOT NULL,
                reported_by INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT,
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
            CREATE TABLE IF NOT EXISTS location_aliases (
                alias TEXT PRIMARY KEY,
                store TEXT NOT NULL,
                added_by INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hunter_role_earned (
                user_id INTEGER PRIMARY KEY,
                earned_at TEXT NOT NULL
            );
        """)
        # Migrations for existing database schemas
        try:
            await db.execute("ALTER TABLE pings ADD COLUMN location TEXT")
        except Exception:
            pass  # Column already exists
        try:
            await db.execute("ALTER TABLE media ADD COLUMN image_hash TEXT")
        except Exception:
            pass  # Column already exists
        try:
            await db.execute("ALTER TABLE chat ADD COLUMN message_content TEXT")
        except Exception:
            pass  # Column already exists
        # Migration: add message_id column for jump links
        try:
            await db.execute("ALTER TABLE pings ADD COLUMN message_id INTEGER")
        except Exception:
            pass  # Column already exists
        await db.commit()
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


async def record_hunter_role_earned(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO hunter_role_earned (user_id, earned_at) VALUES (?, ?)",
            (user_id, now_iso())
        )
        await db.commit()


def days_ago_iso(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def is_admin_or_mod(member):
    return any(r.id in (ADMIN_ROLE_ID, MOD_ROLE_ID) for r in member.roles)


def get_announcement_channel(guild):
    for ch in guild.text_channels:
        if ch.name == "poke-hunter-access":
            return ch
    return guild.get_channel(ANNOUNCEMENTS_CHANNEL_ID)


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


def extract_location_from_text(content):
    """Extract location words from a ping message."""
    if not content:
        return None
    c = content.lower()
    # Strip Discord mentions: <@!123>, <@&123>, <@123>
    c = re.sub(r'<@!?\d+>', ' ', c)
    c = re.sub(r'<@&\d+>', ' ', c)
    # Strip @location/@oos prefix
    c = re.sub(r'@(location|oos)\s*', ' ', c)
    # Remove store names
    store_list = CONFIG.get("store_channels", [])
    for store in store_list:
        c = c.replace(store, ' ').replace(store.replace('-', ' '), ' ')
    # Remove abbreviations
    for abbr in STORE_ABBREVIATIONS:
        c = c.replace(abbr, ' ')
    # Clean common words
    stop_words = [
        'at', 'on', 'in', 'the', 'has', 'have', 'stock', 'restock', 'found',
        'just', 'got', 'etb', 'etbs', 'blisters', 'pc', 'exclusive', 'tin',
        'tins', 'box', 'boxes', 'packs', 'collection', 'nothing', 'yet',
        'fresh', 'drop', 'hits', 'hit', 'securing', 'secured', 'available',
        'left', 'only', 'none', 'empty', 'cleared', 'wiped', 'asking',
        'price', 'sell', 'selling', 'trade', 'want', 'oos', 'location',
        'pokémon', 'pokemon', 'is', 'stocking', 'stock', 'no', 'not',
        'but', 'and', 'or', 'with', 'for', 'to', 'of', 'it', 'be',
        'supposedly', 'outside', 'waiting', 'people', 'line', 'about',
        'drove', 'asking', 'deep', 'back', 'front'
    ]
    for w in stop_words:
        c = re.sub(r'\b' + re.escape(w) + r'\b', ' ', c)
    # Remove non-alpha characters
    c = re.sub(r'[^\w\s]', ' ', c).strip()
    c = re.sub(r'\s+', ' ', c).strip()
    # Take only first few words as location (max 2 words)
    words = c.split()[:2]
    return ' '.join(words) if words else None


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


STORE_ABBREVIATIONS = {
    "dg": "dollar-tree-dollar-general-family-dollar",
    "dt": "dollar-tree-dollar-general-family-dollar",
    "fd": "dollar-tree-dollar-general-family-dollar",
    "dollar general": "dollar-tree-dollar-general-family-dollar",
    "dollar-general": "dollar-tree-dollar-general-family-dollar",
    "dollar tree": "dollar-tree-dollar-general-family-dollar",
    "dollar-tree": "dollar-tree-dollar-general-family-dollar",
    "family dollar": "dollar-tree-dollar-general-family-dollar",
    "family-dollar": "dollar-tree-dollar-general-family-dollar",
    "familydollar": "dollar-tree-dollar-general-family-dollar",
    "familydollars": "dollar-tree-dollar-general-family-dollar",
    "@familydollar": "dollar-tree-dollar-general-family-dollar",
    "@familydollars": "dollar-tree-dollar-general-family-dollar",
    "@dollar general": "dollar-tree-dollar-general-family-dollar",
    "@dollar tree": "dollar-tree-dollar-general-family-dollar",
    "@dollar-general": "dollar-tree-dollar-general-family-dollar",
    "@dollar-tree": "dollar-tree-dollar-general-family-dollar",
    "@dollargeneral": "dollar-tree-dollar-general-family-dollar",
    "@dollartree": "dollar-tree-dollar-general-family-dollar",
    "ace": "others",
    "ace hardware": "others",
    "bn": "barnes-and-noble",
    "b&n": "barnes-and-noble",
    "barnes noble": "barnes-and-noble",
    "barnesandnoble": "barnes-and-noble",
    "@barnesandnoble": "barnes-and-noble",
    "bb": "best-buy",
    "bestbuy": "best-buy",
    "@bestbuy": "best-buy",
    "gs": "gamestop",
    "@gamestop": "gamestop",
    "mc": "micro-center",
    "microcenter": "micro-center",
    "@microcenter": "micro-center",
    "sam": "sam's-costco",
    "costco": "sam's-costco",
    "sams": "sam's-costco",
    "sam's": "sam's-costco",
    "@sams": "sam's-costco",
    "@costco": "sam's-costco",
    "wc": "walgreens-cvs",
    "wag": "walgreens-cvs",
    "walgreens": "walgreens-cvs",
    "cvs": "walgreens-cvs",
    "@walgreens": "walgreens-cvs",
    "@cvs": "walgreens-cvs",
    "pc": "pokemon-center",
    "pk": "pokemon-center",
    "pokemoncenter": "pokemon-center",
    "@pokemoncenter": "pokemon-center",
    "km": "kroger",
    "@kroger": "kroger",
    "@walmart": "walmart",
    "@target": "target",
    "@aldi": "aldi",
    "@academy": "academy",
    "@amazon": "amazon",
    "@mitsuwa": "mitsuwa",
    "@scheels": "scheels",
    "@gamestop": "gamestop",
}

# Location aliases — vague location words that map to a specific store
LOCATION_WORDS = [
    "alliance", "glade", "custer", "watauga", "beach", "carroll",
    "lakewood", "richardson", "plano", "mesa", "hulen", "west7th",
    "sunset", "highland", "park", "lake", "north", "south", "east", "west",
    "keller", "grapevine", "flower", "mound", "hurst", "bedford", "euless",
    "arlington", "mansfield", "cedar", "hill", "duncan", "denton",
]


def extract_store_from_text(message):
    store_mentions = []
    content_lower = message.content.lower()
    store_list = CONFIG.get("store_channels", [])

    # Check actual role mentions
    role_names = [r.name.lower() for r in message.role_mentions]
    has_location_ping = "location" in role_names
    has_oos_ping = "oos" in role_names

    # Check for store-specific role mentions (e.g. @walmart, @target)
    store_role_pings = []
    for role in message.role_mentions:
        role_name = role.name.lower()
        if role_name in store_list or role_name.replace(" ", "-") in store_list:
            store_role_pings.append(role_name)

    # Also check for text-based mentions (when user can't actually ping the role)
    if not has_location_ping and "@location" in content_lower:
        has_location_ping = True
    if not has_oos_ping and "@oos" in content_lower:
        has_oos_ping = True

    # Check for text-based store role mentions
    for store in store_list:
        text_mention = f"@{store}"
        text_mention_space = f"@{store.replace('-', ' ')}"
        if text_mention in content_lower or text_mention_space in content_lower:
            if store not in store_role_pings:
                store_role_pings.append(store)

    # Check abbreviations
    words = content_lower.split()
    for abbr, store_channel in STORE_ABBREVIATIONS.items():
        if abbr in words and store_channel not in store_role_pings:
            store_role_pings.append(store_channel)

    # If store roles were pinged directly, log them
    if store_role_pings:
        ping_type = "location"
        for store in store_role_pings:
            store_mentions.append({
                "role_type": ping_type,
                "channel": message.channel.name,
                "store": store
            })
        return store_mentions

    if not has_location_ping and not has_oos_ping:
        return store_mentions

    ping_type = "location" if has_location_ping else "oos"

    for store in store_list:
        if store in content_lower or store.replace("-", " ") in content_lower:
            store_mentions.append({
                "role_type": ping_type,
                "channel": message.channel.name,
                "store": store
            })

    # Check abbreviations if no store matched yet
    if not store_mentions:
        words = content_lower.split()
        for abbr, store_channel in STORE_ABBREVIATIONS.items():
            if abbr in words:
                store_mentions.append({
                    "role_type": ping_type,
                    "channel": message.channel.name,
                    "store": store_channel
                })
                break

    if not store_mentions and message.channel.name in store_list:
        store_mentions.append({
            "role_type": ping_type,
            "channel": message.channel.name,
            "store": message.channel.name
        })

    # If no store match but we detected a ping, log it with channel name
    if not store_mentions:
        store_mentions.append({
            "role_type": ping_type,
            "channel": message.channel.name,
            "store": message.channel.name
        })

    return store_mentions


import hashlib

async def log_ping(user_id, channel_id, store, mention_type, content=None, location=None, message_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO pings (user_id, channel_id, store, mention_type, timestamp, message_content, location, message_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, channel_id, store, mention_type, now_iso(), content, location, message_id)
        )
        ping_id = cursor.lastrowid
        await db.commit()
        return ping_id


async def log_media(user_id, channel_id, attachment=None):
    img_hash = None
    if attachment:
        try:
            # Generate MD5 hash of attachment bytes to detect duplicate image uploads
            data = await attachment.read()
            img_hash = hashlib.md5(data).hexdigest()
        except Exception:
            pass

    async with aiosqlite.connect(DB_PATH) as db:
        if img_hash:
            # Check if this exact image hash was already logged by this user (or any user) in recent history
            cursor = await db.execute(
                "SELECT id FROM media WHERE image_hash = ?", (img_hash,)
            )
            if await cursor.fetchone():
                return False  # Duplicate image detected, ignore

        await db.execute(
            "INSERT INTO media (user_id, channel_id, timestamp, image_hash) VALUES (?, ?, ?, ?)",
            (user_id, channel_id, now_iso(), img_hash)
        )
        await db.commit()
        return True


async def log_chat(user_id, channel_id, content=""):
    if not content:
        return False

    clean_content = content.strip()
    
    # Requirement: 15+ character minimum for chat tracking
    if len(clean_content) < 15:
        return False

    async with aiosqlite.connect(DB_PATH) as db:
        # Anti-Spam: Check if user sent the EXACT same message content in the last 24 hours
        cutoff = days_ago_iso(1)
        cursor = await db.execute(
            "SELECT id FROM chat WHERE user_id = ? AND message_content = ? AND timestamp >= ?",
            (user_id, clean_content[:500], cutoff)
        )
        if await cursor.fetchone():
            return False  # Duplicate message detected, ignore

        await db.execute(
            "INSERT INTO chat (user_id, channel_id, timestamp, message_content) VALUES (?, ?, ?, ?)",
            (user_id, channel_id, now_iso(), clean_content[:500])
        )
        await db.commit()
        return True


# ─── Access Engine ───────────────────────────────────────────────────────────

async def check_grant_access(user_id, guild):
    """Only GRANT access when ping threshold is reached. Never revoke on message."""
    member = guild.get_member(user_id)
    if not member:
        return

    hunter_role = guild.get_role(POKEMON_HUNTER_ROLE_ID)
    if not hunter_role:
        return

    if hunter_role in member.roles:
        return

    total_pings = await count_total("pings", user_id)
    required = int(await get_setting("pings_to_gain"))
    if total_pings >= required:
        await member.add_roles(hunter_role, reason="Reached ping threshold")
        await record_hunter_role_earned(user_id)
        channel = get_announcement_channel(guild)
        if channel:
            try:
                await channel.send(
                    f"🎉 {member.mention} has earned the **Pokemon Hunter** role! "
                    f"You now have access to all store channels."
                )
            except discord.Forbidden:
                pass


async def check_access(user_id, guild):
    """Full check — used only by daily maintenance task."""
    member = guild.get_member(user_id)
    if not member:
        return

    hunter_role = guild.get_role(POKEMON_HUNTER_ROLE_ID)
    if not hunter_role:
        return

    if hunter_role in member.roles:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id FROM whitelist WHERE user_id = ?", (user_id,)
            )
            if await cursor.fetchone():
                return

        # Don't revoke until user has had the role for the full maintenance window
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT earned_at FROM hunter_role_earned WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                earned_at = datetime.fromisoformat(row[0])
                window = int(await get_setting("maintenance_window_days"))
                if datetime.now(timezone.utc) < earned_at + timedelta(days=window):
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
        channel = get_announcement_channel(guild)
        if channel:
            try:
                await channel.send(
                    f"⚠️ {member.mention} has lost the **Pokemon Hunter** role due to inactivity. "
                    f"You need to keep posting pings to maintain access."
                )
            except discord.Forbidden:
                pass
    else:
        total_pings = await count_total("pings", user_id)
        required = int(await get_setting("pings_to_gain"))
        if total_pings >= required:
            await member.add_roles(hunter_role, reason="Reached ping threshold")
            await record_hunter_role_earned(user_id)
            channel = get_announcement_channel(guild)
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

    # Record bot start time (only set once, never overwritten)
    existing_start = await get_setting("bot_start_time")
    if not existing_start:
        await set_setting("bot_start_time", datetime.now(timezone.utc).isoformat())

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
                await record_hunter_role_earned(member.id)
                channel = get_announcement_channel(member.guild)
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
    # Check for MEE6 achievement announcements (Gold/Diamond)
    if message.author.bot and message.author.name == "MEE6":
        content = message.content.lower()
        if "(gold)" in content or "(diamond)" in content:
            if message.mentions:
                guild = message.guild
                hunter_role = guild.get_role(POKEMON_HUNTER_ROLE_ID)
                if hunter_role:
                    for user in message.mentions:
                        member = guild.get_member(user.id)
                        if member and hunter_role not in member.roles:
                            try:
                                await member.add_roles(hunter_role, reason="MEE6 Gold/Diamond achievement")
                                await record_hunter_role_earned(member.id)
                                # Post to #poke-hunter-access
                                for ch in guild.text_channels:
                                    if ch.name == "poke-hunter-access":
                                        await ch.send(
                                            f"🏆 {member.mention} earned a MEE6 Gold/Diamond achievement and has been granted **Pokemon Hunter** access!"
                                        )
                                        break
                            except discord.Forbidden:
                                pass
        return

    if message.author.bot:
        return
    if not message.guild:
        return

    await bot.process_commands(message)

    channel_id = message.channel.id
    user_id = message.author.id

    # Track pings in all channels except server-announcements and get-roles (max 1 ping per message)
    if message.channel.id not in (ANNOUNCEMENTS_CHANNEL_ID, GETROLES_CHANNEL_ID):
        store_mentions = extract_store_from_text(message)
        if store_mentions:
            loc = extract_location_from_text(message.content)
            await log_ping(user_id, channel_id, store_mentions[0]["store"], store_mentions[0]["role_type"], message.content[:500], loc, message.id)
            await check_grant_access(user_id, message.guild)

    # Track media (attachments) only in media channels
    media_channels = CONFIG.get("media_channels", [])
    if message.channel.name in media_channels:
        if message.attachments:
            for attachment in message.attachments:
                logged = await log_media(user_id, channel_id, attachment)
                if logged:
                    await check_grant_access(user_id, message.guild)

    # Track chat messages in all channels except server-announcements and get-roles
    if message.channel.id not in (ANNOUNCEMENTS_CHANNEL_ID, GETROLES_CHANNEL_ID):
        await log_chat(user_id, channel_id, message.content)


@bot.event
async def on_raw_reaction_add(payload):
    """Allow Hunter role holders, Admins, and Mods to report fake pings with 🚩 reaction."""
    if str(payload.emoji) != "🚩":
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    user = guild.get_member(payload.user_id)
    if not user or user.bot:
        return

    # Check if reporter is Hunter, Admin, or Mod
    hunter_role = guild.get_role(POKEMON_HUNTER_ROLE_ID)
    is_authorized = is_admin_or_mod(user) or (hunter_role and hunter_role in user.roles)
    if not is_authorized:
        return

    channel = guild.get_channel(payload.channel_id)
    if not channel:
        return

    try:
        message = await channel.fetch_message(payload.message_id)
    except Exception:
        return

    if message.author.bot:
        return

    # Check if this message contained a recorded ping in SQLite
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, user_id FROM pings WHERE channel_id = ? AND timestamp LIKE ?",
            (channel.id, f"{message.created_at.strftime('%Y-%m-%d')}%")
        )
        ping_rows = await cursor.fetchall()
        
        # Match ping content if possible
        matched_ping = None
        for pid, p_uid in ping_rows:
            if p_uid == message.author.id:
                matched_ping = (pid, p_uid)
                break

        if matched_ping:
            ping_id, author_id = matched_ping
            # Check if already flagged
            c_check = await db.execute("SELECT id FROM flagged_pings WHERE ping_id = ?", (ping_id,))
            if await c_check.fetchone():
                return  # Already flagged

            # Record flag
            await db.execute(
                "INSERT INTO flagged_pings (ping_id, reported_by, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                (ping_id, user.id, author_id, "Reaction 🚩 flag", now_iso())
            )
            # Remove original ping from table
            await db.execute("DELETE FROM pings WHERE id = ?", (ping_id,))
            # Deduct double points (Insert penalty dummy ping or remove extra ping)
            # To deduct double ping points (-2 pings penalty): delete 1 extra ping if exists
            await db.execute(
                "DELETE FROM pings WHERE id IN (SELECT id FROM pings WHERE user_id = ? ORDER BY id DESC LIMIT 1)",
                (author_id,)
            )
            await db.commit()

            try:
                await channel.send(
                    f"🚩 **Ping Flagged & Removed:** {user.mention} flagged a suspicious ping by {message.author.mention}. "
                    f"Double ping points (-2) deducted as a penalty."
                )
            except discord.Forbidden:
                pass


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
    required = int(await get_setting("pings_to_gain"))
    hunter_role = ctx.guild.get_role(POKEMON_HUNTER_ROLE_ID)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, COUNT(*) as cnt FROM pings GROUP BY user_id ORDER BY cnt DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()

    if not rows:
        await ctx.send("No pings recorded yet.")
        return

    embed = discord.Embed(
        title="Ping Leaderboard",
        description=f"**{required}** pings needed for **Pokemon Hunter** role",
        color=discord.Color.gold()
    )
    description = ""
    medals = ["🥇", "🥈", "🥉"]
    for i, (user_id, count) in enumerate(rows):
        prefix = medals[i] if i < 3 else f"**{i+1}.**"
        member = ctx.guild.get_member(user_id)
        has_hunter = hunter_role in member.roles if member and hunter_role else False
        status = "✅" if has_hunter else f"({count}/{required})"
        description += f"{prefix} <@{user_id}> — {count} pings {status}\n"
    embed.description = description
    await ctx.send(embed=embed)


@bot.command(name="mylevel", aliases=["mystatus", "status", "me"])
async def mylevel_cmd(ctx):
    user = ctx.author
    total = await count_total("pings", user.id)
    window = int(await get_setting("maintenance_window_days"))
    recent = await count_in_window("pings", user.id, window)
    media_count = await count_in_window("media", user.id, window)
    chat_count = await count_in_window("chat", user.id, int(await get_setting("chat_window_days")))
    hunter_role = ctx.guild.get_role(POKEMON_HUNTER_ROLE_ID)
    has_hunter = hunter_role in user.roles if hunter_role else False
    required = int(await get_setting("pings_to_gain"))

    embed = discord.Embed(title=f"Your Activity — {user.display_name}", color=discord.Color.purple())
    embed.add_field(name="Total Pings", value=str(total), inline=True)
    embed.add_field(name=f"Pings ({window}d)", value=str(recent), inline=True)
    embed.add_field(name="Media Posts", value=str(media_count), inline=True)
    embed.add_field(name="Chat Messages", value=str(chat_count), inline=True)
    embed.add_field(name="Pokemon Hunter", value="✅ Yes" if has_hunter else "❌ No", inline=True)

    if has_hunter:
        status = "✅ Maintaining"
    else:
        needed = max(0, required - total)
        if needed > 0:
            status = f"⏳ {needed} more ping(s) needed ({total}/{required})"
        else:
            status = "⏳ Eligible — run `!sync` to get role"
    embed.add_field(name="Status", value=status, inline=False)
    await ctx.send(embed=embed)


# ─── Help Command ───────────────────────────────────────────────────────────

@bot.command(name="helpme")
async def helpme_cmd(ctx):
    embed = discord.Embed(
        title="PokeHunt Bot — Commands",
        description="Track your activity and earn the **Pokemon Hunter** role!",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="📊 Your Stats",
        value=(
            "`!pings` — Your ping count (last 14 days)\n"
            "`!pings @user` — Check someone else's pings\n"
            "`!pingtotal` — Your total lifetime pings\n"
            "`!pingtotal @user` — Someone else's total pings\n"
            "`!pingleaderboard` — Top ping contributors\n"
            "`!mylevel` — Full activity breakdown\n"
            "`!helpme` — Show this message"
        ),
        inline=False
    )

    embed.add_field(
        name="🎯 How to Earn Pokemon Hunter",
        value=(
            "• Post **10 pings** (mention `@location` or `@OOS` in any channel)\n"
            "• Once you hit 10, you unlock the role automatically\n"
            "• Use `!pings` to check your progress"
        ),
        inline=False
    )

    if is_admin_or_mod(ctx.author):
        embed.add_field(
            name="🛡️ Admin Commands",
            value=(
                "`!whitelist add @user` — Grant permanent Hunter access\n"
                "`!whitelist remove @user` — Remove from whitelist\n"
                "`!resetpings @user` — Clear a user's ping history\n"
                "`!resetallpings` — Clear ALL ping history\n"
                "`!stats @user` — Detailed stats for a user\n"
                "`!allStats` — Server-wide activity overview\n"
                "`!sync` — Run manual access check"
            ),
            inline=False
        )
        embed.add_field(
            name="📊 Restock Tracking",
            value=(
                "`!predict <store>` — Predict next restock\n"
                "`!predict <store> <location>` — e.g. `!predict target alliance`\n"
                "`!rh <store>` — Recent restock dates\n"
                "`!rh <store> <location>` — e.g. `!rh walmart beach`\n"
                "`!deepbackfill` — Scan for past pings (7 days)\n"
                "`!deepbackfill 14` — Scan last 14 days\n"
                "`!addlocation <word>` — Add a location word\n"
                "`!removelocation <word>` — Remove a location word\n"
                "`!listlocations` — Show all location words"
            ),
            inline=False
        )

    embed.set_footer(text="PokeHunt Bot • DFW TCG Syndicate")
    await ctx.send(embed=embed)


# ─── Admin Commands ──────────────────────────────────────────────────────────

@bot.command(name="whitelist")
@commands.has_role(ADMIN_ROLE_ID)
async def whitelist_cmd(ctx, action: str = None, target: str = None):
    if action not in ("add", "remove") or not target:
        await ctx.send("Usage: `!whitelist add/remove @user` or `!whitelist add/remove userid`")
        return

    # Try to get member from mention first, then by ID
    member = None
    if ctx.message.mentions:
        member = ctx.message.mentions[0]
    else:
        try:
            user_id = int(target)
            member = ctx.guild.get_member(user_id)
            if not member:
                member = await ctx.guild.fetch_member(user_id)
        except (ValueError, discord.NotFound):
            await ctx.send("❌ Could not find that user. Use `@mention` or their user ID.")
            return

    if not member:
        await ctx.send("❌ Could not find that user in this server.")
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
                await record_hunter_role_earned(member.id)
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


@bot.command(name="confirm", hidden=True)
async def confirm_cmd(ctx):
    pass  # Used by resetallpings confirmation flow


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


@bot.command(name="stats")
@commands.has_role(ADMIN_ROLE_ID)
async def stats_cmd(ctx, target: discord.Member = None):
    """Show detailed stats for a specific user.
    Usage: !stats @user"""
    if not target:
        target = ctx.author

    window = int(await get_setting("maintenance_window_days"))
    total_pings = await count_total("pings", target.id)
    recent_pings = await count_in_window("pings", target.id, window)
    media_count = await count_in_window("media", target.id, window)
    chat_count = await count_in_window("chat", target.id, int(await get_setting("chat_window_days")))
    hunter_role = ctx.guild.get_role(POKEMON_HUNTER_ROLE_ID)
    has_hunter = hunter_role in target.roles if hunter_role else False

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT store, COUNT(*) as cnt FROM pings WHERE user_id = ? GROUP BY store ORDER BY cnt DESC LIMIT 10",
            (target.id,)
        )
        store_rows = await cursor.fetchall()
        cursor = await db.execute(
            "SELECT mention_type, COUNT(*) as cnt FROM pings WHERE user_id = ? GROUP BY mention_type",
            (target.id,)
        )
        type_rows = await cursor.fetchall()
        cursor = await db.execute("SELECT user_id FROM whitelist WHERE user_id = ?", (target.id,))
        is_whitelisted = await cursor.fetchone()

    embed = discord.Embed(
        title=f"Stats — {target.display_name}",
        color=discord.Color.green() if has_hunter else discord.Color.red()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Pokemon Hunter", value="✅ Yes" if has_hunter else "❌ No", inline=True)
    embed.add_field(name="Whitelisted", value="✅ Yes" if is_whitelisted else "❌ No", inline=True)
    embed.add_field(name="Total Pings", value=str(total_pings), inline=True)
    embed.add_field(name=f"Pings ({window}d)", value=str(recent_pings), inline=True)
    embed.add_field(name=f"Required ({window}d)", value=str(await get_setting("pings_to_maintain")), inline=True)
    embed.add_field(name="Media Posts", value=str(media_count), inline=True)
    embed.add_field(name="Chat Messages", value=str(chat_count), inline=True)

    if type_rows:
        type_display = ", ".join([f"{t}: {c}" for t, c in type_rows])
        embed.add_field(name="Ping Types", value=type_display, inline=False)

    if store_rows:
        store_display = "\n".join([f"• **{s}**: {c}" for s, c in store_rows])
        embed.add_field(name="Top Stores", value=store_display, inline=False)

    await ctx.send(embed=embed)


@bot.command(name="allstats")
@commands.has_role(ADMIN_ROLE_ID)
async def allstats_cmd(ctx):
    """Show an overview of all members with activity and Hunter status."""
    guild = ctx.guild
    hunter_role = guild.get_role(POKEMON_HUNTER_ROLE_ID)
    window = int(await get_setting("maintenance_window_days"))
    required = int(await get_setting("pings_to_gain"))

    await ctx.send("🔄 Gathering stats...")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, COUNT(*) as cnt FROM pings GROUP BY user_id ORDER BY cnt DESC"
        )
        all_pingers = await cursor.fetchall()

        cursor = await db.execute(
            f"SELECT user_id, COUNT(*) as cnt FROM pings WHERE timestamp >= ? GROUP BY user_id",
            (days_ago_iso(window),)
        )
        recent_pingers = {uid: cnt for uid, cnt in await cursor.fetchall()}

        cursor = await db.execute("SELECT user_id FROM whitelist")
        whitelisted = {row[0] for row in await cursor.fetchall()}

    hunter_count = 0
    ready_count = 0
    near_count = 0
    inactive_count = 0
    entries = []

    for user_id, total in all_pingers:
        member = guild.get_member(user_id)
        if not member:
            continue

        has_hunter = hunter_role in member.roles if hunter_role else False
        is_wl = user_id in whitelisted
        recent = recent_pingers.get(user_id, 0)
        maintain_req = int(await get_setting("pings_to_maintain"))

        if has_hunter:
            hunter_count += 1
        if total >= required or is_wl:
            ready_count += 1
        elif total >= required * 0.7:
            near_count += 1
        else:
            inactive_count += 1

        entries.append((member.display_name, total, recent, has_hunter, is_wl, user_id))

    total_active = len(all_pingers)
    embed = discord.Embed(title="Server Activity Overview", color=discord.Color.blue())
    embed.add_field(name="Total Active Users", value=str(total_active), inline=True)
    embed.add_field(name="Pokemon Hunter Holders", value=str(hunter_count), inline=True)
    embed.add_field(name="Whitelisted", value=str(len(whitelisted)), inline=True)
    embed.add_field(name=f"Ready ({required}+ pings)", value=str(ready_count), inline=True)
    embed.add_field(name=f"Near Ready (70%+)", value=str(near_count), inline=True)
    embed.add_field(name="Below Threshold", value=str(inactive_count), inline=True)

    top20 = entries[:20]
    if top20:
        leaderboard = ""
        medals = ["🥇", "🥈", "🥉"]
        for i, (name, total, recent, has_h, is_wl, uid) in enumerate(top20):
            prefix = medals[i] if i < 3 else f"**{i+1}.**"
            status = "✅" if has_h else ("⭐" if is_wl else "")
            leaderboard += f"{prefix} {name} — {total} total, {recent} recent {status}\n"
        embed.add_field(name="Top 20 by Total Pings", value=leaderboard, inline=False)

    embed.set_footer(text=f"✅ = Hunter | ⭐ = Whitelisted | Req: {required} pings")
    await ctx.send(embed=embed)


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
                await record_hunter_role_earned(member.id)
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
                await record_hunter_role_earned(member.id)
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
                await record_hunter_role_earned(member.id)
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


@bot.command(name="messagescan")
@commands.has_role(ADMIN_ROLE_ID)
async def messagescan_cmd(ctx, msg_threshold: int = None):
    """Scan message history and grant Hunter to members above a message count threshold.
    Usage: !messagescan [threshold]
    Example: !messagescan 50  (grants Hunter to everyone with 50+ messages)"""
    global scan_in_progress
    if scan_in_progress:
        await ctx.send("❌ A scan is already running. Wait for it to finish.")
        return
    scan_in_progress = True

    guild = ctx.guild
    hunter_role = guild.get_role(POKEMON_HUNTER_ROLE_ID)
    if not hunter_role:
        await ctx.send("❌ Could not find Pokemon Hunter role.")
        scan_in_progress = False
        return

    if msg_threshold is None:
        msg_threshold = int(await get_setting("messages_to_gain"))

    await ctx.send(f"🔄 Scanning message history (threshold: {msg_threshold} messages)...")

    user_messages = {}
    scanned_channels = 0
    total_messages = 0
    progress_msg = await ctx.send("📡 Starting scan...")
    last_update = 0

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
                            f"Messages: {total_messages:,} | Users tracked: {len(user_messages)}"
                )
                last_update = scanned_channels
            except discord.Forbidden:
                pass

        try:
            async for message in channel.history(limit=10000, oldest_first=False):
                total_messages += 1
                if message.author.bot:
                    continue
                uid = message.author.id
                user_messages[uid] = user_messages.get(uid, 0) + 1
        except discord.Forbidden:
            continue
        except Exception:
            continue

    try:
        await progress_msg.edit(content="✅ Scan complete! Processing results...")
    except discord.Forbidden:
        pass

    if not user_messages:
        await ctx.send("❌ No messages found.")
        scan_in_progress = False
        return

    granted = 0
    skipped = 0
    below_threshold = 0
    not_in_server = 0

    for user_id, count in user_messages.items():
        member = guild.get_member(user_id)
        if not member:
            not_in_server += 1
            continue

        if hunter_role in member.roles:
            skipped += 1
            continue

        if count >= msg_threshold:
            try:
                await member.add_roles(hunter_role, reason=f"Message scan: {count} messages")
                await record_hunter_role_earned(member.id)
                granted += 1
            except discord.Forbidden:
                pass
        else:
            below_threshold += 1

    top_users = sorted(user_messages.items(), key=lambda x: x[1], reverse=True)[:10]
    top_display = ", ".join([f"<@{uid}>: {cnt}" for uid, cnt in top_users])

    summary = (
        f"✅ Message scan complete! (threshold: {msg_threshold})\n"
        f"• Scanned **{scanned_channels}** channels, **{total_messages:,}** messages\n"
        f"• **{granted}** members granted Hunter role\n"
        f"• **{skipped}** already had Hunter\n"
        f"• **{below_threshold}** below {msg_threshold} messages\n"
        f"• **{not_in_server}** members not in server\n"
        f"• **{len(user_messages)}** unique users\n"
        f"• Top chatters: {top_display}"
    )
    await ctx.send(summary)
    scan_in_progress = False


@bot.command(name="predict")
@commands.has_role(ADMIN_ROLE_ID)
async def predict_cmd(ctx, *args):
    """Analyze ping patterns and predict next restock.
    Usage: !predict target
    Usage: !predict target watauga (specific location)
    Usage: !predict (shows all stores)"""
    store_list = CONFIG.get("store_channels", [])
    days = 30
    store = None
    location = None

    non_digit_args = [a for a in args if not a.isdigit()]
    digit_args = [a for a in args if a.isdigit()]

    if digit_args:
        days = int(digit_args[0])
    if non_digit_args:
        # Check if first arg is a role mention — resolve to role name
        if ctx.message.role_mentions:
            store = ctx.message.role_mentions[0].name.lower()
            if len(non_digit_args) > 1:
                location = " ".join(non_digit_args[1:]).lower()
        else:
            # Try multi-word store first (e.g. "dollar general", "best buy")
            joined = " ".join(a.lower().lstrip("@").strip("<&>") for a in non_digit_args)
            store = None
            location = None
            # Try progressively shorter prefixes as store names
            for i in range(len(non_digit_args), 0, -1):
                candidate = " ".join(a.lower().lstrip("@").strip("<&>") for a in non_digit_args[:i])
                if candidate in STORE_ABBREVIATIONS or candidate in store_list:
                    store = candidate
                    if i < len(non_digit_args):
                        location = " ".join(non_digit_args[i:]).lower()
                    break
            if store is None:
                store = non_digit_args[0].lower().lstrip("@").strip("<&>")
                if len(non_digit_args) > 1:
                    location = " ".join(non_digit_args[1:]).lower()

        # Resolve abbreviations
        if store and store in STORE_ABBREVIATIONS:
            store = STORE_ABBREVIATIONS[store]

    if store and store not in store_list:
        await ctx.send(f"❌ Unknown store. Valid stores: {', '.join(store_list)}")
        return

    stores_to_check = [store] if store else store_list
    await ctx.send(f"🔄 Analyzing restock patterns...")

    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    async with aiosqlite.connect(DB_PATH) as db:
        for s in stores_to_check:
            if location:
                cursor = await db.execute(
                    "SELECT timestamp, message_content, store, location FROM pings WHERE (store LIKE ? OR store = ?) AND (LOWER(location) LIKE ? OR LOWER(message_content) LIKE ?) AND channel_id NOT IN (?, ?) ORDER BY timestamp ASC",
                    (f"%{s}%", s, f"%{location}%", f"%{location}%", ANNOUNCEMENTS_CHANNEL_ID, GETROLES_CHANNEL_ID)
                )
            else:
                cursor = await db.execute(
                    "SELECT timestamp, message_content, store, location FROM pings WHERE store LIKE ? AND channel_id NOT IN (?, ?) ORDER BY timestamp ASC",
                    (f"%{s}%", ANNOUNCEMENTS_CHANNEL_ID, GETROLES_CHANNEL_ID)
                )
            rows = await cursor.fetchall()

            embed = discord.Embed(
                title=f"Predict — {s.title()}",
                color=discord.Color.blue()
            )
            if len(rows) == 0:
                embed.description = "No pings found."
                await ctx.send(embed=embed)
                continue

            # Group pings by location
            location_data = defaultdict(lambda: {
                "dates": set(), "day_counts": defaultdict(int),
                "hour_counts": defaultdict(int), "gaps": [], "pings": 0,
                "timestamps": []
            })

            for (ts, content, ping_store, stored_loc) in rows:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    from zoneinfo import ZoneInfo
                    dt = dt.astimezone(ZoneInfo("America/Chicago"))
                except (ValueError, TypeError):
                    continue
                loc = stored_loc.title() if stored_loc else "General"
                date_str = dt.strftime("%Y-%m-%d")
                ld = location_data[loc]
                ld["pings"] += 1
                ld["timestamps"].append(dt)
                if date_str not in ld["dates"]:
                    ld["dates"].add(date_str)
                    ld["day_counts"][dt.weekday()] += 1
                    ld["hour_counts"][dt.hour] += 1

            def build_location_prediction(loc_name, ld):
                loc_dates = sorted(ld["dates"])
                lines = []
                ping_count = ld["pings"]
                date_count = len(loc_dates)

                if date_count >= 2:
                    loc_gaps = []
                    for i in range(1, len(loc_dates)):
                        d1 = datetime.strptime(loc_dates[i-1], "%Y-%m-%d")
                        d2 = datetime.strptime(loc_dates[i], "%Y-%m-%d")
                        loc_gaps.append((d2 - d1).days)
                    avg_gap = sum(loc_gaps) / len(loc_gaps)
                    gap_std = (sum((g - avg_gap) ** 2 for g in loc_gaps) / len(loc_gaps)) ** 0.5 if len(loc_gaps) > 1 else avg_gap

                    if gap_std < 1.5:
                        confidence = "High"
                        conf_pct = min(95, 70 + int((1.5 - gap_std) * 15))
                    elif gap_std < 3:
                        confidence = "Medium"
                        conf_pct = min(70, 40 + int((3 - gap_std) * 10))
                    else:
                        confidence = "Low"
                        conf_pct = max(15, 40 - int(gap_std * 5))

                    last_dt = datetime.strptime(loc_dates[-1], "%Y-%m-%d")
                    next_dt = last_dt + timedelta(days=round(avg_gap))
                    days_until = (next_dt - datetime.now()).days

                    if days_until <= 0:
                        prediction = "⚡ **Possible restock NOW**"
                    elif days_until <= 2:
                        prediction = f"⏰ Likely in **{days_until} day(s)** ({next_dt.strftime('%A')})"
                    else:
                        prediction = f"📅 **{next_dt.strftime('%A, %b %d')}** (~{days_until}d)"

                    lines.append(f"Prediction: {prediction}")
                    lines.append(f"Avg cycle: **{avg_gap:.1f} days** (±{gap_std:.1f})")
                else:
                    avg_gap = 7
                    confidence = "Low"
                    conf_pct = 15
                    lines.append(f"Prediction: Need more data ({date_count} date(s))")

                if ld["day_counts"]:
                    top_day_idx = max(ld["day_counts"], key=ld["day_counts"].get)
                    top_day = DAY_NAMES[top_day_idx]
                    day_pct = round(ld["day_counts"][top_day_idx] / date_count * 100) if date_count else 0
                    lines.append(f"Best day: **{top_day}** ({day_pct}%)")

                if ld["hour_counts"]:
                    top_hour = max(ld["hour_counts"], key=ld["hour_counts"].get)
                    hour_pct = round(ld["hour_counts"][top_hour] / date_count * 100) if date_count else 0
                    hour_end = (top_hour + 3) % 24
                    lines.append(f"Best window: **{top_hour}:00-{hour_end}:00** ({hour_pct}%)")

                lines.append(f"Confidence: **{confidence}** ({conf_pct}%)")
                lines.append(f"Data: {ping_count} pings across {date_count} days")
                return "\n".join(lines)

            if location:
                # Show specific location prediction
                matched_locs = []
                for loc_name, ld in location_data.items():
                    if location in loc_name.lower():
                        matched_locs.append((loc_name, ld))

                if not matched_locs:
                    embed.description = f"No pings found for **{location}** at {s.title()}."
                    await ctx.send(embed=embed)
                    continue

                for loc_name, ld in matched_locs:
                    pred_text = build_location_prediction(loc_name, ld)
                    embed.add_field(name=f"📍 {loc_name}", value=pred_text, inline=False)

            else:
                # Show all locations
                embed.description = f"**{len(rows)}** total pings across **{len(location_data)}** locations"

                sorted_locs = sorted(location_data.items(), key=lambda x: x[1]["pings"], reverse=True)
                real_locs = [(n, ld) for n, ld in sorted_locs if n != "General" and len(n) <= 30]

                if real_locs:
                    for loc_name, ld in real_locs[:5]:
                        pred_text = build_location_prediction(loc_name, ld)
                        embed.add_field(name=f"📍 {loc_name}", value=pred_text, inline=False)
                    if len(real_locs) > 5:
                        remaining = len(real_locs) - 5
                        embed.set_footer(text=f"...and {remaining} more locations. Use !predict {s} <location> for details.")
                else:
                    embed.add_field(name="No locations found", value="Pings found but no location data extracted yet.", inline=False)

            await ctx.send(embed=embed)


@bot.command(name="restockhistory", aliases=["rh"])
@commands.has_role(ADMIN_ROLE_ID)
async def restockhistory_cmd(ctx, *args):
    """View recent ping history for a store to identify restock dates.
    Usage: !restockhistory (all stores)
    Usage: !restockhistory target
    Usage: !restockhistory target alliance (specific location)
    Usage: !restockhistory target 60 (last 60 days)"""
    store_list = CONFIG.get("store_channels", [])
    days = 30
    store = None
    location = None

    non_digit_args = [a for a in args if not a.isdigit()]
    digit_args = [a for a in args if a.isdigit()]

    if digit_args:
        days = int(digit_args[0])
    if non_digit_args:
        if ctx.message.role_mentions:
            store = ctx.message.role_mentions[0].name.lower()
            if len(non_digit_args) > 1:
                location = " ".join(non_digit_args[1:]).lower()
        else:
            joined = " ".join(a.lower().lstrip("@").strip("<&>") for a in non_digit_args)
            store = None
            location = None
            for i in range(len(non_digit_args), 0, -1):
                candidate = " ".join(a.lower().lstrip("@").strip("<&>") for a in non_digit_args[:i])
                if candidate in STORE_ABBREVIATIONS or candidate in store_list:
                    store = candidate
                    if i < len(non_digit_args):
                        location = " ".join(non_digit_args[i:]).lower()
                    break
            if store is None:
                store = non_digit_args[0].lower().lstrip("@").strip("<&>")
                if len(non_digit_args) > 1:
                    location = " ".join(non_digit_args[1:]).lower()

        if store and store in STORE_ABBREVIATIONS:
            store = STORE_ABBREVIATIONS[store]

    if store and store not in store_list:
        await ctx.send(f"❌ Unknown store. Valid stores: {', '.join(store_list)}")
        return

    cutoff = days_ago_iso(days)
    stores_to_check = [store] if store else store_list
    await ctx.send(f"🔄 Loading restock history...")
    found_any = False

    async with aiosqlite.connect(DB_PATH) as db:
        for s in stores_to_check:
            if location:
                cursor = await db.execute(
                    "SELECT timestamp, message_content, user_id, store, location, channel_id, message_id FROM pings WHERE (store LIKE ? OR store = ?) AND (LOWER(location) LIKE ? OR LOWER(message_content) LIKE ?) AND timestamp >= ? AND channel_id NOT IN (?, ?) ORDER BY timestamp ASC",
                    (f"%{s}%", s, f"%{location}%", f"%{location}%", cutoff, ANNOUNCEMENTS_CHANNEL_ID, GETROLES_CHANNEL_ID)
                )
                rows = await cursor.fetchall()
                if not rows:
                    cursor = await db.execute(
                        "SELECT timestamp, message_content, user_id, store, location, channel_id, message_id FROM pings WHERE store LIKE ? AND timestamp >= ? AND channel_id NOT IN (?, ?) ORDER BY timestamp ASC",
                        (f"%{s}%", cutoff, ANNOUNCEMENTS_CHANNEL_ID, GETROLES_CHANNEL_ID)
                    )
                    rows = await cursor.fetchall()
                    location_not_found = True
                else:
                    location_not_found = False
            else:
                cursor = await db.execute(
                    "SELECT timestamp, message_content, user_id, store, location, channel_id, message_id FROM pings WHERE store LIKE ? AND timestamp >= ? AND channel_id NOT IN (?, ?) ORDER BY timestamp ASC",
                    (f"%{s}%", cutoff, ANNOUNCEMENTS_CHANNEL_ID, GETROLES_CHANNEL_ID)
                )
                rows = await cursor.fetchall()
                location_not_found = False

            if not rows:
                continue

            found_any = True
            daily_data = {}
            guild_id = ctx.guild.id if ctx.guild else None
            for (ts, content, uid, ping_store, stored_loc, channel_id, message_id) in rows:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    # Convert to Central Time (CST/CDT)
                    from zoneinfo import ZoneInfo
                    dt = dt.astimezone(ZoneInfo("America/Chicago"))
                except (ValueError, TypeError):
                    continue
                date_key = dt.strftime("%Y-%m-%d (%a)")
                time_str = dt.strftime("%I:%M %p CT")
                if date_key not in daily_data:
                    daily_data[date_key] = []
                daily_data[date_key].append({
                    "time": time_str,
                    "content": content[:100] if content else None,
                    "user": uid,
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "guild_id": guild_id
                })

            sorted_dates = sorted(daily_data.items())

            embed = discord.Embed(
                title=f"Restock History — {s.title()} (last {days}d)",
                color=discord.Color.green()
            )

            history_text = ""
            for date_key, entries in sorted_dates[-15:]:
                times = [e["time"] for e in entries]
                time_range = f"{times[0]}" if len(times) == 1 else f"{times[0]} - {times[-1]}"
                history_text += f"**{date_key}** — {len(entries)} ping(s) @ {time_range}\n"

                for e in entries[-3:]:
                    if e["content"]:
                        short = e["content"][:80].replace("\n", " ")
                        if e.get("message_id") and e.get("channel_id") and e.get("guild_id"):
                            jump_url = f"https://discord.com/channels/{e['guild_id']}/{e['channel_id']}/{e['message_id']}"
                            history_text += f"└ `{e['time']}` <@{e['user']}>: {short} — [Jump]({jump_url})\n"
                        else:
                            history_text += f"└ `{e['time']}` <@{e['user']}>: {short}\n"

                if len(entries) > 3:
                    history_text += f"└ ...and {len(entries) - 3} more\n"
                history_text += "\n"

            if len(sorted_dates) > 15:
                history_text = f"*Showing last 15 of {len(sorted_dates)} dates*\n\n" + history_text

            embed.description = history_text
            if location_not_found and location:
                embed.set_footer(text=f"No pings found mentioning '{location}'. Try `!rh {s}` to see all {s} pings.")
            else:
                embed.set_footer(text=f"Total: {len(rows)} pings across {len(daily_data)} days")
            await ctx.send(embed=embed)

    if not found_any:
        await ctx.send(f"No pings found in the last {days} days.")


@bot.command(name="addlocation")
@commands.has_role(ADMIN_ROLE_ID)
async def addlocation_cmd(ctx, location_word: str = None):
    """Add a location word so vague mentions get tracked.
    Usage: !addlocation alliance
    When someone says 'alliance' in a store channel, it'll be tracked as that store."""
    if not location_word:
        await ctx.send("Usage: `!addlocation <location_word>`\nExample: `!addlocation alliance`")
        return

    if location_word.lower() not in LOCATION_WORDS:
        LOCATION_WORDS.append(location_word.lower())
        await ctx.send(f"✅ Added **{location_word}** as a location word. When mentioned in a store/hunting channel, it'll be tracked as a ping for that store.")
    else:
        await ctx.send(f"**{location_word}** is already a tracked location word.")


@bot.command(name="removelocation")
@commands.has_role(ADMIN_ROLE_ID)
async def removelocation_cmd(ctx, location_word: str = None):
    """Remove a location word.
    Usage: !removelocation alliance"""
    if not location_word:
        await ctx.send("Usage: `!removelocation <location_word>`")
        return

    if location_word.lower() in LOCATION_WORDS:
        LOCATION_WORDS.remove(location_word.lower())
        await ctx.send(f"✅ Removed **{location_word}** from tracked location words.")
    else:
        await ctx.send(f"**{location_word}** is not a tracked location word.")


@bot.command(name="listlocations")
@commands.has_role(ADMIN_ROLE_ID)
async def listlocations_cmd(ctx):
    """Show all tracked location words."""
    if not LOCATION_WORDS:
        await ctx.send("No location words configured.")
        return

    lines = [f"• {loc}" for loc in sorted(LOCATION_WORDS)]
    embed = discord.Embed(title="Tracked Location Words", description="\n".join(lines), color=discord.Color.blue())
    embed.set_footer(text="When these appear in store/hunting channels, they're tracked as pings for that channel's store.")
    await ctx.send(embed=embed)


@bot.command(name="fixlocations")
@commands.has_role(ADMIN_ROLE_ID)
async def fixlocations_cmd(ctx):
    """Re-extract location data for all existing pings without deleting anything."""
    await ctx.send("🔄 Fixing locations for existing pings...")
    updated = 0
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id, message_content FROM pings")
        rows = await cursor.fetchall()
        for (ping_id, content) in rows:
            new_loc = extract_location_from_text(content)
            await db.execute("UPDATE pings SET location = ? WHERE id = ?", (new_loc, ping_id))
            updated += 1
        await db.commit()
    await ctx.send(f"✅ Updated location data for **{updated}** pings.")


@bot.command(name="stopscan")
@commands.has_role(ADMIN_ROLE_ID)
async def stopscan_cmd(ctx):
    """Force-reset the scan lock if a previous scan got stuck.
    Usage: !stopscan"""
    global scan_in_progress
    scan_in_progress = False
    await ctx.send("✅ Scan lock reset. You can now run `!fixlinks` or `!backfill`.")


@bot.command(name="fixlinks")
@commands.has_role(ADMIN_ROLE_ID)
async def fixlinks_cmd(ctx, days: int = 14):
    """Add jump-link message IDs to existing pings that don't have them.
    Usage: !fixlinks
    Usage: !fixlinks 7  (only last 7 days)"""
    global scan_in_progress
    if scan_in_progress:
        await ctx.send("❌ A scan is already running. Use `!stopscan` if it's stuck.")
        return
    scan_in_progress = True

    await ctx.send(f"🔄 Adding jump links to pings from the last {days} days...")
    if days > 14:
        await ctx.send("💡 Tip: Use `!fixlinks <days>` to scan a smaller window if this hangs.")
    progress_msg = await ctx.send("📡 Starting...")
    updated = 0

    cutoff = days_ago_iso(days)

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, user_id, channel_id, timestamp, message_content FROM pings WHERE message_id IS NULL AND timestamp >= ? ORDER BY timestamp DESC",
                (cutoff,)
            )
            pings_to_fix = await cursor.fetchall()

        if not pings_to_fix:
            await ctx.send("✅ All pings already have jump links.")
            return

        await ctx.send(f"Found **{len(pings_to_fix)}** pings missing jump links. Scanning channels...")

        # Group pings by channel so we fetch each channel's history only once
        pings_by_channel = defaultdict(list)
        for ping in pings_to_fix:
            pings_by_channel[ping[2]].append(ping)

        channels_total = len(pings_by_channel)
        channels_done = 0

        for channel_id, channel_pings in pings_by_channel.items():
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                continue
            if channel.id in (ANNOUNCEMENTS_CHANNEL_ID, GETROLES_CHANNEL_ID):
                continue
            try:
                if not channel.permissions_for(ctx.guild.me).read_message_history:
                    continue
            except discord.Forbidden:
                continue

            # Sort pending pings by timestamp so we can walk history once
            channel_pings.sort(key=lambda p: p[3])
            pending = list(channel_pings)

            try:
                oldest_dt = datetime.fromisoformat(channel_pings[0][3].replace("Z", "+00:00"))
                newest_dt = datetime.fromisoformat(channel_pings[-1][3].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            try:
                async for msg in channel.history(limit=None, after=oldest_dt, before=newest_dt + timedelta(minutes=5)):
                    if msg.author.bot:
                        continue
                    msg_lower = msg.content.lower()
                    if '@location' not in msg_lower and '@oos' not in msg_lower:
                        continue

                    # Try to match this message against remaining pending pings
                    matched_ping = None
                    for ping in pending:
                        ping_id, user_id, _, timestamp, _ = ping
                        if msg.author.id != user_id:
                            continue
                        try:
                            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        except (ValueError, TypeError):
                            continue
                        ts_diff = abs((msg.created_at - dt).total_seconds())
                        if ts_diff < 300:
                            matched_ping = ping
                            break

                    if matched_ping:
                        ping_id = matched_ping[0]
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute(
                                "UPDATE pings SET message_id = ? WHERE id = ?",
                                (msg.id, ping_id)
                            )
                            await db.commit()
                        updated += 1
                        pending.remove(matched_ping)
                        if not pending:
                            break
            except Exception as e:
                print(f"fixlinks error in channel {channel_id}: {e}")
                continue

            channels_done += 1
            try:
                await progress_msg.edit(content=f"📡 Channels scanned: {channels_done}/{channels_total} | Updated: {updated}")
            except discord.Forbidden:
                pass

        await progress_msg.edit(content=f"✅ Jump links added! Updated {updated} of {len(pings_to_fix)} pings.")
    except Exception as e:
        await ctx.send(f"❌ Error during fixlinks: {e}")
        raise
    finally:
        scan_in_progress = False


@bot.command(name="backfill")
@commands.has_role(ADMIN_ROLE_ID)
async def backfill_cmd(ctx):
    """Backfill message content for old pings that don't have it.
    Scans Discord history and matches messages to existing ping records."""
    global scan_in_progress
    if scan_in_progress:
        await ctx.send("❌ A scan is already running. Wait for it to finish.")
        return
    scan_in_progress = True

    # Clean up pings from server-announcements
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, channel_id FROM pings"
        )
        all_pings = await cursor.fetchall()
        removed = 0
        for (pid, ch_id) in all_pings:
            ch = ctx.guild.get_channel(ch_id)
            if ch and ch.id == 1502087476305461349:
                await db.execute("DELETE FROM pings WHERE id = ?", (pid,))
                removed += 1
        await db.commit()
    if removed > 0:
        await ctx.send(f"🗑️ Removed {removed} pings from server-announcements.")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM pings WHERE channel_id IN (?, ?)", (ANNOUNCEMENTS_CHANNEL_ID, GETROLES_CHANNEL_ID))
        await db.commit()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id, message_content FROM pings WHERE message_content IS NOT NULL AND message_content != ''")
        all_pings = await cursor.fetchall()
        cleared = 0
        for (pid, content) in all_pings:
            if content and '@location' not in content.lower() and '@oos' not in content.lower():
                await db.execute("DELETE FROM pings WHERE id = ?", (pid,))
                cleared += 1
        await db.commit()
    if cleared > 0:
        await ctx.send(f"🗑️ Deleted {cleared} pings with invalid content.")

    await ctx.send("🔄 Backfilling message content for old pings...")
    progress_msg = await ctx.send("📡 Starting...")
    updated = 0
    scanned = 0

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, user_id, channel_id, store, timestamp FROM pings WHERE message_content IS NULL OR message_content = '' OR message_content = 'None' OR message_id IS NULL"
        )
        pings_to_fix = await cursor.fetchall()

    if not pings_to_fix:
        await ctx.send("✅ All pings already have message content and jump links.")
        scan_in_progress = False
        return

    await ctx.send(f"Found **{len(pings_to_fix)}** pings missing content or jump links. Scanning channels...")

    channel_cache = {}
    for ping_id, user_id, channel_id, store, timestamp in pings_to_fix:
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        if channel_id not in channel_cache:
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                continue
            # Skip excluded channels
            if channel.id in (ANNOUNCEMENTS_CHANNEL_ID, GETROLES_CHANNEL_ID):
                continue
            try:
                if not channel.permissions_for(ctx.guild.me).read_message_history:
                    continue
            except discord.Forbidden:
                continue
            channel_cache[channel_id] = channel

        channel = channel_cache[channel_id]
        scanned += 1

        if scanned % 50 == 0:
            try:
                await progress_msg.edit(content=f"📡 Scanned {scanned}/{len(pings_to_fix)} | Updated: {updated}")
            except discord.Forbidden:
                pass

        try:
            async for msg in channel.history(limit=50, around=dt):
                if msg.author.id == user_id and not msg.author.bot:
                    content_lower = msg.content.lower()
                    if '@location' not in content_lower and '@oos' not in content_lower:
                        continue
                    ts_diff = abs((msg.created_at - dt).total_seconds())
                    if ts_diff < 120:
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute(
                                "UPDATE pings SET message_content = ?, message_id = ? WHERE id = ?",
                                (msg.content[:500], msg.id, ping_id)
                            )
                            await db.commit()
                        updated += 1
                        break
        except (discord.Forbidden, Exception):
            continue

    await progress_msg.edit(content=f"✅ Backfill complete! Updated {updated} of {len(pings_to_fix)} pings.")
    scan_in_progress = False


@bot.command(name="deepbackfill")
@commands.has_role(ADMIN_ROLE_ID)
async def deepbackfill_cmd(ctx, days: int = 7):
    """Scan store channels for past messages and create ping records.
    Usage: !deepbackfill (7 days default)
    Usage: !deepbackfill 14 (last 14 days)"""
    global scan_in_progress
    if scan_in_progress:
        await ctx.send("❌ A scan is already running. Wait for it to finish.")
        return
    scan_in_progress = True

    store_list = CONFIG.get("store_channels", [])
    scan_channels = [s for s in store_list]  # walmart, target, etc.

    # Dynamically find all channels under Ft Worth Area Hunts and Dallas Area Hunts categories
    location_categories = ["ft worth area hunts", "dallas area hunts", "others", "store general info"]
    for cat_name in location_categories:
        category = discord.utils.get(ctx.guild.categories, name__iexact=cat_name)
        if category:
            for ch in category.text_channels:
                if ch.name not in scan_channels:
                    scan_channels.append(ch.name)

    # Always include these hunting/general channels
    for ch_name in ["open-hunting", "general-chat"]:
        if ch_name not in scan_channels:
            scan_channels.append(ch_name)

    cutoff = datetime.utcnow() - timedelta(days=days)
    total_added = 0
    total_skipped = 0
    progress_msg = await ctx.send(f"📡 Deep backfilling last {days} days across {len(scan_channels)} channels...")

    async with aiosqlite.connect(DB_PATH) as db:
        for channel_name in scan_channels:
            channel = discord.utils.get(ctx.guild.text_channels, name=channel_name)
            if not channel:
                continue
            try:
                if not channel.permissions_for(ctx.guild.me).read_message_history:
                    continue
            except discord.Forbidden:
                continue

            added = 0
            skipped = 0
            seen_messages = set()
            is_store_or_hunting = channel_name in store_list or channel_name in ["open-hunting"] or channel.category and channel.category.name.lower() in location_categories
            async for message in channel.history(limit=2000, after=cutoff):
                if message.author.bot:
                    continue

                content_lower = message.content.lower()

                # Check actual Discord role mentions (like real-time handler does)
                role_names = [r.name.lower() for r in message.role_mentions]
                has_ping = "location" in role_names or "oos" in role_names

                # Also check text-based fallback for users who can't ping the role
                if not has_ping:
                    has_ping = "@location" in content_lower or "@oos" in content_lower

                msg_key = f"{message.author.id}:{message.channel.id}:{message.content[:200]}"
                if msg_key in seen_messages:
                    continue
                seen_messages.add(msg_key)

                matched_stores = []

                if has_ping:
                    for store in store_list:
                        if store in content_lower or store.replace("-", " ") in content_lower:
                            matched_stores.append(store)
                    for abbr, store_channel in STORE_ABBREVIATIONS.items():
                        if abbr in content_lower.split() and store_channel not in matched_stores:
                            matched_stores.append(store_channel)
                    if not matched_stores and channel_name in store_list:
                        matched_stores.append(channel_name)

                if not matched_stores and is_store_or_hunting:
                    words = content_lower.split()
                    for loc_word in LOCATION_WORDS:
                        if loc_word in words:
                            if channel_name in store_list:
                                matched_stores.append(channel_name)
                            break
                    if not matched_stores:
                        for store in store_list:
                            if store in content_lower or store.replace("-", " ") in content_lower:
                                matched_stores.append(store)

                if not matched_stores:
                    continue

                mention_type = "location" if has_ping else "location"

                cursor = await db.execute(
                    "SELECT id FROM pings WHERE user_id = ? AND channel_id = ? AND timestamp >= ?",
                    (message.author.id, message.channel.id, cutoff.isoformat())
                )
                existing = await cursor.fetchall()
                existing_times = set()
                for (eid,) in existing:
                    pass

                msg_time = message.created_at
                skip = False
                for (eid,) in existing:
                    cursor2 = await db.execute("SELECT timestamp, message_content FROM pings WHERE id = ?", (eid,))
                    row = await cursor2.fetchone()
                    if row:
                        try:
                            existing_dt = datetime.fromisoformat(row[0].replace("Z", "+00:00")).replace(tzinfo=None)
                            existing_content = (row[1] or "")[:200]
                            if abs((msg_time - existing_dt).total_seconds()) < 60 and existing_content == message.content[:200]:
                                skip = True
                                break
                        except (ValueError, TypeError):
                            pass

                if skip:
                    skipped += 1
                    continue

                mention_type = "location" if "location" in role_names else "oos"

                # Extract location from message
                loc = extract_location_from_text(message.content)

                for store in matched_stores:
                    await db.execute(
                        "INSERT INTO pings (user_id, channel_id, store, mention_type, timestamp, message_content, location, message_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (message.author.id, message.channel.id, store, mention_type, message.created_at.isoformat(), message.content[:500], loc, message.id)
                    )
                    added += 1

            total_added += added
            total_skipped += skipped
            if added > 0:
                try:
                    await progress_msg.edit(content=f"📡 Scanned #{channel_name}: +{added} pings | Total: {total_added}")
                except discord.Forbidden:
                    pass

        await db.commit()

    await progress_msg.edit(content=f"✅ Deep backfill complete! Added **{total_added}** pings across {len(scan_channels)} channels ({total_skipped} skipped as duplicates).")
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
