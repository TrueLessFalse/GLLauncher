"""Автонастройка GreenLuma 2026 (NormalMode)."""
from __future__ import annotations
import logging, os, platform, subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional
from config import Settings, check_normalmode_files, find_greenluma_dll, find_steam_exe, resolve_normalmode_dir, write_dllinjector_ini
log = logging.getLogger(__name__)

@dataclass
class CheckResult:
    ok: bool; normalmode_dir: str = ""; missing_files: List[str] = field(default_factory=list)
    found_files: List[str] = field(default_factory=list); warnings: List[str] = field(default_factory=list); messages: List[str] = field(default_factory=list)

@dataclass
class SetupResult:
    ok: bool; steam_exe: str = ""; dll_path: str = ""; ini_path: str = ""; normalmode_dir: str = ""
    errors: List[str] = field(default_factory=list); warnings: List[str] = field(default_factory=list); messages: List[str] = field(default_factory=list)

def check_greenluma_setup(settings):
    r = CheckResult(ok=True)
    nm = resolve_normalmode_dir(settings.greenluma_normalmode_dir)
    if not nm: r.ok = False; r.warnings.append("NormalMode не найдена"); return r
    r.normalmode_dir = nm
    m, f = check_normalmode_files(nm)
    r.missing_files, r.found_files = m, f
    if m: r.ok = False
    ini = os.path.join(nm, "DLLInjector.ini")
    if os.path.isfile(ini):
        try:
            with open(ini, "r", encoding="utf-8", errors="replace") as fh:
                if "UseFullPathsFromIni = 1" in fh.read(): r.messages.append("DLLInjector.ini настроен")
                else: r.messages.append("DLLInjector.ini не настроен")
        except: pass
    else: r.messages.append("DLLInjector.ini не найден")
    if settings.steam_exe and os.path.isfile(settings.steam_exe): r.messages.append(f"Steam.exe: {settings.steam_exe}")
    elif find_steam_exe(): r.messages.append("Steam.exe будет найден автоматически")
    else: r.warnings.append("Steam.exe не найден")
    return r

def setup_greenluma(settings, progress_cb=None):
    r = SetupResult(ok=True)
    def _log(m):
        log.info(m); r.messages.append(m)
        if progress_cb:
            try: progress_cb(m)
            except: pass
    if platform.system() != "Windows": r.ok = False; r.errors.append("Только Windows"); return r
    nm = resolve_normalmode_dir(settings.greenluma_normalmode_dir)
    if not nm: r.ok = False; r.errors.append("NormalMode не найдена"); return r
    if nm != settings.greenluma_normalmode_dir: settings.greenluma_normalmode_dir = nm
    r.normalmode_dir = nm; _log(f"NormalMode: {nm}")
    m, f = check_normalmode_files(nm)
    if m: r.ok = False; r.errors.append("Не хватает: " + ", ".join(m)); return r
    _log(f"Файлы OK ({len(f)})")
    se = settings.steam_exe
    if not se or not os.path.isfile(se):
        _log("Поиск Steam.exe…"); se = find_steam_exe()
        if not se: r.ok = False; r.errors.append("Steam.exe не найден"); return r
        settings.steam_exe = se
    r.steam_exe = se; _log(f"Steam.exe: {se}")
    dp = find_greenluma_dll(nm)
    if not dp: r.ok = False; r.errors.append("GreenLuma_2026_x64.dll не найден"); return r
    r.dll_path = dp; _log(f"DLL: {dp}")
    try:
        ip = write_dllinjector_ini(nm, se, dp); r.ini_path = ip; _log(f"INI: {ip}")
    except OSError as e: r.ok = False; r.errors.append(f"INI: {e}"); return r
    try: settings.save()
    except: pass
    _log("Готово!")
    return r

def open_applist_manager(settings):
    if not settings.greenluma_normalmode_dir: return False
    nm = resolve_normalmode_dir(settings.greenluma_normalmode_dir)
    if not nm: return False
    for c in [os.path.join(nm, "AppListManager.exe"), os.path.join(os.path.dirname(nm), "AppListManager.exe")]:
        if os.path.isfile(c):
            try:
                if platform.system() == "Windows": os.startfile(c)
                else: subprocess.Popen([c], cwd=os.path.dirname(c))
                return True
            except: return False
    return False
