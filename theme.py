"""Пресеты тем Light/Dark + палитра выбора цветов."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Optional

@dataclass
class ThemeSettings:
    bg: str = "#f0f2f5"
    card_bg: str = "#ffffff"
    text: str = "#1d1d1f"
    muted: str = "#6e6e73"
    accent: str = "#0066cc"
    accent_hover: str = "#0052a3"
    button_hover: str = "#e4e6eb"
    preset: str = "light"

    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, d):
        s = cls()
        if not isinstance(d, dict): return s
        for k in ("bg","card_bg","text","muted","accent","accent_hover","button_hover","preset"):
            if k in d and isinstance(d[k], str): setattr(s, k, d[k])
        return s
    @classmethod
    def light_preset(cls):
        return cls(bg="#f0f2f5", card_bg="#ffffff", text="#1d1d1f", muted="#6e6e73",
                   accent="#0066cc", accent_hover="#0052a3", button_hover="#e4e6eb", preset="light")
    @classmethod
    def dark_preset(cls):
        return cls(bg="#1a1a1c", card_bg="#2c2c2e", text="#ffffff", muted="#8e8e93",
                   accent="#0a84ff", accent_hover="#409cff", button_hover="#3a3a3c", preset="dark")

def apply_theme(style, theme):
    bg, cb, tx, mt, ac = theme.bg, theme.card_bg, theme.text, theme.muted, theme.accent
    ah = getattr(theme, 'accent_hover', ac)
    bh = getattr(theme, 'button_hover', '#e4e6eb')
    style.configure("TFrame", background=bg)
    style.configure("Card.TFrame", background=cb, relief="flat", borderwidth=0)
    style.configure("TLabel", background=bg, foreground=tx, font=("Segoe UI", 10))
    style.configure("Title.TLabel", font=("Segoe UI Semibold", 18), foreground=tx, background=bg)
    style.configure("Subtitle.TLabel", font=("Segoe UI Semibold", 12), foreground=tx, background=bg)
    style.configure("Muted.TLabel", foreground=mt, font=("Segoe UI", 9), background=bg)
    style.configure("TButton", font=("Segoe UI", 10), background=cb, foreground=tx, relief="flat", padding=(12, 6))
    style.map("TButton", background=[("active", bh), ("pressed", bh), ("disabled", bg)], foreground=[("disabled", mt)])
    style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), background=ac, foreground="#ffffff", relief="flat", padding=(14, 7))
    style.map("Accent.TButton", background=[("active", ah), ("pressed", ah), ("disabled", "#9ca3af")], foreground=[("disabled", "#e5e7eb")])
    style.configure("Success.TButton", font=("Segoe UI Semibold", 10), background="#16a34a", foreground="#ffffff", relief="flat", padding=(14, 7))
    style.map("Success.TButton", background=[("active", "#15803d"), ("pressed", "#166534")])
    style.configure("TEntry", font=("Segoe UI", 11), fieldbackground=cb, foreground=tx, padding=4)
    style.map("TEntry", bordercolor=[("focus", ac)])
    style.configure("Treeview", rowheight=32, font=("Segoe UI", 10), background=cb, foreground=tx, fieldbackground=cb)
    style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", tx)])
    style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10),
                    background="#f3f4f6" if theme.preset == "light" else "#3a3a3c",
                    foreground=tx, relief="flat", padding=(8, 6))
    style.configure("TLabelframe", background=cb, relief="flat", borderwidth=0)
    style.configure("TLabelframe.Label", background=cb, foreground=tx, font=("Segoe UI Semibold", 11))
    style.configure("TScrollbar", background=bg, troughcolor=bg, arrowcolor=mt)
    style.map("TScrollbar", background=[("active", bh)])
    style.configure("TRadiobutton", background=bg, foreground=tx, font=("Segoe UI", 10))
    style.map("TRadiobutton", background=[("active", bg)])
    style.configure("TCheckbutton", background=bg, foreground=tx, font=("Segoe UI", 10))
    style.map("TCheckbutton", background=[("active", bg)])

def ask_color(parent, initial_color="#ffffff"):
    """Открыть системную палитру выбора цвета.

    Args:
        parent: родительское окно.
        initial_color: начальный цвет (hex).

    Returns:
        Выбранный цвет (hex) или None если отменено.
    """
    from tkinter import colorchooser
    result = colorchooser.askcolor(color=initial_color, parent=parent, title="Выберите цвет")
    if result and result[1]:
        return result[1]
    return None
