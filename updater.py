"""Проверка обновлений GreenLuma."""
from __future__ import annotations
import logging, os, platform, re, socket, urllib.error, urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple
log = logging.getLogger(__name__)
DEFAULT_UPDATE_URL = "https://cs.rin.ru/forum/viewtopic.php?f=10&t=103709"
FETCH_TIMEOUT = 20
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9,ru;q=0.8"}
_VRE = re.compile(r"GreenLuma[\s_]+2026[\s_]*v?(\d+(?:\.\d+)+)", re.I)

def is_greenluma_version_available():
    try: import greenluma_version, requests; return True
    except: return False

@dataclass
class UpdateInfo:
    has_update: bool = False; installed_version: str = ""; latest_version: str = ""
    installed_source: str = ""; latest_source: str = ""; topic_url: str = ""
    error: Optional[str] = None; last_checked: float = 0.0; raw_title: str = ""
    @property
    def status_text(self):
        if self.error: return f"⚠ {self.error}"
        if not self.latest_version: return "Не удалось определить версию"
        if not self.installed_version: return f"Последняя: {self.latest_version}"
        if self.has_update: return f"✨ Обновление: {self.installed_version} → {self.latest_version}"
        return f"✓ Последняя: {self.installed_version}"

def get_installed_version(d):
    if not d or not os.path.isdir(d): return "", ""
    parent = os.path.dirname(d)
    for name in (os.path.basename(parent), os.path.basename(d)):
        m = _VRE.search(name)
        if m: return m.group(1), "folder"
    for tp in [os.path.join(parent, "GreenLuma2026.txt"), os.path.join(d, "GreenLuma2026.txt")]:
        if os.path.isfile(tp):
            try:
                with open(tp, "r", encoding="utf-8", errors="replace") as f:
                    m = _VRE.search(f.read(4096))
                    if m: return m.group(1), "txt"
            except: pass
    if platform.system() == "Windows":
        ep = os.path.join(d, "DLLInjector.exe")
        if os.path.isfile(ep):
            try:
                import ctypes
                from ctypes import wintypes
                sz = ctypes.windll.version.GetFileVersionInfoSizeW(ep, None)
                if sz:
                    buf = (ctypes.c_char * sz)()
                    if ctypes.windll.version.GetFileVersionInfoW(ep, 0, sz, buf):
                        pv, vl = wintypes.LPVOID(), wintypes.UINT()
                        if ctypes.windll.version.VerQueryValueW(buf, r"\\", ctypes.byref(pv), ctypes.byref(vl)):
                            class FFI(ctypes.Structure):
                                _fields_ = [("s", wintypes.DWORD)] * 13
                            ffi = ctypes.cast(pv, ctypes.POINTER(FFI)).contents
                            if ffi.s == 0xFEEF04BD:
                                return f"{(ffi.s>>16)&0xFFFF}.{ffi.s&0xFFFF}.{(ffi.s>>16)&0xFFFF}.{ffi.s&0xFFFF}", "exe"
            except: pass
    return "", ""

def _parse_v(v):
    m = re.match(r"^(\d+(?:\.\d+)*)(?:-(.+))?$", v.strip())
    if not m: return ((), v)
    try: return (tuple(int(x) for x in m.group(1).split(".")), m.group(2) or "")
    except: return ((), v)

def compare_versions(v1, v2):
    n1, s1 = _parse_v(v1); n2, s2 = _parse_v(v2)
    for a, b in zip(n1, n2):
        if a < b: return -1
        if a > b: return 1
    if len(n1) < len(n2): return -1
    if len(n1) > len(n2): return 1
    if not s1 and s2: return 1
    if s1 and not s2: return -1
    if s1 < s2: return -1
    if s1 > s2: return 1
    return 0

def fetch_with_greenluma_version(url=DEFAULT_UPDATE_URL):
    import greenluma_version
    log.info("greenluma_version: %s", url)
    try:
        info = greenluma_version.get_greenluma_version(url=url, timeout=FETCH_TIMEOUT, retries=2, retry_delay=1.5)
        return info.version, info.page_title
    except greenluma_version.GreenlumaFetchError as e: raise OSError(str(e)) from e

def fetch_with_urllib(url=DEFAULT_UPDATE_URL):
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            try: html = raw.decode("utf-8")
            except: html = raw.decode("cp1251", errors="replace")
    except urllib.error.HTTPError as e: raise OSError(f"HTTP {e.code}") from e
    except (socket.timeout, urllib.error.URLError) as e: raise OSError(f"Нет соединения: {e}") from e
    tm = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I | re.S)
    rt = tm.group(1).strip() if tm else ""
    if rt:
        m = _VRE.search(rt)
        if m: return m.group(1), rt
    all_v = _VRE.findall(html)
    if all_v: return all_v[-1], rt
    return "", rt

def fetch_cs_rin_ru_topic(url=DEFAULT_UPDATE_URL):
    if is_greenluma_version_available():
        try:
            v, t = fetch_with_greenluma_version(url)
            if v: return v, t
        except: pass
    return fetch_with_urllib(url)

def check_for_updates(normalmode_dir="", update_url="", use_cache=True, cached_version="", cache_age_seconds=0, cache_ttl_seconds=86400):
    info = UpdateInfo()
    if update_url: info.topic_url = update_url
    elif not update_url: info.topic_url = DEFAULT_UPDATE_URL
    if normalmode_dir:
        v, s = get_installed_version(normalmode_dir)
        info.installed_version = v; info.installed_source = s
    import time; info.last_checked = time.time()
    lv = ""; ls = ""
    if use_cache and cached_version and cache_age_seconds < cache_ttl_seconds:
        lv = cached_version; ls = "cache"
    else:
        try:
            lv, rt = fetch_cs_rin_ru_topic(info.topic_url)
            info.raw_title = rt
            ls = "greenluma_version" if is_greenluma_version_available() else "urllib"
        except OSError as e:
            info.error = str(e)
            if cached_version: lv = cached_version; ls = "cache (stale)"
    info.latest_version = lv; info.latest_source = ls
    if lv and info.installed_version: info.has_update = compare_versions(info.installed_version, lv) < 0
    elif lv and not info.installed_version: info.has_update = True
    return info

def open_topic_in_browser(url=DEFAULT_UPDATE_URL):
    try:
        import webbrowser; webbrowser.open(url); return True
    except: return False
