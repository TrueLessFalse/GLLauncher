"""Автообновление программы."""
from __future__ import annotations
import json, logging, os, platform, subprocess, sys, tempfile, urllib.error, urllib.request
from dataclasses import dataclass
from typing import Optional
log = logging.getLogger(__name__)
APP_VERSION = "3.0.0"
DEFAULT_VERSION_URL = "https://raw.githubusercontent.com/TrueLessFalse/GLLauncher/refs/heads/main/version.json"
FETCH_TIMEOUT = 15
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

@dataclass
class AppUpdateInfo:
    has_update: bool = False; current_version: str = ""; latest_version: str = ""
    download_url: str = ""; release_notes: str = ""; min_app_version: str = ""
    error: Optional[str] = None; can_auto_update: bool = True
    @property
    def status_text(self):
        if self.error: return f"⚠ {self.error}"
        if not self.latest_version: return "Нет данных"
        if self.has_update: return f"✨ Обновление: {self.current_version} → {self.latest_version}"
        return f"✓ Последняя: {self.current_version}"

def _pv(v):
    try: return tuple(int(x) for x in v.strip().split("."))
    except: return (0,)

def compare_app_versions(v1, v2):
    p1, p2 = _pv(v1), _pv(v2)
    ml = max(len(p1), len(p2)); p1 = p1 + (0,)*(ml-len(p1)); p2 = p2 + (0,)*(ml-len(p2))
    return -1 if p1 < p2 else (1 if p1 > p2 else 0)

def check_for_app_updates(version_url=DEFAULT_VERSION_URL, current_version=APP_VERSION):
    info = AppUpdateInfo(); info.current_version = current_version
    try:
        req = urllib.request.Request(version_url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e: info.error = f"HTTP {e.code}"; return info
    except (urllib.error.URLError, OSError) as e: info.error = f"Сеть: {e}"; return info
    except json.JSONDecodeError as e: info.error = f"JSON: {e}"; return info
    if not isinstance(data, dict): info.error = "Не объект"; return info
    info.latest_version = str(data.get("version", "")).strip()
    info.download_url = str(data.get("download_url", "")).strip()
    info.release_notes = str(data.get("release_notes", "")).strip()
    info.min_app_version = str(data.get("min_app_version", "")).strip()
    if not info.latest_version: info.error = "Нет 'version'"; return info
    info.has_update = compare_app_versions(current_version, info.latest_version) < 0
    info.can_auto_update = bool(info.download_url)
    return info

def download_and_install_update(info, progress_cb=None):
    def _log(m):
        log.info(m)
        if progress_cb:
            try: progress_cb(m)
            except: pass
    if not info.has_update: return False, "Обновление не требуется."
    if not info.download_url: return False, "Нет URL."
    if not info.can_auto_update: return False, "Нет URL."

    # Определяем путь к текущему .exe (только в frozen режиме)
    if getattr(sys, "frozen", False):
        current_exe = os.path.abspath(sys.executable)
        exe_name = os.path.basename(current_exe)
    else:
        # При запуске из исходников — нельзя автообновить
        return False, "Автообновление работает только в собранном .exe. Скачайте новую версию вручную."

    _log(f"Текущий файл: {current_exe}")
    _log(f"Скачиваю версию {info.latest_version}…")

    td = tempfile.gettempdir()
    new_path = os.path.join(td, exe_name + "_new")

    try:
        req = urllib.request.Request(info.download_url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            last_log = 0
            with open(new_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    # Логируем не чаще раза в секунду
                    now = __import__("time").monotonic()
                    if now - last_log >= 1.0 or downloaded == total:
                        if total > 0:
                            pct = downloaded * 100 // total
                            _log(f"Скачано {downloaded // 1024} КБ / {total // 1024} КБ ({pct}%)")
                        else:
                            _log(f"Скачано {downloaded // 1024} КБ…")
                        last_log = now
    except (urllib.error.HTTPError, OSError) as e:
        return False, f"Ошибка скачивания: {e}"

    _log("Скачивание завершено.")
    _log("Создаю скрипт обновления…")

    bp = os.path.join(td, "gllauncher_update.bat")
    bat_content = f"""@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
echo Updating {exe_name}...

REM Ждём закрытия программы (максимум 30 секунд)
set /a count=0
:wait
tasklist /FI "IMAGENAME eq {exe_name}" 2>nul | find /i "{exe_name}" >nul 2>nul
if !errorlevel! equ 0 (
    set /a count+=1
    if !count! geq 30 goto :force
    timeout /t 1 /nobreak >nul
    goto :wait
)

:replace
echo Replacing file...
copy /Y "{new_path}" "{current_exe}"
if !errorlevel! neq 0 (
    echo ERROR: Failed to replace file
    echo Source: {new_path}
    echo Target: {current_exe}
    pause
    goto :cleanup
)

echo Starting updated program...
start "" "{current_exe}"

:cleanup
del "{new_path}" >nul 2>&1
del "%~f0" >nul 2>&1
exit

:force
echo Forcing close...
taskkill /F /IM "{exe_name}" >nul 2>&1
timeout /t 2 /nobreak >nul
goto :replace
"""

    try:
        with open(bp, "w", encoding="utf-8") as f:
            f.write(bat_content)
    except OSError as e:
        return False, f"Не удалось создать скрипт: {e}"

    _log("Запускаю скрипт обновления…")
    _log("Программа будет закрыта для замены файла.")

    try:
        subprocess.Popen(
            ["cmd", "/c", bp],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        return False, f"Не удалось запустить скрипт: {e}"

    return True, f"Обновление {info.latest_version} скачано. Программа перезапустится."

def open_download_page(url):
    try:
        import webbrowser; webbrowser.open(url); return True
    except: return False
