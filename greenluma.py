"""Запуск GreenLuma + мягкое закрытие Steam."""
from __future__ import annotations
import logging, os, platform, subprocess, threading, time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple
from config import Settings, find_dll_injector, resolve_normalmode_dir
log = logging.getLogger(__name__)
STEAM_PROCESS_NAMES = ("steam.exe", "Steam.exe", "SteamService.exe", "steamwebhelper.exe", "DLLInjector.exe")

@dataclass
class LaunchResult:
    success: bool; message: str; injector_path: Optional[str] = None; pid: Optional[int] = None; steam_was_killed: bool = False

def _try_psutil():
    try: import psutil; return psutil
    except: return None

def get_steam_processes():
    ps = _try_psutil()
    if ps:
        out = []
        try:
            for p in ps.process_iter(attrs=["pid","name"]):
                try:
                    n = p.info.get("name","")
                    if n and n.lower() in {x.lower() for x in STEAM_PROCESS_NAMES}: out.append((p.info["pid"], n))
                except: continue
            return out
        except: pass
    if platform.system() != "Windows": return []
    try:
        r = subprocess.run(["tasklist","/FO","CSV","/NH"], capture_output=True, timeout=10, text=True)
        if r.returncode != 0: return []
        sn = {x.lower() for x in STEAM_PROCESS_NAMES}; out = []
        for line in r.stdout.splitlines():
            parts = line.strip().split('","')
            if len(parts) >= 2:
                n = parts[0].strip('"')
                if n.lower() in sn:
                    try: out.append((int(parts[1].strip('"')), n))
                    except: pass
        return out
    except: return []

def is_steam_running(): return bool(get_steam_processes())

def close_steam(steam_exe="", timeout=30):
    if platform.system() != "Windows": return False, "Только Windows"
    procs = get_steam_processes()
    if not procs: return True, "Steam не был запущен"
    if steam_exe and os.path.isfile(steam_exe):
        try:
            subprocess.Popen([steam_exe, "-shutdown"], cwd=os.path.dirname(steam_exe),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            time.sleep(1)
            if not get_steam_processes(): return True, "Steam закрыт"
    try:
        subprocess.run(["taskkill","/F","/IM","steam.exe"], capture_output=True, timeout=10)
    except: pass
    for _ in range(10):
        time.sleep(0.5)
        if not get_steam_processes(): return True, "Steam закрыт (taskkill)"
    return False, "Не удалось закрыть Steam"

def launch_greenluma(settings, on_result=None, close_steam_first=True):
    def worker():
        r = _do_launch(settings, close_steam_first)
        if on_result:
            try: on_result(r)
            except: pass
    t = threading.Thread(target=worker, daemon=True); t.start(); return t

def _do_launch(settings, close_steam_first=True):
    if platform.system() != "Windows": return LaunchResult(False, "Только Windows")
    killed = False
    if close_steam_first:
        if get_steam_processes():
            ok, _ = close_steam(settings.steam_exe, 30)
            killed = ok
    nm = resolve_normalmode_dir(settings.greenluma_normalmode_dir)
    if not nm: return LaunchResult(False, f"Папка NormalMode не найдена:\n{settings.greenluma_normalmode_dir!r}\n\nОткройте «⚙ Настройки» и укажите папку.", steam_was_killed=killed)
    inj = find_dll_injector(nm)
    if not inj: return LaunchResult(False, f"DLLInjector.exe не найден в {nm}", steam_was_killed=killed)
    ini = os.path.join(nm, "DLLInjector.ini")
    if not os.path.isfile(ini): return LaunchResult(False, "DLLInjector.ini не найден. Сначала автонастройка.", inj, None, killed)
    with open(ini, "r", encoding="utf-8", errors="replace") as f:
        if "UseFullPathsFromIni = 1" not in f.read(): return LaunchResult(False, "DLLInjector.ini не настроен. Сначала автонастройка.", inj, None, killed)
    ad = settings.applist_dir
    if not ad or not os.path.isdir(ad): return LaunchResult(False, f"Папка AppList не найдена: {ad!r}", inj, None, killed)
    tc = sum(1 for n in os.listdir(ad) if n.lower().endswith(".txt"))
    if tc == 0: return LaunchResult(False, "В AppList нет .txt файлов. Сначала добавьте игры.", inj, None, killed)
    try:
        try:
            p = subprocess.Popen([inj], cwd=nm, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            msg = f"GreenLuma запущена (PID {p.pid}).\nИнжектор: {os.path.basename(inj)}\nAppList: {ad} ({tc} файлов)"
            if killed: msg = "Steam закрыт.\n" + msg
            return LaunchResult(True, msg, inj, p.pid, killed)
        except OSError as e:
            if getattr(e, "winerror", None) == 740 or "740" in str(e):
                import ctypes; rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", inj, "", nm, 1)
                if isinstance(rc, int) and rc <= 32: return LaunchResult(False, f"UAC отменён (код {rc})", inj, None, killed)
                return LaunchResult(True, "GreenLuma запущена через UAC. Подтвердите диалог.", inj, None, killed)
            raise
    except OSError as e: return LaunchResult(False, f"Ошибка: {e}", inj, None, killed)
