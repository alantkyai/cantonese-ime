"""Isolated mapped-image replacement experiment; never accesses live install paths."""
from __future__ import annotations

import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / '.local/native/packages/preview-20261022-persistent-final/native/CantoneseIME.dll'
NEW = ROOT / '.local/native/packages/preview-20261022-adaptive-compact-final/native/CantoneseIME.dll'
OLD_PIN = 'f22d1c0f376e1aa93908bdc7420374d36fe35ed78c6e018e0086fd34aeba0a2d'
NEW_PIN = '4a5e1138f77d45ed9c406e1f4cb4113531095c005f816accf06bd881d5c002cc'
INVALID = c.c_void_p(-1).value
k = c.WinDLL('kernel32', use_last_error=True)
k.LoadLibraryW.argtypes = [w.LPCWSTR]; k.LoadLibraryW.restype = w.HMODULE
k.FreeLibrary.argtypes = [w.HMODULE]; k.FreeLibrary.restype = w.BOOL
k.GetProcAddress.argtypes = [w.HMODULE,c.c_char_p]; k.GetProcAddress.restype = c.c_void_p
k.CreateFileW.argtypes = [w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
k.CreateFileW.restype = w.HANDLE
k.CloseHandle.argtypes = [w.HANDLE]; k.CloseHandle.restype = w.BOOL
k.ReadFile.argtypes = [w.HANDLE,c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.c_void_p]; k.ReadFile.restype = w.BOOL
k.SetFilePointerEx.argtypes = [w.HANDLE,c.c_longlong,c.c_void_p,w.DWORD]; k.SetFilePointerEx.restype = w.BOOL
k.SetFileInformationByHandle.argtypes = [w.HANDLE,c.c_int,c.c_void_p,w.DWORD]
k.SetFileInformationByHandle.restype = w.BOOL

def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def emit(value):
    print(json.dumps(value, ensure_ascii=False),flush=True)

def child(path: Path):
    original_hash = digest(path)
    handle = k.LoadLibraryW(str(path))
    if not handle:
        raise c.WinError(c.get_last_error())
    try:
        address = k.GetProcAddress(handle,b'DllCanUnloadNow')
        if not address:
            raise c.WinError(c.get_last_error())
        call = c.WINFUNCTYPE(c.c_long)(address)
        def probe():
            return {'pid':__import__('os').getpid(),'module':int(handle),'function':int(address),
                    'function_bytes_sha256':hashlib.sha256(c.string_at(address,64)).hexdigest(),
                    'dll_can_unload_hresult':call(),'loaded_disk_sha256':original_hash,'pointer_bits':c.sizeof(c.c_void_p)*8}
        emit({'ready':True,**probe()})
        for line in sys.stdin:
            if line.strip()=='probe': emit(probe())
            elif line.strip()=='exit': break
            else: raise ValueError('Unexpected child command')
    finally:
        k.FreeLibrary(handle)

def start(path: Path):
    process = subprocess.Popen([sys.executable,'-I','-u',str(Path(__file__).resolve()),'--child',str(path)],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                               creationflags=0x08000000)
    line = process.stdout.readline()
    if not line:
        _,errors=process.communicate(timeout=10)
        raise RuntimeError(f'Child failed before ready: {errors}')
    return process,json.loads(line)

def end(process):
    if process.poll() is None:
        output,errors=process.communicate('exit\n',timeout=10)
    else:
        output,errors=process.communicate(timeout=10)
    if process.returncode:
        raise RuntimeError(f'Fixture child failed: {process.returncode}: {errors}')
    return {'exit_code':process.returncode,'stderr':errors}

def hash_handle(handle):
    if not k.SetFilePointerEx(handle,0,None,0): raise c.WinError(c.get_last_error())
    checksum=hashlib.sha256(); block=c.create_string_buffer(65536); count=w.DWORD()
    while True:
        if not k.ReadFile(handle,block,len(block),c.byref(count),None): raise c.WinError(c.get_last_error())
        if not count.value: break
        checksum.update(block.raw[:count.value])
    return checksum.hexdigest()

def rename(handle,target):
    name=str(target).encode('utf-16-le'); raw=c.create_string_buffer(22+len(name))
    c.c_uint32.from_buffer(raw,16).value=len(name)
    c.memmove(c.addressof(raw)+20,name,len(name))
    if not k.SetFileInformationByHandle(handle,3,raw,len(raw)): raise c.WinError(c.get_last_error())

def trial(root: Path, name: str, access: int, share: int):
    directory=root/name; directory.mkdir()
    canonical=directory/'CantoneseIME.dll'; retired=directory/'retired.dll'
    shutil.copyfile(OLD,canonical)
    process,before=start(canonical); newer=None; held=None
    report={'name':name,'access':hex(access),'sharing':hex(share),'before':before}
    try:
        held=k.CreateFileW(str(canonical),access,share,None,3,0,None)
        if held==INVALID:
            report['open_succeeded']=False; report['open_winerror']=c.get_last_error()
            held=None; return report
        report['open_succeeded']=True; report['held_hash_before']=hash_handle(held)
        try: rename(held,retired)
        except OSError as error:
            report['rename_succeeded']=False; report['rename_winerror']=error.winerror; return report
        report['rename_succeeded']=True
        report['old_path_absent_after_rename']=not canonical.exists()
        report['held_hash_after_rename']=hash_handle(held)
        shutil.copyfile(NEW,canonical)
        report['new_path_sha256']=digest(canonical)
        process.stdin.write('probe\n'); process.stdin.flush()
        report['old_process_after_publish']=json.loads(process.stdout.readline())
        newer,new_before=start(canonical); report['new_process_after_publish']=new_before
        report['old_mapping_stable']=(before['module']==report['old_process_after_publish']['module'] and
                                     before['function_bytes_sha256']==report['old_process_after_publish']['function_bytes_sha256'] and
                                     report['old_process_after_publish']['dll_can_unload_hresult']==0)
        report['new_process_loaded_new_disk_hash']=new_before['loaded_disk_sha256']==NEW_PIN
        # A no-write handle still pins identity and refuses subsequent incompatible writes.
        writer=k.CreateFileW(str(retired),0x40000000,7,None,3,0,None)
        report['retired_write_open_succeeded']=writer!=INVALID
        if writer!=INVALID: k.CloseHandle(writer)
        else: report['retired_write_open_winerror']=c.get_last_error()
        # Rollback must never overwrite the fresh canonical file while it exists.
        try:
            rename(held,canonical)
        except OSError as error:
            report['rollback_existing_target_refused']=True
            report['rollback_existing_target_winerror']=error.winerror
        else:
            raise RuntimeError('Mapped rename unexpectedly replaced an existing target')
        report['new_child_exit']=end(newer); newer=None
        new_handle=k.CreateFileW(str(canonical),0xC0010000,0,None,3,0,None)
        if new_handle==INVALID: raise c.WinError(c.get_last_error())
        try:
            rename(new_handle,directory/'new-withdrawn.dll')
            rename(held,canonical)
            report['rollback_old_handle_sha256']=hash_handle(held)
            process.stdin.write('probe\n'); process.stdin.flush()
            report['old_process_after_rollback']=json.loads(process.stdout.readline())
            report['mapped_rollback_succeeded']=(report['rollback_old_handle_sha256']==OLD_PIN and
                report['old_process_after_rollback']['module']==before['module'] and
                report['old_process_after_rollback']['function_bytes_sha256']==before['function_bytes_sha256'] and
                report['old_process_after_rollback']['dll_can_unload_hresult']==0)
        finally:
            k.CloseHandle(new_handle)
        return report
    finally:
        if newer is not None: report['new_child_exit']=end(newer)
        if held is not None: k.CloseHandle(held)
        report['old_child_exit']=end(process)
        if retired.exists(): report['retained_old_disk_sha256']=digest(retired)
        report['final_canonical_sha256']=digest(canonical)

def main():
    global OLD, NEW, OLD_PIN, NEW_PIN
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--child',type=Path)
    parser.add_argument('--old-dll',type=Path,default=OLD); parser.add_argument('--new-dll',type=Path,default=NEW)
    parser.add_argument('--old-sha256',default=OLD_PIN); parser.add_argument('--new-sha256',default=NEW_PIN)
    parser.add_argument('--output',type=Path,default=ROOT/'.local/native/mapped-image-upgrade-proof.json')
    args=parser.parse_args()
    if args.child: child(args.child); return
    OLD=args.old_dll.resolve(strict=True); NEW=args.new_dll.resolve(strict=True)
    OLD_PIN=args.old_sha256; NEW_PIN=args.new_sha256
    output=args.output.resolve()
    output.relative_to(ROOT)
    if c.sizeof(c.c_void_p)!=8: raise ValueError('Run this Windows fixture with 64-bit Python')
    if digest(OLD)!=OLD_PIN or digest(NEW)!=NEW_PIN: raise ValueError('Pinned package DLL changed')
    root=ROOT/'.local/native/mapped-image-fixtures'/uuid.uuid4().hex; root.mkdir(parents=True)
    trials=[]
    for name,access,share in [('write_delete_exclusive',0xC0010000,0),
                              ('read_delete_share_read',0x80010000,1),
                              ('read_delete_share_all',0x80010000,7)]:
        trials.append(trial(root,name,access,share))
    result={'captured_at_utc':datetime.now(timezone.utc).isoformat(),'fixture_root':str(root),
            'source_sha256':digest(Path(__file__).resolve()),'old_dll_sha256':OLD_PIN,'new_dll_sha256':NEW_PIN,
            'scope':'Workspace DLL copies in owned child processes only; no installed files, IPC, registration, settings, UI or other processes changed.',
            'trials':trials}
    successful=[row for row in trials if row.get('rename_succeeded')]
    result['passed']=(not trials[0]['open_succeeded'] and len(successful)==2 and all(
        row['old_mapping_stable'] and row['new_process_loaded_new_disk_hash'] and row['mapped_rollback_succeeded'] and
        row['rollback_existing_target_refused'] and not row['retired_write_open_succeeded'] and
        row['held_hash_before']==OLD_PIN and row['held_hash_after_rename']==OLD_PIN and
        row['final_canonical_sha256']==OLD_PIN and row['old_child_exit']['exit_code']==0 and
        row['new_child_exit']['exit_code']==0 for row in successful))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    emit(result)
    if not result['passed']: raise SystemExit(1)

if __name__=='__main__': main()
