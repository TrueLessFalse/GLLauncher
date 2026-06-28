"""Steam Store API — мультирегиональный поиск RU+US."""
from __future__ import annotations
import json, logging, socket, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 12
DEFAULT_SEARCH_CCS = ["RU", "US"]
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}

@dataclass
class SearchResult:
    appid: int; name: str; tiny_image: str = ""; price: Optional[str] = None
    platforms: List[str] = field(default_factory=list); available_in: List[str] = field(default_factory=list)
    @property
    def store_url(self): return f"https://store.steampowered.com/app/{self.appid}"
    @property
    def steamdb_url(self): return f"https://steamdb.info/app/{self.appid}"
    @property
    def is_ru_unavailable(self): return bool(self.available_in) and "RU" not in self.available_in
    @property
    def regions_label(self):
        if not self.available_in: return "—"
        if "RU" in self.available_in and "US" in self.available_in: return "RU+US"
        if "RU" in self.available_in: return "RU"
        if "US" in self.available_in: return "US only"
        return "+".join(self.available_in)

@dataclass
class DlcInfo:
    appid: int; name: str; header_image: str = ""; release_date: str = ""; loaded_cc: str = ""
    @property
    def store_url(self): return f"https://store.steampowered.com/app/{self.appid}"
    @property
    def steamdb_url(self): return f"https://steamdb.info/app/{self.appid}"
    @property
    def is_ru_unavailable(self): return bool(self.loaded_cc) and self.loaded_cc != "RU"

@dataclass
class GameDetails:
    appid: int; name: str; header_image: str = ""; short_description: str = ""
    developers: List[str] = field(default_factory=list); publishers: List[str] = field(default_factory=list)
    release_date: str = ""; dlc: List[DlcInfo] = field(default_factory=list)
    loaded_cc: str = ""; available_in: List[str] = field(default_factory=list)

class SteamApiError(Exception): pass
class SteamApiRateLimitError(SteamApiError): pass
class SteamApiNetworkError(SteamApiError): pass

def _http_get_json(url, timeout=DEFAULT_TIMEOUT):
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp: raw = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 429: raise SteamApiRateLimitError("Steam временно отклоняет запросы (HTTP 429).")
        raise SteamApiError(f"HTTP {e.code}: {e.reason}") from e
    except (socket.timeout, urllib.error.URLError) as e: raise SteamApiNetworkError(f"Нет соединения: {e}") from e
    if not raw: raise SteamApiError("Пустой ответ")
    try: return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e: raise SteamApiError(f"JSON: {e}") from e

def search_apps(term, language="russian", cc="RU"):
    term = (term or "").strip()
    if not term: return []
    url = f"https://store.steampowered.com/api/storesearch/?{urllib.parse.urlencode({'term':term,'l':language,'cc':cc})}"
    data = _http_get_json(url)
    results = []
    for it in data.get("items") or []:
        aid = it.get("id")
        try: aid = int(aid)
        except: continue
        po = it.get("price") or {}; ps = None
        if po.get("final") is not None:
            try: ps = f"{po['final']/100:.2f} {po.get('currency','')}".strip()
            except: pass
        plat = []
        sp = it.get("platforms") or {}
        if sp.get("windows"): plat.append("Windows")
        if sp.get("mac"): plat.append("macOS")
        if sp.get("linux"): plat.append("Linux")
        results.append(SearchResult(appid=aid, name=it.get("name",f"App {aid}").strip(), tiny_image=it.get("tiny_image",""), price=ps, platforms=plat, available_in=[cc]))
    return results

def search_apps_multi_cc(term, language="russian", ccs=None):
    if ccs is None: ccs = DEFAULT_SEARCH_CCS
    if not ccs: ccs = ["RU"]
    term = (term or "").strip()
    if not term: return []
    per_cc = {}
    def _do(cc):
        try: return cc, search_apps(term, language, cc), None
        except SteamApiError as e: return cc, [], e
    with ThreadPoolExecutor(max_workers=min(4,len(ccs))) as ex:
        for fut in as_completed([ex.submit(_do, cc) for cc in ccs]):
            cc, res, exc = fut.result()
            if exc: log.warning("Поиск %s: %s", cc, exc); continue
            per_cc[cc] = res
    if not per_cc: raise SteamApiError("Поиск не удался ни в одном регионе")
    merged = {}
    for cc in ccs:
        if cc not in per_cc: continue
        for r in per_cc[cc]:
            if r.appid in merged:
                e = merged[r.appid]
                if cc not in e.available_in: e.available_in.append(cc)
                if not e.price and r.price: e.price = r.price
                if not e.tiny_image and r.tiny_image: e.tiny_image = r.tiny_image
            else: merged[r.appid] = r
    order = []
    for cc in ccs:
        if cc not in per_cc: continue
        for r in per_cc[cc]:
            if r.appid not in order: order.append(r.appid)
    return [merged[a] for a in order if a in merged]

def get_app_details(appid, language="russian", cc="RU"):
    url = f"https://store.steampowered.com/api/appdetails?{urllib.parse.urlencode({'appids':appid,'l':language,'cc':cc})}"
    data = _http_get_json(url)
    payload = data.get(str(appid)) or {}
    if not payload.get("success"): return None
    d = payload.get("data") or {}
    rel = d.get("release_date") or {}
    return GameDetails(appid=appid, name=d.get("name",f"App {appid}"), header_image=d.get("header_image",""),
        short_description=d.get("short_description",""), developers=d.get("developers") or [],
        publishers=d.get("publishers") or [], release_date=rel.get("date",""),
        dlc=[DlcInfo(appid=aid, name=f"DLC {aid}") for aid in (d.get("dlc") or [])], loaded_cc=cc)

def get_app_details_auto_cc(appid, language="russian", ccs=None, known_available_in=None):
    if ccs is None: ccs = DEFAULT_SEARCH_CCS
    order = [cc for cc in ccs if cc in (known_available_in or ccs)] + [cc for cc in ccs if cc not in (known_available_in or [])]
    if "RU" in order: order.remove("RU"); order.insert(0, "RU")
    for cc in order:
        try: d = get_app_details(appid, language, cc)
        except SteamApiRateLimitError: raise
        except SteamApiError: continue
        if d:
            d.loaded_cc = cc
            if known_available_in: d.available_in = list(known_available_in)
            return d
    return None

def fetch_dlc_info_auto_cc(dlc_ids, language="russian", ccs=None):
    if ccs is None: ccs = DEFAULT_SEARCH_CCS
    out = []
    for aid in dlc_ids:
        d = None
        for cc in ccs:
            try: d = get_app_details(aid, language, cc)
            except SteamApiRateLimitError: raise
            except SteamApiError: d = None; continue
            if d: d.loaded_cc = cc; break
        if d: out.append(DlcInfo(appid=d.appid, name=d.name, header_image=d.header_image, release_date=d.release_date, loaded_cc=d.loaded_cc))
        else: out.append(DlcInfo(appid=aid, name=f"DLC {aid} (недоступно)"))
    return out

def get_full_game_with_dlc_auto_cc(appid, language="russian", ccs=None, known_available_in=None):
    if ccs is None: ccs = DEFAULT_SEARCH_CCS
    g = get_app_details_auto_cc(appid, language, ccs, known_available_in)
    if g is None: return None
    if g.dlc: g.dlc = fetch_dlc_info_auto_cc([d.appid for d in g.dlc], language, ccs)
    return g
