"""Loopback-only, payment-free simulator and local video test bench."""
import base64
import binascii
import json
import os
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import DryRun, ServiceError, Sessions, analyze, decide


def synthetic_observation(scenario):
    observation = dict(plate="", confidence=0.99, white=True, nissan=True,
                       roof_lpr=True, blue_side_marking=True)
    if scenario == "ordinary":
        observation.update(white=False, nissan=False, roof_lpr=False, blue_side_marking=False)
    elif scenario == "known":
        observation.update(plate="DEMO123", roof_lpr=False)
    elif scenario == "uncertain":
        observation["confidence"] = 0.60
    elif scenario != "visual":
        raise ValueError("Unknown scenario")
    return observation


class Simulation:
    def __init__(self, directory):
        self.path = Path(directory) / "simulation.sqlite3"
        self.lock = threading.Lock()
        self.provider = DryRun()
        self.token = secrets.token_urlsafe(32)

    def process(self, observation):
        reason = decide(observation, ["DEMO123"])
        with self.lock:
            store = Sessions(self.path)
            try:
                if reason in ("plate_match", "visual_match"):
                    result = store.start(self.provider, "simulation", "DEMO000")
                else:
                    result = {"action": "ignored", "status": store.status(self.provider, "simulation", "DEMO000")}
                return dict(result, reason=reason, observation=observation, payment_enabled=False)
            finally:
                store.close()

    def reset(self):
        with self.lock:
            store = Sessions(self.path)
            try:
                store.reconcile(self.provider, "simulation", "DEMO000")
            finally:
                store.close()
        return {"status": "idle", "payment_enabled": False}

    def status(self):
        with self.lock:
            store = Sessions(self.path)
            try:
                return store.status(self.provider, "simulation", "DEMO000")
            finally:
                store.close()

    def frame(self, encoded):
        if not isinstance(encoded, str):
            raise ValueError("Frame must be base64 JPEG or PNG")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Invalid frame encoding") from None
        if not 1 <= len(raw) <= 5_000_000:
            raise ValueError("Frame too large or empty")
        # Temporary files are removed on both successful and failed inference.
        with tempfile.TemporaryDirectory(prefix="parking-frame-") as directory:
            path = Path(directory) / "frame.jpg"
            path.write_bytes(raw)
            observation = analyze([path])
        return self.process(observation)


def make_server(port, simulation):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload, content_type="application/json"):
            raw = payload if isinstance(payload, bytes) else json.dumps(payload, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src blob:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def valid_host(self):
            return self.headers.get("Host") in ("127.0.0.1:%s" % self.server.server_port, "localhost:%s" % self.server.server_port)

        def do_GET(self):
            if not self.valid_host():
                return self.reply(403, {"error": "Loopback host required"})
            if self.path == "/":
                page = Path(__file__).with_name("simulator.html").read_text()
                page = page.replace("__SIMULATION_TOKEN__", simulation.token)
                return self.reply(200, page.encode(), "text/html; charset=utf-8")
            if self.path == "/api/config":
                return self.reply(200, {"vision_configured": bool(os.environ.get("OLLAMA_MODEL")), "payment_enabled": False, "session_status": simulation.status()})
            self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if not self.valid_host() or not secrets.compare_digest(self.headers.get("X-Simulation-Token", ""), simulation.token):
                return self.reply(403, {"error": "Open the simulator page to start"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 7_000_000:
                    return self.reply(413, {"error": "Request too large or empty"})
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Expected an object")
                if self.path == "/api/event":
                    result = simulation.process(synthetic_observation(body.get("scenario")))
                elif self.path == "/api/frame":
                    result = simulation.frame(body.get("image"))
                elif self.path == "/api/reset":
                    result = simulation.reset()
                else:
                    return self.reply(404, {"error": "Not found"})
                self.reply(200, result)
            except (ValueError, ServiceError) as exc:
                self.reply(400, {"error": str(exc)})
            except OSError:
                self.reply(500, {"error": "Local file or service unavailable"})

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port=8765):
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="parking-simulation-") as directory:
        server = make_server(port, Simulation(directory))
        print("Open http://127.0.0.1:%s — simulation only; payments disabled. Ctrl+C to stop." % server.server_port, flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
