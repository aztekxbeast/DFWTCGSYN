# PokeHunt Discord Bot

A Discord bot for managing store-based Pokemon TCG stock alerts and activity-based role access.

## What This Bot Does

**Core purpose:** Track user pings (role mentions) for in-store stock and OOS alerts, then automatically grant/revoke the Pokemon Hunter role based on activity.

### Features

- **Ping Tracker** — Counts `@location` and `@OOS` mentions per user per store
- **Media Tracker** — Counts attachment posts in #pulls / #success channels
- **Chat Tracker** — Counts messages in chat channels
- **Activity-Based Access** — Auto-grants/revokes Pokemon Hunter role based on thresholds
- **MEE6 Sync** — Grants Hunter role head-start to MEE6 Silver+ members on join
- **Admin Commands** — Whitelist, threshold tuning, reset, and more (no code edits needed)

---

## Bot Commands

### User Commands

| Command | Description |
|---------|-------------|
| `!pings` | Your ping count for the past 14 days |
| `!pings @username` | Another user's ping count (past 14 days) |
| `!pingtotal` | Your total lifetime pings |
| `!pingtotal @username` | Another user's total lifetime pings |
| `!pingleaderboard` | Top ping contributors (all time) |
| `!mylevel` | Your current role + activity status |

### Admin Commands

| Command | Description |
|---------|-------------|
| `!whitelist add @user` | Grant permanent Hunter access |
| `!whitelist remove @user` | Remove from whitelist |
| `!resetpings @user` | Clear a user's ping history |
| `!resetallpings` | Clear ALL ping history (dangerous) |
| `!set <key> <value>` | Change a threshold setting |
| `!settings` | Show current settings |
| `!sync` | Run access check manually (grant/revoke) |
| `!mee6sync` | Sync MEE6 Silver+ roles now |

---

## Access Rules

### Gaining Pokemon Hunter Role
- **10 lifetime pings** (`@location` or `@OOS` mentions) to unlock

### Maintaining Pokemon Hunter Role (checked every 24h)
One of these must be true within the last 10 days:
- **4+ pings** (in-store stock or OOS alerts), OR
- **4+ media posts** (photos in #pulls / #success), OR
- **30+ chat messages** (in tracked channels), OR
- **Whitelisted** by an admin

### MEE6 Head Start
- Members joining with MEE6 **Silver role or higher** are auto-granted Hunter immediately

---

## Server Channel Structure

### Pokemon Trainer Role (default on join)
Access to:
- `#server-announcements`
- `#general-announcements`
- `#open-hunting` (new members post pings here to earn access)
- `#general-chat`

### Pokemon Hunter Role (unlocked after earning access)
Access to:
- All store channels (`#walmart`, `#target`, `#barnes-noble`, etc.)
- `#pulls` / `#success`
- All announcement and general channels

### How Pings Work
When posting in store channels:
- **In stock:** Mention `@location` role + store name + details
- **Out of stock:** Mention `@OOS` role + store name

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
- **Database:** SQLite (no server needed)
- **Hosting:** Oracle Cloud Always Free / Vultr $3.50/mo / DigitalOcean $4/mo

---

## Setup

### Prerequisites
- Python 3.10 or higher
- A Discord bot token ([discord.com/developers](https://discord.com/developers))
- Bot invited with permissions: `Manage Roles`, `Read Message History`, `Send Messages`, `View Channels`, `Mention Everyone`

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
Edit `config.json` to set your thresholds and channel IDs:
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

---

## File Structure

```
RepoHUB/
  bot.py              # Main bot code
  config.json         # Tunable settings (edit this, not the code)
  .env.example        # Environment variable template
  .env                # Your secrets (DO NOT commit)
  requirements.txt    # Python dependencies
  data/               # SQLite database (auto-created)
  README.md           # This file
```

---

## Database Schema

The bot stores everything in `data/pokehunt.db` (SQLite, auto-created):

- **pings** — `(user_id, channel, store, mention_type, timestamp)`
- **media** — `(user_id, channel, timestamp)`
- **chat** — `(user_id, channel, timestamp)`
- **whitelist** — `(user_id, added_by, timestamp)`
- **settings** — `(key, value)` — mirrors config.json

---

## Roadmap

- [x] Core ping tracker
- [x] Media tracker
- [x] Chat tracker
- [x] Activity-based role access
- [x] MEE6 Silver+ sync
- [x] Admin commands
- [ ] Web admin dashboard (Phase 2)
- [ ] Store-specific ping filtering
- [ ] Ping history export

---

## Credits

Built for the Pokemon TCG hunting community.
