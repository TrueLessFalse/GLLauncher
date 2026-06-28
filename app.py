"""GLLauncher — главное приложение."""
from __future__ import annotations
import logging, os, platform, queue, sys, threading, tkinter as tk, webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

try:
    from PIL import Image, ImageTk
    _PIL = True
except ImportError:
    _PIL = False

import steam_api
from applist_io import ScanResult, clear_applist_txt_files, scan_applist_dir
from config import (DEFAULT_UPDATE_URL, Settings, find_dll_injector, find_steam_exe, resolve_normalmode_dir, settings_file_path, state_file_path, log_file_path, is_portable_mode)
from download_list import DownloadItem, DownloadList
from greenluma import LaunchResult, launch_greenluma
from greenluma_setup import CheckResult, SetupResult, check_greenluma_setup, open_applist_manager, setup_greenluma
from image_cache import ImageCache
from theme import ThemeSettings, apply_theme
from tutorial import create_app_tour
from updater import UpdateInfo, check_for_updates, open_topic_in_browser
from app_updater import APP_VERSION, AppUpdateInfo, check_for_app_updates, download_and_install_update, open_download_page

APP_TITLE = "GLLauncher — поиск игр и DLC Steam"

def _setup_crash_logging():
    import traceback
    def hook(t, v, tb):
        try:
            from config import log_file_path as _lp; lp = _lp()
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            with open(lp, "a", encoding="utf-8") as f:
                f.write(f"\n=== Crash at {__import__('datetime').datetime.now()} ===\n")
                f.write("".join(traceback.format_exception(t, v, tb)))
        except: pass
        try: traceback.print_exception(t, v, tb)
        except: pass
        try:
            from tkinter import messagebox as _mb
            _mb.showerror(APP_TITLE, f"Ошибка:\n\n{t.__name__}: {v}\n\nЛог: {lp}")
        except: pass
    sys.excepthook = hook

class SteamListerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1320x820"); self.root.minsize(980, 640)
        self.settings = Settings.load()
        self._setup_style()
        self.download_list = DownloadList()
        self.download_list.add_listener(self._on_download_list_changed)
        self.image_cache = ImageCache()
        self._ui_queue = queue.Queue()
        self.root.after(100, self._drain_ui_queue)
        self._search_results = []
        self._search_thread = None
        self._dlc_threads = {}
        self._import_thread = None
        self._launch_thread = None
        self._results_sort_state = ("name", False)
        self.download_list.load_from_file(state_file_path())
        self._build_ui()
        self._apply_theme_to_widgets()
        self._refresh_paths_display()
        self._update_status()
        self._restore_window_geometry()
        self._setup_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        if not self.settings.tutorial_completed:
            self.root.after(800, self._on_show_tutorial)
        self.root.after(5000, lambda: self._check_updates_background(False))

    def _setup_style(self):
        style = ttk.Style()
        try: style.theme_use("clam")
        except: pass
        if self.settings.theme_settings:
            self.theme = ThemeSettings.from_dict(self.settings.theme_settings)
        else:
            self.theme = ThemeSettings.light_preset()
        apply_theme(style, self.theme)

    def _apply_theme_to_widgets(self):
        if hasattr(self, 'dl_listbox'):
            try: self.dl_listbox.config(bg=self.theme.card_bg, fg=self.theme.text, selectbackground=self.theme.accent, selectforeground="#ffffff")
            except: pass

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=14); main.pack(fill=tk.BOTH, expand=True)
        self.main_frame = main
        main.columnconfigure(0, weight=3, uniform="cols"); main.columnconfigure(1, weight=2, uniform="cols"); main.rowconfigure(2, weight=1)
        # Шапка
        header = ttk.Frame(main); header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10)); header.columnconfigure(0, weight=1)
        tr = ttk.Frame(header); tr.grid(row=0, column=0, sticky="ew"); tr.columnconfigure(0, weight=1)
        ttk.Label(tr, text="GLLauncher", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        hb = ttk.Frame(tr); hb.grid(row=0, column=1, sticky="e")
        self.update_btn = ttk.Button(hb, text="🔍 GreenLuma", command=self._on_check_updates); self.update_btn.grid(row=0, column=0, padx=(0,4))
        self.app_update_btn = ttk.Button(hb, text="🔄 Программа", command=self._on_check_app_updates); self.app_update_btn.grid(row=0, column=1, padx=(0,4))
        ttk.Button(hb, text="⚙ Настройки", command=self._on_show_settings).grid(row=0, column=2, padx=(0,4))
        ttk.Button(hb, text="❓ Обучение", command=self._on_show_tutorial).grid(row=0, column=3)
        ttk.Label(header, text="Поиск игр и DLC в Steam · запуск GreenLuma 2026", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2,0))
        # Панель управления
        cf = ttk.Frame(main); cf.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0,10)); cf.columnconfigure(0, weight=1)
        gb = ttk.Frame(cf); gb.grid(row=0, column=0, sticky="w")
        self.auto_setup_btn = ttk.Button(gb, text="🔧 Автонастройка", style="Accent.TButton", command=self._on_auto_setup_greenluma); self.auto_setup_btn.grid(row=0, column=0, padx=(0,6))
        self.launch_btn = ttk.Button(gb, text="🚀 Запустить GreenLuma", style="Success.TButton", command=self._on_launch_greenluma); self.launch_btn.grid(row=0, column=1, padx=(0,6))
        ttk.Button(gb, text="📥 Импорт", command=self._on_import_from_applist).grid(row=0, column=2)
        # Левая колонка
        left = ttk.Frame(main); left.grid(row=2, column=0, sticky="nsew", padx=(0,5)); left.columnconfigure(0, weight=1); left.rowconfigure(2, weight=1)
        sf = ttk.Frame(left); sf.grid(row=0, column=0, sticky="ew", pady=(0,6)); sf.columnconfigure(0, weight=1)
        ttk.Label(sf, text="Поиск игры:", style="Subtitle.TLabel").grid(row=0, column=0, sticky="w")
        er = ttk.Frame(sf); er.grid(row=1, column=0, sticky="ew", pady=(4,0)); er.columnconfigure(0, weight=1)
        self.search_var = tk.StringVar(); self.search_entry = ttk.Entry(er, textvariable=self.search_var); self.search_entry.grid(row=0, column=0, sticky="ew", ipady=4)
        self.search_entry.bind("<Return>", lambda _: self._on_search_clicked())
        self.search_btn = ttk.Button(er, text="Найти", style="Accent.TButton", command=self._on_search_clicked); self.search_btn.grid(row=0, column=1, padx=(6,0))
        ar = ttk.Frame(left); ar.grid(row=1, column=0, sticky="ew", pady=(4,6))
        self.add_selected_btn = ttk.Button(ar, text="＋ В список", style="Accent.TButton", command=self._on_add_selected_to_list); self.add_selected_btn.grid(row=0, column=0, padx=(0,4))
        self.open_game_btn = ttk.Button(ar, text="📂 Страница DLC", command=self._on_open_game_page); self.open_game_btn.grid(row=0, column=1, padx=(0,4))
        self.open_steamdb_btn = ttk.Button(ar, text="🔗 SteamDB", command=self._on_open_steamdb); self.open_steamdb_btn.grid(row=0, column=2)
        # Таблица результатов
        rw = ttk.Frame(left, style="Card.TFrame", padding=6); rw.grid(row=2, column=0, sticky="nsew"); rw.columnconfigure(0, weight=1); rw.rowconfigure(0, weight=1)
        self.results_tree = ttk.Treeview(rw, columns=("name","in_list"), show="tree headings", selectmode="browse")
        self.results_tree.heading("#0", text="Обложка"); self.results_tree.heading("name", text="Название"); self.results_tree.heading("in_list", text="✓")
        self.results_tree.column("#0", width=70, stretch=False, anchor="center"); self.results_tree.column("name", width=500, anchor="w"); self.results_tree.column("in_list", width=40, stretch=False, anchor="center")
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        self.results_tree.tag_configure("ru_unavailable", foreground="#b00020", background="#fff3f3")
        vsb = ttk.Scrollbar(rw, orient="vertical", command=self.results_tree.yview); vsb.grid(row=0, column=1, sticky="ns"); self.results_tree.configure(yscrollcommand=vsb.set)
        self.results_tree.bind("<Double-1>", lambda _: self._on_open_game_page())
        for col in ("name","in_list"): self.results_tree.heading(col, command=lambda c=col: self._sort_results_by(c))
        self._build_results_context_menu(); self.results_tree.bind("<Button-3>", self._on_results_right_click, add="+")
        # Правая колонка
        right = ttk.Frame(main); right.grid(row=2, column=1, sticky="nsew", padx=(5,0)); right.columnconfigure(0, weight=1); right.rowconfigure(2, weight=1)
        ttk.Label(right, text="Список для загрузки", style="Subtitle.TLabel").grid(row=0, column=0, sticky="w")
        la = ttk.Frame(right); la.grid(row=1, column=0, sticky="ew", pady=(4,6))
        ttk.Button(la, text="↑", width=3, command=lambda: self._on_move_selected(-1)).grid(row=0, column=0, padx=(0,2))
        ttk.Button(la, text="↓", width=3, command=lambda: self._on_move_selected(+1)).grid(row=0, column=1, padx=2)
        ttk.Button(la, text="✕ Удалить", command=self._on_remove_selected).grid(row=0, column=2, padx=2)
        ttk.Button(la, text="🗑 Очистить", command=self._on_clear_list).grid(row=0, column=3, padx=2)
        dw = ttk.Frame(right, style="Card.TFrame", padding=6); dw.grid(row=2, column=0, sticky="nsew"); dw.columnconfigure(0, weight=1); dw.rowconfigure(0, weight=1)
        self.dl_listbox = tk.Listbox(dw, font=("Consolas",10), activestyle="dotbox", bg=self.theme.card_bg, fg=self.theme.text, selectbackground=self.theme.accent, selectforeground="#ffffff", bd=0, highlightthickness=0)
        self.dl_listbox.grid(row=0, column=0, sticky="nsew")
        dv = ttk.Scrollbar(dw, orient="vertical", command=self.dl_listbox.yview); dv.grid(row=0, column=1, sticky="ns"); self.dl_listbox.configure(yscrollcommand=dv.set)
        self._drag_data = {"index": -1}
        self.dl_listbox.bind("<ButtonPress-1>", self._on_dl_press, add="+")
        self.dl_listbox.bind("<B1-Motion>", self._on_dl_motion, add="+")
        self.dl_listbox.bind("<ButtonRelease-1>", self._on_dl_release, add="+")
        self._build_dl_context_menu(); self.dl_listbox.bind("<Button-3>", self._on_dl_right_click, add="+")
        # Низ
        bottom = ttk.Frame(main); bottom.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10,0)); bottom.columnconfigure(0, weight=1)
        sr = ttk.Frame(bottom); sr.grid(row=0, column=0, sticky="ew"); sr.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Готово к работе")
        ttk.Label(sr, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.dirty_label = ttk.Label(sr, text="💾 Автоэкспорт…", style="Muted.TLabel", foreground="#16a34a")
        self.applist_path_var = tk.StringVar(value=self.settings.applist_dir)
        self.greenluma_path_var = tk.StringVar(value=self.settings.greenluma_normalmode_dir)
        self._list_dirty = False
        self._refresh_download_listbox()
        self._update_dirty_state(False)

    def _run_in_ui(self, fn): self._ui_queue.put(fn)
    def _drain_ui_queue(self):
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try: fn()
                except: pass
        except queue.Empty: pass
        self.root.after(100, self._drain_ui_queue)

    # Поиск
    def _on_search_clicked(self):
        term = self.search_var.get().strip()
        if not term: return
        self.search_btn.configure(state="disabled"); self.status_var.set(f"Поиск «{term}»…")
        for iid in self.results_tree.get_children(""): self.results_tree.delete(iid)
        self._search_results = []
        ccs = list(self.settings.search_ccs) if self.settings.search_ccs else ["RU","US"]
        def worker():
            try: results = steam_api.search_apps_multi_cc(term, language=self.settings.steam_language, ccs=ccs)
            except steam_api.SteamApiRateLimitError as e: self._run_in_ui(lambda: messagebox.showwarning(APP_TITLE, str(e))); results = []
            except steam_api.SteamApiError as e: self._run_in_ui(lambda: messagebox.showerror(APP_TITLE, f"Ошибка: {e}")); results = []
            self._run_in_ui(lambda: self._render_results(results, term))
        self._search_thread = threading.Thread(target=worker, daemon=True); self._search_thread.start()

    def _render_results(self, results, term):
        self._search_results = results; self.search_btn.configure(state="normal")
        for r in results:
            il = "✓" if self.download_list.contains(r.appid) else ""
            tags = ("ru_unavailable",) if r.is_ru_unavailable else ()
            self.results_tree.insert("", "end", iid=str(r.appid), text="…", values=(r.name, il), tags=tags)
        if results:
            self.status_var.set(f"Найдено {len(results)} по «{term}»")
            self._load_covers(results)
        else: self.status_var.set(f"По «{term}» ничего не найдено")

    def _load_covers(self, results):
        if not _PIL or not self.image_cache.pil_available: return
        def worker(r):
            if not r.tiny_image: return
            img = self.image_cache.get_pil_image(r.tiny_image, size=(48,48))
            if not img: return
            def apply():
                try:
                    photo = ImageTk.PhotoImage(img)
                    if not hasattr(self, "_covers"): self._covers = {}
                    self._covers[r.appid] = photo
                    self.results_tree.item(str(r.appid), image=photo)
                except: pass
            self._run_in_ui(apply)
        for r in results: threading.Thread(target=worker, args=(r,), daemon=True).start()

    def _sort_results_by(self, col):
        if not self._search_results: return
        pc, pr = self._results_sort_state
        rev = not pr if col == pc else False
        self._results_sort_state = (col, rev)
        def key(r): return r.name.lower() if col == "name" else (1 if self.download_list.contains(r.appid) else 0)
        try: sr = sorted(self._search_results, key=key, reverse=rev)
        except: return
        sel = self.results_tree.selection()
        self._search_results = sr
        for iid in self.results_tree.get_children(""): self.results_tree.delete(iid)
        for r in sr:
            il = "✓" if self.download_list.contains(r.appid) else ""
            tags = ("ru_unavailable",) if r.is_ru_unavailable else ()
            ph = getattr(self, "_covers", {}).get(r.appid)
            self.results_tree.insert("", "end", iid=str(r.appid), text="…" if not ph else "", image=ph if ph else "", values=(r.name, il), tags=tags)
        if sel:
            for s in sel:
                try: self.results_tree.selection_set(s)
                except: pass
        a = " ↓" if rev else " ↑"
        for c in ("name","in_list"):
            b = {"name":"Название","in_list":"✓"}[c]
            self.results_tree.heading(c, text=b + (a if c == col else ""))

    def _get_selected_result(self):
        sel = self.results_tree.selection()
        if not sel: return None
        try: aid = int(sel[0])
        except: return None
        for r in self._search_results:
            if r.appid == aid: return r
        return None

    def _on_add_selected_to_list(self):
        r = self._get_selected_result()
        if not r: return
        if self.download_list.add(r.appid, r.name, "app"): self.status_var.set(f"Добавлено: {r.name}")
        else: self.status_var.set(f"Уже в списке: {r.name}")
        self._refresh_in_list_col()

    def _on_open_steamdb(self):
        r = self._get_selected_result()
        if r: webbrowser.open(r.steamdb_url)

    def _on_open_game_page(self):
        r = self._get_selected_result()
        if not r: return
        GamePageWindow(self.root, self, r)

    def _refresh_in_list_col(self):
        for iid in self.results_tree.get_children(""):
            try: aid = int(iid)
            except: continue
            self.results_tree.set(iid, "in_list", "✓" if self.download_list.contains(aid) else "")

    # Контекстные меню
    def _build_results_context_menu(self):
        self.results_menu = tk.Menu(self.root, tearoff=0)
        self.results_menu.add_command(label="＋ Добавить", command=self._on_add_selected_to_list)
        self.results_menu.add_command(label="📂 Страница DLC", command=self._on_open_game_page)
        self.results_menu.add_separator()
        self.results_menu.add_command(label="🔗 SteamDB", command=self._on_open_steamdb)
        self.results_menu.add_command(label="📋 Копировать appid", command=self._copy_aid)

    def _on_results_right_click(self, e):
        rid = self.results_tree.identify_row(e.y)
        if rid: self.results_tree.selection_set(rid); self.results_tree.focus(rid)
        try: self.results_menu.tk_popup(e.x_root, e.y_root)
        finally: self.results_menu.grab_release()

    def _build_dl_context_menu(self):
        self.dl_menu = tk.Menu(self.root, tearoff=0)
        self.dl_menu.add_command(label="↑ Вверх", command=lambda: self._on_move_selected(-1))
        self.dl_menu.add_command(label="↓ Вниз", command=lambda: self._on_move_selected(+1))
        self.dl_menu.add_separator()
        self.dl_menu.add_command(label="✕ Удалить", command=self._on_remove_selected)
        self.dl_menu.add_command(label="📋 Копировать appid", command=self._copy_dl_aid)
        self.dl_menu.add_separator()
        self.dl_menu.add_command(label="🗑 Очистить", command=self._on_clear_list)

    def _on_dl_right_click(self, e):
        idx = self.dl_listbox.nearest(e.y)
        if 0 <= idx < self.dl_listbox.size():
            self.dl_listbox.selection_clear(0, tk.END); self.dl_listbox.selection_set(idx); self.dl_listbox.activate(idx)
        try: self.dl_menu.tk_popup(e.x_root, e.y_root)
        finally: self.dl_menu.grab_release()

    def _copy_aid(self):
        r = self._get_selected_result()
        if not r: return
        self.root.clipboard_clear(); self.root.clipboard_append(str(r.appid))

    def _copy_dl_aid(self):
        sel = self.dl_listbox.curselection()
        if not sel: return
        items = self.download_list.items()
        if 0 <= sel[0] < len(items):
            self.root.clipboard_clear(); self.root.clipboard_append(str(items[sel[0]].appid))

    # Список загрузки
    def _on_download_list_changed(self):
        self._run_in_ui(lambda: (self._refresh_download_listbox(), self._update_dirty_state(True)))

    def _refresh_download_listbox(self):
        items = self.download_list.items()
        cs = self.dl_listbox.curselection()
        self.dl_listbox.delete(0, tk.END)
        for it in items: self.dl_listbox.insert(tk.END, it.display())
        if cs:
            try: self.dl_listbox.selection_set(cs[0])
            except: pass
        self._refresh_in_list_col(); self._update_status()
        try: self.download_list.save_to_file(state_file_path())
        except: pass

    def _update_status(self):
        n = len(self.download_list)
        self.status_var.set("Список пуст." if n == 0 else f"В списке: {n} элем.")

    def _update_dirty_state(self, dirty):
        self._list_dirty = dirty
        if dirty:
            self.dirty_label.grid(row=0, column=1, sticky="e", padx=(8,0))
            self._auto_export_silent()
        else: self.dirty_label.grid_forget()

    def _auto_export_silent(self):
        items = self.download_list.items(); ad = self.settings.applist_dir
        if not items or not ad or not os.path.isdir(ad): return
        def worker():
            try:
                clear_applist_txt_files(ad)
                for i, it in enumerate(items):
                    with open(os.path.join(ad, f"{i}.txt"), "w", encoding="utf-8") as f: f.write(str(it.appid))
                self._run_in_ui(lambda: self._update_dirty_state(False))
            except: pass
        threading.Thread(target=worker, daemon=True).start()

    def _on_remove_selected(self):
        sel = self.dl_listbox.curselection()
        if not sel: return
        self.download_list.remove_at(sel[0])

    def _on_clear_list(self):
        if self.download_list and messagebox.askyesno(APP_TITLE, "Очистить список?"): self.download_list.clear()

    def _on_move_selected(self, d):
        sel = self.dl_listbox.curselection()
        if not sel: return
        idx = sel[0]
        if d < 0: self.download_list.move_up(idx); ni = max(0, idx-1)
        else: self.download_list.move_down(idx); ni = min(len(self.download_list)-1, idx+1)
        self.dl_listbox.selection_clear(0, tk.END)
        try: self.dl_listbox.selection_set(ni); self.dl_listbox.see(ni)
        except: pass

    def _on_dl_press(self, e):
        idx = self.dl_listbox.nearest(e.y)
        if 0 <= idx < self.dl_listbox.size():
            self._drag_data["index"] = idx; self.dl_listbox.selection_clear(0, tk.END); self.dl_listbox.selection_set(idx)

    def _on_dl_motion(self, e):
        if self._drag_data["index"] < 0: return
        idx = self.dl_listbox.nearest(e.y)
        if idx < 0 or idx >= self.dl_listbox.size() or idx == self._drag_data["index"]: return
        src = self._drag_data["index"]
        if idx > src:
            for _ in range(idx-src): self.download_list.move_down(src); src += 1
        else:
            for _ in range(src-idx): self.download_list.move_up(src); src -= 1
        self._drag_data["index"] = idx
        self.dl_listbox.selection_clear(0, tk.END)
        try: self.dl_listbox.selection_set(idx)
        except: pass

    def _on_dl_release(self, _): self._drag_data["index"] = -1

    # Пути
    def _refresh_paths_display(self):
        can = False
        nm = resolve_normalmode_dir(self.settings.greenluma_normalmode_dir)
        if nm: can = find_dll_injector(nm) is not None
        self.launch_btn.configure(state="normal" if can else "disabled")

    def _on_choose_applist_dir(self):
        ini = self.settings.applist_dir or os.path.expanduser("~")
        ch = filedialog.askdirectory(title="Папка AppList", initialdir=ini if os.path.isdir(ini) else None)
        if not ch: return
        if os.path.basename(ch).lower() != "applist":
            c = os.path.join(ch, "AppList")
            if messagebox.askyesno(APP_TITLE, f"Создать подпапку AppList в:\n{ch}?"): ch = c
        self.settings.applist_dir = os.path.abspath(ch)
        try: os.makedirs(self.settings.applist_dir, exist_ok=True)
        except OSError as e: messagebox.showwarning(APP_TITLE, f"Не удалось создать:\n{e}"); return
        self.settings.save(); self._refresh_paths_display()
        self._check_and_offer_import()

    def _on_choose_normalmode_dir(self):
        ini = self.settings.greenluma_normalmode_dir or self.settings.applist_dir or os.path.expanduser("~")
        ch = filedialog.askdirectory(title="Папка NormalMode", initialdir=ini if os.path.isdir(ini) else None)
        if not ch: return
        nm = resolve_normalmode_dir(ch)
        if nm:
            self.settings.greenluma_normalmode_dir = nm; self.settings.save(); self._refresh_paths_display()
            self._check_applist_near_greenluma()
        else:
            messagebox.showwarning(APP_TITLE, f"NormalMode не найдена:\n{ch}")

    def _check_and_offer_import(self):
        ad = self.settings.applist_dir
        if not ad or not os.path.isdir(ad): return
        try: tf = [f for f in os.listdir(ad) if f.lower().endswith(".txt")]
        except: return
        if not tf: return
        ec = len(self.download_list)
        msg = f"В AppList найдено {len(tf)} .txt файлов.\nВ списке {ec} элем.\n\nИмпортировать?" if ec else f"В AppList найдено {len(tf)} .txt файлов.\n\nИмпортировать?"
        if messagebox.askyesno(APP_TITLE, msg): self._on_import_from_applist()

    def _check_applist_near_greenluma(self):
        nm = resolve_normalmode_dir(self.settings.greenluma_normalmode_dir)
        if not nm: return
        parent = os.path.dirname(nm)
        for c in [os.path.join(nm, "AppList"), os.path.join(parent, "AppList")]:
            if not os.path.isdir(c): continue
            try: tf = [f for f in os.listdir(c) if f.lower().endswith(".txt")]
            except: continue
            if not tf: continue
            if messagebox.askyesno(APP_TITLE, f"Найдена папка AppList:\n{c}\n\n{len(tf)} .txt файлов.\n\nИспользовать и импортировать?"):
                self.settings.applist_dir = c; self.settings.save(); self._refresh_paths_display(); self._check_and_offer_import(); return

    def _on_import_from_applist(self):
        if not self.settings.applist_dir or not os.path.isdir(self.settings.applist_dir):
            messagebox.showinfo(APP_TITLE, "Укажите папку AppList в настройках."); return
        if self._import_thread and self._import_thread.is_alive(): return
        if len(self.download_list) > 0 and not messagebox.askyesno(APP_TITLE, f"В списке {len(self.download_list)} элем.\n\nИмпортировать из AppList?"): return
        self.status_var.set("Импорт…"); ad = self.settings.applist_dir; lang = self.settings.steam_language
        def worker():
            scan = scan_applist_dir(ad)
            self._run_in_ui(lambda: self._apply_import(scan, lang))
        self._import_thread = threading.Thread(target=worker, daemon=True); self._import_thread.start()

    def _apply_import(self, scan, lang):
        el = [f"  {f.file_name}: {f.error}" for f in scan.files if f.error] + [f"  ⚠ {w}" for w in scan.warnings]
        valid = scan.valid_appids
        if not valid:
            messagebox.showinfo(APP_TITLE, "Нет валидных файлов" + ("\n\n" + "\n".join(el[:20]) if el else "")); return
        added = skipped = 0
        for _, aid in [(i, a) for i, a in [(i, a) for i, a in enumerate(valid)]]:
            if self.download_list.add(aid, f"App {aid}", "app"): added += 1
            else: skipped += 1
        messagebox.showinfo(APP_TITLE, f"Импорт: +{added} новых, {skipped} уже было" + ("\n\nОшибки:\n" + "\n".join(el[:20]) if el else ""))
        self.status_var.set(f"Импорт: +{added}")
        self._fetch_names(valid, lang)

    def _fetch_names(self, appids, lang):
        items = self.download_list.items()
        tf = [it.appid for it in items if it.appid in appids and it.name.startswith("App ")]
        if not tf: return
        ccs = list(self.settings.search_ccs) if self.settings.search_ccs else ["RU","US"]
        def worker():
            for aid in tf:
                try: d = steam_api.get_app_details_auto_cc(aid, language=lang, ccs=ccs)
                except: continue
                if d:
                    with self.download_list._lock:
                        for it in self.download_list._items:
                            if it.appid == aid: it.name = d.name; break
                    self._run_in_ui(self._refresh_download_listbox)
        threading.Thread(target=worker, daemon=True).start()

    # Автонастройка
    def _on_auto_setup_greenluma(self):
        if not self.settings.greenluma_normalmode_dir:
            if messagebox.askyesno(APP_TITLE, "Укажите папку NormalMode. Открыть настройки?"):
                self._on_show_settings()
            return
        AutoSetupDialog(self.root, self)

    # Запуск
    def _on_launch_greenluma(self):
        if not self.settings.greenluma_normalmode_dir:
            if messagebox.askyesno(APP_TITLE, "GreenLuma не настроена. Открыть настройки?"): self._on_show_settings()
            return
        if self._launch_thread and self._launch_thread.is_alive(): return
        if len(self.download_list) > 0:
            ad = self.settings.applist_dir
            if not ad or not os.path.isdir(ad) or not any(f.lower().endswith(".txt") for f in os.listdir(ad)):
                if messagebox.askyesno(APP_TITLE, "В AppList нет файлов. Экспортировать?"): self._auto_export_silent()
        self.launch_btn.configure(state="disabled"); self.status_var.set("Запуск GreenLuma…")
        def on_result(r):
            def show():
                self.launch_btn.configure(state="normal"); self.status_var.set(r.message.replace("\n"," | "))
                if r.success: messagebox.showinfo(APP_TITLE, r.message)
                else: messagebox.showerror(APP_TITLE, r.message)
            self._run_in_ui(show)
        self._launch_thread = launch_greenluma(self.settings, on_result=on_result)

    # Обновления GreenLuma
    def _on_check_updates(self):
        self.update_btn.configure(state="disabled", text="🔍…"); self.status_var.set("Проверка GreenLuma…")
        self._check_updates_background(True)

    def _check_updates_background(self, force=False):
        import time
        nm = resolve_normalmode_dir(self.settings.greenluma_normalmode_dir)
        url = self.settings.update_url or DEFAULT_UPDATE_URL
        ca = time.time() - self.settings.last_update_check if self.settings.last_update_check else 999999
        def worker():
            try: info = check_for_updates(normalmode_dir=nm or "", update_url=url, use_cache=not force, cached_version=self.settings.last_known_version, cache_age_seconds=ca)
            except Exception as e: info = UpdateInfo(error=str(e))
            try:
                import time as _t; self.settings.last_update_check = _t.time()
                if info.latest_version: self.settings.last_known_version = info.latest_version
                self.settings.save()
            except: pass
            self._run_in_ui(lambda: self._show_update_result(info, force))
        threading.Thread(target=worker, daemon=True).start()

    def _show_update_result(self, info, force):
        self.update_btn.configure(state="normal", text="🔍 GreenLuma"); self.status_var.set(info.status_text)
        if info.has_update:
            try: self.update_btn.configure(style="Warning.TButton", text=f"✨ {info.latest_version}")
            except: pass
        else:
            try: self.update_btn.configure(style="TButton")
            except: pass
        if force or (info.has_update and not info.error):
            if info.has_update:
                msg = f"✨ Обновление GreenLuma!\n\nУстановленная: {info.installed_version or '?'}\nПоследняя: {info.latest_version}\n\nСкачать на cs.rin.ru?\n{info.topic_url}"
                if messagebox.askyesno(APP_TITLE, msg): open_topic_in_browser(info.topic_url)
            elif info.error:
                messagebox.showwarning(APP_TITLE, f"Ошибка:\n{info.error}")
            else:
                messagebox.showinfo(APP_TITLE, info.status_text)

    # Автообновление программы
    def _on_check_app_updates(self):
        if not self.settings.app_update_url:
            messagebox.showinfo(APP_TITLE, "URL не настроен. Откройте настройки."); return
        self.app_update_btn.configure(state="disabled", text="🔄…")
        url = self.settings.app_update_url
        def worker():
            try: info = check_for_app_updates(version_url=url, current_version=APP_VERSION)
            except Exception as e: info = AppUpdateInfo(error=str(e), current_version=APP_VERSION)
            self._run_in_ui(lambda: self._show_app_update(info))
        threading.Thread(target=worker, daemon=True).start()

    def _show_app_update(self, info):
        self.app_update_btn.configure(state="normal", text="🔄 Программа"); self.status_var.set(info.status_text)
        if info.error: messagebox.showwarning(APP_TITLE, f"Ошибка:\n{info.error}"); return
        if info.has_update:
            msg = f"✨ Обновление GLLauncher!\n\nТекущая: {info.current_version}\nНовая: {info.latest_version}\n\n"
            if info.release_notes: msg += f"Что нового:\n{info.release_notes[:500]}\n\n"
            if info.can_auto_update:
                msg += "Скачать и установить?"; 
                if messagebox.askyesno(APP_TITLE, msg): self._do_auto_update(info)
            else:
                msg += "Открыть страницу загрузки?"
                if messagebox.askyesno(APP_TITLE, msg): open_download_page(info.download_url)
        else: messagebox.showinfo(APP_TITLE, f"✓ Последняя версия: {info.current_version}")

    def _do_auto_update(self, info):
        pw = tk.Toplevel(self.root); pw.title("Обновление"); pw.geometry("500x250"); pw.transient(self.root); pw.grab_set()
        ttk.Label(pw, text="Скачивание обновления…", style="Subtitle.TLabel").pack(pady=(16,8))
        lt = tk.Text(pw, height=10, wrap="word", font=("Consolas",9)); lt.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0,8)); lt.configure(state="disabled")
        # Индикатор прогресса
        pb = ttk.Progressbar(pw, mode="indeterminate"); pb.pack(fill=tk.X, padx=16, pady=(0,8))
        pb.start(15)
        def al(m):
            lt.configure(state="normal"); lt.insert(tk.END, m+"\n"); lt.see(tk.END); lt.configure(state="disabled")
            pw.update_idletasks()
        def worker():
            try:
                ok, msg = download_and_install_update(info, progress_cb=lambda m: self._run_in_ui(lambda: al(m)))
            except Exception as e:
                ok, msg = False, f"Непредвиденная ошибка: {e}"
            def fin():
                pb.stop()
                if ok:
                    al("✓ " + msg)
                    al("Программа закрывается для замены файла…")
                    pw.update()
                    # Ждём 3 секунды, чтобы batch-скрипт успел запуститься
                    self.root.after(3000, self._on_close)
                else:
                    al("✗ " + msg)
                    pb.pack_forget()
                    ttk.Button(pw, text="Закрыть", command=pw.destroy).pack(pady=8)
            self._run_in_ui(fin)
        threading.Thread(target=worker, daemon=True).start()

    # Настройки
    def _on_show_settings(self): SettingsDialog(self.root, self)

    # Обучение
    def _on_show_tutorial(self):
        try: create_app_tour(self)
        except: pass

    # Горячие клавиши
    def _setup_hotkeys(self):
        self.root.bind("<Control-f>", lambda _: self.search_entry.focus_set())
        self.root.bind("<Control-l>", lambda _: self._on_launch_greenluma())
        self.root.bind("<F1>", lambda _: self._on_show_tutorial())
        self.root.bind("<Delete>", lambda _: self._on_remove_selected())
        self.dl_listbox.bind("<Delete>", lambda _: self._on_remove_selected())

    # Геометрия
    def _save_window_geometry(self):
        try:
            st = self.root.state()
            if st == "zoomed": self.settings.window_state = "zoomed"
            else: self.settings.window_state = "normal"; self.settings.window_geometry = self.root.geometry()
            self.settings.save()
        except: pass

    def _restore_window_geometry(self):
        try:
            if self.settings.window_state == "zoomed": self.root.state("zoomed")
            elif self.settings.window_geometry: self.root.geometry(self.settings.window_geometry)
        except: pass

    def _on_close(self):
        self._save_window_geometry()
        try: self.download_list.save_to_file(state_file_path())
        except: pass
        self.root.destroy()


class GamePageWindow(tk.Toplevel):
    def __init__(self, parent, app, result):
        super().__init__(parent); self.app = app; self.result = result
        self.title(f"Страница игры — {result.name}"); self.geometry("900x640"); self.minsize(700,500)
        self.transient(parent); self.grab_set()
        self._dlc_items = []; self._build_ui(); self._load_details()

    def _build_ui(self):
        c = ttk.Frame(self, padding=12); c.pack(fill=tk.BOTH, expand=True); c.columnconfigure(0, weight=1); c.rowconfigure(3, weight=1)
        ttk.Label(c, text=self.result.name, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        mr = ttk.Frame(c); mr.grid(row=1, column=0, sticky="ew", pady=(2,0))
        ttk.Label(mr, text=f"AppID: {self.result.appid}", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0,12))
        ls = ttk.Label(mr, text="Steam ↗", style="Muted.TLabel", cursor="hand2", foreground="#0066cc"); ls.grid(row=0, column=1, sticky="w", padx=(0,12))
        ls.bind("<Button-1>", lambda _: webbrowser.open(self.result.store_url))
        ld = ttk.Label(mr, text="SteamDB ↗", style="Muted.TLabel", cursor="hand2", foreground="#0066cc"); ld.grid(row=0, column=2, sticky="w")
        ld.bind("<Button-1>", lambda _: webbrowser.open(self.result.steamdb_url))
        ac = ttk.Frame(c); ac.grid(row=2, column=0, sticky="ew", pady=(10,6))
        ttk.Button(ac, text="＋ Добавить игру", style="Accent.TButton", command=self._on_add_game).grid(row=0, column=0, padx=(0,6))
        self.add_all_dlc_btn = ttk.Button(ac, text="＋＋ Все DLC", command=self._on_add_all_dlc); self.add_all_dlc_btn.grid(row=0, column=1, padx=(0,6))
        self.status_lbl = ttk.Label(ac, text="", style="Muted.TLabel"); self.status_lbl.grid(row=0, column=2, sticky="w", padx=(8,0))
        info = ttk.Frame(c, style="Card.TFrame", padding=8); info.grid(row=3, column=0, sticky="ew", pady=(0,8)); info.columnconfigure(1, weight=1)
        self.iv = {"dev": tk.StringVar(value="Разработчик: —"), "pub": tk.StringVar(value="Издатель: —"), "rel": tk.StringVar(value="Дата: —"), "desc": tk.StringVar(value="")}
        for i, (k, v) in enumerate([("dev",self.iv["dev"]),("pub",self.iv["pub"]),("rel",self.iv["rel"])]):
            ttk.Label(info, textvariable=v).grid(row=i, column=0, columnspan=2, sticky="w")
        ttk.Label(info, textvariable=self.iv["desc"], wraplength=820, justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=(4,0))
        dw = ttk.Frame(c); dw.grid(row=4, column=0, sticky="nsew"); dw.columnconfigure(0, weight=1); dw.rowconfigure(0, weight=1)
        self.dlc_tree = ttk.Treeview(dw, columns=("appid","name","release","cc","in_list"), show="tree headings", selectmode="extended")
        for col, txt, w in [("#0","Обложка",60),("appid","AppID",90),("name","DLC",470),("release","Дата",110),("cc","Регион",70),("in_list","✓",70)]:
            self.dlc_tree.heading(col, text=txt); self.dlc_tree.column(col, width=w, stretch=False if col != "name" else True)
        self.dlc_tree.grid(row=0, column=0, sticky="nsew")
        vs = ttk.Scrollbar(dw, orient="vertical", command=self.dlc_tree.yview); vs.grid(row=0, column=1, sticky="ns"); self.dlc_tree.configure(yscrollcommand=vs.set)
        self.dlc_tree.tag_configure("ru_unavailable", foreground="#b00020", background="#fff3f3")
        b = ttk.Frame(c); b.grid(row=5, column=0, sticky="ew", pady=(8,0))
        ttk.Button(b, text="＋ Выбранные DLC", command=self._on_add_selected_dlc).grid(row=0, column=0)
        ttk.Button(b, text="Закрыть", command=self.destroy).grid(row=0, column=1, padx=(8,0))
        self.app.download_list.add_listener(self._on_dl_changed)

    def _show_loading_placeholder(self):
        for iid in self.dlc_tree.get_children(""): self.dlc_tree.delete(iid)
        self.dlc_tree.insert("", "end", iid="loading", text="⏳", values=("","Загрузка DLC...","","",""))
        self._loading_dots = 0; self._animate_loading()

    def _animate_loading(self):
        try:
            if not self.dlc_tree.exists("loading"): return
        except: return
        self._loading_dots = (self._loading_dots + 1) % 4
        try: self.dlc_tree.item("loading", values=("","Загрузка DLC" + "."*self._loading_dots,"","",""))
        except: return
        self._loading_after = self.after(500, self._animate_loading)

    def _load_details(self):
        self.status_lbl.configure(text="Загрузка…"); self._show_loading_placeholder()
        ccs = list(self.app.settings.search_ccs) if self.app.settings.search_ccs else ["RU","US"]
        lang = self.app.settings.steam_language
        known = list(self.result.available_in) if self.result.available_in else None
        def worker():
            try: d = steam_api.get_full_game_with_dlc_auto_cc(self.result.appid, language=lang, ccs=ccs, known_available_in=known)
            except: d = None
            self.app._run_in_ui(lambda: self._render_details(d))
        t = threading.Thread(target=worker, daemon=True); t.start()

    def _render_details(self, d):
        if hasattr(self, "_loading_after"): self.after_cancel(self._loading_after)
        if d is None: self.status_lbl.configure(text="Не удалось загрузить"); return
        self.iv["dev"].set("Разработчик: " + (", ".join(d.developers) or "—"))
        self.iv["pub"].set("Издатель: " + (", ".join(d.publishers) or "—"))
        ri = f" [регионы: {'+'.join(d.available_in)}]" if d.available_in else (f" [из {d.loaded_cc}]" if d.loaded_cc else "")
        if d.is_ru_unavailable if hasattr(d, 'is_ru_unavailable') else False: ri = " ⚠ НЕ в RU" + ri
        self.iv["rel"].set("Дата: " + (d.release_date or "—") + ri)
        self.iv["desc"].set(d.short_description)
        self._dlc_items = list(d.dlc)
        for iid in self.dlc_tree.get_children(""): self.dlc_tree.delete(iid)
        for dlc in self._dlc_items:
            il = "✓" if self.app.download_list.contains(dlc.appid) else ""
            tags = ("ru_unavailable",) if dlc.is_ru_unavailable else ()
            self.dlc_tree.insert("", "end", iid=str(dlc.appid), text="…", values=(dlc.appid, dlc.name, dlc.release_date or "—", dlc.loaded_cc, il), tags=tags)
        if self._dlc_items:
            self.add_all_dlc_btn.configure(state="normal")
            ru_un = sum(1 for d in self._dlc_items if d.is_ru_unavailable)
            self.status_lbl.configure(text=f"DLC: {len(self._dlc_items)}" + (f" ({ru_un} недоступно в RU)" if ru_un else ""))
        else: self.status_lbl.configure(text="Нет DLC")
        self._load_dlc_covers(self._dlc_items)

    def _load_dlc_covers(self, dlcs):
        if not _PIL or not self.app.image_cache.pil_available: return
        if not hasattr(self, "_dlc_covers"): self._dlc_covers = {}
        def worker(dlc):
            if not dlc.header_image: return
            img = self.app.image_cache.get_pil_image(dlc.header_image, size=(48,48))
            if not img: return
            def apply():
                try:
                    ph = ImageTk.PhotoImage(img); self._dlc_covers[dlc.appid] = ph
                    self.dlc_tree.item(str(dlc.appid), image=ph)
                except: pass
            self.app._run_in_ui(apply)
        for d in dlcs: threading.Thread(target=worker, args=(d,), daemon=True).start()

    def _on_add_game(self):
        if self.app.download_list.add(self.result.appid, self.result.name, "app"): self.status_lbl.configure(text="Игра добавлена")
        else: self.status_lbl.configure(text="Уже в списке")

    def _on_add_selected_dlc(self):
        sel = self.dlc_tree.selection()
        if not sel: return
        added = 0
        for iid in sel:
            try: aid = int(iid)
            except: continue
            name = f"DLC {aid}"
            for d in self._dlc_items:
                if d.appid == aid: name = d.name; break
            if self.app.download_list.add(aid, name, "dlc"): added += 1
        self.status_lbl.configure(text=f"Добавлено DLC: {added}")

    def _on_add_all_dlc(self):
        if not self._dlc_items: return
        added = 0
        for d in self._dlc_items:
            if self.app.download_list.add(d.appid, d.name, "dlc"): added += 1
        self.status_lbl.configure(text=f"Добавлено: {added}")

    def _on_dl_changed(self):
        def r():
            for iid in self.dlc_tree.get_children(""):
                try: aid = int(iid)
                except: continue
                self.dlc_tree.set(iid, "in_list", "✓" if self.app.download_list.contains(aid) else "")
        self.app._run_in_ui(r)

    def destroy(self):
        try: self.app.download_list._listeners.remove(self._on_dl_changed)
        except: pass
        super().destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent); self.app = app
        self.title("Настройки GLLauncher"); self.geometry("720x720"); self.minsize(650,600)
        self.transient(parent); self.grab_set()
        s = app.settings
        from updater import DEFAULT_UPDATE_URL
        self._app_update_url = tk.StringVar(value=s.app_update_url)
        self._update_url = tk.StringVar(value=s.update_url or DEFAULT_UPDATE_URL)
        self._search_ccs = tk.StringVar(value=", ".join(s.search_ccs))
        self._applist_dir = tk.StringVar(value=s.applist_dir)
        self._normalmode_dir = tk.StringVar(value=s.greenluma_normalmode_dir)
        if s.theme_settings: ts = ThemeSettings.from_dict(s.theme_settings)
        else: ts = ThemeSettings.light_preset()
        self._ts = ts
        self._theme_preset = tk.StringVar(value=ts.preset)
        self._build_ui()

    def _build_ui(self):
        outer = ttk.Frame(self); outer.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview); sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); canvas.configure(yscrollcommand=sb.set)
        c = ttk.Frame(canvas, padding=16); cw = canvas.create_window((0,0), window=c, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        c.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)),"units"))
        self.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))
        c.columnconfigure(0, weight=1); row = 0
        ttk.Label(c, text="Настройки GLLauncher", style="Title.TLabel").grid(row=row, column=0, sticky="w", pady=(0,12)); row += 1
        # Пути
        pf = ttk.LabelFrame(c, text="Пути", padding=10); pf.grid(row=row, column=0, sticky="ew", pady=(0,10)); pf.columnconfigure(1, weight=1); row += 1
        ttk.Label(pf, text="Папка AppList:").grid(row=0, column=0, sticky="w", padx=(0,8))
        ttk.Entry(pf, textvariable=self._applist_dir, state="readonly").grid(row=0, column=1, sticky="ew")
        ttk.Button(pf, text="Изменить…", command=lambda: self._choose_dir("AppList")).grid(row=0, column=2, padx=(6,0))
        ttk.Label(pf, text="Папка NormalMode:").grid(row=1, column=0, sticky="w", padx=(0,8), pady=(8,0))
        ttk.Entry(pf, textvariable=self._normalmode_dir, state="readonly").grid(row=1, column=1, sticky="ew", pady=(8,0))
        ttk.Button(pf, text="Изменить…", command=lambda: self._choose_dir("NormalMode")).grid(row=1, column=2, padx=(6,0), pady=(8,0))
        # Обновления программы
        uf = ttk.LabelFrame(c, text="Обновления программы", padding=10); uf.grid(row=row, column=0, sticky="ew", pady=(0,10)); uf.columnconfigure(0, weight=1); row += 1
        ttk.Label(uf, text="URL version.json:").grid(row=0, column=0, sticky="w")
        ttk.Entry(uf, textvariable=self._app_update_url).grid(row=1, column=0, sticky="ew", pady=(4,0))
        ttk.Label(uf, text="По умолчанию: https://raw.githubusercontent.com/TrueLessFalse/GLLauncher/refs/heads/main/version.json", style="Muted.TLabel", wraplength=600).grid(row=2, column=0, sticky="w", pady=(2,0))
        br = ttk.Frame(uf); br.grid(row=3, column=0, sticky="ew", pady=(8,0))
        ttk.Button(br, text="🔄 Проверить", command=self._on_check_now).grid(row=0, column=0, sticky="w")
        ttk.Button(br, text="↩ Сбросить", command=self._on_reset_url).grid(row=0, column=1, sticky="e")
        # GreenLuma
        gf = ttk.LabelFrame(c, text="Обновления GreenLuma (cs.rin.ru)", padding=10); gf.grid(row=row, column=0, sticky="ew", pady=(0,10)); gf.columnconfigure(0, weight=1); row += 1
        ttk.Label(gf, text="URL темы (пусто = по умолчанию):").grid(row=0, column=0, sticky="w")
        ttk.Entry(gf, textvariable=self._update_url).grid(row=1, column=0, sticky="ew", pady=(4,0))
        ttk.Label(gf, text="По умолчанию: https://cs.rin.ru/forum/viewtopic.php?f=10&t=103709", style="Muted.TLabel", wraplength=600).grid(row=2, column=0, sticky="w", pady=(2,0))
        # Поиск
        sf = ttk.LabelFrame(c, text="Поиск Steam", padding=10); sf.grid(row=row, column=0, sticky="ew", pady=(0,10)); sf.columnconfigure(0, weight=1); row += 1
        ttk.Label(sf, text="Регионы (через запятую: RU, US, TR):").grid(row=0, column=0, sticky="w")
        ttk.Entry(sf, textvariable=self._search_ccs).grid(row=1, column=0, sticky="ew", pady=(4,0))
        # Персонализация
        tf = ttk.LabelFrame(c, text="Персонализация", padding=10); tf.grid(row=row, column=0, sticky="ew", pady=(0,10)); tf.columnconfigure(1, weight=1); row += 1
        # Пресеты
        ttk.Label(tf, text="Пресет:").grid(row=0, column=0, sticky="w", padx=(0,8))
        pr = ttk.Frame(tf); pr.grid(row=0, column=1, columnspan=3, sticky="w")
        ttk.Radiobutton(pr, text="Светлая", value="light", variable=self._theme_preset, command=self._on_preset_change).grid(row=0, column=0, padx=(0,12))
        ttk.Radiobutton(pr, text="Тёмная", value="dark", variable=self._theme_preset, command=self._on_preset_change).grid(row=0, column=1, padx=(0,12))
        ttk.Radiobutton(pr, text="Своя", value="custom", variable=self._theme_preset).grid(row=0, column=2)
        # Переменные цветов
        self._theme_bg = tk.StringVar(value=self._ts.bg)
        self._theme_card = tk.StringVar(value=self._ts.card_bg)
        self._theme_text = tk.StringVar(value=self._ts.text)
        self._theme_accent = tk.StringVar(value=self._ts.accent)
        self._theme_hover = tk.StringVar(value=getattr(self._ts, 'button_hover', '#e4e6eb'))
        # Цвет фона
        ttk.Label(tf, text="Цвет фона:").grid(row=1, column=0, sticky="w", padx=(0,8), pady=(8,0))
        ttk.Entry(tf, textvariable=self._theme_bg).grid(row=1, column=1, sticky="ew", pady=(8,0))
        self._sw_bg = tk.Label(tf, text="  ", bg=self._theme_bg.get(), relief="solid", bd=1)
        self._sw_bg.grid(row=1, column=2, padx=(4,0), pady=(8,0))
        ttk.Button(tf, text="🎨", width=3, command=lambda: self._pick_color(self._theme_bg, self._sw_bg)).grid(row=1, column=3, padx=(4,0), pady=(8,0))
        # Цвет карточек
        ttk.Label(tf, text="Цвет панелей:").grid(row=2, column=0, sticky="w", padx=(0,8), pady=(4,0))
        ttk.Entry(tf, textvariable=self._theme_card).grid(row=2, column=1, sticky="ew", pady=(4,0))
        self._sw_card = tk.Label(tf, text="  ", bg=self._theme_card.get(), relief="solid", bd=1)
        self._sw_card.grid(row=2, column=2, padx=(4,0), pady=(4,0))
        ttk.Button(tf, text="🎨", width=3, command=lambda: self._pick_color(self._theme_card, self._sw_card)).grid(row=2, column=3, padx=(4,0), pady=(4,0))
        # Цвет текста
        ttk.Label(tf, text="Цвет текста:").grid(row=3, column=0, sticky="w", padx=(0,8), pady=(4,0))
        ttk.Entry(tf, textvariable=self._theme_text).grid(row=3, column=1, sticky="ew", pady=(4,0))
        self._sw_text = tk.Label(tf, text="  ", bg=self._theme_text.get(), relief="solid", bd=1)
        self._sw_text.grid(row=3, column=2, padx=(4,0), pady=(4,0))
        ttk.Button(tf, text="🎨", width=3, command=lambda: self._pick_color(self._theme_text, self._sw_text)).grid(row=3, column=3, padx=(4,0), pady=(4,0))
        # Цвет акцента
        ttk.Label(tf, text="Цвет акцента:").grid(row=4, column=0, sticky="w", padx=(0,8), pady=(4,0))
        ttk.Entry(tf, textvariable=self._theme_accent).grid(row=4, column=1, sticky="ew", pady=(4,0))
        self._sw_accent = tk.Label(tf, text="  ", bg=self._theme_accent.get(), relief="solid", bd=1)
        self._sw_accent.grid(row=4, column=2, padx=(4,0), pady=(4,0))
        ttk.Button(tf, text="🎨", width=3, command=lambda: self._pick_color(self._theme_accent, self._sw_accent)).grid(row=4, column=3, padx=(4,0), pady=(4,0))
        # Цвет наведения
        ttk.Label(tf, text="Цвет наведения:").grid(row=5, column=0, sticky="w", padx=(0,8), pady=(4,0))
        ttk.Entry(tf, textvariable=self._theme_hover).grid(row=5, column=1, sticky="ew", pady=(4,0))
        self._sw_hover = tk.Label(tf, text="  ", bg=self._theme_hover.get(), relief="solid", bd=1)
        self._sw_hover.grid(row=5, column=2, padx=(4,0), pady=(4,0))
        ttk.Button(tf, text="🎨", width=3, command=lambda: self._pick_color(self._theme_hover, self._sw_hover)).grid(row=5, column=3, padx=(4,0), pady=(4,0))
        # Конфиг
        cf = ttk.LabelFrame(c, text="Конфигурация", padding=10); cf.grid(row=row, column=0, sticky="ew", pady=(0,10)); cf.columnconfigure(0, weight=1); row += 1
        cp = settings_file_path(); sp = state_file_path(); lp = log_file_path()
        ttk.Label(cf, text=f"Конфиг: {cp}\nЛог: {lp}\nРежим: {'Portable' if is_portable_mode() else 'Обычный'}", style="Muted.TLabel", wraplength=600, justify="left").grid(row=0, column=0, columnspan=3, sticky="w")
        cb = ttk.Frame(cf); cb.grid(row=1, column=0, sticky="w", pady=(8,0))
        ttk.Button(cb, text="📂 Папка", command=lambda: self._open(os.path.dirname(cp))).grid(row=0, column=0, padx=(0,4))
        ttk.Button(cb, text="📝 settings.json", command=lambda: self._open(cp)).grid(row=0, column=1, padx=4)
        ttk.Button(cb, text="📋 Лог", command=lambda: self._open(lp)).grid(row=0, column=2, padx=4)
        # Низ
        b = ttk.Frame(c); b.grid(row=row, column=0, sticky="ew", pady=(12,0))
        ttk.Button(b, text="Отмена", command=self.destroy).grid(row=0, column=0)
        ttk.Button(b, text="💾 Сохранить", style="Accent.TButton", command=self._on_save).grid(row=0, column=1, sticky="e", padx=(8,0))

    def _choose_dir(self, name):
        if name == "AppList": self.app._on_choose_applist_dir(); self._applist_dir.set(self.app.settings.applist_dir)
        elif name == "NormalMode": self.app._on_choose_normalmode_dir(); self._normalmode_dir.set(self.app.settings.greenluma_normalmode_dir)

    def _pick_color(self, var, swatch):
        """Открыть палитру выбора цвета."""
        from theme import ask_color
        color = ask_color(self, var.get())
        if color:
            var.set(color)
            try: swatch.config(bg=color)
            except: pass

    def _on_preset_change(self):
        """При выборе пресета — обновить поля цвета."""
        preset = self._theme_preset.get()
        if preset == "light": t = ThemeSettings.light_preset()
        elif preset == "dark": t = ThemeSettings.dark_preset()
        else: return
        self._theme_bg.set(t.bg); self._theme_card.set(t.card_bg)
        self._theme_text.set(t.text); self._theme_accent.set(t.accent)
        self._theme_hover.set(t.button_hover)
        for var, sw in [(self._theme_bg, self._sw_bg), (self._theme_card, self._sw_card),
                        (self._theme_text, self._sw_text), (self._theme_accent, self._sw_accent),
                        (self._theme_hover, self._sw_hover)]:
            try: sw.config(bg=var.get())
            except: pass

    def _on_check_now(self):
        self.app.settings.app_update_url = self._app_update_url.get().strip(); self.app.settings.save()
        self.destroy(); self.app._on_check_app_updates()

    def _on_reset_url(self):
        self._app_update_url.set("https://raw.githubusercontent.com/TrueLessFalse/GLLauncher/refs/heads/main/version.json")

    def _open(self, path):
        try:
            if platform.system() == "Windows": os.startfile(path)
            else: import subprocess; subprocess.Popen(["xdg-open", path])
        except: pass

    def _on_save(self):
        s = self.app.settings
        s.app_update_url = self._app_update_url.get().strip()
        from updater import DEFAULT_UPDATE_URL
        gl = self._update_url.get().strip(); s.update_url = "" if gl == DEFAULT_UPDATE_URL else gl
        cs = self._search_ccs.get().strip()
        if cs:
            ccs = [c.strip().upper() for c in cs.split(",") if c.strip()]
            if ccs: s.search_ccs = ccs
        # Сохраняем тему со всеми цветами
        theme = ThemeSettings(
            bg=self._theme_bg.get(),
            card_bg=self._theme_card.get(),
            text=self._theme_text.get(),
            muted="#6e6e73" if self._theme_preset.get() == "light" else "#8e8e93",
            accent=self._theme_accent.get(),
            accent_hover=self._theme_accent.get(),
            button_hover=self._theme_hover.get(),
            preset=self._theme_preset.get(),
        )
        s.theme_settings = theme.to_dict()
        s.save(); self.app._refresh_paths_display()
        self.app.status_var.set("Настройки сохранены. Перезапустите для темы.")
        self.destroy()


class AutoSetupDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent); self.app = app
        self.title("Автонастройка GreenLuma 2026"); self.geometry("720x500"); self.minsize(600,400)
        self.transient(parent); self.grab_set()
        self._build_ui(); self.after(100, self._run)

    def _build_ui(self):
        c = ttk.Frame(self, padding=12); c.pack(fill=tk.BOTH, expand=True); c.columnconfigure(0, weight=1); c.rowconfigure(1, weight=1)
        ttk.Label(c, text="Автонастройка GreenLuma 2026", style="Title.TLabel").pack(pady=(0,4))
        ttk.Label(c, text="1. Проверка файлов NormalMode\n2. Поиск Steam.exe (реестр)\n3. Поиск GreenLuma_2026_x64.dll\n4. Запись DLLInjector.ini", style="Muted.TLabel", justify="left").pack(pady=(0,8))
        self.log_text = tk.Text(c, height=15, wrap="word", font=("Consolas",9)); self.log_text.pack(fill=tk.BOTH, expand=True, pady=(0,8))
        self.log_text.configure(state="disabled")
        b = ttk.Frame(c); b.pack()
        ttk.Button(b, text="📂 AppListManager", command=self._on_open_alm).grid(row=0, column=0, padx=4)
        ttk.Button(b, text="🔄 Повторить", command=self._run).grid(row=0, column=1, padx=4)
        ttk.Button(b, text="Закрыть", command=self.destroy).grid(row=0, column=2, padx=4)

    def _log(self, m):
        self.log_text.configure(state="normal"); self.log_text.insert(tk.END, m+"\n"); self.log_text.see(tk.END); self.log_text.configure(state="disabled")
        self.update_idletasks()

    def _run(self):
        self.log_text.configure(state="normal"); self.log_text.delete("1.0", tk.END); self.log_text.configure(state="disabled")
        def progress(m): self.app._run_in_ui(lambda: self._log(m))
        def worker():
            r = setup_greenluma(self.app.settings, progress_cb=progress)
            self.app._run_in_ui(lambda: self._show(r))
            self.app._run_in_ui(self.app._refresh_paths_display)
        threading.Thread(target=worker, daemon=True).start()

    def _show(self, r):
        if r.ok:
            self._log(""); self._log("✓ Готово!"); self._log(f"  Steam.exe: {r.steam_exe}"); self._log(f"  DLL: {r.dll_path}"); self._log(f"  INI: {r.ini_path}")
            messagebox.showinfo("Автонастройка", f"Готово!\nSteam.exe: {r.steam_exe}\nDLL: {r.dll_path}", parent=self)
        else:
            self._log(""); self._log("✗ Ошибка:")
            for e in r.errors: self._log(f"  {e}")
            messagebox.showerror("Автонастройка", "\n".join(r.errors), parent=self)

    def _on_open_alm(self):
        if not open_applist_manager(self.app.settings):
            messagebox.showinfo("AppListManager", "Не найден.", parent=self)


def main():
    _setup_crash_logging()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = tk.Tk()
    SteamListerApp(root)
    root.mainloop()

if __name__ == "__main__":
    sys.exit(main())
