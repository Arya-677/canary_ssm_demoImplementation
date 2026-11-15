"""Reviewed Memory Leaking Service Implementation.

A self-contained microservice providing deterministic request execution that
progressively accumulates memory in physical RSS with each request to /work.
Binds strictly to loopback (127.0.0.1).
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

# Global leak container retaining byte buffers in physical resident memory
_LEAK_CONTAINER: list[bytearray] = []


class LeakingRequestHandler(BaseHTTPRequestHandler):
    server: "LeakingServer"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send_json(200, {"status": "ok", "service": "leaking_service"})
        elif parsed.path == "/work":
            # Real physical memory accumulation
            leak_mb = float(params.get("leak_mb", [1.0])[0])
            rounds = int(params.get("n", [100])[0])

            t0 = time.perf_counter()
            # Allocate physical memory and keep live reference
            if leak_mb > 0:
                chunk_bytes = int(leak_mb * 1024 * 1024)
                # Initialize with non-zero bytes to ensure OS physically pages it in
                _LEAK_CONTAINER.append(bytearray(b"X" * chunk_bytes))

            data = b"benchmark_workload_seed"
            for _ in range(min(rounds, 1000)):
                data = hashlib.sha256(data).digest()
            latency_ms = (time.perf_counter() - t0) * 1000.0

            total_leaked_mb = sum(len(c) for c in _LEAK_CONTAINER) / (1024 * 1024)

            self._send_json(
                200,
                {
                    "status": "ok",
                    "leaked_mb_this_request": leak_mb,
                    "total_retained_mb": round(total_leaked_mb, 2),
                    "retained_chunks": len(_LEAK_CONTAINER),
                    "latency_ms": round(latency_ms, 3),
                },
            )
        elif parsed.path == "/error":
            # Application-level fault injection for classification testing
            self._send_json(500, {"error": "InternalServerError", "message": "Injected application failure"})
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
        pass


class LeakingServer(HTTPServer):
    def __init__(self, host: str, port: int) -> None:
        super().__init__((host, port), LeakingRequestHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory leaking microservice worker")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (loopback only)")
    parser.add_argument("--port", type=int, default=0, help="Bind port (0 for ephemeral)")
    args = parser.parse_args()

    if args.host not in ("127.0.0.1", "localhost"):
        sys.stderr.write("Error: service may only bind to loopback (127.0.0.1)\n")
        sys.exit(1)

    server = LeakingServer(args.host, args.port)
    assigned_port = server.server_address[1]

    sys.stdout.write(f"LISTENING {assigned_port}\n")
    sys.stdout.flush()

    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
