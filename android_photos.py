# android_photos.py — копирование фото/видео с Android по ADB.
# adb скачивается автоматически (platform-tools от Google) при первом запуске.
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

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


def _run(adb, args, **kw):
    return subprocess.run([adb] + args, capture_output=True, text=True,
                          encoding='utf-8', errors='replace',
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                          **kw)


def list_files(adb, say):
    r = _run(adb, ['devices'])
    lines = [l for l in r.stdout.splitlines()[1:] if l.strip()]
    if not lines:
        raise RuntimeError('Телефон не найден. Проверьте кабель и отладку по USB.')
    if any('unauthorized' in l for l in lines):
        raise RuntimeError('Разрешите отладку по USB на экране телефона.')
    if not any(l.endswith('device') for l in lines):
        raise RuntimeError(f'Странное состояние adb: {r.stdout.strip()}')

    say('Читаю список файлов с Android...\n')
    files = []
    for src in SOURCES:
        r = _run(adb, ['shell', f"find '{src}' -type f 2>/dev/null"])
        paths = [p.strip() for p in r.stdout.splitlines() if p.strip()]
        for i in range(0, len(paths), 100):
            chunk = paths[i:i + 100]
            q = ' '.join("'" + p.replace("'", "'\\''") + "'" for p in chunk)
            r = _run(adb, ['shell', f"stat -c '%n|%s|%Y' {q} 2>/dev/null"])
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


def sync(dest, start, end, target_for, workers, say):
    adb = find_adb(say)
    try:
        all_files = list_files(adb, say)
    except RuntimeError as e:
        say(f'Не вижу Android: {e}\n')
        return
    sel = [f for f in all_files
           if start <= datetime.date.fromtimestamp(f[2]) <= end]
    say(f'На телефоне: {len(all_files)} файлов; в периоде: {len(sel)} '
        f'({sum(f[1] for f in sel) / 2**30:.1f} ГБ)\n')

    os.makedirs(dest, exist_ok=True)
    stats = {'ok': 0, 'skip': 0, 'fail': 0}
    failures = []

    def worker(path, size, mts):
        name = os.path.basename(path)
        target = target_for(name, mts)
        if os.path.exists(target) and os.path.getsize(target) == size:
            stats['skip'] += 1
            return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        err = None
        for _ in range(3):
            r = _run(adb, ['pull', path, target])
            if r.returncode == 0 and os.path.exists(target) \
                    and os.path.getsize(target) == size:
                stats['ok'] += 1
                if stats['ok'] % 100 == 0:
                    say(f"скопировано {stats['ok']}\n")
                return
            err = (r.stderr or r.stdout).strip()
        stats['fail'] += 1
        failures.append(f'{name}: {err}')

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda f: worker(*f), sel))
    say(f"ГОТОВО. скопировано={stats['ok']} уже было={stats['skip']} "
        f"ошибок={stats['fail']}\n")
    if failures:
        with open(os.path.join(dest, 'unfixable.txt'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(failures))
        say('Список ошибок: unfixable.txt\n')
