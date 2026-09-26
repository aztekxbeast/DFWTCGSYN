# Changelog — PokeHunt Bot

**Updated:** 2026-09-26 · **Live on Fly** `pokehunt-bot-drifting-sky-3389` · **GitHub** `aztekxbeast/DFWTCGSYN` @ `main`

**No Hunter roles were auto-changed by these deploys.** Use `!syncdry` then `!sync` when you’re ready.

---

## Summary

| Area | Change |
|---|---|
| Ping rules | Official store-role pings only (announcements rules) |
| Earn / keep | 10 counted pings to earn · 4 counted (or media/chat) in 10 days to keep |
| Audit | Who granted/rejected; `!addping` logs the admin |
| Staff tools | `!pingreport`, `!sync` / `!syncdry`, `!givehunter` / `!removehunter` |
| Member tools | `!predict` / `!rh` for **Pokemon Hunter+** |
| Fixes | Embed size, location aliases (`lw`, `n tarrant`), honest predict, no extra commands |

---

## What counts as a ping (official rules)

| ✅ Counts | ❌ Does not |
|---|---|
| Real **store role** + place/stock (`@Target` Watauga …) | Typed `@walmart` **without** selecting the role |
| `@Other` + store name + details | `@location` / `@OOS` alone, no store |
| Store role + short place (`@Target` NRH) | Bare `Target` / `Costco` / `pc` / `bb` in chat |
| | Questions (“Target?”, “Anyone at BB?”) |
| | Product URL spam only |
| | Same message logged twice (backfill) |
| | Trainer in `#open-hunting` **without photo** |

### Examples that count
```
@Target Dallas pkwy has PB etc
@Walmart Watauga <@&OOS>
@Other  — Costco Overton has 5-pack tins
@Target NRH
```
Trainer in `#open-hunting`: **include a photo**.

### Examples that do not
```
Anyone at target?
Target
Costco
@walmart
https://www.target.com/p/pokemon-...
```

**`lw` = Lake Worth** (and similar aliases work in `!predict` / `!rh`).

---

## Commands

### Members
| Command | Who | Notes |
|---|---|---|
| `!pings` / `!mylevel` / `!helpme` | everyone | progress & help |
| `!predict <store> [location]` | **Hunter+** | e.g. `!predict target alliance` |
| `!rh <store> [location]` | **Hunter+** | e.g. `!rh walmart beach` |

### Staff
| Command | Who | What |
|---|---|---|
| `!pingreport @user` | Admin · Mod · **Prof. Oak** | Full history (mention, **username**, or ID) |
| `!syncdry` | Admin · Mod | Preview who would gain/lose — **no role changes** |
| `!sync` | Admin | Re-scores old pings + applies grants/revokes |
| `!givehunter @user [reason]` | **Admin** | Manual grant + log |
| `!removehunter @user [reason]` | **Admin** | Manual revoke + log |
| `!addping @user <count>` | **Admin only** | Logs who added |
| `!whitelist` / `!resetpings` / `!restorehunters` / `!stats` | Admin | as before |

**Unauthorized `!addping` (or other staff cmds):** bot **replies** to the attempt and tags **`@aztekbeast`** in that same message, and logs `admin_actions`.

```
!pingreport Deuces
!pingreport trenguyen85 20
!syncdry
!givehunter @Member verified in ticket
!removehunter @Member fake pings
!addping @Member 5          ← Admin only
!predict target eastchase
!rh target lw
```

---

## `!sync` / `!syncdry` (what actually happens)

1. **Re-scores historical pings** under official rules (built-in — no extra command).
2. For each member with pings:
   - **Grant** Hunter if **10 counted** pings
   - **Keep** if whitelist, still in **10-day grace**, or:
     - **4 counted** pings in 10 days, **or**
     - 4 media in 10 days, **or**
     - 30 chat (15+ chars) in 7 days
   - **Revoke** otherwise (after grace)

`!syncdry` = same math, **zero role changes**. Use it first.

---

## `!predict` (honest output)

No more “Possible restock NOW” on chat spam.

| Output | Meaning |
|---|---|
| 🟢 Activity today | Pings today |
| 👀 Active yesterday | Watch next 24h |
| 📊 Frequent activity | Short/noisy cycle — **not** a restock clock |
| ⏰ Possible ~date | Stable cycle, due soon |
| ⏳ Overdue | Sparse history, last activity Xd ago |
| Confidence High | Only if 8+ dates, 6+ gaps, avg ≥ 2 days, low variance |

Location variants group as one place (`Eastchase PB` / `17 Eastchase` → **Eastchase**).  
Aliases: `lw` → Lake Worth, `n tarrant` / `tarrant` → North Tarrant, etc.

Embeds auto-split if over Discord’s 6000-char limit.

---

## DB / audit (for staff tickets)

| Table / field | Purpose |
|---|---|
| `pings.counts_for_grant` | 1 = official ping |
| `pings.reject_reason` | `no_store_role`, `question`, `empty_report`, `no_photo`… |
| `pings.added_by` | who ran `!addping` |
| `pings.message_id` | dedupe / jump links |
| `hunter_role_earned.grant_reason` | why role was given |
| `role_grant_log` | every grant/revoke + actor |
| `admin_actions` | staff commands + denied attempts |

`!pingreport` pulls all of this for a user (e.g. Role Support tickets).

---

## Also merged from `main` (kept)

- Hunting Noob auto-assign / `!assignnoobs`
- `!rh` newest-first, 14-day default, embed cap
- Open-hunting media requirement for Trainers
- Flagging (`🚩`/`❌`) **Admin/Mod only**

---

## Config (already set on Fly)

| Env | Value |
|---|---|
| `PROFESSOR_OAK_ROLE_ID` | `1539123032847687730` |
| `AZTEK_USER_ID` | `638486065430265877` |
| `HUNTING_NOOB_ROLE_ID` | *(from earlier main work)* |

---

## Suggested rollout

1. Announce the ping format to members (store role + place; photo in open-hunting).  
2. `!syncdry` — review who would drop.  
3. `!sync` when staff agrees.  
4. Tickets: `!pingreport <name>` (username works).
