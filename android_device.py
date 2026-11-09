# android_device.py — адаптер Android (adb) к шову Device из transfer.py.
# adb скачивается автоматически (platform-tools от Google) при первом запуске.
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

ADB_URL = 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip'
ADB_DIR = os.path.join(os.environ.get('LOCALAPPDATA', tempfile.gettempdir()),
                       'PhonePhotoTransfer', 'platform-tools')
SOURCES = ['/sdcard/DCIM', '/sdcard/Pictures', '/sdcard/Movies']


def find_adb(say):
    adb = shutil.which('adb')
    if adb:
        return adb
    adb = os.path.join(ADB_DIR, 'adb.exe')
    if os.path.exists(adb):
        return adb
    say('Скачиваю Android platform-tools (adb) с сайта Google...\n')
    os.makedirs(ADB_DIR, exist_ok=True)
    zip_path = os.path.join(ADB_DIR, 'pt.zip')
    urllib.request.urlretrieve(ADB_URL, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        for name in ('platform-tools/adb.exe', 'platform-tools/AdbWinApi.dll',
                     'platform-tools/AdbWinUsbApi.dll'):
            z.extract(name, ADB_DIR)
    os.remove(zip_path)
    say('adb установлен.\n')
    return adb


def _run(adb, args):
    return subprocess.run([adb] + args, capture_output=True, text=True,
                          encoding='utf-8', errors='replace',
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


class AndroidDevice:
    def __init__(self, say=print):
        self._adb = find_adb(say)
        r = _run(self._adb, ['devices'])
        lines = [l for l in r.stdout.splitlines()[1:] if l.strip()]
        if not lines:
            raise RuntimeError('Телефон не найден. Проверьте кабель и '
                               'отладку по USB.')
        if any('unauthorized' in l for l in lines):
            raise RuntimeError('Разрешите отладку по USB на экране телефона.')
        if not any(l.endswith('device') for l in lines):
            raise RuntimeError(f'Странное состояние adb: {r.stdout.strip()}')

    def list_files(self):
        files = []
        for src in SOURCES:
            r = _run(self._adb,
                     ['shell', f"find '{src}' -type f 2>/dev/null"])
            paths = [p.strip() for p in r.stdout.splitlines() if p.strip()]
            for i in range(0, len(paths), 100):
                chunk = paths[i:i + 100]
                q = ' '.join("'" + p.replace("'", "'\\''") + "'" for p in chunk)
                r = _run(self._adb,
                         ['shell', f"stat -c '%n|%s|%Y' {q} 2>/dev/null"])
                for line in r.stdout.splitlines():
                    parts = line.rsplit('|', 2)
                    if len(parts) != 3:
                        continue
                    path, size, mts = parts
                    try:
                        files.append((path, int(size), float(mts)))
                    except ValueError:
                        continue
        return files

    def fetch(self, path, target):
        r = _run(self._adb, ['pull', path, target])
        if r.returncode != 0:
            raise IOError((r.stderr or r.stdout).strip())
