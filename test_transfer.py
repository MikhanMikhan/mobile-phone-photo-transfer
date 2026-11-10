# test_transfer.py — тесты ядра переноса через фейковое устройство (без телефона).
import datetime
import os
import tempfile
import unittest

import transfer

MTS = datetime.datetime(2026, 4, 10, 12, 0, 0).timestamp()
APRIL = (datetime.date(2026, 4, 1), datetime.date(2026, 4, 30))


class FakeDevice:
    """Файлы: {path: bytes}; attempts — счётчик вызовов fetch; fail_times — сколько
    первых попыток по пути должны падать."""
    def __init__(self, files, mtimes=None, fail_times=None):
        self.files = files
        self.mtimes = mtimes or {p: MTS for p in files}
        self.fail_times = fail_times or {}
        self.attempts = {}

    def list_files(self):
        return [(p, len(d), self.mtimes.get(p, MTS))
                for p, d in self.files.items()]

    def fetch(self, path, target):
        self.attempts[path] = self.attempts.get(path, 0) + 1
        if self.attempts[path] <= self.fail_times.get(path, 0):
            raise IOError('сбой')
        with open(target, 'wb') as fh:
            fh.write(self.files[path])


def run(device, dest, **kw):
    kw.setdefault('say', lambda *a: None)
    return transfer.run(device, dest, *APRIL, **kw)


class TransferTest(unittest.TestCase):
    def setUp(self):
        self.dest = tempfile.mkdtemp()

    def test_layout_and_period_filter(self):
        dev = FakeDevice({
            '/DCIM/a.jpg': b'a1',
            '/DCIM/b.mov': b'b22',
            '/DCIM/old.jpg': b'old',
        }, mtimes={'/DCIM/old.jpg':
                   datetime.datetime(2026, 1, 1).timestamp()})
        r = run(dev, self.dest)
        self.assertEqual((r.total, r.selected, r.ok), (3, 2, 2))
        self.assertTrue(os.path.exists(
            os.path.join(self.dest, '2026-04-10', 'фото', 'a.jpg')))
        self.assertTrue(os.path.exists(
            os.path.join(self.dest, '2026-04-10', 'видео', 'b.mov')))

    def test_aae_skipped(self):
        r = run(FakeDevice({'/DCIM/a.aae': b'x'}), self.dest)
        self.assertEqual((r.total, r.selected, r.ok), (0, 0, 0))

    def test_flat(self):
        run(FakeDevice({'/DCIM/a.jpg': b'a1'}), self.dest, flat=True)
        self.assertTrue(os.path.exists(os.path.join(self.dest, 'a.jpg')))

    def test_rerun_skips_by_size_and_mtime(self):
        dev = FakeDevice({'/DCIM/a.jpg': b'a1'})
        run(dev, self.dest)
        r2 = run(dev, self.dest)
        self.assertEqual((r2.ok, r2.skip), (0, 1))

    def test_changed_mtime_recopies(self):
        dev = FakeDevice({'/DCIM/a.jpg': b'a1'})
        run(dev, self.dest)
        t = os.path.join(self.dest, '2026-04-10', 'фото', 'a.jpg')
        os.utime(t, (0, 0))
        r2 = run(dev, self.dest)
        self.assertEqual(r2.ok, 1)

    def test_retry_then_success(self):
        dev = FakeDevice({'/DCIM/a.jpg': b'a1'}, fail_times={'/DCIM/a.jpg': 2})
        r = run(dev, self.dest)
        self.assertEqual((r.ok, r.fail, dev.attempts['/DCIM/a.jpg']), (1, 0, 3))

    def test_failure_recorded_in_unfixable(self):
        dev = FakeDevice({'/DCIM/a.jpg': b'a1'}, fail_times={'/DCIM/a.jpg': 9})
        r = run(dev, self.dest)
        self.assertEqual((r.ok, r.fail), (0, 1))
        with open(os.path.join(self.dest, 'unfixable.txt'),
                  encoding='utf-8') as fh:
            self.assertIn('a.jpg', fh.read())


if __name__ == '__main__':
    unittest.main()
