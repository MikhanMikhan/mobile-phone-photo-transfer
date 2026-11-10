# iphone_photos.py — консольное копирование фото/видео с телефона.
#
# Режимы выбора периода (один из):
#   --month 2026-04              за указанный месяц
#   --last-week                  за последние 7 дней
#   --last-month                 за последние 30 дней
#   --from 2026-05-01 --to 2026-06-15   произвольный диапазон (включительно)
#
# Прочее:
#   --android                    Android вместо iPhone
#   --flat                       не раскладывать по дням и фото/видео
#   --workers 4                  число параллельных скачиваний
#
# Запуск:  python iphone_photos.py ПАПКА --month 2026-04
import argparse
import datetime

import transfer


def parse_args():
    p = argparse.ArgumentParser(description='Копирование фото с телефона')
    p.add_argument('dest', help='куда копировать')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--month', help='ГГГГ-ММ, напр. 2026-04')
    g.add_argument('--last-week', action='store_true', help='последние 7 дней')
    g.add_argument('--last-month', action='store_true', help='последние 30 дней')
    g.add_argument('--from', dest='date_from', help='с даты ГГГГ-ММ-ДД (нужен и --to)')
    p.add_argument('--to', help='по дату ГГГГ-ММ-ДД (включительно)')
    p.add_argument('--android', action='store_true', help='Android вместо iPhone')
    p.add_argument('--ip', help='IP телефона для Android по Wi-Fi')
    p.add_argument('--flat', action='store_true', help='без раскладки по дням и фото/видео')
    p.add_argument('--jpeg', action='store_true', help='конвертировать HEIC в JPEG')
    p.add_argument('--workers', type=int, default=4)
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


def make_device(android, ip=None):
    if android:
        from android_device import AndroidDevice
        return AndroidDevice(ip=ip or None)
    from iphone_device import IPhoneDevice
    return IPhoneDevice()


if __name__ == '__main__':
    args, start, end = parse_args()
    try:
        device = make_device(args.android, args.ip)
    except RuntimeError as e:
        raise SystemExit(e)
    transfer.run(device, args.dest, start, end, flat=args.flat,
                 workers=args.workers, convert_heic=args.jpeg)
