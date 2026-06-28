"""Потокобезопасная модель списка загрузки."""
from __future__ import annotations
import json, os, threading
from dataclasses import dataclass, asdict
from typing import Callable, List, Optional

@dataclass
class DownloadItem:
    appid: int; name: str; kind: str = "app"
    def display(self): tag = "DLC" if self.kind == "dlc" else "APP"; return f"[{tag}] {self.appid}  —  {self.name}"

class DownloadList:
    def __init__(self):
        self._items: List[DownloadItem] = []
        self._lock = threading.RLock()
        self._listeners: List[Callable[[], None]] = []
    def add_listener(self, cb): self._listeners.append(cb)
    def _notify(self):
        for cb in list(self._listeners):
            try: cb()
            except: pass
    def add(self, appid, name, kind="app"):
        with self._lock:
            for it in self._items:
                if it.appid == appid: return False
            self._items.append(DownloadItem(appid=appid, name=name, kind=kind))
            self._notify(); return True
    def remove_at(self, index):
        with self._lock:
            if 0 <= index < len(self._items):
                r = self._items.pop(index); self._notify(); return r
            return None
    def clear(self):
        with self._lock: self._items.clear(); self._notify()
    def move_up(self, index):
        with self._lock:
            if 1 <= index < len(self._items):
                self._items[index-1], self._items[index] = self._items[index], self._items[index-1]; self._notify()
    def move_down(self, index):
        with self._lock:
            if 0 <= index < len(self._items)-1:
                self._items[index+1], self._items[index] = self._items[index], self._items[index+1]; self._notify()
    def items(self):
        with self._lock: return list(self._items)
    def appids(self):
        with self._lock: return [it.appid for it in self._items]
    def __len__(self):
        with self._lock: return len(self._items)
    def contains(self, appid):
        with self._lock: return any(it.appid == appid for it in self._items)
    def save_to_file(self, path):
        with self._lock: payload = {"version":1,"items":[asdict(it) for it in self._items]}
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    def load_from_file(self, path):
        if not os.path.exists(path): return
        try:
            with open(path, "r", encoding="utf-8") as f: payload = json.load(f)
        except: return
        seen = set()
        new = []
        for it in (payload.get("items") or []):
            try: aid = int(it.get("appid"))
            except: continue
            if aid in seen: continue
            seen.add(aid)
            new.append(DownloadItem(appid=aid, name=str(it.get("name",f"App {aid}")), kind=str(it.get("kind","app"))))
        with self._lock: self._items = new
        self._notify()
