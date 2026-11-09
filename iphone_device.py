# iphone_device.py — адаптер iPhone (AFC) к шову Device из transfer.py.
# pymobiledevice3 асинхронный, поэтому внутри крутится свой event loop
# в фоновом потоке; наружу — обычные синхронные методы.
import asyncio
import datetime
import threading

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.afc import AfcService


class IPhoneDevice:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._afc = self._call(self._connect())

    def _call(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    async def _connect(self):
        try:
            lockdown = await create_using_usbmux(autopair=False)
        except Exception as e:
            raise RuntimeError(f'Не вижу iPhone: {e}\n'
                               f'Проверьте кабель и «Доверять» на экране.')
        return AfcService(lockdown)

    def list_files(self):
        return self._call(self._list_dcim())

    async def _list_dcim(self):
        files = []
        for d in await self._afc.listdir('/DCIM'):
            if not d.endswith('APPLE'):
                continue
            sub = f'/DCIM/{d}'
            try:
                names = await self._afc.listdir(sub)
            except Exception:
                continue
            for f in names:
                st = await self._afc.stat(f'{sub}/{f}')
                mt = st['st_mtime']
                mts = (mt.timestamp() if isinstance(mt, datetime.datetime)
                       else float(mt))
                files.append((f'{sub}/{f}', int(st['st_size']), mts))
        return files

    def fetch(self, path, target):
        data = self._call(self._afc.get_file_contents(path))
        with open(target, 'wb') as fh:
            fh.write(data)
