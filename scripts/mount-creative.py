#!/usr/bin/env python3
"""Mount Creative using macOS NetFS and a Keychain password kept in memory."""
import ctypes as c
import os
import subprocess

if os.path.ismount('/Volumes/Creative'):
    print('Creative is already mounted at /Volumes/Creative.')
    raise SystemExit(0)
r = subprocess.run(['security', 'find-internet-password', '-a', 'egouda',
                    '-s', 'home-server.lan', '-w'], capture_output=True, text=True)
if r.returncode:
    raise SystemExit('Save the Creative password in Keychain with setup-mac-creative.py first.')
password = r.stdout.rstrip('\n')
del r
cf = c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
net = c.CDLL('/System/Library/Frameworks/NetFS.framework/NetFS')
ptr = c.c_void_p
cf.CFStringCreateWithCString.argtypes = [ptr, c.c_char_p, c.c_uint32]
cf.CFStringCreateWithCString.restype = ptr
cf.CFURLCreateWithString.argtypes = [ptr, ptr, ptr]
cf.CFURLCreateWithString.restype = ptr
cf.CFDictionaryCreateMutable.argtypes = [ptr, c.c_long, ptr, ptr]
cf.CFDictionaryCreateMutable.restype = ptr
cf.CFDictionarySetValue.argtypes = [ptr, ptr, ptr]
cf.CFRelease.argtypes = [ptr]
net.NetFSMountURLSync.argtypes = [ptr, ptr, ptr, ptr, ptr, ptr, c.POINTER(ptr)]
net.NetFSMountURLSync.restype = c.c_int
owned = []
def string(value):
    result = cf.CFStringCreateWithCString(None, value.encode(), 0x08000100)
    owned.append(result)
    return result
try:
    url = cf.CFURLCreateWithString(None, string('smb://home-server.lan/Creative'), None)
    owned.append(url)
    key_callbacks = c.addressof((c.c_byte * 48).in_dll(cf, 'kCFTypeDictionaryKeyCallBacks'))
    value_callbacks = c.addressof((c.c_byte * 40).in_dll(cf, 'kCFTypeDictionaryValueCallBacks'))
    options = cf.CFDictionaryCreateMutable(None, 0, key_callbacks, value_callbacks)
    owned.append(options)
    cf.CFDictionarySetValue(options, string('UIOption'), string('NoUI'))
    mounts = ptr()
    result = net.NetFSMountURLSync(url, None, string('egouda'), string(password), options, None, c.byref(mounts))
    if mounts.value:
        owned.append(mounts.value)
    if result or not os.path.ismount('/Volumes/Creative'):
        raise SystemExit(f'Creative mount failed (macOS status {result}); check Tailscale, DNS and credentials.')
    print('Creative mounted in Finder at /Volumes/Creative.')
finally:
    for obj in reversed(owned):
        cf.CFRelease(obj)
