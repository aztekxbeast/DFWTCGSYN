# Changelog — PokeHunt Bot

**Updated:** 2026-09-27 · **Live on Fly** `pokehunt-bot-drifting-sky-3389` · **GitHub** `aztekxbeast/DFWTCGSYN` @ `main`

**2026-09-27 deploy:** `ed0a2fc` + `150fafb` live on Fly (machine `87475e6c644998`, iad). No Hunter roles auto-changed. After review run `!syncdry` then `!sync` to re-score history.

---

## 2026-10-01 — New store: BJs Wholesale (@BJs Wholesale role now counts as a ping)

| Area | Change |
|---|---|
| Store list | Added `bjs-wholesale` to `store_channels` in `config.json` — pinging the **@BJs Wholesale** role counts as an official store ping (needs the usual details/photo per rules) |
| Role matching | Name variants all map correctly: `BJs Wholesale`, `BJ's Wholesale`, `BJS`, `Bjs`, `bjs-wholesale` |
| Reports | BJ's pings show as `bjs-wholesale` in `!pingreport` / history (own store, not lumped into `others`) |

---

## 2026-10-01 — Fix: intermittent missing Hunting Noob on join (write race + self-healing)

| Area | Change |
|---|---|
| Root cause | Role writes made in the same second as the rules-gate flip (users clicking through screening instantly) can be washed out — bot logged "assigned" but roles were missing server-side (e.g. meowzer024, dropmass, pugachu99) |
| Join flow | Pending members no longer get role writes at join — roles are assigned only **after** the gate passes (avoids the wash-out) |
| Re-check | 90s after the gate, a re-check repairs any role that didn't stick (logged as `rules_recheck`) |
| Self-heal sweep | Every 10 min (and at startup): members who joined within 7 days and passed the gate get missing Trainer/Hunting Noob (logged as `sweep`) — catches races, restarts, and lost events |
| Logging | Role-assignment failures now print errors instead of being silently swallowed |

---

## 2026-09-28 — Fix: pings with @Barnes / @SamsClub / @5Below etc. never counted

| Area | Change |
|---|---|
| Store role matching | Role names that don't normalize to store keys now map correctly: **Barnes** → `barnes-and-noble`, **SamsClub** → `sam's-costco`, and **5Below / DicksSG / HEB / LocalCardStore / PopShelf / QT** → `others` bucket (same as Ace Hardware). Their pings were silently dropped (not even logged as rows) |
| OOS clarification | Store role **+ @OOS** together always counted fine when the store role matched (e.g. `@Target` + `@OOS`) — the misses were purely the unmatched role names above |
| `!deepbackfill` | Now also matches store names from role mentions (same matcher as live), so recovered pings get the correct store instead of "unknown" |

---

## 2026-09-28 — Ping report times shown in DFW local time (CT)

| Area | Change |
|---|---|
| `!pingreport` | Ping history, grant/revoke log, admin actions, and Earned date now display in **America/Chicago** — matches how Discord shows message times to mods (was raw UTC, ~5h off) |
| `!whitelist view` | Added-on dates also converted to CT |
| Footer | Report now labels "times in CT (DFW)" |

---

## 2026-09-28 — Rules GATE counts as rules acknowledgment (fix: new members missing Hunting Noob)

| Area | Change |
|---|---|
| Rules gate | Passing Discord's membership-screening rules gate (`pending` → cleared) now assigns **Pokemon Trainer** + **Hunting Noob** — same as reacting to the rules post (was reaction-only, so gate-only acks got nothing) |
| Reaction ack | Now uses the event's member payload + fetch fallback — brand-new members no longer silently skipped on cache miss |
| Logging | Rules-gate grants logged as `rules_ack`/`rules_gate`; failures print instead of vanishing |

Root cause for `tempezts` (Ponch): server has `MEMBER_VERIFICATION_GATE_ENABLED`; the user joined and acknowledged via the gate — no reaction event ever fired, and the DB showed no `rules_ack` row. Role fixed manually; automation now covers the gate path.

---

## 2026-09-27 — Hunting Noob auto-assigned when Hunter role is lost

| Area | Change |
|---|---|
| Maintenance revoke | Losing **Pokemon Hunter** for failing activity maintenance now auto-assigns **Hunting Noob** (was only in `!removehunter`) |
| Any role change | New `on_member_update` sync: Hunter lost (admin edit / other bot) → **Hunting Noob** · Hunter gained → Noob removed |
| Guard | Noob only assigned to **Pokemon Trainer** holders (unchanged) |

---

## 2026-09-27 — Ticket fixes (pings not counting) + rules → Hunting Noob

| Area | Change |
|---|---|
| Rules ack | ✅ on official rules post → **Pokemon Trainer** + **Hunting Noob** (until Hunter) |
| Rules bind | Pinned `#rules-and-guidelines` `1496203694994227313` / msg `1542167722752876704` · `!setrules` |
| Ping match | Store roles match by normalized name (`BestBuy` / `Best Buy` / `best-buy`) |
| Photo pings | Store role **+ photo** counts even with no caption (was `empty_report`) |
| `#open-hunting` photo | Required for **Trainers only** (Hunters may text-report) |
| Hunting Noob | Removed on every Hunter grant (incl. `!givehunter`) · restored by `!removehunter` |
| `!status` / `!mylevel` | Uses **counted** pings for eligibility · never tells members to run admin `!sync` · auto-grants when eligible |
| `!sync` rescore | Fixed crash selecting missing `pings.source` column |
| Repo | GUI controller, icons, scripts included in git |

### Still required on Fly (not in secrets yet)

`HUNTING_NOOB_ROLE_ID` — without it rules check mark cannot assign Hunting Noob.  
Optional explicit: `RULES_CHANNEL_ID=1496203694994227313`, `RULES_MESSAGE_ID=1542167722752876704` (also hardcoded in `bot.py`).

**Discord perms (manual):** `#open-hunting` → **Hunting Noob** → View + Send Messages (+ Attach Files).

---

## Prior summary (official ping rules)

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
| Store role **+ photo** (even no caption) | `@location` / `@OOS` alone, no store |
| `@Other` + store name + details (or photo) | Bare `Target` / `Costco` / `pc` / `bb` in chat |
| Store role + short place (`@Target` NRH) | Questions (“Target?”, “Anyone at BB?”) |
| Hunter text report in `#open-hunting` | Product URL spam only |
| | Trainer in `#open-hunting` **without photo** |

### Examples that count
```
@Target Dallas pkwy has PB etc
@Walmart Watauga <@&OOS>
@Other  — Costco Overton has 5-pack tins
@Target NRH
@BestBuy Midway & 635 + photo
@Target + shelf photo (no caption)
```
Trainer in `#open-hunting`: **include a photo**. Hunters: text is OK.

### Examples that do not
```
Anyone at target?
Target
Costco
@walmart          ← typed text, not a role ping
https://www.target.com/p/pokemon-...
I'm 47 at alliance Costco
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
