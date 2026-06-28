"""Получение версии GreenLuma с cs.rin.ru — обход security check."""
from __future__ import annotations
import re, sys, time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple
try: import requests
except ImportError as e: raise ImportError("pip install requests") from e
try: from bs4 import BeautifulSoup
except: BeautifulSoup = None

DEFAULT_URL = "https://cs.rin.ru/forum/viewtopic.php?f=10&t=103709"
DEFAULT_TIMEOUT = 20.0
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_VRE = r"\d+(?:\.\d+){1,3}"
_FULL = re.compile(rf"GreenLuma\s+(?P<product>\d{{4}})\s+(?P<version>{_VRE})", re.I)
_NEAR = re.compile(rf"GreenLuma(?:\s+\d{{4}})?\s+(?P<version>{_VRE})", re.I)
_ATTACH = re.compile(rf"GreenLuma[_ ]+\d{{4}}[_ ]+(?P<version>{_VRE})", re.I)

@dataclass(frozen=True)
class GreenlumaInfo:
    version: str; product_name: str; full_title: str; page_title: str; url: str; source: str; fetched_at: str
    def as_dict(self): return {"version": self.version, "product_name": self.product_name, "full_title": self.full_title, "page_title": self.page_title, "url": self.url, "source": self.source, "fetched_at": self.fetched_at}

class GreenlumaFetchError(RuntimeError): pass

def _build_session(session, ua):
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", ua)
    s.headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
    s.headers.setdefault("Accept-Language", "ru-RU,ru;q=0.9,en;q=0.8")
    return s

def _bypass_security(session, url, timeout):
    r1 = session.get(url, allow_redirects=False, timeout=timeout)
    if r1.status_code == 200: return r1
    if r1.status_code != 401: raise GreenlumaFetchError(f"Статус {r1.status_code}")
    tm = re.search(r'securitytoken=([^";\s]+)', r1.text)
    em = re.search(r"securitytoken_expiration=(\d+)", r1.text)
    if not tm or not em: raise GreenlumaFetchError("Не удалось извлечь securitytoken")
    session.cookies.set("securitytoken", tm.group(1), domain="cs.rin.ru", path="/", secure=True)
    session.cookies.set("securitytoken_expiration", em.group(1), domain="cs.rin.ru", path="/", secure=True)
    su = url.replace("cs.rin.ru/forum/", "cs.rin.ru/securitycheck/forum/", 1)
    r2 = session.get(su, allow_redirects=True, timeout=timeout)
    if r2.status_code != 200: raise GreenlumaFetchError(f"Security check не пройден ({r2.status_code})")
    r3 = session.get(url, allow_redirects=True, timeout=timeout)
    if r3.status_code != 200: raise GreenlumaFetchError(f"Статус {r3.status_code}")
    return r3

def _parse_version(html):
    pt = ""
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if m: pt = re.sub(r"\s+", " ", m.group(1)).strip()
    if pt:
        m = _FULL.search(pt)
        if m: return m.group("version"), f"GreenLuma {m.group('product')}", f"GreenLuma {m.group('product')} {m.group('version')}", "title", pt
    for block in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S | re.I):
        t = re.sub(r"<[^>]+>", "", block); t = re.sub(r"\s+", " ", t).strip()
        m = _FULL.search(t) or _NEAR.search(t)
        if m:
            v = m.group("version"); pm = re.search(r"GreenLuma\s+(\d{4})", t, re.I)
            p = f"GreenLuma {pm.group(1)}" if pm else "GreenLuma"
            return v, p, f"{p} {v}", "h2", pt
    ms = re.search(rf"Заголовок сообщения:\s*</b>\s*(GreenLuma\s+\d{{4}}\s+{_VRE})", html, re.I)
    if ms:
        f = re.sub(r"\s+", " ", ms.group(1)).strip(); m = _FULL.search(f)
        if m: return m.group("version"), f"GreenLuma {m.group('product')}", f, "post", pt
    ma = _ATTACH.search(html)
    if ma:
        v = ma.group("version"); ym = re.search(r"GreenLuma[_ ]+(\d{4})", ma.group(0), re.I)
        p = f"GreenLuma {ym.group(1)}" if ym else "GreenLuma"
        return v, p, f"{p} {v}", "attach", pt
    raise GreenlumaFetchError("Версия не извлечена")

def get_greenluma_version(url=DEFAULT_URL, *, timeout=DEFAULT_TIMEOUT, session=None, user_agent=DEFAULT_UA, retries=2, retry_delay=1.5):
    s = _build_session(session, user_agent); last = None
    for a in range(retries + 1):
        try:
            r = _bypass_security(s, url, timeout)
            v, p, f, src, pt = _parse_version(r.text)
            return GreenlumaInfo(version=v, product_name=p, full_title=f, page_title=pt, url=r.url, source=src, fetched_at=datetime.now(timezone.utc).isoformat())
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last = e
            if a < retries: time.sleep(retry_delay)
            continue
        except GreenlumaFetchError: raise
        except Exception as e: raise GreenlumaFetchError(f"Ошибка: {e}") from e
    raise GreenlumaFetchError(f"Превышено попыток ({retries+1}). {last}")

if __name__ == "__main__":
    try:
        info = get_greenluma_version()
        print(info.version if "--json" not in sys.argv else __import__("json").dumps(info.as_dict(), ensure_ascii=False, indent=2))
    except GreenlumaFetchError as e: print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)
