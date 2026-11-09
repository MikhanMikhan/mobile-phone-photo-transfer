# iphone_photos_app.py — единое приложение: GUI + AFC-логика (для сборки в .exe)
import asyncio, datetime, os, queue, threading, tkinter as tk
from tkinter import filedialog, ttk

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.afc import AfcService

VIDEO_EXT = {'.mov', '.mp4', '.m4v'}
SKIP_EXT = {'.aae'}


async def list_dcim(afc):
    files = []
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


async def sync(dest, start, end, flat, workers, say):
    say(f'Период: {start} .. {end}\n')
    try:
        lockdown = await create_using_usbmux(autopair=False)
    except Exception as e:
        say(f'Не вижу iPhone: {e}\nПроверьте кабель и «Доверять» на экране.\n')
        return
    afc = AfcService(lockdown)
    say('Читаю список файлов с iPhone...\n')
    all_files = await list_dcim(afc)
    sel = [f for f in all_files
           if start <= datetime.date.fromtimestamp(f[2]) <= end]
    say(f'На iPhone: {len(all_files)} файлов; в периоде: {len(sel)} '
        f'({sum(f[1] for f in sel) / 2**30:.1f} ГБ)\n')

    os.makedirs(dest, exist_ok=True)
    sem = asyncio.Semaphore(workers)
    stats = {'ok': 0, 'skip': 0, 'fail': 0}
    failures = []

    def target_for(name, mts):
        if flat:
            return os.path.join(dest, name)
        dt = datetime.datetime.fromtimestamp(mts)
        kind = 'видео' if os.path.splitext(name)[1].lower() in VIDEO_EXT else 'фото'
        return os.path.join(dest, dt.strftime('%Y-%m-%d'), kind, name)

    async def worker(path, size, mts):
        name = os.path.basename(path)
        target = target_for(name, mts)
        if os.path.exists(target) and os.path.getsize(target) == size:
            stats['skip'] += 1
            return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        async with sem:
            err = None
            for _ in range(3):
                try:
                    data = await afc.get_file_contents(path)
                    if len(data) != size:
                        raise IOError(f'размер {len(data)} != {size}')
                    with open(target, 'wb') as fh:
                        fh.write(data)
                    stats['ok'] += 1
                    if stats['ok'] % 100 == 0:
                        say(f"скопировано {stats['ok']}\n")
                    return
                except Exception as e:
                    err = e
                    await asyncio.sleep(1)
            stats['fail'] += 1
            failures.append(f'{name}: {err}')

    await asyncio.gather(*(worker(*f) for f in sel))
    say(f"ГОТОВО. скопировано={stats['ok']} уже было={stats['skip']} "
        f"ошибок={stats['fail']}\n")
    if failures:
        with open(os.path.join(dest, 'unfixable.txt'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(failures))
        say('Список ошибок: unfixable.txt\n')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Фото с iPhone')
        pad = {'padx': 8, 'pady': 4}

        f = ttk.Frame(self); f.pack(fill='x', **pad)
        ttk.Label(f, text='Папка:').pack(side='left')
        self.dest = ttk.Entry(f, width=42)
        self.dest.pack(side='left', padx=4)
        ttk.Button(f, text='Обзор…', command=self.browse).pack(side='left')

        self.mode = tk.StringVar(value='month')
        box = ttk.LabelFrame(self, text='Период')
        box.pack(fill='x', **pad)

        r1 = ttk.Frame(box); r1.pack(fill='x', **pad)
        ttk.Radiobutton(r1, text='Месяц (ГГГГ-ММ):', variable=self.mode,
                        value='month').pack(side='left')
        self.month = ttk.Entry(r1, width=10)
        self.month.insert(0, '2026-04')
        self.month.pack(side='left', padx=4)

        ttk.Radiobutton(box, text='Последняя неделя', variable=self.mode,
                        value='last-week').pack(anchor='w', **pad)
        ttk.Radiobutton(box, text='Последний месяц', variable=self.mode,
                        value='last-month').pack(anchor='w', **pad)

        r4 = ttk.Frame(box); r4.pack(fill='x', **pad)
        ttk.Radiobutton(r4, text='Диапазон: с', variable=self.mode,
                        value='range').pack(side='left')
        self.date_from = ttk.Entry(r4, width=12)
        self.date_from.insert(0, '2026-05-01')
        self.date_from.pack(side='left', padx=4)
        ttk.Label(r4, text='по').pack(side='left')
        self.date_to = ttk.Entry(r4, width=12)
        self.date_to.insert(0, '2026-06-15')
        self.date_to.pack(side='left', padx=4)

        self.flat = tk.BooleanVar()
        ttk.Checkbutton(self, text='Без раскладки по дням и фото/видео',
                        variable=self.flat).pack(anchor='w', **pad)

        self.go = ttk.Button(self, text='Старт', command=self.start)
        self.go.pack(**pad)

        self.log = tk.Text(self, width=70, height=14, state='disabled')
        self.log.pack(**pad)
        self.q = queue.Queue()
        self.after(100, self.poll)

    def browse(self):
        d = filedialog.askdirectory()
        if d:
            self.dest.delete(0, 'end')
            self.dest.insert(0, d)

    def start(self):
        dest = self.dest.get().strip()
        if not dest:
            self.say('Укажите папку\n')
            return
        today = datetime.date.today()
        m = self.mode.get()
        try:
            if m == 'month':
                y, mo = map(int, self.month.get().split('-'))
                start = datetime.date(y, mo, 1)
                end = (datetime.date(y + (mo == 12), mo % 12 + 1, 1)
                       - datetime.timedelta(days=1))
            elif m == 'last-week':
                start, end = today - datetime.timedelta(days=7), today
            elif m == 'last-month':
                start, end = today - datetime.timedelta(days=30), today
            else:
                start = datetime.date.fromisoformat(self.date_from.get().strip())
                end = datetime.date.fromisoformat(self.date_to.get().strip())
        except ValueError:
            self.say('Проверьте формат дат (ГГГГ-ММ-ДД)\n')
            return
        self.go.config(state='disabled')
        threading.Thread(target=self.run,
                         args=(dest, start, end, self.flat.get()),
                         daemon=True).start()

    def run(self, dest, start, end, flat):
        try:
            asyncio.run(sync(dest, start, end, flat, 8, self.say))
        except Exception as e:
            self.say(f'Ошибка: {e}\n')
        self.q.put(None)

    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item is None:
                    self.go.config(state='normal')
                else:
                    self.say(item)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def say(self, text):
        self.q.put(text) if threading.current_thread() is not threading.main_thread() \
            else self._append(text)

    def _append(self, text):
        self.log.config(state='normal')
        self.log.insert('end', text)
        self.log.see('end')
        self.log.config(state='disabled')


App().mainloop()
