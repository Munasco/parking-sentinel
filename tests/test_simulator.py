import base64
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from parking_sentinel.simulator import Simulation, make_server, synthetic_observation


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.simulation = Simulation(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_guided_sequence_uses_real_rules_and_duplicate_guard(self):
        results = [self.simulation.process(synthetic_observation(kind)) for kind in
                   ("ordinary", "known", "known", "uncertain")]
        self.assertEqual([r["action"] for r in results], ["ignored", "simulated", "suppressed", "ignored"])
        self.assertEqual([r["reason"] for r in results], ["no_match", "plate_match", "plate_match", "below_threshold"])
        self.assertTrue(all(r["payment_enabled"] is False for r in results))
        self.simulation.reset()
        self.assertEqual(self.simulation.process(synthetic_observation("visual"))["action"], "simulated")

    def test_frame_passes_bytes_to_vision_and_deletes_temporary_file(self):
        visited = []
        raw = b"\xff\xd8\xffsynthetic-test-transport"

        def vision(paths):
            visited.append(paths[0])
            self.assertEqual(Path(paths[0]).read_bytes(), raw)
            return synthetic_observation("visual")

        with patch("parking_sentinel.simulator.analyze", side_effect=vision):
            result = self.simulation.frame(base64.b64encode(raw).decode())
        self.assertEqual(result["action"], "simulated")
        self.assertFalse(Path(visited[0]).exists())

    def test_bad_frames_and_scenarios_rejected(self):
        for data in (None, "!notbase64", ""):
            with self.assertRaises(ValueError):
                self.simulation.frame(data)
        with self.assertRaises(ValueError):
            synthetic_observation("pay")

    def test_http_demo_and_token_boundary(self):
        server = make_server(0, self.simulation)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%s" % server.server_port
        try:
            with urllib.request.urlopen(base) as response:
                page = response.read().decode()
                self.assertIn(self.simulation.token, page)
                self.assertNotIn("__SIMULATION_TOKEN__", page)
            request = urllib.request.Request(base + "/api/event", data=b'{"scenario":"known"}', headers={"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 403)
            request.add_header("X-Simulation-Token", self.simulation.token)
            with patch("parking_sentinel.core.ParkGraph.start", side_effect=AssertionError("No payment allowed")), patch("parking_sentinel.core.AmpCheckout.start", side_effect=AssertionError("No checkout allowed")):
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(json.load(response)["action"], "simulated")
            with urllib.request.urlopen(base + "/api/config") as response:
                self.assertEqual(json.load(response)["session_status"], "active")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
