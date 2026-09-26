# Official ping rules scorecard

Compared staff announcements to bot behavior, then re-scored production pings.

## Official rules (from general announcements)

1. **Ping the store role** (`@Target`), not an area role.
2. Format is store + place + stock: `@Target Dallas pkwy has PB etc`.
3. No store role? Use **`@Other`** and write the store in the body.
4. **`@Pokemon Trainer` must include a photo** in `#open-hunting` or it **doesn’t count**.
5. Hunters post in area/store channels (organization).
6. **10 counted pings** to gain Hunter; **4 in 10 days** to keep it.
7. Don’t spam — staff checks “realistic” volume.
8. Disputes go to tickets (staff can look up real pings).

Documented in `docs/ping-rules-vs-bot.md`.

## What used to count (old bot) vs official

Old bot = `extract_store_from_text` + `log_ping` before this pass.  
Official = staff announcements + `validate_ping` after this pass.

| Behavior | Old bot | Official / new bot |
|---|---|---|
| Real `@Store` **role** ping (`<@&…>`) with a place or stock line (`@Target` Watauga …) | **count** | **count** |
| Real `@Store` role ping with **no body** (only the role pills) | **count** | no (`empty_report`) |
| Text `@walmart` / `@target` typed **without** selecting the role | **count** | no (`no_store_role`) |
| Text `@location` / `@oos` alone (no store role) | **count** | no (`no_store_role`) |
| Bare word `Target` / `Costco` / `Walmart` in chat | **count** | no (`no_store_role`) |
| Abbreviation token `pc` `bb` `gs` `mc` `dt` `dg` `costco` `sams` as a word | **count** (treated as store ping) | no (`no_store_role`) |
| Questions (“Target?”, “Anyone at BB?”, “Is Best Buy getting tins?”) | **count** | no (`question`) |
| Product URL spam (`https://www.target.com/p/...`) | **count** (URL has `target`) | no (`link_only` / `no_store_role`) |
| Same Discord message logged 2–4× (realtime + backfill) | **count each row** | no (dedupe on `message_id`) |
| `@Pokemon Trainer` post in `#open-hunting` **without photo** | **count** | no (`no_photo`) |
| `@Other` role + store name + details | **count** | **count** |
| `!addping` dump by staff | **count** (unlogged) | **count** only with `added_by` + `admin_actions` / `role_grant_log` |

**Notes**
- “Text `@walmart` without role” means the user **typed** `@walmart` as normal characters. Discord never pinged the Walmart role. In the DB that looks like plain text, not `<@&role_id>`.
- `@Location` / `@OOS` are real roles on the server. Staff said: ping the **store** (`@Target`), not the area. Bare `@Location`/`@OOS` with no store role is not a report.
- `!addping` is a staff tool, not in the announcements. It still moves the counter, but now it must record **who** issued it.

## Production re-score (4,297 unique messages)

| Result | Count | Share |
|---|---:|---:|
| **PASS** (would count now) | 3,031 | 71% |
| `no_store_role` (chat / abbrev / text @store) | 1,120 | 26% |
| `empty_report` (roles only, no place) | 67 | 2% |
| `manual` (!addping) | 60 | 1% |
| `store_name_only` | 10 | 0% |
| `question` | 9 | 0% |

**Duplicate rows ignored:** 2,834 of 7,131 (~40% double-count).

### Grant impact

| Rule set | Users with 10+ pings |
|---|---:|
| Old raw unique | **173** |
| Official counted | **132** |

So **~40 users** would not have hit Hunter under the announcements’ rules.

Worst “would not qualify” (high raw, low official): Coralla, Smurf_pc, WARHAMMER, Kram70, CantuCzrl, BugsFunny, oezax, etc. (see `data/fake-ping-audit-report.md` for usernames).

## Code / DB changes made in `bot.py`

### DB (new)

- `pings.channel_name`, `has_photo`, `counts_for_grant`, `reject_reason`, `added_by`
- `hunter_role_earned.grant_reason`
- **`role_grant_log`** — every Hunter grant/revoke with `reason`, `source`, `actor_id`, `ping_count`, timestamp
- **`admin_actions`** — who ran `!addping` / whitelist / denied attempts

### Detection

- `extract_store_from_text` now **only** accepts:
  - real **store role** mentions, or
  - **`@Other`** + store name in body
- `validate_ping()` rejects empty reports, pure questions, link-only, bare store names
- Trainers in `#open-hunting` need a **photo** (`no_photo` reject)
- `log_ping` **dedupes on `message_id`**
- Grant uses `counts_for_grant = 1` only (`count_total(..., only_counted=True)`)

### `!addping` security

- Admin/Mod only (`has_any_role(ADMIN, MOD)`)
- Stores **`added_by`** on each inserted ping
- Writes `admin_actions` + `role_grant_log` when it flips someone over threshold
- **Unauthorized attempt** → bot pings the offender **and** `@aztekbeast` (`AZTEK_USER_ID`, default `638486065430265877`)

### Grant-reason log

Every path records `source` + `reason`:

| source | when |
|---|---|
| `threshold` | 10 counted pings |
| `mee6_silver` / `mee6_gold_diamond` / `mee6_sync` / `mee6_import` / `mee6_scan` | MEE6 paths |
| `whitelist` | staff whitelist |
| `manual_restore` | `!restorehunters` |
| `maintenance` | revoke for inactivity |
| `message_scan` | `!messagescan` |

## Still open (staff judgment)

1. **Backfill 104 vs 132:** some short `Watauga @Store @OOS` posts count as real (location + store role). That matches the “store + place” example.
2. **Manual pings** still count toward 10 — decide if they should be capped or flagged as `counts_for_grant=0` until reviewed.
3. **Photo rule** only applied in `#open-hunting`. If you want photos everywhere for Trainers, say so and we’ll widen it.
4. **Deploy** these bot changes to Fly when ready (`flyctl deploy`).
5. Optional: backfill `counts_for_grant` on historical rows with the same classifier so `!pings` / `!sync` match the new rules immediately.

---

## Staff tools added

### `!pingreport @user [limit]` (aliases: `!pingrep`, `!phistory`)
- **Who:** Admin, Mod, **or Professor Oak** (`PROFESSOR_OAK_ROLE_ID`)
- **Output:** Hunter/whitelist status, raw vs counted totals, score breakdown, last N pings with ✅/❌ and jump links, grant/revoke log, `!addping` audit
- Every run is written to `admin_actions` (who looked up whom)

### Unauthorized staff commands
- Bot **replies** to the attempt and tags **`@aztekbeast`** in the **same** message (Discord reply = permanent log trail)
