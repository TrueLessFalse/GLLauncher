"""Settings, поиск Steam.exe, генерация DLLInjector.ini."""
from __future__ import annotations
import json, os, platform, sys, re, shutil
from dataclasses import asdict, dataclass, field
from typing import List, Optional

def _default_applist() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "AppList")
    if platform.system() == "Windows":
        return "C:\\AppList"
    return os.path.join(os.path.expanduser("~"), "AppList")

def _settings_dir() -> str:
    if is_portable_mode():
        d = os.path.join(_executable_dir(), "data")
    elif platform.system() == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "SteamLister")
    else:
        d = os.path.join(os.path.expanduser("~"), ".steamlister")
    os.makedirs(d, exist_ok=True)
    return d

def _executable_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()

def is_portable_mode() -> bool:
    return os.path.isfile(os.path.join(_executable_dir(), "portable.txt"))

def settings_file_path() -> str:
    return os.path.join(_settings_dir(), "settings.json")

def state_file_path() -> str:
    return os.path.join(_settings_dir(), "steamlister_state.json")

def log_file_path() -> str:
    return os.path.join(_settings_dir(), "steamlister.log")

DEFAULT_UPDATE_URL = "https://cs.rin.ru/forum/viewtopic.php?f=10&t=103709"
NORMALMODE_FILES = ["DLLInjector.exe","DLLInjector.ini","GreenLuma_2026_x64.dll","GreenLuma_2026_x86.dll","GreenLumaSettings_2026.exe"]
_VERSION_RE = re.compile(r"GreenLuma[\s_]+2026[\s_]*v?(\d+(?:\.\d+)+)", re.I)

@dataclass
class Settings:
    applist_dir: str = field(default_factory=_default_applist)
    greenluma_normalmode_dir: str = ""
    steam_exe: str = ""
    steam_language: str = "russian"
    steam_country: str = "RU"
    search_ccs: List[str] = field(default_factory=lambda: ["RU", "US"])
    window_geometry: str = ""
    window_state: str = "normal"
    tutorial_completed: bool = False
    last_update_check: float = 0.0
    last_known_version: str = ""
    update_url: str = ""
    app_update_url: str = "https://raw.githubusercontent.com/TrueLessFalse/GLLauncher/refs/heads/main/version.json"
    theme_settings: dict = field(default_factory=dict)

    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        s = cls()
        if not isinstance(data, dict): return s
        for k in ("applist_dir","greenluma_normalmode_dir","steam_exe","steam_language","steam_country","window_geometry","window_state","update_url","app_update_url"):
            if k in data and isinstance(data[k], str): setattr(s, k, data[k])
        if "search_ccs" in data and isinstance(data["search_ccs"], list):
            s.search_ccs = [str(c).upper() for c in data["search_ccs"] if c] or ["RU","US"]
        if "tutorial_completed" in data: s.tutorial_completed = bool(data["tutorial_completed"])
        if "last_update_check" in data: s.last_update_check = float(data.get("last_update_check",0))
        if "last_known_version" in data: s.last_known_version = str(data.get("last_known_version",""))
        if "theme_settings" in data and isinstance(data["theme_settings"], dict): s.theme_settings = data["theme_settings"]
        return s
    def save(self):
        p = settings_file_path(); tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    @classmethod
    def load(cls) -> "Settings":
        p = settings_file_path()
        if not os.path.exists(p): return cls()
        try:
            with open(p, "r", encoding="utf-8") as f: return cls.from_dict(json.load(f))
        except: return cls()

_STEAM_PATHS = [r"C:\Program Files (x86)\Steam\Steam.exe", r"C:\Program Files\Steam\Steam.exe", r"D:\Steam\Steam.exe"]

def find_steam_exe() -> Optional[str]:
    if platform.system() != "Windows": return None
    try:
        import winreg
        for hive, path in [(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"), (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam")]:
            try:
                with winreg.OpenKey(hive, path) as key:
                    val, _ = winreg.QueryValueEx(key, "SteamPath" if hive == winreg.HKEY_CURRENT_USER else "InstallPath")
                    c = os.path.join(val, "Steam.exe")
                    if os.path.isfile(c): return os.path.abspath(c)
            except: pass
    except: pass
    for p in _STEAM_PATHS:
        if os.path.isfile(p): return os.path.abspath(p)
    return None

def resolve_normalmode_dir(path: str) -> Optional[str]:
    if not path or not os.path.isdir(path): return None
    if os.path.isfile(os.path.join(path, "DLLInjector.exe")): return os.path.abspath(path)
    c = os.path.join(path, "NormalMode")
    if os.path.isdir(c) and os.path.isfile(os.path.join(c, "DLLInjector.exe")): return os.path.abspath(c)
    try:
        for n in os.listdir(path):
            if n.lower().startswith("greenluma"):
                nm = os.path.join(path, n, "NormalMode")
                if os.path.isdir(nm) and os.path.isfile(os.path.join(nm, "DLLInjector.exe")): return os.path.abspath(nm)
    except: pass
    return None

def check_normalmode_files(d: str):
    missing, found = [], []
    for f in NORMALMODE_FILES:
        (found if os.path.isfile(os.path.join(d, f)) else missing).append(f)
    return missing, found

def find_dll_injector(d: str) -> Optional[str]:
    p = os.path.join(d, "DLLInjector.exe")
    return p if os.path.isfile(p) else None

def find_greenluma_dll(d: str) -> Optional[str]:
    p = os.path.join(d, "GreenLuma_2026_x64.dll")
    return p if os.path.isfile(p) else None

_INI_TEMPLATE = """[DllInjector]
AllowMultipleInstancesOfDLLInjector = 0
UseFullPathsFromIni = 1

# Exe to start
Exe = {steam_exe}
CommandLine =

# Dll to inject
Dll = {dll_path}

# Export to call in dll
Export = Init

# Check if call to export returned positive value
CheckReturnValue = 0

# Wait for started exe to close before exiting the DllInjector process.
WaitForProcessTermination = 0

# Set a fake parent process
EnableFakeParentProcess = 1
FakeParentProcess = explorer.exe

# Enable security mitigations on child process.
EnableMitigationsOnChildProcess = 0

DEP = 1
SEHOP = 1
HeapTerminate = 1
ForceRelocateImages = 1
BottomUpASLR = 1
HighEntropyASLR = 1
RelocationsRequired = 1
StrictHandleChecks = 0
Win32kSystemCallDisable = 0
ExtensionPointDisable = 1
CFG = 1
CFGExportSuppression = 1
StrictCFG = 1
DynamicCodeDisable = 0
DynamicCodeAllowOptOut = 0
BlockNonMicrosoftBinaries = 0
FontDisable = 1
NoRemoteImages = 1
NoLowLabelImages = 1
PreferSystem32 = 0
RestrictIndirectBranchPrediction = 1
SpeculativeStoreBypassDisable = 0
ShadowStack = 0
ContextIPValidation = 0
BlockNonCETEHCONT = 0
BlockFSCTL = 0

# Number to files to create
CreateFiles = 1

# Name of the file(s) to create
FileToCreate_1 = StealthMode.bin
FileToCreate_2 =

#Patch an x86 exe to enable IMAGE_FILE_LARGE_ADDRESS_AWARE
Use4GBPatch = 0
FileToPatch_1 = 

BootImage =
BootImageWidth = 0
BootImageHeight = 0
BootImageXOffest = 0
BootImageYOffest = 0
"""

def generate_dllinjector_ini(steam_exe: str, dll_path: str) -> str:
    return _INI_TEMPLATE.format(steam_exe=steam_exe, dll_path=dll_path)

def write_dllinjector_ini(d: str, steam_exe: str, dll_path: str) -> str:
    p = os.path.join(d, "DLLInjector.ini")
    if os.path.isfile(p):
        b = p + ".bak_steamlister"
        if not os.path.isfile(b):
            try: shutil.copy2(p, b)
            except: pass
    c = generate_dllinjector_ini(steam_exe, dll_path)
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f: f.write(c)
        os.replace(tmp, p)
    except:
        try: os.unlink(tmp)
        except: pass
        raise
    return p

def get_installed_version(d: str):
    if not d or not os.path.isdir(d): return "", ""
    parent = os.path.dirname(d)
    for name in (os.path.basename(parent), os.path.basename(d)):
        m = _VERSION_RE.search(name)
        if m: return m.group(1), "folder"
    for tp in [os.path.join(parent, "GreenLuma2026.txt"), os.path.join(d, "GreenLuma2026.txt")]:
        if os.path.isfile(tp):
            try:
                with open(tp, "r", encoding="utf-8", errors="replace") as f:
                    m = _VERSION_RE.search(f.read(4096))
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
                                _fields_ = [("s",wintypes.DWORD)]*13
                            ffi = ctypes.cast(pv, ctypes.POINTER(FFI)).contents
                            if ffi.s == 0xFEEF04BD:
                                v = f"{(ffi.s>>16)&0xFFFF}.{ffi.s&0xFFFF}.{(ffi.s>>16)&0xFFFF}.{ffi.s&0xFFFF}"
                                return v, "exe"
            except: pass
    return "", ""
