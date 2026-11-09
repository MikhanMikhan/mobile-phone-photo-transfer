# iphone_photos_app.py — GUI для переноса фото с телефона (для сборки в .exe).
# Тонкий адаптер: вся логика — в transfer.py, устройства — в *_device.py.
import datetime
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import transfer
from iphone_photos import make_device


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Фото с телефона')
        pad = {'padx': 8, 'pady': 4}

        dev = ttk.LabelFrame(self, text='Устройство')
        dev.pack(fill='x', **pad)
        self.device = tk.StringVar(value='iphone')
        ttk.Radiobutton(dev, text='iPhone', variable=self.device,
                        value='iphone').pack(side='left', **pad)
        ttk.Radiobutton(dev, text='Android', variable=self.device,
                        value='android').pack(side='left', **pad)

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
                         args=(dest, start, end, self.flat.get(),
                               self.device.get()),
                         daemon=True).start()

    def run(self, dest, start, end, flat, device):
        try:
            dev = make_device(device == 'android')
            transfer.run(dev, dest, start, end, flat=flat, workers=4,
                         say=self.say)
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
                    self._append(item)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def say(self, text):
        if threading.current_thread() is threading.main_thread():
            self._append(text)
        else:
            self.q.put(text)

    def _append(self, text):
        self.log.config(state='normal')
        self.log.insert('end', text)
        self.log.see('end')
        self.log.config(state='disabled')


App().mainloop()
