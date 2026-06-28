"""Импорт/очистка файлов AppList."""
from __future__ import annotations
import os, re
from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass
class ScannedFile:
    index: int; file_name: str; file_path: str; appid: int; raw_content: str; error: str = ""

@dataclass
class ScanResult:
    files: List[ScannedFile] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    @property
    def valid_appids(self):
        return [f.appid for f in self.files if f.appid is not None and not f.error]
    @property
    def has_errors(self): return any(f.error for f in self.files) or bool(self.warnings)

def scan_applist_dir(d):
    result = ScanResult()
    if not d or not os.path.isdir(d):
        result.warnings.append("Папка не существует"); return result
    try: entries = sorted(os.listdir(d))
    except OSError as e: result.warnings.append(str(e)); return result
    txt = [e for e in entries if e.lower().endswith(".txt")]
    if not txt: result.warnings.append("Нет .txt файлов"); return result
    nre = re.compile(r"^(\d+)\.txt$", re.I)
    for fn in txt:
        fp = os.path.join(d, fn); m = nre.match(fn); idx = int(m.group(1)) if m else None
        try:
            with open(fp, "r", encoding="utf-8") as f: raw = f.read()
        except OSError as e: result.files.append(ScannedFile(idx, fn, fp, None, "", str(e))); continue
        s = raw.strip(); appid = None; err = None
        if not s: err = "Пустой"
        else:
            mn = re.search(r"\d+", s.splitlines()[0].strip())
            if mn:
                try: appid = int(mn.group(0))
                except: err = "Не число"
            else: err = "Нет числа"
        result.files.append(ScannedFile(idx, fn, fp, appid, s, err))
    return result

def clear_applist_txt_files(d):
    removed, errors = 0, []
    if not os.path.isdir(d): return 0, ["Папка не существует"]
    try:
        for n in os.listdir(d):
            if not n.lower().endswith(".txt"): continue
            try: os.remove(os.path.join(d, n)); removed += 1
            except OSError as e: errors.append(f"{n}: {e}")
    except OSError as e: errors.append(str(e))
    return removed, errors
