"""Serve the real-frame Gemini video preview on loopback; no payment endpoints."""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MEDIA = "parking-enforcement-staged-60s.mp4"


def make_server(port):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload, content_type="application/json"):
            raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self' https://generativelanguage.googleapis.com; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            allowed = ("127.0.0.1:%s" % self.server.server_port, "localhost:%s" % self.server.server_port)
            if self.headers.get("Host") not in allowed:
                return self.reply(403, {"error": "Loopback host required"})
            if self.path in ("/", "/parking-preview.html"):
                page = Path(__file__).resolve().parents[1] / "parking-preview.html"
                return self.reply(200, page.read_bytes(), "text/html; charset=utf-8")
            if self.path in ("/media/" + MEDIA, "/parking_sentinel/media/" + MEDIA):
                return self.video()
            self.reply(404, {"error": "Not found"})

        def video(self):
            path = Path(__file__).parent / "media" / "parking-enforcement-staged-60s.mp4"
            size = path.stat().st_size
            start, end = 0, size - 1
            partial = self.headers.get("Range")
            if partial:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", partial)
                if not match or not any(match.groups()):
                    return self.reply(416, {"error": "Invalid byte range"})
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = min(int(last), end) if last else end
                else:
                    start = max(0, size - int(last))
                if start > end or start >= size:
                    return self.reply(416, {"error": "Range outside video"})
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if partial:
                self.send_header("Content-Range", "bytes %s-%s/%s" % (start, end, size))
            self.end_headers()
            try:
                with path.open("rb") as source:
                    source.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = source.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Normal when a browser pauses, seeks, or switches clips.

        def do_POST(self):
            self.reply(405, {"error": "This preview has no action endpoints"})

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port=8765):
    server = make_server(port)
    print("Open http://127.0.0.1:%s — video preview; connect Gemini for recognition. Payments disabled. Ctrl+C to stop." % server.server_port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
