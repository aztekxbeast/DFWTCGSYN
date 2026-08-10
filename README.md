# PokeHunt Discord Bot

**Implementation:** Option A — Everything in one custom bot, zero subscriptions (~$0/month)

A single Python bot that handles ping tracking, media tracking, chat activity tracking, and automatic role management. No web dashboard, no domain, no paid services.

---

## What This Bot Does

One bot does everything:
- Counts `@location` / `@OOS` role mentions per user (ping tracker)
- Counts attachment posts in #pulls / #success (media tracker)
- Counts chat messages (chat tracker)
- Auto-grants Pokemon Hunter role at 10 total pings
- Auto-revokes Hunter role if activity drops below thresholds
- Grants Hunter head-start to MEE6 Silver+ members on join
- All admin settings adjustable via slash commands (no code edits)

---

## Option A Step-by-Step

### Step 1: Create the Discord Application
- Go to discord.com/developers → New Application → Bot
- Copy the bot token (paste into `.env`)
- Invite bot to server with permissions: `Manage Roles`, `Read Message History`, `Send Messages`, `View Channels`, `Mention Everyone`

### Step 2: Build the Bot (done — see `bot.py`)
- **Logger:** `on_message` → if message mentions `@location` or `@OOS` in a store channel → log ping. If attachment in #pulls → log media. If in chat channel → log chat.
- **Role access engine:** Daily cron checks all members. Grant Hunter at 10 pings. Revoke if <4 pings, <4 media posts, <30 chats in their windows. Whitelist bypasses everything.
- **Commands:** `!pings`, `!pingtotal`, `!pingleaderboard`, `!whitelist add/remove`, `!set`, `!settings`, `!sync`, `!mee6sync`
- **MEE6 sync:** On member join, if they have MEE6 Silver role → auto-grant Hunter.

### Step 3: Channel Structure (Discord settings, no code)
- **Pokemon Trainer role (default on join):** #server-announcements, #general-announcements, #open-hunting, #training-hunting, #general-chat
- **Pokemon Hunter role (unlocks after earning):** #walmart, #target, #barnes-noble, #pulls, all store channels
- Store channels require @location + store name, or @OOS — mods enforce, bot counts

### Step 4: Ticketing — skip building it
- Add **TicketTool** (free) → `/setup` → pick a support category
- Don't fix what ain't broken

### Step 5: Questionnaire — use Discord's built-in
- Server Settings → Onboarding → buttons for Area / TCG / Pokefam
- Zero code, zero cost

### Step 6: Free 24/7 Hosting
- **Oracle Cloud Always Free** — ARM, 4 cores, 24GB RAM, permanently free
- Sign up: oracle.com/cloud/free
- Deploy with `systemd` + auto-restart
- If Oracle rejects signup → **Vultr $3.50/mo** fallback

### Step 7: Skip domain and web dashboard for v1
- All admin settings via `!set` slash commands in a hidden #admin channel
- Add website later only if you outgrow it

---

## Bot Commands

### User Commands

| Command | Description |
|---------|-------------|
| `!pings` | Your ping count for the past 14 days |
| `!pings @username` | Another user's ping count (past 14 days) |
| `!pingtotal` | Your total pings (all time) |
| `!pingtotal @username` | Another user's total pings (all time) |
| `!pingleaderboard` | Top ping contributors (all time) |
| `!mylevel` | Your current role + activity status |

### Admin Commands

| Command | Description |
|---------|-------------|
| `!whitelist add @user` | Grant permanent Hunter access |
| `!whitelist remove @user` | Remove from whitelist |
| `!resetpings @user` | Clear a user's ping history |
| `!resetallpings` | Clear ALL ping history (dangerous) |
| `!set <key> <value>` | Change a threshold setting (no code edit needed) |
| `!settings` | Show current settings |
| `!sync` | Run access check manually (grant/revoke) |
| `!mee6sync` | Sync MEE6 Silver+ roles now |

---

## Access Rules

### Gaining Pokemon Hunter Role
- **10 total pings** (`@location` or `@OOS` mentions) to unlock
- Once you hit 10, you get the role. You can lose it if inactive, then re-earn it.

### Maintaining Pokemon Hunter Role (checked every 24h)
One of these must be true within the last 10 days:
- **4+ pings** (in-store stock or OOS alerts), OR
- **4+ media posts** (photos in #pulls / #success), OR
- **30+ chat messages** (in tracked channels), OR
- **Whitelisted** by an admin

### MEE6 Head Start
- Members joining with MEE6 **Silver role or higher** are auto-granted Hunter immediately

---

## Required Free Bots

| Bot | Purpose | Cost |
|-----|---------|------|
| **PokeHunt** (this bot) | Ping tracking + role access | Free (self-hosted) |
| **MEE6** | Chat XP + Silver role rewards | Free tier |
| **TicketTool** | Support tickets | Free |
| **Discord Onboarding** | Role questionnaire | Free (built-in) |

---

## Tech Stack

- **Language:** Python 3.10+
- **Library:** discord.py 2.x
- **Database:** SQLite (no server needed — one file, `data/pokehunt.db`)
- **Hosting:** Oracle Cloud Always Free (or Vultr $3.50/mo)

---

## Setup

### Prerequisites
- Python 3.10+ (https://www.python.org/downloads/)
- Your Discord bot token (from Discord Developer Portal — already set up)
- Bot invited to server with: `Manage Roles`, `Read Message History`, `Send Messages`, `View Channels`, `Mention Everyone`

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

### 3. Configure Settings
Edit `config.json` to set your thresholds:
```json
{
  "pings_to_gain": 10,
  "pings_to_maintain": 4,
  "maintenance_window_days": 10,
  "media_to_maintain": 4,
  "chat_to_maintain": 30,
  "chat_window_days": 7
}
```

### 4. Run
```bash
python bot.py
```
Bot stays online while terminal is running. For 24/7, deploy to Oracle Cloud.

---

## File Structure

```
RepoHUB/
  bot.py              # Main bot code (single file)
  config.json         # Tunable settings — edit this, not the code
  .env.example        # Environment variable template
  .env                # Your secrets (DO NOT commit)
  requirements.txt    # Python dependencies
  data/               # SQLite database (auto-created)
  README.md           # This file
```

---

## Database Schema

Everything stored in `data/pokehunt.db` (SQLite, auto-created):

- **pings** — `(user_id, channel, store, mention_type, timestamp)`
- **media** — `(user_id, channel, timestamp)`
- **chat** — `(user_id, channel, timestamp)`
- **whitelist** — `(user_id, added_by, timestamp)`
- **settings** — `(key, value)` — mirrors config.json

---

## Year 1 Cost

- **Bot hosting:** $0 (Oracle Cloud Always Free)
- **Domain:** $0 (skip for v1)
- **MEE6:** $0 (free tier)
- **TicketTool:** $0 (free)
- **Total: $0/year**

If Oracle Cloud doesn't work out: Vultr $3.50/mo = $42/year.

---

## Roadmap

- [x] Core ping tracker
- [x] Media tracker
- [x] Chat tracker
- [x] Activity-based role access
- [x] MEE6 Silver+ sync
- [x] Admin commands (no code edits needed)
- [ ] Deploy to Oracle Cloud (24/7 hosting)
- [ ] Web admin dashboard (Phase 2 — only if needed)

---

## Credits

Built for the Pokemon TCG hunting community.
Option A implementation — zero subscriptions, full automation.
