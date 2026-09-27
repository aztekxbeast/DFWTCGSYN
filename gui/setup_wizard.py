"""Guided Discord login wizard for non-technical users.

Opens the Discord Developer Portal, walks through creating a bot, copying the
token, inviting the bot, and collecting IDs — then saves credentials forever.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Callable, Optional

import customtkinter as ctk
from tkinter import messagebox

from gui import theme as T

# Discord permission integer used in the invite link:
# VIEW_CHANNEL | SEND_MESSAGES | READ_MESSAGE_HISTORY | MENTION_EVERYONE | MANAGE_ROLES
INVITE_PERMISSIONS = 268635136

PORTAL_APPS = "https://discord.com/developers/applications"
PORTAL_NEW_APP = "https://discord.com/developers/applications?new_application=true"
DEVELOPER_MODE_HELP = (
    "In Discord: User Settings → Advanced → enable Developer Mode.\n"
    "Then right-click your server → Copy Server ID."
)


def open_url(url: str) -> None:
    webbrowser.open(url)


def bot_tab_url(app_id: str) -> str:
    app_id = (app_id or "").strip()
    if app_id.isdigit():
        return f"https://discord.com/developers/applications/{app_id}/bot"
    return PORTAL_APPS


def oauth_url(app_id: str) -> str:
    app_id = (app_id or "").strip()
    if app_id.isdigit():
        return f"https://discord.com/developers/applications/{app_id}/oauth2"
    return PORTAL_APPS


def invite_url(client_id: str) -> str:
    client_id = (client_id or "").strip()
    if not client_id.isdigit():
        return PORTAL_APPS
    params = {
        "client_id": client_id,
        "permissions": str(INVITE_PERMISSIONS),
        "scope": "bot applications.commands",
    }
    return "https://discord.com/oauth2/authorize?" + urllib.parse.urlencode(params)


def validate_bot_token(token: str) -> tuple[bool, str]:
    """Return (ok, message). Never raises."""
    token = (token or "").strip()
    if not token:
        return False, "Paste a token first."
    req = urllib.request.Request(
        "https://discord.com/api/v10/users/@me",
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "PokeHuntController/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "Discord rejected that token. Copy it again from the Bot tab."
        return False, f"Discord API error (HTTP {exc.code})."
    except Exception as exc:
        return False, f"Could not reach Discord: {exc}"
    username = body.get("username") or body.get("id") or "bot"
    return True, f"Token works — bot account “{username}”."


class StepCard(ctk.CTkFrame):
    def __init__(self, master, number: int, title: str, body: str, **kwargs):
        super().__init__(
            master, fg_color=T.SURFACE_2, corner_radius=T.RADIUS,
            border_width=1, border_color=T.BORDER, **kwargs,
        )
        self.grid_columnconfigure(1, weight=1)
        badge = ctk.CTkLabel(
            self, text=str(number), width=28, height=28, corner_radius=14,
            fg_color=T.ACCENT, text_color="#FFFFFF", font=T.FONT_UI_BOLD,
        )
        badge.grid(row=0, column=0, padx=(14, 10), pady=(14, 0), sticky="n")
        ctk.CTkLabel(
            self, text=title, text_color=T.TEXT, font=T.FONT_UI_BOLD, anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(14, 2))
        ctk.CTkLabel(
            self, text=body, text_color=T.TEXT_MUTED, font=T.FONT_UI,
            justify="left", anchor="w", wraplength=520,
        ).grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=(0, 10))
        # keep number column size
        self.grid_columnconfigure(0, weight=0)


class SetupWizard(ctk.CTkFrame):
    """Full-page guided setup for grabbing a Discord bot token."""

    def __init__(
        self,
        master,
        on_complete: Callable[[str, dict[str, str]], None],
        on_skip_advanced: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color=T.BG, corner_radius=0, **kwargs)
        self.on_complete = on_complete
        self.on_skip_advanced = on_skip_advanced
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._validated = False
        self._bot_username = ""

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(20, 4))
        ctk.CTkLabel(
            header, text="Connect Discord", text_color=T.TEXT, font=T.FONT_TITLE,
        ).pack(side="left")
        ctk.CTkButton(
            header, text="Skip to advanced form", height=32, fg_color="transparent",
            hover_color=T.SURFACE_3, text_color=T.TEXT_MUTED, font=T.FONT_CAPTION,
            command=self._skip,
        ).pack(side="right")

        ctk.CTkLabel(
            self,
            text=(
                "You only do this once. A Discord bot token is a password for the bot — "
                "not your personal Discord login. After you save it here, the app remembers it forever."
            ),
            text_color=T.TEXT_MUTED, font=T.FONT_UI, justify="left", anchor="w",
            wraplength=640,
        ).grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 4))

        # Scrollable body
        body = ctk.CTkScrollableFrame(self, fg_color=T.BG)
        body.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 0))
        body.grid_columnconfigure(0, weight=1)

        # ── Step 1: Create app ───────────────────────────────────────────
        s1 = StepCard(
            body, 1, "Open Discord Developer Portal",
            "Sign in with the same Discord account that owns your server.\n"
            "Click “New Application”, name it (e.g. PokeHunt), and Create.",
        )
        s1.pack(fill="x", padx=20, pady=(8, 10))
        ctk.CTkButton(
            s1, text="Open Developer Portal", height=36, fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER, text_color="#FFFFFF", font=T.FONT_UI_BOLD,
            command=lambda: open_url(PORTAL_NEW_APP),
        ).grid(row=2, column=1, sticky="w", padx=(0, 14), pady=(4, 14))

        # ── Step 2: Bot token ────────────────────────────────────────────
        s2 = StepCard(
            body, 2, "Copy your Bot Token",
            "In the left sidebar click “Bot”.\n"
            "Click “Reset Token” (or “Copy” if a token already shows).\n"
            "Confirm with your 2FA/MFA if Discord asks, then Copy the token.\n"
            "Tip: paste it below immediately so you don’t lose it.",
        )
        s2.pack(fill="x", padx=20, pady=(0, 10))

        app_id_row = ctk.CTkFrame(s2, fg_color="transparent")
        app_id_row.grid(row=2, column=1, sticky="ew", padx=(0, 14), pady=(0, 6))
        ctk.CTkLabel(
            app_id_row, text="Application ID (from General Information)",
            text_color=T.TEXT_MUTED, font=T.FONT_CAPTION, anchor="w",
        ).pack(side="left")
        self.app_id_var = ctk.StringVar()
        ctk.CTkEntry(
            s2, textvariable=self.app_id_var, placeholder_text="Optional but unlocks one-click links",
            fg_color=T.SURFACE, border_color=T.BORDER, text_color=T.TEXT,
        ).grid(row=3, column=1, sticky="ew", padx=(0, 14), pady=(0, 6))
        ctk.CTkButton(
            s2, text="Open Bot settings page", height=34, fg_color=T.SURFACE_3,
            hover_color=T.BORDER, text_color=T.TEXT,
            command=lambda: open_url(bot_tab_url(self.app_id_var.get())),
        ).grid(row=4, column=1, sticky="w", padx=(0, 14), pady=(0, 10))

        token_label = ctk.CTkLabel(
            s2, text="Paste Bot Token", text_color=T.TEXT, font=T.FONT_UI_BOLD, anchor="w",
        )
        token_label.grid(row=5, column=1, sticky="ew", padx=(0, 14), pady=(4, 2))
        token_row = ctk.CTkFrame(s2, fg_color="transparent")
        token_row.grid(row=6, column=1, sticky="ew", padx=(0, 14), pady=(0, 6))
        self.token_var = ctk.StringVar()
        self.token_entry = ctk.CTkEntry(
            token_row, textvariable=self.token_var, show="•",
            fg_color=T.SURFACE, border_color=T.BORDER, text_color=T.TEXT,
            placeholder_text="Bot token from the Bot tab",
        )
        self.token_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            token_row, text="Show", width=70, height=32, fg_color=T.SURFACE_3,
            hover_color=T.BORDER, text_color=T.TEXT, command=self._toggle_token,
        ).pack(side="left", padx=(8, 0))

        val_row = ctk.CTkFrame(s2, fg_color="transparent")
        val_row.grid(row=7, column=1, sticky="ew", padx=(0, 14), pady=(0, 14))
        ctk.CTkButton(
            val_row, text="Check token", height=34, fg_color=T.SURFACE_3,
            hover_color=T.BORDER, text_color=T.TEXT, command=self._check_token,
        ).pack(side="left")
        self.token_status = ctk.CTkLabel(
            val_row, text="", text_color=T.TEXT_MUTED, font=T.FONT_CAPTION,
        )
        self.token_status.pack(side="left", padx=12)

        # ── Step 3: Message Content Intent ───────────────────────────────
        s3 = StepCard(
            body, 3, "Turn on Message Content Intent",
            "Still on the Bot page → Privileged Gateway Intents.\n"
            "Enable “Message Content Intent”. Save Changes if asked.\n"
            "The bot needs this to read ping messages.",
        )
        s3.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkButton(
            s3, text="Open Bot settings page", height=34, fg_color=T.SURFACE_3,
            hover_color=T.BORDER, text_color=T.TEXT,
            command=lambda: open_url(bot_tab_url(self.app_id_var.get())),
        ).grid(row=2, column=1, sticky="w", padx=(0, 14), pady=(0, 14))

        # ── Step 4: Invite ───────────────────────────────────────────────
        s4 = StepCard(
            body, 4, "Invite the bot to your server",
            "Use the button below (needs Application ID from step 2),\n"
            "or in the Portal: OAuth2 → URL Generator → scopes bot +\n"
            "applications.commands → permissions: Manage Roles, View Channels,\n"
            "Send Messages, Read Message History, Mention Everyone → copy URL → open it.",
        )
        s4.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkButton(
            s4, text="Open invite link", height=34, fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER, text_color="#FFFFFF",
            command=self._open_invite,
        ).grid(row=2, column=1, sticky="w", padx=(0, 14), pady=(0, 6))
        self.invite_hint = ctk.CTkLabel(
            s4, text="Enter Application ID first, then click the invite button.",
            text_color=T.TEXT_DIM, font=T.FONT_CAPTION, anchor="w",
        )
        self.invite_hint.grid(row=3, column=1, sticky="ew", padx=(0, 14), pady=(0, 14))

        # ── Step 5: Server ID ────────────────────────────────────────────
        s5 = StepCard(
            body, 5, "Copy your Server ID",
            DEVELOPER_MODE_HELP,
        )
        s5.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(
            s5, text="Server (Guild) ID", text_color=T.TEXT, font=T.FONT_UI_BOLD, anchor="w",
        ).grid(row=2, column=1, sticky="ew", padx=(0, 14), pady=(4, 2))
        self.guild_var = ctk.StringVar()
        ctk.CTkEntry(
            s5, textvariable=self.guild_var, placeholder_text="A long number like 123456789012345678",
            fg_color=T.SURFACE, border_color=T.BORDER, text_color=T.TEXT,
        ).grid(row=3, column=1, sticky="ew", padx=(0, 14), pady=(0, 14))

        # ── Step 6: optional IDs ─────────────────────────────────────────
        s6 = StepCard(
            body, 6, "Optional IDs (roles & channels)",
            "Leave blank to start. Right-click a role or channel in Discord\n"
            "with Developer Mode on → Copy ID, then paste below.",
        )
        s6.pack(fill="x", padx=20, pady=(0, 10))

        self.id_vars: dict[str, ctk.StringVar] = {}
        optional_fields = [
            ("POKEMON_HUNTER_ROLE_ID", "Pokemon Hunter role ID"),
            ("POKEMON_TRAINER_ROLE_ID", "Pokemon Trainer role ID"),
            ("ADMIN_ROLE_ID", "Admin role ID"),
            ("MOD_ROLE_ID", "Moderator role ID"),
            ("ANNOUNCEMENTS_CHANNEL_ID", "Announcements channel ID"),
            ("GETROLES_CHANNEL_ID", "Get-roles channel ID"),
            ("GENERAL_CHAT_CHANNEL_ID", "General chat channel ID"),
            ("OPEN_HUNTING_CHANNEL_ID", "Open hunting channel ID"),
            ("MOD_CHAT_CHANNEL_ID", "Mod chat channel ID"),
            ("PULLS_CHANNEL_ID", "#pulls channel ID"),
            ("SUCCESS_CHANNEL_ID", "#success channel ID"),
            ("MEE6_SILVER_ROLE_ID", "MEE6 Silver role ID"),
        ]
        for i, (key, label) in enumerate(optional_fields):
            row = ctk.CTkFrame(s6, fg_color="transparent")
            row.grid(row=2 + i, column=1, sticky="ew", padx=(0, 14), pady=(2, 0))
            ctk.CTkLabel(row, text=label, text_color=T.TEXT_MUTED, font=T.FONT_CAPTION,
                         width=200, anchor="w").pack(side="left")
            var = ctk.StringVar()
            self.id_vars[key] = var
            ctk.CTkEntry(row, textvariable=var, fg_color=T.SURFACE, border_color=T.BORDER,
                         text_color=T.TEXT).pack(side="left", fill="x", expand=True)
        # bottom padding for last field
        ctk.CTkFrame(s6, fg_color="transparent", height=8).grid(
            row=2 + len(optional_fields), column=1, sticky="ew", pady=(0, 14)
        )

        # ── Save bar ─────────────────────────────────────────────────────
        save_bar = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=0)
        save_bar.grid(row=3, column=0, sticky="ew", padx=0, pady=(12, 0))
        inner = ctk.CTkFrame(save_bar, fg_color="transparent")
        inner.pack(fill="x", padx=28, pady=14)
        self.save_status = ctk.CTkLabel(
            inner, text="Ready when you are — this saves permanently.",
            text_color=T.TEXT_MUTED, font=T.FONT_CAPTION,
        )
        self.save_status.pack(side="left")
        ctk.CTkButton(
            inner, text="Save & finish", height=42, width=180, corner_radius=10,
            fg_color=T.SUCCESS, hover_color="#2D8C4A", text_color="#FFFFFF",
            font=T.FONT_UI_BOLD, command=self._save_and_finish,
        ).pack(side="right")

    # ── actions ──────────────────────────────────────────────────────────

    def _skip(self) -> None:
        if self.on_skip_advanced:
            self.on_skip_advanced()

    def _toggle_token(self) -> None:
        if self.token_entry.cget("show") == "•":
            self.token_entry.configure(show="")
        else:
            self.token_entry.configure(show="•")

    def _check_token(self) -> None:
        token = self.token_var.get().strip()
        self.token_status.configure(text="Checking with Discord…", text_color=T.TEXT_MUTED)
        self.update_idletasks()
        ok, msg = validate_bot_token(token)
        self._validated = ok
        self.token_status.configure(
            text=msg, text_color=T.SUCCESS if ok else T.DANGER
        )
        if ok:
            self._bot_username = msg

    def _open_invite(self) -> None:
        app_id = self.app_id_var.get().strip()
        if not app_id.isdigit():
            self.invite_hint.configure(
                text="Paste the Application ID (step 2) first — it’s a long number.",
                text_color=T.WARNING,
            )
            open_url(PORTAL_APPS)
            return
        open_url(invite_url(app_id))
        self.invite_hint.configure(
            text="Invite page opened in your browser. Pick your server and Authorize.",
            text_color=T.SUCCESS,
        )

    def _save_and_finish(self) -> None:
        token = self.token_var.get().strip()
        guild = self.guild_var.get().strip()
        if not token:
            self.save_status.configure(
                text="Paste your bot token in step 2 first.", text_color=T.DANGER,
            )
            return
        if not guild.isdigit():
            self.save_status.configure(
                text="Server ID must be a long number (step 5).", text_color=T.DANGER,
            )
            return

        # Auto-validate if the user skipped Check token
        if not self._validated:
            self.save_status.configure(text="Checking token…", text_color=T.TEXT_MUTED)
            self.update_idletasks()
            ok, msg = validate_bot_token(token)
            if not ok:
                self.save_status.configure(text=msg, text_color=T.DANGER)
                return
            self._validated = True

        ids: dict[str, str] = {"GUILD_ID": guild}
        for key, var in self.id_vars.items():
            ids[key] = var.get().strip()
        if self.app_id_var.get().strip():
            # Not a required env field, but useful later
            pass

        self.save_status.configure(text="Saving…", text_color=T.TEXT_MUTED)
        self.update_idletasks()
        self.on_complete(token, ids)
