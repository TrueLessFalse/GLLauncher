"""Кэш обложек игр."""
from __future__ import annotations
import hashlib, logging, os, socket, threading, urllib.error, urllib.request
from typing import Optional
log = logging.getLogger(__name__)
def _cache_dir():
    try:
        from config import cache_dir; return cache_dir()
    except:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "covers")
_HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
def _key(url):
    h = hashlib.md5(url.encode()).hexdigest()
    ext = ".jpg"
    l = url.lower().split("?")[0]
    if l.endswith(".png"): ext = ".png"
    return h + ext
class ImageCache:
    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir or _cache_dir()
        os.makedirs(self.cache_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._in_flight = {}
        self._pil = False
        try:
            from PIL import Image; self._pil = True
        except ImportError: pass
    @property
    def pil_available(self): return self._pil
    def get_path(self, url, timeout=8):
        if not url: return None
        k = _key(url); path = os.path.join(self.cache_dir, k)
        if os.path.exists(path) and os.path.getsize(path) > 0: return path
        with self._lock:
            if k in self._in_flight: return None
            self._in_flight[k] = True
        try:
            req = urllib.request.Request(url, headers=_HEAD)
            with urllib.request.urlopen(req, timeout=timeout) as resp: raw = resp.read()
            if raw:
                with open(path, "wb") as f:
                    f.write(raw)
                return path
        except: return None
        finally:
            with self._lock: self._in_flight.pop(k, None)
    def get_pil_image(self, url, size=None, timeout=8):
        if not self._pil: return None
        p = self.get_path(url, timeout)
        if not p: return None
        try:
            from PIL import Image
            img = Image.open(p); img.load()
            if size: img = img.resize(size, Image.LANCZOS)
            return img
        except: return None
