"""PokeHunt Controller — native desktop GUI for the Discord restock bot.

Login model (sticky by design):
  Bot tokens from the Discord Developer Portal do not expire unless you reset
  them. On first run the GUI saves the token to macOS Keychain, ~/.config/pokehunt,
  and the project .env — every subsequent launch loads them automatically.
  You only re-enter credentials if you click Reset or revoke the token.
"""

from __future__ import annotations

import json
import os
import sys
import tkinter as tk
from pathlib import Path
from typing import Any, Callable, Optional

import customtkinter as ctk
from tkinter import messagebox

from gui import credentials as creds
from gui import stats as stats_mod
from gui import theme as T
from gui.bot_manager import BotManager
from gui.setup_wizard import SetupWizard

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_JSON = PROJECT_ROOT / "config.json"
APP_TITLE = "PokeHunt Controller"


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_config() -> dict[str, Any]:
    if CONFIG_JSON.exists():
        try:
            return json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config(data: dict[str, Any]) -> None:
    CONFIG_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class StatusDot(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=T.TEXT_DIM, corner_radius=7, width=14, height=14, **kwargs)
        self.grid_propagate(False)
        self.configure(width=14, height=14)

    def set_color(self, color: str) -> None:
        self.configure(fg_color=color)


class StatCard(ctk.CTkFrame):
    def __init__(self, master, title: str, **kwargs):
        super().__init__(master, fg_color=T.SURFACE_2, corner_radius=T.RADIUS,
                         border_width=1, border_color=T.BORDER, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=title, text_color=T.TEXT_MUTED, font=T.FONT_CAPTION,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        self.value_label = ctk.CTkLabel(self, text="—", text_color=T.TEXT, font=T.FONT_STAT,
                                        anchor="w")
        self.value_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 14))

    def set_value(self, value: Any) -> None:
        self.value_label.configure(text=str(value))


class NavButton(ctk.CTkButton):
    def __init__(self, master, label: str, **kwargs):
        super().__init__(
            master, text=label, anchor="w", height=40, corner_radius=8,
            fg_color="transparent", hover_color=T.SURFACE_3,
            text_color=T.TEXT_MUTED, font=T.FONT_UI, **kwargs,
        )
        self._active = False

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self.configure(fg_color=T.ACCENT_SOFT, text_color=T.TEXT)
        else:
            self.configure(fg_color="transparent", text_color=T.TEXT_MUTED)


# ─────────────────────────────────────────────────────────────────────────────
# main app
# ─────────────────────────────────────────────────────────────────────────────

class PokeHuntApp(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        super().__init__(fg_color=T.BG)
        self.title(APP_TITLE)
        self.geometry("980x640")
        self.minsize(880, 560)
        self._center(980, 640)

        self.bot = BotManager()
        self.bot.add_listener(self._on_bot_event)
        self._page = "dashboard"
        self._nav_buttons: dict[str, NavButton] = {}
        self._status_colors = {
            "stopped": T.TEXT_DIM,
            "starting": T.WARNING,
            "running": T.SUCCESS,
            "stopping": T.WARNING,
            "failed": T.DANGER,
        }

        self._build_shell()
        self.after(200, self._boot)

    def _center(self, w: int, h: int) -> None:
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── shell ─────────────────────────────────────────────────────────────

    def _build_shell(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=0, width=T.SIDEBAR_W)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=16, pady=(20, 18))
        poke = ctk.CTkLabel(brand, text="◉", text_color=T.GOLD, font=("SF Pro Display", 22, "bold"))
        poke.pack(side="left")
        ctk.CTkLabel(brand, text="PokeHunt", text_color=T.TEXT, font=T.FONT_SECTION).pack(side="left", padx=(8, 0))

        nav_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav_frame.grid(row=1, column=0, sticky="ew", padx=12)
        for key, label in (
            ("dashboard", "Dashboard"),
            ("logs", "Logs"),
            ("settings", "Settings"),
            ("credentials", "Credentials"),
            ("setup", "Connect Discord"),
        ):
            btn = NavButton(nav_frame, label, command=lambda k=key: self.show_page(k))
            btn.pack(fill="x", pady=2)
            self._nav_buttons[key] = btn

        # Bottom status pill
        foot = ctk.CTkFrame(self.sidebar, fg_color=T.SURFACE_2, corner_radius=8)
        foot.grid(row=2, column=0, sticky="ew", padx=12, pady=16)
        self.sidebar_status_dot = StatusDot(foot)
        self.sidebar_status_dot.pack(side="left", padx=(10, 8), pady=10)
        self.sidebar_status_label = ctk.CTkLabel(
            foot, text="Stopped", text_color=T.TEXT_MUTED, font=T.FONT_CAPTION
        )
        self.sidebar_status_label.pack(side="left", pady=10)
        self.sidebar_creds_hint = ctk.CTkLabel(
            foot, text="Token saved once", text_color=T.TEXT_DIM, font=("SF Pro Text", 9)
        )
        self.sidebar_creds_hint.pack(side="bottom", padx=10, pady=(0, 8))

        # Main content host
        self.content = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self._pages: dict[str, ctk.CTkFrame] = {}
        self._build_dashboard()
        self._build_logs()
        self._build_settings()
        self._build_credentials()
        self._build_setup_wizard()
        self.show_page("dashboard")

    def _page_frame(self, key: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.content, fg_color=T.BG, corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew")
        self._pages[key] = frame
        return frame

    def show_page(self, key: str) -> None:
        self._page = key
        for name, frame in self._pages.items():
            if name == key:
                frame.tkraise()
            # keep all gridded; raise only
        for name, btn in self._nav_buttons.items():
            btn.set_active(name == key)
        if key == "dashboard":
            self._refresh_stats()
        if key == "credentials":
            self._refresh_credentials_page()

    # ── dashboard ─────────────────────────────────────────────────────────

    def _build_dashboard(self) -> None:
        page = self._page_frame("dashboard")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 8))
        ctk.CTkLabel(header, text="Dashboard", text_color=T.TEXT, font=T.FONT_TITLE).pack(side="left")
        self.conn_badge = ctk.CTkLabel(
            header, text="  Offline  ", text_color=T.TEXT_DIM, font=T.FONT_CAPTION,
            fg_color=T.SURFACE_2, corner_radius=6
        )
        self.conn_badge.pack(side="right", ipady=4, ipadx=8)

        # Hero status card
        hero = ctk.CTkFrame(page, fg_color=T.SURFACE, corner_radius=T.RADIUS,
                            border_width=1, border_color=T.BORDER)
        hero.grid(row=1, column=0, sticky="ew", padx=28, pady=(8, 12))
        hero.grid_columnconfigure(1, weight=1)

        self.hero_dot = StatusDot(hero)
        self.hero_dot.grid(row=0, column=0, rowspan=2, padx=(20, 12), pady=20)
        self.hero_title = ctk.CTkLabel(hero, text="Bot is stopped", text_color=T.TEXT, font=T.FONT_SECTION, anchor="w")
        self.hero_title.grid(row=0, column=1, sticky="w", pady=(18, 0))
        self.hero_sub = ctk.CTkLabel(
            hero,
            text="Credentials are stored permanently — no Discord re-login needed.",
            text_color=T.TEXT_MUTED, font=T.FONT_UI, anchor="w",
        )
        self.hero_sub.grid(row=1, column=1, sticky="w", pady=(2, 18))

        btns = ctk.CTkFrame(hero, fg_color="transparent")
        btns.grid(row=0, column=2, rowspan=2, padx=16, pady=16)
        self.connect_btn = ctk.CTkButton(
            btns, text="Connect Discord", width=140, height=36, corner_radius=8,
            fg_color=T.GOLD, hover_color="#FFD84D", text_color="#1A1400",
            font=T.FONT_UI_BOLD, command=lambda: self.show_page("setup"),
        )
        self.connect_btn.pack(side="left", padx=4)
        self.start_btn = ctk.CTkButton(
            btns, text="Start Bot", width=110, height=36, corner_radius=8,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, text_color="#FFFFFF",
            font=T.FONT_UI_BOLD, command=self._on_start,
        )
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = ctk.CTkButton(
            btns, text="Stop", width=80, height=36, corner_radius=8,
            fg_color=T.SURFACE_3, hover_color=T.BORDER, text_color=T.TEXT,
            font=T.FONT_UI, command=self._on_stop, state="disabled",
        )
        self.stop_btn.pack(side="left", padx=4)
        self.restart_btn = ctk.CTkButton(
            btns, text="Restart", width=90, height=36, corner_radius=8,
            fg_color=T.SURFACE_3, hover_color=T.BORDER, text_color=T.TEXT,
            font=T.FONT_UI, command=self._on_restart, state="disabled",
        )
        self.restart_btn.pack(side="left", padx=4)

        # Stats row
        stats_row = ctk.CTkFrame(page, fg_color="transparent")
        stats_row.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 8))
        for i in range(4):
            stats_row.grid_columnconfigure(i, weight=1, uniform="stat")
        self.card_pings = StatCard(stats_row, "Pings (10 days)")
        self.card_pings.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.card_hunters = StatCard(stats_row, "Hunters earned")
        self.card_hunters.grid(row=0, column=1, sticky="nsew", padx=4)
        self.card_media = StatCard(stats_row, "Media (10 days)")
        self.card_media.grid(row=0, column=2, sticky="nsew", padx=4)
        self.card_chat = StatCard(stats_row, "Chat (7 days)")
        self.card_chat.grid(row=0, column=3, sticky="nsew", padx=(8, 0))

        # Bottom split: top stores + recent
        bottom = ctk.CTkFrame(page, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="nsew", padx=28, pady=(8, 24))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)
        bottom.grid_rowconfigure(0, weight=1)

        stores_card = ctk.CTkFrame(bottom, fg_color=T.SURFACE, corner_radius=T.RADIUS,
                                   border_width=1, border_color=T.BORDER)
        stores_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(stores_card, text="Top stores", text_color=T.TEXT, font=T.FONT_SECTION,
                     anchor="w").pack(fill="x", padx=16, pady=(14, 6))
        self.stores_box = ctk.CTkTextbox(
            stores_card, fg_color=T.SURFACE_2, text_color=T.TEXT_MUTED,
            font=T.FONT_MONO, height=160, border_width=1, border_color=T.BORDER_SOFT,
        )
        self.stores_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.stores_box.configure(state="disabled")

        recent_card = ctk.CTkFrame(bottom, fg_color=T.SURFACE, corner_radius=T.RADIUS,
                                   border_width=1, border_color=T.BORDER)
        recent_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(recent_card, text="Recent pings", text_color=T.TEXT, font=T.FONT_SECTION,
                     anchor="w").pack(fill="x", padx=16, pady=(14, 6))
        self.recent_box = ctk.CTkTextbox(
            recent_card, fg_color=T.SURFACE_2, text_color=T.TEXT_MUTED,
            font=T.FONT_MONO, height=160, border_width=1, border_color=T.BORDER_SOFT,
        )
        self.recent_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.recent_box.configure(state="disabled")

    def _refresh_stats(self) -> None:
        s = stats_mod.fetch_dashboard_stats()
        self.card_pings.set_value(s["pings_10d"] if s["db_exists"] else "—")
        self.card_hunters.set_value(s["hunters_earned"] if s["db_exists"] else "—")
        self.card_media.set_value(s["media_10d"] if s["db_exists"] else "—")
        self.card_chat.set_value(s["chat_7d"] if s["db_exists"] else "—")

        self.stores_box.configure(state="normal")
        self.stores_box.delete("1.0", "end")
        if s["top_stores"]:
            for store, count in s["top_stores"]:
                self.stores_box.insert("end", f"{store:<32} {count:>4}\n")
        else:
            self.stores_box.insert("end", "No ping data yet.\nStart the bot and wait for activity.")
        self.stores_box.configure(state="disabled")

        self.recent_box.configure(state="normal")
        self.recent_box.delete("1.0", "end")
        if s["recent_pings"]:
            for row in s["recent_pings"]:
                store = (row.get("store") or "?")[:18]
                mtype = row.get("mention_type") or ""
                loc = row.get("location") or ""
                ts = (row.get("timestamp") or "")[:16].replace("T", " ")
                self.recent_box.insert("end", f"{ts}  {store:<18} {mtype:<8} {loc}\n")
        else:
            self.recent_box.insert("end", "No recent pings recorded.")
        self.recent_box.configure(state="disabled")

    # ── logs ──────────────────────────────────────────────────────────────

    def _build_logs(self) -> None:
        page = self._page_frame("logs")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 8))
        ctk.CTkLabel(header, text="Live logs", text_color=T.TEXT, font=T.FONT_TITLE).pack(side="left")
        ctk.CTkButton(
            header, text="Clear", width=80, height=32, fg_color=T.SURFACE_3,
            hover_color=T.BORDER, text_color=T.TEXT, command=self.bot.clear_logs,
        ).pack(side="right")

        self.log_box = ctk.CTkTextbox(
            page, fg_color=T.SURFACE, text_color=T.TEXT_MUTED, font=T.FONT_MONO,
            border_width=1, border_color=T.BORDER, corner_radius=T.RADIUS,
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=28, pady=(8, 24))
        self.log_box.configure(state="disabled")

    def _append_logs_ui(self) -> None:
        if self._page != "logs" and not self.winfo_exists():
            return
        lines = self.bot.get_logs(limit=250)
        if not hasattr(self, "log_box"):
            return
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        for line in lines:
            prefix = {"out": "", "err": "! ", "sys": "» "}.get(line.stream, "")
            self.log_box.insert("end", f"{prefix}{line.text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ── settings ──────────────────────────────────────────────────────────

    def _build_settings(self) -> None:
        page = self._page_frame("settings")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 8))
        ctk.CTkLabel(header, text="Bot settings", text_color=T.TEXT, font=T.FONT_TITLE).pack(side="left")
        self.settings_saved = ctk.CTkLabel(header, text="", text_color=T.SUCCESS, font=T.FONT_CAPTION)
        self.settings_saved.pack(side="right")

        body = ctk.CTkScrollableFrame(page, fg_color=T.SURFACE, corner_radius=T.RADIUS,
                                      border_width=1, border_color=T.BORDER)
        body.grid(row=1, column=0, sticky="nsew", padx=28, pady=(8, 24))

        self._config = _load_config()
        self._settings_vars: dict[str, tk.Variable] = {}

        editable = [
            ("pings_to_gain", "Pings required to earn Hunter", "int"),
            ("pings_to_maintain", "Pings to maintain (window)", "int"),
            ("maintenance_window_days", "Maintenance window (days)", "int"),
            ("media_to_maintain", "Media posts to maintain", "int"),
            ("chat_to_maintain", "Chat messages to maintain", "int"),
            ("chat_window_days", "Chat window (days)", "int"),
            ("mee6_level_threshold", "MEE6 level threshold", "int"),
            ("messages_to_gain", "Messages to gain", "int"),
            ("daily_maintenance_hour", "Daily maintenance hour (UTC)", "int"),
            ("daily_maintenance_minute", "Daily maintenance minute", "int"),
            ("pokemon_hunter_role_name", "Hunter role name", "str"),
            ("pokemon_trainer_role_name", "Trainer role name", "str"),
            ("admin_role_name", "Admin role name", "str"),
            ("mod_role_name", "Moderator role name", "str"),
            ("ping_leaderboard_size", "Leaderboard size", "int"),
        ]

        for i, (key, label, kind) in enumerate(editable):
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=6, padx=12)
            ctk.CTkLabel(row, text=label, text_color=T.TEXT_MUTED, font=T.FONT_UI, width=240,
                         anchor="w").pack(side="left")
            var = tk.StringVar(value=str(self._config.get(key, "")))
            entry = ctk.CTkEntry(row, textvariable=var, width=220, fg_color=T.SURFACE_2,
                                 border_color=T.BORDER, text_color=T.TEXT)
            entry.pack(side="right")
            self._settings_vars[key] = (var, kind)

        save_row = ctk.CTkFrame(body, fg_color="transparent")
        save_row.pack(fill="x", pady=16, padx=12)
        ctk.CTkButton(
            save_row, text="Save settings", width=140, height=36, fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER, text_color="#FFFFFF", font=T.FONT_UI_BOLD,
            command=self._save_settings,
        ).pack(side="left")

    def _save_settings(self) -> None:
        cfg = _load_config()
        for key, (var, kind) in self._settings_vars.items():
            raw = var.get().strip()
            if kind == "int":
                try:
                    cfg[key] = int(raw)
                except ValueError:
                    continue
            else:
                cfg[key] = raw
        _save_config(cfg)
        self.settings_saved.configure(text="Saved")
        self.after(2000, lambda: self.settings_saved.configure(text=""))

    # ── credentials ───────────────────────────────────────────────────────

    def _build_credentials(self) -> None:
        page = self._page_frame("credentials")
        page.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 8))
        ctk.CTkLabel(header, text="Credentials", text_color=T.TEXT, font=T.FONT_TITLE).pack(side="left")
        ctk.CTkButton(
            header, text="Guided setup wizard", height=32, fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER, text_color="#FFFFFF", font=T.FONT_UI_BOLD,
            command=lambda: self.show_page("setup"),
        ).pack(side="right")

        note = ctk.CTkLabel(
            page,
            text=(
                "Discord bot tokens do not expire unless you reset them in the Developer Portal.\n"
                "Save once here — Keychain + ~/.config/pokehunt + project .env — and you will never need to log in again.\n"
                "Not sure how to get a token? Use the Guided setup wizard."
            ),
            text_color=T.TEXT_MUTED, font=T.FONT_UI, justify="left", anchor="w",
        )
        note.grid(row=1, column=0, sticky="ew", padx=28, pady=(4, 12))

        status_card = ctk.CTkFrame(page, fg_color=T.SURFACE, corner_radius=T.RADIUS,
                                   border_width=1, border_color=T.BORDER)
        status_card.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 12))
        self.creds_summary = ctk.CTkTextbox(
            status_card, fg_color=T.SURFACE_2, text_color=T.TEXT_MUTED, font=T.FONT_MONO,
            height=110, border_width=1, border_color=T.BORDER_SOFT,
        )
        self.creds_summary.pack(fill="x", padx=16, pady=16)

        form = ctk.CTkScrollableFrame(page, fg_color=T.SURFACE, corner_radius=T.RADIUS,
                                      border_width=1, border_color=T.BORDER)
        form.grid(row=3, column=0, sticky="nsew", padx=28, pady=(0, 12))
        page.grid_rowconfigure(3, weight=1)

        current = creds.load_credentials()

        ctk.CTkLabel(form, text="Discord Bot Token", text_color=T.TEXT, font=T.FONT_UI_BOLD,
                     anchor="w").pack(fill="x", padx=12, pady=(12, 2))
        token_row = ctk.CTkFrame(form, fg_color="transparent")
        token_row.pack(fill="x", padx=12, pady=(0, 8))
        self.token_var = tk.StringVar(value="")
        self.token_entry = ctk.CTkEntry(
            token_row, textvariable=self.token_var, show="•", width=420,
            fg_color=T.SURFACE_2, border_color=T.BORDER, text_color=T.TEXT,
            placeholder_text="Paste your bot token (saved permanently)",
        )
        self.token_entry.pack(side="left", fill="x", expand=True)
        self.show_token_btn = ctk.CTkButton(
            token_row, text="Show", width=70, height=32, fg_color=T.SURFACE_3,
            hover_color=T.BORDER, text_color=T.TEXT, command=self._toggle_token_visibility,
        )
        self.show_token_btn.pack(side="left", padx=(8, 0))

        fields = [
            ("GUILD_ID", "Server (Guild) ID", True),
            ("POKEMON_HUNTER_ROLE_ID", "Pokemon Hunter role ID", False),
            ("POKEMON_TRAINER_ROLE_ID", "Pokemon Trainer role ID", False),
            ("ADMIN_ROLE_ID", "Admin role ID", False),
            ("MOD_ROLE_ID", "Moderator role ID", False),
            ("ANNOUNCEMENTS_CHANNEL_ID", "Announcements channel ID", False),
            ("GETROLES_CHANNEL_ID", "Get-roles channel ID", False),
            ("GENERAL_CHAT_CHANNEL_ID", "General chat channel ID", False),
            ("OPEN_HUNTING_CHANNEL_ID", "Open hunting channel ID", False),
            ("MOD_CHAT_CHANNEL_ID", "Mod chat channel ID", False),
            ("PULLS_CHANNEL_ID", "#pulls channel ID", False),
            ("SUCCESS_CHANNEL_ID", "#success channel ID", False),
            ("MEE6_SILVER_ROLE_ID", "MEE6 Silver role ID", False),
        ]
        self.id_vars: dict[str, tk.StringVar] = {}
        for key, label, required in fields:
            ctk.CTkLabel(form, text=label + (" *" if required else ""), text_color=T.TEXT_MUTED,
                         font=T.FONT_UI, anchor="w").pack(fill="x", padx=12, pady=(8, 0))
            var = tk.StringVar(value=current.get(key, ""))
            self.id_vars[key] = var
            ctk.CTkEntry(form, textvariable=var, fg_color=T.SURFACE_2, border_color=T.BORDER,
                         text_color=T.TEXT).pack(fill="x", padx=12, pady=(2, 0))

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=28, pady=(4, 24))
        ctk.CTkButton(
            actions, text="Save credentials (remember forever)", height=40,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, text_color="#FFFFFF",
            font=T.FONT_UI_BOLD, command=self._save_creds_from_form,
        ).pack(side="left")
        ctk.CTkButton(
            actions, text="Validate token", height=40, width=130,
            fg_color=T.SURFACE_3, hover_color=T.BORDER, text_color=T.TEXT,
            command=self._validate_token,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            actions, text="Reset saved login", height=40, width=130,
            fg_color=T.DANGER_SOFT, hover_color=T.DANGER, text_color=T.TEXT,
            command=self._reset_creds,
        ).pack(side="right")

        self.creds_status = ctk.CTkLabel(page, text="", text_color=T.TEXT_MUTED, font=T.FONT_CAPTION)
        self.creds_status.grid(row=5, column=0, sticky="w", padx=28, pady=(0, 16))

    def _refresh_credentials_page(self) -> None:
        summary = creds.credentials_summary()
        text = (
            f"Status:     {summary['ready']}\n"
            f"Token:      {summary['token_masked']}\n"
            f"Guild ID:   {summary['guild_id']}\n"
            f"Hunter role:{summary['hunter_role']}\n"
            f"Storage:    {summary['storage']}"
        )
        self.creds_summary.configure(state="normal")
        self.creds_summary.delete("1.0", "end")
        self.creds_summary.insert("1.0", text)
        self.creds_summary.configure(state="disabled")

        current = creds.load_credentials()
        for key, var in self.id_vars.items():
            if not var.get():
                var.set(current.get(key, ""))

    def _toggle_token_visibility(self) -> None:
        if self.token_entry.cget("show") == "•":
            self.token_entry.configure(show="")
            self.show_token_btn.configure(text="Hide")
        else:
            self.token_entry.configure(show="•")
            self.show_token_btn.configure(text="Show")

    def _save_creds_from_form(self) -> None:
        token = self.token_var.get().strip()
        existing = creds.load_credentials()
        if not token:
            # Keep previously saved token if user left the field blank
            token = existing.get("DISCORD_TOKEN") or ""
        guild = self.id_vars["GUILD_ID"].get().strip()
        if not token:
            self.creds_status.configure(text="Enter a bot token first.", text_color=T.DANGER)
            return
        if not guild:
            self.creds_status.configure(text="Guild ID is required.", text_color=T.DANGER)
            return
        ids = {k: v.get().strip() for k, v in self.id_vars.items()}
        saved = creds.save_credentials(token, ids)
        self.token_var.set("")
        self.token_entry.configure(show="•")
        self.show_token_btn.configure(text="Show")
        self.creds_status.configure(
            text=f"Saved permanently · token {saved.get('DISCORD_TOKEN','')[:6]}… · Keychain + ~/.config/pokehunt + .env",
            text_color=T.SUCCESS,
        )
        self._refresh_credentials_page()
        self._update_hero_for_creds()

    def _validate_token(self) -> None:
        token = self.token_var.get().strip() or (creds.load_credentials().get("DISCORD_TOKEN") or "")
        if not token:
            self.creds_status.configure(text="No token to validate.", text_color=T.DANGER)
            return
        self.creds_status.configure(text="Validating with Discord…", text_color=T.TEXT_MUTED)
        self.update_idletasks()
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bot {token}", "User-Agent": "PokeHuntController/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            name = body.get("username") or body.get("id") or "bot"
            self.creds_status.configure(
                text=f"Token valid — logged in as {name}#{body.get('discriminator','0') if body.get('discriminator') not in (None,'0') else ''}".strip(),
                text_color=T.SUCCESS,
            )
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                self.creds_status.configure(
                    text="Token rejected by Discord. Copy a fresh token from the Developer Portal.",
                    text_color=T.DANGER,
                )
            else:
                self.creds_status.configure(text=f"Discord API error HTTP {exc.code}", text_color=T.WARNING)
        except Exception as exc:  # network / timeout
            self.creds_status.configure(text=f"Could not reach Discord: {exc}", text_color=T.WARNING)

    def _reset_creds(self) -> None:
        if not messagebox.askyesno(
            "Reset login",
            "Delete the saved bot token and IDs?\nYou will need to paste them again on next start.",
        ):
            return
        creds.clear_credentials()
        self.token_var.set("")
        for var in self.id_vars.values():
            var.set("")
        self.creds_status.configure(text="Saved login cleared.", text_color=T.WARNING)
        self._refresh_credentials_page()
        self._update_hero_for_creds()

    # ── setup wizard ─────────────────────────────────────────────────────

    def _build_setup_wizard(self) -> None:
        page = self._page_frame("setup")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        self.wizard = SetupWizard(
            page,
            on_complete=self._on_wizard_complete,
            on_skip_advanced=lambda: self.show_page("credentials"),
        )
        self.wizard.grid(row=0, column=0, sticky="nsew")

    def _on_wizard_complete(self, token: str, ids: dict[str, str]) -> None:
        saved = creds.save_credentials(token, ids)
        # Sync form fields
        self.token_var.set("")
        for key, var in self.id_vars.items():
            var.set(saved.get(key, ""))
        self._refresh_credentials_page()
        self._update_hero_for_creds()
        self.show_page("dashboard")
        self.hero_sub.configure(
            text="Discord connected. Login saved permanently — press Start Bot."
        )
        self.hero_dot.set_color(T.SUCCESS)

    # ── bot actions ───────────────────────────────────────────────────────

    def _on_start(self) -> None:
        saved = creds.load_credentials()
        if not saved.get("_has_credentials"):
            self.show_page("setup")
            return
        self.bot.start(env_overrides={k: v for k, v in saved.items() if k in creds.ID_FIELDS or k == "DISCORD_TOKEN"})

    def _on_stop(self) -> None:
        self.bot.stop()

    def _on_restart(self) -> None:
        saved = creds.load_credentials()
        self.bot.restart(env_overrides={k: v for k, v in saved.items() if k in creds.ID_FIELDS or k == "DISCORD_TOKEN"})

    def _on_bot_event(self, event: str) -> None:
        # Called from worker threads — marshal to UI thread
        try:
            self.after(0, self._handle_bot_event, event)
        except Exception:
            pass

    def _handle_bot_event(self, event: str) -> None:
        if event == "log":
            self._append_logs_ui()
        elif event == "status":
            self._apply_status_ui()

    def _apply_status_ui(self) -> None:
        status = self.bot.status
        color = self._status_colors.get(status, T.TEXT_DIM)
        self.sidebar_status_dot.set_color(color)
        self.hero_dot.set_color(color)
        labels = {
            "stopped": "Stopped",
            "starting": "Starting…",
            "running": "Running",
            "stopping": "Stopping…",
            "failed": "Failed",
        }
        self.sidebar_status_label.configure(text=labels.get(status, status.title()))

        titles = {
            "stopped": "Bot is stopped",
            "starting": "Connecting to Discord…",
            "running": "Bot is online",
            "stopping": "Shutting down…",
            "failed": "Bot failed to start",
        }
        self.hero_title.configure(text=titles.get(status, status.title()))

        if status == "running":
            self.hero_sub.configure(text="Tracking pings, media, and chat. Token reused from Keychain — no re-login.")
            self.conn_badge.configure(text="  Online  ", text_color=T.SUCCESS, fg_color=T.SUCCESS_SOFT)
        elif status == "failed":
            err = self.bot.last_error or "See Logs for details."
            self.hero_sub.configure(text=err)
            self.conn_badge.configure(text="  Failed  ", text_color=T.DANGER, fg_color=T.DANGER_SOFT)
        elif status == "starting":
            self.hero_sub.configure(text="Handshake with Discord gateway…")
            self.conn_badge.configure(text="  Connecting  ", text_color=T.WARNING, fg_color=T.WARNING_SOFT)
        else:
            if creds.has_sticky_credentials():
                self.hero_sub.configure(text="Credentials are stored permanently — no Discord re-login needed.")
            else:
                self.hero_title.configure(text="Connect Discord to get started")
                self.hero_sub.configure(text="Use Connect Discord to grab your bot token in a few clicks.")
            self.conn_badge.configure(text="  Offline  ", text_color=T.TEXT_DIM, fg_color=T.SURFACE_2)

        running = self.bot.is_running()
        has_creds = bool(creds.has_sticky_credentials())
        if has_creds:
            self.connect_btn.pack_forget()
            if not self.start_btn.winfo_ismapped():
                self.start_btn.pack(side="left", padx=4)
        else:
            if not self.connect_btn.winfo_ismapped():
                self.connect_btn.pack(side="left", padx=4)
            self.start_btn.pack_forget()
        self.start_btn.configure(state="disabled" if running or status == "starting" or not has_creds else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")
        self.restart_btn.configure(state="normal" if running else "disabled")

    def _update_hero_for_creds(self) -> None:
        if self.bot.is_running():
            return
        summary = creds.credentials_summary()
        if summary["ready"].startswith("Yes"):
            self.hero_sub.configure(text="Credentials saved — press Start Bot. Login sticks across launches.")
            if hasattr(self, "sidebar_creds_hint"):
                self.sidebar_creds_hint.configure(text="Login saved permanently")
        else:
            self.hero_sub.configure(text="Use Connect Discord to grab your bot token in a few clicks.")
            if hasattr(self, "sidebar_creds_hint"):
                self.sidebar_creds_hint.configure(text="Setup required")

    # ── boot / close ──────────────────────────────────────────────────────

    def _boot(self) -> None:
        self._apply_status_ui()
        self._refresh_stats()
        self._refresh_credentials_page()
        if not creds.has_sticky_credentials():
            self.show_page("setup")
        else:
            self._update_hero_for_creds()
        # Periodic refresh
        self.after(4000, self._tick)

    def _tick(self) -> None:
        try:
            if self._page == "dashboard":
                self._refresh_stats()
            self._apply_status_ui()
        except Exception:
            pass
        self.after(4000, self._tick)

    def on_close(self) -> None:
        if self.bot.is_running():
            if not messagebox.askyesno(
                "Quit PokeHunt",
                "The Discord bot is still running.\nStop it and quit?",
            ):
                return
            self.bot.stop(timeout=5)
        self.destroy()


def main() -> None:
    # Allow `python -m gui` from project root
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    app = PokeHuntApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
