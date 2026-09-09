import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from parking_sentinel.simulator import make_server, MEDIA


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:%s' % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_video_preview_has_no_scripted_or_payment_endpoints(self):
        with urllib.request.urlopen(self.base) as response:
            page = response.read().decode()
            self.assertIn('generateContent', page)
            self.assertIn(MEDIA, page)
            self.assertNotIn('Scripted rule tests', page)
            self.assertIn('https://generativelanguage.googleapis.com', response.headers['Content-Security-Policy'])
        for path in ('/api/event', '/api/frame', '/api/reset', '/checkout'):
            request = urllib.request.Request(self.base + path, data=b'{}')
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 405)
        request = urllib.request.Request(self.base, headers={'Host': 'external.example'})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 403)

    def test_video_ranges_support_playback_and_seeking(self):
        media = Path(__file__).resolve().parents[1] / 'parking_sentinel/media' / MEDIA
        for route in ('/media/', '/parking_sentinel/media/'):
            request = urllib.request.Request(self.base + route + MEDIA, headers={'Range': 'bytes=0-31'})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), media.read_bytes()[:32])
                self.assertEqual(response.headers['Content-Range'], 'bytes 0-31/%s' % media.stat().st_size)
        request = urllib.request.Request(self.base + '/media/' + MEDIA, headers={'Range': 'bytes=-16'})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.read(), media.read_bytes()[-16:])
        request = urllib.request.Request(self.base + '/media/' + MEDIA, headers={'Range': 'bytes=999999999-'})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 416)


if __name__ == '__main__':
    unittest.main()
