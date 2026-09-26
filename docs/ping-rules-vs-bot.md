# Official ping rules vs bot detection

Source: staff announcements (AztekxBeast, Aug–Sep 2026) for DFW TCG SYNDICATE.

## What staff says a ping IS

| Rule | Source | Meaning |
|---|---|---|
| Ping the **store**, not the area | 8/30 | `@Target`, `@Walmart` — not `@Dallas` / location roles (those ping everyone) |
| Include store + details | 8/30 example | `@Target Dallas pkwy has PB etc` |
| No store role? Use `@Other` + details | 8/30 | “if there isn't a store tag use @Other and add details for the store” |
| **Photo required** for Trainers in open-hunting | 8/30 | “@Pokemon Trainer is supposed to ping with a photo in open hunting or it doesn't count” |
| Hunters post in **area channels** (or store channels) | 8/30 | Organization, not a free-for-all in general chat |
| **10 pings** to unlock Hunter | 9/1, help | Lifetime/period to *gain* access |
| **4 pings / 10 days** to keep it | 9/1 | Maintenance only |
| Don’t spam pings | open-hunting note | “We can see how many pings you have realistically” |
| Disputes → ticket | 8/11, 9/4 | Staff can look up real pings |

## What the bot counts NOW (too loose)

In `extract_store_from_text` / `on_message` **before** this pass:

| Behavior | Old bot counted? | Official |
|---|---|---|
| Real `@Store` role + place/stock text | yes | **yes** |
| Real `@Store` role with empty body (only role pills) | yes | no |
| Text `@walmart` / `@target` without selecting the role | yes | no |
| Text `@location` / `@oos` alone | yes | no |
| Bare word `Target` / `Costco` / `pc` / `bb` | yes | no |
| Abbreviation token treated as a store ping | yes | no |
| Questions with a store word | yes | no |
| Product URL spam (`target.com/...`) | yes | no |
| Same message inserted 2–4× | yes (each row) | no (dedupe) |
| Trainer in open-hunting without photo | yes | no |
| `!addping` | yes (no actor log) | staff tool; must log who |

## What should count (proposed strict criteria)

A ping **counts for Hunter grant/maintain** only if ALL of:

1. **Real store role mention** (`<@&…>` whose role name is a store)  
   **OR** `@Other` / `@other` with a store name spelled in the body.
2. **Body has real report text** after stripping mentions — min ~12 chars, not only the store name.
3. **Not a pure question** (no `?` as the whole message / “anyone/has anyone/is there” patterns without a report).
4. **Not a bare product URL** dump (links alone don’t count).
5. **Unique `message_id`** (ignore re-inserts).
6. **Trainer (non-Hunter) in #open-hunting:** must have **≥1 image attachment**.
7. Prefer area/store channels; still allow store channels. Optionally exclude pure social channels unless a real store role is used.

## DB fields we need (new)

| Column | Why |
|---|---|
| `message_id` (already) | dedupe key |
| `channel_name` | audit |
| `has_photo` | trainer rule |
| `counts_for_grant` | 0/1 quality gate |
| `reject_reason` | why it didn’t count (question, no_role, spam, no_photo…) |
| `grant_reason` on `hunter_role_earned` | threshold / manual / mee6 / whitelist |
| `added_by` on pings when manual | who ran `!addping` |

## Grant math (should be)

- **Gain:** `COUNT(*) FROM pings WHERE user_id=? AND counts_for_grant=1` ≥ 10
- **Maintain:** same in last 10 days ≥ 4 (or media/chat maintain as today)
- `!pings` shows both raw and counted totals so staff can see “realistic” volume
