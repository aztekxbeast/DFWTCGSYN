# Security Review — Railway October 21 Incident Response

**Date:** 2026-10-29
**Trigger:** Railway (railway.app) security incident of October 20–22, 2026
(unauthorized access to Railway internal systems; attacker targeted AI provider
API keys; up to 1.85% of workspaces had env vars potentially compromised).
**Scope:** Full exposure audit of this project — local machine, GitHub repository,
Fly.io server, and Discord bot credentials.

## Findings

| # | Severity | Area | Finding | Outcome |
|---|----------|------|---------|---------|
| 1 | HIGH | GitHub PAT | Classic PAT `dfw-tcg-bot` (`repo, workflow`, no expiry) had been stored in Railway env vars before Oct 21 and was embedded in `.git/config` as the remote URL credential | **Resolved** — token deleted, remote URL cleaned, replaced by GitHub CLI credential |
| 2 | MEDIUM | GitHub app access | Railway GitHub app connection history unknown (Railway advisory: review installed app access) | **Reviewed** in GitHub settings (2026-10-29) |
| 3 | MEDIUM | Railway account | Account existed (empty/unused); advisory requires rotating anything stored pre-Oct 21 | **Resolved** — verified empty, password rotated, account deleted |
| 4 | LOW | Repo visibility | Repository is public (owner decision; code verified secret-free across all history) | **Accepted** — owner chose to keep public |
| 5 | INFO | Discord bot token | Never stored on Railway — not implicated by the incident | **No action** |

## Areas verified clean

- **Git history** — no committed secrets (only `.env.example` placeholders and code
  f-strings matched secret-pattern scans)
- **Local storage** — `.env` (real token) exists but is gitignored and untracked;
  no Keychain item; no `~/.config/pokehunt` credentials file
- **Fly.io** — all secrets stored as Fly secrets (`DISCORD_TOKEN` etc., values
  never in `fly.toml` or source); SQLite DB on a volume, never network-exposed
- **GitHub** — zero webhooks, zero deploy keys; Actions workflow
  (`.github/workflows/fly-deploy.yml`) uses `secrets.FLY_API_TOKEN` correctly
- **Container registry** — no Docker/GHCR credentials on the workstation; Fly
  builds remotely (Railway advisory item 4 does not apply)

## Remediation performed (2026-10-29)

1. GitHub CLI device-flow login established as the new git credential path
   (keyring-stored OAuth token, scopes `repo, read:org, gist`)
2. Old embedded PAT removed from the git remote URL; verified read + write +
   API access through the new path
3. Suspect PAT deleted in GitHub; fine-grained token list checked; installed
   GitHub apps reviewed
4. Railway account cleaned up and deleted

## Remaining recommendations

- Prefer **fine-grained PATs or SSH** if any new token is ever needed; avoid
  no-expiry tokens
- Re-run this audit if Railway's investigation publishes new impact details
  (follow-up report pending as of 2026-10-29)
- Consider rotating `FLY_API_TOKEN` (GitHub Actions secret) periodically as
  general hygiene — it was never exposed to Railway

## References

- Railway changelog: <https://railway.com/changelog/2026-10-23-october-21-security-incident>
- Railway preliminary report: <https://blog.railway.com/p/preliminary-report-october-security-incident>
