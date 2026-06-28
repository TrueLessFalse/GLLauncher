"""Обучение пользователя с подсветкой полей."""
from __future__ import annotations
import platform, tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

class Step:
    def __init__(self, title, description, target_getter, hint=""):
        self.title = title; self.description = description; self.target_getter = target_getter; self.hint = hint

class HighlightOverlay:
    def __init__(self, root):
        self.root = root; self.windows = []
    def highlight(self, widget):
        self.clear()
        if not widget: return
        widget.update_idletasks(); self.root.update_idletasks()
        try: x = widget.winfo_rootx(); y = widget.winfo_rooty(); w = widget.winfo_width(); h = widget.winfo_height()
        except: return
        if w <= 1 or h <= 1: return
        t = 4; c = "#ffb300"
        for bx, by, bw, bh in [(x-t, y-t, w+2*t, t), (x-t, y+h, w+2*t, t), (x-t, y, t, h), (x+w, y, t, h)]:
            if bw <= 0 or bh <= 0: continue
            win = tk.Toplevel(self.root); win.overrideredirect(True); win.geometry(f"{bw}x{bh}+{bx}+{by}")
            win.attributes("-topmost", True)
            if platform.system() == "Windows":
                try: win.attributes("-disabled", True)
                except: pass
            try: win.configure(background=c, highlightthickness=0)
            except: pass
            self.windows.append(win)
    def clear(self):
        for w in self.windows:
            try: w.destroy()
            except: pass
        self.windows = []

class TourDialog(tk.Toplevel):
    def __init__(self, parent, steps, on_complete=None, on_skip=None):
        super().__init__(parent)
        self.steps = steps; self.current = 0; self.on_complete = on_complete; self.on_skip = on_skip
        self.title("Обучение"); self.geometry("440x300"); self.minsize(400, 260)
        self.transient(parent)
        self.highlight = HighlightOverlay(parent)
        self._build_ui(); self._show_step()
        self.protocol("WM_DELETE_WINDOW", self._on_skip)
        self.after(50, self._position)
    def _build_ui(self):
        c = ttk.Frame(self, padding=16); c.pack(fill=tk.BOTH, expand=True)
        c.columnconfigure(0, weight=1); c.rowconfigure(2, weight=1)
        self.sl = ttk.Label(c, text="", style="Muted.TLabel"); self.sl.grid(row=0, column=0, sticky="w")
        self.tl = ttk.Label(c, text="", style="Title.TLabel", font=("Segoe UI Semibold", 14)); self.tl.grid(row=1, column=0, sticky="w", pady=(4, 8))
        self.dt = tk.Text(c, wrap="word", height=8, font=("Segoe UI", 10), bg=self.cget("bg"), relief="flat", padx=0, pady=0, highlightthickness=0, cursor="arrow"); self.dt.grid(row=2, column=0, sticky="nsew")
        self.dt.configure(state="disabled")
        self.hl = ttk.Label(c, text="", style="Muted.TLabel"); self.hl.grid(row=3, column=0, sticky="w", pady=(8, 0))
        br = ttk.Frame(c); br.grid(row=4, column=0, sticky="ew", pady=(12, 0)); br.columnconfigure(1, weight=1)
        ttk.Button(br, text="Пропустить", command=self._on_skip).grid(row=0, column=0, sticky="w")
        self.pb = ttk.Button(br, text="← Назад", command=self._prev); self.pb.grid(row=0, column=1, sticky="e", padx=(0, 4))
        self.nb = ttk.Button(br, text="Далее →", style="Accent.TButton", command=self._next); self.nb.grid(row=0, column=2, sticky="e")
    def _position(self):
        try:
            self.update_idletasks(); sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
            self.geometry(f"+{sw-self.winfo_width()-30}+{sh-self.winfo_height()-60}")
        except: pass
    def _show_step(self):
        if self.current >= len(self.steps): self._on_complete(); return
        if self.current < 0: self.current = 0
        s = self.steps[self.current]
        self.sl.configure(text=f"Шаг {self.current+1} из {len(self.steps)}")
        self.tl.configure(text=s.title)
        self.dt.configure(state="normal"); self.dt.delete("1.0", tk.END); self.dt.insert("1.0", s.description); self.dt.configure(state="disabled")
        self.hl.configure(text=f"💡 {s.hint}" if s.hint else "")
        try:
            t = s.target_getter()
            if t: self.highlight.highlight(t)
            else: self.highlight.clear()
        except: self.highlight.clear()
        self.pb.configure(state="normal" if self.current > 0 else "disabled")
        self.nb.configure(text="✓ Завершить" if self.current == len(self.steps)-1 else "Далее →")
    def _next(self):
        if self.current >= len(self.steps)-1: self._on_complete(); return
        self.current += 1; self._show_step()
    def _prev(self):
        if self.current > 0: self.current -= 1; self._show_step()
    def _on_complete(self):
        self.highlight.clear()
        if self.on_complete:
            try: self.on_complete()
            except: pass
        self.destroy()
    def _on_skip(self):
        self.highlight.clear()
        if self.on_skip:
            try: self.on_skip()
            except: pass
        self.destroy()

def create_app_tour(app):
    steps = [
        Step("Укажите папку NormalMode", "Скачайте GreenLuma 2026 и распакуйте. В настройках укажите папку NormalMode.", lambda: getattr(app, "auto_setup_btn", None), "⚙ Настройки → Пути → NormalMode"),
        Step("Укажите папку AppList", "AppList — где лежат 0.txt, 1.txt с appid. Укажите или создайте в настройках.", lambda: getattr(app, "auto_setup_btn", None), "⚙ Настройки → Пути → AppList"),
        Step("Автонастройка GreenLuma", "Нажмите «🔧 Автонастройка» — приложение само найдёт Steam.exe и настроит DLLInjector.ini.", lambda: getattr(app, "auto_setup_btn", None), "Нажмите «🔧 Автонастройка»"),
        Step("Найдите игры", "Введите название и нажмите «Найти». Поиск в RU и US одновременно.", lambda: getattr(app, "search_btn", None), "Введите название → «Найти»"),
        Step("Добавьте в список", "Выберите игру → «＋ В список». Двойной клик — страница DLC.", lambda: getattr(app, "add_selected_btn", None), "Выберите → «＋ В список»"),
        Step("Запустите GreenLuma", "Список автоэкспортируется в AppList. Нажмите «🚀 Запустить».", lambda: getattr(app, "launch_btn", None), "Нажмите «🚀 Запустить GreenLuma»"),
        Step("Готово!", "Теперь вы знаете всё. Обучение можно повторить через «❓ Обучение».", lambda: None, "Нажмите «✓ Завершить»"),
    ]
    return TourDialog(parent=app.root, steps=steps, on_complete=lambda: _mark(app), on_skip=lambda: _mark(app))

def _mark(app):
    try: app.settings.tutorial_completed = True; app.settings.save()
    except: pass
