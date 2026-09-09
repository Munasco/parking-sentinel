import concurrent.futures
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from parking_sentinel.core import AmpCheckout, DryRun, ParkGraph, ServiceError, Sessions, analyze, decide


def observation(**overrides):
    return dict(dict(plate="", confidence=0.99, white=True, nissan=True, roof_lpr=True, blue_side_marking=True), **overrides)


class Decisions(unittest.TestCase):
    def test_exact_plate_normalization(self):
        self.assertEqual(decide(observation(plate="TEST 123", white=False), ["test123"]), "plate_match")

    def test_visual_fallback_requires_all_attributes(self):
        self.assertEqual(decide(observation(), []), "visual_match")
        for key in ("white", "nissan", "roof_lpr", "blue_side_marking"):
            self.assertEqual(decide(observation(**{key: False}), []), "no_match")

    def test_low_confidence_plate_is_ignored(self):
        self.assertEqual(decide(observation(plate="TEST123", confidence=0.5), ["TEST123"]), "below_threshold")

    def test_reject_malformed_model_output(self):
        for data in (observation(confidence=float("nan")), observation(confidence=True), observation(confidence=1.1), observation(white="true"), observation(plate=None), {}, [], observation(unexpected=True)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                decide(data, [])


class Persistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.sqlite3"
        self.store = Sessions(self.path)
        self.provider = DryRun()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_duplicate_survives_restart_and_end_allows_new_session(self):
        self.assertEqual(self.store.start(self.provider, "lot", "TEST123")["action"], "simulated")
        self.store.close()
        self.store = Sessions(self.path)
        self.assertEqual(self.store.start(self.provider, "lot", "TEST123")["action"], "suppressed")
        self.store.end(self.provider, "lot", "TEST123")
        self.assertEqual(self.store.start(self.provider, "lot", "TEST123")["action"], "simulated")

    def test_timeout_never_retries(self):
        with patch.object(self.provider, "start", side_effect=ServiceError("timeout")) as start:
            with self.assertRaises(ServiceError):
                self.store.start(self.provider, "lot", "TEST123")
            self.assertEqual(self.store.start(self.provider, "lot", "TEST123")["status"], "pending")
            self.assertEqual(start.call_count, 1)

    def test_unknown_receipt_remains_pending(self):
        with patch.object(self.provider, "start", return_value={"success": True}):
            with self.assertRaises(ServiceError):
                self.store.start(self.provider, "lot", "TEST123")
        self.assertEqual(self.store.status(self.provider, "lot", "TEST123"), "pending")

    def test_end_timeout_blocks_duplicate_end(self):
        self.store.start(self.provider, "lot", "TEST123")
        with patch.object(self.provider, "end", side_effect=ServiceError("timeout")) as end:
            for _ in range(2):
                with self.assertRaises(ServiceError):
                    self.store.end(self.provider, "lot", "TEST123")
            self.assertEqual(end.call_count, 1)
        self.assertEqual(self.store.status(self.provider, "lot", "TEST123"), "ending")

    def test_concurrent_detections_create_once(self):
        def run(_):
            store = Sessions(self.path)
            try:
                return store.start(self.provider, "lot", "TEST123")["action"]
            finally:
                store.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(run, range(8)))
        self.assertEqual(results.count("simulated"), 1)
        self.assertEqual(results.count("suppressed"), 7)

    def test_amp_checkout_never_claims_payment(self):
        with patch("webbrowser.open", return_value=True), patch.dict(os.environ, {"AMP_CHECKOUT_URL": "https://aimsmobilepay.com/"}):
            result = self.store.start(AmpCheckout(), "lot", "TEST123")
        self.assertEqual(result, {"status": "awaiting_payment", "action": "checkout_opened"})

    def test_missing_browser_leaves_pending(self):
        with patch("webbrowser.open", return_value=False), self.assertRaises(ServiceError):
            self.store.start(AmpCheckout(), "lot", "TEST123")
        self.assertEqual(self.store.status(AmpCheckout(), "lot", "TEST123"), "pending")


class HttpContract(unittest.TestCase):
    def test_wrapped_session_response(self):
        with patch.dict(os.environ, {"PARKGRAPH_API_KEY": "test-key"}), patch("parking_sentinel.core.request_json", return_value={"session": {"id": "test", "session_code": "code"}}):
            self.assertEqual(ParkGraph().start("lot", "TEST123"), {"id": "test", "session_code": "code"})

    def test_search_rejects_invalid_coordinates(self):
        with patch.dict(os.environ, {"PARKGRAPH_API_KEY": "test-key"}):
            for lat, lng, radius in ((91, 0, 5), (0, 181, 5), (0, 0, -1), (float("nan"), 0, 5)):
                with self.assertRaises(ValueError):
                    ParkGraph().search(lat, lng, radius)

    def test_vision_and_provider_requests(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path, body, self.headers.get("Authorization")))
                if self.path == "/api/chat":
                    result = {"message": {"content": json.dumps(observation())}}
                elif self.path == "/sessions":
                    result = {"id": "test-session", "session_code": "test-code"}
                else:
                    result = {"status": "ended"}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:%s" % server.server_port
            with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"PARKGRAPH_API_KEY": "test-key", "OLLAMA_URL": base, "OLLAMA_MODEL": "test-vision"}):
                image = Path(folder) / "test.png"
                image.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic-transport-fixture")
                self.assertEqual(decide(analyze([image]), []), "visual_match")
                provider = ParkGraph()
                provider.base = base
                receipt = provider.start("test-lot", "TEST123")
                provider.end(receipt)
            self.assertEqual(requests[0][0], "/api/chat")
            self.assertFalse(requests[0][1]["stream"])
            self.assertEqual(len(requests[0][1]["messages"][0]["images"]), 1)
            self.assertEqual(requests[1], ("/sessions", {"lot_id": "test-lot", "plate": "TEST123"}, "Bearer test-key"))
            self.assertEqual(requests[2][1], {"session_id": "test-session", "session_code": "test-code"})
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
