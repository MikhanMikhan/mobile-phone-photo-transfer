# transfer.py — ядро переноса фото/видео с устройства на диск.
#
# Шов «Устройство» (Device): любой объект с двумя методами —
#   list_files() -> [(path, size, mtime_unix)]
#   fetch(path, local_target) -> None   (raise при ошибке)
# Реализации: iphone_device.IPhoneDevice, android_device.AndroidDevice.
import datetime
import os
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

VIDEO_EXT = {'.mov', '.mp4', '.m4v'}
SKIP_EXT = {'.aae'}
HEIC_EXT = {'.heic', '.heif'}


def heic_to_jpg(src, dst):
    import pillow_heif
    from PIL import Image
    pillow_heif.register_heif_opener()
    Image.open(src).convert('RGB').save(dst, 'JPEG', quality=95)


class Result(NamedTuple):
    total: int      # файлов на устройстве
    selected: int   # попало в период
    ok: int
    skip: int
    fail: int
    failures: list  # ['имя: ошибка', ...]


def target_path(dest, flat, name, mts):
    if flat:
        return os.path.join(dest, name)
    dt = datetime.datetime.fromtimestamp(mts)
    kind = 'видео' if os.path.splitext(name)[1].lower() in VIDEO_EXT else 'фото'
    return os.path.join(dest, dt.strftime('%Y-%m-%d'), kind, name)


def run(device, dest, start, end, flat=False, workers=4, say=print,
        progress=None, convert_heic=False):
    """Перенести файлы с device в dest за период [start, end] (date, включительно).
    progress(done, total) вызывается после каждого обработанного файла.
    convert_heic=True: HEIC-файлы сохраняются как .jpg (оригинал удаляется)."""
    """Перенести файлы с device в dest за период [start, end] (date, включительно)."""
    say(f'Период: {start} .. {end}\n')
    say('Читаю список файлов с устройства...\n')
    all_files = [(p, s, m) for p, s, m in device.list_files()
                 if os.path.splitext(p)[1].lower() not in SKIP_EXT]
    sel = [f for f in all_files
           if start <= datetime.date.fromtimestamp(f[2]) <= end]
    say(f'На устройстве: {len(all_files)} файлов; в периоде: {len(sel)} '
        f'({sum(f[1] for f in sel) / 2**30:.1f} ГБ)\n')

    os.makedirs(dest, exist_ok=True)
    stats = {'done': 0, 'ok': 0, 'skip': 0, 'fail': 0}
    failures = []

    def worker(path, size, mts):
        name = os.path.basename(path)
        try:
            target = target_path(dest, flat, name, mts)
            heic = (convert_heic
                    and os.path.splitext(name)[1].lower() in HEIC_EXT)
            final = (os.path.splitext(target)[0] + '.jpg') if heic else target
            if heic:
                if os.path.exists(final):
                    stats['skip'] += 1
                    return
            elif (os.path.exists(target)
                    and os.path.getsize(target) == size
                    and abs(os.path.getmtime(target) - mts) < 2):
                stats['skip'] += 1
                return
            os.makedirs(os.path.dirname(target), exist_ok=True)
            err = None
            for _ in range(3):
                try:
                    device.fetch(path, target)
                    if os.path.getsize(target) != size:
                        raise IOError(
                            f'размер {os.path.getsize(target)} != {size}')
                    if heic:
                        heic_to_jpg(target, final)
                        os.remove(target)
                    os.utime(final, (mts, mts))
                    stats['ok'] += 1
                    return
                except Exception as e:
                    err = e
            stats['fail'] += 1
            failures.append(f'{name}: {err}')
        finally:
            stats['done'] += 1
            if progress:
                progress(stats['done'], len(sel))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda f: worker(*f), sel))

    say(f"ГОТОВО. скопировано={stats['ok']} уже было={stats['skip']} "
        f"ошибок={stats['fail']}\n")
    if failures:
        with open(os.path.join(dest, 'unfixable.txt'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(failures))
        say('Список ошибок: unfixable.txt\n')
    return Result(len(all_files), len(sel), stats['ok'], stats['skip'],
                  stats['fail'], failures)
