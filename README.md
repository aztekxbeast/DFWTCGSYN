# PokeHunt Discord Bot

A single Python bot that tracks ping activity, media posts, and chat messages to automatically manage the **Pokemon Hunter** role in your Discord server. Deployed on Fly.io.

---

## What This Bot Does

- Counts `@location` / `@OOS` role mentions per user (ping tracker)
- Counts attachment posts in #pulls / #success (media tracker)
- Counts chat messages (chat tracker)
- Auto-grants Pokemon Hunter role at 10 total pings
- Daily maintenance checks keep Hunters active
- Grants Hunter head-start to MEE6 Silver+ members on join
- Restock prediction engine with location-based pattern analysis
- Deep backfill to scan historical messages for past pings
- All admin settings adjustable via `!set` commands (no code edits)

---

## Channel Tracking

### Store Channels (Ping Tracking)
Ping tracking is active in all store channels — when someone mentions `@location` or `@OOS` (or types `@location` / `@OOS` as text) with a store name, it records a ping.

#### 📁 Category: General Store Info
| Channel | What Triggers a Ping |
|---------|---------------------|
| **#academy** | `@location academy` or `@oos academy` |
| **#aldi** | `@location aldi` or `@oos aldi` |
| **#amazon** | `@location amazon` or `@oos amazon` |
| **#barnes-and-noble** | `@location barnes and noble` or abbreviations `bn`, `b&n` |
| **#best-buy** | `@location best buy` or abbreviation `bb` |
| **#dollar-tree-dollar-general-family-dollar** | `@location` + store name or abbreviations `dg`, `dt`, `fd` |
| **#gamestop** | `@location gamestop` or abbreviation `gs` |
| **#kroger** | `@location kroger` or abbreviation `km` |
| **#micro-center** | `@location micro center` or abbreviation `mc` |
| **#mitsuwa** | `@location mitsuwa` |
| **#others** | `@location` + any store name |
| **#other-pokémon** | `@location` + any store name |
| **#pokemon-center** | `@location pokemon center` or abbreviations `pc`, `pk` |
| **#sam's-costco** | `@location sam's` or abbreviations `sam`, `sams`, `costco` |
| **#scheels** | `@location scheels` |
| **#target** | `@location target` |
| **#walgreens-cvs** | `@location walgreens` or abbreviations `wc`, `wag` |
| **#walmart** | `@location walmart` |

### Location Words
Vague location mentions (e.g. "alliance", "glade", "watauga", "beach") in store channels are tracked as pings for that store. Use `!addlocation` to add more.

### Other Tracked Channels

| Channel | Ping Tracking | Media Tracking | Chat Tracking |
|---------|---------------|----------------|---------------|
| **#server-announcements** | ❌ NOT tracked | ❌ | ❌ |
| **#get-roles** | ❌ NOT tracked | ❌ | ❌ |
| **#general-announcements** | ✅ Tracked | ❌ | ✅ |
| **#open-hunting** | ✅ Tracked | ❌ | ✅ |
| **#training-hunting** | ✅ Tracked | ❌ | ✅ |
| **#general-chat** | ✅ Tracked | ❌ | ✅ |
| **#ft-worth-area-hunts** | ✅ Tracked | ❌ | ✅ |
| **#dallas-area-hunts** | ✅ Tracked | ❌ | ✅ |
| **#pulls** | ✅ Tracked | ✅ | ✅ |
| **#success** | ✅ Tracked | ✅ | ✅ |

---

## Access Rules

### Gaining Pokemon Hunter Role
- **10 total pings** (`@location` or `@OOS` mentions) to unlock
- Once you hit 10, you get the role automatically
- Announcement posted in #server-announcements when granted

### Maintaining Pokemon Hunter Role (checked daily)
One of these must be true within the window:
- **4+ pings** within 10 days, OR
- **4+ media posts** within 10 days, OR
- **30+ chat messages** within 7 days, OR
- **Whitelisted** by an admin (bypasses all checks)

### MEE6 Head Start
- Members joining with MEE6 **Silver role or higher** are auto-granted Hunter immediately

---

## Commands

### User Commands

| Command | Description |
|---------|-------------|
| `!pings` | Your ping count (last 10 days) |
| `!pings @user` | Check someone else's pings |
| `!pingtotal` | Your total lifetime pings |
| `!pingtotal @user` | Someone else's total pings |
| `!pingleaderboard` | Top ping contributors |
| `!mylevel` | Full activity breakdown + progress to Hunter |
| `!helpme` | Show all commands |

### Admin Commands

| Command | Description |
|---------|-------------|
| `!whitelist add @user` | Grant permanent Hunter access |
| `!whitelist remove @user` | Remove from whitelist |
| `!resetpings @user` | Clear a user's ping history |
| `!resetallpings` | Clear ALL ping history (requires `!confirm`) |
| `!stats @user` | Detailed stats for a user |
| `!allstats` | Server-wide activity overview |
| `!sync` | Run manual access check |
| `!set <key> <value>` | Change a setting |
| `!settings` | Show current settings |
| `!mee6sync` | Sync MEE6 Silver+ roles now |
| `!mee6import` | Import MEE6 level data via API |
| `!mee6scan` | Scan messages for MEE6 level-up history |
| `!messagescan` | Scan message history for access grants |

### Restock & Location Commands

| Command | Description |
|---------|-------------|
| `!predict <store>` | Predict next restock with per-location breakdown |
| `!predict <store> <location>` | Predict for specific location (e.g. `!predict target alliance`) |
| `!rh <store>` | Recent restock dates (alias for `!restockhistory`) |
| `!rh <store> <location>` | Filter by location (e.g. `!rh walmart beach`) |
| `!addlocation <word>` | Add a location word (e.g. `!addlocation renaissance`) |
| `!removelocation <word>` | Remove a location word |
| `!listlocations` | Show all tracked location words |
| `!fixlocations` | Re-extract location data for existing pings in DB |
| `!deepbackfill` | Scan channels for past pings (7 days) |
| `!deepbackfill 14` | Scan last 14 days |
| `!backfill` | Backfill message content for old pings |

---

## Bot Settings

All settings stored in `config.json` and adjustable at runtime via `!set`:

```json
{
  "pings_to_gain": 10,
  "pings_to_maintain": 4,
  "maintenance_window_days": 10,
  "media_to_maintain": 4,
  "media_channels": ["pulls", "success"],
  "chat_to_maintain": 30,
  "chat_window_days": 7,
  "chat_channels": ["general-chat", "open-hunting", "general"],
  "store_channels": ["academy", "aldi", "amazon", "barnes-and-noble", "best-buy", "dollar-tree-dollar-general-family-dollar", "gamestop", "kroger", "micro-center", "mitsuwa", "others", "other-pokémon", "pokemon-center", "sam's-costco", "scheels", "target", "walgreens-cvs", "walmart"],
  "training_channel": "open-hunting",
  "mee6_level_threshold": 10,
  "messages_to_gain": 50,
  "mee6_silver_role_name": "Silver",
  "pokemon_trainer_role_name": "Pokemon Trainer",
  "pokemon_hunter_role_name": "Pokemon Hunter",
  "admin_role_name": "Admin",
  "mod_role_name": "Moderator",
  "ping_leaderboard_size": 15,
  "daily_maintenance_hour": 3,
  "daily_maintenance_minute": 0
}
```

---

## Tech Stack

- **Language:** Python 3.14
- **Library:** discord.py 2.x
- **Database:** SQLite (auto-created, stored on Fly.io volume)
- **Hosting:** Fly.io (auto-deployed from GitHub)

---

## Setup

### Prerequisites
- Python 3.10+ (for local testing)
- Discord bot token (from Discord Developer Portal)
- Bot invited with: `Manage Roles`, `Read Message History`, `Send Messages`, `View Channels`, `Mention Everyone`

### 1. Clone & Install
```bash
git clone https://github.com/aztekxbeast/RepoHUB.git
cd RepoHUB
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env with your bot token, guild ID, role IDs, channel IDs
```

### 3. Run Locally
```bash
python bot.py
```

### 4. Deploy to Fly.io
```bash
# Install flyctl: https://fly.io/docs/hands-on/install-flyctl/
flyctl auth login
flyctl launch    # First time only
flyctl deploy    # Deploy after changes
flyctl restart   # If bot is stuck
```

Bot data persists on a Fly.io volume mounted at `/app/data`.

---

## File Structure

```
RepoHUB/
  bot.py              # Main bot code (single file)
  config.json         # Tunable settings
  .env.example        # Environment variable template
  .env                # Your secrets (DO NOT commit)
  requirements.txt    # Python dependencies
  Dockerfile          # Docker config for Fly.io
  fly.toml            # Fly.io deployment config
  data/               # SQLite database (on Fly.io volume)
  README.md           # This file
```

---

## Database Schema

Everything stored in `data/pokehunt.db` (SQLite):

- **pings** — `(id, user_id, channel_id, store, mention_type, timestamp, message_content, location)`
- **media** — `(id, user_id, channel_id, timestamp)`
- **chat** — `(id, user_id, channel_id, timestamp)`
- **whitelist** — `(user_id, added_by, timestamp)`
- **settings** — `(key, value)` — mirrors config.json
- **location_aliases** — `(alias, store, added_by, timestamp)`
- **hunter_role_earned** — `(user_id, earned_at)` — tracks when user earned Hunter access

---

## Required Bots

| Bot | Purpose | Cost |
|-----|---------|------|
| **PokeHunt** (this bot) | Ping tracking + role access + restock predictions | Free (self-hosted) |
| **MEE6** | Chat XP + Silver role rewards | Free tier |
| **TicketTool** | Support tickets | Free |
| **Discord Onboarding** | Role questionnaire | Free (built-in) |

---

## Roadmap

- [x] Core ping tracker
- [x] Media tracker
- [x] Chat tracker
- [x] Activity-based role access
- [x] MEE6 Silver+ sync
- [x] Admin commands (no code edits needed)
- [x] Deploy to Fly.io (24/7 hosting)
- [x] Restock prediction engine
- [x] Deep backfill for historical pings
- [x] Location tracking and filtering
- [ ] Per-location prediction confidence windows
- [ ] Web admin dashboard (Phase 2 — only if needed)

---

## Credits

Built for the Pokemon TCG hunting community.
