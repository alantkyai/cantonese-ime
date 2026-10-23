"""Explicit current-user COM registration and native registration diagnostics.

No elevation, default keyboard changes, service installation or autorun entries.
Persistent TSF registration may fail on Windows when machine writes are needed;
the exact HRESULT is preserved rather than silently requesting elevation.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes as w
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import struct
import winreg

ROOT = Path(__file__).resolve().parents[1]
CLSID = "{67718E6F-49A1-4F54-88D6-30578FC70C5D}"
PROFILE = "{A7136205-2245-45CC-A6AA-702B3F2E8D42}"
CLASS_KEY = rf"Software\Classes\CLSID\{CLSID}"
TIP_KEY = rf"Software\Microsoft\CTF\TIP\{CLSID}"


def elevated() -> bool:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD)]
    token = w.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        value, length = w.DWORD(), w.DWORD()
        if not advapi.GetTokenInformation(token, 20, ctypes.byref(value), ctypes.sizeof(value), ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        return bool(value.value)
    finally:
        kernel.CloseHandle(token)


def inspect_key(hive, path):
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            def read(key):
                values = {}
                count, value_count, _ = winreg.QueryInfoKey(key)
                for index in range(value_count):
                    name, data, kind = winreg.EnumValue(key, index)
                    values[name] = {"value": data.hex() if isinstance(data, bytes) else data, "type": kind}
                children = {}
                for index in range(count):
                    name = winreg.EnumKey(key, index)
                    with winreg.OpenKey(key, name) as child:
                        children[name] = read(child)
                return {"values": values, "children": children}
            return read(key)
    except FileNotFoundError:
        return None


def snapshot():
    return {name: {"com": inspect_key(hive, CLASS_KEY), "tip": inspect_key(hive, TIP_KEY)}
            for name, hive in (("HKCU", winreg.HKEY_CURRENT_USER), ("HKLM", winreg.HKEY_LOCAL_MACHINE))}


def verify_dll(path):
    data = path.read_bytes()
    if data[:2] != b"MZ" or len(data) < 64:
        raise ValueError("Invalid DLL image.")
    offset = struct.unpack_from("<I", data, 60)[0]
    if data[offset:offset + 4] != b"PE\0\0" or struct.unpack_from("<H", data, offset + 4)[0] != 0x8664:
        raise ValueError("DLL must be AMD64.")
    return hashlib.sha256(data).hexdigest()


def com_only(path):
    if inspect_key(winreg.HKEY_CURRENT_USER, CLASS_KEY) is not None:
        raise ValueError("Current-user COM class already exists; refusing overwrite.")
    # Writes only the project-owned, previously absent CLSID under HKCU.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CLASS_KEY, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "Cantonese IME (Preview)")
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CLASS_KEY + r"\InprocServer32", 0,
                            winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(path))
        winreg.SetValueEx(key, "ThreadingModel", 0, winreg.REG_SZ, "Apartment")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "register", "register-com-only", "unregister-com-only", "unregister"))
    parser.add_argument("--dll", type=Path, default=ROOT / ".local/native/build-x64/CantoneseIME.dll")
    parser.add_argument("--log", type=Path, default=ROOT / ".local/native/registration.jsonl")
    args = parser.parse_args()
    if os.name != "nt" or struct.calcsize("P") != 8:
        raise RuntimeError("Use x64 Python on Windows.")
    before = snapshot()
    entry = {"time_utc": datetime.now(timezone.utc).isoformat(), "action": args.action,
             "pid": os.getpid(), "token_elevated": elevated(), "clsid": CLSID,
             "profile": PROFILE, "before": before}
    try:
        if args.action != "status":
            if entry["token_elevated"]:
                raise RuntimeError("Run without administrator elevation for this current-user preview.")
            path = args.dll.resolve(strict=True)
            path.relative_to(ROOT)
            entry.update(dll=str(path), dll_sha256=verify_dll(path))
            if args.action == "register-com-only":
                com_only(path)
                entry["result"] = "HKCU COM class only; no persistent TSF profile registered"
            elif args.action == "unregister-com-only":
                current = inspect_key(winreg.HKEY_CURRENT_USER, CLASS_KEY)
                if current is None:
                    raise RuntimeError("The project COM class is not registered for this account.")
                if set(current["children"]) != {"InprocServer32"}:
                    raise RuntimeError("Unexpected COM subkeys; refusing removal.")
                inproc = current["children"]["InprocServer32"]
                if inproc["children"] or Path(inproc["values"].get("", {}).get("value", "")).resolve() != path:
                    raise RuntimeError("Registration does not point at the requested project DLL.")
                winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, CLASS_KEY + r"\InprocServer32", winreg.KEY_WOW64_64KEY, 0)
                winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, CLASS_KEY, winreg.KEY_WOW64_64KEY, 0)
                entry["result"] = "Removed only the verified project-owned HKCU COM class"
            else:
                if args.action == "register" and (before["HKCU"]["com"] or before["HKLM"]["com"] or
                                                    before["HKCU"]["tip"] or before["HKLM"]["tip"]):
                    raise RuntimeError("Project identity already registered; refusing to overwrite existing entries.")
                if args.action == "unregister":
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLASS_KEY + r"\InprocServer32") as key:
                        registered, _ = winreg.QueryValueEx(key, "")
                    if Path(registered).resolve() != path:
                        raise RuntimeError("Registration does not point at the requested project DLL.")
                library = ctypes.WinDLL(str(path), use_last_error=True)
                operation = getattr(library, "DllRegisterServer" if args.action == "register" else "DllUnregisterServer")
                operation.argtypes = []
                operation.restype = ctypes.c_long
                result = operation()
                entry["hresult"] = f"0x{result & 0xffffffff:08X}"
                entry["succeeded"] = result >= 0
    except Exception as error:
        entry["error"] = str(error)
    entry["after"] = snapshot()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a", encoding="utf-8") as output:
        output.write(json.dumps(entry, ensure_ascii=True) + "\n")
    print(json.dumps(entry, ensure_ascii=True, indent=2))
    return 1 if "error" in entry or entry.get("succeeded") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
