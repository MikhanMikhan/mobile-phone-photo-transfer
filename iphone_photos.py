# iphone_photos.py — копирование фото/видео с iPhone по протоколу AFC (без MTP).
#
# Режимы выбора периода (один из):
#   --month 2026-04              за указанный месяц
#   --last-week                  за последние 7 дней
#   --last-month                 за последние 30 дней
#   --from 2026-05-01 --to 2026-06-15   произвольный диапазон (включительно)
#
# Прочее:
#   --flat                       не раскладывать по дням и фото/видео
#   --workers 8                  число параллельных скачиваний
#
# Запуск:  uv run --with pymobiledevice3 iphone_photos.py ПАПКА --month 2026-04
import argparse, asyncio, datetime, os, sys

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.afc import AfcService

VIDEO_EXT = {'.mov', '.mp4', '.m4v'}
SKIP_EXT = {'.aae'}


def parse_args():
    p = argparse.ArgumentParser(description='Копирование фото с iPhone по AFC')
    p.add_argument('dest', help='куда копировать')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--month', help='ГГГГ-ММ, напр. 2026-04')
    g.add_argument('--last-week', action='store_true', help='последние 7 дней')
    g.add_argument('--last-month', action='store_true', help='последние 30 дней')
    g.add_argument('--from', dest='date_from', help='с даты ГГГГ-ММ-ДД (нужен и --to)')
    p.add_argument('--to', help='по дату ГГГГ-ММ-ДД (включительно)')
    p.add_argument('--flat', action='store_true', help='без раскладки по дням и фото/видео')
    p.add_argument('--workers', type=int, default=8)
    a = p.parse_args()
    today = datetime.date.today()
    if a.month:
        y, m = map(int, a.month.split('-'))
        start = datetime.date(y, m, 1)
        end = (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1))
    elif a.last_week:
        start, end = today - datetime.timedelta(days=7), today
    elif a.last_month:
        start, end = today - datetime.timedelta(days=30), today
    else:
        if not a.to:
            p.error('--from требует --to')
        start = datetime.date.fromisoformat(a.date_from)
        end = datetime.date.fromisoformat(a.to)
    return a, start, end


async def list_dcim(afc):
    files = []  # (path, size, mtime)
    for d in await afc.listdir('/DCIM'):
        if not d.endswith('APPLE'):
            continue
        sub = f'/DCIM/{d}'
        try:
            names = await afc.listdir(sub)
        except Exception:
            continue
        for f in names:
            if os.path.splitext(f)[1].lower() in SKIP_EXT:
                continue
            st = await afc.stat(f'{sub}/{f}')
            mt = st['st_mtime']
            mts = mt.timestamp() if isinstance(mt, datetime.datetime) else float(mt)
            files.append((f'{sub}/{f}', int(st['st_size']), mts))
    return files


async def main():
    args, start, end = parse_args()
    print(f'Период: {start} .. {end}', flush=True)

    lockdown = await create_using_usbmux(autopair=False)
    afc = AfcService(lockdown)

    print('Читаю список файлов с iPhone...', flush=True)
    all_files = await list_dcim(afc)
    sel = [f for f in all_files
           if start <= datetime.date.fromtimestamp(f[2]) <= end]
    total_bytes = sum(f[1] for f in sel)
    print(f'На iPhone: {len(all_files)} файлов; в периоде: {len(sel)} '
          f'({total_bytes / 2**30:.1f} ГБ)', flush=True)

    os.makedirs(args.dest, exist_ok=True)
    sem = asyncio.Semaphore(args.workers)
    stats = {'ok': 0, 'skip': 0, 'fail': 0}
    failures = []

    def target_for(name, mts):
        if args.flat:
            return os.path.join(args.dest, name)
        dt = datetime.datetime.fromtimestamp(mts)
        kind = 'видео' if os.path.splitext(name)[1].lower() in VIDEO_EXT else 'фото'
        return os.path.join(args.dest, dt.strftime('%Y-%m-%d'), kind, name)

    async def worker(path, size, mts):
        name = os.path.basename(path)
        target = target_for(name, mts)
        if os.path.exists(target) and os.path.getsize(target) == size:
            stats['skip'] += 1
            return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        async with sem:
            for attempt in range(3):
                try:
                    data = await afc.get_file_contents(path)
                    if len(data) != size:
                        raise IOError(f'размер {len(data)} != {size}')
                    with open(target, 'wb') as fh:
                        fh.write(data)
                    stats['ok'] += 1
                    if stats['ok'] % 100 == 0:
                        print(f"скопировано {stats['ok']}", flush=True)
                    return
                except Exception as e:
                    err = e
                    await asyncio.sleep(1)
            stats['fail'] += 1
            failures.append(f'{name}: {err}')

    await asyncio.gather(*(worker(*f) for f in sel))
    print(f"ГОТОВО. скопировано={stats['ok']} уже было={stats['skip']} "
          f"ошибок={stats['fail']}", flush=True)
    if failures:
        with open(os.path.join(args.dest, 'unfixable.txt'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(failures))
        print('Список ошибок: unfixable.txt', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
