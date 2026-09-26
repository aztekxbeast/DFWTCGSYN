# Changelog — PokeHunt ping rules & staff tools

**Date:** 2026-09-26  
**Scope:** Counting rules going forward + staff tooling. **No Hunter roles were changed.**

---

## What changed

### Ping counting (going forward)

Pings only count toward **Pokemon Hunter** when they match the server rules from the general announcements.

| ✅ Counts | ❌ Does not count |
|---|---|
| Real **store role** ping + place/stock (`@Target` Watauga …) | Typed `@walmart` **without** selecting the role |
| `@Other` + store name + details | `@location` / `@oos` with no store |
| Store role + short place name (`@Target` NRH) | Bare `Target` / `Costco` / `pc` / `bb` in chat |
| | Questions (“Target?”, “Anyone at BB?”) |
| | Product link spam only |
| | Same message counted twice (backfill) |
| | Trainer post in `#open-hunting` **without a photo** |

**Thresholds (unchanged):** 10 counted pings to **gain** Hunter · 4 in 10 days (or media/chat rules) to **keep** it.

### Examples that COUNT

```
@Target Dallas pkwy has PB etc
```

```
@Walmart Watauga <@&OOS>
```

```
@Other  — Costco Overton has the 5-pack tins
```

```
@Target NRH
```
*(store role + place name is OK)*

Trainer in `#open-hunting` (must include photo):
```
@Target Carroll (photo attached)
```

### Examples that DO NOT count

```
Anyone at target?
Is Best Buy getting the ascended tins?
Target
Costco
@walmart          ← typed text, not the role
```

```
https://www.target.com/p/pokemon-...
```
*(link only)*

---

## New DB / audit fields

| Where | What |
|---|---|
| `pings.counts_for_grant` | 1 if it meets official rules |
| `pings.reject_reason` | why it failed (`question`, `no_store_role`, `no_photo`, …) |
| `pings.added_by` | who ran `!addping` |
| `pings.has_photo` / `channel_name` / `message_id` | evidence + dedupe |
| `hunter_role_earned.grant_reason` | why the role was given |
| `role_grant_log` | every grant/revoke + reason + actor + ping count |
| `admin_actions` | staff commands and denied attempts |

---

## New / updated commands

### `!pingreport @user` (Admin · Mod · **Professor Oak**)

Aliases: `!pingrep`, `!phistory`

Shows that member’s full ping picture:

- Hunter / whitelist / when they earned it  
- Raw rows vs **official counted** total  
- Score breakdown (pass vs rejected)  
- Last N pings with ✅/❌, 📷 photo, jump links  
- Grant/revoke log and `!addping` history  

**Examples**
```
!pingreport @SomeUser
!pingreport 123456789012345678
!pingreport @SomeUser 20
```

Every lookup is logged in `admin_actions` (who checked whom).

> **Configured on Fly:** `PROFESSOR_OAK_ROLE_ID=1539123032847687730` (Professor Oak) and `AZTEK_USER_ID=638486065430265877`. Also listed in `.env.example`.

### `!syncdry` (Admin · Mod)

Aliases: `!drysync`, `!syncpreview`, `!syncdryrun`

**Preview only — does not change any roles.**

Prints:
- 🔺 Would **grant** Hunter  
- 🔻 Would **revoke** Hunter  
- 👀 Watch / near threshold  
- ✅ Keep (including whitelist)

**Example**
```
!syncdry
```

### `!addping @user <count>` (Admin only)

Still staff-only. Each insert now records **who** ran it (`pings.added_by` + `admin_actions`).

**Staff example**
```
!addping @Member 5
```
Bot reply includes who issued it (e.g. `Added 5 ping(s) to @Member (by @Mod). Counted total: 12.`).

#### If someone is NOT Admin or Mod

They **cannot** add pings. The bot will:

1. **Not** insert any pings  
2. **Reply** to their command message (so the attempt is stuck in the thread)  
3. Tag **the person who tried it** and **`@aztekbeast`** in that same reply  
4. Write the attempt to `admin_actions` (`denied:addping`, their ID, the command text)

**Example — member runs `!addping @Friend 10`:**

> 🚫 @RandomUser tried `!addping` without Admin/Mod. @aztekbeast — unauthorized access attempt.

Same treatment for `!whitelist`, `!resetpings`, `!resetallpings`, `!restorehunters`, `!set` / `!settings`, and `!pingreport` (unless Professor Oak).

#### Review staff abuse later

```
!pingreport @SomeoneWhoGotExtraPings
```
Shows `Manual !addping` count, `added_by` history, and grant/revoke log.

### Other admin commands (unchanged behavior, more logging)

`!whitelist`, `!resetpings`, `!restorehunters`, `!sync`, `!stats` — denied attempts also ping `@aztekbeast`.

---

## How members earn Hunter (summary)

1. Post a **real store ping** (see examples above) in a store or area channel.  
2. Trainers: include a **photo** in `#open-hunting`.  
3. Hit **10 counted** pings → role is granted automatically.  
4. Keep it with **4 counted pings in 10 days** (or the media/chat maintain rules).  
5. Check progress: `!pings` / `!mylevel` / `!helpme`  
6. Staff review: `!pingreport @you` or open a ticket.

---

## What was NOT done

- **No Hunter roles were added or removed** in this deploy.  
- Historical DB rows are unchanged; only **new** messages use the strict rules.  
- Optional later: re-score old rows with `counts_for_grant`, then use `!sync` after staff review.

---

## Deploy notes

- Code: `bot.py` + docs  
- Fly app: `pokehunt-bot-drifting-sky-3389`  
- After deploy, new pings follow the rules above immediately.  
- Recommended env: `AZTEK_USER_ID`, `PROFESSOR_OAK_ROLE_ID` (if not set, Oak cannot run `!pingreport`).


### `!givehunter @user [reason]` / `!removehunter @user [reason]` (Admin only)

Manually grant or revoke **Pokemon Hunter**. Logs actor + reason in `role_grant_log` and `admin_actions`.

```
!givehunter @Member verified in ticket
!removehunter @Member fake pings — see #mod-log
```

Whitelist members cannot be removed by non-Admin.
