# iphone_photos_gui.py — окно для iphone_photos.py
# Запуск: uv run --with pymobiledevice3 python iphone_photos_gui.py
import os, queue, subprocess, sys, threading, tkinter as tk
from tkinter import filedialog, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, 'iphone_photos.py')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Фото с iPhone')
        self.resizable(False, False)
        pad = {'padx': 8, 'pady': 4}

        f = ttk.Frame(self)
        f.pack(fill='x', **pad)
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
        args = ['uv', 'run', '--with', 'pymobiledevice3', 'python', SCRIPT, dest]
        m = self.mode.get()
        if m == 'month':
            args += ['--month', self.month.get().strip()]
        elif m == 'range':
            args += ['--from', self.date_from.get().strip(),
                     '--to', self.date_to.get().strip()]
        else:
            args += [f'--{m}']
        if self.flat.get():
            args.append('--flat')
        self.go.config(state='disabled')
        self.say('$ ' + ' '.join(args) + '\n')
        threading.Thread(target=self.run, args=(args,), daemon=True).start()

    def run(self, args):
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding='utf-8', errors='replace', env=env)
        for line in proc.stdout:
            self.q.put(line)
        proc.wait()
        self.q.put(f'\n[завершено, код {proc.returncode}]\n')
        self.q.put(None)

    def poll(self):
        try:
            while True:
                line = self.q.get_nowait()
                if line is None:
                    self.go.config(state='normal')
                else:
                    self.say(line)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def say(self, text):
        self.log.config(state='normal')
        self.log.insert('end', text)
        self.log.see('end')
        self.log.config(state='disabled')


App().mainloop()
