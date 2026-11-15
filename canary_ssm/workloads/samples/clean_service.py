"""Reviewed Clean Service Implementation.

A self-contained microservice providing deterministic request execution without
accumulating resident memory. Binds strictly to loopback (127.0.0.1).
This service is completely independent and has zero imports from the test harness.
"""
import argparse
import hashlib
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


class CleanRequestHandler(BaseHTTPRequestHandler):
    server: "CleanServer"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send_json(200, {"status": "ok", "service": "clean_service"})
        elif parsed.path == "/work":
            # Perform bounded computation without retaining memory
            rounds = int(params.get("n", [500])[0])
            t0 = time.perf_counter()
            data = b"benchmark_workload_seed"
            for _ in range(min(rounds, 10000)):
                data = hashlib.sha256(data).digest()
            latency_ms = (time.perf_counter() - t0) * 1000.0

            self._send_json(
                200,
                {
                    "status": "ok",
                    "rounds": rounds,
                    "latency_ms": round(latency_ms, 3),
                },
            )
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/shutdown":
            self._send_json(200, {"status": "shutting down"})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self._send_json(404, {"error": "not found"})

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Suppress noisy standard server logging to stdout
        pass


class CleanServer(HTTPServer):
    def __init__(self, host: str, port: int) -> None:
        super().__init__((host, port), CleanRequestHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean microservice worker")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (loopback only)")
    parser.add_argument("--port", type=int, default=0, help="Bind port (0 for ephemeral)")
    args = parser.parse_args()

    # Enforce loopback only
    if args.host not in ("127.0.0.1", "localhost"):
        sys.stderr.write("Error: service may only bind to loopback (127.0.0.1)\n")
        sys.exit(1)

    server = CleanServer(args.host, args.port)
    assigned_port = server.server_address[1]

    # Deterministic signal to parent harness: print LISTENING port
    sys.stdout.write(f"LISTENING {assigned_port}\n")
    sys.stdout.flush()

    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
