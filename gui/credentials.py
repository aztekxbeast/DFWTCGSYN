"""One-time Discord credential storage.

Bot tokens do not expire unless reset in the Discord Developer Portal.
This module stores them once (Keychain + local config + project .env) so the
user never has to re-enter login details on every launch.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path.home() / ".config" / "pokehunt"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"
ENV_PATH = PROJECT_ROOT / ".env"
KEYCHAIN_SERVICE = "pokehunt-discord-bot"
KEYCHAIN_ACCOUNT = "discord-bot-token"

# Fields persisted across launches (ids are not secrets; token is).
ID_FIELDS = (
    "GUILD_ID",
    "POKEMON_TRAINER_ROLE_ID",
    "POKEMON_HUNTER_ROLE_ID",
    "ADMIN_ROLE_ID",
    "MOD_ROLE_ID",
    "ANNOUNCEMENTS_CHANNEL_ID",
    "GETROLES_CHANNEL_ID",
    "GENERAL_CHAT_CHANNEL_ID",
    "OPEN_HUNTING_CHANNEL_ID",
    "MOD_CHAT_CHANNEL_ID",
    "PULLS_CHANNEL_ID",
    "SUCCESS_CHANNEL_ID",
    "MEE6_SILVER_ROLE_ID",
)

TOKEN_PLACEHOLDER_MARKERS = (
    "your-bot-token-here",
    "your-token-here",
    "changeme",
)


def ensure_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, stat.S_IRWXU)
    except OSError:
        pass
    return CONFIG_DIR


def _keychain_available() -> bool:
    return subprocess.call(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) in (0, 44)  # 44 = not found (still usable)


def save_token_to_keychain(token: str) -> bool:
    """Store the Discord bot token in macOS Keychain. Returns True on success."""
    if not token or not token.strip():
        return False
    token = token.strip()
    # Replace any existing item first
    subprocess.call(
        ["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    result = subprocess.run(
        ["security", "add-generic-password",
         "-U",  # update if exists
         "-a", KEYCHAIN_ACCOUNT,
         "-s", KEYCHAIN_SERVICE,
         "-w", token],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def load_token_from_keychain() -> Optional[str]:
    result = subprocess.run(
        ["security", "find-generic-password",
         "-w",  # print password only
         "-s", KEYCHAIN_SERVICE,
         "-a", KEYCHAIN_ACCOUNT],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    token = (result.stdout or "").strip()
    return token or None


def delete_token_from_keychain() -> None:
    subprocess.call(
        ["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _read_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _is_placeholder_token(token: Optional[str]) -> bool:
    if not token:
        return True
    lowered = token.lower()
    return any(m in lowered for m in TOKEN_PLACEHOLDER_MARKERS)


def load_credentials() -> dict[str, Any]:
    """Load credentials from Keychain + local config + project .env.

    Precedence for the token: Keychain → credentials.json → .env
    IDs: credentials.json → .env
    """
    ensure_config_dir()
    file_creds: dict[str, Any] = {}
    if CREDENTIALS_PATH.exists():
        try:
            file_creds = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            file_creds = {}

    env_creds = _read_env_file(ENV_PATH)

    token = load_token_from_keychain()
    if _is_placeholder_token(token):
        token = file_creds.get("DISCORD_TOKEN") or env_creds.get("DISCORD_TOKEN")
    if _is_placeholder_token(token):
        token = None

    result: dict[str, Any] = {"DISCORD_TOKEN": token}
    for field in ID_FIELDS:
        value = file_creds.get(field) or env_creds.get(field) or ""
        result[field] = str(value) if value not in (None, "") else ""
    result["_has_credentials"] = bool(token) and bool(result.get("GUILD_ID"))
    result["_keychain_ok"] = load_token_from_keychain() is not None
    return result


def save_credentials(token: str, ids: dict[str, str]) -> dict[str, Any]:
    """Persist credentials forever: Keychain + credentials.json + project .env."""
    ensure_config_dir()
    token = (token or "").strip()
    clean_ids = {k: str(v).strip() for k, v in ids.items() if k in ID_FIELDS}

    payload = {"DISCORD_TOKEN": token, **clean_ids}
    CREDENTIALS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(CREDENTIALS_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

    keychain_ok = save_token_to_keychain(token)

    # Write .env so `python bot.py` works standalone too (token may be blank if keychain-only)
    env_token = token if not keychain_ok else token  # keep in .env as fallback
    lines = [
        "# Generated by PokeHunt Controller — do not commit",
        f"DISCORD_TOKEN={env_token}",
        "",
    ]
    for field in ID_FIELDS:
        lines.append(f"{field}={clean_ids.get(field, '')}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(ENV_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

    return load_credentials()


def clear_credentials() -> None:
    delete_token_from_keychain()
    if CREDENTIALS_PATH.exists():
        CREDENTIALS_PATH.unlink()
    if ENV_PATH.exists():
        ENV_PATH.unlink()


def has_sticky_credentials() -> bool:
    creds = load_credentials()
    return bool(creds.get("_has_credentials"))


def credentials_summary() -> dict[str, str]:
    """Human-readable summary of what is stored (never returns the raw token)."""
    creds = load_credentials()
    token = creds.get("DISCORD_TOKEN") or ""
    if token and len(token) > 12:
        masked = f"{token[:6]}…{token[-4:]}"
    elif token:
        masked = "••••••••"
    else:
        masked = "Not saved"
    return {
        "token_masked": masked,
        "guild_id": creds.get("GUILD_ID") or "—",
        "hunter_role": creds.get("POKEMON_HUNTER_ROLE_ID") or "—",
        "storage": "macOS Keychain + ~/.config/pokehunt" if creds.get("_keychain_ok") else "~/.config/pokehunt",
        "ready": "Yes" if creds.get("_has_credentials") else "No — run Setup",
    }
